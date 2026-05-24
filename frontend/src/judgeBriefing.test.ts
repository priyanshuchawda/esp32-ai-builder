import { describe, expect, it } from 'vitest'
import { formatBriefingModel, type JudgeBriefing } from './judgeBriefing'

const briefing: JudgeBriefing = {
  provider: 'gemini',
  model: 'gemma-4-26b-a4b-it',
  primary_model: 'gemma-4-31b-it',
  fallback_used: true,
  title: 'Captured CSI evidence briefing',
  sensing_claim: 'No trusted activity claim.',
  evidence: ['Signal quality is weak.'],
  calibration_context: 'Capture empty next.',
  limitations: ['Wi-Fi CSI does not provide camera pose.'],
  next_action: 'Collect an empty session.',
}

describe('judge briefing display helpers', () => {
  it('identifies hosted fallback model output', () => {
    expect(formatBriefingModel(briefing)).toBe('gemma-4-26b-a4b-it fallback')
  })

  it('identifies deterministic local fallback output', () => {
    expect(formatBriefingModel({ ...briefing, provider: 'rules' })).toBe('local rules')
  })
})
