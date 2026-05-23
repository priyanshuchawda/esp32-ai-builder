import time
from collections import Counter, deque


class SignalQualityMonitor:
    def __init__(self, window_seconds=10.0, stale_seconds=3.0):
        self.window_seconds = float(window_seconds)
        self.stale_seconds = float(stale_seconds)
        self.samples = deque()

    def record_packet(self, seq, rssi, n_subcarriers, timestamp=None):
        ts = time.time() if timestamp is None else float(timestamp)
        self.samples.append(
            {
                "seq": int(seq),
                "rssi": int(rssi),
                "n_subcarriers": int(n_subcarriers),
                "timestamp": ts,
            }
        )
        self._trim(ts)

    def summary(self, now=None):
        ts = time.time() if now is None else float(now)
        self._trim(ts)

        if not self.samples:
            return self._empty_summary("BAD", ["no_packets"])

        first_ts = self.samples[0]["timestamp"]
        last_ts = self.samples[-1]["timestamp"]
        age = max(0.0, ts - last_ts)
        duration = max(ts - first_ts, 0.001)
        fps = len(self.samples) / duration
        seqs = [sample["seq"] for sample in self.samples]
        rssis = [sample["rssi"] for sample in self.samples]
        subcarrier_modes = dict(Counter(sample["n_subcarriers"] for sample in self.samples))
        dominant_subcarriers, dominant_subcarrier_count = max(
            subcarrier_modes.items(),
            key=lambda item: (item[1], item[0]),
        )
        dominant_subcarrier_ratio = dominant_subcarrier_count / len(self.samples)
        sequence_gaps = sum(1 for prev, cur in zip(seqs, seqs[1:]) if cur != prev + 1)
        rssi_spread = max(rssis) - min(rssis)

        reasons = []
        status = "GOOD"

        if age > self.stale_seconds:
            reasons.append("stale_stream")
            status = "BAD"
        if fps < 1.0:
            reasons.append("very_low_fps")
            status = "BAD"
        elif fps < 5.0:
            reasons.append("low_fps")
            if status != "BAD":
                status = "WEAK"
        if sequence_gaps:
            reasons.append("sequence_gaps")
            gap_rate = sequence_gaps / max(1, len(seqs) - 1)
            if gap_rate > 0.2:
                status = "BAD"
            elif status != "BAD":
                status = "WEAK"
        if rssi_spread > 30:
            reasons.append("rssi_unstable")
            if status != "BAD":
                status = "WEAK"
        if len(subcarrier_modes) > 1 and dominant_subcarrier_ratio < 0.9:
            reasons.append("mixed_subcarriers")
            if status != "BAD":
                status = "WEAK"

        return {
            "status": status,
            "fps": round(fps, 2),
            "packets": len(self.samples),
            "age_seconds": round(age, 2),
            "sequence_gaps": sequence_gaps,
            "rssi_min": min(rssis),
            "rssi_max": max(rssis),
            "rssi_spread": rssi_spread,
            "subcarrier_modes": subcarrier_modes,
            "dominant_subcarriers": dominant_subcarriers,
            "dominant_subcarrier_ratio": round(dominant_subcarrier_ratio, 3),
            "reasons": reasons,
        }

    def _trim(self, now):
        cutoff = now - self.window_seconds
        while self.samples and self.samples[0]["timestamp"] < cutoff:
            self.samples.popleft()

    def _empty_summary(self, status, reasons):
        return {
            "status": status,
            "fps": 0.0,
            "packets": 0,
            "age_seconds": 0.0,
            "sequence_gaps": 0,
            "rssi_min": 0,
            "rssi_max": 0,
            "rssi_spread": 0,
            "subcarrier_modes": {},
            "dominant_subcarriers": 0,
            "dominant_subcarrier_ratio": 0.0,
            "reasons": reasons,
        }
