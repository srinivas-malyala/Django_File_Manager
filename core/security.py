"""Small, framework-backed security controls shared by browser views."""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

security_logger = logging.getLogger("security")


def _request_identity(request: HttpRequest) -> str:
    """Use trusted server state, never a client-supplied forwarding header."""
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"


def check_rate_limit(request: HttpRequest, scope: str) -> tuple[bool, int]:
    """Apply a fixed-window cache limit and fail open if cache is unavailable."""
    limit, window = settings.SECURITY_RATE_LIMITS[scope]
    identity_hash = hashlib.sha256(_request_identity(request).encode()).hexdigest()
    cache_key = f"security-rate-limit:{scope}:{identity_hash}"
    try:
        if cache.add(cache_key, 1, timeout=window):
            count = 1
        else:
            count = cache.incr(cache_key)
    except Exception:
        security_logger.error("rate_limit_cache_unavailable scope=%s", scope)
        return True, 0

    if count <= limit:
        return True, 0
    security_logger.warning("rate_limit_rejection scope=%s", scope)
    return False, window


class RateLimitedViewMixin:
    """Throttle selected methods before browser view processing."""

    rate_limit_scope: str
    rate_limit_methods = frozenset({"GET", "POST"})

    def dispatch(self, request, *args, **kwargs):
        if request.method in self.rate_limit_methods:
            allowed, retry_after = check_rate_limit(request, self.rate_limit_scope)
            if not allowed:
                response = HttpResponse(
                    "Too many requests. Please try again later.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )
                response["Retry-After"] = str(retry_after)
                return response
        return super().dispatch(request, *args, **kwargs)
