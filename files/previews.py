"""Safe, bounded preview classification and text extraction."""

from dataclasses import dataclass

from .models import FileRecord
from .services import FileStorageService


@dataclass(frozen=True)
class TextPreview:
    content: str
    truncated: bool


class FilePreviewService:
    """Allow only explicitly supported extensions into browser previews."""

    MAX_TEXT_PREVIEW_BYTES = 1024 * 1024
    IMAGE_CONTENT_TYPES = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
    }
    TEXT_TYPES = {"txt", "csv"}

    @classmethod
    def preview_kind(cls, record: FileRecord) -> str:
        if record.file_type in cls.IMAGE_CONTENT_TYPES:
            return "image"
        if record.file_type in cls.TEXT_TYPES:
            return "text"
        if record.file_type == "pdf":
            return "pdf"
        return "unsupported"

    @classmethod
    def inline_content_type(cls, record: FileRecord) -> str | None:
        if record.file_type in cls.IMAGE_CONTENT_TYPES:
            return cls.IMAGE_CONTENT_TYPES[record.file_type]
        if record.file_type == "pdf":
            return "application/pdf"
        return None

    @classmethod
    def read_text(cls, record: FileRecord) -> TextPreview:
        stored_file = FileStorageService.open_file(record)
        try:
            content = stored_file.read(cls.MAX_TEXT_PREVIEW_BYTES + 1)
        finally:
            stored_file.close()

        truncated = len(content) > cls.MAX_TEXT_PREVIEW_BYTES
        bounded_content = content[: cls.MAX_TEXT_PREVIEW_BYTES]
        return TextPreview(
            content=bounded_content.decode("utf-8-sig", errors="replace"),
            truncated=truncated,
        )
