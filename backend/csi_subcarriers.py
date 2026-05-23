from collections import deque


def normalize_amplitudes(amplitudes, target_len=128):
    target = int(target_len)
    values = [float(value) for value in amplitudes[:target]]
    if len(values) < target:
        values.extend([0.0] * (target - len(values)))
    return values


def mean_signal(values):
    return sum(values) / len(values) if values else 0.0


class SubcarrierSelector:
    def __init__(self, target_len=128, top_k=16, min_frames=8, history_size=40):
        self.target_len = int(target_len)
        self.top_k = max(1, int(top_k))
        self.min_frames = max(1, int(min_frames))
        self.history = deque(maxlen=max(self.min_frames, int(history_size)))

    def add_frame(self, amplitudes):
        real_values = [float(value) for value in amplitudes]
        normalized = normalize_amplitudes(real_values, target_len=self.target_len)
        self.history.append(normalized)

        selected_indices = self._selected_indices()
        if selected_indices:
            selected_values = [normalized[index] for index in selected_indices]
            selected_signal = mean_signal(selected_values)
        else:
            selected_signal = mean_signal(real_values)

        return {
            "normalized_amplitudes": normalized,
            "selected_indices": selected_indices,
            "selected_signal": selected_signal,
            "frame_count": len(self.history),
        }

    def _selected_indices(self):
        if len(self.history) < self.min_frames:
            return []

        frames = list(self.history)
        scores = []
        for index in range(self.target_len):
            column = [frame[index] for frame in frames]
            populated = [value for value in column if value > 0.0]
            if not populated:
                continue

            coverage = len(populated) / len(column)
            mean = mean_signal(populated)
            variance = mean_signal([(value - mean) ** 2 for value in populated])
            coefficient_of_variation = (variance ** 0.5) / mean if mean else float("inf")
            scores.append((coverage, coefficient_of_variation, index))

        scores.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [index for _, _, index in scores[: self.top_k]]
