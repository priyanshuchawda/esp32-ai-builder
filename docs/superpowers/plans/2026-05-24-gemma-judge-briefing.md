# Gemma Judge Briefing Implementation Plan

1. Add failing backend tests for rule guardrails, hosted fallback, and a
   no-reprobe `POST /api/judge-briefing` response.
2. Implement the briefing prompt/parser and API using the existing event
   signature and calibration snapshot.
3. Add failing frontend formatting tests and typed response module.
4. Add an explicit briefing button and report panel to Observatory.
5. Update operator/API documentation.
6. Run Python and frontend gates, then real ESP, hosted Gemma, and browser
   verification before the PR is merged.
