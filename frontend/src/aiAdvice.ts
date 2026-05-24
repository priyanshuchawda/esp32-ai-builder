import type { ObservatoryPayload } from './ObservatoryScene'

export type AiAdvice = {
  provider: string
  model: string
  primary_model: string
  fallback_used: boolean
  status: 'trusted' | 'weak' | 'blocked' | string
  room_interpretation: string
  why: string[]
  next_action: string
  judge_caption: string
  telegram_message: string
  confidence: number
}

export type AiAdvicePayload = {
  title: string
  generated_at: string
  source: string
  observatory: ObservatoryPayload
  advice: AiAdvice
}

export function buildFallbackAiAdvice(observatory: ObservatoryPayload): AiAdvice {
  const weakSignal = observatory.signal.quality !== 'GOOD' || observatory.visual.trust !== 'trusted'
  const emptyRoom = observatory.persons.range === '0' || observatory.visual.pose_state === 'none'
  const reasons = humanizeReasons([...observatory.visual.reasons, ...observatory.signal.reasons])

  if (weakSignal) {
    return {
      provider: 'rules',
      model: 'rules',
      primary_model: 'rules',
      fallback_used: false,
      status: observatory.visual.trust === 'blocked' ? 'blocked' : 'weak',
      room_interpretation: 'The ESP32 stream is visible, but this signal is not strong enough for a trusted room-state claim.',
      why: reasons.length > 0 ? reasons.slice(0, 3) : ['signal quality is not good'],
      next_action: 'Improve packet rate and RSSI stability, then run Live ESP again.',
      judge_caption: 'Gemma advice is blocked until RF quality is trusted.',
      telegram_message: 'CSI quality watch: signal weak, no trusted room-state claim.',
      confidence: 0.45,
    }
  }

  if (emptyRoom) {
    return {
      provider: 'rules',
      model: 'rules',
      primary_model: 'rules',
      fallback_used: false,
      status: 'trusted',
      room_interpretation: 'The current CSI summary matches an empty-room baseline.',
      why: reasons.length > 0 ? reasons.slice(0, 3) : ['trusted empty-room baseline'],
      next_action: 'Keep this run as a calibration reference.',
      judge_caption: 'Trusted RF baseline: no occupied zone detected.',
      telegram_message: 'Trusted CSI: room appears empty.',
      confidence: 1,
    }
  }

  return {
    provider: 'rules',
    model: 'rules',
    primary_model: 'rules',
    fallback_used: false,
    status: 'trusted',
    room_interpretation: `The CSI summary supports a ${observatory.visual.pose_state.replaceAll('_', ' ')} activity visualization.`,
    why: reasons.length > 0 ? reasons.slice(0, 3) : ['trusted CSI activity state'],
    next_action: 'Keep the ESP and router positions stable while collecting more labeled windows.',
    judge_caption: 'Trusted Wi-Fi CSI activity state rendered in Observatory mode.',
    telegram_message: `Trusted CSI: ${observatory.visual.pose_state.replaceAll('_', ' ')} candidate.`,
    confidence: 1,
  }
}

export function formatAdviceModel(advice: AiAdvice): string {
  if (advice.provider === 'rules') {
    return 'local rules'
  }
  return advice.fallback_used ? `${advice.model} fallback` : advice.model
}

function humanizeReasons(reasons: string[]): string[] {
  return Array.from(new Set(reasons.filter(Boolean).map((reason) => reason.replaceAll('_', ' '))))
}
