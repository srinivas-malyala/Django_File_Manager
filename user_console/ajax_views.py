"""Authenticated JSON enhancements for the Phase 8 console."""

import logging
from dataclasses import replace
from time import monotonic

from django.contrib.auth.mixins import AccessMixin
from django.core.paginator import EmptyPage, Paginator
from django.db.models import BigIntegerField, Count, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views import View

from files.models import FileRecord
from files.search import FileQueryParameters, FileQueryService, FileQueryValidationError
from files.serializers import FileRecordSerializer
from core.security import RateLimitedViewMixin

performance_logger = logging.getLogger("performance")


def json_response(*, data, message: str, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {
            "success": status < 400,
            "data": data if status < 400 else None,
            "message": message,
            "timestamp": timezone.now().isoformat(),
        },
        status=status,
    )


class JsonLoginRequiredMixin(AccessMixin):
    """Return JSON 401 instead of an HTML login redirect."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_response(
                data=None, message="Authentication required", status=401
            )
        return super().dispatch(request, *args, **kwargs)


class ConsoleAjaxFileStatsView(JsonLoginRequiredMixin, View):
    def get(self, request) -> JsonResponse:
        statistics = FileRecord.objects.filter(uploaded_by=request.user).aggregate(
            total_files=Count("id"),
            total_storage=Coalesce(
                Sum("file_size"),
                0,
                output_field=BigIntegerField(),
            ),
        )
        return json_response(
            data=statistics,
            message="File statistics retrieved successfully",
        )


class ConsoleAjaxRecentFilesView(JsonLoginRequiredMixin, View):
    MAX_RECENT_FILES = 20

    def get(self, request) -> JsonResponse:
        raw_limit = request.GET.get("limit", "5")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return json_response(data=None, message="Invalid limit", status=400)
        if limit <= 0:
            return json_response(data=None, message="Invalid limit", status=400)
        limit = min(limit, self.MAX_RECENT_FILES)

        records = FileRecord.objects.filter(uploaded_by=request.user)[:limit]
        results = [self._serialize_record(record) for record in records]
        return json_response(
            data={"results": results, "limit": limit},
            message="Recent files retrieved successfully",
        )

    @staticmethod
    def _serialize_record(record: FileRecord) -> dict:
        data = dict(FileRecordSerializer(record).data)
        data["detail_url"] = reverse("user_console:file_detail", args=[record.pk])
        data["download_url"] = reverse("user_console:file_download", args=[record.pk])
        return data


class ConsoleAjaxSearchView(RateLimitedViewMixin, JsonLoginRequiredMixin, View):
    MAX_AJAX_PAGE_SIZE = 20
    rate_limit_scope = "file_search"
    rate_limit_methods = frozenset({"GET"})

    def get(self, request) -> JsonResponse:
        started_at = monotonic()
        query_params = request.GET.copy()
        if "page_size" not in query_params:
            query_params["page_size"] = "10"
        try:
            parameters = FileQueryParameters.from_query_params(query_params)
            parameters = replace(
                parameters,
                page_size=min(parameters.page_size, self.MAX_AJAX_PAGE_SIZE),
            )
            queryset = FileQueryService.build_queryset(request.user, parameters)
            paginator = Paginator(queryset, parameters.page_size)
            page = paginator.page(parameters.page)
        except FileQueryValidationError as exc:
            return json_response(data=None, message=str(exc), status=400)
        except EmptyPage:
            return json_response(data=None, message="Page does not exist", status=404)

        results = []
        for record in page.object_list:
            data = dict(FileRecordSerializer(record).data)
            data["detail_url"] = reverse("user_console:file_detail", args=[record.pk])
            results.append(data)
        response = json_response(
            data={
                "count": paginator.count,
                "page": page.number,
                "page_size": parameters.page_size,
                "total_pages": paginator.num_pages,
                "results": results,
            },
            message="Files retrieved successfully",
        )
        performance_logger.info(
            "ajax_file_search user_id=%s result_count=%s duration_ms=%.2f",
            request.user.pk,
            len(results),
            (monotonic() - started_at) * 1000,
        )
        return response
