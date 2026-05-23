import statistics


class PresenceCalibration:
    def __init__(self, min_samples=60, multiplier=4.0, min_threshold=0.6, active=True):
        self.min_samples = int(min_samples)
        self.multiplier = float(multiplier)
        self.min_threshold = float(min_threshold)
        self.active = active
        self.samples = []
        self.ready = False
        self.baseline_mean = 0.0
        self.baseline_variance = 0.0
        self.baseline_std = 0.0
        self.threshold = self.min_threshold

    def add_sample(self, sample):
        if self.ready or not self.active:
            return self.summary()

        self.samples.append(float(sample))
        if len(self.samples) >= self.min_samples:
            self._finalize()
        return self.summary()

    def effective_threshold(self, manual_threshold):
        if self.ready:
            return self.threshold
        return float(manual_threshold)

    def reset(self, min_samples=None):
        if min_samples is not None:
            self.min_samples = int(min_samples)
        self.active = True
        self.samples = []
        self.ready = False
        self.baseline_mean = 0.0
        self.baseline_variance = 0.0
        self.baseline_std = 0.0
        self.threshold = self.min_threshold

    def _finalize(self):
        self.baseline_mean = statistics.fmean(self.samples)
        self.baseline_variance = statistics.pvariance(self.samples)
        self.baseline_std = self.baseline_variance ** 0.5
        self.threshold = max(
            self.min_threshold,
            self.baseline_variance + (self.baseline_std * self.multiplier),
        )
        self.ready = True
        self.active = False

    def summary(self):
        return {
            "ready": self.ready,
            "active": self.active,
            "samples": len(self.samples),
            "target_samples": self.min_samples,
            "baseline_mean": self.baseline_mean,
            "baseline_variance": self.baseline_variance,
            "baseline_std": self.baseline_std,
            "threshold": self.threshold,
        }
