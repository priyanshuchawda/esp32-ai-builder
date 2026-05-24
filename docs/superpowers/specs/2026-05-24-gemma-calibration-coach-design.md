# Gemma Calibration Coach Design

## Goal

Turn the existing local labeled-window calibration report into an actionable
capture-readiness explanation. Gemma is an advisor over evaluated CSI
evidence; it is not the detector or classifier.

## Scope

- Read the existing `empty`, `sitting`, and `walking` label records already
  produced by the Python filtering engine.
- Reuse the engine calibration report's readiness and held-out evaluation
  calculations.
- Add `GET /api/calibration-coach` returning compact report data and advice.
- Use hosted `gemma-4-31b-it`, with `gemma-4-26b-a4b-it` fallback, for
  evidence-grounded wording when credentials are available.
- Use deterministic local guidance if hosted inference is unavailable.
- Add a React dashboard panel that displays readiness, records per label,
  evaluation accuracy, model metadata, and the recommended next action.

## Explicit Non-Goals

- No automatic capture sessions.
- No new dataset creation or committed labeled records.
- No model training beyond the existing local calibration evaluator.
- No claim that Gemma recognizes pose from raw CSI.

## Data Boundary

The backend reads local JSONL label records through the existing calibration
report algorithm. The hosted request contains only readiness counts,
evaluation accuracy/confusion, and target label names. It does not contain raw
CSI windows, credentials, or serial data.

## Advice Contract

The endpoint returns:

- `report`: compact readiness and evaluation summary.
- `advice.provider`, `advice.model`, `advice.primary_model`,
  `advice.fallback_used`.
- `advice.status`: `collect`, `improve`, or `ready`.
- `advice.headline`, `advice.evidence`, `advice.next_label`,
  `advice.next_action`, and `advice.judge_caption`.

Rules fallback selects the first missing target label. When labels are ready
but held-out evaluation is weak, it recommends improving the confused class.

## Verification

- Unit tests for report adapter, rules guidance, hosted model fallback, and
  endpoint response.
- React tests/build/lint for the display helpers and UI.
- Live endpoint request against the user's existing local calibration records
  with hosted Gemma enabled.
- Browser verification that the dashboard renders the coach evidence and model
  metadata without starting a new capture.
