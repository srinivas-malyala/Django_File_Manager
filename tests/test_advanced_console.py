"""Phase 7 advanced console and safe preview tests."""

from urllib.parse import parse_qs

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from files.models import FileRecord
from files.previews import FilePreviewService
from files.services import FileStorageService

User = get_user_model()
PASSWORD = "Advanced-Console-Passphrase-42"


@pytest.fixture
def advanced_user(db):
    return User.objects.create_user(
        username="advanced-user",
        email="advanced-user@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def advanced_other_user(db):
    return User.objects.create_user(
        username="advanced-other",
        email="advanced-other@example.com",
        password=PASSWORD,
    )


@pytest.fixture
def advanced_client(advanced_user) -> Client:
    client = Client()
    client.force_login(advanced_user)
    return client


def create_record(owner, name: str, *, description: str = "", size: int = 10):
    return FileRecord.objects.create(
        filename=f"generated-{name}",
        original_filename=name,
        file_path=f"files/generated-{name}",
        file_size=size,
        mime_type="text/plain",
        description=description,
        uploaded_by=owner,
    )


def create_stored_file(owner, name: str, content: bytes) -> FileRecord:
    return FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile(name, content),
        owner=owner,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route_name",
    [
        "user_console:file_advanced",
        "user_console:file_search",
        "user_console:file_preview",
        "user_console:file_preview_content",
    ],
)
def test_phase_seven_views_require_login(route_name: str) -> None:
    args = (
        []
        if route_name in {"user_console:file_advanced", "user_console:file_search"}
        else ["00000000-0000-0000-0000-000000000001"]
    )
    url = reverse(route_name, args=args)

    response = Client().get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


@pytest.mark.django_db
def test_advanced_search_combines_filters_and_remains_owner_scoped(
    advanced_client,
    advanced_user,
    advanced_other_user,
) -> None:
    create_record(
        advanced_user,
        "Alpha Report.PDF",
        description="Quarterly document",
        size=100,
    )
    create_record(advanced_user, "notes.txt", description="Quarterly notes", size=50)
    create_record(
        advanced_other_user,
        "Foreign Report.PDF",
        description="Quarterly document",
        size=100,
    )

    response = advanced_client.get(
        reverse("user_console:file_advanced"),
        {"search": "quarterly", "file_type": "pdf", "sort": "name"},
    )

    assert response.status_code == 200
    assert [item.original_filename for item in response.context["files"]] == [
        "Alpha Report.PDF"
    ]
    assert b"Foreign Report.PDF" not in response.content


@pytest.mark.django_db
def test_search_alias_uses_advanced_search_workflow(
    advanced_client,
    advanced_user,
) -> None:
    create_record(advanced_user, "matching.txt", description="needle")
    create_record(advanced_user, "other.txt", description="haystack")

    response = advanced_client.get(
        reverse("user_console:file_search"),
        {"search": "needle"},
    )

    assert response.status_code == 200
    assert [item.original_filename for item in response.context["files"]] == [
        "matching.txt"
    ]


@pytest.mark.django_db
def test_advanced_filters_survive_grid_toggle_and_pagination(
    advanced_client,
    advanced_user,
) -> None:
    for index in range(21):
        create_record(
            advanced_user,
            f"report-{index:02}.txt",
            description="retained filter",
        )

    response = advanced_client.get(
        reverse("user_console:file_advanced"),
        {
            "search": "report",
            "file_type": "txt",
            "sort": "name",
            "page_size": "20",
            "view": "grid",
        },
    )

    assert response.status_code == 200
    assert response.context["view_mode"] == "grid"
    assert response.context["is_paginated"] is True
    grid_query = parse_qs(response.context["grid_view_query"])
    pagination_query = parse_qs(response.context["pagination_query"])
    assert grid_query == {
        "search": ["report"],
        "file_type": ["txt"],
        "sort": ["name"],
        "page_size": ["20"],
        "view": ["grid"],
    }
    assert pagination_query["search"] == ["report"]
    assert pagination_query["file_type"] == ["txt"]
    assert pagination_query["view"] == ["grid"]
    assert b"row-cols-1" in response.content


@pytest.mark.django_db
def test_basic_file_list_supports_list_and_grid_modes(
    advanced_client,
    advanced_user,
) -> None:
    create_record(advanced_user, "display.txt")

    list_response = advanced_client.get(
        reverse("user_console:file_list"), {"view": "list"}
    )
    grid_response = advanced_client.get(
        reverse("user_console:file_list"), {"view": "grid"}
    )

    assert list_response.status_code == 200
    assert b"table-responsive" in list_response.content
    assert grid_response.status_code == 200
    assert grid_response.context["view_mode"] == "grid"
    assert b"row-cols-1" in grid_response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "expected_error"),
    [
        ({"sort": "uploaded_by"}, b"Select a valid choice"),
        ({"page": "not-a-number"}, b"A positive integer is required"),
        ({"unknown": "value"}, b"Unsupported query parameter"),
        ({"view": "unsafe"}, b"Unsupported view mode"),
        (
            {"date_from": "2026-02-01", "date_to": "2026-01-01"},
            b"End date must be on or after start date",
        ),
    ],
)
def test_invalid_advanced_query_is_rendered_safely(
    advanced_client,
    query,
    expected_error,
) -> None:
    response = advanced_client.get(reverse("user_console:file_advanced"), query)

    assert response.status_code == 200
    assert expected_error in response.content
    assert list(response.context["files"]) == []


@pytest.mark.django_db
def test_text_preview_autoescapes_uploaded_markup(
    advanced_client,
    advanced_user,
    temporary_media_root,
) -> None:
    record = create_stored_file(
        advanced_user,
        "unsafe.txt",
        b"<script>alert('preview-xss')</script>\nplain text",
    )

    response = advanced_client.get(
        reverse("user_console:file_preview", args=[record.pk])
    )

    assert response.status_code == 200
    assert response.context["preview_kind"] == "text"
    assert b"&lt;script&gt;" in response.content
    assert b"<script>alert" not in response.content


@pytest.mark.django_db
def test_csv_preview_uses_safe_text_rendering(
    advanced_client,
    advanced_user,
    temporary_media_root,
) -> None:
    record = create_stored_file(
        advanced_user,
        "data.csv",
        b"name,value\n<script>,danger\n",
    )

    response = advanced_client.get(
        reverse("user_console:file_preview", args=[record.pk])
    )

    assert response.status_code == 200
    assert response.context["preview_kind"] == "text"
    assert b"&lt;script&gt;" in response.content


@pytest.mark.django_db
def test_text_preview_is_bounded_and_reports_truncation(
    advanced_client,
    advanced_user,
    temporary_media_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(FilePreviewService, "MAX_TEXT_PREVIEW_BYTES", 5)
    record = create_stored_file(advanced_user, "long.txt", b"123456789")

    response = advanced_client.get(
        reverse("user_console:file_preview", args=[record.pk])
    )

    assert response.status_code == 200
    assert response.context["preview_content"] == "12345"
    assert response.context["preview_truncated"] is True
    assert b"Preview truncated" in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filename", "content", "kind", "content_type"),
    [
        ("image.png", b"not-a-real-image-but-streamed", "image", "image/png"),
        ("document.pdf", b"%PDF-1.7\npreview", "pdf", "application/pdf"),
    ],
)
def test_image_and_pdf_previews_use_authenticated_allowlisted_inline_content(
    advanced_client,
    advanced_user,
    temporary_media_root,
    filename,
    content,
    kind,
    content_type,
) -> None:
    record = create_stored_file(advanced_user, filename, content)

    page_response = advanced_client.get(
        reverse("user_console:file_preview", args=[record.pk])
    )
    content_response = advanced_client.get(
        reverse("user_console:file_preview_content", args=[record.pk])
    )

    assert page_response.status_code == 200
    assert page_response.context["preview_kind"] == kind
    assert content_response.status_code == 200
    assert b"".join(content_response.streaming_content) == content
    assert content_response["Content-Type"] == content_type
    assert content_response["Content-Disposition"].startswith("inline;")
    assert content_response["X-Content-Type-Options"] == "nosniff"
    assert content_response["Cache-Control"] == "private, no-store"
    assert content_response["Content-Security-Policy"] == "sandbox; default-src 'none'"


@pytest.mark.django_db
def test_unsupported_format_shows_download_message_and_cannot_stream_inline(
    advanced_client,
    advanced_user,
    temporary_media_root,
) -> None:
    record = create_stored_file(advanced_user, "document.docx", b"office bytes")

    page_response = advanced_client.get(
        reverse("user_console:file_preview", args=[record.pk])
    )
    content_response = advanced_client.get(
        reverse("user_console:file_preview_content", args=[record.pk])
    )

    assert page_response.status_code == 200
    assert page_response.context["preview_kind"] == "unsupported"
    assert b"Preview unavailable for this file type" in page_response.content
    assert content_response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("route_name", ["file_preview", "file_preview_content"])
def test_preview_routes_are_owner_scoped(
    advanced_client,
    advanced_other_user,
    temporary_media_root,
    route_name,
) -> None:
    foreign_record = create_stored_file(
        advanced_other_user,
        "foreign.png",
        b"private image",
    )

    response = advanced_client.get(
        reverse(f"user_console:{route_name}", args=[foreign_record.pk])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_missing_text_content_returns_404(
    advanced_client,
    advanced_user,
    temporary_media_root,
) -> None:
    record = create_stored_file(advanced_user, "missing.txt", b"will disappear")
    (temporary_media_root / record.file_path).unlink()

    response = advanced_client.get(
        reverse("user_console:file_preview", args=[record.pk])
    )

    assert response.status_code == 404
