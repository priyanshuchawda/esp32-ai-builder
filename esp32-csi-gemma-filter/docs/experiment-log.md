# Wi-Fi CSI Filtering Experiment Log

This document records runs of the CSI filtering engine, tracking noise reduction performance across different modes.

## Log Template

| Date/Time | Mode (Sim/Serial) | Duration (s) | Advisor Used (Gemma/Rule) | Selected Filter | Raw Var | Filtered Var | Noise Reduction (%) | Notes/Observations |
|---|---|---|---|---|---|---|---|---|
| *YYYY-MM-DD HH:MM* | *Simulate/Serial* | *20* | *Gemma / Rule-based* | *median* | *0.000* | *0.000* | *0.0%* | *Observation detail* |

---

## Log Entries

### Entry 1 (Simulated Baseline Run)
- **Date/Time**: 2026-05-21 19:15
- **Mode**: Simulate
- **Duration**: 20 seconds
- **Advisor Used**: Rule-based (Ollama Offline Fallback)
- **Selected Filter**: median (spikes present)
- **Raw Var**: 29.4201
- **Filtered Var**: 3.6210
- **Noise Reduction**: 87.69%
- **Notes/Observations**: Successfully tested Hampel and median fallbacks; the simulator generated spike values which were successfully flattened, drastically reducing variance.
