#!/usr/bin/env python3
"""
RuView Terminal CSI Receiver & DSP Visualizer
Listens to ESP32 UDP packets (port 5005, ADR-018 format), processes
signals, detects presence/breathing/heart rate/falls, and displays them.
"""

import sys
import os
import socket
import struct
import time
import math
from collections import deque
import numpy as np
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

try:
    from backend.csi_calibration import PresenceCalibration
    from backend.csi_confidence import evaluate_presence_confidence
    from backend.csi_filters import StreamingHampelFilter
    from backend.csi_motion import MotionLevelEstimator, gate_motion_for_quality
    from backend.csi_quality import SignalQualityMonitor
    from backend.csi_recommendations import build_signal_recommendations
    from backend.csi_subcarriers import SubcarrierSelector
    from backend.live_label_evaluator import evaluate_live_labels
    from backend.live_occupancy import classify_occupancy
except ImportError:
    from csi_calibration import PresenceCalibration
    from csi_confidence import evaluate_presence_confidence
    from csi_filters import StreamingHampelFilter
    from csi_motion import MotionLevelEstimator, gate_motion_for_quality
    from csi_quality import SignalQualityMonitor
    from csi_recommendations import build_signal_recommendations
    from csi_subcarriers import SubcarrierSelector
    from live_label_evaluator import evaluate_live_labels
    from live_occupancy import classify_occupancy

# Try importing scipy for butterworth bandpass filters
try:
    from scipy.signal import butter, lfilter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Configuration defaults
BIND_IP = "0.0.0.0"
BIND_PORT = 5005
BUFFER_SIZE = 200
UDP_TIMEOUT_SEC = 0.1
LIVE_LABELS_DIR = "backend/data/live_labels"


def default_evaluator_report():
    return {
        "readiness": {"ready": False},
        "model": {"feature": "filtered_variance", "threshold": 0.0},
    }


def load_evaluator_report(labels_dir=LIVE_LABELS_DIR):
    try:
        return evaluate_live_labels(labels_dir)
    except Exception:
        return default_evaluator_report()

class RuViewDSP:
    def __init__(self, fps=50.0):
        self.fps = fps
        self.raw_history = deque(maxlen=BUFFER_SIZE)
        self.filtered_history = deque(maxlen=BUFFER_SIZE)
        self.resp_history = deque(maxlen=BUFFER_SIZE)
        self.heart_history = deque(maxlen=BUFFER_SIZE)
        
        # Calibration / variance thresholds
        self.presence_threshold = 0.6
        self.fall_threshold = 12.0
        self.presence_calibration = PresenceCalibration(active=False)
        self.spike_filter = StreamingHampelFilter(window_size=9, threshold=3.0, min_spike_delta=5.0)
        self.motion_estimator = MotionLevelEstimator()
        self.motion_state = self.motion_estimator.summary()
        
        # Debouncing/cooldowns
        self.last_fall_time = 0.0
        self.fall_cooldown = 5.0  # seconds
        
        # Exercise Rep Counter
        self.rep_count = 0
        self.rep_state = 0  # 0 = down, 1 = up
        self.last_rep_time = 0.0
        self.last_presence_time = time.time()
        
        # Filter coefficients cache to avoid calling scipy.signal.butter on every sample
        self._filter_cache = {}

    def start_presence_calibration(self, target_samples=60):
        self.presence_calibration = PresenceCalibration(
            min_samples=target_samples,
            min_threshold=self.presence_threshold,
            active=True,
        )
        return self.presence_calibration.summary()

    def reset_presence_calibration(self):
        self.presence_calibration = PresenceCalibration(active=False)
        return self.presence_calibration.summary()
        
    def add_sample(self, raw_val):
        self.motion_state = self.motion_estimator.update(raw_val)
        clean_val = self.spike_filter.update(raw_val)
        self.raw_history.append(clean_val)
        if self.presence_calibration.active:
            self.presence_calibration.add_sample(clean_val)
        
        # 1. Apply EMA Lowpass Denoising (Alpha = 0.2)
        alpha = 0.2
        if len(self.filtered_history) > 0:
            prev = self.filtered_history[-1]
            filtered = alpha * clean_val + (1 - alpha) * prev
        else:
            filtered = clean_val
        self.filtered_history.append(filtered)
        
        # 2. Extract Respiration Band (0.1 - 0.5 Hz)
        resp_val = self._bandpass_filter(list(self.filtered_history), 0.1, 0.5)
        self.resp_history.append(resp_val)
        
        # 3. Extract Heart Rate Band (0.8 - 2.0 Hz)
        heart_val = self._bandpass_filter(list(self.filtered_history), 0.8, 2.0)
        self.heart_history.append(heart_val)
        
    def _bandpass_filter(self, data_list, low, high):
        if len(data_list) < 15:
            return 0.0
            
        data = np.array(data_list, dtype=float)
        # Detrend (remove DC offset)
        data_detrended = data - np.mean(data)
        
        if HAS_SCIPY:
            try:
                cache_key = (low, high, self.fps)
                if cache_key in self._filter_cache:
                    b, a = self._filter_cache[cache_key]
                else:
                    nyq = 0.5 * self.fps
                    low_norm = low / nyq
                    high_norm = high / nyq
                    b, a = butter(2, [low_norm, high_norm], btype='bandpass')
                    self._filter_cache[cache_key] = (b, a)
                y = lfilter(b, a, data_detrended)
                return y[-1]
            except Exception:
                pass
                
        # Software filter fallback (Dual EMA difference)
        # Respiration / Heart rate frequency mapping to fast/slow EMA
        if low == 0.1: # Respiration
            alpha_slow, alpha_fast = 0.03, 0.15
        else: # Heart rate
            alpha_slow, alpha_fast = 0.15, 0.45
            
        EMA_slow = data_detrended[0]
        EMA_fast = data_detrended[0]
        for val in data_detrended:
            EMA_slow = alpha_slow * val + (1 - alpha_slow) * EMA_slow
            EMA_fast = alpha_fast * val + (1 - alpha_fast) * EMA_fast
        return EMA_fast - EMA_slow

    def process_telemetry(self):
        calibration_summary = self.presence_calibration.summary()
        effective_presence_threshold = self.presence_calibration.effective_threshold(self.presence_threshold)

        if len(self.filtered_history) < 30:
            return {
                "presence": False,
                "resp_bpm": 0.0,
                "heart_bpm": 0.0,
                "variance": 0.0,
                "fall_alert": False,
                "acceleration": 0.0,
                "rep_count": 0,
                "effective_presence_threshold": effective_presence_threshold,
                "calibration": calibration_summary,
                "spikes_filtered": self.spike_filter.replaced_count,
                "motion": self.motion_state,
            }
            
        raw_arr = np.array(self.raw_history)
        filtered_arr = np.array(self.filtered_history)
        
        # 1. Presence (using signal variance over last 3 seconds)
        window_size = min(len(raw_arr), int(self.fps * 3))
        recent_raw = raw_arr[-window_size:]
        variance = np.var(recent_raw)
        std_dev = np.std(recent_raw)
        
        presence = (variance > effective_presence_threshold) or (std_dev > (effective_presence_threshold * 0.8))
        
        # Track presence for auto-reset of rep count
        now = time.time()
        if presence:
            self.last_presence_time = now
        elif now - self.last_presence_time > 8.0:
            self.rep_count = 0  # auto-reset after 8 seconds of emptiness
            
        # 2. Respiration Rate (Zero-crossings of respiration wave)
        recent_resp = list(self.resp_history)[-100:]
        resp_bpm = self._compute_bpm_zero_crossing(recent_resp) if presence else 0.0
        
        # 3. Heart Rate
        recent_heart = list(self.heart_history)[-100:]
        heart_bpm = self._compute_bpm_zero_crossing(recent_heart) if presence else 0.0
        # Sanity check for human heart rate
        if heart_bpm < 45 or heart_bpm > 140:
            heart_bpm = 0.0
            
        # 4. Fall Detection (Second derivative of filtered signal)
        acceleration = 0.0
        fall_alert = False
        if len(filtered_arr) > 4:
            # 1st and 2nd derivatives
            d1 = np.diff(filtered_arr[-5:])
            d2 = np.diff(d1)
            acceleration = np.max(np.abs(d2)) if len(d2) > 0 else 0.0
            
            # Trigger check
            if acceleration > self.fall_threshold:
                self.last_fall_time = now
                
            fall_alert = (now - self.last_fall_time) < self.fall_cooldown
            
        # 5. Hysteresis Exercise Rep Counter (runs during presence & active motion)
        if presence and len(filtered_arr) >= 50:
            recent_filtered = filtered_arr[-int(self.fps * 4):]
            mean_val = np.mean(recent_filtered)
            f_std = np.std(recent_filtered)
            curr_val = filtered_arr[-1]
            
            # Only count reps if there is significant active motion
            if f_std > 0.4:
                thresh = max(0.5, 0.5 * f_std)
                if self.rep_state == 0 and curr_val > mean_val + thresh:
                    self.rep_state = 1
                elif self.rep_state == 1 and curr_val < mean_val - thresh:
                    if now - self.last_rep_time > 0.8:
                        self.rep_count += 1
                        self.last_rep_time = now
                    self.rep_state = 0
            
        return {
            "presence": presence,
            "resp_bpm": resp_bpm,
            "heart_bpm": heart_bpm,
            "variance": variance,
            "fall_alert": fall_alert,
            "acceleration": acceleration,
            "rep_count": self.rep_count,
            "effective_presence_threshold": effective_presence_threshold,
            "calibration": self.presence_calibration.summary(),
            "spikes_filtered": self.spike_filter.replaced_count,
            "motion": self.motion_state,
        }
        
    def _compute_bpm_zero_crossing(self, signal):
        if len(signal) < 20:
            return 0.0
        crossings = 0
        for i in range(1, len(signal)):
            if (signal[i-1] < 0 and signal[i] >= 0) or (signal[i-1] >= 0 and signal[i] < 0):
                crossings += 1
        duration = len(signal) / self.fps
        cycles = crossings / 2.0
        bpm = (cycles / duration) * 60.0
        return round(bpm, 1)

def draw_ascii_graph(history, width=50, height=8):
    if not history:
        return ""
    history_slice = list(history)[-width:]
    min_val = min(history_slice)
    max_val = max(history_slice)
    span = max_val - min_val
    if span == 0:
        span = 1.0
        
    grid = [[" " for _ in range(len(history_slice))] for _ in range(height)]
    for col, val in enumerate(history_slice):
        row = int((val - min_val) / span * (height - 1))
        row = max(0, min(height - 1, row))
        grid[height - 1 - row][col] = "#"
        
    lines = ["".join(row) for row in grid]
    lines[0] = f"{max_val:6.1f} | {lines[0]}"
    for r in range(1, height - 1):
        lines[r] = f"       | {lines[r]}"
    lines[height - 1] = f"{min_val:6.1f} | {lines[height - 1]}"
    return "\n".join(lines)


def with_presence_confidence(telemetry, signal_quality):
    enriched = dict(telemetry)
    enriched["motion"] = gate_motion_for_quality(enriched.get("motion", {}), signal_quality)
    enriched["occupancy"] = classify_occupancy(enriched, signal_quality, load_evaluator_report())
    enriched["presence_confidence"] = evaluate_presence_confidence(enriched, signal_quality)
    enriched["recommendations"] = build_signal_recommendations(
        signal_quality,
        enriched["presence_confidence"],
        enriched,
    )
    return enriched

def make_layout(stats, telemetry, dsp):
    # Header Panel
    header_text = Text("RuView -- Terminal WiFi Spatial Intelligence", style="bold cyan")
    header_panel = Panel(header_text, border_style="cyan")
    
    # Telemetry Panel
    confidence = telemetry.get("presence_confidence", {})
    confidence_label = confidence.get("label", "ROOM EMPTY")
    confidence_score = int(confidence.get("score", 0))
    confidence_reasons = ", ".join(confidence.get("reasons", [])[:2]) or "clear"
    if confidence.get("alert_allowed", False):
        presence_str = "[bold green][+] CONFIRMED HUMAN[/bold green]"
    elif telemetry["presence"]:
        presence_str = "[bold yellow][~] UNCONFIRMED MOTION[/bold yellow]"
    else:
        presence_str = "[bold grey][-] ROOM EMPTY[/bold grey]"
    fall_str = "[blink bold red][!] FALL DETECTED![/blink bold red]" if telemetry["fall_alert"] else "[bold green][+] SAFE (No Fall)[/bold green]"
    
    table = Table(show_header=False, box=None)
    table.add_row("Occupancy Status:", presence_str)
    table.add_row("Fall Monitor:", fall_str)
    table.add_row("Breathing Rate:", f"[bold yellow]{telemetry['resp_bpm']} BPM[/bold yellow]" if telemetry['resp_bpm'] > 0 else "Calculating...")
    table.add_row("Est. Heart Rate:", f"[bold magenta]{int(telemetry['heart_bpm'])} BPM[/bold magenta]" if telemetry['heart_bpm'] > 0 else "Calculating...")
    table.add_row("Signal Variance:", f"{telemetry['variance']:.4f}")
    motion = telemetry.get("motion", {})
    table.add_row("Motion Level:", f"{motion.get('display_level', motion.get('level', 'STILL'))} {float(motion.get('score', 0.0) or 0.0):.3f}")
    occupancy = telemetry.get("occupancy", {})
    table.add_row("Occupancy Class:", occupancy.get("class", "UNKNOWN"))
    table.add_row("Presence Threshold:", f"{telemetry.get('effective_presence_threshold', 0.0):.4f}")
    table.add_row("Calibration:", "READY" if telemetry.get("calibration", {}).get("ready") else "MANUAL")
    table.add_row("Confidence Gate:", f"{confidence_score}% {confidence_label}")
    table.add_row("Gate Reason:", confidence_reasons)
    table.add_row("Spikes Filtered:", str(telemetry.get("spikes_filtered", 0)))
    for item in telemetry.get("recommendations", [])[:2]:
        table.add_row("Next Action:", f"{item.get('title', '')}: {item.get('action', '')}")
    table.add_row("Max Acceleration:", f"{telemetry['acceleration']:.2f}")
    table.add_row("Exercise Reps:", f"[bold cyan]{telemetry['rep_count']}[/bold cyan]")
    
    telemetry_panel = Panel(table, title="[bold white]Telemetry[/bold white]", border_style="blue")
    
    # Network Stats Panel
    net_table = Table(show_header=False, box=None)
    net_table.add_row("Node ID:", str(stats.get("node_id", "N/A")))
    net_table.add_row("Frequency:", f"{stats.get('freq_mhz', 'N/A')} MHz")
    net_table.add_row("Sequence:", str(stats.get("seq", "N/A")))
    net_table.add_row("RSSI:", f"{stats.get('rssi', 'N/A')} dBm")
    net_table.add_row("Noise Floor:", f"{stats.get('noise', 'N/A')} dBm")
    net_table.add_row("Rx Speed (FPS):", f"[bold green]{stats.get('fps', 0.0):.1f} FPS[/bold green]")
    selected = stats.get("selected_subcarriers", [])
    if selected:
        net_table.add_row("Top Subcarriers:", ", ".join(str(index) for index in selected[:8]))
    signal_quality = stats.get("signal_quality", {})
    quality_status = signal_quality.get("status", "BAD")
    quality_reasons = ", ".join(signal_quality.get("reasons", [])[:2]) or "stable"
    net_table.add_row("Signal Quality:", f"{quality_status} ({quality_reasons})")
    
    net_panel = Panel(net_table, title="[bold white]Network & Radio[/bold white]", border_style="green")
    
    # ASCII Graphs
    raw_graph = draw_ascii_graph(dsp.raw_history, width=50, height=8)
    resp_graph = draw_ascii_graph(dsp.resp_history, width=50, height=8)
    
    raw_panel = Panel(raw_graph, title="[bold white]Raw Subcarrier Magnitude (Mean)[/bold white]", border_style="cyan")
    resp_panel = Panel(resp_graph, title="[bold white]Extracted Respiration Waveform (0.1-0.5 Hz)[/bold white]", border_style="red")
    
    # Combined Layout
    main_table = Table.grid(expand=True)
    main_table.add_column(ratio=1)
    main_table.add_column(ratio=1)
    main_table.add_row(telemetry_panel, net_panel)
    main_table.add_row(raw_panel, resp_panel)
    
    outer_table = Table.grid(expand=True)
    outer_table.add_row(header_panel)
    outer_table.add_row(main_table)
    
    return outer_table

def parse_adr018_packet(data):
    if len(data) < 20:
        return None
    try:
        magic, node_id, antennas, n_subcarriers, freq_mhz, seq, rssi, noise, reserved = struct.unpack("<IBBHIIbbH", data[:20])
        if magic != 0xC5110001:
            return None
            
        iq_data = data[20:]
        amplitudes = []
        
        # Super-fast inline signed conversion
        for i in range(0, min(len(iq_data), n_subcarriers * 2) - 1, 2):
            I = iq_data[i]
            if I >= 128:
                I -= 256
            Q = iq_data[i + 1]
            if Q >= 128:
                Q -= 256
            amplitudes.append((I * I + Q * Q) ** 0.5)
            
        raw_signal = sum(amplitudes) / len(amplitudes) if amplitudes else 0.0
        
        return {
            "node_id": node_id,
            "seq": seq,
            "rssi": rssi,
            "noise": noise,
            "freq_mhz": freq_mhz,
            "n_subcarriers": n_subcarriers,
            "amplitudes": amplitudes,
            "raw_signal": raw_signal
        }
    except Exception:
        return None

def main():
    console = Console()
    console.print("[bold green]Starting RuView Terminal Ingestion Service...[/bold green]")
    
    # Set up UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((BIND_IP, BIND_PORT))
        console.print(f"[bold green][+] Bound to UDP port {BIND_PORT}. Listening for ESP32 packets...[/bold green]")
    except Exception as e:
        console.print(f"[bold red][-] Failed to bind UDP port {BIND_PORT}: {e}[/bold red]")
        sys.exit(1)
        
    sock.settimeout(UDP_TIMEOUT_SEC)
    
    # DSP & Stats Inits
    dsp = RuViewDSP(fps=50.0)
    quality_monitor = SignalQualityMonitor()
    subcarrier_selector = SubcarrierSelector()
    stats = {
        "node_id": "Offline",
        "seq": 0,
        "rssi": 0,
        "noise": 0,
        "freq_mhz": 0,
        "fps": 0.0,
        "signal_quality": quality_monitor.summary()
    }
    
    packet_counter = 0
    last_fps_time = time.time()
    last_ui_update = 0.0
    telemetry = dsp.process_telemetry()
    
    with Live(make_layout(stats, telemetry, dsp), console=console, refresh_per_second=10) as live:
        try:
            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                    packet = parse_adr018_packet(data)
                    if packet:
                        packet_counter += 1
                        quality_monitor.record_packet(
                            seq=packet["seq"],
                            rssi=packet["rssi"],
                            n_subcarriers=packet["n_subcarriers"],
                            timestamp=time.time(),
                        )
                        stats.update(packet)
                        stats["signal_quality"] = quality_monitor.summary()
                        
                        subcarrier_selection = subcarrier_selector.add_frame(packet["amplitudes"])
                        selected_signal = subcarrier_selection["selected_signal"]
                        stats["selected_subcarriers"] = subcarrier_selection["selected_indices"]
                        stats["selected_signal"] = selected_signal
                        
                        # Add selected subcarrier signal to DSP
                        dsp.add_sample(selected_signal)
                        
                        # Update FPS
                        now = time.time()
                        if now - last_fps_time >= 1.0:
                            stats["fps"] = packet_counter / (now - last_fps_time)
                            packet_counter = 0
                            last_fps_time = now
                            
                            # Dynamically adjust DSP sample rate to fit actual receipt rate
                            if stats["fps"] > 5.0:
                                dsp.fps = stats["fps"]
                                
                except socket.timeout:
                    # Keep updates going even if no packets are arriving
                    pass
                except Exception as e:
                    # Suppress single packet parsing errors
                    pass
                
                # Periodically re-calculate telemetry and refresh UI (max 10 Hz)
                now = time.time()
                if now - last_ui_update >= 0.1:
                    telemetry = dsp.process_telemetry()
                    # If offline for more than 3 seconds, reset FPS
                    if now - last_fps_time > 3.0:
                        stats["fps"] = 0.0
                        stats["node_id"] = "Offline (No Signal)"
                        stats["signal_quality"] = quality_monitor.summary(now=now)
                    telemetry = with_presence_confidence(telemetry, stats.get("signal_quality", {}))
                    live.update(make_layout(stats, telemetry, dsp))
                    last_ui_update = now
                    
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Shutting down terminal receiver...[/bold yellow]")
        finally:
            sock.close()

if __name__ == "__main__":
    main()
