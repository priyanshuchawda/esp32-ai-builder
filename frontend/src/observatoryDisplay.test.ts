import { describe, expect, it } from 'vitest'
import { formatPersonRange, formatVitalValue } from './observatoryDisplay'

describe('Observatory judge-facing measurement display', () => {
  it('labels single-link person count as a candidate when it is not trusted', () => {
    expect(
      formatPersonRange({
        range: '2?',
        label: 'multi-zone candidate',
        trusted: false,
      }),
    ).toBe('2? candidate')
  })

  it('suppresses motion-blocked vital estimates', () => {
    expect(
      formatVitalValue(
        {
          available: false,
          trusted: false,
          label: 'motion blocks estimate',
        },
        61.2,
      ),
    ).toBe('--')
  })

  it('marks permitted experimental vital values as estimates', () => {
    expect(
      formatVitalValue(
        {
          available: true,
          trusted: false,
          label: 'experimental estimate',
        },
        15.2,
      ),
    ).toBe('15.2 est.')
  })

  it('does not render a missing individual metric as a zero estimate', () => {
    expect(
      formatVitalValue(
        {
          available: true,
          trusted: false,
          label: 'experimental estimate',
        },
        0,
      ),
    ).toBe('--')
  })
})
