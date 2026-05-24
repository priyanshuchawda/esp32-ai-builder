import { describe, expect, it } from 'vitest'
import { formatTelegramDelivery, type TelegramDeliveryPayload } from './telegramDelivery'

const sent: TelegramDeliveryPayload = {
  status: 'sent',
  event_signature: 'sig',
  message_id: 52,
  destination: '...4321',
  detail: 'Telegram accepted the prepared message.',
}

describe('telegram delivery display helpers', () => {
  it('shows the masked Telegram acknowledgment after delivery', () => {
    expect(formatTelegramDelivery(sent)).toBe('Sent #52 to ...4321')
  })

  it('shows backend detail when delivery is not confirmed', () => {
    expect(
      formatTelegramDelivery({
        ...sent,
        status: 'failed',
        message_id: null,
        detail: 'Telegram rejected the prepared message.',
      }),
    ).toBe('Telegram rejected the prepared message.')
    expect(
      formatTelegramDelivery({
        ...sent,
        status: 'not_configured',
        message_id: null,
        destination: null,
        detail: 'Telegram credentials are not configured.',
      }),
    ).toBe('Telegram credentials are not configured.')
  })
})
