# Gemma Judge Briefing Design

## Goal

Produce a concise, on-demand explanation of a captured Observatory event for
a judge or operator. The report combines an already displayed ESP-derived
snapshot with compact local calibration readiness; it does not trigger new
sensing or training.

## API Contract

`POST /api/judge-briefing` accepts `{ "observatory": <compact snapshot> }`.
The backend reads the existing compact calibration report and returns:

- the sensor event signature;
- `briefing.provider`, `model`, primary/fallback status;
- `briefing.title`, `sensing_claim`, `evidence`, `calibration_context`,
  `limitations`, and `next_action`.

Hosted Gemma receives only compact Observatory fields and compact calibration
report output. Raw CSI windows and credentials remain local.

## Guardrails

- A weak/blocked snapshot cannot become a trusted presence or activity claim.
- Briefings always state that activity is inferred from Wi-Fi CSI, not camera
  pose or identity.
- Hosted failure returns deterministic wording with the same trust gate.

## UI

Observatory adds an explicit **Generate briefing** action. It appears after the
current scene and interpretation and displays a compact report panel with
model status, claim, evidence, limitations, and next action.

## Validation

Use unit tests for no-reprobe behavior, trust alignment, hosted fallback and
frontend formatting. Then verify on a real ESP snapshot, hosted Gemma, and the
browser UI.
