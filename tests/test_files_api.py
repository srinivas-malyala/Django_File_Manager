"""Phase 3 secure upload and owner-scoped file API tests."""

from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from files.models import FileRecord
from files.services import FileStorageService
from files.validators import FileValidator

User = get_user_model()
PASSWORD = "File-API-Passphrase-42"


@pytest.fixture
def file_api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def upload_user(db):
    return User.objects.create_user(
        username="upload-user",
        email="upload-user@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def authenticated_file_client(file_api_client, upload_user) -> APIClient:
    file_api_client.force_authenticate(user=upload_user)
    return file_api_client


@pytest.mark.django_db
def test_valid_upload_persists_safe_metadata_and_complete_content(
    authenticated_file_client,
    upload_user,
    temporary_media_root,
) -> None:
    content = b"%PDF-1.7\n1 0 obj\nPhase 3 content\nendobj\n"
    upload = SimpleUploadedFile(
        "Quarterly Report.pdf",
        content,
        content_type="application/x-client-claim",
    )

    response = authenticated_file_client.post(
        reverse("file_api:upload"),
        {"file": upload, "description": "Quarterly results"},
        format="multipart",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "File uploaded successfully"
    assert "file_path" not in payload["data"]
    assert "uploaded_by" not in payload["data"]

    record = FileRecord.objects.get(pk=payload["data"]["id"])
    assert record.uploaded_by == upload_user
    assert record.original_filename == "Quarterly_Report.pdf"
    assert record.description == "Quarterly results"
    assert record.file_size == len(content)
    assert record.mime_type
    assert record.mime_type != "application/x-client-claim"
    assert UUID(Path(record.filename).stem) == record.pk
    assert record.file_path == f"files/{record.filename}"
    assert (temporary_media_root / record.file_path).read_bytes() == content


@pytest.mark.django_db
def test_upload_rejects_invalid_extension_without_writing_file(
    authenticated_file_client,
    temporary_media_root,
) -> None:
    upload = SimpleUploadedFile("script.exe", b"not executable content")

    response = authenticated_file_client.post(
        reverse("file_api:upload"),
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert FileRecord.objects.count() == 0
    assert list(temporary_media_root.rglob("*")) == []


@pytest.mark.django_db
def test_upload_rejects_file_above_configured_limit(
    authenticated_file_client,
    temporary_media_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(FileValidator, "MAX_FILE_SIZE", 4)
    upload = SimpleUploadedFile("oversized.txt", b"12345")

    response = authenticated_file_client.post(
        reverse("file_api:upload"),
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 400
    assert "50 MB" in response.json()["message"]
    assert FileRecord.objects.count() == 0
    assert list(temporary_media_root.rglob("*")) == []


@pytest.mark.django_db
def test_upload_rejects_empty_file(
    authenticated_file_client,
    temporary_media_root,
) -> None:
    upload = SimpleUploadedFile("empty.txt", b"")

    response = authenticated_file_client.post(
        reverse("file_api:upload"),
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 400
    assert response.json()["success"] is False
    assert FileRecord.objects.count() == 0
    assert list(temporary_media_root.rglob("*")) == []


@pytest.mark.django_db
def test_upload_sanitizes_path_traversal_filename(
    authenticated_file_client,
    temporary_media_root,
) -> None:
    upload = SimpleUploadedFile(r"..\..\quarterly report.pdf", b"%PDF-1.7\nsafe")

    response = authenticated_file_client.post(
        reverse("file_api:upload"),
        {"file": upload},
        format="multipart",
    )

    assert response.status_code == 201
    record = FileRecord.objects.get()
    assert record.original_filename == "quarterly_report.pdf"
    assert ".." not in record.original_filename
    assert "/" not in record.original_filename
    assert "\\" not in record.original_filename
    assert (temporary_media_root / record.file_path).is_file()


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint_name", ["file_api:upload", "file_api:list"])
def test_file_endpoints_require_authentication(file_api_client, endpoint_name) -> None:
    response = (
        file_api_client.post(reverse(endpoint_name))
        if endpoint_name.endswith("upload")
        else file_api_client.get(reverse(endpoint_name))
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_file_list_is_scoped_to_authenticated_owner(
    authenticated_file_client,
    upload_user,
) -> None:
    other_user = User.objects.create_user(
        username="other-user",
        email="other-user@example.com",
        password=PASSWORD,
    )
    own_record = FileRecord.objects.create(
        filename="own.txt",
        original_filename="own.txt",
        file_path="files/own.txt",
        file_size=3,
        mime_type="text/plain",
        uploaded_by=upload_user,
    )
    FileRecord.objects.create(
        filename="other.txt",
        original_filename="other.txt",
        file_path="files/other.txt",
        file_size=5,
        mime_type="text/plain",
        uploaded_by=other_user,
    )

    response = authenticated_file_client.get(reverse("file_api:list"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert [item["id"] for item in payload["data"]] == [str(own_record.pk)]


@pytest.mark.django_db
def test_storage_is_cleaned_if_database_persistence_fails(
    upload_user,
    temporary_media_root,
) -> None:
    upload = SimpleUploadedFile("cleanup.txt", b"content that must be cleaned")

    with patch.object(
        FileRecord.objects, "create", side_effect=RuntimeError("db failed")
    ):
        with pytest.raises(RuntimeError, match="db failed"):
            FileStorageService().create_file(uploaded_file=upload, owner=upload_user)

    assert FileRecord.objects.count() == 0
    assert list(temporary_media_root.rglob("*")) == [temporary_media_root / "files"]


@pytest.mark.django_db
def test_cleanup_failure_preserves_original_persistence_error(
    upload_user,
    temporary_media_root,
    caplog,
) -> None:
    upload = SimpleUploadedFile("cleanup.txt", b"orphaned only in this isolated test")

    with (
        patch.object(
            FileRecord.objects, "create", side_effect=RuntimeError("db failed")
        ),
        patch(
            "files.services.default_storage.delete",
            side_effect=OSError("delete failed"),
        ),
        pytest.raises(RuntimeError, match="db failed"),
    ):
        FileStorageService().create_file(uploaded_file=upload, owner=upload_user)

    assert "orphan_cleanup_failure" in caplog.text
    assert len(list(temporary_media_root.glob("files/*"))) == 1
