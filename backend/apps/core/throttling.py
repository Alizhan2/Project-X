from rest_framework.throttling import ScopedRateThrottle


class IpScopedRateThrottle(ScopedRateThrottle):
    """Always keyed by client IP, even for signed-in sessions (used for login/register so an existing session
    cannot be used to dodge the limit)."""

    def get_cache_key(self, request, view):
        if not self.scope:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def throttle(scope, by_ip=False):
    """Apply a named rate (settings REST_FRAMEWORK.DEFAULT_THROTTLE_RATES) to a function-based DRF view.
    Place ABOVE @api_view. Default key: user id when signed in, otherwise client IP (see DOEDU_TRUSTED_PROXIES)."""

    def deco(view):
        view.cls.throttle_classes = [IpScopedRateThrottle if by_ip else ScopedRateThrottle]
        view.cls.throttle_scope = scope
        return view

    return deco
