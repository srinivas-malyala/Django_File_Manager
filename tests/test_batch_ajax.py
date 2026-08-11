"""Phase 8 batch operation and authenticated AJAX tests."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from files.batch import BatchFileService, BatchOperationError
from files.models import FileRecord
from files.services import FileStorageOperationError, FileStorageService

User = get_user_model()
PASSWORD = "Batch-Ajax-Passphrase-42"


@pytest.fixture
def batch_user(db):
    return User.objects.create_user(
        username="batch-user",
        email="batch-user@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def batch_other_user(db):
    return User.objects.create_user(
        username="batch-other",
        email="batch-other@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def batch_client(batch_user) -> Client:
    client = Client()
    client.force_login(batch_user)
    return client


def stored_file(owner, name: str, content: bytes) -> FileRecord:
    return FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile(name, content),
        owner=owner,
    )


def metadata_file(owner, name: str, size: int = 10) -> FileRecord:
    return FileRecord.objects.create(
        filename=f"generated-{name}",
        original_filename=name,
        file_path=f"files/generated-{name}",
        file_size=size,
        mime_type="text/plain",
        description="searchable batch document",
        uploaded_by=owner,
    )


@pytest.mark.django_db
def test_batch_view_requires_login() -> None:
    response = Client().post(reverse("user_console:file_batch"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


@pytest.mark.django_db
def test_batch_view_is_csrf_protected(batch_user) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(batch_user)

    response = client.post(reverse("user_console:file_batch"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_batch_delete_removes_all_selected_owner_files(
    batch_client,
    batch_user,
    temporary_media_root,
) -> None:
    first = stored_file(batch_user, "first.txt", b"first")
    second = stored_file(batch_user, "second.txt", b"second")
    physical_paths = [
        temporary_media_root / first.file_path,
        temporary_media_root / second.file_path,
    ]

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {"action": "delete", "file_ids": [str(first.pk), str(second.pk)]},
    )

    assert response.status_code == 302
    assert response.url == reverse("user_console:file_list")
    assert FileRecord.objects.count() == 0
    assert all(not path.exists() for path in physical_paths)


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["delete", "download"])
def test_mixed_owner_and_foreign_batch_is_rejected_before_any_operation(
    batch_client,
    batch_user,
    batch_other_user,
    temporary_media_root,
    action,
) -> None:
    own_record = stored_file(batch_user, "own.txt", b"own")
    foreign_record = stored_file(batch_other_user, "foreign.txt", b"foreign")

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {
            "action": action,
            "file_ids": [str(own_record.pk), str(foreign_record.pk)],
        },
    )

    assert response.status_code == 400
    assert FileRecord.objects.filter(pk=own_record.pk).exists() is True
    assert FileRecord.objects.filter(pk=foreign_record.pk).exists() is True
    assert (temporary_media_root / own_record.file_path).is_file()
    assert (temporary_media_root / foreign_record.file_path).is_file()


@pytest.mark.django_db
def test_batch_collection_is_bounded_before_processing(
    batch_client, batch_user
) -> None:
    records = [metadata_file(batch_user, f"file-{index}.txt") for index in range(101)]

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {"action": "delete", "file_ids": [str(record.pk) for record in records]},
    )

    assert response.status_code == 400
    assert FileRecord.objects.count() == 101


@pytest.mark.django_db
def test_batch_download_zip_uses_sanitized_unique_names_without_internal_paths(
    batch_client,
    batch_user,
    temporary_media_root,
) -> None:
    first = stored_file(batch_user, "duplicate.txt", b"first content")
    second = stored_file(batch_user, "duplicate.txt", b"second content")
    second.original_filename = r"..\..\duplicate.txt"
    second.save(update_fields=["original_filename"])

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {"action": "download", "file_ids": [str(first.pk), str(second.pk)]},
    )

    assert response.status_code == 200
    archive_bytes = b"".join(response.streaming_content)
    with ZipFile(BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == ["duplicate.txt", "duplicate (2).txt"]
        assert archive.read("duplicate.txt") == b"first content"
        assert archive.read("duplicate (2).txt") == b"second content"
        assert all("/" not in name and "\\" not in name for name in archive.namelist())
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Cache-Control"] == "private, no-store"
    assert first.file_path not in archive_bytes.decode("latin-1")


@pytest.mark.django_db
def test_batch_download_enforces_aggregate_size_limit(
    batch_client,
    batch_user,
    temporary_media_root,
    monkeypatch,
) -> None:
    record = stored_file(batch_user, "large.txt", b"12345")
    monkeypatch.setattr(BatchFileService, "MAX_BATCH_DOWNLOAD_BYTES", 4)

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {"action": "download", "file_ids": [str(record.pk)]},
    )

    assert response.status_code == 400
    assert b"exceed the batch download limit" in response.content


@pytest.mark.django_db
def test_batch_operation_rejects_missing_physical_content(
    batch_client,
    batch_user,
    temporary_media_root,
) -> None:
    record = stored_file(batch_user, "missing.txt", b"gone")
    (temporary_media_root / record.file_path).unlink()

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {"action": "download", "file_ids": [str(record.pk)]},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_batch_service_rejects_empty_and_oversized_direct_collections(
    batch_user,
) -> None:
    record = metadata_file(batch_user, "bounded.txt")

    with pytest.raises(BatchOperationError, match="at least one"):
        BatchFileService.validate_records([])
    with pytest.raises(BatchOperationError, match="no more than 100"):
        BatchFileService.validate_records([record] * 101)


@pytest.mark.django_db
def test_batch_storage_availability_failure_is_wrapped_safely(
    batch_user,
) -> None:
    record = metadata_file(batch_user, "storage.txt")

    with (
        patch("files.batch.default_storage.exists", side_effect=OSError("backend")),
        pytest.raises(FileStorageOperationError, match="availability"),
    ):
        BatchFileService.ensure_content_exists([record])


@pytest.mark.django_db
def test_zip_builder_closes_partial_archive_when_file_open_fails(
    batch_user,
    temporary_media_root,
) -> None:
    record = stored_file(batch_user, "failure.txt", b"content")

    with (
        patch(
            "files.batch.FileStorageService.open_file",
            side_effect=FileStorageOperationError("open failed"),
        ),
        pytest.raises(FileStorageOperationError, match="open failed"),
    ):
        BatchFileService.build_zip([record])


@pytest.mark.django_db
def test_zip_builder_falls_back_when_metadata_filename_is_invalid(
    batch_client,
    batch_user,
    temporary_media_root,
) -> None:
    record = stored_file(batch_user, "fallback.txt", b"fallback content")
    record.original_filename = "."
    record.save(update_fields=["original_filename"])

    response = batch_client.post(
        reverse("user_console:file_batch"),
        {"action": "download", "file_ids": [str(record.pk)]},
    )

    assert response.status_code == 200
    with ZipFile(BytesIO(b"".join(response.streaming_content))) as archive:
        assert archive.namelist() == [f"{record.pk}.unknown"]
        assert archive.read(archive.namelist()[0]) == b"fallback content"


@pytest.mark.django_db
def test_batch_view_returns_safe_error_for_storage_failure(
    batch_client,
    batch_user,
) -> None:
    record = metadata_file(batch_user, "failure.txt")

    with patch(
        "user_console.batch_views.BatchFileService.build_zip",
        side_effect=FileStorageOperationError("secret backend detail"),
    ):
        response = batch_client.post(
            reverse("user_console:file_batch"),
            {"action": "download", "file_ids": [str(record.pk)]},
        )

    assert response.status_code == 500
    assert response.content == b"Batch operation could not be completed."
    assert b"secret" not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route_name",
    [
        "user_console:ajax_file_stats",
        "user_console:ajax_recent_files",
        "user_console:ajax_search",
    ],
)
def test_ajax_views_return_json_401_for_anonymous_users(route_name: str) -> None:
    response = Client().get(reverse(route_name))

    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["message"] == "Authentication required"


@pytest.mark.django_db
def test_ajax_statistics_are_owner_scoped(
    batch_client,
    batch_user,
    batch_other_user,
) -> None:
    metadata_file(batch_user, "one.txt", size=100)
    metadata_file(batch_user, "two.txt", size=200)
    metadata_file(batch_other_user, "foreign.txt", size=1000)

    response = batch_client.get(reverse("user_console:ajax_file_stats"))

    assert response.status_code == 200
    assert response.json()["data"] == {"total_files": 2, "total_storage": 300}


@pytest.mark.django_db
def test_ajax_recent_files_are_owner_scoped_and_bounded(
    batch_client,
    batch_user,
    batch_other_user,
) -> None:
    for index in range(25):
        metadata_file(batch_user, f"owner-{index:02}.txt")
    metadata_file(batch_other_user, "foreign.txt")

    response = batch_client.get(
        reverse("user_console:ajax_recent_files"),
        {"limit": 100},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["limit"] == 20
    assert len(data["results"]) == 20
    assert all(item["original_filename"] != "foreign.txt" for item in data["results"])
    assert all("file_path" not in item for item in data["results"])


@pytest.mark.django_db
@pytest.mark.parametrize("limit", ["invalid", "0", "-1"])
def test_ajax_recent_files_reject_invalid_limit(batch_client, limit) -> None:
    response = batch_client.get(
        reverse("user_console:ajax_recent_files"),
        {"limit": limit},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid limit"


@pytest.mark.django_db
def test_ajax_search_is_owner_scoped_paginated_and_bounded(
    batch_client,
    batch_user,
    batch_other_user,
) -> None:
    for index in range(25):
        metadata_file(batch_user, f"matching-{index:02}.txt")
    metadata_file(batch_other_user, "matching-foreign.txt")

    response = batch_client.get(
        reverse("user_console:ajax_search"),
        {"search": "matching", "page_size": 100, "sort": "name"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 25
    assert data["page_size"] == 20
    assert len(data["results"]) == 20
    assert all(
        item["original_filename"] != "matching-foreign.txt" for item in data["results"]
    )
    assert all("file_path" not in item for item in data["results"])
    assert all(
        item["detail_url"].startswith("/console/files/") for item in data["results"]
    )


@pytest.mark.django_db
def test_ajax_search_rejects_invalid_query_and_page(batch_client, batch_user) -> None:
    metadata_file(batch_user, "one.txt")

    invalid_response = batch_client.get(
        reverse("user_console:ajax_search"),
        {"sort": "uploaded_by"},
    )
    missing_page_response = batch_client.get(
        reverse("user_console:ajax_search"),
        {"page": 99},
    )

    assert invalid_response.status_code == 400
    assert missing_page_response.status_code == 404


@pytest.mark.django_db
def test_advanced_console_exposes_progressive_live_search_and_batch_form(
    batch_client,
) -> None:
    response = batch_client.get(reverse("user_console:file_advanced"))

    assert response.status_code == 200
    assert reverse("user_console:ajax_search").encode() in response.content
    assert reverse("user_console:file_batch").encode() in response.content
    assert b"file-search.js" in response.content
    assert b"csrfmiddlewaretoken" in response.content


def test_live_search_script_is_debounced_and_uses_safe_dom_rendering() -> None:
    script_path = Path(__file__).parent.parent / "static/console/js/file-search.js"
    script = script_path.read_text()

    assert "setTimeout(search, 300)" in script
    assert "textContent = item.original_filename" in script
    assert "innerHTML" not in script
    assert 'credentials: "same-origin"' in script
