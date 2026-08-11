"""Phase 6 basic web console tests."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from files.models import FileRecord
from files.services import FileStorageService

User = get_user_model()
PASSWORD = "Console-Passphrase-42"


@pytest.fixture
def console_user(db):
    return User.objects.create_user(
        username="console-user",
        email="console-user@example.com",
        password=PASSWORD,
        first_name="Console",
        last_name="User",
    )


@pytest.fixture
def other_console_user(db):
    return User.objects.create_user(
        username="other-console-user",
        email="other-console-user@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def console_client(console_user) -> Client:
    client = Client()
    client.force_login(console_user)
    return client


@pytest.fixture
def console_file(console_user, temporary_media_root) -> FileRecord:
    return FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("console-document.txt", b"console content"),
        owner=console_user,
        description="Console document",
    )


def create_metadata_record(owner, name: str, size: int = 10) -> FileRecord:
    return FileRecord.objects.create(
        filename=f"generated-{name}",
        original_filename=name,
        file_path=f"files/generated-{name}",
        file_size=size,
        mime_type="text/plain",
        uploaded_by=owner,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route_name", "method"),
    [
        ("user_console:dashboard", "get"),
        ("user_console:profile", "get"),
        ("user_console:file_list", "get"),
        ("user_console:file_upload", "get"),
        ("user_console:file_detail", "get"),
        ("user_console:file_download", "get"),
        ("user_console:file_delete", "post"),
    ],
)
def test_console_views_require_login(route_name: str, method: str) -> None:
    client = Client()
    args = [uuid4()] if route_name.rsplit(":", 1)[-1].startswith("file_d") else []
    url = reverse(route_name, args=args)

    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


@pytest.mark.django_db
def test_dashboard_shows_owner_statistics_recent_files_and_quick_actions(
    console_client,
    console_user,
    other_console_user,
) -> None:
    own_record = create_metadata_record(console_user, "own.txt", size=2048)
    create_metadata_record(other_console_user, "private.txt", size=4096)

    response = console_client.get(reverse("user_console:dashboard"))

    assert response.status_code == 200
    assert response.context["total_files"] == 1
    assert response.context["total_storage"] == 2048
    assert list(response.context["recent_files"]) == [own_record]
    assert b"own.txt" in response.content
    assert b"private.txt" not in response.content
    assert b"Upload File" in response.content
    assert b"Browse Files" in response.content
    assert b"Search Files" in response.content


@pytest.mark.django_db
def test_file_list_is_owner_scoped_and_paginated(
    console_client,
    console_user,
    other_console_user,
) -> None:
    for index in range(21):
        create_metadata_record(console_user, f"owner-{index:02}.txt")
    create_metadata_record(other_console_user, "foreign.txt")

    response = console_client.get(reverse("user_console:file_list"), {"page": 2})

    assert response.status_code == 200
    assert response.context["is_paginated"] is True
    assert len(response.context["files"]) == 1
    assert response.context["files"][0].uploaded_by == console_user
    assert b"foreign.txt" not in response.content


@pytest.mark.django_db
def test_browser_upload_uses_shared_validation_and_storage(
    console_client,
    console_user,
    temporary_media_root,
) -> None:
    upload = SimpleUploadedFile("Browser Report.PDF", b"%PDF-1.7\nconsole upload")

    response = console_client.post(
        reverse("user_console:file_upload"),
        {"file": upload, "description": "Uploaded in browser"},
    )

    record = FileRecord.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("user_console:file_detail", args=[record.pk])
    assert record.uploaded_by == console_user
    assert record.original_filename == "Browser_Report.PDF"
    assert record.description == "Uploaded in browser"
    assert (temporary_media_root / record.file_path).is_file()


@pytest.mark.django_db
def test_browser_upload_displays_validation_errors_without_writing(
    console_client,
    temporary_media_root,
) -> None:
    upload = SimpleUploadedFile("malware.exe", b"invalid")

    response = console_client.post(
        reverse("user_console:file_upload"),
        {"file": upload},
    )

    assert response.status_code == 200
    assert b"This file extension is not allowed" in response.content
    assert FileRecord.objects.count() == 0
    assert list(temporary_media_root.rglob("*")) == []


@pytest.mark.django_db
def test_owner_can_view_file_detail_without_javascript(
    console_client,
    console_file,
) -> None:
    response = console_client.get(
        reverse("user_console:file_detail", args=[console_file.pk])
    )

    assert response.status_code == 200
    assert response.context["file"] == console_file
    assert console_file.original_filename.encode() in response.content
    assert b'method="post"' in response.content
    assert b"csrfmiddlewaretoken" in response.content
    assert b"<script" not in response.content


@pytest.mark.django_db
def test_console_file_detail_is_owner_scoped(
    console_client,
    other_console_user,
) -> None:
    foreign_record = create_metadata_record(other_console_user, "foreign.txt")

    response = console_client.get(
        reverse("user_console:file_detail", args=[foreign_record.pk])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_owner_can_stream_console_download(console_client, console_file) -> None:
    response = console_client.get(
        reverse("user_console:file_download", args=[console_file.pk])
    )

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"console content"
    assert "console-document.txt" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
def test_console_download_is_owner_scoped(
    console_client,
    other_console_user,
) -> None:
    foreign_record = create_metadata_record(other_console_user, "foreign.txt")

    response = console_client.get(
        reverse("user_console:file_download", args=[foreign_record.pk])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_console_delete_removes_record_and_content(
    console_client,
    console_file,
    temporary_media_root,
) -> None:
    record_id = console_file.pk
    physical_path = temporary_media_root / console_file.file_path

    response = console_client.post(
        reverse("user_console:file_delete", args=[record_id])
    )

    assert response.status_code == 302
    assert response.url == reverse("user_console:file_list")
    assert FileRecord.objects.filter(pk=record_id).exists() is False
    assert physical_path.exists() is False


@pytest.mark.django_db
def test_console_delete_is_post_only_and_csrf_protected(
    console_user,
    console_file,
) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(console_user)
    url = reverse("user_console:file_delete", args=[console_file.pk])

    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 403
    assert FileRecord.objects.filter(pk=console_file.pk).exists() is True


@pytest.mark.django_db
def test_console_delete_is_owner_scoped(
    console_client,
    other_console_user,
) -> None:
    foreign_record = create_metadata_record(other_console_user, "foreign.txt")

    response = console_client.post(
        reverse("user_console:file_delete", args=[foreign_record.pk])
    )

    assert response.status_code == 404
    assert FileRecord.objects.filter(pk=foreign_record.pk).exists() is True


@pytest.mark.django_db
def test_console_profile_and_navigation_are_available(
    console_client,
    console_user,
) -> None:
    response = console_client.get(reverse("user_console:profile"))

    assert response.status_code == 200
    assert console_user.username.encode() in response.content
    assert console_user.email.encode() in response.content
    assert reverse("user_console:dashboard").encode() in response.content
    assert reverse("user_console:file_list").encode() in response.content
    assert reverse("user_console:profile").encode() in response.content
    assert reverse("accounts:logout").encode() in response.content
