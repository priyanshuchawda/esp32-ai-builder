import { describe, expect, it } from 'vitest'
import type { AiAdvice } from './aiAdvice'
import {
  beginEvidenceEvent,
  completeEvidenceEvent,
  eventSignature,
  type EvidenceEvent,
} from './evidenceTimeline'
import type { ObservatoryPayload } from './ObservatoryScene'

const weakObservatory: ObservatoryPayload = {
  source: 'actual_udp_probe',
  truth_label: 'visualization_only_not_densepose',
  visual: {
    pose_state: 'unknown',
    avatar: 'transparent',
    trust: 'weak',
    opacity: 0.28,
    claim: 'CSI-inferred activity visualization',
    reasons: ['signal_quality_not_good'],
  },
  persons: {
    range: 'unknown',
    label: 'count blocked',
    trusted: false,
  },
  signal: {
    quality: 'WEAK',
    fps: 2.1,
    packets: 8,
    reasons: ['low_fps'],
  },
  vitals: {
    resp_bpm: 0,
    heart_bpm: 0,
    available: false,
    trusted: false,
    label: 'not available',
    reasons: ['signal_quality_not_good'],
  },
  motion: {
    display_level: 'UNSTABLE',
    state: 'insufficient_data',
    cadence_spm: 0,
    trusted: false,
  },
}

const rulesAdvice: AiAdvice = {
  provider: 'rules',
  model: 'rules',
  primary_model: 'rules',
  fallback_used: false,
  status: 'weak',
  room_interpretation: 'Signal is not trusted enough for a room-state claim.',
  why: ['signal quality is not good'],
  next_action: 'Improve signal stability.',
  judge_caption: 'RF quality blocks a trusted claim.',
  telegram_message: 'CSI quality watch: signal weak.',
  confidence: 0.45,
}

describe('Gemma evidence timeline helpers', () => {
  it('creates a deterministic signature from visible ESP evidence', () => {
    expect(eventSignature(weakObservatory)).toBe(
      'actual_udp_probe|WEAK|weak|unknown|unknown|insufficient_data',
    )
  })

  it('adds one pending event and suppresses an unchanged transition', () => {
    const first = beginEvidenceEvent([], weakObservatory, '2026-05-24T00:00:00Z')
    const repeated = beginEvidenceEvent(first, weakObservatory, '2026-05-24T00:01:00Z')

    expect(first).toHaveLength(1)
    expect(first[0].state).toBe('pending')
    expect(repeated).toBe(first)
  })

  it('caps stored evidence to the five latest distinct events', () => {
    let events: EvidenceEvent[] = []
    for (let index = 0; index < 6; index += 1) {
      const state = {
        ...weakObservatory,
        motion: { ...weakObservatory.motion, state: `state-${index}` },
      }
      events = beginEvidenceEvent(events, state, `2026-05-24T00:00:0${index}Z`)
    }

    expect(events).toHaveLength(5)
    expect(events[0].observatory.motion.state).toBe('state-5')
  })

  it('completes only the matching pending event with advice', () => {
    const pending = beginEvidenceEvent([], weakObservatory, '2026-05-24T00:00:00Z')
    const result = completeEvidenceEvent(pending, eventSignature(weakObservatory), rulesAdvice)

    expect(result[0].state).toBe('complete')
    expect(result[0].advice).toEqual(rulesAdvice)
  })
})
