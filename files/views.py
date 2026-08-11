"""Owner-scoped file REST views through the Phase 4 lifecycle."""

import logging
from time import monotonic
from typing import Any
from uuid import UUID

from django.core.paginator import EmptyPage, Paginator
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import FileRecord
from .search import FileQueryParameters, FileQueryService, FileQueryValidationError
from .serializers import (
    FileMetadataUpdateSerializer,
    FileRecordSerializer,
    FileUploadSerializer,
)
from .services import (
    FileAccessService,
    FileStorageOperationError,
    FileStorageService,
    StoredFileMissingError,
)
from .validators import FileValidationError

security_logger = logging.getLogger("security")
file_operations_logger = logging.getLogger("file_operations")
performance_logger = logging.getLogger("performance")


def error_response(
    message: str,
    *,
    errors: Any = None,
    response_status: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    return Response(
        {
            "success": False,
            "data": None,
            "message": message,
            "errors": errors or {},
            "timestamp": timezone.now().isoformat(),
        },
        status=response_status,
    )


def get_owned_file(request: Request, file_id: UUID) -> FileRecord | None:
    """Resolve a record through owner scope so foreign UUIDs remain undisclosed."""
    record = FileAccessService.get_owned_file(request.user, file_id)
    if record is None:
        security_logger.warning(
            "file_access_rejection user_id=%s file_id=%s",
            request.user.pk,
            file_id,
        )
    return record


class FileUploadView(APIView):
    """Validate and store a file owned by the authenticated user."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "file_upload"

    def post(self, request: Request) -> Response:
        serializer = FileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            security_logger.info(
                "file_validation_rejection user_id=%s", request.user.pk
            )
            return error_response(
                "File upload validation failed", errors=serializer.errors
            )

        try:
            record = FileStorageService().create_file(
                uploaded_file=serializer.validated_data["file"],
                owner=request.user,
                description=serializer.validated_data.get("description"),
            )
        except FileValidationError as exc:
            security_logger.info(
                "file_validation_rejection user_id=%s", request.user.pk
            )
            return error_response(str(exc), errors={"file": [str(exc)]})

        return Response(
            {
                "success": True,
                "data": FileRecordSerializer(record).data,
                "message": "File uploaded successfully",
                "timestamp": timezone.now().isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class FileListView(APIView):
    """List only files owned by the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        records = FileRecord.objects.filter(uploaded_by=request.user)
        return Response(
            {
                "success": True,
                "data": FileRecordSerializer(records, many=True).data,
                "message": "Files retrieved successfully",
                "timestamp": timezone.now().isoformat(),
            }
        )


class MyFilesView(APIView):
    """Return a validated, owner-scoped, server-paginated file collection."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "file_search"

    def get(self, request: Request) -> Response:
        started_at = monotonic()
        try:
            parameters = FileQueryParameters.from_query_params(request.query_params)
            queryset = FileQueryService.build_queryset(request.user, parameters)
            paginator = Paginator(queryset, parameters.page_size)
            page = paginator.page(parameters.page)
        except FileQueryValidationError as exc:
            return error_response("Invalid file query", errors=exc.errors)
        except EmptyPage:
            return error_response(
                "Page does not exist",
                errors={"page": ["Page does not exist."]},
                response_status=status.HTTP_404_NOT_FOUND,
            )

        def page_url(page_number: int) -> str:
            query_params = request.query_params.copy()
            query_params["page"] = page_number
            return request.build_absolute_uri(
                f"{request.path}?{query_params.urlencode()}"
            )

        response = Response(
            {
                "success": True,
                "data": {
                    "count": paginator.count,
                    "page": page.number,
                    "page_size": parameters.page_size,
                    "total_pages": paginator.num_pages,
                    "next": (
                        page_url(page.next_page_number()) if page.has_next() else None
                    ),
                    "previous": (
                        page_url(page.previous_page_number())
                        if page.has_previous()
                        else None
                    ),
                    "results": FileRecordSerializer(page.object_list, many=True).data,
                },
                "message": "Files retrieved successfully",
                "timestamp": timezone.now().isoformat(),
            }
        )
        performance_logger.info(
            "file_search user_id=%s result_count=%s duration_ms=%.2f",
            request.user.pk,
            len(page.object_list),
            (monotonic() - started_at) * 1000,
        )
        return response


class FileDetailView(APIView):
    """Retrieve, update, or delete one owner-scoped file record."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, file_id: UUID) -> Response:
        record = get_owned_file(request, file_id)
        if record is None:
            return error_response(
                "File not found",
                response_status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "success": True,
                "data": FileRecordSerializer(record).data,
                "message": "File retrieved successfully",
                "timestamp": timezone.now().isoformat(),
            }
        )

    def put(self, request: Request, file_id: UUID) -> Response:
        record = get_owned_file(request, file_id)
        if record is None:
            return error_response(
                "File not found",
                response_status=status.HTTP_404_NOT_FOUND,
            )

        serializer = FileMetadataUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "File metadata validation failed",
                errors=serializer.errors,
            )

        if "description" in serializer.validated_data:
            FileStorageService.update_description(
                record,
                serializer.validated_data["description"],
            )
        return Response(
            {
                "success": True,
                "data": FileRecordSerializer(record).data,
                "message": "File metadata updated successfully",
                "timestamp": timezone.now().isoformat(),
            }
        )

    def delete(self, request: Request, file_id: UUID) -> Response:
        record = get_owned_file(request, file_id)
        if record is None:
            return error_response(
                "File not found",
                response_status=status.HTTP_404_NOT_FOUND,
            )

        try:
            FileStorageService.delete_file(record)
        except StoredFileMissingError:
            return error_response(
                "Stored file content was not found",
                response_status=status.HTTP_404_NOT_FOUND,
            )
        except FileStorageOperationError:
            return error_response(
                "File could not be deleted",
                response_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "success": True,
                "data": None,
                "message": "File deleted successfully",
                "timestamp": timezone.now().isoformat(),
            }
        )


class FileDownloadView(APIView):
    """Stream owner-authorized content using a safe attachment filename."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, file_id: UUID):
        record = get_owned_file(request, file_id)
        if record is None:
            return error_response(
                "File not found",
                response_status=status.HTTP_404_NOT_FOUND,
            )

        try:
            stored_file = FileStorageService.open_file(record)
        except StoredFileMissingError:
            return error_response(
                "Stored file content was not found",
                response_status=status.HTTP_404_NOT_FOUND,
            )
        except FileStorageOperationError:
            return error_response(
                "File could not be downloaded",
                response_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = FileResponse(
            stored_file,
            as_attachment=True,
            filename=record.original_filename,
            content_type=record.mime_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        file_operations_logger.info(
            "download_started user_id=%s file_id=%s",
            request.user.pk,
            record.pk,
        )
        return response
