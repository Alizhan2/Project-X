"""A passenger-facing timeline of what happened to a booking. Built only from records that already exist
(booking, payment attempts, refunds, disruption notifications); nothing extra is stored, and the texts are
fixed phrases that the frontend translates. No e-mail, IP or other personal data is included."""

from apps.transport.markets import booking_timezone, local_iso

# Notification kinds that describe something that happened to the journey (not generic account messages).
JOURNEY_NOTICE_KINDS = {
    "journey_delayed", "journey_disrupted", "replacement_options", "no_replacement",
    "replacement_confirmed", "reservation_released",
}


def booking_activity(booking):
    events = [{"kind": "reserved", "title": "Places reserved", "at": booking.created_at}]
    for attempt in booking.payment_attempts.all():
        if attempt.status == "succeeded":
            title = "Payment confirmed (simulated)" if attempt.purpose == "initial" else "Replacement paid (simulated)"
            events.append({"kind": "payment", "title": title, "at": attempt.created_at, "amount": f"{attempt.amount:.2f}", "currency": attempt.currency})
        elif attempt.status == "failed":
            events.append({"kind": "payment_failed", "title": "Payment failed (simulated)", "at": attempt.created_at})
    for note in booking.notifications.all():
        if note.kind in JOURNEY_NOTICE_KINDS:
            events.append({"kind": note.kind, "title": note.title, "at": note.created_at})
    for refund in booking.refunds.all():
        events.append({"kind": "refund", "title": {"requested": "Refund requested (simulated)", "pending": "Refund pending (simulated)", "failed": "Refund failed (simulated)", "completed": "Refund issued (simulated)"}[refund.status], "at": refund.completed_at or refund.created_at,
                       "amount": f"{refund.amount:.2f}", "currency": refund.currency})
    if booking.cancelled_at:
        events.append({"kind": "cancelled", "title": "Booking cancelled", "at": booking.cancelled_at})
    events.sort(key=lambda e: e["at"])
    zone = booking_timezone(booking)
    return [{**e, "at": local_iso(e["at"], zone)} for e in events]
