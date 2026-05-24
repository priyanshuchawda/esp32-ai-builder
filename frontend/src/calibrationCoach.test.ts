import { describe, expect, it } from 'vitest'
import {
  formatCoachAccuracy,
  formatCoachNextLabel,
  labelReadiness,
  type CalibrationCoachPayload,
} from './calibrationCoach'

const payload: CalibrationCoachPayload = {
  generated_at: '2026-05-24T00:00:00Z',
  report: {
    summary: { total_records: 9, labels: {} },
    readiness: {
      ready: false,
      labels: {
        empty: { records: 0, needed: 3, ready: false },
        sitting: { records: 4, needed: 0, ready: true },
        walking: { records: 5, needed: 0, ready: true },
      },
      next_labels: ['empty'],
    },
    evaluation: { eligible: true, accuracy: 0.5 },
  },
  advice: {
    provider: 'gemini',
    model: 'gemma-4-31b-it',
    primary_model: 'gemma-4-31b-it',
    fallback_used: false,
    status: 'collect',
    headline: 'Collect an empty baseline.',
    evidence: ['empty needs three usable windows'],
    next_label: 'empty',
    next_action: 'Record a stable empty session next.',
    judge_caption: 'Calibration requires empty-room evidence.',
  },
}

describe('calibration coach display helpers', () => {
  it('formats held-out accuracy only when evaluation is eligible', () => {
    expect(formatCoachAccuracy(payload.report)).toBe('50% held-out')
    expect(
      formatCoachAccuracy({
        ...payload.report,
        evaluation: { eligible: false },
      }),
    ).toBe('not eligible')
  })

  it('formats the recommended capture label', () => {
    expect(formatCoachNextLabel(payload.advice)).toBe('capture empty')
    expect(formatCoachNextLabel({ ...payload.advice, next_label: 'none' })).toBe(
      'coverage complete',
    )
  })

  it('returns missing labels with their usable record counts', () => {
    expect(labelReadiness(payload.report, 'empty')).toEqual({
      records: 0,
      needed: 3,
      ready: false,
    })
  })
})
