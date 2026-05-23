# ESP32 RuView Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the ESP32 DevKit V1 RuView-compatible pipeline by making live readings trustworthy before adding higher-level AI behavior.

**Architecture:** Keep ESP32 firmware lightweight and keep all calibration, quality scoring, confidence gating, Gemma/Gemini summaries, and Telegram decisions on the laptop. Each GitHub issue lands independently through `feat/<issue-number>` branches, a PR, merge, and branch deletion.

**Tech Stack:** PlatformIO Arduino ESP32 firmware, Python/uv backend, Streamlit dashboard, pytest, GitHub CLI.

---

### Issue #21: Adaptive Empty-Room Calibration

- [x] Add a laptop-side `PresenceCalibration` model in `backend/csi_calibration.py`.
- [x] Add tests that prove calibration learns baseline variance/std and raises threshold above room noise.
- [x] Wire calibrated threshold into `RuViewDSP` while preserving manual fallback.
- [x] Surface calibration state in telemetry and Streamlit sidebar.
- [x] Verify with focused pytest, Python compile, PlatformIO build, and live COM5/UDP sample.

### Issue #22: Live CSI Signal Quality Scoring

- [x] Track FPS, sequence gaps, RSSI spread, timeout age, and subcarrier mix.
- [x] Compute `GOOD`, `WEAK`, or `BAD` quality state with reasons.
- [x] Show quality in terminal and Streamlit UI.
- [x] Verify with unit tests and live UDP sample.

### Issue #23: Test Collection Hygiene

- [x] Add pytest configuration so active tests run without collecting archived RuView/legacy tests.
- [x] Document intended commands.
- [x] Verify root and scoped test commands.

### Issue #24: Calibrated Confidence Gating

- [x] Combine calibration status, signal quality, and presence decision into confidence.
- [x] Gate Telegram/AI summary wording behind confidence.
- [x] Verify low-confidence suppression and high-confidence alert paths.
