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

type ScenarioSnapshot = {
  scenario: string
  telemetry: Telemetry
  quality: Quality
  summary: Summary
  fingerprint: Fingerprint
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

function App() {
  const [payload, setPayload] = useState<DemoPayload>(fallbackPayload)
  const [selectedScenario, setSelectedScenario] = useState('occupied_still')
  const [apiStatus, setApiStatus] = useState<'connecting' | 'online' | 'fallback'>('connecting')
  const [liveProbe, setLiveProbe] = useState<LiveProbePayload | null>(null)
  const [liveProbeStatus, setLiveProbeStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [liveProbeError, setLiveProbeError] = useState('')

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

  const selected = payload.selected
  const live = liveProbe?.snapshot ?? payload.live
  const selectedValues = useMemo(
    () => fingerprintValues(selected.fingerprint.bars),
    [selected.fingerprint.bars],
  )
  const liveValues = useMemo(() => fingerprintValues(live.fingerprint.bars), [live.fingerprint.bars])
  const wavePath = buildWavePath(selectedValues)

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
            <Metric icon={<AlertTriangle size={18} />} label="Source" value={(live.source ?? 'live').replaceAll('_', ' ')} />
          </div>
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
    </main>
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
