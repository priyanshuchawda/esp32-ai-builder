#!/usr/bin/env python3
"""Compact ESP32 live health probe for UDP CSI and optional serial state."""

from __future__ import annotations

import argparse
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
    udp_summary: dict,
    quality_summary: dict,
    modes: dict[int, int],
    occupancy: dict,
    serial_result: SerialProbeResult | None = None,
) -> list[str]:
    status = _overall_status(udp_summary, quality_summary, serial_result)
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
        f"MODES {_format_modes(modes)}",
    ]

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
    return lines


def run_udp_probe(bind_ip: str, udp_port: int, duration_sec: int, min_fps: float) -> tuple[dict, dict, dict[int, int], dict]:
    from backend.csi_quality import SignalQualityMonitor
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
    return udp_summary, quality_summary, modes, occupancy


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a compact ESP32 live health probe.")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--bind-ip", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--min-fps", type=float, default=5.0)
    parser.add_argument("--serial-port")
    parser.add_argument("--serial-baud", type=int, default=115200)
    parser.add_argument("--serial-seconds", type=float, default=5.0)
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--ai-log", type=Path)
    args = parser.parse_args(argv)

    serial_result = None
    if args.serial_port:
        serial_result = probe_serial(args.serial_port, args.serial_baud, args.serial_seconds)

    udp_summary, quality_summary, modes, occupancy = run_udp_probe(
        bind_ip=args.bind_ip,
        udp_port=args.udp_port,
        duration_sec=args.duration,
        min_fps=args.min_fps,
    )
    lines = build_probe_lines(
        issue=args.issue,
        duration_sec=args.duration,
        udp_summary=udp_summary,
        quality_summary=quality_summary,
        modes=modes,
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


def _overall_status(udp_summary: dict, quality_summary: dict, serial_result: SerialProbeResult | None) -> str:
    if udp_summary.get("status") == "FAIL" or quality_summary.get("status") == "BAD":
        return "FAIL"
    if serial_result is not None and serial_result.status == "FAIL":
        return "WARN"
    if udp_summary.get("status") == "WARN" or quality_summary.get("status") == "WEAK":
        return "WARN"
    return "PASS"


def _format_modes(modes: dict[int, int]) -> str:
    if not modes:
        return "none"
    return ",".join(f"{key}:{modes[key]}" for key in sorted(modes))


def _join_reasons(reasons: list[str]) -> str:
    return ",".join(reasons) if reasons else "none"


if __name__ == "__main__":
    raise SystemExit(main())
