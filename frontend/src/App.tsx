import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Gauge,
  HeartPulse,
  Radio,
  RefreshCw,
  Router,
  ShieldCheck,
  Signal,
  UserRound,
  Waves,
  Wifi,
  Zap,
} from 'lucide-react'
import './App.css'
import { ObservatoryScene, type ObservatoryPayload } from './ObservatoryScene'
import {
  buildFallbackAiAdvice,
  formatAdviceModel,
  type AiAdvice,
  type AiAdvicePayload,
} from './aiAdvice'

type Quality = {
  status: string
  fps: number
  reasons: string[]
}

type Telemetry = {
  presence: boolean
  resp_bpm: number
  heart_bpm: number
  fall_detected: boolean
  variance: number
  rep_count?: number
  acceleration?: number
  motion: {
    display_level: string
    score: number
    trusted: boolean
  }
  occupancy: {
    class: string
    trusted: boolean
    reasons?: string[]
  }
}

type Summary = {
  demo_state: string
  headline: string
  confidence: string
  capabilities: string[]
  next_action: string
}

type Fingerprint = {
  bins: number
  mean: number
  spread: number
  bars: string
}

type RoomState = {
  cluster_id: number
  label: string
  distance: number
  transitioned: boolean
  trusted: boolean
  anomaly_score: number
  timeline: string
}

type Spectrogram = {
  source: string
  time_bins: number
  subcarrier_bins: number
  rows: number[][]
  ascii: string
}

type MaterialChange = {
  baseline_ready: boolean
  trusted?: boolean
  trust_reason?: string
  samples: number
  change_detected: boolean
  event_type: string
  material_hint: string
  changed_bins: number
  new_nulls: number
  removed_nulls: number
  null_map: string
}

type MotionCadence = {
  state: string
  trusted: boolean
  cadence_spm: number
  dominant_frequency_hz: number
  regularity: number
  stride_regularity: number
  sample_count: number
  trust_reason: string
}

type PersonCount = {
  estimate: number
  range: string
  label: string
  confidence: string
  trusted: boolean
  reasons: string[]
}

type ScenarioSnapshot = {
  scenario: string
  telemetry: Telemetry
  quality: Quality
  summary: Summary
  fingerprint: Fingerprint
  room_state?: RoomState
  spectrogram?: Spectrogram
  material_change?: MaterialChange
  motion_cadence?: MotionCadence
  person_count?: PersonCount
  source?: string
  note?: string
}

type PipelineStep = {
  label: string
  detail: string
  state: string
}

type DemoPayload = {
  title: string
  generated_at: string
  selected: ScenarioSnapshot
  scenarios: ScenarioSnapshot[]
  live: ScenarioSnapshot
  pipeline: PipelineStep[]
  capabilities: string[]
}

type LiveProbePayload = {
  source: string
  duration_sec: number
  overall_status: string
  udp: {
    status: string
    reason: string
    packets: number
    fps: number
  }
  snapshot: ScenarioSnapshot
  next_actions: string[]
}

type AppView = 'dashboard' | 'observatory'
type ObservatoryMode = 'demo' | 'live'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

const scenarioLabels: Record<string, string> = {
  empty_room: 'Empty',
  occupied_still: 'Sitting',
  walking: 'Walking',
  fall_event: 'Fall',
  weak_live_stream: 'Weak stream',
}

const scenarioNotes: Record<string, string> = {
  empty_room: 'baseline',
  occupied_still: 'presence + vitals',
  walking: 'motion tracking',
  fall_event: 'safety alert',
  weak_live_stream: 'quality gate',
}

const fallbackPayload: DemoPayload = {
  title: 'ESP32 Wi-Fi CSI Spatial Intelligence',
  generated_at: new Date(0).toISOString(),
  selected: {
    scenario: 'occupied_still',
    telemetry: {
      presence: true,
      resp_bpm: 15.2,
      heart_bpm: 73.5,
      fall_detected: false,
      variance: 8.4,
      motion: { display_level: 'STILL', score: 0.11, trusted: true },
      occupancy: { class: 'OCCUPIED', trusted: true, reasons: [] },
    },
    quality: { status: 'GOOD', fps: 25, reasons: [] },
    summary: {
      demo_state: 'OCCUPIED_STILL',
      headline: 'Human presence visible through Wi-Fi CSI',
      confidence: 'high',
      capabilities: ['presence', 'breathing', 'heart_rate'],
      next_action: 'Keep room stable for cleaner calibration.',
    },
    fingerprint: { bins: 16, mean: 18.6, spread: 12, bars: '..:=+**+=--=*#*=' },
    motion_cadence: {
      state: 'stationary',
      trusted: true,
      cadence_spm: 0,
      dominant_frequency_hz: 0,
      regularity: 0,
      stride_regularity: 0,
      sample_count: 80,
      trust_reason: 'low_motion_energy',
    },
    person_count: {
      estimate: 1,
      range: '1',
      label: 'single occupied zone',
      confidence: 'high',
      trusted: true,
      reasons: ['single_link_estimate'],
    },
  },
  scenarios: [
    {
      scenario: 'empty_room',
      telemetry: {
        presence: false,
        resp_bpm: 0,
        heart_bpm: 0,
        fall_detected: false,
        variance: 1.1,
        motion: { display_level: 'STILL', score: 0.02, trusted: true },
        occupancy: { class: 'EMPTY', trusted: true, reasons: [] },
      },
      quality: { status: 'GOOD', fps: 25, reasons: [] },
      summary: {
        demo_state: 'EMPTY_ROOM',
        headline: 'Room baseline is quiet',
        confidence: 'high',
        capabilities: ['empty-room baseline'],
        next_action: 'Use this as calibration reference.',
      },
      fingerprint: { bins: 16, mean: 12.2, spread: 1, bars: '................' },
      motion_cadence: {
        state: 'stationary',
        trusted: true,
        cadence_spm: 0,
        dominant_frequency_hz: 0,
        regularity: 0,
        stride_regularity: 0,
        sample_count: 80,
        trust_reason: 'low_motion_energy',
      },
      person_count: {
        estimate: 0,
        range: '0',
        label: 'empty room',
        confidence: 'high',
        trusted: true,
        reasons: ['trusted_empty_baseline'],
      },
    },
    {
      scenario: 'occupied_still',
      telemetry: {
        presence: true,
        resp_bpm: 15.2,
        heart_bpm: 73.5,
        fall_detected: false,
        variance: 8.4,
        motion: { display_level: 'STILL', score: 0.11, trusted: true },
        occupancy: { class: 'OCCUPIED', trusted: true, reasons: [] },
      },
      quality: { status: 'GOOD', fps: 25, reasons: [] },
      summary: {
        demo_state: 'OCCUPIED_STILL',
        headline: 'Human presence visible through Wi-Fi CSI',
        confidence: 'high',
        capabilities: ['presence', 'breathing', 'heart_rate'],
        next_action: 'Keep room stable for cleaner calibration.',
      },
      fingerprint: { bins: 16, mean: 18.6, spread: 12, bars: '..:=+**+=--=*#*=' },
      motion_cadence: {
        state: 'stationary',
        trusted: true,
        cadence_spm: 0,
        dominant_frequency_hz: 0,
        regularity: 0,
        stride_regularity: 0,
        sample_count: 80,
        trust_reason: 'low_motion_energy',
      },
      person_count: {
        estimate: 1,
        range: '1',
        label: 'single occupied zone',
        confidence: 'high',
        trusted: true,
        reasons: ['single_link_estimate'],
      },
    },
  ],
  live: {
    scenario: 'weak_live_stream',
    source: 'simulated_fallback',
    note: 'Backend API is offline, so the dashboard is showing local fallback data.',
    telemetry: {
      presence: true,
      resp_bpm: 0,
      heart_bpm: 0,
      fall_detected: false,
      variance: 10,
      motion: { display_level: 'UNSTABLE', score: 2.2, trusted: false },
      occupancy: { class: 'UNKNOWN', trusted: false, reasons: ['signal_quality_weak_blocked'] },
    },
    quality: { status: 'WEAK', fps: 2.7, reasons: ['low_fps', 'rssi_unstable'] },
    summary: {
      demo_state: 'SIGNAL_WATCH',
      headline: 'Signal is visible but not trusted',
      confidence: 'low',
      capabilities: ['presence candidate', 'quality gate'],
      next_action: 'Improve stream FPS before trusting classification.',
    },
    fingerprint: { bins: 16, mean: 22.7, spread: 26, bars: '-#-#-#-#-#-#-#-#' },
    motion_cadence: {
      state: 'signal_watch',
      trusted: false,
      cadence_spm: 0,
      dominant_frequency_hz: 0,
      regularity: 0,
      stride_regularity: 0,
      sample_count: 0,
      trust_reason: 'signal_quality_not_good',
    },
    person_count: {
      estimate: 0,
      range: 'unknown',
      label: 'count blocked',
      confidence: 'low',
      trusted: false,
      reasons: ['signal_quality_not_good'],
    },
  },
  pipeline: [
    { label: 'ESP32 DevKit V1', detail: 'Captures Wi-Fi CSI amplitude changes.', state: 'hardware' },
    { label: 'CSI packet stream', detail: 'Filters unstable packets and FPS drops.', state: 'signal' },
    { label: 'RuView DSP filters', detail: 'Summarizes room state from CSI shape.', state: 'analysis' },
    { label: 'Gemma advisor', detail: 'Adds explainable recommendations when configured.', state: 'ai' },
    { label: 'Telegram + dashboard', detail: 'Shows room status and alerts humans.', state: 'output' },
  ],
  capabilities: ['presence', 'motion', 'vitals', 'fall simulation', 'fingerprint', 'Telegram alert'],
}

function labelForScenario(scenario: string) {
  return scenarioLabels[scenario] ?? scenario.replaceAll('_', ' ')
}

function formatNumber(value: number, digits = 1) {
  return Number.isFinite(value) ? value.toFixed(digits) : '--'
}

function statusClass(status: string) {
  return status.toLowerCase().replaceAll('_', '-')
}

function fingerprintValues(bars: string) {
  const alphabet = '._:-=+*#'
  return Array.from(bars).map((char) => {
    const index = Math.max(0, alphabet.indexOf(char))
    return Math.round(((index + 1) / alphabet.length) * 100)
  })
}

function buildWavePath(values: number[]) {
  if (values.length === 0) {
    return ''
  }
  const width = 360
  const height = 120
  const step = width / Math.max(1, values.length - 1)
  return values
    .map((value, index) => {
      const x = Math.round(index * step)
      const y = Math.round(height - (value / 100) * 92 - 14)
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
}

function buildFallbackObservatory(snapshot: ScenarioSnapshot, source: string): ObservatoryPayload {
  const qualityGood = snapshot.quality.status === 'GOOD'
  const occupied = snapshot.telemetry.occupancy.class === 'OCCUPIED'
  const blocked = !qualityGood || !snapshot.telemetry.occupancy.trusted
  const poseState = !qualityGood ? 'unknown' : !occupied ? 'none' : snapshot.telemetry.fall_detected ? 'fallen' : 'sitting'

  return {
    source,
    truth_label: 'visualization_only_not_densepose',
    visual: {
      pose_state: poseState,
      avatar: poseState === 'none' ? 'none' : blocked ? 'transparent' : poseState,
      trust: blocked ? 'weak' : 'trusted',
      opacity: blocked ? 0.28 : poseState === 'none' ? 0 : 0.86,
      claim: 'CSI-inferred activity visualization',
      reasons: blocked ? ['signal_quality_not_good'] : ['local_dashboard_fallback'],
    },
    persons: snapshot.person_count ?? {
      range: 'unknown',
      label: 'count unavailable',
      trusted: false,
    },
    signal: {
      quality: snapshot.quality.status,
      fps: snapshot.quality.fps,
      packets: 0,
      reasons: snapshot.quality.reasons,
    },
    vitals: {
      resp_bpm: snapshot.telemetry.resp_bpm,
      heart_bpm: snapshot.telemetry.heart_bpm,
      available: Boolean(snapshot.telemetry.resp_bpm || snapshot.telemetry.heart_bpm),
    },
    motion: {
      display_level: snapshot.telemetry.motion.display_level,
      state: snapshot.motion_cadence?.state ?? 'unknown',
      cadence_spm: snapshot.motion_cadence?.cadence_spm ?? 0,
      trusted: Boolean(snapshot.motion_cadence?.trusted),
    },
  }
}

function App() {
  const [payload, setPayload] = useState<DemoPayload>(fallbackPayload)
  const [selectedScenario, setSelectedScenario] = useState('occupied_still')
  const [activeView, setActiveView] = useState<AppView>('dashboard')
  const [apiStatus, setApiStatus] = useState<'connecting' | 'online' | 'fallback'>('connecting')
  const [liveProbe, setLiveProbe] = useState<LiveProbePayload | null>(null)
  const [liveProbeStatus, setLiveProbeStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [liveProbeError, setLiveProbeError] = useState('')
  const [observatoryMode, setObservatoryMode] = useState<ObservatoryMode>('demo')
  const [observatoryPayload, setObservatoryPayload] = useState<ObservatoryPayload | null>(null)
  const [observatoryStatus, setObservatoryStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [observatoryError, setObservatoryError] = useState('')
  const [aiAdvice, setAiAdvice] = useState<AiAdvice | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    fetch(`${API_BASE}/api/judge-demo?scenario=${selectedScenario}`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`)
        }
        return response.json() as Promise<DemoPayload>
      })
      .then((data) => {
        setPayload(data)
        setApiStatus('online')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setPayload((current) => ({ ...current, selected: fallbackPayload.selected }))
        setApiStatus('fallback')
      })

    return () => controller.abort()
  }, [selectedScenario])

  useEffect(() => {
    if (activeView !== 'observatory' || observatoryMode !== 'demo') {
      return
    }

    const controller = new AbortController()

    fetch(`${API_BASE}/api/ai-advice?mode=demo&scenario=${selectedScenario}`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`AI advice returned ${response.status}`)
        }
        return response.json() as Promise<AiAdvicePayload>
      })
      .then((data) => {
        setObservatoryPayload(data.observatory)
        setAiAdvice(data.advice)
        setObservatoryStatus('done')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        const fallbackObservatory = buildFallbackObservatory(payload.selected, 'local_fallback')
        setObservatoryPayload(fallbackObservatory)
        setAiAdvice(buildFallbackAiAdvice(fallbackObservatory))
        setObservatoryError(error instanceof Error ? error.message : 'Observatory demo failed')
        setObservatoryStatus('error')
      })

    return () => controller.abort()
  }, [activeView, observatoryMode, payload.selected, selectedScenario])

  function runLiveProbe() {
    setLiveProbeStatus('running')
    setLiveProbeError('')
    fetch(`${API_BASE}/api/judge-live?duration=5&udp_port=5005`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Live probe returned ${response.status}`)
        }
        return response.json() as Promise<LiveProbePayload>
      })
      .then((data) => {
        setLiveProbe(data)
        setLiveProbeStatus('done')
      })
      .catch((error: unknown) => {
        setLiveProbeError(error instanceof Error ? error.message : 'Live probe failed')
        setLiveProbeStatus('error')
      })
  }

  function runObservatoryLiveProbe() {
    setActiveView('observatory')
    setObservatoryMode('live')
    setObservatoryStatus('running')
    setObservatoryError('')
    setAiAdvice(null)
    fetch(`${API_BASE}/api/ai-advice?mode=live&duration=3&udp_port=5005`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`AI advice live returned ${response.status}`)
        }
        return response.json() as Promise<AiAdvicePayload>
      })
      .then((data) => {
        setObservatoryPayload(data.observatory)
        setAiAdvice(data.advice)
        setObservatoryStatus('done')
      })
      .catch((error: unknown) => {
        const fallbackObservatory = buildFallbackObservatory(liveProbe?.snapshot ?? payload.live, 'local_fallback')
        setObservatoryPayload(fallbackObservatory)
        setAiAdvice(buildFallbackAiAdvice(fallbackObservatory))
        setObservatoryError(error instanceof Error ? error.message : 'Observatory live failed')
        setObservatoryStatus('error')
      })
  }

  const selected = payload.selected
  const live = liveProbe?.snapshot ?? payload.live
  const roomState = selected.room_state
  const liveRoomState = live.room_state
  const materialChange = selected.material_change
  const liveMaterialChange = live.material_change
  const motionCadence = selected.motion_cadence
  const liveMotionCadence = live.motion_cadence
  const personCount = selected.person_count
  const livePersonCount = live.person_count
  const selectedValues = useMemo(
    () => fingerprintValues(selected.fingerprint.bars),
    [selected.fingerprint.bars],
  )
  const liveValues = useMemo(() => fingerprintValues(live.fingerprint.bars), [live.fingerprint.bars])
  const wavePath = buildWavePath(selectedValues)
  const observatory = observatoryPayload ?? buildFallbackObservatory(selected, 'local_fallback')
  const advice = aiAdvice ?? buildFallbackAiAdvice(observatory)

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">ESP32 DevKit V1 / COM5 ready pipeline</p>
          <h1>{payload.title}</h1>
        </div>
        <div className="status-strip" aria-label="system status">
          <span className={`status-pill ${apiStatus}`}>
            {apiStatus === 'online' ? <CheckCircle2 size={16} /> : <RefreshCw size={16} />}
            API {apiStatus}
          </span>
          <span className={`status-pill quality-${statusClass(live.quality.status)}`}>
            <Wifi size={16} />
            {live.quality.status} stream
          </span>
          <a className="icon-link" href="http://localhost:8501" target="_blank" rel="noreferrer">
            <Gauge size={17} />
            Streamlit
          </a>
        </div>
      </header>

      <nav className="view-switcher" aria-label="dashboard views">
        <button
          className={activeView === 'dashboard' ? 'active' : ''}
          onClick={() => setActiveView('dashboard')}
          type="button"
        >
          <BarChart3 size={17} />
          Dashboard
        </button>
        <button
          className={activeView === 'observatory' ? 'active' : ''}
          onClick={() => {
            setActiveView('observatory')
            setObservatoryMode('demo')
            setObservatoryStatus('running')
            setObservatoryError('')
            setAiAdvice(null)
          }}
          type="button"
        >
          <Radio size={17} />
          Observatory
        </button>
      </nav>

      {activeView === 'observatory' ? (
        <ObservatoryExperience
          error={observatoryError}
          mode={observatoryMode}
          onDemo={() => {
            setObservatoryMode('demo')
            setObservatoryPayload(null)
            setObservatoryStatus('running')
            setObservatoryError('')
            setAiAdvice(null)
          }}
          onLive={runObservatoryLiveProbe}
          payload={observatory}
          advice={advice}
          status={observatoryStatus}
        />
      ) : (
        <>
      <section className="scenario-rail" aria-label="scenario controls">
        {payload.scenarios.map((scenario) => (
          <button
            className={`scenario-button ${scenario.scenario === selected.scenario ? 'active' : ''}`}
            key={scenario.scenario}
            onClick={() => setSelectedScenario(scenario.scenario)}
            type="button"
          >
            <span className={`scenario-dot quality-${statusClass(scenario.quality.status)}`} />
            <span>
              <strong>{labelForScenario(scenario.scenario)}</strong>
              <small>{scenarioNotes[scenario.scenario] ?? scenario.summary.demo_state}</small>
            </span>
          </button>
        ))}
      </section>

      <section className="dashboard-grid">
        <article className="panel command-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Selected room state</p>
              <h2>{selected.summary.demo_state}</h2>
            </div>
            <span className={`state-chip quality-${statusClass(selected.quality.status)}`}>
              {selected.quality.status}
            </span>
          </div>
          <p className="headline">{selected.summary.headline}</p>
          {roomState ? (
            <div className="room-state-strip">
              <span>
                <strong>{roomState.label}</strong>
                cluster {roomState.cluster_id}
              </span>
              <span>
                <strong>{formatNumber(roomState.anomaly_score, 2)}</strong>
                anomaly
              </span>
              <code>{roomState.timeline || String(roomState.cluster_id)}</code>
            </div>
          ) : null}
          {materialChange ? <MaterialChangeStrip materialChange={materialChange} /> : null}
          {motionCadence ? <MotionCadenceStrip motionCadence={motionCadence} /> : null}
          {personCount ? <PersonCountStrip personCount={personCount} /> : null}
          <div className="metric-grid">
            <Metric icon={<UserRound size={18} />} label="Occupancy" value={selected.telemetry.occupancy.class} />
            <Metric icon={<Activity size={18} />} label="Motion" value={selected.telemetry.motion.display_level} />
            <Metric icon={<HeartPulse size={18} />} label="Heart" value={`${formatNumber(selected.telemetry.heart_bpm)} bpm`} />
            <Metric icon={<Waves size={18} />} label="Breath" value={`${formatNumber(selected.telemetry.resp_bpm)} bpm`} />
          </div>
          <div className="capability-row">
            {selected.summary.capabilities.map((capability) => (
              <span key={capability}>{capability.replaceAll('_', ' ')}</span>
            ))}
          </div>
        </article>

        <article className="panel fingerprint-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CSI fingerprint</p>
              <h2>{selected.fingerprint.bins} spatial bins</h2>
            </div>
            <Radio size={22} />
          </div>
          <svg className="waveform" viewBox="0 0 360 120" role="img" aria-label="CSI fingerprint waveform">
            <path d="M 0 106 L 360 106" className="wave-baseline" />
            <path d={wavePath} className="wave-path" />
          </svg>
          <div className="bars" aria-label="CSI amplitude bins">
            {selectedValues.map((value, index) => (
              <span key={`${selected.scenario}-${index}`} style={{ height: `${Math.max(12, value)}%` }} />
            ))}
          </div>
          <code className="fingerprint-code">{selected.fingerprint.bars}</code>
          <div className="summary-row">
            <span>mean {formatNumber(selected.fingerprint.mean)}</span>
            <span>spread {formatNumber(selected.fingerprint.spread)}</span>
            <span>variance {formatNumber(selected.telemetry.variance)}</span>
          </div>
          {selected.spectrogram ? <SpectrogramHeatmap spectrogram={selected.spectrogram} /> : null}
        </article>

        <article className="panel live-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">{liveProbe ? 'Actual live probe' : 'Live readiness'}</p>
              <h2>{live.summary.demo_state}</h2>
            </div>
            <button
              className="probe-button"
              disabled={liveProbeStatus === 'running'}
              onClick={runLiveProbe}
              type="button"
            >
              {liveProbeStatus === 'running' ? <RefreshCw size={16} /> : <Signal size={16} />}
              {liveProbeStatus === 'running' ? 'Running' : 'Live probe'}
            </button>
          </div>
          <div className="live-meter">
            {liveValues.map((value, index) => (
              <span key={`live-${index}`} style={{ height: `${Math.max(10, value)}%` }} />
            ))}
          </div>
          <div className="metric-grid compact">
            <Metric icon={<Gauge size={18} />} label="FPS" value={formatNumber(live.quality.fps)} />
            <Metric icon={<ShieldCheck size={18} />} label="Trust" value={live.telemetry.occupancy.trusted ? 'trusted' : 'blocked'} />
            <Metric icon={<Zap size={18} />} label="Packets" value={liveProbe ? String(liveProbe.udp.packets) : '--'} />
            <Metric
              icon={<AlertTriangle size={18} />}
              label="Material"
              value={
                liveMaterialChange?.baseline_ready
                  ? liveMaterialChange.trusted === false
                    ? 'untrusted signal'
                    : liveMaterialChange.material_hint
                  : liveRoomState?.label ?? (live.source ?? 'live').replaceAll('_', ' ')
              }
            />
            <Metric
              icon={<AlertTriangle size={18} />}
              label="Fall"
              value={live.telemetry.fall_detected ? 'alert' : 'clear'}
            />
            <Metric icon={<Activity size={18} />} label="Reps" value={String(live.telemetry.rep_count ?? 0)} />
          </div>
          {liveMotionCadence ? <MotionCadenceStrip motionCadence={liveMotionCadence} compact /> : null}
          {livePersonCount ? <PersonCountStrip personCount={livePersonCount} compact /> : null}
          <p className={`muted ${liveProbeStatus === 'error' ? 'error' : ''}`}>
            {liveProbeStatus === 'error'
              ? liveProbeError
              : liveProbe?.next_actions[0] ?? live.note ?? live.summary.next_action}
          </p>
        </article>

        <article className="panel pipeline-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Processing flow</p>
              <h2>From Wi-Fi CSI to alert</h2>
            </div>
            <Router size={22} />
          </div>
          <div className="pipeline">
            {payload.pipeline.map((step, index) => (
              <div className="pipeline-step" key={step.label}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <strong>{step.label}</strong>
                  <small>{step.detail}</small>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel capability-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Enabled outputs</p>
              <h2>Current capability set</h2>
            </div>
            <BarChart3 size={22} />
          </div>
          <div className="capability-grid">
            {payload.capabilities.map((capability) => (
              <span key={capability}>
                <CheckCircle2 size={16} />
                {capability}
              </span>
            ))}
          </div>
        </article>
      </section>
        </>
      )}
    </main>
  )
}

function ObservatoryExperience({
  advice,
  error,
  mode,
  onDemo,
  onLive,
  payload,
  status,
}: {
  advice: AiAdvice
  error: string
  mode: ObservatoryMode
  onDemo: () => void
  onLive: () => void
  payload: ObservatoryPayload
  status: 'idle' | 'running' | 'done' | 'error'
}) {
  const reasons = payload.visual.reasons.length > 0 ? payload.visual.reasons : payload.signal.reasons
  const statusText = status === 'running' ? 'refreshing' : status === 'error' ? error : payload.visual.claim

  return (
    <section className="observatory-layout" aria-label="CSI observatory mode">
      <div className="observatory-stage">
        <ObservatoryScene payload={payload} />
        <div className="observatory-brand">
          <strong>ESP32 Observatory</strong>
          <span>{payload.truth_label.replaceAll('_', ' ')}</span>
        </div>
        <div className="observatory-mode">
          <button className={mode === 'demo' ? 'active' : ''} onClick={onDemo} type="button">
            Demo
          </button>
          <button className={mode === 'live' ? 'active' : ''} disabled={status === 'running'} onClick={onLive} type="button">
            {status === 'running' ? 'Live...' : 'Live ESP'}
          </button>
        </div>
        <div className="observatory-caption">
          <strong>{payload.visual.pose_state.replaceAll('_', ' ')}</strong>
          <span>{statusText}</span>
        </div>
      </div>

      <aside className="observatory-hud" aria-label="observatory signal summary">
        <div className={`hud-block ai-advice-card advice-${statusClass(advice.status)}`}>
          <div className="hud-heading-row">
            <p className="eyebrow">Gemma advice</p>
            <span>{formatAdviceModel(advice)}</span>
          </div>
          <strong>{advice.judge_caption}</strong>
          <p>{advice.room_interpretation}</p>
          <div className="reason-list">
            {advice.why.map((reason) => (
              <span key={reason}>{reason}</span>
            ))}
          </div>
          <div className="advice-next">
            <span>Next</span>
            <strong>{advice.next_action}</strong>
          </div>
          <div className="telegram-copy">
            <span>Telegram</span>
            <code>{advice.telegram_message}</code>
          </div>
        </div>

        <div className="hud-block">
          <p className="eyebrow">Wi-Fi signal</p>
          <div className="hud-grid">
            <Metric icon={<Wifi size={18} />} label="Quality" value={payload.signal.quality} />
            <Metric icon={<Gauge size={18} />} label="FPS" value={formatNumber(payload.signal.fps)} />
            <Metric icon={<Zap size={18} />} label="Packets" value={String(payload.signal.packets)} />
            <Metric icon={<ShieldCheck size={18} />} label="Trust" value={payload.visual.trust} />
          </div>
        </div>

        <div className="hud-block">
          <p className="eyebrow">Presence</p>
          <div className={`presence-banner ${payload.persons.trusted ? 'trusted' : ''}`}>
            <strong>{payload.persons.range}</strong>
            <span>{payload.persons.label}</span>
          </div>
        </div>

        <div className="hud-block">
          <p className="eyebrow">Vitals</p>
          <div className="hud-grid">
            <Metric icon={<HeartPulse size={18} />} label="Heart" value={`${formatNumber(payload.vitals.heart_bpm)} bpm`} />
            <Metric icon={<Waves size={18} />} label="Breath" value={`${formatNumber(payload.vitals.resp_bpm)} bpm`} />
            <Metric icon={<Activity size={18} />} label="Motion" value={payload.motion.display_level} />
            <Metric icon={<Signal size={18} />} label="Cadence" value={`${formatNumber(payload.motion.cadence_spm, 0)} spm`} />
          </div>
        </div>

        <div className="hud-block">
          <p className="eyebrow">Gate reasons</p>
          <div className="reason-list">
            {reasons.map((reason) => (
              <span key={reason}>{reason.replaceAll('_', ' ')}</span>
            ))}
          </div>
        </div>
      </aside>
    </section>
  )
}

function PersonCountStrip({ personCount, compact = false }: { personCount: PersonCount; compact?: boolean }) {
  const detail = personCount.trusted ? personCount.confidence : personCount.reasons[0]?.replaceAll('_', ' ')

  return (
    <div className={`count-strip ${personCount.trusted ? 'trusted' : ''} ${compact ? 'compact' : ''}`}>
      <span>
        <strong>{personCount.range}</strong>
        single-link count
      </span>
      <span>
        <strong>{personCount.label}</strong>
        {detail}
      </span>
      <code>{personCount.confidence}</code>
    </div>
  )
}

function MotionCadenceStrip({
  motionCadence,
  compact = false,
}: {
  motionCadence: MotionCadence
  compact?: boolean
}) {
  const cadence =
    motionCadence.cadence_spm > 0 ? `${formatNumber(motionCadence.cadence_spm, 0)} spm` : 'no cadence'
  const confidence = motionCadence.trusted ? 'trusted rhythm' : motionCadence.trust_reason.replaceAll('_', ' ')

  return (
    <div className={`cadence-strip ${motionCadence.trusted ? 'trusted' : ''} ${compact ? 'compact' : ''}`}>
      <span>
        <strong>{motionCadence.state.replaceAll('_', ' ')}</strong>
        {confidence}
      </span>
      <span>
        <strong>{cadence}</strong>
        {formatNumber(motionCadence.dominant_frequency_hz, 2)} Hz
      </span>
      <code>r {formatNumber(motionCadence.regularity, 2)}</code>
    </div>
  )
}

function MaterialChangeStrip({ materialChange }: { materialChange: MaterialChange }) {
  const label = !materialChange.baseline_ready
    ? 'learning'
    : materialChange.change_detected
      ? materialChange.event_type
      : 'stable'
  const detail = materialChange.trusted === false ? 'untrusted signal' : materialChange.material_hint

  return (
    <div className={`material-strip ${materialChange.change_detected ? 'changed' : ''}`}>
      <span>
        <strong>{label}</strong>
        {detail}
      </span>
      <span>
        <strong>{materialChange.changed_bins}</strong>
        bins changed
      </span>
      <code>{materialChange.null_map}</code>
    </div>
  )
}

function SpectrogramHeatmap({ spectrogram }: { spectrogram: Spectrogram }) {
  return (
    <div className="spectrogram">
      <div className="spectrogram-heading">
        <span>CSI spectrogram</span>
        <small>
          {spectrogram.time_bins} x {spectrogram.subcarrier_bins}
        </small>
      </div>
      <div
        className="heatmap"
        style={{
          gridTemplateColumns: `repeat(${Math.max(1, spectrogram.subcarrier_bins)}, minmax(0, 1fr))`,
        }}
      >
        {spectrogram.rows.flatMap((row, rowIndex) =>
          row.map((value, columnIndex) => (
            <span
              aria-label={`heat ${value}`}
              key={`${rowIndex}-${columnIndex}`}
              style={{ backgroundColor: `hsl(${190 - value * 1.15} 82% ${22 + value * 0.36}%)` }}
            />
          )),
        )}
      </div>
    </div>
  )
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export default App
