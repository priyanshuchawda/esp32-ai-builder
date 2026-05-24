import { describe, expect, it } from 'vitest'
import {
  buildFallbackAiAdvice,
  formatAdviceModel,
  type AiAdvice,
  type AiAdvicePayload,
} from './aiAdvice'
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
  },
  motion: {
    display_level: 'UNSTABLE',
    state: 'insufficient_data',
    cadence_spm: 0,
    trusted: false,
  },
}

describe('AI advice frontend helpers', () => {
  it('builds a safe fallback advice card for weak live signals', () => {
    const advice = buildFallbackAiAdvice(weakObservatory)

    expect(advice.provider).toBe('rules')
    expect(advice.status).toBe('weak')
    expect(advice.judge_caption).toContain('blocked')
    expect(advice.why.join(' ')).toContain('low fps')
    expect(advice.telegram_message).toContain('CSI')
  })

  it('formats hosted Gemma fallback model usage for display', () => {
    const advice: AiAdvice = {
      provider: 'gemini',
      model: 'gemma-4-26b-a4b-it',
      primary_model: 'gemma-4-31b-it',
      fallback_used: true,
      status: 'trusted',
      room_interpretation: 'Walking rhythm is visible.',
      why: ['quality is good'],
      next_action: 'Keep the ESP still.',
      judge_caption: 'Gemma explains trusted motion.',
      telegram_message: 'Trusted CSI motion.',
      confidence: 0.82,
    }

    expect(formatAdviceModel(advice)).toBe('gemma-4-26b-a4b-it fallback')
  })

  it('keeps backend payload typing tied to the observatory contract', () => {
    const payload: AiAdvicePayload = {
      title: 'ESP32 Wi-Fi CSI AI Advice',
      generated_at: new Date(0).toISOString(),
      source: weakObservatory.source,
      observatory: weakObservatory,
      advice: buildFallbackAiAdvice(weakObservatory),
    }

    expect(payload.observatory.visual.pose_state).toBe('unknown')
    expect(payload.advice.next_action).toBeTruthy()
  })
})
