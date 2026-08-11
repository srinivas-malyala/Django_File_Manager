"""Phase 11 health, discovery, observability, and administration tests."""

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from files.admin import FileRecordAdmin
from files.models import FileRecord
from files.services import FileStorageService

User = get_user_model()
PASSWORD = "Phase-11-Secure-Passphrase-42"


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="regular-observer",
        email="regular-observer@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def application_admin(db):
    return User.objects.create_user(
        username="application-admin",
        email="application-admin@example.com",
        password=PASSWORD,
        is_admin=True,
    )


def test_api_discovery_is_public_and_uses_reversible_routes(client) -> None:
    response = client.get(reverse("core_api:discovery"))

    assert response.status_code == 200
    assert response.json() == {
        "health": reverse("core_api:health"),
        "statistics": reverse("core_api:statistics"),
        "files": reverse("file_api:list"),
        "upload": reverse("file_api:upload"),
        "my_files": reverse("file_api:my_files"),
        "token": reverse("account_api:token_obtain_pair"),
    }


@pytest.mark.django_db
@override_settings(APPLICATION_VERSION="11.2.3")
def test_health_check_reports_dependencies_version_and_timing(client, caplog) -> None:
    response = client.get(reverse("core_api:health"))

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["version"] == "11.2.3"
    assert response.json()["checks"] == {
        "database": "connected",
        "file_storage": "accessible",
    }
    assert response.json()["timestamp"]
    assert response["Cache-Control"] == "no-store"
    assert "health_check status=healthy duration_ms=" in caplog.text


@pytest.mark.django_db
def test_health_check_handles_database_failure_without_leaking_details(
    client, caplog
) -> None:
    secret = "/internal/database/path password=do-not-expose"
    with patch("core.api_views.connection.cursor", side_effect=OSError(secret)):
        response = client.get(reverse("core_api:health"))

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert response.json()["checks"] == {
        "database": "unavailable",
        "file_storage": "accessible",
    }
    assert secret not in response.content.decode()
    assert secret not in caplog.text
    assert "dependency=database error_type=OSError" in caplog.text


@pytest.mark.django_db
def test_health_check_handles_storage_failure_without_leaking_details(
    client, caplog
) -> None:
    secret = "/private/media/root access-key=do-not-expose"
    with patch(
        "core.api_views.default_storage.exists",
        side_effect=PermissionError(secret),
    ):
        response = client.get(reverse("core_api:health"))

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "database": "connected",
        "file_storage": "unavailable",
    }
    assert secret not in response.content.decode()
    assert secret not in caplog.text
    assert "dependency=file_storage error_type=PermissionError" in caplog.text


@pytest.mark.django_db
def test_health_check_reports_all_dependency_failures(client) -> None:
    with (
        patch("core.api_views.connection.cursor", side_effect=OSError),
        patch("core.api_views.default_storage.exists", side_effect=OSError),
    ):
        response = client.get(reverse("core_api:health"))

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "database": "unavailable",
        "file_storage": "unavailable",
    }


@pytest.mark.django_db
def test_statistics_require_authentication() -> None:
    response = APIClient().get(reverse("core_api:statistics"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_statistics_reject_regular_user_and_log_identifier(
    regular_user, caplog
) -> None:
    api_client = APIClient()
    api_client.force_authenticate(user=regular_user)

    response = api_client.get(reverse("core_api:statistics"))

    assert response.status_code == 403
    assert f"admin_statistics_access_rejection user_id={regular_user.pk}" in caplog.text


@pytest.mark.django_db
def test_application_admin_receives_basic_aggregate_statistics(
    application_admin,
    regular_user,
    temporary_media_root,
    caplog,
) -> None:
    inactive_user = User.objects.create_user(
        username="inactive-observer",
        email="inactive-observer@example.com",
        password=PASSWORD,
        is_active=False,
    )
    FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("first.txt", b"123"),
        owner=regular_user,
    )
    FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("second.txt", b"12345"),
        owner=inactive_user,
    )
    api_client = APIClient()
    api_client.force_authenticate(user=application_admin)

    response = api_client.get(reverse("core_api:statistics"))

    assert response.status_code == 200
    assert response.json()["data"] == {
        "total_users": 3,
        "active_users": 2,
        "total_files": 2,
        "total_storage": 8,
    }
    assert response["Cache-Control"] == "private, no-store"
    assert "file_path" not in response.content.decode()
    assert "aggregate_statistics_view user_id=" in caplog.text


@pytest.mark.django_db
def test_superuser_can_access_statistics(db) -> None:
    superuser = User.objects.create_superuser(
        username="statistics-superuser",
        email="statistics-superuser@example.com",
        password=PASSWORD,
    )
    api_client = APIClient()
    api_client.force_authenticate(user=superuser)

    response = api_client.get(reverse("core_api:statistics"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_file_metadata_admin_is_registered_read_only(application_admin) -> None:
    model_admin = admin.site._registry[FileRecord]
    request = RequestFactory().get("/admin/files/filerecord/")
    request.user = application_admin
    application_admin.is_staff = True

    assert isinstance(model_admin, FileRecordAdmin)
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_delete_permission(request) is False
    assert set(model_admin.readonly_fields) == {
        "id",
        "filename",
        "original_filename",
        "file_path",
        "file_size",
        "mime_type",
        "description",
        "upload_date",
        "uploaded_by",
    }


@pytest.mark.django_db
def test_download_and_search_emit_identifier_only_operational_logs(
    regular_user,
    temporary_media_root,
    caplog,
) -> None:
    record = FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("operational.txt", b"content"),
        owner=regular_user,
    )
    api_client = APIClient()
    api_client.force_authenticate(user=regular_user)

    search_response = api_client.get(reverse("file_api:my_files"))
    download_response = api_client.get(reverse("file_api:download", args=[record.pk]))
    b"".join(download_response.streaming_content)

    assert search_response.status_code == 200
    assert download_response.status_code == 200
    assert f"file_search user_id={regular_user.pk}" in caplog.text
    assert (
        f"download_started user_id={regular_user.pk} file_id={record.pk}" in caplog.text
    )
    assert str(temporary_media_root) not in caplog.text
