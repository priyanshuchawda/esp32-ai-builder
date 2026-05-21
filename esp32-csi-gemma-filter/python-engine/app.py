import argparse
import time
import os
import csv
import json
import logging
from datetime import datetime
import numpy as np

import config
from simulator import generate_noisy_data
from serial_reader import SerialReader
from csi_parser import parse_line
from features import extract_features
from filters import apply_filter
from gemma_advisor import query_gemma_advisor
from presence_alerts import TelegramPresenceAlerter, detect_human_presence
from plot_signal import plot_raw_vs_filtered

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("CSIFilterApp")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Gemma 4 E4B Assisted ESP32 CSI Noise Filtering Engine"
    )
    parser.add_argument(
        "--mode",
        choices=["simulate", "serial"],
        default="simulate",
        help="Execution mode: 'simulate' for dummy data, 'serial' for live ESP32 COM port data",
    )
    parser.add_argument(
        "--port",
        default=config.DEFAULT_PORT,
        help=f"Serial port for ESP32 (default: {config.DEFAULT_PORT})",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=config.DEFAULT_BAUD,
        help=f"Baud rate (default: {config.DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=20,
        help="Duration of the run in seconds (default: 20)",
    )
    return parser.parse_args()


def run_app():
    args = parse_args()
    session_id = f"session_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
    logger.info(f"Starting {args.mode} mode. Session ID: {session_id}")
    presence_alerter = TelegramPresenceAlerter.from_env()

    # Storage for run data
    raw_records = []  # List of raw dicts: [timestamp, rssi, csi_0..5, raw_signal]
    filtered_records = []  # List of filtered dicts: [timestamp, rssi, raw_signal, filtered_signal, filter, confidence]
    decisions = []  # List of Gemma decisions

    # Window buffers
    window_rssi = []
    window_signal = []
    window_raw_dicts = []
    missing_count = 0

    start_time = time.time()

    # 1. Determine data stream source
    if args.mode == "simulate":
        logger.info("Initializing noisy simulated signal generator...")
        sampling_rate = config.SIMULATED_SAMPLING_RATE_HZ
        line_generator = generate_noisy_data(args.duration, sampling_rate=sampling_rate)
        window_size_threshold = config.SIMULATED_WINDOW_SAMPLES
        time_based_window = False
    else:
        logger.info(f"Initializing Serial Reader on {args.port} at {args.baud} baud...")
        reader = SerialReader(
            port=args.port, baudrate=args.baud, timeout=config.SERIAL_TIMEOUT
        )
        if not reader.connect():
            logger.error("Could not open serial port. Exiting.")
            return
        line_generator = reader.read_lines()
        window_size_threshold = config.WINDOW_DURATION_SEC
        time_based_window = True

    # 2. Main Processing Loop
    window_start_time = time.time()
    logger.info("Starting processing loop...")

    try:
        for line in line_generator:
            # Check total duration limit
            elapsed = time.time() - start_time
            if elapsed >= args.duration:
                logger.info(f"Duration limit reached ({args.duration}s). Stopping.")
                break

            parsed = parse_line(line)
            if not parsed:
                missing_count += 1
                continue

            # Append to current window buffers
            window_rssi.append(parsed["rssi"])
            window_signal.append(parsed["raw_signal"])
            window_raw_dicts.append(parsed)

            # Store in raw session records
            raw_records.append(parsed)

            # Check if window is complete
            window_complete = False
            if time_based_window:
                if time.time() - window_start_time >= window_size_threshold:
                    window_complete = True
            else:
                if len(window_signal) >= window_size_threshold:
                    window_complete = True

            if window_complete and len(window_signal) > 0:
                logger.info(
                    f"Processing window: {len(window_signal)} samples gathered."
                )

                # Extract features
                features = extract_features(window_rssi, window_signal, missing_count)
                logger.info(
                    f"Features: Outlier Ratio={features['outlier_ratio']}, Signal Std={features['signal_std']}"
                )

                # Query Gemma Advisor
                decision = query_gemma_advisor(features)
                decision["timestamp"] = int(time.time() * 1000)
                decision["window_index"] = len(decisions)
                decisions.append(decision)
                if detect_human_presence(features):
                    presence_alerter.send_presence_alert(features, decision)

                # Apply filter to window signal
                signal_arr = np.array(window_signal)
                filtered_signal_arr = apply_filter(signal_arr, decision)

                # Save filtered samples
                for idx, item in enumerate(window_raw_dicts):
                    filtered_records.append(
                        {
                            "timestamp": item["timestamp"],
                            "rssi": item["rssi"],
                            "raw_signal": item["raw_signal"],
                            "filtered_signal": float(filtered_signal_arr[idx]),
                            "selected_filter": decision["filter"],
                            "gemma_confidence": decision["confidence"],
                        }
                    )

                # Reset window buffers
                window_rssi = []
                window_signal = []
                window_raw_dicts = []
                missing_count = 0
                window_start_time = time.time()

            # If simulated, sleep to match sampling rate timing
            if args.mode == "simulate":
                time.sleep(1.0 / sampling_rate)

    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
    finally:
        if args.mode == "serial":
            reader.close()

    # Process remaining buffer as the final window if any
    if len(window_signal) > 0:
        logger.info(f"Processing final window: {len(window_signal)} samples.")
        features = extract_features(window_rssi, window_signal, missing_count)
        decision = query_gemma_advisor(features)
        decision["timestamp"] = int(time.time() * 1000)
        decision["window_index"] = len(decisions)
        decisions.append(decision)
        if detect_human_presence(features):
            presence_alerter.send_presence_alert(features, decision)

        signal_arr = np.array(window_signal)
        filtered_signal_arr = apply_filter(signal_arr, decision)

        for idx, item in enumerate(window_raw_dicts):
            filtered_records.append(
                {
                    "timestamp": item["timestamp"],
                    "rssi": item["rssi"],
                    "raw_signal": item["raw_signal"],
                    "filtered_signal": float(filtered_signal_arr[idx]),
                    "selected_filter": decision["filter"],
                    "gemma_confidence": decision["confidence"],
                }
            )

    # 3. Save Session Output Files
    if len(raw_records) == 0:
        logger.warning("No data was collected. No files will be saved.")
        return

    # A. Save Decisions JSON
    decision_path = os.path.join(config.DECISIONS_DIR, f"{session_id}_decision.json")
    with open(decision_path, "w") as f:
        json.dump(decisions, f, indent=2)
    logger.info(f"Saved decisions log to {decision_path}")

    # B. Save Raw CSV
    raw_path = os.path.join(config.RAW_DATA_DIR, f"{session_id}_raw.csv")
    with open(raw_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "rssi",
                "csi_0",
                "csi_1",
                "csi_2",
                "csi_3",
                "csi_4",
                "csi_5",
                "raw_signal",
            ]
        )
        for r in raw_records:
            writer.writerow([r["timestamp"], r["rssi"]] + r["csi"] + [r["raw_signal"]])
    logger.info(f"Saved raw data CSV to {raw_path}")

    # C. Save Filtered CSV
    filtered_path = os.path.join(config.FILTERED_DATA_DIR, f"{session_id}_filtered.csv")
    with open(filtered_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "rssi",
                "raw_signal",
                "filtered_signal",
                "selected_filter",
                "gemma_confidence",
            ]
        )
        for r in filtered_records:
            writer.writerow(
                [
                    r["timestamp"],
                    r["rssi"],
                    r["raw_signal"],
                    r["filtered_signal"],
                    r["selected_filter"],
                    r["gemma_confidence"],
                ]
            )
    logger.info(f"Saved filtered data CSV to {filtered_path}")

    # D. Save Plot
    plot_path = os.path.join(config.PLOTS_DIR, f"{session_id}_raw_vs_filtered.png")
    raw_signal_list = [r["raw_signal"] for r in filtered_records]
    filtered_signal_list = [r["filtered_signal"] for r in filtered_records]
    plot_raw_vs_filtered(raw_signal_list, filtered_signal_list, plot_path)

    # 4. Print Summary Stats
    raw_var = np.var(raw_signal_list) if raw_signal_list else 0
    filtered_var = np.var(filtered_signal_list) if filtered_signal_list else 0
    reduction = 100 * (1 - (filtered_var / raw_var)) if raw_var > 0 else 0

    logger.info("=========================================")
    logger.info("            SESSION SUMMARY              ")
    logger.info("=========================================")
    logger.info(f"Total samples collected : {len(raw_records)}")
    logger.info(f"Total windows processed : {len(decisions)}")
    logger.info(f"Raw signal variance     : {raw_var:.4f}")
    logger.info(f"Filtered signal variance: {filtered_var:.4f}")
    logger.info(f"Noise reduction         : {reduction:.2f}%")
    logger.info("=========================================")


if __name__ == "__main__":
    run_app()
