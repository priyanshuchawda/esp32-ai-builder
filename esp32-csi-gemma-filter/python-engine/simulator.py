import time
import random
import math


def generate_noisy_data(duration_seconds, sampling_rate=50.0):
    """
    Generates simulated noisy CSI-like data.

    Format: timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5
    """
    total_samples = int(duration_seconds * sampling_rate)
    start_time_ms = int(time.time() * 1000)
    interval_ms = int(1000 / sampling_rate)

    # Base parameters
    base_rssi = -50.0

    # We will generate a base signal that has:
    # 1. Smooth baseline movement (slow sine wave)
    # 2. Gaussian random noise
    # 3. Transient spike noise (outliers)

    for i in range(total_samples):
        t = i / sampling_rate
        timestamp = start_time_ms + (i * interval_ms)

        # 1. Smooth baseline (slow movement)
        baseline = 20.0 + 5.0 * math.sin(2 * math.pi * 0.05 * t)

        # 2. Gaussian noise
        noise = random.normalvariate(0.0, 1.5)

        # 3. Spikes (outliers) - 5% chance of spikes
        spike = 0.0
        if random.random() < 0.05:
            # Random positive or negative spike
            spike = random.choice([30.0, -25.0]) * random.uniform(0.8, 1.5)

        base_signal = baseline + noise + spike

        # Simulate RSSI drifting with signal
        rssi = int(base_rssi + 0.2 * base_signal + random.normalvariate(0.0, 1.0))

        # Generate 6 subcarriers around base_signal with slight variations
        csi_subcarriers = []
        for _ in range(6):
            # subcarrier value should be a positive integer
            val = max(1, int(base_signal + random.uniform(-2.0, 2.0)))
            csi_subcarriers.append(val)

        # Format: timestamp,rssi,csi_0,csi_1,csi_2,csi_3,csi_4,csi_5
        line = f"{timestamp},{rssi}," + ",".join(map(str, csi_subcarriers))
        yield line

        # Respect real-world timing if we are running the simulator in real-time mode
        # (Though we can also run it fast for batch testing/processing)
