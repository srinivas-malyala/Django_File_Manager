"""File admin registrations will be added in a later phase."""

"""Read-only administrative visibility for private file metadata."""

from django.contrib import admin

from .models import FileRecord


@admin.register(FileRecord)
class FileRecordAdmin(admin.ModelAdmin):
    """Prevent admin edits from bypassing validation and storage lifecycle rules."""

    list_display = (
        "original_filename",
        "uploaded_by",
        "file_size",
        "mime_type",
        "upload_date",
    )
    list_filter = ("mime_type", "upload_date")
    search_fields = ("original_filename", "description", "uploaded_by__username")
    readonly_fields = (
        "id",
        "filename",
        "original_filename",
        "file_path",
        "file_size",
        "mime_type",
        "description",
        "upload_date",
        "uploaded_by",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
