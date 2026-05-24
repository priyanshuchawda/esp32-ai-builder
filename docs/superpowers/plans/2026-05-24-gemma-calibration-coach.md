# Gemma Calibration Coach Implementation Plan

## Backend

1. Add failing tests for loading the engine calibration report and for
   deterministic advice selection.
2. Add a small adapter that executes the existing `calibration_report.py`
   module functions against local labels without copying its math.
3. Add failing tests for hosted Gemma metadata/fallback and API behavior.
4. Add a calibration-specific prompt/parser and `GET /api/calibration-coach`.

## Frontend

1. Add failing tests for calibration display formatting.
2. Add types and a dashboard Calibration Coach panel with explicit refresh.
3. Display label readiness, evaluation accuracy, advisor model/fallback, and
   next action; do not add data collection controls.

## Documentation And Validation

1. Document the endpoint and dashboard workflow.
2. Run changed-file lint, backend tests, filter-engine tests, frontend
   tests/lint/build.
3. Request the coach endpoint with the local existing report and hosted Gemma.
4. Verify the React panel in a browser.
5. Open, check, and merge `feat/105`; keep raw label data local.
