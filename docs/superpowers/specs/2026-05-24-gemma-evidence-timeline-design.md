# Gemma Evidence Timeline Design

**Issue:** #104 - Add non-blocking Gemma evidence timeline to Observatory  
**Status:** Design for review  
**Approved direction:** React Observatory is the judge-facing UI; ESP/DSP remains the sensing authority and Gemma is an interpretation layer.

## Purpose

Make Gemma visibly useful without presenting it as a sensor. A judge should see the exact ESP-derived evidence that caused an event, followed by Gemma's bounded explanation of that same evidence. Live scene rendering must not wait for the hosted model.

## Existing Problem

Live Observatory currently calls `GET /api/ai-advice?mode=live`, which performs the ESP probe and Gemma request in one operation. The 3D scene therefore waits for model latency or timeout. Calling advice again would also collect a new RF window, so the displayed signal and the explanation may not describe the same capture.

## Approaches Considered

1. Keep the combined endpoint and add a loading state.
   This is smallest, but the avatar remains blocked by model latency and the judge cannot distinguish ESP sensing from AI generation.

2. Poll sensor state and request Gemma for every refresh.
   This looks active, but it spends API calls on unchanged RF state and floods the timeline with duplicate explanations.

3. Split acquisition from event interpretation and cache by transition signature.
   This is the selected approach. It makes ESP evidence visible first, sends one compact stable snapshot to Gemma only for a new event, and reuses advice when no meaningful state changed.

## Data Flow

1. The React UI requests `GET /api/observatory-live?mode=live&duration=3&udp_port=5005`.
2. As soon as the endpoint returns, React updates the 3D scene, signal/vitals gating and event evidence row.
3. A pure frontend helper computes an event signature from trusted display fields:
   `source`, `signal.quality`, `visual.trust`, `visual.pose_state`, `persons.range`, and `motion.state`.
4. If the signature is new, React marks the event interpretation as pending and submits the exact returned observatory payload to a new interpretation endpoint.
5. The backend sends only the compact observatory contract to hosted Gemma using existing primary/fallback/rules logic and trust alignment.
6. The matching timeline entry is completed with provider, model, fallback flag, caption, reasons, next action and Telegram-ready message text.
7. If the signature is unchanged, the existing timeline/advice remains in place and no hosted call is made.

## API Design

Retain the existing `GET /api/ai-advice` route for current demo compatibility.

Add:

```text
POST /api/ai-advice/interpret
body: { "observatory": <compact ObservatoryPayload> }
response: {
  "generated_at": "<UTC timestamp>",
  "source": "...",
  "event_signature": "...",
  "advice": <existing AiAdvice contract>
}
```

The server validates that required observatory sections are present and derives the event signature server-side as audit metadata. It does not accept raw CSI arrays and does not run a second ESP probe.

## UI Design

The Observatory keeps the existing full-screen scene and HUD. Add an unframed `Evidence timeline` section below or within the right HUD flow, sized for the most recent five events.

Each entry shows:

- timestamp and state transition label, such as `GOOD / walking candidate`
- evidence chips: quality, FPS, trust, pose state and person candidate
- AI state: `pending`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it fallback`, or `local rules`
- one judge caption and the next action after advice completes

Language remains explicit: `ESP inference` labels the evidence and `Gemma interpretation` labels the generated explanation. Telegram text is displayed as `message ready`, not `sent`, unless a real send acknowledgement exists.

## Failure And Trust Handling

- Weak or blocked ESP state is still rendered immediately, with the transparent/unknown avatar already used by Observatory.
- Gemma may explain why evidence is blocked, but existing backend trust alignment prevents it from upgrading an untrusted sensor claim.
- Hosted timeout or API failure completes the timeline entry with deterministic rules advice.
- An advice failure never removes the sensor snapshot or blocks further live captures.
- Only compact state is transmitted to Gemini API; secrets, raw CSI frames and dataset files remain local.

## Testing

Backend:

- POST interpretation endpoint uses the submitted observatory snapshot and never calls the live probe.
- Server event signature is stable for identical evidence and changes for meaningful state transitions.
- Weak-state hosted wording remains trust-gated.
- Rules fallback response remains valid when hosted invocation is unavailable.

Frontend:

- Event signature and timeline reducer append only changed events.
- Scene payload updates before advice resolution.
- Pending entries update with hosted/fallback/rules model metadata.
- Telegram display is labelled as ready text, not delivery status.

Validation:

- Backend pytest gate and frontend Vitest/lint/build.
- Local API and compiled React browser smoke.
- Live ESP capture on UDP `5005` showing evidence immediately and one interpretation entry per changed capture.
- Compact results recorded in local `ai.log`, without tokens or raw captures.

## Deferred Follow-Up

Issue #105 will reuse the interpretation presentation for calibration coaching. Automatic interval-based monitoring and acknowledged Telegram delivery are separate features and should not be implied by this PR.
