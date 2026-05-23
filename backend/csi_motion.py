class MotionLevelEstimator:
    def __init__(
        self,
        alpha=0.25,
        baseline_alpha=0.05,
        minimal_threshold=0.25,
        moderate_threshold=1.0,
        high_threshold=3.0,
    ):
        self.alpha = max(0.0, min(1.0, float(alpha)))
        self.baseline_alpha = max(0.0, min(1.0, float(baseline_alpha)))
        self.minimal_threshold = float(minimal_threshold)
        self.moderate_threshold = float(moderate_threshold)
        self.high_threshold = float(high_threshold)
        self.baseline = None
        self.score = 0.0
        self.samples = 0

    def update(self, value):
        value = float(value)
        if self.baseline is None:
            self.baseline = value
            self.samples = 1
            return self.summary()

        residual = abs(value - self.baseline)
        self.score = (self.alpha * residual) + ((1.0 - self.alpha) * self.score)
        self.baseline = (self.baseline_alpha * value) + ((1.0 - self.baseline_alpha) * self.baseline)
        self.samples += 1
        return self.summary()

    def summary(self):
        score = self.score
        if score >= self.high_threshold:
            level = "HIGH"
        elif score >= self.moderate_threshold:
            level = "MODERATE"
        elif score >= self.minimal_threshold:
            level = "MINIMAL"
        else:
            level = "STILL"

        return {
            "level": level,
            "display_level": level,
            "trusted": True,
            "reasons": [],
            "score": round(score, 4),
            "baseline": round(self.baseline or 0.0, 4),
            "samples": self.samples,
        }


def gate_motion_for_quality(motion, signal_quality):
    motion = dict(motion or {})
    quality = signal_quality or {}
    status = str(quality.get("status", "BAD")).upper()
    reasons = list(quality.get("reasons", []))
    trusted = status == "GOOD"

    motion["trusted"] = trusted
    motion["reasons"] = reasons
    motion["display_level"] = motion.get("level", "STILL") if trusted else "UNSTABLE"
    return motion
