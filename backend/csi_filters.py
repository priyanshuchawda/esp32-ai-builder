from collections import deque
import statistics


class StreamingHampelFilter:
    def __init__(self, window_size=9, threshold=3.0, min_spike_delta=5.0):
        self.window_size = max(3, int(window_size))
        self.threshold = float(threshold)
        self.min_spike_delta = float(min_spike_delta)
        self.history = deque(maxlen=self.window_size)
        self.replaced_count = 0

    def update(self, value):
        value = float(value)
        if len(self.history) < self.window_size:
            self.history.append(value)
            return value

        baseline = list(self.history)
        median = statistics.median(baseline)
        deviations = [abs(sample - median) for sample in baseline]
        mad = statistics.median(deviations)
        sigma = 1.4826 * mad
        delta = abs(value - median)

        if self._is_outlier(delta, sigma, baseline):
            output = median
            self.replaced_count += 1
        else:
            output = value

        self.history.append(output)
        return output

    def _is_outlier(self, delta, sigma, baseline):
        if delta < self.min_spike_delta:
            return False
        if sigma > 1e-6:
            return delta > self.threshold * sigma

        spread = max(baseline) - min(baseline)
        if spread <= 1e-6:
            return True

        std = statistics.pstdev(baseline)
        return std > 1e-6 and delta > self.threshold * std
