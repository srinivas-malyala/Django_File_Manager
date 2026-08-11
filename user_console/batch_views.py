"""Phase 8 browser batch operations."""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    FileResponse,
    Http404,
    HttpResponseBadRequest,
    HttpResponseServerError,
)
from django.shortcuts import redirect
from django.views import View

from files.batch import BatchFileService, BatchOperationError
from files.services import FileStorageOperationError, StoredFileMissingError

from .forms import BatchFileOperationForm

file_operations_logger = logging.getLogger("file_operations")


class ConsoleBatchFileView(LoginRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request):
        form = BatchFileOperationForm(request.POST, user=request.user)
        if not form.is_valid():
            return HttpResponseBadRequest("Invalid batch request.")

        validated_records = {
            str(record.pk): record for record in form.cleaned_data["file_ids"]
        }
        records = [
            validated_records[file_id] for file_id in request.POST.getlist("file_ids")
        ]
        action = form.cleaned_data["action"]
        try:
            if action == "delete":
                deleted_count = BatchFileService.delete_files(records)
                messages.success(
                    request, f"Deleted {deleted_count} files successfully."
                )
                return redirect("user_console:file_list")

            archive = BatchFileService.build_zip(records)
        except BatchOperationError as exc:
            return HttpResponseBadRequest(str(exc))
        except StoredFileMissingError as exc:
            raise Http404("Stored file content was not found") from exc
        except FileStorageOperationError:
            return HttpResponseServerError("Batch operation could not be completed.")

        response = FileResponse(
            archive,
            as_attachment=True,
            filename="files.zip",
            content_type="application/zip",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        file_operations_logger.info(
            "batch_download_started user_id=%s file_count=%s",
            request.user.pk,
            len(records),
        )
        return response
