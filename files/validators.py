"""Reusable layered validation for private file uploads."""

import mimetypes
from dataclasses import dataclass

from django.core.files.uploadedfile import UploadedFile
from django.core.files.utils import validate_file_name
from django.utils.text import get_valid_filename

try:
    import magic
except ImportError:  # pragma: no cover - supported fallback for constrained platforms
    magic = None


class FileValidationError(ValueError):
    """Raised when an uploaded file violates an application rule."""


@dataclass(frozen=True)
class ValidatedFile:
    """Sanitized metadata produced by successful upload validation."""

    original_filename: str
    extension: str
    mime_type: str


class FileValidator:
    """Validate filename, extension, size, and detectable content type."""

    MAX_FILE_SIZE = 50 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "bmp",
        "pdf",
        "doc",
        "docx",
        "txt",
        "rtf",
        "xls",
        "xlsx",
        "csv",
        "zip",
        "rar",
        "7z",
    }
    STRICT_MIME_TYPES = {
        "jpg": {"image/jpeg"},
        "jpeg": {"image/jpeg"},
        "png": {"image/png"},
        "gif": {"image/gif"},
        "bmp": {"image/bmp", "image/x-ms-bmp"},
        "pdf": {"application/pdf"},
        "txt": {"text/plain"},
        "csv": {"text/csv", "text/plain", "application/csv"},
    }
    UNSAFE_MIME_TYPES = {
        "application/javascript",
        "application/x-dosexec",
        "application/x-executable",
        "application/x-httpd-php",
        "application/x-sharedlib",
        "text/html",
        "text/javascript",
        "text/x-php",
    }

    def validate_file(self, uploaded_file: UploadedFile) -> ValidatedFile:
        if uploaded_file is None or not getattr(uploaded_file, "name", ""):
            raise FileValidationError("A filename is required.")

        original_filename = self.sanitize_filename(uploaded_file.name)
        extension = original_filename.rsplit(".", 1)[-1].lower()
        if "." not in original_filename or extension not in self.ALLOWED_EXTENSIONS:
            raise FileValidationError("This file extension is not allowed.")

        size = getattr(uploaded_file, "size", None)
        if size is None or size <= 0:
            raise FileValidationError("Empty files are not allowed.")
        if size > self.MAX_FILE_SIZE:
            raise FileValidationError("The file exceeds the 50 MB size limit.")

        mime_type = self.detect_mime_type(uploaded_file, original_filename)
        self.validate_mime_type(extension, mime_type)
        return ValidatedFile(original_filename, extension, mime_type[:100])

    @classmethod
    def validate_mime_type(cls, extension: str, mime_type: str) -> None:
        """Reject executable content and reliable extension/content mismatches."""
        normalized_mime = mime_type.split(";", 1)[0].strip().lower()
        if normalized_mime in cls.UNSAFE_MIME_TYPES:
            raise FileValidationError("The file content type is not allowed.")

        expected_types = cls.STRICT_MIME_TYPES.get(extension)
        if (
            magic is not None
            and expected_types
            and normalized_mime not in expected_types
        ):
            raise FileValidationError(
                "The file content does not match its filename extension."
            )

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Remove path components and normalize unsafe filename characters."""
        basename = filename.replace("\\", "/").split("/")[-1].replace("\x00", "")
        try:
            validate_file_name(basename)
            sanitized = get_valid_filename(basename)
        except Exception as exc:
            raise FileValidationError("The filename is invalid.") from exc

        if not sanitized:
            raise FileValidationError("The filename is invalid.")

        if len(sanitized) > 255:
            if "." in sanitized:
                stem, extension = sanitized.rsplit(".", 1)
                suffix = f".{extension}"
                if len(suffix) >= 255:
                    raise FileValidationError("The filename is invalid.")
                sanitized = f"{stem[: 255 - len(suffix)]}{suffix}"
            else:
                sanitized = sanitized[:255]
        return sanitized

    @staticmethod
    def detect_mime_type(uploaded_file: UploadedFile, filename: str) -> str:
        """Inspect file content when possible, falling back to extension inference."""
        if magic is not None:
            try:
                position = uploaded_file.tell()
                header = uploaded_file.read(4096)
                uploaded_file.seek(position)
                detected = magic.from_buffer(header, mime=True)
                if detected:
                    return str(detected)
            except Exception:
                try:
                    uploaded_file.seek(0)
                except (AttributeError, OSError):
                    pass

        guessed_type, _ = mimetypes.guess_type(filename)
        return guessed_type or "application/octet-stream"
