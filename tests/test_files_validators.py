"""Focused security tests for reusable upload validation."""

from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from files.validators import FileValidationError, FileValidator


def test_validator_requires_filename() -> None:
    with pytest.raises(FileValidationError, match="filename is required"):
        FileValidator().validate_file(None)


def test_validator_rejects_empty_content_directly() -> None:
    upload = SimpleUploadedFile("empty.txt", b"")

    with pytest.raises(FileValidationError, match="Empty files"):
        FileValidator().validate_file(upload)


@pytest.mark.parametrize("filename", [".", "   "])
def test_sanitizer_rejects_filename_without_usable_characters(filename: str) -> None:
    with pytest.raises(FileValidationError, match="filename is invalid"):
        FileValidator.sanitize_filename(filename)


def test_sanitizer_bounds_long_filename_while_preserving_extension() -> None:
    sanitized = FileValidator.sanitize_filename(f"{'a' * 300}.pdf")

    assert len(sanitized) == 255
    assert sanitized.endswith(".pdf")


def test_sanitizer_bounds_long_extensionless_filename() -> None:
    sanitized = FileValidator.sanitize_filename("a" * 300)

    assert sanitized == "a" * 255


def test_sanitizer_rejects_extension_that_cannot_fit() -> None:
    with pytest.raises(FileValidationError, match="filename is invalid"):
        FileValidator.sanitize_filename(f"name.{'x' * 300}")


def test_content_mime_detection_restores_stream_position(monkeypatch) -> None:
    detector = SimpleNamespace(from_buffer=lambda content, mime: "application/pdf")
    monkeypatch.setattr("files.validators.magic", detector)
    upload = SimpleUploadedFile("document.pdf", b"%PDF-1.7\ncontent")
    upload.seek(4)

    detected = FileValidator.detect_mime_type(upload, upload.name)

    assert detected == "application/pdf"
    assert upload.tell() == 4


def test_mime_detection_falls_back_when_content_inspection_fails(monkeypatch) -> None:
    detector = SimpleNamespace(
        from_buffer=lambda content, mime: (_ for _ in ()).throw(RuntimeError("failed"))
    )
    monkeypatch.setattr("files.validators.magic", detector)
    upload = SimpleUploadedFile("notes.txt", b"plain text")

    detected = FileValidator.detect_mime_type(upload, upload.name)

    assert detected == "text/plain"
    assert upload.tell() == 0


def test_unknown_mime_type_uses_binary_fallback(monkeypatch) -> None:
    monkeypatch.setattr("files.validators.magic", None)
    upload = SimpleUploadedFile("unknown.unmapped", b"content")

    detected = FileValidator.detect_mime_type(upload, upload.name)

    assert detected == "application/octet-stream"
