import logging

logger = logging.getLogger(__name__)


def parse_line(line: str) -> dict | None:
    """
    Parses a single serial output line.
    Expected format: timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5

    Returns a dictionary of parsed data or None if the line is invalid.
    """
    if not line:
        return None

    # Split by comma
    parts = line.strip().split(",")

    # Check column count (should be 8 columns: timestamp, rssi, 6 subcarriers)
    if len(parts) != 8:
        logger.warning(
            f"Invalid line format (expected 8 parts, got {len(parts)}): {line}"
        )
        return None

    try:
        # Parse timestamp and RSSI
        timestamp = int(parts[0])
        rssi = int(parts[1])

        # Parse CSI subcarriers
        csi = [float(val) for val in parts[2:]]

        # Calculate raw_signal as the average amplitude of the subcarriers
        raw_signal = sum(csi) / len(csi)

        return {
            "timestamp": timestamp,
            "rssi": rssi,
            "csi": csi,
            "raw_signal": raw_signal,
        }
    except ValueError as e:
        logger.warning(f"Failed to parse line values to numeric format ({e}): {line}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error parsing line ({e}): {line}")
        return None
