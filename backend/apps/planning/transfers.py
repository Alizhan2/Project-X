"""Shared transfer timing and accessibility rules for search, checkout and disruption checks."""

from datetime import timezone as datetime_timezone

from django.conf import settings

from apps.transport.models import TransferLink


class TransferRules(dict):
    """Keep the existing minutes-map interface while retaining the explicit walking/buffer split."""

    def __init__(self, links):
        self.links = {(link.from_stop_id, link.to_stop_id): link for link in links}
        super().__init__((key, link.minutes + link.boarding_buffer_minutes) for key, link in self.links.items())


def load_transfer_rules():
    return TransferRules(TransferLink.objects.all())


def transfer_minutes(transfers, origin, destination):
    if origin.pk == destination.pk:
        return settings.MIN_SAME_STOP_TRANSFER_MIN
    return transfers.get((origin.pk, destination.pk))


def connection_accessible(transfers, origin, destination):
    if origin.step_free is not True or destination.step_free is not True:
        return False
    if origin.pk == destination.pk:
        return True
    link = getattr(transfers, "links", {}).get((origin.pk, destination.pk))
    return link is not None and link.step_free is True


def leg_accessible(leg):
    return (leg.wheelchair_accessible is True and leg.from_stop.step_free is True
            and leg.to_stop.step_free is True)


def assess_connection(origin, destination, arrival, departure, transfers, *, on_demand=False):
    """EX01 uses complete timestamps; flooring minutes preserves the strict 0/5-minute boundaries."""
    same_stop = origin.pk == destination.pk
    link = getattr(transfers, "links", {}).get((origin.pk, destination.pk))
    required = transfer_minutes(transfers, origin, destination)
    walk = 0 if same_stop else (link.minutes if link else required)
    boarding = settings.MIN_SAME_STOP_TRANSFER_MIN if same_stop else (link.boarding_buffer_minutes if link else 0)
    path = origin.step_free if same_stop else (link.step_free if link else None)
    elapsed = departure.astimezone(datetime_timezone.utc) - arrival.astimezone(datetime_timezone.utc)
    margin = int(elapsed.total_seconds() // 60) - required if required is not None else None
    status = "infeasible" if margin is None or margin < 0 else "at_risk" if margin < 5 else "feasible"
    if on_demand and required is not None and margin >= 0:
        status = "on_demand"
    return {
        "from_stop": origin.code, "to_stop": destination.code,
        "walking_minutes": walk, "boarding_buffer_minutes": boarding,
        "margin_minutes": None if status == "on_demand" else margin,
        "status": status,
        "path_step_free": "unknown" if path is None else "yes" if path else "no",
    }
