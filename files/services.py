"""Storage and persistence services for private file uploads."""

import logging
import uuid
from uuid import UUID

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from .models import FileRecord
from .validators import FileValidator

file_operations_logger = logging.getLogger("file_operations")
errors_logger = logging.getLogger("errors")


class StoredFileMissingError(FileNotFoundError):
    """Raised when metadata points to content that is absent from storage."""


class FileStorageOperationError(RuntimeError):
    """Raised when the storage backend cannot complete an operation."""


class FileAccessService:
    """Resolve file records without ever bypassing their authenticated owner."""

    @staticmethod
    def get_owned_file(
        owner: AbstractBaseUser,
        file_id: UUID,
    ) -> FileRecord | None:
        return FileRecord.objects.filter(pk=file_id, uploaded_by=owner).first()


class FileStorageService:
    """Coordinate private file storage and metadata persistence."""

    storage_prefix = "files"

    def __init__(self, validator: FileValidator | None = None) -> None:
        self.validator = validator or FileValidator()

    def create_file(
        self,
        *,
        uploaded_file: UploadedFile,
        owner: AbstractBaseUser,
        description: str | None = None,
    ) -> FileRecord:
        validated = self.validator.validate_file(uploaded_file)
        record_id = uuid.uuid4()
        storage_name = f"{self.storage_prefix}/{record_id}.{validated.extension}"
        stored_path: str | None = None

        try:
            stored_path = default_storage.save(storage_name, uploaded_file)
            with transaction.atomic():
                record = FileRecord.objects.create(
                    id=record_id,
                    filename=stored_path.rsplit("/", 1)[-1],
                    original_filename=validated.original_filename,
                    file_path=stored_path,
                    file_size=uploaded_file.size,
                    mime_type=validated.mime_type,
                    description=description,
                    uploaded_by=owner,
                )
        except Exception:
            if stored_path:
                try:
                    default_storage.delete(stored_path)
                except Exception as cleanup_exc:
                    errors_logger.error(
                        "orphan_cleanup_failure user_id=%s error_type=%s",
                        owner.pk,
                        type(cleanup_exc).__name__,
                    )
            raise

        file_operations_logger.info(
            "upload_success user_id=%s file_id=%s",
            owner.pk,
            record.pk,
        )
        return record

    @staticmethod
    def update_description(
        record: FileRecord,
        description: str | None,
    ) -> FileRecord:
        record.description = description
        record.save(update_fields=["description"])
        file_operations_logger.info(
            "metadata_update user_id=%s file_id=%s",
            record.uploaded_by_id,
            record.pk,
        )
        return record

    @staticmethod
    def open_file(record: FileRecord):
        """Open stored content for streaming without exposing its internal path."""
        try:
            if not default_storage.exists(record.file_path):
                raise StoredFileMissingError("Stored file content was not found.")
            return default_storage.open(record.file_path, mode="rb")
        except StoredFileMissingError:
            raise
        except FileNotFoundError as exc:
            raise StoredFileMissingError("Stored file content was not found.") from exc
        except Exception as exc:
            errors_logger.error(
                "storage_open_failure user_id=%s file_id=%s error_type=%s",
                record.uploaded_by_id,
                record.pk,
                type(exc).__name__,
            )
            raise FileStorageOperationError(
                "Stored file content could not be opened."
            ) from exc

    @staticmethod
    def delete_file(record: FileRecord) -> None:
        """Delete physical content before removing its owner-scoped metadata."""
        try:
            if not default_storage.exists(record.file_path):
                raise StoredFileMissingError("Stored file content was not found.")
            default_storage.delete(record.file_path)
        except StoredFileMissingError:
            raise
        except Exception as exc:
            errors_logger.error(
                "storage_delete_failure user_id=%s file_id=%s error_type=%s",
                record.uploaded_by_id,
                record.pk,
                type(exc).__name__,
            )
            raise FileStorageOperationError(
                "Stored file content could not be deleted."
            ) from exc

        user_id = record.uploaded_by_id
        file_id = record.pk
        try:
            record.delete()
        except Exception as exc:
            errors_logger.error(
                "metadata_delete_failure_after_storage_delete user_id=%s file_id=%s error_type=%s",
                user_id,
                file_id,
                type(exc).__name__,
            )
            raise FileStorageOperationError(
                "File metadata could not be deleted."
            ) from exc

        file_operations_logger.info(
            "delete_success user_id=%s file_id=%s",
            user_id,
            file_id,
        )
