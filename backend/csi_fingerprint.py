def build_fingerprint(amplitudes, bins=16):
    values = [float(value) for value in amplitudes or []]
    if not values:
        return {
            "bins": 0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "spread": 0.0,
            "bars": "",
        }

    compact = _bin_values(values, bins)
    min_val = min(compact)
    max_val = max(compact)
    spread = max_val - min_val
    return {
        "bins": len(compact),
        "min": round(min_val, 2),
        "max": round(max_val, 2),
        "mean": round(sum(compact) / len(compact), 2),
        "spread": round(spread, 2),
        "bars": _bars(compact, min_val, max_val),
    }


def format_fingerprint_lines(fingerprint, prefix="CSI_FINGERPRINT"):
    return [
        (
            f"{prefix} bins={fingerprint.get('bins', 0)} "
            f"mean={fingerprint.get('mean', 0.0)} "
            f"spread={fingerprint.get('spread', 0.0)}"
        ),
        f"{prefix} bars={fingerprint.get('bars', '') or 'none'}",
    ]


def _bin_values(values, bins):
    if bins <= 0 or len(values) <= bins:
        return values
    result = []
    for index in range(bins):
        start = int(index * len(values) / bins)
        end = int((index + 1) * len(values) / bins)
        chunk = values[start:max(start + 1, end)]
        result.append(sum(chunk) / len(chunk))
    return result


def _bars(values, min_val, max_val):
    glyphs = "._:-=+*#"
    spread = max(max_val - min_val, 0.001)
    chars = []
    for value in values:
        level = int(round(((value - min_val) / spread) * (len(glyphs) - 1)))
        chars.append(glyphs[max(0, min(level, len(glyphs) - 1))])
    return "".join(chars)
