#!/usr/bin/env python3
"""Deterministic CSI demo snapshots for terminal and dashboard showcases."""

from __future__ import annotations

import argparse

from backend.csi_fingerprint import build_fingerprint, format_fingerprint_lines
from backend.csi_power_summary import build_power_summary, format_power_summary_lines


SCENARIOS = {
    "empty_room": {
        "telemetry": {
            "presence": False,
            "resp_bpm": 0.0,
            "heart_bpm": 0.0,
            "fall_detected": False,
            "motion": {"display_level": "STILL", "score": 0.02, "trusted": True},
            "occupancy": {"class": "EMPTY", "trusted": True, "reasons": []},
            "variance": 1.1,
        },
        "quality": {"status": "GOOD", "fps": 25.0, "reasons": []},
    },
    "occupied_still": {
        "telemetry": {
            "presence": True,
            "resp_bpm": 15.2,
            "heart_bpm": 73.5,
            "fall_detected": False,
            "motion": {"display_level": "STILL", "score": 0.11, "trusted": True},
            "occupancy": {"class": "OCCUPIED", "trusted": True, "reasons": []},
            "variance": 8.4,
        },
        "quality": {"status": "GOOD", "fps": 25.0, "reasons": []},
    },
    "walking": {
        "telemetry": {
            "presence": True,
            "resp_bpm": 18.1,
            "heart_bpm": 91.0,
            "fall_detected": False,
            "motion": {"display_level": "HIGH", "score": 4.6, "trusted": True},
            "occupancy": {"class": "OCCUPIED", "trusted": True, "reasons": []},
            "variance": 22.0,
        },
        "quality": {"status": "GOOD", "fps": 25.0, "reasons": []},
    },
    "fall_event": {
        "telemetry": {
            "presence": True,
            "resp_bpm": 0.0,
            "heart_bpm": 0.0,
            "fall_detected": True,
            "motion": {"display_level": "HIGH", "score": 12.7, "trusted": True},
            "occupancy": {"class": "OCCUPIED", "trusted": True, "reasons": []},
            "variance": 38.0,
        },
        "quality": {"status": "GOOD", "fps": 25.0, "reasons": []},
    },
    "weak_live_stream": {
        "telemetry": {
            "presence": True,
            "resp_bpm": 0.0,
            "heart_bpm": 0.0,
            "fall_detected": False,
            "motion": {"display_level": "UNSTABLE", "score": 2.2, "trusted": False},
            "occupancy": {"class": "UNKNOWN", "trusted": False, "reasons": ["signal_quality_weak_blocked"]},
            "variance": 10.0,
        },
        "quality": {"status": "WEAK", "fps": 2.7, "reasons": ["low_fps", "rssi_unstable"]},
    },
}


def build_demo_snapshot(scenario: str) -> dict:
    key = scenario.lower()
    if key not in SCENARIOS:
        valid = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unknown demo scenario '{scenario}'. Valid scenarios: {valid}")

    data = SCENARIOS[key]
    telemetry = dict(data["telemetry"])
    quality = dict(data["quality"])
    return {
        "scenario": key,
        "telemetry": telemetry,
        "quality": quality,
        "summary": build_power_summary(telemetry, quality),
        "fingerprint": build_fingerprint(_scenario_amplitudes(key), bins=16),
    }


def format_demo_snapshot(snapshot: dict) -> list[str]:
    telemetry = snapshot["telemetry"]
    quality = snapshot["quality"]
    lines = [f"DEMO_SCENARIO {snapshot['scenario']}"]
    lines.extend(format_power_summary_lines(snapshot["summary"], prefix="SIM_DEMO"))
    lines.extend(format_fingerprint_lines(snapshot["fingerprint"], prefix="SIM_FINGERPRINT"))
    lines.extend(
        [
            f"SIM_METRIC quality={quality.get('status')} fps={quality.get('fps')}",
            (
                "SIM_METRIC "
                f"resp_bpm={telemetry.get('resp_bpm')} "
                f"heart_bpm={telemetry.get('heart_bpm')} "
                f"variance={telemetry.get('variance')}"
            ),
            (
                "SIM_METRIC "
                f"occupancy={telemetry.get('occupancy', {}).get('class')} "
                f"motion={telemetry.get('motion', {}).get('display_level')}"
            ),
        ]
    )
    return lines


def _scenario_amplitudes(scenario):
    base_shapes = {
        "empty_room": [12, 12, 13, 12, 12, 13, 12, 12, 12, 13, 12, 12, 13, 12, 12, 12],
        "occupied_still": [13, 14, 15, 18, 22, 25, 24, 21, 18, 16, 15, 17, 21, 24, 20, 16],
        "walking": [14, 20, 28, 18, 25, 34, 21, 30, 17, 26, 36, 22, 31, 19, 27, 35],
        "fall_event": [12, 15, 19, 28, 42, 55, 39, 24, 18, 21, 33, 48, 36, 20, 15, 13],
        "weak_live_stream": [10, 30, 12, 34, 11, 29, 13, 36, 12, 33, 14, 31, 10, 35, 11, 32],
    }
    return base_shapes.get(scenario, base_shapes["empty_room"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print deterministic ESP32 CSI demo snapshots.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="occupied_still")
    parser.add_argument("--all", action="store_true", help="Print every demo scenario.")
    args = parser.parse_args(argv)

    scenarios = sorted(SCENARIOS) if args.all else [args.scenario]
    first = True
    for scenario in scenarios:
        if not first:
            print("")
        first = False
        print("\n".join(format_demo_snapshot(build_demo_snapshot(scenario))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
