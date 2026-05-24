type PersonDisplay = {
  range: string
  label: string
  trusted: boolean
}

type VitalDisplay = {
  available: boolean
  trusted: boolean
  label: string
}

export function formatPersonRange(persons: PersonDisplay): string {
  if (persons.trusted || persons.range === 'unknown') {
    return persons.range
  }
  return `${persons.range} candidate`
}

export function formatVitalValue(vitals: VitalDisplay, value: number): string {
  if (!vitals.available || value <= 0) {
    return '--'
  }
  return vitals.trusted ? `${value.toFixed(1)} bpm` : `${value.toFixed(1)} est.`
}
