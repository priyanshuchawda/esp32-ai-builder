#!/usr/bin/env python3
"""Compact ESP32 live health probe for UDP CSI and optional serial state."""

from __future__ import annotations

import argparse
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SerialProbeResult:
    status: str
    port: str
    lines: int = 0
    error_type: str | None = None
    error_message: str | None = None


def summarize_udp(packet_count: int, elapsed_sec: float, min_fps: float = 5.0) -> dict:
    fps = round(packet_count / max(elapsed_sec, 0.001), 2)
    if packet_count <= 0:
        return {"status": "FAIL", "reason": "no_packets", "packets": packet_count, "fps": 0.0}
    if fps < min_fps:
        return {"status": "WARN", "reason": "low_fps", "packets": packet_count, "fps": fps}
    return {"status": "PASS", "reason": "ok", "packets": packet_count, "fps": fps}


def build_probe_lines(
    *,
    issue: int | None,
    duration_sec: int,
    config_summary: dict | None = None,
    udp_summary: dict,
    quality_summary: dict,
    modes: dict[int, int],
    fingerprint: dict | None = None,
    occupancy: dict,
    serial_result: SerialProbeResult | None = None,
) -> list[str]:
    from backend.csi_fingerprint import format_fingerprint_lines
    from backend.csi_power_summary import build_power_summary, format_power_summary_lines

    status = _overall_status(udp_summary, quality_summary, serial_result, config_summary)
    issue_part = f"issue={issue} " if issue is not None else ""
    lines = [
        f"LIVE_PROBE {issue_part}status={status} duration_sec={duration_sec}".strip(),
        (
            "UDP_STATUS "
            f"{udp_summary.get('status')} "
            f"packets={udp_summary.get('packets', 0)} "
            f"fps={udp_summary.get('fps', 0.0)} "
            f"reason={udp_summary.get('reason', 'unknown')}"
        ),
    ]

    if config_summary is not None:
        lines.append(
            "CONFIG_STATUS "
            f"{config_summary.get('status')} "
            f"target_ip={config_summary.get('target_ip', 'unknown')} "
            f"local_ip={config_summary.get('local_ip', 'unknown')} "
            f"target_port={config_summary.get('target_port', 'unknown')} "
            f"reason={config_summary.get('reason', 'unknown')}"
        )

    lines.append(f"MODES {_format_modes(modes)}")

    if serial_result is not None:
        serial_line = (
            "SERIAL_STATUS "
            f"{serial_result.status} "
            f"port={serial_result.port} "
            f"lines={serial_result.lines}"
        )
        if serial_result.error_type:
            serial_line += f" error={serial_result.error_type}"
        lines.append(serial_line)

    lines.extend(
        [
            (
                "QUALITY_STATUS "
                f"{quality_summary.get('status', 'UNKNOWN')} "
                f"reasons={_join_reasons(quality_summary.get('reasons', []))}"
            ),
            (
                "OCCUPANCY "
                f"{occupancy.get('class', 'UNKNOWN')} "
                f"trusted={occupancy.get('trusted', False)} "
                f"reasons={_join_reasons(occupancy.get('reasons', []))}"
            ),
        ]
    )
    summary_telemetry = {
        "presence": occupancy.get("class") == "OCCUPIED",
        "occupancy": occupancy,
        "motion": {"display_level": "UNSTABLE", "trusted": False}
        if quality_summary.get("status") in {"BAD", "WEAK"}
        else {},
    }
    lines.extend(format_power_summary_lines(build_power_summary(summary_telemetry, quality_summary), prefix="POWER_SUMMARY"))
    if fingerprint is not None:
        lines.extend(format_fingerprint_lines(fingerprint, prefix="CSI_FINGERPRINT"))
    for action in recommend_next_actions(config_summary, udp_summary, quality_summary, serial_result):
        lines.append(f"NEXT_ACTION {action}")
    return lines


def run_udp_probe(bind_ip: str, udp_port: int, duration_sec: int, min_fps: float) -> tuple[dict, dict, dict[int, int], dict, dict, dict]:
    from backend.csi_fingerprint import build_fingerprint
    from backend.csi_quality import SignalQualityMonitor
    from backend.csi_spectrogram import build_spectrogram
    from backend.csi_subcarriers import SubcarrierSelector
    from backend.csi_terminal_receiver import RuViewDSP, load_evaluator_report, parse_adr018_packet, with_presence_confidence
    from backend.live_occupancy import classify_occupancy

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_ip, udp_port))
    sock.settimeout(0.2)

    dsp = RuViewDSP(fps=50.0)
    quality = SignalQualityMonitor()
    selector = SubcarrierSelector()
    packet_count = 0
    modes: dict[int, int] = {}
    latest_amplitudes = []
    recent_frames = []
    started = time.time()
    end_at = started + duration_sec

    try:
        while time.time() < end_at:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            packet = parse_adr018_packet(data)
            if not packet:
                continue
            packet_count += 1
            latest_amplitudes = packet["amplitudes"]
            recent_frames.append(packet["amplitudes"])
            if len(recent_frames) > 96:
                recent_frames.pop(0)
            modes[packet["n_subcarriers"]] = modes.get(packet["n_subcarriers"], 0) + 1
            quality.record_packet(
                seq=packet["seq"],
                rssi=packet["rssi"],
                n_subcarriers=packet["n_subcarriers"],
                timestamp=time.time(),
            )
            selected = selector.add_frame(packet["amplitudes"])["selected_signal"]
            dsp.add_sample(selected)
    finally:
        sock.close()

    elapsed = time.time() - started
    udp_summary = summarize_udp(packet_count, elapsed, min_fps=min_fps)
    quality_summary = quality.summary(now=time.time())
    telemetry = with_presence_confidence(dsp.process_telemetry(), quality_summary)
    occupancy = classify_occupancy(telemetry, quality_summary, load_evaluator_report())
    fingerprint = build_fingerprint(latest_amplitudes, bins=16)
    spectrogram = build_spectrogram(recent_frames, time_bins=24, subcarrier_bins=16)
    return udp_summary, quality_summary, modes, occupancy, fingerprint, spectrogram


def load_firmware_network_config(path: Path | None = None, text: str | None = None) -> dict:
    if text is None:
        if path is None or not path.exists():
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")

    target_ip = _read_define_string(text, "TARGET_IP")
    target_port = _read_define_int(text, "TARGET_PORT")
    config = {}
    if target_ip:
        config["target_ip"] = target_ip
    if target_port is not None:
        config["target_port"] = target_port
    return config


def summarize_target_ip(target_ip: str | None, local_ip: str | None, target_port: int | None = None) -> dict:
    if not target_ip:
        return {
            "status": "WARN",
            "reason": "target_ip_missing",
            "target_ip": "unknown",
            "local_ip": local_ip or "unknown",
            "target_port": target_port or "unknown",
        }
    if not local_ip:
        return {
            "status": "WARN",
            "reason": "local_ip_unknown",
            "target_ip": target_ip,
            "local_ip": "unknown",
            "target_port": target_port or "unknown",
        }
    if target_ip != local_ip:
        return {
            "status": "FAIL",
            "reason": "target_ip_mismatch",
            "target_ip": target_ip,
            "local_ip": local_ip,
            "target_port": target_port or "unknown",
        }
    return {
        "status": "PASS",
        "reason": "ok",
        "target_ip": target_ip,
        "local_ip": local_ip,
        "target_port": target_port or "unknown",
    }


def detect_local_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def probe_serial(port: str, baud: int, seconds: float) -> SerialProbeResult:
    try:
        import serial
    except ImportError as exc:
        return SerialProbeResult(status="SKIP", port=port, error_type=type(exc).__name__, error_message=str(exc))

    lines = 0
    try:
        ser = serial.Serial(port, baud, timeout=0.5)
        try:
            end_at = time.time() + seconds
            while time.time() < end_at:
                if ser.readline():
                    lines += 1
        finally:
            ser.close()
    except Exception as exc:
        error_type = "PermissionError" if "PermissionError" in str(exc) else type(exc).__name__
        return SerialProbeResult(status="FAIL", port=port, lines=lines, error_type=error_type, error_message=str(exc))

    return SerialProbeResult(status="PASS" if lines else "WARN", port=port, lines=lines)


def recommend_next_actions(
    config_summary: dict | None,
    udp_summary: dict,
    quality_summary: dict,
    serial_result: SerialProbeResult | None,
) -> list[str]:
    actions: list[str] = []

    if config_summary is not None and config_summary.get("status") == "FAIL":
        if config_summary.get("reason") == "target_ip_mismatch":
            actions.append("update_firmware_target_ip")

    no_udp = udp_summary.get("status") == "FAIL" and udp_summary.get("reason") == "no_packets"
    serial_locked = serial_result is not None and serial_result.status == "FAIL"
    if serial_locked and serial_result.error_type == "PermissionError":
        actions.append("release_or_replug_serial_port")

    if no_udp:
        actions.append("reset_or_reflash_esp_streaming_firmware")

    reasons = set(quality_summary.get("reasons", []))
    if "low_fps" in reasons or "very_low_fps" in reasons:
        actions.append("improve_wifi_signal_or_reduce_receiver_load")
    if "rssi_unstable" in reasons:
        actions.append("stabilize_esp_router_position")

    return _dedupe(actions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a compact ESP32 live health probe.")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--bind-ip", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--min-fps", type=float, default=5.0)
    parser.add_argument("--serial-port")
    parser.add_argument("--serial-baud", type=int, default=115200)
    parser.add_argument("--serial-seconds", type=float, default=5.0)
    parser.add_argument("--credentials", type=Path, default=Path("include/wifi_credentials.h"))
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--ai-log", type=Path)
    args = parser.parse_args(argv)

    serial_result = None
    if args.serial_port:
        serial_result = probe_serial(args.serial_port, args.serial_baud, args.serial_seconds)

    udp_summary, quality_summary, modes, occupancy, fingerprint, _spectrogram = run_udp_probe(
        bind_ip=args.bind_ip,
        udp_port=args.udp_port,
        duration_sec=args.duration,
        min_fps=args.min_fps,
    )
    firmware_config = load_firmware_network_config(path=args.credentials)
    config_summary = summarize_target_ip(
        target_ip=firmware_config.get("target_ip"),
        local_ip=detect_local_ip(),
        target_port=firmware_config.get("target_port"),
    )
    lines = build_probe_lines(
        issue=args.issue,
        duration_sec=args.duration,
        config_summary=config_summary,
        udp_summary=udp_summary,
        quality_summary=quality_summary,
        modes=modes,
        fingerprint=fingerprint,
        occupancy=occupancy,
        serial_result=serial_result,
    )

    output = "\n".join(lines)
    print(output)
    if args.ai_log:
        args.ai_log.parent.mkdir(parents=True, exist_ok=True)
        with args.ai_log.open("a", encoding="utf-8") as log_file:
            log_file.write(output + "\n")

    return 1 if lines[0].startswith("LIVE_PROBE") and "status=FAIL" in lines[0] else 0


def _overall_status(
    udp_summary: dict,
    quality_summary: dict,
    serial_result: SerialProbeResult | None,
    config_summary: dict | None,
) -> str:
    if config_summary is not None and config_summary.get("status") == "FAIL":
        return "FAIL"
    if udp_summary.get("status") == "FAIL" or quality_summary.get("status") == "BAD":
        return "FAIL"
    if serial_result is not None and serial_result.status == "FAIL":
        return "WARN"
    if udp_summary.get("status") == "WARN" or quality_summary.get("status") == "WEAK":
        return "WARN"
    return "PASS"


def _read_define_string(text: str, name: str) -> str | None:
    match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+\"([^\"]+)\"", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def _read_define_int(text: str, name: str) -> int | None:
    match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+(\d+)", text, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _format_modes(modes: dict[int, int]) -> str:
    if not modes:
        return "none"
    return ",".join(f"{key}:{modes[key]}" for key in sorted(modes))


def _join_reasons(reasons: list[str]) -> str:
    return ",".join(reasons) if reasons else "none"


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
