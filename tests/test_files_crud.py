"""Phase 4 file lifecycle and object-authorization tests."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from files.models import FileRecord
from files.services import FileStorageService

User = get_user_model()
PASSWORD = "Lifecycle-Passphrase-42"


@pytest.fixture
def lifecycle_users(db):
    owner = User.objects.create_user(
        username="lifecycle-owner",
        email="lifecycle-owner@example.com",
        password=PASSWORD,
    )
    other = User.objects.create_user(
        username="lifecycle-other",
        email="lifecycle-other@example.com",
        password=PASSWORD,
    )
    return owner, other


@pytest.fixture
def lifecycle_records(lifecycle_users, temporary_media_root):
    owner, other = lifecycle_users
    own_content = b"owner file content"
    other_content = b"other user private content"
    own_record = FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("owner.txt", own_content),
        owner=owner,
        description="Original description",
    )
    other_record = FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("other.txt", other_content),
        owner=other,
        description="Other description",
    )
    return {
        "owner": owner,
        "other": other,
        "own_record": own_record,
        "other_record": other_record,
        "own_content": own_content,
        "other_content": other_content,
        "media_root": temporary_media_root,
    }


@pytest.fixture
def lifecycle_client(lifecycle_records) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=lifecycle_records["owner"])
    return client


@pytest.mark.django_db
def test_owner_can_retrieve_own_file(lifecycle_client, lifecycle_records) -> None:
    record = lifecycle_records["own_record"]

    response = lifecycle_client.get(reverse("file_api:detail", args=[record.pk]))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["id"] == str(record.pk)
    assert payload["data"]["description"] == "Original description"
    assert "file_path" not in payload["data"]
    assert "uploaded_by" not in payload["data"]


@pytest.mark.django_db
def test_user_cannot_view_another_users_file(
    lifecycle_client, lifecycle_records
) -> None:
    other_record = lifecycle_records["other_record"]

    response = lifecycle_client.get(reverse("file_api:detail", args=[other_record.pk]))

    assert response.status_code == 404
    assert response.json()["message"] == "File not found"


@pytest.mark.django_db
def test_owner_can_update_description_only(lifecycle_client, lifecycle_records) -> None:
    record = lifecycle_records["own_record"]

    response = lifecycle_client.put(
        reverse("file_api:detail", args=[record.pk]),
        {"description": "Updated description"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["description"] == "Updated description"
    record.refresh_from_db()
    assert record.description == "Updated description"


@pytest.mark.django_db
def test_update_rejects_immutable_fields(lifecycle_client, lifecycle_records) -> None:
    record = lifecycle_records["own_record"]
    original_filename = record.filename

    response = lifecycle_client.put(
        reverse("file_api:detail", args=[record.pk]),
        {
            "description": "Must not be applied",
            "filename": "attacker-controlled.txt",
            "uploaded_by": lifecycle_records["other"].pk,
        },
        format="json",
    )

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert set(errors) == {"filename", "uploaded_by"}
    record.refresh_from_db()
    assert record.description == "Original description"
    assert record.filename == original_filename
    assert record.uploaded_by == lifecycle_records["owner"]


@pytest.mark.django_db
def test_user_cannot_update_another_users_file(
    lifecycle_client, lifecycle_records
) -> None:
    other_record = lifecycle_records["other_record"]

    response = lifecycle_client.put(
        reverse("file_api:detail", args=[other_record.pk]),
        {"description": "Unauthorized change"},
        format="json",
    )

    assert response.status_code == 404
    other_record.refresh_from_db()
    assert other_record.description == "Other description"


@pytest.mark.django_db
def test_owner_can_stream_download_with_safe_headers(
    lifecycle_client, lifecycle_records
) -> None:
    record = lifecycle_records["own_record"]

    response = lifecycle_client.get(reverse("file_api:download", args=[record.pk]))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == lifecycle_records["own_content"]
    assert response["Content-Type"] == record.mime_type
    assert response["Content-Disposition"].startswith("attachment;")
    assert "owner.txt" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert record.file_path not in str(response.headers)


@pytest.mark.django_db
def test_user_cannot_download_another_users_file(
    lifecycle_client, lifecycle_records
) -> None:
    other_record = lifecycle_records["other_record"]

    response = lifecycle_client.get(
        reverse("file_api:download", args=[other_record.pk])
    )

    assert response.status_code == 404
    assert response.json()["message"] == "File not found"


@pytest.mark.django_db
def test_owner_delete_removes_physical_file_and_database_record(
    lifecycle_client, lifecycle_records
) -> None:
    record = lifecycle_records["own_record"]
    record_id = record.pk
    physical_path = lifecycle_records["media_root"] / record.file_path
    assert physical_path.is_file()

    response = lifecycle_client.delete(reverse("file_api:detail", args=[record_id]))

    assert response.status_code == 200
    assert response.json()["message"] == "File deleted successfully"
    assert FileRecord.objects.filter(pk=record_id).exists() is False
    assert physical_path.exists() is False


@pytest.mark.django_db
def test_user_cannot_delete_another_users_file(
    lifecycle_client, lifecycle_records
) -> None:
    other_record = lifecycle_records["other_record"]
    physical_path = lifecycle_records["media_root"] / other_record.file_path

    response = lifecycle_client.delete(
        reverse("file_api:detail", args=[other_record.pk])
    )

    assert response.status_code == 404
    assert FileRecord.objects.filter(pk=other_record.pk).exists() is True
    assert physical_path.is_file()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["detail", "download"])
def test_anonymous_user_cannot_access_individual_file(
    lifecycle_records,
    operation,
) -> None:
    client = APIClient()
    record = lifecycle_records["own_record"]

    response = client.get(reverse(f"file_api:{operation}", args=[record.pk]))

    assert response.status_code == 401


@pytest.mark.django_db
def test_missing_record_returns_owner_safe_404(lifecycle_client) -> None:
    response = lifecycle_client.get(reverse("file_api:detail", args=[uuid4()]))

    assert response.status_code == 404
    assert response.json()["message"] == "File not found"


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["download", "delete"])
def test_missing_physical_file_returns_404_and_preserves_metadata(
    lifecycle_client,
    lifecycle_records,
    operation,
) -> None:
    record = lifecycle_records["own_record"]
    physical_path = Path(lifecycle_records["media_root"] / record.file_path)
    physical_path.unlink()
    url = (
        reverse("file_api:download", args=[record.pk])
        if operation == "download"
        else reverse("file_api:detail", args=[record.pk])
    )

    response = (
        lifecycle_client.get(url)
        if operation == "download"
        else lifecycle_client.delete(url)
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Stored file content was not found"
    assert FileRecord.objects.filter(pk=record.pk).exists() is True


@pytest.mark.django_db
def test_storage_delete_failure_returns_safe_error_and_preserves_record(
    lifecycle_client,
    lifecycle_records,
) -> None:
    record = lifecycle_records["own_record"]
    physical_path = lifecycle_records["media_root"] / record.file_path

    with patch(
        "files.services.default_storage.delete",
        side_effect=OSError("backend unavailable"),
    ):
        response = lifecycle_client.delete(reverse("file_api:detail", args=[record.pk]))

    assert response.status_code == 500
    assert response.json()["message"] == "File could not be deleted"
    assert "backend unavailable" not in str(response.json())
    assert FileRecord.objects.filter(pk=record.pk).exists() is True
    assert physical_path.is_file()


@pytest.mark.django_db
def test_storage_open_failure_returns_safe_error(
    lifecycle_client,
    lifecycle_records,
) -> None:
    record = lifecycle_records["own_record"]

    with patch(
        "files.services.default_storage.open",
        side_effect=OSError("storage credentials leaked here"),
    ):
        response = lifecycle_client.get(reverse("file_api:download", args=[record.pk]))

    assert response.status_code == 500
    assert response.json()["message"] == "File could not be downloaded"
    assert "credentials" not in str(response.json())


@pytest.mark.django_db
def test_storage_race_that_removes_file_before_open_returns_404(
    lifecycle_client,
    lifecycle_records,
) -> None:
    record = lifecycle_records["own_record"]

    with patch(
        "files.services.default_storage.open",
        side_effect=FileNotFoundError("vanished"),
    ):
        response = lifecycle_client.get(reverse("file_api:download", args=[record.pk]))

    assert response.status_code == 404
    assert response.json()["message"] == "Stored file content was not found"


@pytest.mark.django_db
def test_database_delete_failure_is_logged_and_returns_safe_error(
    lifecycle_client,
    lifecycle_records,
    caplog,
) -> None:
    record = lifecycle_records["own_record"]
    physical_path = lifecycle_records["media_root"] / record.file_path

    with patch(
        "files.services.FileRecord.delete",
        side_effect=RuntimeError("database unavailable"),
    ):
        response = lifecycle_client.delete(reverse("file_api:detail", args=[record.pk]))

    assert response.status_code == 500
    assert response.json()["message"] == "File could not be deleted"
    assert "database unavailable" not in str(response.json())
    assert "metadata_delete_failure_after_storage_delete" in caplog.text
    assert FileRecord.objects.filter(pk=record.pk).exists() is True
    assert physical_path.exists() is False
