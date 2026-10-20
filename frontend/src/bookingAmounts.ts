import type { Booking } from './api'

const cents = (amount: string) => {
  if (!/^\d+\.\d{2}$/.test(amount)) throw new Error('Expected a nonnegative two-decimal amount')
  return BigInt(amount.replace('.', ''))
}

/** Settled cash flow, independent of the current journey price after replacements. */
export function netPaid(booking: Pick<Booking, 'payments' | 'refunds'>): string {
  const paid = booking.payments.reduce((sum, payment) =>
    payment.status === 'succeeded' ? sum + cents(payment.amount) : sum, 0n)
  const refunded = booking.refunds.reduce((sum, refund) =>
    refund.status === 'completed' ? sum + cents(refund.amount) : sum, 0n)
  const net = paid - refunded
  const absolute = net < 0n ? -net : net
  return `${net < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`
}
