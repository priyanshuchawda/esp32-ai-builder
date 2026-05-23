import streamlit as st
import numpy as np
import pandas as pd
import socket
import struct
import threading
import time
import queue
from collections import deque
import plotly.graph_objects as go

from backend.csi_calibration import PresenceCalibration
from backend.csi_confidence import evaluate_presence_confidence
from backend.csi_quality import SignalQualityMonitor

# Try importing scipy for Butter filters; if unavailable, we use a simple digital filter fallback
try:
    from scipy.signal import butter, lfilter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Try importing serial for COM port fallback
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# Set page configuration with clean title and layout
st.set_page_config(
    page_title="pi RuView -- WiFi Spatial Intelligence",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom retro terminal CSS styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&display=swap');
    
    /* Force monospace retro-terminal styling throughout the app */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #05070a !important;
        color: #33ff33 !important; /* Matrix green default */
        font-family: 'Fira Code', 'Courier New', Courier, monospace !important;
    }
    
    /* Ensure all streamlit texts, labels, and boxes use monospace */
    * {
        font-family: 'Fira Code', 'Courier New', Courier, monospace !important;
    }
    
    /* Style sidebar for a dark terminal appearance */
    [data-testid="stSidebar"] {
        background-color: #0c0f13 !important;
        border-right: 2px solid #1b2028;
    }
    
    /* Custom terminal panel container */
    .terminal-container {
        border: 2px solid #20262e;
        background-color: #090d12 !important;
        border-radius: 4px;
        padding: 16px;
        margin-bottom: 20px;
        box-shadow: 0 0 15px rgba(0, 0, 0, 0.7);
    }
    
    /* Panel titles styled like terminal text blocks */
    .terminal-header {
        font-size: 1.05rem;
        font-weight: bold;
        color: #00ffcc; /* Glowing cyan */
        border-bottom: 2px double #20262e;
        padding-bottom: 6px;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Row styling mimicking terminal tabular output */
    .terminal-row {
        display: flex;
        justify-content: space-between;
        margin-bottom: 8px;
        font-size: 0.95rem;
        border-bottom: 1px dashed rgba(32, 38, 46, 0.4);
        padding-bottom: 4px;
    }
    
    .terminal-label {
        color: #8892b0;
    }
    
    .terminal-value {
        font-weight: bold;
        color: #e6f1ff;
    }
    
    /* Text Color helper utilities matching Rich's terminal styles */
    .cyan-text { color: #00ffcc !important; text-shadow: 0 0 4px rgba(0, 255, 204, 0.3); }
    .green-text { color: #33ff33 !important; text-shadow: 0 0 4px rgba(51, 255, 51, 0.3); }
    .yellow-text { color: #ffeb3b !important; text-shadow: 0 0 4px rgba(255, 235, 59, 0.3); }
    .magenta-text { color: #e91e63 !important; text-shadow: 0 0 4px rgba(233, 30, 99, 0.3); }
    .red-text { color: #ff5555 !important; text-shadow: 0 0 4px rgba(255, 85, 85, 0.3); }
    .grey-text { color: #6a737d !important; }
    
    /* Fall banner mimicking a flashing warning light */
    .fall-banner {
        background-color: rgba(255, 85, 85, 0.15) !important;
        border: 2px solid #ff5555 !important;
        color: #ff5555 !important;
        text-shadow: 0 0 8px rgba(255, 85, 85, 0.6);
        font-size: 1.5rem;
        font-weight: bold;
        text-align: center;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 20px;
        animation: blinker 1s linear infinite;
    }
    
    @keyframes blinker {
        50% { opacity: 0.3; }
    }
</style>
""", unsafe_allow_html=True)

# ----------------- CACHED SHARED RESOURCES -----------------
BUFFER_SIZE = 200


def default_presence_confidence():
    return {
        "score": 0,
        "level": "LOW",
        "alert_allowed": False,
        "label": "ROOM EMPTY",
        "reasons": ["no_presence_decision"],
    }


def with_presence_confidence(telemetry, signal_quality):
    enriched = dict(telemetry)
    enriched["presence_confidence"] = evaluate_presence_confidence(enriched, signal_quality)
    return enriched


def is_human_confirmed(telemetry):
    confidence = telemetry.get("presence_confidence")
    if confidence is None:
        return False
    return bool(confidence.get("alert_allowed", False))

@st.cache_resource
def get_global_resources():
    """Returns persistent, shared objects across sessions and reloads to avoid leaks."""
    standby_telemetry = {
        "presence": False,
        "resp_bpm": 0.0,
        "heart_bpm": 0.0,
        "variance": 0.0,
        "fall_alert": False,
        "acceleration": 0.0,
        "rep_count": 0,
        "effective_presence_threshold": 0.6,
        "calibration": {
            "ready": False,
            "active": False,
            "samples": 0,
            "target_samples": 60,
            "baseline_mean": 0.0,
            "baseline_variance": 0.0,
            "baseline_std": 0.0,
            "threshold": 0.6
        },
        "presence_confidence": default_presence_confidence(),
        "apnea_status": {
            "is_apnea": False,
            "is_hypopnea": False,
            "current_event_duration": 0.0,
            "baseline_br": 0.0,
            "ahi": 0.0,
            "hours": 0.0,
            "events_count": 0,
            "severity": "Insufficient data",
            "events": [],
            "summary": {
                "total_events": 0,
                "apneas": 0,
                "hypopneas": 0,
                "avg_apnea_duration": 0.0,
                "avg_hypopnea_duration": 0.0,
                "max_duration": 0.0,
                "baseline_br": 0.0
            }
        }
    }
    standby_stats = {
        "node_id": "Offline (Standby)",
        "seq": "N/A",
        "rssi": -95,
        "noise": -96,
        "freq_mhz": 0,
        "fps": 0.0,
        "signal_quality": {
            "status": "BAD",
            "fps": 0.0,
            "packets": 0,
            "age_seconds": 0.0,
            "sequence_gaps": 0,
            "rssi_min": 0,
            "rssi_max": 0,
            "rssi_spread": 0,
            "subcarrier_modes": {},
            "reasons": ["no_packets"]
        }
    }
    return {
        "queue": queue.Queue(maxsize=1000),
        "latest_package": {
            "stats": standby_stats,
            "telemetry": standby_telemetry,
            "raw_history": [],
            "filtered_history": [],
            "resp_history": []
        },
        "lock": threading.Lock(),
        "shutdown_event": threading.Event(),
        "config": {
            "presence_threshold": 0.6,
            "fall_threshold": 12.0,
            "calibration_active": False,
            "calibration_reset_requested": False,
            "calibration_target_samples": 60
        }
    }

resources = get_global_resources()
data_queue = resources["queue"]
thread_shutdown = resources["shutdown_event"]
config = resources["config"]

# ----------------- DSP & SENSING ENGINE -----------------

class ApneaDetector:
    def __init__(self, apnea_thresh=3.0, hypopnea_drop=0.5, min_duration_sec=10):
        self.apnea_thresh = apnea_thresh
        self.hypopnea_drop = hypopnea_drop
        self.min_duration_sec = min_duration_sec

        # Rolling baseline (exponential moving average)
        self.baseline_br = None
        self.baseline_alpha = 0.005  # slow adaptation

        # Event tracking
        self.events = []           # list of dicts: {"type": "apnea"/"hypopnea", "start_ts": ts, "end_ts": ts, "duration_sec": dur, "avg_br": br}
        self.current_event = None   # dict: {"type": "apnea"/"hypopnea", "start_ts": ts}
        self.event_samples = []     # list of floats

        # Time tracking
        self.start_time = None
        self.last_time = None
        self.total_samples = 0
        self.hourly_events = {}     # hour_index -> count

    def ingest(self, timestamp, br, presence):
        if not presence:
            # If no presence, reset current event tracking (person left or empty room)
            self.current_event = None
            self.event_samples = []
            return {"is_apnea": False, "is_hypopnea": False, "baseline": self.baseline_br, "br": br}

        if not self.start_time:
            self.start_time = timestamp
        self.last_time = timestamp
        self.total_samples += 1

        # Update baseline (only with "normal" breathing: above 2x apnea threshold, and either no baseline yet or less than 2x baseline)
        if br > self.apnea_thresh * 2 and (self.baseline_br is None or br < self.baseline_br * 2):
            if self.baseline_br is None:
                self.baseline_br = br
            else:
                self.baseline_br = self.baseline_br * (1 - self.baseline_alpha) + br * self.baseline_alpha

        # Detect events
        is_apnea = br < self.apnea_thresh
        is_hypopnea = self.baseline_br is not None and br < self.baseline_br * (1 - self.hypopnea_drop) and not is_apnea
        in_event = is_apnea or is_hypopnea

        if in_event:
            if not self.current_event:
                self.current_event = {
                    "type": "apnea" if is_apnea else "hypopnea",
                    "start_ts": timestamp
                }
                self.event_samples = [br]
            else:
                self.event_samples.append(br)
                # Upgrade hypopnea to apnea if BR drops further
                if is_apnea and self.current_event["type"] == "hypopnea":
                    self.current_event["type"] = "apnea"
        else:
            # Event ended
            if self.current_event:
                duration = timestamp - self.current_event["start_ts"]
                if duration >= self.min_duration_sec:
                    avg_br = sum(self.event_samples) / len(self.event_samples) if self.event_samples else 0.0
                    event = {
                        "type": self.current_event["type"],
                        "start_ts": self.current_event["start_ts"],
                        "end_ts": timestamp,
                        "duration_sec": duration,
                        "avg_br": avg_br
                    }
                    self.events.append(event)
                    
                    # Track hourly
                    hour_idx = int((self.current_event["start_ts"] - self.start_time) // 3600)
                    self.hourly_events[hour_idx] = self.hourly_events.get(hour_idx, 0) + 1
                    
                self.current_event = None
                self.event_samples = []

        return {"is_apnea": is_apnea, "is_hypopnea": is_hypopnea, "baseline": self.baseline_br, "br": br}

    def get_ahi(self):
        if not self.start_time or not self.last_time:
            return {"ahi": 0.0, "hours": 0.0, "events": 0, "severity": "Insufficient data"}
        
        hours = (self.last_time - self.start_time) / 3600.0
        if hours < 0.000277:  # Less than 1 second
            return {"ahi": 0.0, "hours": hours, "events": 0, "severity": "Insufficient data"}
            
        total_events = len(self.events)
        hours_clamped = max(hours, 0.00277)
        ahi = total_events / hours_clamped

        if ahi < 5:
            severity = "Normal"
        elif ahi < 15:
            severity = "Mild"
        elif ahi < 30:
            severity = "Moderate"
        else:
            severity = "Severe"

        return {"ahi": ahi, "hours": hours, "events": total_events, "severity": severity}

    def get_event_summary(self):
        apneas = [e for e in self.events if e["type"] == "apnea"]
        hypopneas = [e for e in self.events if e["type"] == "hypopnea"]
        
        avg_apnea_dur = sum(e["duration_sec"] for e in apneas) / len(apneas) if apneas else 0.0
        avg_hypopnea_dur = sum(e["duration_sec"] for e in hypopneas) / len(hypopneas) if hypopneas else 0.0
        max_dur = max((e["duration_sec"] for e in self.events), default=0.0)
        
        return {
            "total_events": len(self.events),
            "apneas": len(apneas),
            "hypopneas": len(hypopneas),
            "avg_apnea_duration": avg_apnea_dur,
            "avg_hypopnea_duration": avg_hypopnea_dur,
            "max_duration": max_dur,
            "baseline_br": self.baseline_br or 0.0
        }

class RuViewDSP:
    def __init__(self, fps=50.0):
        self.fps = fps
        self.raw_history = deque(maxlen=BUFFER_SIZE)
        self.filtered_history = deque(maxlen=BUFFER_SIZE)
        self.resp_history = deque(maxlen=BUFFER_SIZE)
        self.heart_history = deque(maxlen=BUFFER_SIZE)
        
        # Debouncing/cooldowns
        self.last_fall_time = 0.0
        self.fall_cooldown = 5.0  # seconds
        
        # Exercise Rep Counter
        self.rep_count = 0
        self.rep_state = 0  # 0 = down, 1 = up
        self.last_rep_time = 0.0
        self.last_presence_time = time.time()
        
        # Sleep Apnea & Hypopnea Screener
        self.apnea_detector = ApneaDetector()
        self.last_apnea_check_time = 0.0
        self.presence_calibration = PresenceCalibration(active=False)
        
        # Filter coefficients cache to avoid calling scipy.signal.butter on every sample
        self._filter_cache = {}

    def start_presence_calibration(self, target_samples=60):
        self.presence_calibration = PresenceCalibration(
            min_samples=target_samples,
            min_threshold=0.6,
            active=True,
        )
        return self.presence_calibration.summary()

    def reset_presence_calibration(self):
        self.presence_calibration = PresenceCalibration(active=False)
        return self.presence_calibration.summary()
        
    def add_sample(self, raw_val):
        self.raw_history.append(raw_val)
        if self.presence_calibration.active:
            self.presence_calibration.add_sample(raw_val)
        
        # 1. Apply EMA Lowpass Denoising (Alpha = 0.2)
        alpha = 0.2
        if len(self.filtered_history) > 0:
            prev = self.filtered_history[-1]
            filtered = alpha * raw_val + (1 - alpha) * prev
        else:
            filtered = raw_val
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

    def process_telemetry(self, presence_threshold, fall_threshold):
        calibration_summary = self.presence_calibration.summary()
        effective_presence_threshold = self.presence_calibration.effective_threshold(presence_threshold)

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
                "apnea_status": {
                    "is_apnea": False,
                    "is_hypopnea": False,
                    "current_event_duration": 0.0,
                    "baseline_br": 0.0,
                    "ahi": 0.0,
                    "hours": 0.0,
                    "events_count": 0,
                    "severity": "Insufficient data",
                    "events": [],
                    "summary": {
                        "total_events": 0,
                        "apneas": 0,
                        "hypopneas": 0,
                        "avg_apnea_duration": 0.0,
                        "avg_hypopnea_duration": 0.0,
                        "max_duration": 0.0,
                        "baseline_br": 0.0
                    }
                }
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
            d1 = np.diff(filtered_arr[-5:])
            d2 = np.diff(d1)
            acceleration = np.max(np.abs(d2)) if len(d2) > 0 else 0.0
            
            if acceleration > fall_threshold:
                self.last_fall_time = now
                
            fall_alert = (now - self.last_fall_time) < self.fall_cooldown
            
        # 5. Hysteresis Exercise Rep Counter (runs during presence & active motion)
        if presence and len(filtered_arr) >= 50:
            recent_filtered = filtered_arr[-int(self.fps * 4):]
            mean_val = np.mean(recent_filtered)
            f_std = np.std(recent_filtered)
            curr_val = filtered_arr[-1]
            
            if f_std > 0.4:
                thresh = max(0.5, 0.5 * f_std)
                if self.rep_state == 0 and curr_val > mean_val + thresh:
                    self.rep_state = 1
                elif self.rep_state == 1 and curr_val < mean_val - thresh:
                    if now - self.last_rep_time > 0.8:
                        self.rep_count += 1
                        self.last_rep_time = now
                    self.rep_state = 0
            
        # 6. Sleep Apnea & Hypopnea Screening (throttle to 1 Hz)
        if now - self.last_apnea_check_time >= 1.0:
            self.apnea_detector.ingest(now, resp_bpm, presence)
            self.last_apnea_check_time = now
            
        ahi_info = self.apnea_detector.get_ahi()
        event_summary = self.apnea_detector.get_event_summary()
        
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
            "apnea_status": {
                "is_apnea": self.apnea_detector.current_event is not None and self.apnea_detector.current_event["type"] == "apnea",
                "is_hypopnea": self.apnea_detector.current_event is not None and self.apnea_detector.current_event["type"] == "hypopnea",
                "current_event_duration": now - self.apnea_detector.current_event["start_ts"] if self.apnea_detector.current_event else 0.0,
                "baseline_br": self.apnea_detector.baseline_br or 0.0,
                "ahi": ahi_info["ahi"],
                "hours": ahi_info["hours"],
                "events_count": ahi_info["events"],
                "severity": ahi_info["severity"],
                "events": list(self.apnea_detector.events),
                "summary": event_summary
            }
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

# ----------------- PARSERS & BACKGROUND LOOPS -----------------

def parse_adr018_packet(data):
    if len(data) < 20:
        return None
    try:
        magic, node_id, antennas, n_subcarriers, freq_mhz, seq, rssi, noise, reserved = struct.unpack("<IBBHIIbbH", data[:20])
        if magic != 0xC5110001:
            return None
            
        iq_data = data[20:]
        amplitudes = []
        
        # Fast signed conversion
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
            "raw_signal": raw_signal
        }
    except Exception:
        return None

def apply_calibration_controls(dsp, config):
    if config.get("calibration_reset_requested", False):
        dsp.reset_presence_calibration()
        config["calibration_reset_requested"] = False

    if config.get("calibration_active", False) and not dsp.presence_calibration.active:
        target_samples = int(config.get("calibration_target_samples", 60))
        dsp.start_presence_calibration(target_samples=target_samples)

def update_calibration_config(config, telemetry):
    calibration = telemetry.get("calibration", {})
    if calibration.get("ready") and not calibration.get("active"):
        config["calibration_active"] = False

def udp_receiver_loop(port, shutdown_event, data_queue, config):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))
    except Exception as e:
        if hasattr(data_queue, "put"):
            data_queue.put({"error": f"Failed to bind port {port}: {e}"})
        else:
            with data_queue["lock"]:
                data_queue["latest_package"] = {"error": f"Failed to bind port {port}: {e}"}
        return

    sock.settimeout(0.2)
    
    dsp = RuViewDSP(fps=50.0)
    quality_monitor = SignalQualityMonitor()
    packet_counter = 0
    last_fps_time = time.time()
    
    while not shutdown_event.is_set():
        try:
            data, addr = sock.recvfrom(4096)
            packet = parse_adr018_packet(data)
            if packet:
                apply_calibration_controls(dsp, config)
                quality_monitor.record_packet(
                    seq=packet["seq"],
                    rssi=packet["rssi"],
                    n_subcarriers=packet["n_subcarriers"],
                    timestamp=time.time(),
                )
                packet_counter += 1
                now = time.time()
                if now - last_fps_time >= 1.0:
                    fps = packet_counter / (now - last_fps_time)
                    packet_counter = 0
                    last_fps_time = now
                    if fps > 5.0:
                        dsp.fps = fps
                else:
                    fps = dsp.fps
                
                dsp.add_sample(packet["raw_signal"])
                
                p_thresh = config.get("presence_threshold", 0.6)
                f_thresh = config.get("fall_threshold", 12.0)
                telemetry = dsp.process_telemetry(p_thresh, f_thresh)
                update_calibration_config(config, telemetry)
                signal_quality = quality_monitor.summary(now=time.time())
                telemetry = with_presence_confidence(telemetry, signal_quality)
                
                ui_package = {
                    "stats": {
                        "node_id": packet["node_id"],
                        "seq": packet["seq"],
                        "rssi": packet["rssi"],
                        "noise": packet["noise"],
                        "freq_mhz": packet["freq_mhz"],
                        "fps": fps,
                        "signal_quality": signal_quality
                    },
                    "telemetry": telemetry,
                    "raw_history": list(dsp.raw_history),
                    "filtered_history": list(dsp.filtered_history),
                    "resp_history": list(dsp.resp_history)
                }
                
                if hasattr(data_queue, "put"):
                    if data_queue.full():
                        try: data_queue.get_nowait()
                        except queue.Empty: pass
                    data_queue.put(ui_package)
                else:
                    with data_queue["lock"]:
                        data_queue["latest_package"] = ui_package
        except socket.timeout:
            # Report offline status if no packets received for 3 seconds
            now = time.time()
            if now - last_fps_time > 3.0:
                apply_calibration_controls(dsp, config)
                signal_quality = quality_monitor.summary(now=now)
                p_thresh = config.get("presence_threshold", 0.6)
                f_thresh = config.get("fall_threshold", 12.0)
                telemetry = dsp.process_telemetry(p_thresh, f_thresh)
                update_calibration_config(config, telemetry)
                telemetry["presence"] = False
                telemetry = with_presence_confidence(telemetry, signal_quality)
                
                ui_package = {
                    "stats": {
                        "node_id": "Offline (No Signal)",
                        "seq": "N/A",
                        "rssi": 0,
                        "noise": 0,
                        "freq_mhz": 0,
                        "fps": 0.0,
                        "signal_quality": signal_quality
                    },
                    "telemetry": telemetry,
                    "raw_history": list(dsp.raw_history),
                    "filtered_history": list(dsp.filtered_history),
                    "resp_history": list(dsp.resp_history)
                }
                if hasattr(data_queue, "put"):
                    if data_queue.full():
                        try: data_queue.get_nowait()
                        except queue.Empty: pass
                    data_queue.put(ui_package)
                else:
                    with data_queue["lock"]:
                        data_queue["latest_package"] = ui_package
                last_fps_time = now
        except Exception:
            continue
            
    sock.close()

def serial_receiver_loop(port_name, baud_rate, shutdown_event, data_queue, config):
    if not HAS_SERIAL:
        return
    try:
        ser = serial.Serial(port_name, baud_rate, timeout=0.2)
    except Exception as e:
        if hasattr(data_queue, "put"):
            data_queue.put({"error": f"Failed to open COM port {port_name}: {e}"})
        else:
            with data_queue["lock"]:
                data_queue["latest_package"] = {"error": f"Failed to open COM port {port_name}: {e}"}
        return

    dsp = RuViewDSP(fps=50.0)
    quality_monitor = SignalQualityMonitor()
    packet_counter = 0
    serial_seq = 0
    last_fps_time = time.time()
    
    while not shutdown_event.is_set():
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line or line.startswith("#"):
                continue
            
            parts = line.split(",")
            if len(parts) >= 8:
                apply_calibration_controls(dsp, config)
                ts = int(parts[0])
                rssi = int(parts[1])
                bins = [float(x) for x in parts[2:8]]
                avg_signal = sum(bins) / len(bins)
                packet_counter += 1
                serial_seq += 1
                quality_monitor.record_packet(
                    seq=serial_seq,
                    rssi=rssi,
                    n_subcarriers=len(bins),
                    timestamp=time.time(),
                )
                
                now = time.time()
                if now - last_fps_time >= 1.0:
                    fps = packet_counter / (now - last_fps_time)
                    packet_counter = 0
                    last_fps_time = now
                    if fps > 5.0:
                        dsp.fps = fps
                else:
                    fps = dsp.fps
                
                dsp.add_sample(avg_signal)
                
                p_thresh = config.get("presence_threshold", 0.6)
                f_thresh = config.get("fall_threshold", 12.0)
                telemetry = dsp.process_telemetry(p_thresh, f_thresh)
                update_calibration_config(config, telemetry)
                signal_quality = quality_monitor.summary(now=time.time())
                telemetry = with_presence_confidence(telemetry, signal_quality)
                
                ui_package = {
                    "stats": {
                        "node_id": 1,
                        "seq": serial_seq,
                        "rssi": rssi,
                        "noise": -95,
                        "freq_mhz": 2437,
                        "fps": fps,
                        "signal_quality": signal_quality
                    },
                    "telemetry": telemetry,
                    "raw_history": list(dsp.raw_history),
                    "filtered_history": list(dsp.filtered_history),
                    "resp_history": list(dsp.resp_history)
                }
                
                if hasattr(data_queue, "put"):
                    if data_queue.full():
                        try: data_queue.get_nowait()
                        except queue.Empty: pass
                    data_queue.put(ui_package)
                else:
                    with data_queue["lock"]:
                        data_queue["latest_package"] = ui_package
        except Exception:
            time.sleep(0.01)
            continue
    ser.close()

def generate_simulated_packet(seq, config_dict=None):
    now_ms = int(time.time() * 1000)
    t = time.time()
    
    sim_mode = "Auto Cycle"
    if config_dict:
        sim_mode = config_dict.get("simulation_mode", "Auto Cycle")
        
    # Default parameters
    breathing = 0.0
    heartbeat = 0.0
    motion_spike = 0.0
    fall_spike = 0.0
    human_noise_std = 0.05  # baseline thermal noise
    is_motion = False
    
    if sim_mode == "Auto Cycle":
        # 60-second periodic cycle for sleep apnea/hypopnea pre-screening verification
        cycle_t = t % 60
        if 30 <= cycle_t < 45:
            mode = "Apnea"
        elif 0 <= cycle_t < 15:
            mode = "Hypopnea"
        elif 15 <= cycle_t < 30:
            mode = "Fitness"
        else:
            mode = "Normal Sleeping"
    else:
        mode = sim_mode
        
    if mode == "Apnea":
        # Apnea: breathing ceases, low noise, presence is still active
        breathing = 0.0
        heartbeat = 0.04 * np.sin(2 * np.pi * 1.1 * t)
        human_noise_std = 0.28  # enough to keep variance around 0.1 - 0.2
        is_motion = False
    elif mode == "Hypopnea":
        # Hypopnea: shallow respiration
        breathing = 0.15 * np.sin(2 * np.pi * 0.1 * t)
        heartbeat = 0.04 * np.sin(2 * np.pi * 1.15 * t)
        human_noise_std = 0.28
        is_motion = False
    elif mode == "Fitness":
        # Fitness: large squats/rhythmic movement
        # 4-second squat cycle: large sine wave component to drive variance and triggers
        breathing = 0.8 * np.sin(2 * np.pi * 0.5 * t)  # rapid breathing (30 bpm)
        heartbeat = 0.12 * np.sin(2 * np.pi * 2.0 * t)  # high heart rate (120 bpm)
        # We need a large sine movement for the rep counter
        motion_spike = 2.5 * np.sin(2 * np.pi * 0.25 * t)  # 4-second period
        human_noise_std = 0.6
        is_motion = True
    elif mode == "Normal Sleeping":
        # Sleeping: slow regular breathing
        breathing = 0.5 * np.sin(2 * np.pi * 0.2 * t)  # 12 bpm
        heartbeat = 0.06 * np.sin(2 * np.pi * 1.1 * t)  # 66 bpm
        human_noise_std = 0.30
        is_motion = False
    elif mode == "Fall":
        # Fall detection: large spike
        # We simulate a fall trigger periodically
        fall_cycle = t % 15
        if fall_cycle < 1.5:
            # Huge deceleration spike
            fall_spike = 16.0 * np.exp(-fall_cycle * 4)
        else:
            fall_spike = 0.0
        breathing = 0.2 * np.sin(2 * np.pi * 0.15 * t)  # shallow breathing after fall
        heartbeat = 0.09 * np.sin(2 * np.pi * 1.5 * t)  # rapid heart rate (90 bpm)
        human_noise_std = 0.35
        is_motion = (fall_cycle < 1.0)
    elif mode == "Idle":
        # Idle: standard standing
        breathing = 0.4 * np.sin(2 * np.pi * 0.25 * t)  # 15 bpm
        heartbeat = 0.07 * np.sin(2 * np.pi * 1.25 * t)  # 75 bpm
        # Minor postural sway
        motion_spike = 0.15 * np.sin(2 * np.pi * 0.05 * t)
        human_noise_std = 0.45
        is_motion = False
    elif mode == "Empty Room":
        # Empty room: minimal variance, presence false
        breathing = 0.0
        heartbeat = 0.0
        human_noise_std = 0.05  # below presence threshold
        is_motion = False

    base_signal = 25.0 + breathing + heartbeat + motion_spike + fall_spike
    
    # We add both Gaussian thermal noise and human presence micro-reflections
    raw_signal = base_signal + np.random.normal(0, human_noise_std)
    
    return {
        "timestamp": now_ms,
        "node_id": 1,
        "seq": seq,
        "rssi": -48 + int(np.sin(t/5)*3) if not is_motion else -52 + int(np.random.normal(0, 2)),
        "noise": -96,
        "freq_mhz": 2457,
        "n_subcarriers": 128,
        "raw_signal": raw_signal
    }

def simulator_loop(shutdown_event, data_queue, config):
    dsp = RuViewDSP(fps=25.0)
    quality_monitor = SignalQualityMonitor()
    packet_counter = 0
    last_fps_time = time.time()
    seq = 0
    
    while not shutdown_event.is_set():
        apply_calibration_controls(dsp, config)
        packet = generate_simulated_packet(seq, config)
        seq += 1
        packet_counter += 1
        quality_monitor.record_packet(
            seq=packet["seq"],
            rssi=packet["rssi"],
            n_subcarriers=packet["n_subcarriers"],
            timestamp=time.time(),
        )
        
        now = time.time()
        if now - last_fps_time >= 1.0:
            fps = packet_counter / (now - last_fps_time)
            packet_counter = 0
            last_fps_time = now
            if fps > 5.0:
                dsp.fps = fps
        else:
            fps = dsp.fps
            
        dsp.add_sample(packet["raw_signal"])
        
        p_thresh = config.get("presence_threshold", 0.6)
        f_thresh = config.get("fall_threshold", 12.0)
        telemetry = dsp.process_telemetry(p_thresh, f_thresh)
        update_calibration_config(config, telemetry)
        signal_quality = quality_monitor.summary(now=time.time())
        telemetry = with_presence_confidence(telemetry, signal_quality)
        
        ui_package = {
            "stats": {
                "node_id": packet["node_id"],
                "seq": packet["seq"],
                "rssi": packet["rssi"],
                "noise": packet["noise"],
                "freq_mhz": packet["freq_mhz"],
                "fps": fps,
                "signal_quality": signal_quality
            },
            "telemetry": telemetry,
            "raw_history": list(dsp.raw_history),
            "filtered_history": list(dsp.filtered_history),
            "resp_history": list(dsp.resp_history)
        }
        
        if hasattr(data_queue, "put"):
            if data_queue.full():
                try: data_queue.get_nowait()
                except queue.Empty: pass
            data_queue.put(ui_package)
        else:
            with data_queue["lock"]:
                data_queue["latest_package"] = ui_package
        
        time.sleep(0.04) # 25 Hz simulation rate


# Helper to launch thread safely
def start_receiver_thread(source_mode, port_to_bind, com_port_selected, serial_baud):
    thread_shutdown.clear()
    
    # Empty queue
    while not data_queue.empty():
        try: data_queue.get_nowait()
        except queue.Empty: break
        
    standby_telemetry = {
        "presence": False,
        "resp_bpm": 0.0,
        "heart_bpm": 0.0,
        "variance": 0.0,
        "fall_alert": False,
        "acceleration": 0.0,
        "rep_count": 0,
        "effective_presence_threshold": 0.6,
        "calibration": {
            "ready": False,
            "active": False,
            "samples": 0,
            "target_samples": 60,
            "baseline_mean": 0.0,
            "baseline_variance": 0.0,
            "baseline_std": 0.0,
            "threshold": 0.6
        },
        "presence_confidence": default_presence_confidence(),
        "apnea_status": {
            "is_apnea": False,
            "is_hypopnea": False,
            "current_event_duration": 0.0,
            "baseline_br": 0.0,
            "ahi": 0.0,
            "hours": 0.0,
            "events_count": 0,
            "severity": "Insufficient data",
            "events": [],
            "summary": {
                "total_events": 0,
                "apneas": 0,
                "hypopneas": 0,
                "avg_apnea_duration": 0.0,
                "avg_hypopnea_duration": 0.0,
                "max_duration": 0.0,
                "baseline_br": 0.0
            }
        }
    }
    standby_stats = {
        "node_id": "Offline (Standby)",
        "seq": "N/A",
        "rssi": -95,
        "noise": -96,
        "freq_mhz": 0,
        "fps": 0.0,
        "signal_quality": {
            "status": "BAD",
            "fps": 0.0,
            "packets": 0,
            "age_seconds": 0.0,
            "sequence_gaps": 0,
            "rssi_min": 0,
            "rssi_max": 0,
            "rssi_spread": 0,
            "subcarrier_modes": {},
            "reasons": ["no_packets"]
        }
    }
    with resources["lock"]:
        resources["latest_package"] = {
            "stats": standby_stats,
            "telemetry": standby_telemetry,
            "raw_history": [],
            "filtered_history": [],
            "resp_history": []
        }
        
    if source_mode == "WiFi UDP Receiver":
        t = threading.Thread(
            name="RuViewReceiverThread",
            target=udp_receiver_loop,
            args=(port_to_bind, thread_shutdown, resources, config),
            daemon=True
        )
        t.start()
    elif source_mode == "USB Serial COM Port" and com_port_selected:
        t = threading.Thread(
            name="RuViewReceiverThread",
            target=serial_receiver_loop,
            args=(com_port_selected, serial_baud, thread_shutdown, resources, config),
            daemon=True
        )
        t.start()
    elif source_mode == "Signal Simulator":
        t = threading.Thread(
            name="RuViewReceiverThread",
            target=simulator_loop,
            args=(thread_shutdown, resources, config),
            daemon=True
        )
        t.start()

# ----------------- 3D OBSERVATORY VISUALIZATION -----------------

def get_skeleton_coords(telemetry):
    t = time.time()
    apnea_status = telemetry.get("apnea_status", {})
    is_apnea = apnea_status.get("is_apnea", False)
    is_hypopnea = apnea_status.get("is_hypopnea", False)
    resp_bpm = telemetry.get("resp_bpm", 0.0)
    variance = telemetry.get("variance", 0.0)
    
    # 1. Fall Alert Posture (horizontal collapsed on floor)
    if is_human_confirmed(telemetry) and telemetry.get("fall_alert", False):
        joints = {
            "head": [0.0, 1.2, 0.15],
            "neck": [0.0, 0.9, 0.15],
            "shoulder_l": [-0.3, 0.9, 0.15],
            "shoulder_r": [0.3, 0.9, 0.15],
            "elbow_l": [-0.4, 0.6, 0.15],
            "elbow_r": [0.4, 0.6, 0.15],
            "wrist_l": [-0.3, 0.3, 0.15],
            "wrist_r": [0.3, 0.3, 0.15],
            "hip_l": [-0.2, 0.0, 0.15],
            "hip_r": [0.2, 0.0, 0.15],
            "knee_l": [-0.2, -0.5, 0.15],
            "knee_r": [0.2, -0.5, 0.15],
            "ankle_l": [-0.2, -1.0, 0.15],
            "ankle_r": [0.2, -1.0, 0.15]
        }
        joints["hip_center"] = [0.0, 0.0, 0.15]
        return joints, False

    # 2. Sleeping / Apnea screening posture
    is_sleeping = False
    if is_human_confirmed(telemetry) and (is_apnea or is_hypopnea or variance < 1.0):
        is_sleeping = True
        
    if is_sleeping:
        bed_z = 0.4
        body_z = bed_z + 0.05
        
        freq = resp_bpm / 60.0 if resp_bpm > 0 else 0.0
        chest_amplitude = 0.03 if not is_apnea else 0.0
        if is_hypopnea:
            chest_amplitude = 0.01
        chest_offset = chest_amplitude * np.sin(2 * np.pi * freq * t)
        
        joints = {
            "head": [0.0, 1.2, body_z],
            "neck": [0.0, 0.9, body_z],
            "shoulder_l": [-0.3, 0.9, body_z],
            "shoulder_r": [0.3, 0.9, body_z],
            "elbow_l": [-0.4, 0.6, body_z],
            "elbow_r": [0.4, 0.6, body_z],
            "wrist_l": [-0.2, 0.4, body_z + 0.05 + chest_offset],
            "wrist_r": [0.2, 0.4, body_z + 0.05 + chest_offset],
            "hip_l": [-0.2, 0.0, body_z],
            "hip_r": [0.2, 0.0, body_z],
            "knee_l": [-0.25, -0.5, body_z + 0.05],
            "knee_r": [0.25, -0.5, body_z + 0.05],
            "ankle_l": [-0.2, -1.0, body_z],
            "ankle_r": [0.2, -1.0, body_z]
        }
        joints["hip_center"] = [0.0, 0.0, body_z + chest_offset]
        return joints, True

    # 3. Exercising / Squats posture (indicated by high variance & presence)
    is_exercising = is_human_confirmed(telemetry) and variance >= 1.0
    if is_exercising:
        # 4-second squat cycles
        squat_val = 0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t)
        
        z_head = 1.0 + 0.7 * squat_val
        z_neck = 0.85 + 0.55 * squat_val
        z_shoulder = 0.8 + 0.5 * squat_val
        z_hip = 0.45 + 0.35 * squat_val
        z_knee = 0.25 + 0.15 * squat_val
        z_wrist = z_shoulder + 0.15 - 0.3 * (1.0 - squat_val)
        
        joints = {
            "head": [0.0, 0.0, z_head],
            "neck": [0.0, 0.0, z_neck],
            "shoulder_l": [-0.35, 0.0, z_shoulder],
            "shoulder_r": [0.35, 0.0, z_shoulder],
            "elbow_l": [-0.45, 0.2, z_shoulder - 0.2],
            "elbow_r": [0.45, 0.2, z_shoulder - 0.2],
            "wrist_l": [-0.4, 0.3, z_wrist],
            "wrist_r": [0.4, 0.3, z_wrist],
            "hip_l": [-0.2, 0.0, z_hip],
            "hip_r": [0.2, 0.0, z_hip],
            "knee_l": [-0.3, 0.1, z_knee],
            "knee_r": [0.3, 0.1, z_knee],
            "ankle_l": [-0.25, 0.0, 0.0],
            "ankle_r": [0.25, 0.0, 0.0]
        }
        joints["hip_center"] = [0.0, 0.0, z_hip]
        return joints, False

    # 4. Standard upright idle
    freq = resp_bpm / 60.0 if resp_bpm > 0 else 0.25
    breathing_jitter = 0.01 * np.sin(2 * np.pi * freq * t)
    
    joints = {
        "head": [0.0, 0.0, 1.7 + breathing_jitter],
        "neck": [0.0, 0.0, 1.45 + breathing_jitter],
        "shoulder_l": [-0.35, 0.0, 1.4],
        "shoulder_r": [0.35, 0.0, 1.4],
        "elbow_l": [-0.45, -0.15, 1.1],
        "elbow_r": [0.45, -0.15, 1.1],
        "wrist_l": [-0.35, -0.25, 0.85],
        "wrist_r": [0.35, -0.25, 0.85],
        "hip_l": [-0.2, 0.0, 0.8],
        "hip_r": [0.2, 0.0, 0.8],
        "knee_l": [-0.25, 0.05, 0.4],
        "knee_r": [0.25, 0.05, 0.4],
        "ankle_l": [-0.2, 0.0, 0.0],
        "ankle_r": [0.2, 0.0, 0.0]
    }
    joints["hip_center"] = [0.0, 0.0, 0.8 + breathing_jitter]
    return joints, False

def generate_3d_observatory(telemetry, stats):
    fig = go.Figure()
    
    # 1. Floor grid points matching the green Matrix grid in the image
    grid_x = []
    grid_y = []
    grid_z = []
    for x in np.arange(-4, 4.1, 0.8):
        for y in np.arange(-4, 4.1, 0.8):
            grid_x.append(x)
            grid_y.append(y)
            grid_z.append(0.0)
            
    fig.add_trace(go.Scatter3d(
        x=grid_x, y=grid_y, z=grid_z,
        mode='markers',
        marker=dict(size=4, color='#33ff33', symbol='square', opacity=0.15),
        showlegend=False
    ))
    
    # 2. Concentric Blue WiFi Wave Spheres centered at the Sensor Node
    sensor_pos = [0.0, -4.0, 0.5]
    radii = [1.5, 3.2, 5.0]
    
    sphere_x = []
    sphere_y = []
    sphere_z = []
    
    for r in radii:
        # Longitude curves
        for theta in [0, np.pi/4, np.pi/2, 3*np.pi/4]:
            phi = np.linspace(0, np.pi, 20)
            xs = sensor_pos[0] + r * np.cos(theta) * np.sin(phi)
            ys = sensor_pos[1] + r * np.sin(theta) * np.sin(phi)
            zs = sensor_pos[2] + r * np.cos(phi)
            zs = np.clip(zs, 0.0, None)
            
            sphere_x.extend(list(xs) + [None])
            sphere_y.extend(list(ys) + [None])
            sphere_z.extend(list(zs) + [None])
            
        # Latitude curves
        for phi in [np.pi/4, np.pi/2, 3*np.pi/4]:
            theta = np.linspace(0, 2*np.pi, 30)
            xs = sensor_pos[0] + r * np.cos(theta) * np.sin(phi)
            ys = sensor_pos[1] + r * np.sin(theta) * np.sin(phi)
            zs = sensor_pos[2] + r * np.cos(phi) * np.ones_like(theta)
            zs = np.clip(zs, 0.0, None)
            
            sphere_x.extend(list(xs) + [None])
            sphere_y.extend(list(ys) + [None])
            sphere_z.extend(list(zs) + [None])
            
    fig.add_trace(go.Scatter3d(
        x=sphere_x, y=sphere_y, z=sphere_z,
        mode='lines',
        line=dict(color='rgba(0, 100, 255, 0.18)', width=1.3),
        showlegend=False
    ))

            
    # 3. Sensor Node visualization
    fig.add_trace(go.Scatter3d(
        x=[sensor_pos[0]], y=[sensor_pos[1]], z=[sensor_pos[2]],
        mode='markers+text',
        marker=dict(size=8, color='#00ffcc', symbol='diamond'),
        text=["NODE-1"],
        textposition="top center",
        textfont=dict(color="#00ffcc", family="monospace", size=9),
        showlegend=False
    ))
    
    # 4. Human Body Skeleton (only if present)
    if telemetry.get("presence", False):
        joints, draw_bed = get_skeleton_coords(telemetry)
        
        # Draw Bed mattress frame if sleeping
        if draw_bed:
            bx = [-0.7, 0.7, 0.7, -0.7, -0.7, None,
                  -0.7, 0.7, 0.7, -0.7, -0.7, None,
                  -0.7, -0.7, None, 0.7, 0.7, None,
                  0.7, 0.7, None, -0.7, -0.7]
            by = [-1.2, -1.2, 1.2, 1.2, -1.2, None,
                  -1.2, -1.2, 1.2, 1.2, -1.2, None,
                  -1.2, -1.2, None, -1.2, -1.2, None,
                  1.2, 1.2, None, 1.2, 1.2]
            bz = [0.4, 0.4, 0.4, 0.4, 0.4, None,
                  0.0, 0.0, 0.0, 0.0, 0.0, None,
                  0.4, 0.0, None, 0.4, 0.0, None,
                  0.4, 0.0, None, 0.4, 0.0]
            fig.add_trace(go.Scatter3d(
                x=bx, y=by, z=bz,
                mode='lines',
                line=dict(color='rgba(139, 69, 19, 0.25)', width=2),
                showlegend=False
            ))
            
        # Define bone lines (separated by None segments)
        BONE_CONNECTIONS = [
            ("head", "neck"),
            ("shoulder_l", "shoulder_r"),
            ("shoulder_l", "neck"),
            ("shoulder_r", "neck"),
            ("shoulder_l", "elbow_l"),
            ("elbow_l", "wrist_l"),
            ("shoulder_r", "elbow_r"),
            ("elbow_r", "wrist_r"),
            ("neck", "hip_center"),
            ("hip_l", "hip_center"),
            ("hip_r", "hip_center"),
            ("hip_l", "knee_l"),
            ("knee_l", "ankle_l"),
            ("hip_r", "knee_r"),
            ("knee_r", "ankle_r")
        ]
        
        skeleton_x = []
        skeleton_y = []
        skeleton_z = []
        for start, end in BONE_CONNECTIONS:
            p1 = joints[start]
            p2 = joints[end]
            skeleton_x.extend([p1[0], p2[0], None])
            skeleton_y.extend([p1[1], p2[1], None])
            skeleton_z.extend([p1[2], p2[2], None])
            
        # Green Glowing Bones
        fig.add_trace(go.Scatter3d(
            x=skeleton_x, y=skeleton_y, z=skeleton_z,
            mode='lines',
            line=dict(color='#33ff33', width=5),
            showlegend=False
        ))
        
        # Red Joint Nodes
        jx = [v[0] for v in joints.values()]
        jy = [v[1] for v in joints.values()]
        jz = [v[2] for v in joints.values()]
        fig.add_trace(go.Scatter3d(
            x=jx, y=jy, z=jz,
            mode='markers',
            marker=dict(size=4.5, color='#ff5555', symbol='circle'),
            showlegend=False
        ))
        
    # Configure 3D layout to hide grids/backgrounds for pure terminal look
    fig.update_layout(
        scene=dict(
            xaxis=dict(visible=False, range=[-5, 5]),
            yaxis=dict(visible=False, range=[-5, 5]),
            zaxis=dict(visible=False, range=[0, 5]),
            aspectratio=dict(x=1, y=1, z=0.5),
            camera=dict(
                eye=dict(x=1.6, y=-1.6, z=1.1)
            )
        ),
        paper_bgcolor='#090d12',
        plot_bgcolor='#090d12',
        margin=dict(r=0, l=0, b=0, t=0),
        height=380,
    )
    return fig

# ----------------- MAIN APP USER INTERFACE -----------------

# Terminal-style Header Console
st.markdown("""
<div style='text-align: center; border: 2px solid #20262e; background-color: #090d12; padding: 10px; margin-bottom: 20px; border-radius: 4px; box-shadow: 0 0 10px rgba(0, 255, 204, 0.2);'>
    <h1 style='margin: 0; font-family: monospace; color: #00ffcc; font-size: 2rem; font-weight: bold;'>🔮 pi RuView</h1>
    <div style='color: #8892b0; font-family: monospace; font-size: 0.9rem; margin-top: 5px;'>WiFi Spatial Intelligence Receiver Console</div>
</div>
""", unsafe_allow_html=True)

# Sidebar Configuration
st.sidebar.markdown("### 📶 Console Ingestion")
source_mode = st.sidebar.selectbox(
    "Data Source Mode",
    ["WiFi UDP Receiver", "USB Serial COM Port", "Signal Simulator"]
)

# Sidebar variables
port_to_bind = 5005
com_port_selected = ""
serial_baud = 115200

if source_mode == "WiFi UDP Receiver":
    port_to_bind = st.sidebar.number_input("UDP Bind Port", min_value=1024, max_value=65535, value=5005)
elif source_mode == "USB Serial COM Port":
    if HAS_SERIAL:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            com_port_selected = st.sidebar.selectbox("Select COM Port", ports)
        serial_baud = st.sidebar.number_input("Baud Rate", value=115200)
    else:
        st.sidebar.error("pyserial is not installed.")
else:
    st.sidebar.success("Ingesting simulated spatial signals.")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Calibration Settings")
presence_threshold = st.sidebar.slider("Presence Var Threshold", min_value=0.1, max_value=5.0, value=0.6, step=0.05)
fall_accel_threshold = st.sidebar.slider("Fall Acceleration Threshold", min_value=5.0, max_value=30.0, value=12.0, step=0.5)
calibration_target_samples = st.sidebar.number_input("Empty Calibration Samples", min_value=30, max_value=300, value=60, step=10)

cal_col1, cal_col2 = st.sidebar.columns(2)
start_calibration = cal_col1.button("Calibrate Empty")
reset_calibration = cal_col2.button("Reset Cal")

# Dynamically update background thread configuration
config["presence_threshold"] = presence_threshold
config["fall_threshold"] = fall_accel_threshold
config["calibration_target_samples"] = calibration_target_samples

if start_calibration:
    config["calibration_reset_requested"] = True
    config["calibration_active"] = True

if reset_calibration:
    config["calibration_reset_requested"] = True
    config["calibration_active"] = False

with resources["lock"]:
    sidebar_package = resources.get("latest_package", {})
sidebar_calibration = sidebar_package.get("telemetry", {}).get("calibration", {})
if sidebar_calibration:
    cal_state = "READY" if sidebar_calibration.get("ready") else "ACTIVE" if sidebar_calibration.get("active") else "MANUAL"
    st.sidebar.caption(
        f"Calibration: {cal_state} | "
        f"{sidebar_calibration.get('samples', 0)}/{sidebar_calibration.get('target_samples', calibration_target_samples)} samples | "
        f"threshold {sidebar_calibration.get('threshold', presence_threshold):.2f}"
    )

st.sidebar.markdown("---")
st.sidebar.write("### Controller")

col_btn1, col_btn2 = st.sidebar.columns(2)
start_streaming = col_btn1.button("▶️ Launch")
stop_streaming = col_btn2.button("⏹️ Halt")

# Check current running state
is_running = any(t.name == "RuViewReceiverThread" for t in threading.enumerate())

if stop_streaming:
    if is_running:
        thread_shutdown.set()
        # Wait for thread to stop
        for t in threading.enumerate():
            if t.name == "RuViewReceiverThread":
                t.join(timeout=1.0)
        st.sidebar.success("Sensing engine halted.")
        st.rerun()

if start_streaming:
    if is_running:
        # Halt existing first
        thread_shutdown.set()
        for t in threading.enumerate():
            if t.name == "RuViewReceiverThread":
                t.join(timeout=1.0)
    start_receiver_thread(source_mode, port_to_bind, com_port_selected, serial_baud)
    st.sidebar.success("Sensing engine active.")
    st.rerun()

# Display active state
if is_running:
    st.sidebar.markdown("<div style='color:#33ff33; font-weight:bold; font-size:14px; margin-top:10px;'>● ENGINE ACTIVE</div>", unsafe_allow_html=True)
else:
    st.sidebar.markdown("<div style='color:#6a737d; font-weight:bold; font-size:14px; margin-top:10px;'>○ ENGINE STANDBY</div>", unsafe_allow_html=True)

# ----------------- MAIN REAL-TIME DASHBOARD RENDER -----------------

# Standby placeholders to keep interface populated when not running
standby_telemetry = {
    "presence": False,
    "resp_bpm": 0.0,
    "heart_bpm": 0.0,
    "variance": 0.0,
    "fall_alert": False,
    "acceleration": 0.0,
    "rep_count": 0,
    "effective_presence_threshold": 0.6,
    "calibration": {
        "ready": False,
        "active": False,
        "samples": 0,
        "target_samples": 60,
        "baseline_mean": 0.0,
        "baseline_variance": 0.0,
        "baseline_std": 0.0,
        "threshold": 0.6
    },
    "presence_confidence": default_presence_confidence(),
    "apnea_status": {
        "is_apnea": False,
        "is_hypopnea": False,
        "current_event_duration": 0.0,
        "baseline_br": 0.0,
        "ahi": 0.0,
        "hours": 0.0,
        "events_count": 0,
        "severity": "Insufficient data",
        "events": [],
        "summary": {
            "total_events": 0,
            "apneas": 0,
            "hypopneas": 0,
            "avg_apnea_duration": 0.0,
            "avg_hypopnea_duration": 0.0,
            "max_duration": 0.0,
            "baseline_br": 0.0
        }
    }
}

standby_stats = {
    "node_id": "Offline (Standby)",
    "seq": "N/A",
    "rssi": -95,
    "noise": -96,
    "freq_mhz": 0,
    "fps": 0.0,
    "signal_quality": {
        "status": "BAD",
        "fps": 0.0,
        "packets": 0,
        "age_seconds": 0.0,
        "sequence_gaps": 0,
        "rssi_min": 0,
        "rssi_max": 0,
        "rssi_spread": 0,
        "subcarrier_modes": {},
        "reasons": ["no_packets"]
    }
}

# --- Premium Card Rendering Helpers (HTML/CSS) ---

def draw_vital_signs(telemetry, container):
    heart_bpm = telemetry.get("heart_bpm", 0.0)
    resp_bpm = telemetry.get("resp_bpm", 0.0)
    presence = telemetry.get("presence", False)
    human_confirmed = is_human_confirmed(telemetry)
    variance = telemetry.get("variance", 0.0)
    confidence = telemetry.get("presence_confidence") or {}
    confidence_val = int(confidence.get("score", 0))
    
    # Determine value strings
    heart_str = f"{int(heart_bpm)}" if (human_confirmed and heart_bpm > 0) else "---"
    resp_str = f"{int(resp_bpm)}" if (human_confirmed and resp_bpm > 0) else "---"
    
    # Determine progress bar percentages
    if human_confirmed and heart_bpm > 0:
        heart_pct = min(100, max(0, int((heart_bpm - 40) / 100 * 100)))
    else:
        heart_pct = 0
        
    if human_confirmed and resp_bpm > 0:
        resp_pct = min(100, max(0, int(resp_bpm / 40 * 100)))
    else:
        resp_pct = 0
        
    if presence and not confidence:
        t = time.time()
        var_boost = min(15, int(variance * 10))
        confidence_val = min(98, max(65, int(80 + np.sin(t) * 4 + var_boost)))
    elif not presence:
        confidence_val = 0
        
    html = f"""
    <div class='terminal-container' style='border: 1px solid #1b2028; border-radius: 8px; padding: 20px; background-color: #0c0f13; margin-bottom: 15px;'>
        <div style='color: #8892b0; font-size: 0.75rem; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 20px; font-weight: bold;'>VITAL SIGNS</div>
        
        <!-- Heart Rate Row -->
        <div style='margin-bottom: 20px;'>
            <div style='display: flex; align-items: center; justify-content: space-between;'>
                <div style='display: flex; align-items: center; gap: 8px;'>
                    <span style='color: #ff5555; font-size: 1.1rem;'>❤️</span>
                    <span style='color: #8892b0; font-size: 0.75rem; letter-spacing: 1px;'>HEART RATE</span>
                </div>
                <div style='font-size: 1.6rem; font-weight: bold; color: #fff;'>
                    <span style='color: #ff5555;'>{heart_str}</span> <span style='font-size: 0.85rem; color: #8892b0;'>BPM</span>
                </div>
            </div>
            <div style='background-color: #1b2028; height: 3px; border-radius: 2px; margin-top: 8px; overflow: hidden;'>
                <div style='background-color: #ff5555; width: {heart_pct}%; height: 100%; transition: width 0.3s ease;'></div>
            </div>
        </div>
        
        <!-- Respiration Row -->
        <div style='margin-bottom: 20px;'>
            <div style='display: flex; align-items: center; justify-content: space-between;'>
                <div style='display: flex; align-items: center; gap: 8px;'>
                    <span style='color: #ffeb3b; font-size: 1.1rem;'>🫁</span>
                    <span style='color: #8892b0; font-size: 0.75rem; letter-spacing: 1px;'>RESPIRATION</span>
                </div>
                <div style='font-size: 1.6rem; font-weight: bold; color: #fff;'>
                    <span style='color: #ffeb3b;'>{resp_str}</span> <span style='font-size: 0.85rem; color: #8892b0;'>RPM</span>
                </div>
            </div>
            <div style='background-color: #1b2028; height: 3px; border-radius: 2px; margin-top: 8px; overflow: hidden;'>
                <div style='background-color: #ffeb3b; width: {resp_pct}%; height: 100%; transition: width 0.3s ease;'></div>
            </div>
        </div>
        
        <!-- Confidence Row -->
        <div>
            <div style='display: flex; align-items: center; justify-content: space-between;'>
                <div style='display: flex; align-items: center; gap: 8px;'>
                    <span style='color: #33ff33; font-size: 1.1rem;'>⚖️</span>
                    <span style='color: #8892b0; font-size: 0.75rem; letter-spacing: 1px;'>CONFIDENCE</span>
                </div>
                <div style='font-size: 1.6rem; font-weight: bold; color: #fff;'>
                    <span style='color: #33ff33;'>{confidence_val}</span><span style='font-size: 1.1rem; color: #33ff33;'>%</span>
                </div>
            </div>
            <div style='background-color: #1b2028; height: 3px; border-radius: 2px; margin-top: 8px; overflow: hidden;'>
                <div style='background-color: #33ff33; width: {confidence_val}%; height: 100%; transition: width 0.3s ease;'></div>
            </div>
        </div>
    </div>
    """
    container.markdown(html, unsafe_allow_html=True)


def draw_sleep_apnea(telemetry, container):
    apnea_status = telemetry.get("apnea_status", {})
    if not apnea_status:
        container.empty()
        return
        
    is_apnea = apnea_status.get("is_apnea", False)
    is_hypopnea = apnea_status.get("is_hypopnea", False)
    cur_dur = apnea_status.get("current_event_duration", 0.0)
    baseline_br = apnea_status.get("baseline_br", 0.0)
    ahi = apnea_status.get("ahi", 0.0)
    severity = apnea_status.get("severity", "N/A")
    summary = apnea_status.get("summary", {})
    total_events = summary.get("total_events", 0)
    apneas_count = summary.get("apneas", 0)
    hypopneas_count = summary.get("hypopneas", 0)
    monitored_sec = apnea_status.get("hours", 0.0) * 3600.0
    presence = telemetry.get("presence", False)
    human_confirmed = is_human_confirmed(telemetry)
    
    if not human_confirmed:
        status_str = "<span class='grey-text'>[-] ENGINE INACTIVE</span>"
    elif is_apnea:
        status_str = f"<span class='red-text' style='font-weight:bold;'>⚠️ APNEA DETECTED ({cur_dur:.0f}s)</span>"
    elif is_hypopnea:
        status_str = f"<span class='yellow-text' style='font-weight:bold;'>⚠️ HYPOPNEA DETECTED ({cur_dur:.0f}s)</span>"
    else:
        status_str = "<span class='green-text'>[+] NORMAL BREATHING</span>"
        
    m_mins = int(monitored_sec // 60)
    m_secs = int(monitored_sec % 60)
    monitored_str = f"{m_mins}m {m_secs}s"
    
    if severity == "Normal":
        sev_str = f"<span class='green-text'>{severity}</span>"
    elif severity == "Mild":
        sev_str = f"<span class='yellow-text'>{severity}</span>"
    elif severity == "Moderate":
        sev_str = f"<span class='magenta-text'>{severity}</span>"
    elif severity == "Severe":
        sev_str = f"<span class='red-text' style='font-weight:bold;'>{severity}</span>"
    else:
        sev_str = f"<span class='grey-text'>{severity}</span>"
        
    html = f"""
    <div class='terminal-container' style='border: 1px solid #1b2028; border-radius: 8px; padding: 20px; background-color: #0c0f13; margin-bottom: 15px;'>
        <div class='terminal-header'>Sleep Apnea Screener</div>
        <div class='terminal-row'><span class='terminal-label'>Screener Status:</span><span class='terminal-value'>{status_str}</span></div>
        <div class='terminal-row'><span class='terminal-label'>Baseline BR:</span><span class='terminal-value'>{baseline_br:.1f} BPM</span></div>
        <div class='terminal-row'><span class='terminal-label'>Monitored Time:</span><span class='terminal-value'>{monitored_str}</span></div>
        <div class='terminal-row'><span class='terminal-label'>AHI Index:</span><span class='terminal-value cyan-text'>{ahi:.2f}</span></div>
        <div class='terminal-row'><span class='terminal-label'>AHI Severity:</span><span class='terminal-value'>{sev_str}</span></div>
        <div class='terminal-row'><span class='terminal-label'>Total Events:</span><span class='terminal-value'>{total_events} (A: {apneas_count} / H: {hypopneas_count})</span></div>
    </div>
    """
    container.markdown(html, unsafe_allow_html=True)


def draw_wifi_signal(stats, telemetry, raw_hist, container):
    rssi = stats.get("rssi", -95)
    variance = telemetry.get("variance", 0.0)
    presence = telemetry.get("presence", False)
    signal_quality = stats.get("signal_quality", {})
    quality_status = signal_quality.get("status", "BAD")
    quality_reasons = signal_quality.get("reasons", [])
    quality_color = {
        "GOOD": "#33ff33",
        "WEAK": "#ffeb3b",
        "BAD": "#ff5555",
    }.get(quality_status, "#6a737d")
    quality_reason_text = ", ".join(quality_reasons[:2]) if quality_reasons else "stable"
    confidence = telemetry.get("presence_confidence") or {}
    confidence_label = confidence.get("label", "ROOM EMPTY")
    human_confirmed = is_human_confirmed(telemetry)
    
    # Motion calculations
    motion_val = variance * 0.05 if presence else (0.002 + np.random.uniform(-0.001, 0.001))
    if motion_val < 0: motion_val = 0.0
    
    persons_count = 1 if human_confirmed else 0
    if human_confirmed:
        persons_dots = "<span style='color: #33ff33;'>●</span> <span style='color: #1b2028;'>● ● ● ● ● ● ●</span>"
    elif presence:
        persons_dots = "<span style='color: #ffeb3b;'>●</span> <span style='color: #1b2028;'>● ● ● ● ● ● ●</span>"
    else:
        persons_dots = "<span style='color: #1b2028;'>● ● ● ● ● ● ● ●</span>"
        
    # Generate custom SVG sparkline from raw_hist
    history_slice = list(raw_hist)[-35:]
    if history_slice:
        min_val = min(history_slice)
        max_val = max(history_slice)
        rng = max_val - min_val if max_val != min_val else 1.0
        
        points = []
        width = 240
        height = 35
        for idx, val in enumerate(history_slice):
            x = int(idx * (width / (len(history_slice) - 1)))
            y = int(height - 2 - ((val - min_val) / rng) * (height - 4))
            points.append(f"{x},{y}")
        svg_path = "M " + " L ".join(points)
    else:
        svg_path = "M 0,17 L 240,17"
        
    sparkline_svg = f"""
    <svg width="100%" height="35" viewBox="0 0 240 35" style="margin-top: 15px; overflow: visible;">
        <defs>
            <linearGradient id="sparkline-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="rgba(0, 100, 255, 0.35)" />
                <stop offset="100%" stop-color="rgba(0, 100, 255, 0.0)" />
            </linearGradient>
        </defs>
        <path d="{svg_path} L 240,35 L 0,35 Z" fill="url(#sparkline-grad)" stroke="none" />
        <path d="{svg_path}" fill="none" stroke="#00ffff" stroke-width="1.8" style="filter: drop-shadow(0 0 2px rgba(0, 255, 255, 0.5));" />
    </svg>
    """
    
    html = f"""
    <div class='terminal-container' style='border: 1px solid #1b2028; border-radius: 8px; padding: 20px; background-color: #0c0f13; margin-bottom: 15px;'>
        <div style='color: #8892b0; font-size: 0.75rem; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 20px; font-weight: bold;'>WIFI SIGNAL</div>
        
        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.85rem;'>
            <span style='color: #8892b0; font-family: monospace;'>RSSI</span>
            <span style='font-weight: bold; color: #00ffff; font-family: monospace;'>{rssi} dBm</span>
        </div>

        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.85rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Quality</span>
            <span style='font-weight: bold; color: {quality_color}; font-family: monospace;'>{quality_status}</span>
        </div>

        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.78rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Reason</span>
            <span style='font-weight: bold; color: #00ffff; font-family: monospace; text-align: right;'>{quality_reason_text}</span>
        </div>
        
        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.85rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Variance</span>
            <span style='font-weight: bold; color: #00ffff; font-family: monospace;'>{variance:.2f}</span>
        </div>
        
        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.85rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Motion</span>
            <span style='font-weight: bold; color: #00ffff; font-family: monospace;'>{motion_val:.3f}</span>
        </div>
        
        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.85rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Persons</span>
            <span style='font-weight: bold; color: #00ffff; font-family: monospace; display: flex; align-items: center; gap: 6px;'>
                {persons_count} &nbsp;&nbsp;&nbsp;&nbsp; {persons_dots}
            </span>
        </div>

        <div style='display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.78rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Gate</span>
            <span style='font-weight: bold; color: #00ffff; font-family: monospace; text-align: right;'>{confidence_label}</span>
        </div>
        
        {sparkline_svg}
    </div>
    """
    container.markdown(html, unsafe_allow_html=True)


def draw_presence(telemetry, container):
    presence = telemetry.get("presence", False)
    effective_threshold = telemetry.get("effective_presence_threshold", 0.0)
    calibration = telemetry.get("calibration", {})
    calibration_state = "READY" if calibration.get("ready") else "ACTIVE" if calibration.get("active") else "MANUAL"
    confidence = telemetry.get("presence_confidence") or default_presence_confidence()
    confidence_score = int(confidence.get("score", 0))
    confidence_label = confidence.get("label", "ROOM EMPTY")
    reason_text = ", ".join(confidence.get("reasons", [])[:2]) or "clear"
    
    if is_human_confirmed(telemetry):
        presence_badge = """
        <div style='border: 1px solid #33ff33; background-color: rgba(51, 255, 51, 0.05); color: #33ff33; padding: 10px 16px; border-radius: 4px; font-weight: bold; font-size: 1.1rem; letter-spacing: 2px; display: inline-block; width: 100%; text-shadow: 0 0 6px rgba(51, 255, 51, 0.4); box-sizing: border-box; text-align: center;'>
            CONFIRMED
        </div>
        """
    elif presence:
        presence_badge = """
        <div style='border: 1px solid #ffeb3b; background-color: rgba(255, 235, 59, 0.05); color: #ffeb3b; padding: 10px 16px; border-radius: 4px; font-weight: bold; font-size: 1.1rem; letter-spacing: 2px; display: inline-block; width: 100%; box-sizing: border-box; text-align: center;'>
            VERIFYING
        </div>
        """
    else:
        presence_badge = """
        <div style='border: 1px solid #6a737d; background-color: rgba(106, 115, 125, 0.05); color: #6a737d; padding: 10px 16px; border-radius: 4px; font-weight: bold; font-size: 1.1rem; letter-spacing: 2px; display: inline-block; width: 100%; box-sizing: border-box; text-align: center;'>
            ABSENT
        </div>
        """
        
    html = f"""
    <div class='terminal-container' style='border: 1px solid #1b2028; border-radius: 8px; padding: 15px; background-color: #0c0f13; margin-bottom: 15px; box-sizing: border-box;'>
        <div style='color: #8892b0; font-size: 0.7rem; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px; font-weight: bold; text-align: left;'>PRESENCE</div>
        {presence_badge}
        <div style='display: flex; justify-content: space-between; margin-top: 12px; font-size: 0.78rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Threshold</span>
            <span style='font-weight: bold; color: #00ffcc; font-family: monospace;'>{effective_threshold:.2f}</span>
        </div>
        <div style='display: flex; justify-content: space-between; margin-top: 6px; font-size: 0.78rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Calibration</span>
            <span style='font-weight: bold; color: #00ffcc; font-family: monospace;'>{calibration_state}</span>
        </div>
        <div style='display: flex; justify-content: space-between; margin-top: 6px; font-size: 0.78rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Confidence</span>
            <span style='font-weight: bold; color: #00ffcc; font-family: monospace;'>{confidence_score}%</span>
        </div>
        <div style='display: flex; justify-content: space-between; margin-top: 6px; font-size: 0.72rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Gate</span>
            <span style='font-weight: bold; color: #00ffcc; font-family: monospace; text-align: right;'>{confidence_label}</span>
        </div>
        <div style='display: flex; justify-content: space-between; margin-top: 6px; font-size: 0.72rem;'>
            <span style='color: #8892b0; font-family: monospace;'>Reason</span>
            <span style='font-weight: bold; color: #00ffcc; font-family: monospace; text-align: right;'>{reason_text}</span>
        </div>
    </div>
    """
    container.markdown(html, unsafe_allow_html=True)


def draw_apnea_events(telemetry, container):
    apnea_status = telemetry.get("apnea_status", {})
    events_list = apnea_status.get("events", []) if apnea_status else []
    sorted_events = sorted(events_list, key=lambda x: x["start_ts"], reverse=True)[:6]
    
    rows_html = ""
    if not sorted_events:
        rows_html = "<div class='grey-text' style='text-align:center; padding:15px; font-size: 0.85rem;'>No apnea/hypopnea events logged.</div>"
    else:
        for ev in sorted_events:
            ev_type = ev["type"].upper()
            color_class = "red-text" if ev_type == "APNEA" else "yellow-text"
            time_str = time.strftime('%H:%M:%S', time.localtime(ev["start_ts"]))
            dur = ev["duration_sec"]
            avg_br = ev["avg_br"]
            rows_html += f"""
            <div class='terminal-row' style='font-size: 0.85rem;'>
                <span class='terminal-label'>[{time_str}] <span class='{color_class}'>{ev_type}</span></span>
                <span class='terminal-value'>Dur: {dur:.1f}s | Avg BR: {avg_br:.1f}</span>
            </div>
            """
            
    html = f"""
    <div class='terminal-container' style='border: 1px solid #1b2028; border-radius: 8px; padding: 20px; background-color: #0c0f13; margin-bottom: 15px;'>
        <div class='terminal-header'>Apnea Event Log</div>
        {rows_html}
    </div>
    """
    container.markdown(html, unsafe_allow_html=True)


def draw_indicators_and_keys(telemetry, container):
    presence = is_human_confirmed(telemetry)
    variance = telemetry.get("variance", 0.0)
    
    # Determine mode active state
    is_sleeping = False
    apnea_status = telemetry.get("apnea_status", {})
    if apnea_status:
        is_apnea = apnea_status.get("is_apnea", False)
        is_hypopnea = apnea_status.get("is_hypopnea", False)
        if presence and (is_apnea or is_hypopnea or variance < 1.0):
            is_sleeping = True
            
    is_exercising = presence and variance >= 1.0
    
    # Gesture vs Gait colors (Gesture is active when idle/sleeping, Gait is active during fitness/squatting)
    if not presence:
        gesture_color = "#404b56"
        gesture_bg = "transparent"
        gait_color = "#404b56"
        gait_bg = "transparent"
    elif is_exercising:
        gesture_color = "#404b56"
        gesture_bg = "transparent"
        gait_color = "#33ff33"
        gait_bg = "rgba(51, 255, 51, 0.1)"
    else:
        gesture_color = "#ffeb3b"
        gesture_bg = "rgba(255, 235, 59, 0.1)"
        gait_color = "#404b56"
        gait_bg = "transparent"
        
    html = f"""
    <div style='display: flex; justify-content: center; gap: 15px; margin-top: 15px; margin-bottom: 15px;'>
        <span style='border: 1px solid {gesture_color}; color: {gesture_color}; background-color: {gesture_bg}; padding: 3px 14px; border-radius: 12px; font-size: 0.8rem; font-weight: bold; letter-spacing: 0.5px; transition: all 0.3s ease;'>GESTURE</span>
        <span style='border: 1px solid {gait_color}; color: {gait_color}; background-color: {gait_bg}; padding: 3px 14px; border-radius: 12px; font-size: 0.8rem; font-weight: bold; letter-spacing: 0.5px; transition: all 0.3s ease;'>GAIT</span>
    </div>
    <div style='display: flex; justify-content: center; gap: 15px; color: #404b56; font-size: 0.75rem; font-family: monospace; border-top: 1px solid #1b2028; padding-top: 12px; margin-top: 5px;'>
        <span>[A] Orbit</span>
        <span>[D] Scenario</span>
        <span>[F] FPS</span>
        <span>[S] Settings</span>
        <span>[Space] Pause</span>
    </div>
    """
    container.markdown(html, unsafe_allow_html=True)


# --- 3-Column Dashboard Structure ---

# Custom dark template for Plotly graphs to match terminal
plotly_layout_args = dict(
    paper_bgcolor='#090d12',
    plot_bgcolor='#090d12',
    font=dict(family="Fira Code, Courier New, monospace", color="#8892b0", size=10),
    xaxis=dict(
        showgrid=True, 
        gridcolor='#1b2028', 
        zeroline=False, 
        showticklabels=False,
        linecolor='#20262e',
        mirror=True
    ),
    yaxis=dict(
        showgrid=True, 
        gridcolor='#1b2028', 
        zeroline=False,
        linecolor='#20262e',
        mirror=True
    ),
    margin=dict(l=40, r=10, t=30, b=10),
    height=250,
)

@st.fragment(run_every=0.5)
def render_dashboard(is_running, source_mode):
    # Extract the latest package safely from the global resources under lock
    with resources["lock"]:
        latest_package = resources["latest_package"]
        
    # Check for error reported by background thread
    if latest_package and "error" in latest_package:
        st.error(latest_package["error"])
        thread_shutdown.set()
        st.rerun()

    # Determine stats, telemetry, and histories to render
    if is_running and latest_package:
        stats = latest_package["stats"]
        telemetry = latest_package["telemetry"]
        raw_hist = latest_package["raw_history"]
        filt_hist = latest_package["filtered_history"]
        resp_hist = latest_package["resp_history"]
        
        status_text = "● DEMO" if source_mode == "Signal Simulator" else "● LIVE"
        status_color = "#33ff33"
        status_bg = "rgba(51, 255, 51, 0.1)"
    else:
        stats = standby_stats
        telemetry = standby_telemetry
        raw_hist = []
        filt_hist = []
        resp_hist = []
        
        status_text = "○ STANDBY"
        status_color = "#6a737d"
        status_bg = "rgba(106, 115, 125, 0.1)"

    # Fall warning light banner
    if is_running and telemetry.get("fall_alert", False):
        st.markdown("<div class='fall-banner'>⚠️ FALL DETECTED!</div>", unsafe_allow_html=True)

    col_left, col_mid, col_right = st.columns([1.0, 1.8, 1.2])

    with col_left:
        draw_vital_signs(telemetry, st)
        draw_sleep_apnea(telemetry, st)

    with col_mid:
        # Header block inside the 3D observatory
        col_mid_title, col_mid_selector = st.columns([2, 1])
        with col_mid_title:
            st.markdown("""
            <div style="margin-bottom: 5px;">
                <h1 style="margin: 0; font-family: 'Fira Code', monospace; color: #ffffff; font-size: 2.1rem; font-weight: bold; line-height: 1.1;">
                    <span style="color: #33ff33;">π</span> RuView
                </h1>
                <div style="color: #8892b0; font-family: monospace; font-size: 0.7rem; letter-spacing: 1.5px; text-transform: uppercase; margin-top: 3px;">
                    WIFI DENSEPOSE SENSING OBSERVATORY
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_mid_selector:
            badge_and_select_col1, badge_and_select_col2 = st.columns([1, 2.5])
            with badge_and_select_col1:
                st.markdown(f"""
                <div style='margin-top: 5px; text-align: right;'>
                    <span style='background-color: {status_bg}; border: 1px solid {status_color}; color: {status_color}; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; letter-spacing: 0.5px;'>{status_text}</span>
                </div>
                """, unsafe_allow_html=True)
            with badge_and_select_col2:
                if source_mode == "Signal Simulator":
                    scenario_mode_selected = st.selectbox(
                        "Scenario Select",
                        ["Auto Cycle", "Fitness", "Normal Sleeping", "Apnea", "Hypopnea", "Fall", "Idle", "Empty Room"],
                        label_visibility="collapsed",
                        key="scenario_select"
                    )
                    config["simulation_mode"] = scenario_mode_selected
                else:
                    st.selectbox(
                        "Scenario Select",
                        ["Live Ingestion"],
                        disabled=True,
                        label_visibility="collapsed",
                        key="scenario_select_live"
                    )
                    
        st.markdown("""
        <div style="color: #8892b0; font-style: italic; font-size: 0.85rem; margin-top: 5px; margin-bottom: 12px; font-family: 'Fira Code', monospace;">
            Rep counting and exercise classification from body kinematics.
        </div>
        """, unsafe_allow_html=True)
        
        fig_3d = generate_3d_observatory(telemetry, stats)
        st.plotly_chart(fig_3d, use_container_width=True, config={'displayModeBar': False}, key="observatory_3d_plot")
        
        draw_indicators_and_keys(telemetry, st)

    with col_right:
        draw_wifi_signal(stats, telemetry, raw_hist, st)
        draw_presence(telemetry, st)
        draw_apnea_events(telemetry, st)

    st.markdown("### 📈 Live Signal Waves")
    chart_col1, chart_col2 = st.columns(2)
    
    # Graph 1: Raw & Filtered CSI
    fig_csi = go.Figure()
    y_raw = raw_hist if raw_hist else [25.0] * 50
    y_filt = filt_hist if filt_hist else [25.0] * 50
    fig_csi.add_trace(go.Scatter(y=y_raw, mode='lines', name='Raw Signal', line=dict(color='#00ffcc', width=1.5)))
    fig_csi.add_trace(go.Scatter(y=y_filt, mode='lines', name='Filtered CSI', line=dict(color='#33ff33', width=2.0)))
    fig_csi.update_layout(
        title="Raw Subcarrier Magnitude (Mean)",
        **plotly_layout_args
    )
    with chart_col1:
        st.plotly_chart(fig_csi, use_container_width=True, key="csi_history_plot")
        
    # Graph 2: Extracted Respiration Waveform
    fig_resp = go.Figure()
    y_resp = resp_hist if resp_hist else [0.0] * 50
    fig_resp.add_trace(go.Scatter(y=y_resp, mode='lines', name='Respiration Waveform', line=dict(color='#ff5555', width=2.0)))
    fig_resp.update_layout(
        title="Extracted Respiration Waveform (0.1-0.5 Hz)",
        **plotly_layout_args
    )
    with chart_col2:
        st.plotly_chart(fig_resp, use_container_width=True, key="respiration_history_plot")

    if not is_running:
        st.info("🔮 Receiver standby. Select ingestion parameters in the sidebar and click **Launch**.")
        st.markdown("""
        ### 💻 Console Instructions:
        1. Select data source mode from the sidebar options.
        2. Click **Launch** to initialize the ingestion and processing loops.
        
        *If running offline, select **Signal Simulator** to test the real-time DSP filters, telemetry heuristics, and live 3D skeleton.*
        """)

# Run fragment render block
render_dashboard(is_running, source_mode)


