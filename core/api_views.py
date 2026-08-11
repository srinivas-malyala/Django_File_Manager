"""Phase 11 service discovery, health, and administrative statistics APIs."""

import logging
from time import monotonic

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import connection
from django.db.models import BigIntegerField, Count, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from files.models import FileRecord

errors_logger = logging.getLogger("errors")
performance_logger = logging.getLogger("performance")
security_logger = logging.getLogger("security")
admin_logger = logging.getLogger("admin")


class ApiDiscoveryView(APIView):
    """Advertise stable API entry points without requiring credentials."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "health": reverse("core_api:health"),
                "statistics": reverse("core_api:statistics"),
                "files": reverse("file_api:list"),
                "upload": reverse("file_api:upload"),
                "my_files": reverse("file_api:my_files"),
                "token": reverse("account_api:token_obtain_pair"),
            }
        )


class HealthCheckView(APIView):
    """Report generic dependency states while keeping infrastructure private."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @staticmethod
    def _database_status() -> str:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            errors_logger.error(
                "health_dependency_failure dependency=database error_type=%s",
                type(exc).__name__,
            )
            return "unavailable"
        return "connected"

    @staticmethod
    def _storage_status() -> str:
        try:
            default_storage.exists("health-check")
        except Exception as exc:
            errors_logger.error(
                "health_dependency_failure dependency=file_storage error_type=%s",
                type(exc).__name__,
            )
            return "unavailable"
        return "accessible"

    def get(self, request: Request) -> Response:
        started_at = monotonic()
        checks = {
            "database": self._database_status(),
            "file_storage": self._storage_status(),
        }
        is_healthy = checks == {
            "database": "connected",
            "file_storage": "accessible",
        }
        health_status = "healthy" if is_healthy else "unhealthy"
        performance_logger.info(
            "health_check status=%s duration_ms=%.2f",
            health_status,
            (monotonic() - started_at) * 1000,
        )
        response = Response(
            {
                "status": health_status,
                "timestamp": timezone.now().isoformat(),
                "version": settings.APPLICATION_VERSION,
                "checks": checks,
            },
            status=(
                status.HTTP_200_OK
                if is_healthy
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
        )
        response["Cache-Control"] = "no-store"
        return response


class IsApplicationAdmin(BasePermission):
    """Allow system statistics only to designated application administrators."""

    message = "Administrator access is required."

    def has_permission(self, request: Request, view) -> bool:
        allowed = bool(
            request.user.is_authenticated
            and (request.user.is_admin or request.user.is_superuser)
        )
        if not allowed and request.user.is_authenticated:
            security_logger.warning(
                "admin_statistics_access_rejection user_id=%s", request.user.pk
            )
        return allowed


class AggregateStatisticsView(APIView):
    """Return non-sensitive global counts to application administrators."""

    permission_classes = [IsApplicationAdmin]

    def get(self, request: Request) -> Response:
        user_model = get_user_model()
        file_statistics = FileRecord.objects.aggregate(
            total_files=Count("id"),
            total_storage=Coalesce(
                Sum("file_size"),
                0,
                output_field=BigIntegerField(),
            ),
        )
        data = {
            "total_users": user_model.objects.count(),
            "active_users": user_model.objects.filter(is_active=True).count(),
            **file_statistics,
        }
        admin_logger.info("aggregate_statistics_view user_id=%s", request.user.pk)
        response = Response(
            {
                "success": True,
                "data": data,
                "message": "Aggregate statistics retrieved successfully",
                "timestamp": timezone.now().isoformat(),
            }
        )
        response["Cache-Control"] = "private, no-store"
        return response
