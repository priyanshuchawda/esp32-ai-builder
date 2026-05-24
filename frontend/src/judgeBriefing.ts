import type { CalibrationReport } from './calibrationCoach'

export type JudgeBriefing = {
  provider: string
  model: string
  primary_model: string
  fallback_used: boolean
  title: string
  sensing_claim: string
  evidence: string[]
  calibration_context: string
  limitations: string[]
  next_action: string
}

export type JudgeBriefingPayload = {
  generated_at: string
  event_signature: string
  calibration: CalibrationReport
  briefing: JudgeBriefing
}

export function formatBriefingModel(briefing: JudgeBriefing): string {
  if (briefing.provider === 'rules') {
    return 'local rules'
  }
  return briefing.fallback_used ? `${briefing.model} fallback` : briefing.model
}
