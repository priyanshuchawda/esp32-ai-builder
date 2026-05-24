export type CalibrationLabelReadiness = {
  records: number
  needed: number
  ready: boolean
  ignored?: number
}

export type CalibrationReport = {
  summary: {
    total_records: number
    labels: Record<string, { records: number }>
  }
  readiness: {
    ready: boolean
    labels: Record<string, CalibrationLabelReadiness>
    next_labels: string[]
  }
  evaluation: {
    eligible: boolean
    accuracy?: number
  }
}

export type CalibrationCoachAdvice = {
  provider: string
  model: string
  primary_model: string
  fallback_used: boolean
  status: 'collect' | 'improve' | 'ready' | string
  headline: string
  evidence: string[]
  next_label: string
  next_action: string
  judge_caption: string
}

export type CalibrationCoachPayload = {
  generated_at: string
  report: CalibrationReport
  advice: CalibrationCoachAdvice
}

export function formatCoachAccuracy(report: CalibrationReport): string {
  if (!report.evaluation.eligible || typeof report.evaluation.accuracy !== 'number') {
    return 'not eligible'
  }
  return `${Math.round(report.evaluation.accuracy * 100)}% held-out`
}

export function formatCoachNextLabel(advice: CalibrationCoachAdvice): string {
  return advice.next_label === 'none' ? 'coverage complete' : `capture ${advice.next_label}`
}

export function labelReadiness(report: CalibrationReport, label: string): CalibrationLabelReadiness {
  return report.readiness.labels[label] ?? { records: 0, needed: 0, ready: false }
}

export function formatCoachModel(advice: CalibrationCoachAdvice): string {
  if (advice.provider === 'rules') {
    return 'local rules'
  }
  return advice.fallback_used ? `${advice.model} fallback` : advice.model
}
