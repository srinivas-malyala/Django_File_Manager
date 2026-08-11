"""REST authentication views introduced in Phase 2."""

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token"


class ThrottledTokenBlacklistView(TokenBlacklistView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token"


class AuthenticationStatusView(APIView):
    """Confirm that the supplied API credentials authenticate a real user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "success": True,
                "data": {
                    "id": request.user.pk,
                    "username": request.user.get_username(),
                },
                "message": "Authentication successful",
                "timestamp": timezone.now().isoformat(),
            }
        )
