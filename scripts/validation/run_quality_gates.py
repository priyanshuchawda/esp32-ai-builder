#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_GATES = (
    ("backend pytest", ("uv", "run", "--project", "backend", "pytest", "-q")),
    ("pio run", ("pio", "run")),
)


def make_run_id(now=None):
    now = now or dt.datetime.now()
    return now.strftime("%Y%m%d-%H%M%S")


def slugify(name):
    return "".join(char.lower() if char.isalnum() else "-" for char in name).strip("-")


def tail_lines(path, limit=24):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def format_result(status, name, elapsed, log_path):
    return f"{status} | {name} | {elapsed:.1f}s | log={log_path}"


def run_gate(name, command, log_dir, tail_limit):
    log_path = log_dir / f"{slugify(name)}.log"
    env = os.environ.copy()
    repo_path = str(Path.cwd())
    env["PYTHONPATH"] = repo_path + os.pathsep + env.get("PYTHONPATH", "")
    start = time.perf_counter()
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        completed = subprocess.run(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            env=env,
        )
    elapsed = time.perf_counter() - start
    status = "PASS" if completed.returncode == 0 else "FAIL"
    print(format_result(status, name, elapsed, log_path.resolve()))
    if completed.returncode != 0:
        print("Relevant final lines:")
        for line in tail_lines(log_path, limit=tail_limit):
            print(line)
    return completed.returncode


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run compact project validation gates.")
    parser.add_argument("--skip-pio", action="store_true", help="Skip PlatformIO firmware build.")
    parser.add_argument("--tail", type=int, default=24, help="Failure log tail line count.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    run_id = make_run_id()
    log_dir = Path("artifacts") / "validation" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    gates = list(DEFAULT_GATES)
    if args.skip_pio:
        gates = [gate for gate in gates if gate[0] != "pio run"]

    exit_code = 0
    for name, command in gates:
        gate_code = run_gate(name, command, log_dir, args.tail)
        if gate_code != 0:
            exit_code = gate_code

    print(f"RUN_ID={run_id}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
