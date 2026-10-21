from .models import Notification


def notify(user, kind, title, body, booking=None, dedupe_key=None, link=""):
    """Create a notification once per (user, dedupe_key). Returns it, or None if it already existed."""
    key = dedupe_key or f"{kind}:{booking.pk if booking else ''}:{title}"
    obj, created = Notification.objects.get_or_create(
        user=user, dedupe_key=key, defaults={"kind": kind, "title": title, "body": body, "booking": booking, "link": link}
    )
    return obj if created else None
