export type TelegramDeliveryPayload = {
  status: 'sent' | 'failed' | 'not_configured' | string
  event_signature: string
  message_id: number | null
  destination: string | null
  detail: string
}

export function formatTelegramDelivery(delivery: TelegramDeliveryPayload): string {
  if (delivery.status === 'sent' && delivery.message_id !== null && delivery.destination) {
    return `Sent #${delivery.message_id} to ${delivery.destination}`
  }
  return delivery.detail
}
