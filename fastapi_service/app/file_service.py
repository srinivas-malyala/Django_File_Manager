"""Upload validation and private content storage."""

import mimetypes
from pathlib import Path
import re
from uuid import uuid4

from fastapi import UploadFile

try:
    import magic
except ImportError:  # pragma: no cover
    magic = None


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


class UploadValidationError(ValueError):
    pass


def sanitize_filename(filename: str | None) -> tuple[str, str]:
    basename = (filename or "").replace("\\", "/").split("/")[-1].replace("\x00", "")
    basename = re.sub(r"[^A-Za-z0-9._ -]", "_", basename).strip(" .")
    if not basename or "." not in basename:
        raise UploadValidationError("A valid filename and extension are required.")
    extension = basename.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("This file extension is not allowed.")
    if len(basename) > 255:
        suffix = f".{extension}"
        basename = f"{basename[:-len(suffix)][:255-len(suffix)]}{suffix}"
    return basename, extension


def detect_mime(header: bytes, filename: str) -> str:
    if magic is not None:
        detected = magic.from_buffer(header, mime=True)
        if detected:
            return str(detected).split(";", 1)[0].lower()[:100]
    return (mimetypes.guess_type(filename)[0] or "application/octet-stream")[:100]


def validate_mime(extension: str, mime_type: str) -> None:
    if mime_type in UNSAFE_MIME_TYPES:
        raise UploadValidationError("The file content type is not allowed.")
    expected = STRICT_MIME_TYPES.get(extension)
    if magic is not None and expected and mime_type not in expected:
        raise UploadValidationError("The file content does not match its extension.")


async def store_upload(upload: UploadFile, destination: Path, max_size: int):
    original_filename, extension = sanitize_filename(upload.filename)
    file_id = str(uuid4())
    stored_filename = f"{file_id}.{extension}"
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / stored_filename
    temporary_path = destination / f".{stored_filename}.part"
    size = 0
    header = b""
    try:
        with temporary_path.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise UploadValidationError(
                        "The file exceeds the 50 MB size limit."
                    )
                if len(header) < 4096:
                    header += chunk[: 4096 - len(header)]
                output.write(chunk)
        if size == 0:
            raise UploadValidationError("Empty files are not allowed.")
        mime_type = detect_mime(header, original_filename)
        validate_mime(extension, mime_type)
        temporary_path.replace(final_path)
        return file_id, stored_filename, original_filename, size, mime_type, final_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
