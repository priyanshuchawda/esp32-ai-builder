import type { AiAdvice } from './aiAdvice'
import type { ObservatoryPayload } from './ObservatoryScene'

export type EvidenceEvent = {
  signature: string
  capturedAt: string
  observatory: ObservatoryPayload
  state: 'pending' | 'complete'
  advice: AiAdvice | null
}

export function eventSignature(observatory: ObservatoryPayload): string {
  return [
    observatory.source,
    observatory.signal.quality,
    observatory.visual.trust,
    observatory.visual.pose_state,
    observatory.persons.range,
    observatory.motion.state,
  ].join('|')
}

export function beginEvidenceEvent(
  events: EvidenceEvent[],
  observatory: ObservatoryPayload,
  capturedAt: string,
): EvidenceEvent[] {
  const signature = eventSignature(observatory)
  if (events[0]?.signature === signature) {
    return events
  }
  const event: EvidenceEvent = {
    signature,
    capturedAt,
    observatory,
    state: 'pending',
    advice: null,
  }
  return [
    event,
    ...events,
  ].slice(0, 5)
}

export function completeEvidenceEvent(
  events: EvidenceEvent[],
  signature: string,
  advice: AiAdvice,
): EvidenceEvent[] {
  return events.map((event) =>
    event.signature === signature
      ? {
          ...event,
          state: 'complete',
          advice,
        }
      : event,
  )
}
