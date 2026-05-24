# Gemma Evidence Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render live ESP-derived Observatory evidence immediately and attach Gemma interpretation asynchronously only for distinct evidence transitions.

**Architecture:** Preserve `/api/observatory-live` as the sensing endpoint and add a POST interpretation endpoint that accepts the existing compact Observatory contract. Add pure signature/timeline helpers in Python and TypeScript so duplicate transitions are deterministic, testable and do not cause repeated hosted-model calls.

**Tech Stack:** FastAPI, Python `google-genai`, pytest, React 19, TypeScript, Vitest, Vite, Three.js.

---

### Task 1: Backend Interpretation Contract

**Files:**
- Modify: `backend/ai_advice.py`
- Modify: `backend/main.py`
- Modify: `backend/test_ai_advice.py`

- [ ] **Step 1: Write failing backend tests**

Add tests proving that an event signature is deterministic and that `POST /api/ai-advice/interpret` interprets the submitted compact state without invoking `run_udp_probe`:

```python
def test_observatory_event_signature_tracks_display_transition():
    from backend.ai_advice import build_event_signature

    first = build_event_signature(WEAK_OBSERVATORY)
    changed = build_event_signature({**WEAK_OBSERVATORY, "signal": {**WEAK_OBSERVATORY["signal"], "quality": "GOOD"}})

    assert first == "actual_udp_probe|WEAK|weak|unknown|unknown|insufficient_data"
    assert changed != first


def test_ai_interpret_endpoint_uses_posted_snapshot_without_new_probe(monkeypatch):
    monkeypatch.setattr("backend.main.run_udp_probe", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("probe called")))
    monkeypatch.setattr("backend.main.query_ai_advice", lambda _observatory: {"provider": "rules", "model": "rules"})

    response = TestClient(app).post("/api/ai-advice/interpret", json={"observatory": WEAK_OBSERVATORY})

    assert response.status_code == 200
    assert response.json()["event_signature"].startswith("actual_udp_probe|WEAK|")
```

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
backend\.venv\Scripts\python.exe -m pytest -q backend\test_ai_advice.py
```

Expected: failures because `build_event_signature` and `/api/ai-advice/interpret` do not exist.

- [ ] **Step 3: Implement minimal API support**

Add `build_event_signature(observatory)` in `backend/ai_advice.py` by joining the exact UI transition fields. In `backend/main.py`, allow POST in CORS, accept a validated body containing `observatory`, return `generated_at`, `source`, `event_signature` and `query_ai_advice(observatory)`, without reading hardware.

- [ ] **Step 4: Verify backend focused tests pass**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
backend\.venv\Scripts\python.exe -m pytest -q backend\test_ai_advice.py
```

Expected: all advice API tests pass.

### Task 2: Frontend Evidence Timeline State

**Files:**
- Create: `frontend/src/evidenceTimeline.ts`
- Create: `frontend/src/evidenceTimeline.test.ts`
- Modify: `frontend/src/aiAdvice.ts`

- [ ] **Step 1: Write failing TypeScript tests**

Create tests for:

```typescript
expect(eventSignature(weakObservatory)).toBe('actual_udp_probe|WEAK|weak|unknown|unknown|insufficient_data')
expect(beginEvidenceEvent([], weakObservatory, '2026-05-24T00:00:00Z')).toHaveLength(1)
expect(beginEvidenceEvent(existing, weakObservatory, '2026-05-24T00:01:00Z')).toBe(existing)
expect(completeEvidenceEvent(pending, signature, advice)[0].advice).toEqual(advice)
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
cd frontend
pnpm.cmd run test
```

Expected: test import fails because `evidenceTimeline.ts` does not exist.

- [ ] **Step 3: Implement pure timeline helpers**

Define `EvidenceEvent` with `signature`, `capturedAt`, `observatory`, `state: 'pending' | 'complete' | 'error'`, and nullable `advice`. Implement `eventSignature`, `beginEvidenceEvent` with a five-item cap and duplicate suppression, and `completeEvidenceEvent`.

- [ ] **Step 4: Verify helper tests pass**

Run `pnpm.cmd run test` in `frontend`.

Expected: timeline and existing AI advice tests pass.

### Task 3: Non-Blocking React Flow And Timeline Display

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.css`
- Modify: `frontend/src/aiAdvice.test.ts` or `frontend/src/evidenceTimeline.test.ts`

- [ ] **Step 1: Add a testable contract for pending/completed rows**

Expand the timeline helper tests to verify model-label completion and pending evidence state before modifying the component.

- [ ] **Step 2: Replace combined live fetch with split acquisition/interpretation**

In `runObservatoryLiveProbe`, fetch `/api/observatory-live?mode=live...`, set `observatoryPayload` and `observatoryStatus='done'` immediately, then add a pending evidence entry and POST `{ observatory }` to `/api/ai-advice/interpret` only when its signature is new. On advice failure, complete the row with local `buildFallbackAiAdvice`.

- [ ] **Step 3: Render timeline in the Observatory HUD**

Render up to five timeline entries headed `Evidence timeline`, label sensor fields as `ESP inference`, label advice as `Gemma interpretation`, and label Telegram output as `Message ready`.

- [ ] **Step 4: Verify frontend checks**

Run:

```powershell
cd frontend
pnpm.cmd run test
pnpm.cmd run lint
pnpm.cmd run build
```

Expected: tests, lint and build pass.

### Task 4: Documentation And Integrated Validation

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`

- [ ] **Step 1: Document the distinction and API**

Document that `/api/observatory-live` captures ESP evidence and `/api/ai-advice/interpret` interprets an already captured compact snapshot. State that raw CSI remains local and Telegram text is not a delivery acknowledgement.

- [ ] **Step 2: Verify complete backend and frontend gates**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path
backend\.venv\Scripts\python.exe -m pytest -q
cd frontend
pnpm.cmd run test
pnpm.cmd run lint
pnpm.cmd run build
```

Expected: all commands pass.

- [ ] **Step 3: Live ESP and browser evidence**

Start the backend on a free port, build/serve the frontend on another free port, capture `/api/observatory-live?mode=live&duration=3&udp_port=5005`, POST that exact payload to `/api/ai-advice/interpret`, and confirm in the browser that the scene appears before or independently of the timeline interpretation row. Store only compact pass/fail/model/quality metadata in `ai.log`.

- [ ] **Step 4: Publish issue PR**

Stage only `#104` files, commit, push `feat/104`, create the PR, confirm GitGuardian/check status, merge, delete the feature branch, and verify the merged result.
