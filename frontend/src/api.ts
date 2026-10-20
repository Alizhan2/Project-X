export interface Health {
  status: 'ok' | 'error'
  database: string
  database_version?: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch('/api/health/', { signal })
  // 503 still carries a JSON body describing the failure.
  return (await res.json()) as Health
}

export interface Stop {
  code: string
  name: string
  kind: string
  hub: string | null
  step_free: boolean | null
}

export type Tri = 'yes' | 'no' | 'unknown'

export interface SelectionItem {
  departure_id?: number; taxi_offer_id?: number; ready_at?: string; from_stop: string; to_stop: string
}

export interface Leg {
  kind: 'service' | 'taxi'
  departure_id: number | null
  taxi_offer_id: number | null
  mode: string
  operator: string
  route_code: string
  route_name: string
  from: { code: string; name: string }
  to: { code: string; name: string }
  departs_at: string
  arrives_at: string
  status: 'scheduled' | 'delayed' | 'cancelled'
  delay_minutes: number
  unit_price: string
  price_basis: 'passenger' | 'vehicle'
  leg_total: string
  places_left: number | null
  accessibility: { wheelchair_vehicle: Tri; origin_step_free: Tri; destination_step_free: Tri }
  cancellation_policy: string
}

export interface Itinerary {
  departs_at: string
  arrives_at: string
  duration_minutes: number
  transfers: number
  min_transfer_buffer_minutes: number | null
  transfer_buffers: number[]
  legs_param: string
  selection: SelectionItem[]
  passengers: number
  total_price: string
  currency: string
  legs: Leg[]
}

export interface SearchResponse {
  simulated: boolean
  window_hours: number
  count: number
  results: Itinerary[]
}

export class ApiError extends Error {
  fields: Record<string, string>
  status: number
  code?: string
  data: Record<string, unknown>
  constructor(message: string, opts: { fields?: Record<string, string>; status?: number; code?: string; data?: Record<string, unknown> } = {}) {
    super(message)
    this.fields = opts.fields ?? {}
    this.status = opts.status ?? 0
    this.code = opts.code
    this.data = opts.data ?? {}
  }
}

const csrfToken = () => document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] ?? ''

export async function ensureCsrf() {
  if (!csrfToken()) await fetch('/api/auth/csrf/', { credentials: 'same-origin' })
}

export async function request<T>(
  method: string, url: string, body?: unknown, opts: { signal?: AbortSignal; idempotencyKey?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (method !== 'GET') {
    await ensureCsrf()
    headers['X-CSRFToken'] = csrfToken() // re-read every time: login/register rotate the token
    headers['Content-Type'] = 'application/json'
  }
  if (opts.idempotencyKey) headers['Idempotency-Key'] = opts.idempotencyKey
  let res: Response
  try {
    res = await fetch(url, {
      method, headers, signal: opts.signal, credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (e) {
    if (opts.signal?.aborted) throw e
    throw new ApiError('Could not reach the server. Check your connection and try again.')
  }
  if (res.status === 204) return undefined as T
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (res.ok) return data as T
  if (res.status === 400) {
    const fields = Object.fromEntries(
      Object.entries(data).map(([k, v]) => [k, Array.isArray(v) ? v.join(' ') : String(v)]),
    )
    throw new ApiError('Please check the highlighted fields.', { fields, status: 400 })
  }
  if (res.status === 401 || res.status === 403) throw new ApiError('Please sign in to continue.', { status: res.status, code: 'auth' })
  if (res.status === 409) {
    throw new ApiError(String(data.message ?? 'This action conflicts with the current state.'), { status: 409, code: String(data.code ?? ''), data })
  }
  if (res.status === 404) throw new ApiError('Not found.', { status: 404 })
  throw new ApiError(`The server returned an error (${res.status}). Please try again.`, { status: res.status })
}

const getJson = <T,>(url: string, signal?: AbortSignal) => request<T>('GET', url, undefined, { signal })

export const fetchStops = (signal?: AbortSignal) => getJson<Stop[]>('/api/stops/', signal)

export interface SearchParams {
  origin: string
  destination: string
  depart_after: string
  passengers: string
  sort: string
}

export const searchJourneys = (p: SearchParams, signal?: AbortSignal) =>
  getJson<SearchResponse>(`/api/search/?${new URLSearchParams({ ...p })}`, signal)

export interface User { email_verified: boolean; id: number; email: string; name: string; role: string; operator: string | null }
export const fetchMe = (signal?: AbortSignal) => getJson<{ user: User | null }>('/api/auth/me/', signal)
export const login = (email: string, password: string) => request<User>('POST', '/api/auth/login/', { email, password })
export const register = (email: string, full_name: string, password: string) =>
  request<User>('POST', '/api/auth/register/', { email, full_name, password })
export const logout = () => request<void>('POST', '/api/auth/logout/')

export const fetchItinerary = (legs: string, passengers: string, signal?: AbortSignal) =>
  getJson<Itinerary & { simulated: boolean }>(`/api/itinerary/?${new URLSearchParams({ legs, passengers })}`, signal)

export interface BookingLeg {
  sequence: number; status: string; mode: string; operator: string; route_code: string; route_name: string
  from: string; to: string; departs_at: string; arrives_at: string; unit_price: string; price_basis: string; cancellation_policy: string
}
export interface Booking {
  reference: string; status: 'pending_payment' | 'confirmed' | 'cancelled' | 'expired'; status_label: string
  passengers: number; total_amount: string; currency: string; contact_email: string
  expires_at: string; created_at: string; confirmed_at: string | null; simulated_notice: string
  travellers: string[]; legs: BookingLeg[]
  disruption: Disruption | null; cancellable: boolean
  refunds: { status: string; amount: string; reason: string; created_at: string }[]
  payments: { status: string; purpose: string; amount: string; failure_reason: string; created_at: string }[]
}
export interface CheckoutBody {
  passengers: number; legs: SelectionItem[]
  expected_total?: string; contact_email: string; travellers: string[]
}
export const createBooking = (body: CheckoutBody, key: string) =>
  request<Booking>('POST', '/api/bookings/', body, { idempotencyKey: key })
export const fetchBooking = (ref: string, signal?: AbortSignal) => getJson<Booking>(`/api/bookings/${ref}/`, signal)
export const fetchBookings = (signal?: AbortSignal) => getJson<{ results: Booking[] }>('/api/bookings/', signal)
export const payBooking = (ref: string, outcome: 'success' | 'failure', key: string) =>
  request<{ replayed: boolean; payment: { status: string; failure_reason: string }; booking: Booking }>(
    'POST', `/api/bookings/${ref}/pay/`, { outcome }, { idempotencyKey: key })
export const abandonBooking = (ref: string) => request<Booking>('POST', `/api/bookings/${ref}/abandon/`)

// ---- Stage 5: cancellation, notifications, operator ----
export interface Disruption { status: 'ok' | 'delayed' | 'broken'; reason: string; problem_sequence: number | null; arrival_delay_minutes: number }
export interface CancellationQuote {
  disrupted: boolean; total_refund: string
  lines: { sequence: number; route_code: string; paid: string; percent: number; refund: string; reason: string }[]
}
export const fetchQuote = (ref: string) => getJson<CancellationQuote>(`/api/bookings/${ref}/cancellation/`)
export const cancelBooking = (ref: string, expected_refund?: string) =>
  request<Booking>('POST', `/api/bookings/${ref}/cancel/`, expected_refund ? { expected_refund } : {})

export interface AppNotification { id: number; kind: string; title: string; body: string; booking: string | null; created_at: string; read: boolean }
export const fetchNotifications = (signal?: AbortSignal) =>
  getJson<{ unread: number; results: AppNotification[] }>('/api/notifications/', signal)
export const markRead = (id: number) => request<void>('POST', `/api/notifications/${id}/read/`)
export const markAllRead = () => request<void>('POST', '/api/notifications/read-all/')

export interface OpService {
  id: number; route_code: string; route_name: string; mode: string; departs_at: string; ends_at: string
  status: 'scheduled' | 'delayed' | 'cancelled'; delay_minutes: number; capacity: number; places_taken: number
  wheelchair_accessible: boolean | null; first_stop: string; last_stop: string
  events?: { kind: string; delay_minutes: number; affected_bookings: number; created_at: string }[]
}
export interface OpRoute { id: number; code: string; name: string; mode: string; fares: { id: number; from: string; to: string; price: string; currency: string }[] }
export interface Impact {
  affected: { reference: string; passengers: number; booking_status: string; before: string; after: string; reason: string; arrival_delay_minutes: number }[]
  passengers: number; broken: number
}
export const opRoutes = () => getJson<{ operator: string; results: OpRoute[] }>('/api/operator/routes/')
export const opServices = (from?: string) => getJson<{ results: OpService[] }>(`/api/operator/services/${from ? `?from=${from}` : ''}`)
export const opService = (id: string) => getJson<OpService>(`/api/operator/services/${id}/`)
export const opCreate = (b: { route_id: number; departs_at: string; capacity: number; wheelchair_accessible: boolean | null }) =>
  request<OpService>('POST', '/api/operator/services/', b)
export const opEdit = (id: number, b: Partial<{ capacity: number; wheelchair_accessible: boolean | null }>) =>
  request<OpService>('PATCH', `/api/operator/services/${id}/`, b)
export const opFare = (id: number, price: string) => request<{ price: string }>('PATCH', `/api/operator/fares/${id}/`, { price })
export const opImpact = (id: number, action: 'delay' | 'cancel', minutes: number) =>
  request<Impact>('POST', `/api/operator/services/${id}/impact/`, { action, minutes })
export const opChange = (id: number, action: 'delay' | 'cancel', minutes: number) =>
  request<{ noop: boolean; affected_bookings: number; service: OpService }>('POST', `/api/operator/services/${id}/change/`, { action, minutes })

// ---- Stage 6: disruption recovery ----
export interface OfferLeg {
  mode: string; route_code: string; operator: string; from: { name: string }; to: { name: string }
  departs_at: string; arrives_at: string; status: string; delay_minutes: number
  unit_price: string; price_basis: string; places_left: number | null
  accessibility: { wheelchair_vehicle: Tri; origin_step_free: Tri; destination_step_free: Tri }
}
export interface ReplacementOffer {
  id: number; status: string; expires_at: string; arrives_at: string; legs: OfferLeg[]
  replacement_price: string; replaced_value: string; currency: string; difference: string
  settlement: 'pay' | 'refund' | 'none'; reserves_capacity: boolean; availability_warning: string
}
export interface LegRow { sequence: number; mode: string; route_code: string; from: string; to: string; departs_at: string; arrives_at: string }
export interface Replacements {
  state: 'not_disrupted' | 'options' | 'none'; offers: ReplacementOffer[]; retained_legs: LegRow[]; affected_legs: LegRow[]
  original_arrival: string | null; reason?: string; cancellation?: CancellationQuote
}
export const fetchReplacements = (ref: string, signal?: AbortSignal) => getJson<Replacements>(`/api/bookings/${ref}/replacements/`, signal)
export const acceptReplacement = (ref: string, id: number, outcome: 'success' | 'failure', key: string) =>
  request<{ replayed: boolean; booking: Booking }>('POST', `/api/bookings/${ref}/replacements/${id}/accept/`, { outcome }, { idempotencyKey: key })
export const declineReplacement = (ref: string, id: number) => request<ReplacementOffer>('POST', `/api/bookings/${ref}/replacements/${id}/decline/`)
