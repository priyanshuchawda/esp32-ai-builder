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

@st.cache_resource
def get_global_resources():
    """Returns persistent, shared objects across sessions and reloads to avoid leaks."""
    return {
        "queue": queue.Queue(maxsize=1000),
        "shutdown_event": threading.Event(),
        "config": {
            "presence_threshold": 0.6,
            "fall_threshold": 12.0
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
        
    def add_sample(self, raw_val):
        self.raw_history.append(raw_val)
        
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
                nyq = 0.5 * self.fps
                low_norm = low / nyq
                high_norm = high / nyq
                b, a = butter(2, [low_norm, high_norm], btype='bandpass')
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
        if len(self.filtered_history) < 30:
            return {
                "presence": False,
                "resp_bpm": 0.0,
                "heart_bpm": 0.0,
                "variance": 0.0,
                "fall_alert": False,
                "acceleration": 0.0,
                "rep_count": 0,
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
        
        presence = (variance > presence_threshold) or (std_dev > (presence_threshold * 0.8))
        
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

def udp_receiver_loop(port, shutdown_event, data_queue, config):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except Exception as e:
        data_queue.put({"error": f"Failed to bind port {port}: {e}"})
        return

    sock.settimeout(0.2)
    
    dsp = RuViewDSP(fps=50.0)
    packet_counter = 0
    last_fps_time = time.time()
    
    while not shutdown_event.is_set():
        try:
            data, addr = sock.recvfrom(4096)
            packet = parse_adr018_packet(data)
            if packet:
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
                
                ui_package = {
                    "stats": {
                        "node_id": packet["node_id"],
                        "seq": packet["seq"],
                        "rssi": packet["rssi"],
                        "noise": packet["noise"],
                        "freq_mhz": packet["freq_mhz"],
                        "fps": fps
                    },
                    "telemetry": telemetry,
                    "raw_history": list(dsp.raw_history),
                    "filtered_history": list(dsp.filtered_history),
                    "resp_history": list(dsp.resp_history)
                }
                
                if data_queue.full():
                    try: data_queue.get_nowait()
                    except queue.Empty: pass
                data_queue.put(ui_package)
        except socket.timeout:
            # Report offline status if no packets received for 3 seconds
            now = time.time()
            if now - last_fps_time > 3.0:
                p_thresh = config.get("presence_threshold", 0.6)
                f_thresh = config.get("fall_threshold", 12.0)
                telemetry = dsp.process_telemetry(p_thresh, f_thresh)
                telemetry["presence"] = False
                
                ui_package = {
                    "stats": {
                        "node_id": "Offline (No Signal)",
                        "seq": "N/A",
                        "rssi": 0,
                        "noise": 0,
                        "freq_mhz": 0,
                        "fps": 0.0
                    },
                    "telemetry": telemetry,
                    "raw_history": list(dsp.raw_history),
                    "filtered_history": list(dsp.filtered_history),
                    "resp_history": list(dsp.resp_history)
                }
                if data_queue.full():
                    try: data_queue.get_nowait()
                    except queue.Empty: pass
                data_queue.put(ui_package)
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
        data_queue.put({"error": f"Failed to open COM port {port_name}: {e}"})
        return

    dsp = RuViewDSP(fps=50.0)
    packet_counter = 0
    last_fps_time = time.time()
    
    while not shutdown_event.is_set():
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line or line.startswith("#"):
                continue
            
            parts = line.split(",")
            if len(parts) >= 8:
                ts = int(parts[0])
                rssi = int(parts[1])
                bins = [float(x) for x in parts[2:8]]
                avg_signal = sum(bins) / len(bins)
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
                
                dsp.add_sample(avg_signal)
                
                p_thresh = config.get("presence_threshold", 0.6)
                f_thresh = config.get("fall_threshold", 12.0)
                telemetry = dsp.process_telemetry(p_thresh, f_thresh)
                
                ui_package = {
                    "stats": {
                        "node_id": 1,
                        "seq": packet_counter,
                        "rssi": rssi,
                        "noise": -95,
                        "freq_mhz": 2437,
                        "fps": fps
                    },
                    "telemetry": telemetry,
                    "raw_history": list(dsp.raw_history),
                    "filtered_history": list(dsp.filtered_history),
                    "resp_history": list(dsp.resp_history)
                }
                
                if data_queue.full():
                    try: data_queue.get_nowait()
                    except queue.Empty: pass
                data_queue.put(ui_package)
        except Exception:
            time.sleep(0.01)
            continue
    ser.close()

def generate_simulated_packet(seq):
    now_ms = int(time.time() * 1000)
    t = time.time()
    
    # 60-second periodic cycle for sleep apnea/hypopnea pre-screening verification
    cycle_t = t % 60
    
    # Base background physiological noise standard deviation (human presence)
    # When a human is present, chest motion, pulse, and muscle tremors create constant minor CSI variance
    human_noise_std = 0.50
    
    if 30 <= cycle_t < 45:
        # Apnea event: Cessation of breathing (flat/no respiration wave) for 15s
        breathing = 0.0
        # Heartbeat remains present but faint
        heartbeat = 0.04 * np.sin(2 * np.pi * 1.2 * t)
        is_motion = False
    elif 0 <= cycle_t < 15:
        # Hypopnea event: Shallow/slow breathing (6 BPM = 0.1 Hz) for 15s
        # Drop respiration amplitude to 0.15
        breathing = 0.15 * np.sin(2 * np.pi * 0.1 * t)
        heartbeat = 0.04 * np.sin(2 * np.pi * 1.2 * t)
        is_motion = False
    else:
        # Normal breathing: 15 BPM (0.25 Hz)
        breathing = 0.6 * np.sin(2 * np.pi * 0.25 * t)
        heartbeat = 0.08 * np.sin(2 * np.pi * 1.2 * t)
        # Occasional movement spikes during normal breathing (e.g. turning in bed)
        is_motion = (int(t) % 20 < 3)
        
    motion_spike = 0.0
    if is_motion:
        motion_spike = np.sin(2 * np.pi * 1.5 * t) * np.random.uniform(1.2, 3.2)
        
    # Fall event simulator: every 90 seconds (reduced frequency to prevent clashing with apnea cycle)
    is_fall = (int(t) % 90 == 85)
    fall_spike = 0.0
    if is_fall:
        fall_spike = 15.0 * np.exp(-((t % 90) - 85) * 5)
        
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
    packet_counter = 0
    last_fps_time = time.time()
    seq = 0
    
    while not shutdown_event.is_set():
        packet = generate_simulated_packet(seq)
        seq += 1
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
        
        ui_package = {
            "stats": {
                "node_id": packet["node_id"],
                "seq": packet["seq"],
                "rssi": packet["rssi"],
                "noise": packet["noise"],
                "freq_mhz": packet["freq_mhz"],
                "fps": fps
            },
            "telemetry": telemetry,
            "raw_history": list(dsp.raw_history),
            "filtered_history": list(dsp.filtered_history),
            "resp_history": list(dsp.resp_history)
        }
        
        if data_queue.full():
            try: data_queue.get_nowait()
            except queue.Empty: pass
        data_queue.put(ui_package)
        
        time.sleep(0.04) # 25 Hz simulation rate

# Helper to launch thread safely
def start_receiver_thread(source_mode, port_to_bind, com_port_selected, serial_baud):
    thread_shutdown.clear()
    
    # Empty queue
    while not data_queue.empty():
        try: data_queue.get_nowait()
        except queue.Empty: break
        
    if source_mode == "WiFi UDP Receiver":
        t = threading.Thread(
            name="RuViewReceiverThread",
            target=udp_receiver_loop,
            args=(port_to_bind, thread_shutdown, data_queue, config),
            daemon=True
        )
        t.start()
    elif source_mode == "USB Serial COM Port" and com_port_selected:
        t = threading.Thread(
            name="RuViewReceiverThread",
            target=serial_receiver_loop,
            args=(com_port_selected, serial_baud, thread_shutdown, data_queue, config),
            daemon=True
        )
        t.start()
    elif source_mode == "Signal Simulator":
        t = threading.Thread(
            name="RuViewReceiverThread",
            target=simulator_loop,
            args=(thread_shutdown, data_queue, config),
            daemon=True
        )
        t.start()

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

# Dynamically update background thread configuration
config["presence_threshold"] = presence_threshold
config["fall_threshold"] = fall_accel_threshold

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

ui_fall_alert = st.empty()

# Create two columns matching the terminal receiver layout
col_left, col_right = st.columns(2)
with col_left:
    ui_telemetry = st.empty()
    ui_apnea = st.empty()
with col_right:
    ui_network = st.empty()
    ui_apnea_events = st.empty()

st.markdown("### 📈 Live Signal Waves")
chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    ui_csi_chart = st.empty()
with chart_col2:
    ui_resp_chart = st.empty()

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

if is_running:
    last_chart_update = 0.0
    
    # Bounded visual updates loop (refresh UI for ~4 seconds, then yield execution to Streamlit)
    for _ in range(100):
        if thread_shutdown.is_set():
            break
            
        # Extract the latest package from background thread
        latest_package = None
        while not data_queue.empty():
            try:
                latest_package = data_queue.get_nowait()
            except queue.Empty:
                break
                
        if latest_package:
            stats = latest_package["stats"]
            telemetry = latest_package["telemetry"]
            raw_hist = latest_package["raw_history"]
            filt_hist = latest_package["filtered_history"]
            resp_hist = latest_package["resp_history"]
            
            # Check for error reported by background thread
            if "error" in latest_package:
                st.error(latest_package["error"])
                thread_shutdown.set()
                st.rerun()
            
            # 1. Fall warning light banner
            if telemetry["fall_alert"]:
                ui_fall_alert.markdown("<div class='fall-banner'>⚠️ FALL DETECTED!</div>", unsafe_allow_html=True)
            else:
                ui_fall_alert.empty()
                
            # 2. Telemetry panel (matches terminal columns)
            presence_str = "<span class='green-text'>[+] HUMAN PRESENT</span>" if telemetry["presence"] else "<span class='grey-text'>[-] ROOM EMPTY</span>"
            fall_str = "<span class='red-text' style='font-weight:bold;'>[!] FALL DETECTED</span>" if telemetry["fall_alert"] else "<span class='green-text'>[+] SAFE (No Fall)</span>"
            resp_str = f"<span class='yellow-text'>{telemetry['resp_bpm']} BPM</span>" if telemetry['resp_bpm'] > 0 else "Calculating..."
            heart_str = f"<span class='magenta-text'>{int(telemetry['heart_bpm'])} BPM</span>" if telemetry['heart_bpm'] > 0 else "Calculating..."
            
            ui_telemetry.markdown(f"""
            <div class='terminal-container'>
                <div class='terminal-header'>Telemetry</div>
                <div class='terminal-row'><span class='terminal-label'>Occupancy Status:</span><span class='terminal-value'>{presence_str}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Fall Monitor:</span><span class='terminal-value'>{fall_str}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Breathing Rate:</span><span class='terminal-value'>{resp_str}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Est. Heart Rate:</span><span class='terminal-value'>{heart_str}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Signal Variance:</span><span class='terminal-value'>{telemetry['variance']:.4f}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Max Acceleration:</span><span class='terminal-value'>{telemetry['acceleration']:.2f}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Exercise Reps:</span><span class='terminal-value cyan-text'>{telemetry['rep_count']}</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            # Sleep Apnea screener panel
            apnea_status = telemetry.get("apnea_status", {})
            if apnea_status:
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
                
                if is_apnea:
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
                    
                ui_apnea.markdown(f"""
                <div class='terminal-container'>
                    <div class='terminal-header'>Sleep Apnea Screener</div>
                    <div class='terminal-row'><span class='terminal-label'>Screener Status:</span><span class='terminal-value'>{status_str}</span></div>
                    <div class='terminal-row'><span class='terminal-label'>Baseline BR:</span><span class='terminal-value'>{baseline_br:.1f} BPM</span></div>
                    <div class='terminal-row'><span class='terminal-label'>Monitored Time:</span><span class='terminal-value'>{monitored_str}</span></div>
                    <div class='terminal-row'><span class='terminal-label'>AHI Index:</span><span class='terminal-value cyan-text'>{ahi:.2f}</span></div>
                    <div class='terminal-row'><span class='terminal-label'>AHI Severity:</span><span class='terminal-value'>{sev_str}</span></div>
                    <div class='terminal-row'><span class='terminal-label'>Total Events:</span><span class='terminal-value'>{total_events} (A: {apneas_count} / H: {hypopneas_count})</span></div>
                </div>
                """, unsafe_allow_html=True)
            
            # 3. Network & Radio panel (matches terminal columns)
            node_val = stats["node_id"]
            node_str = f"<span class='cyan-text'>{node_val}</span>" if isinstance(node_val, int) else f"<span class='red-text'>{node_val}</span>"
            
            ui_network.markdown(f"""
            <div class='terminal-container'>
                <div class='terminal-header'>Network & Radio</div>
                <div class='terminal-row'><span class='terminal-label'>Node ID:</span><span class='terminal-value'>{node_str}</span></div>
                <div class='terminal-row'><span class='terminal-label'>Frequency:</span><span class='terminal-value'>{stats['freq_mhz']} MHz</span></div>
                <div class='terminal-row'><span class='terminal-label'>Sequence:</span><span class='terminal-value'>{stats['seq']}</span></div>
                <div class='terminal-row'><span class='terminal-label'>RSSI:</span><span class='terminal-value'>{stats['rssi']} dBm</span></div>
                <div class='terminal-row'><span class='terminal-label'>Noise Floor:</span><span class='terminal-value'>{stats['noise']} dBm</span></div>
                <div class='terminal-row'><span class='terminal-label'>Rx Speed (FPS):</span><span class='terminal-value green-text'>{stats['fps']:.1f} FPS</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            # Sleep Apnea event log
            events_list = apnea_status.get("events", [])
            sorted_events = sorted(events_list, key=lambda x: x["start_ts"], reverse=True)[:6]
            
            rows_html = ""
            if not sorted_events:
                rows_html = "<div class='grey-text' style='text-align:center; padding:10px;'>No apnea/hypopnea events logged.</div>"
            else:
                for ev in sorted_events:
                    ev_type = ev["type"].upper()
                    color_class = "red-text" if ev_type == "APNEA" else "yellow-text"
                    time_str = time.strftime('%H:%M:%S', time.localtime(ev["start_ts"]))
                    dur = ev["duration_sec"]
                    avg_br = ev["avg_br"]
                    rows_html += f"""
                    <div class='terminal-row'>
                        <span class='terminal-label'>[{time_str}] <span class='{color_class}'>{ev_type}</span></span>
                        <span class='terminal-value'>Dur: {dur:.1f}s | Avg BR: {avg_br:.1f}</span>
                    </div>
                    """
                    
            ui_apnea_events.markdown(f"""
            <div class='terminal-container'>
                <div class='terminal-header'>Apnea Event Log (Newest First)</div>
                {rows_html}
            </div>
            """, unsafe_allow_html=True)
            
            # 4. Throttled charts redraw (at ~7 Hz) to avoid CPU spikes
            now = time.time()
            if now - last_chart_update >= 0.15:
                last_chart_update = now
                
                # Graph 1: Raw & Filtered CSI
                fig_csi = go.Figure()
                fig_csi.add_trace(go.Scatter(y=raw_hist, mode='lines', name='Raw Signal', line=dict(color='#00ffcc', width=1.5)))
                fig_csi.add_trace(go.Scatter(y=filt_hist, mode='lines', name='Filtered CSI', line=dict(color='#33ff33', width=2.0)))
                fig_csi.update_layout(
                    title="Raw Subcarrier Magnitude (Mean)",
                    **plotly_layout_args
                )
                ui_csi_chart.plotly_chart(fig_csi, use_container_width=True)
                
                # Graph 2: Extracted Respiration Waveform
                fig_resp = go.Figure()
                fig_resp.add_trace(go.Scatter(y=resp_hist, mode='lines', name='Respiration Waveform', line=dict(color='#ff5555', width=2.0)))
                fig_resp.update_layout(
                    title="Extracted Respiration Waveform (0.1-0.5 Hz)",
                    **plotly_layout_args
                )
                ui_resp_chart.plotly_chart(fig_resp, use_container_width=True)
                
        time.sleep(0.04) # Paced 25 Hz UI refresh rate
        
    st.rerun()
else:
    st.info("🔮 Receiver standby. Select ingestion parameters and click **Launch**.")
    st.markdown("""
    ### 💻 Console Instructions:
    1. Select data source mode from the sidebar options.
    2. Click **Launch** to initialize the ingestion and processing loops.
    
    *If running offline, select **Signal Simulator** to test the real-time DSP filters, telemetry heuristics, and live charts.*
    """)
