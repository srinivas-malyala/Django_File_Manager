"""Phase 6 server-rendered, session-authenticated file console."""

import logging
from time import monotonic
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import EmptyPage, Paginator
from django.db.models import BigIntegerField, Count, Sum
from django.db.models.functions import Coalesce
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseServerError,
)
from django.shortcuts import redirect
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from core.security import RateLimitedViewMixin

from files.models import FileRecord
from files.previews import FilePreviewService
from files.search import FileQueryParameters, FileQueryService, FileQueryValidationError
from files.services import (
    FileAccessService,
    FileStorageOperationError,
    FileStorageService,
    StoredFileMissingError,
)
from files.validators import FileValidationError

from .forms import ConsoleFileSearchForm, ConsoleFileUploadForm

security_logger = logging.getLogger("security")
file_operations_logger = logging.getLogger("file_operations")
performance_logger = logging.getLogger("performance")


def collection_view_context(request: HttpRequest, view_mode: str) -> dict[str, str]:
    """Build list/grid and pagination URLs while preserving active filters."""
    query_without_page = request.GET.copy()
    query_without_page.pop("page", None)

    list_query = query_without_page.copy()
    list_query["view"] = "list"
    grid_query = query_without_page.copy()
    grid_query["view"] = "grid"
    return {
        "view_mode": view_mode,
        "list_view_query": list_query.urlencode(),
        "grid_view_query": grid_query.urlencode(),
        "pagination_query": query_without_page.urlencode(),
    }


class OwnerFileMixin(LoginRequiredMixin):
    """Resolve a URL file UUID only inside the current user's collection."""

    request: HttpRequest
    kwargs: dict[str, UUID]

    def get_file(self) -> FileRecord:
        file_id = self.kwargs["file_id"]
        record = FileAccessService.get_owned_file(self.request.user, file_id)
        if record is None:
            security_logger.warning(
                "console_file_access_rejection user_id=%s file_id=%s",
                self.request.user.pk,
                file_id,
            )
            raise Http404("File not found")
        return record


class ConsoleDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "console/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        records = FileRecord.objects.filter(uploaded_by=self.request.user)
        statistics = records.aggregate(
            total_files=Count("id"),
            total_storage=Coalesce(
                Sum("file_size"),
                0,
                output_field=BigIntegerField(),
            ),
        )
        context.update(statistics)
        context["recent_files"] = records[:5]
        return context


class ConsoleFileListView(LoginRequiredMixin, ListView):
    template_name = "console/file_list.html"
    context_object_name = "files"
    paginate_by = 20

    def get_queryset(self):
        return FileRecord.objects.filter(uploaded_by=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        view_mode = self.request.GET.get("view", "list")
        if view_mode not in {"list", "grid"}:
            view_mode = "list"
        context.update(collection_view_context(self.request, view_mode))
        return context


class ConsoleAdvancedFileListView(
    RateLimitedViewMixin, LoginRequiredMixin, TemplateView
):
    """Render validated Phase 5 querying as an accessible browser form."""

    template_name = "console/advanced_files.html"
    rate_limit_scope = "file_search"
    rate_limit_methods = frozenset({"GET"})

    def get_context_data(self, **kwargs):
        started_at = monotonic()
        context = super().get_context_data(**kwargs)
        form = ConsoleFileSearchForm(self.request.GET or None)
        view_mode = self.request.GET.get("view", "list")
        if view_mode not in {"list", "grid"}:
            view_mode = "list"
            if form.is_bound:
                form.is_valid()
                form.add_error(None, "Unsupported view mode.")

        files = FileRecord.objects.none()
        paginator = None
        page_obj = None
        query_is_valid = not form.is_bound or form.is_valid()
        query_params = self.request.GET.copy()
        query_params.pop("view", None)

        if query_is_valid:
            try:
                parameters = FileQueryParameters.from_query_params(query_params)
                files = FileQueryService.build_queryset(self.request.user, parameters)
                paginator = Paginator(files, parameters.page_size)
                page_obj = paginator.page(parameters.page)
                files = page_obj.object_list
            except FileQueryValidationError as exc:
                field, errors = next(iter(exc.errors.items()))
                form.is_valid()
                form.add_error(field if field in form.fields else None, errors[0])
            except EmptyPage as exc:
                raise Http404("Page does not exist") from exc

        context.update(
            {
                "form": form,
                "files": files,
                "paginator": paginator,
                "page_obj": page_obj,
                "is_paginated": bool(paginator and paginator.num_pages > 1),
            }
        )
        context.update(collection_view_context(self.request, view_mode))
        performance_logger.info(
            "console_file_search user_id=%s result_count=%s duration_ms=%.2f",
            self.request.user.pk,
            len(files),
            (monotonic() - started_at) * 1000,
        )
        return context


class ConsoleFileUploadView(RateLimitedViewMixin, LoginRequiredMixin, FormView):
    template_name = "console/file_upload.html"
    form_class = ConsoleFileUploadForm
    rate_limit_scope = "file_upload"
    rate_limit_methods = frozenset({"POST"})

    def form_valid(self, form: ConsoleFileUploadForm) -> HttpResponse:
        try:
            record = FileStorageService().create_file(
                uploaded_file=form.cleaned_data["file"],
                owner=self.request.user,
                description=form.cleaned_data.get("description") or None,
            )
        except FileValidationError as exc:
            form.add_error("file", str(exc))
            return self.form_invalid(form)

        messages.success(self.request, "File uploaded successfully.")
        return redirect("user_console:file_detail", file_id=record.pk)


class ConsoleFileDetailView(OwnerFileMixin, TemplateView):
    template_name = "console/file_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["file"] = self.get_file()
        return context


class ConsoleFilePreviewView(OwnerFileMixin, TemplateView):
    template_name = "console/file_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        record = self.get_file()
        preview_kind = FilePreviewService.preview_kind(record)
        context.update({"file": record, "preview_kind": preview_kind})

        if preview_kind == "text":
            try:
                preview = FilePreviewService.read_text(record)
            except StoredFileMissingError as exc:
                raise Http404("Stored file content was not found") from exc
            except FileStorageOperationError:
                context["preview_error"] = "File preview is temporarily unavailable."
            else:
                context["preview_content"] = preview.content
                context["preview_truncated"] = preview.truncated
        return context


class ConsoleFilePreviewContentView(OwnerFileMixin, View):
    """Stream only allowlisted image/PDF content for authenticated embedding."""

    def get(self, request, file_id: UUID) -> HttpResponse:
        record = self.get_file()
        content_type = FilePreviewService.inline_content_type(record)
        if content_type is None:
            raise Http404("Inline preview is unavailable")
        try:
            stored_file = FileStorageService.open_file(record)
        except StoredFileMissingError as exc:
            raise Http404("Stored file content was not found") from exc
        except FileStorageOperationError:
            return HttpResponseServerError("File preview is temporarily unavailable.")

        response = FileResponse(
            stored_file,
            as_attachment=False,
            filename=record.original_filename,
            content_type=content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        file_operations_logger.info(
            "preview_started user_id=%s file_id=%s",
            request.user.pk,
            record.pk,
        )
        return response


class ConsoleFileDownloadView(OwnerFileMixin, View):
    def get(self, request, file_id: UUID) -> HttpResponse:
        record = self.get_file()
        try:
            stored_file = FileStorageService.open_file(record)
        except StoredFileMissingError as exc:
            raise Http404("Stored file content was not found") from exc
        except FileStorageOperationError:
            return HttpResponseServerError("File could not be downloaded.")

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


class ConsoleFileDeleteView(OwnerFileMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request, file_id: UUID) -> HttpResponse:
        record = self.get_file()
        try:
            FileStorageService.delete_file(record)
        except StoredFileMissingError as exc:
            raise Http404("Stored file content was not found") from exc
        except FileStorageOperationError:
            return HttpResponseServerError("File could not be deleted.")

        messages.success(request, "File deleted successfully.")
        return redirect("user_console:file_list")


class ConsoleProfileView(LoginRequiredMixin, TemplateView):
    template_name = "console/profile.html"


class ConsoleSupportContactView(LoginRequiredMixin, TemplateView):
    """Show authenticated users the available support contact route."""

    template_name = "support/contact.html"


class ConsoleSupportHelpView(LoginRequiredMixin, TemplateView):
    """Provide concise guidance for common file-management tasks."""

    template_name = "support/help.html"


class ConsoleSupportTermsView(LoginRequiredMixin, TemplateView):
    """Present the service's baseline acceptable-use terms."""

    template_name = "support/terms.html"
