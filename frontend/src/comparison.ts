import type { Itinerary } from './api'

type Comparable = Pick<Itinerary, 'total_price' | 'currency' | 'passengers' | 'duration_minutes' | 'arrives_at' | 'transfers' | 'min_transfer_buffer_minutes'>
const cents = (amount: string) => {
  if (!/^\d+\.\d{2}$/.test(amount)) throw new Error('Expected a nonnegative two-decimal price')
  return BigInt(amount.replace('.', ''))
}
const price = (value: bigint) => `${value / 100n}.${String(value % 100n).padStart(2, '0')}`

/** Facts relative to the first chosen option, not a reliability prediction or an AI recommendation. */
export function explainDifference(option: Comparable, baseline: Comparable): string[] {
  if (option.currency !== baseline.currency || option.passengers !== baseline.passengers) {
    return ['These options have different currencies or passenger counts; prices cannot be compared directly.']
  }
  const delta = cents(option.total_price) - cents(baseline.total_price)
  const facts = [delta === 0n ? 'The same total price.' : `${option.currency} ${price(delta < 0n ? -delta : delta)} ${delta < 0n ? 'cheaper' : 'more expensive'} in total.`]
  const minutes = option.duration_minutes - baseline.duration_minutes
  facts.push(minutes === 0 ? 'The same journey duration.' : `${Math.abs(minutes)} min ${minutes < 0 ? 'shorter' : 'longer'} journey.`)
  const arrival = Math.round((Date.parse(option.arrives_at) - Date.parse(baseline.arrives_at)) / 60000)
  facts.push(arrival === 0 ? 'Arrives at the same time.' : `Arrives ${Math.abs(arrival)} min ${arrival < 0 ? 'earlier' : 'later'}.`)
  const transfers = option.transfers - baseline.transfers
  facts.push(option.transfers === 0 ? 'Direct, with no changes.' : transfers === 0 ? 'The same number of transfers.' : `${Math.abs(transfers)} ${transfers < 0 ? 'fewer' : 'more'} transfer${Math.abs(transfers) === 1 ? '' : 's'}.`)
  if (option.min_transfer_buffer_minutes !== null && baseline.min_transfer_buffer_minutes !== null) {
    const buffer = option.min_transfer_buffer_minutes - baseline.min_transfer_buffer_minutes
    facts.push(buffer === 0 ? 'The same tightest connection buffer.' : `${Math.abs(buffer)} min ${buffer > 0 ? 'more' : 'less'} spare time at the tightest connection.`)
  }
  return facts
}
