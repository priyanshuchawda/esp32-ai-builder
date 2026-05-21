# Gemma Noise Filtering Policy

This document explains the communication and control policy applied to local LLM-assisted filtering.

## 1. Summary Statistics Over Raw Telemetry
Wi-Fi CSI packets typically arrive at high sampling rates (e.g. 10 Hz to 100 Hz or more). Running real-time LLM inference for every single frame is computationally impossible on consumer hardware.
Therefore:
- Raw packet information remains in the fast Python DSP stream.
- The Python engine groups samples into windows (e.g. 2-second blocks).
- Only statistical summary features (11 values) are transmitted to the LLM.
- Bandwidth and computation are reduced by over **98%**.

## 2. Strict JSON Protocol
The model `gemma4:e4b` is prompted to output a single JSON object with no conversational preamble or markdown code blocks.

Example Expected Schema:
```json
{
  "filter": "median",
  "window_size": 5,
  "outlier_threshold": 3.0,
  "lowpass_alpha": 0.25,
  "confidence": 0.82,
  "reason": "High outlier ratio suggests spike noise, so median filtering is best."
}
```

## 3. Python Verification & Fallback Mechanisms
To prevent program crashes due to LLM errors or unavailable service:
1. **JSON Cleansing**: Code blocks (````json ... ````) are stripped.
2. **Key Validation**: If any of the required keys (`filter`, `window_size`, `confidence`, etc.) are missing, the response is discarded.
3. **Local Fallback Rules**: If Ollama is offline, times out, or returns invalid syntax, the Python advisor falls back to a deterministic rule-based decision block:
   - `outlier_ratio > 0.10` -> `median` filter (window size 5)
   - `signal_std > 2.0` -> `moving_average` (window size 7)
   - `signal_std > 0.2` -> `lowpass` (alpha 0.25)
   - Otherwise -> `none`
