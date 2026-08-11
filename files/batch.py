"""Bounded batch file operations shared by the browser console."""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from django.core.files.storage import default_storage

from .models import FileRecord
from .services import (
    FileStorageOperationError,
    FileStorageService,
    StoredFileMissingError,
)
from .validators import FileValidationError, FileValidator


class BatchOperationError(ValueError):
    """Raised when a requested batch cannot be processed safely."""


class BatchFileService:
    MAX_BATCH_FILES = 100
    MAX_BATCH_DOWNLOAD_BYTES = 500 * 1024 * 1024
    ZIP_SPOOL_MEMORY_BYTES = 10 * 1024 * 1024

    @classmethod
    def validate_records(cls, records: Iterable[FileRecord]) -> list[FileRecord]:
        bounded_records = list(records)
        if not bounded_records:
            raise BatchOperationError("Select at least one file.")
        if len(bounded_records) > cls.MAX_BATCH_FILES:
            raise BatchOperationError(
                f"Select no more than {cls.MAX_BATCH_FILES} files."
            )
        return bounded_records

    @staticmethod
    def ensure_content_exists(records: Iterable[FileRecord]) -> None:
        for record in records:
            try:
                exists = default_storage.exists(record.file_path)
            except Exception as exc:
                raise FileStorageOperationError(
                    "Stored file availability could not be checked."
                ) from exc
            if not exists:
                raise StoredFileMissingError("Stored file content was not found.")

    @classmethod
    def delete_files(cls, records: Iterable[FileRecord]) -> int:
        bounded_records = cls.validate_records(records)
        cls.ensure_content_exists(bounded_records)
        for record in bounded_records:
            FileStorageService.delete_file(record)
        return len(bounded_records)

    @classmethod
    def build_zip(cls, records: Iterable[FileRecord]):
        bounded_records = cls.validate_records(records)
        total_size = sum(max(record.file_size, 0) for record in bounded_records)
        if total_size > cls.MAX_BATCH_DOWNLOAD_BYTES:
            raise BatchOperationError("Selected files exceed the batch download limit.")
        cls.ensure_content_exists(bounded_records)

        archive_buffer = tempfile.SpooledTemporaryFile(
            max_size=cls.ZIP_SPOOL_MEMORY_BYTES,
            mode="w+b",
        )
        used_names: set[str] = set()
        try:
            with zipfile.ZipFile(
                archive_buffer,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                for record in bounded_records:
                    archive_name = cls._unique_archive_name(record, used_names)
                    stored_file = FileStorageService.open_file(record)
                    try:
                        with archive.open(archive_name, mode="w") as archive_entry:
                            shutil.copyfileobj(
                                stored_file,
                                archive_entry,
                                length=1024 * 1024,
                            )
                    finally:
                        stored_file.close()
            archive_buffer.seek(0)
            return archive_buffer
        except Exception:
            archive_buffer.close()
            raise

    @staticmethod
    def _unique_archive_name(record: FileRecord, used_names: set[str]) -> str:
        try:
            safe_name = FileValidator.sanitize_filename(record.original_filename)
        except FileValidationError:
            safe_name = f"{record.pk}.{record.file_type}"

        candidate = safe_name
        counter = 2
        path = Path(safe_name)
        while candidate.casefold() in used_names:
            candidate = f"{path.stem} ({counter}){path.suffix}"
            counter += 1
        used_names.add(candidate.casefold())
        return candidate
