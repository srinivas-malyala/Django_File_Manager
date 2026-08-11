"""File metadata domain models."""

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone


class FileRecord(models.Model):
    """Metadata for one private file owned by the uploading user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField()
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    upload_date = models.DateTimeField(default=timezone.now)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )

    class Meta:
        ordering = ["-upload_date"]
        indexes = [
            models.Index(
                fields=["uploaded_by", "-upload_date"],
                name="files_owner_date_idx",
            ),
            models.Index(fields=["upload_date"], name="files_upload_date_idx"),
            models.Index(fields=["mime_type"], name="files_mime_type_idx"),
        ]

    def __str__(self) -> str:
        return self.original_filename

    @property
    def file_type(self) -> str:
        """Return the normalized original filename extension without its dot."""
        suffix = Path(self.original_filename).suffix
        return suffix[1:].lower() if suffix else "unknown"

    def get_file_size_display(self) -> str:
        """Return the stored byte count in a concise human-readable form."""
        size = self.file_size
        if size == 1:
            return "1 byte"
        if size < 1024:
            return f"{size} bytes"

        value = float(size)
        for unit in ("KB", "MB", "GB"):
            value /= 1024
            if value < 1024:
                return f"{value:.1f} {unit}"
        return f"{value / 1024:.1f} TB"
