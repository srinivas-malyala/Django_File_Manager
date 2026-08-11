"""Phase 10 adversarial security regression tests."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from files.models import FileRecord
from files.services import FileStorageOperationError, FileStorageService
from files.validators import FileValidationError, FileValidator

User = get_user_model()
PASSWORD = "Security-Hardening-Passphrase-42"


@pytest.fixture(autouse=True)
def clear_rate_limit_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def security_user(db):
    return User.objects.create_user(
        username="security-user",
        email="security@example.com",
        password=PASSWORD,
    )


def test_pdf_extension_with_html_content_is_rejected(monkeypatch) -> None:
    detector = type(
        "Detector",
        (),
        {"from_buffer": staticmethod(lambda content, mime: "text/html")},
    )
    monkeypatch.setattr("files.validators.magic", detector)
    upload = SimpleUploadedFile("invoice.pdf", b"<script>alert(1)</script>")

    with pytest.raises(FileValidationError, match="content type is not allowed"):
        FileValidator().validate_file(upload)


def test_pdf_extension_with_non_pdf_content_is_rejected(monkeypatch) -> None:
    detector = type(
        "Detector",
        (),
        {"from_buffer": staticmethod(lambda content, mime: "text/plain")},
    )
    monkeypatch.setattr("files.validators.magic", detector)
    upload = SimpleUploadedFile("invoice.pdf", b"ordinary text")

    with pytest.raises(FileValidationError, match="does not match"):
        FileValidator().validate_file(upload)


@pytest.mark.django_db
@override_settings(SECURITY_RATE_LIMITS={"login": (2, 60)})
def test_login_rate_limit_uses_remote_address_not_forwarded_header(client) -> None:
    url = reverse("accounts:login")
    credentials = {"username": "unknown", "password": "incorrect"}

    assert (
        client.post(url, credentials, HTTP_X_FORWARDED_FOR="198.51.100.1").status_code
        == 200
    )
    assert (
        client.post(url, credentials, HTTP_X_FORWARDED_FOR="198.51.100.2").status_code
        == 200
    )
    response = client.post(
        url,
        credentials,
        HTTP_X_FORWARDED_FOR="198.51.100.3",
    )

    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert b"incorrect" not in response.content


@pytest.mark.django_db
def test_api_search_is_throttled_by_drf(monkeypatch, security_user) -> None:
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "file_search", "2/minute")
    api_client = APIClient()
    api_client.force_authenticate(user=security_user)
    url = reverse("file_api:my_files")

    assert api_client.get(url).status_code == 200
    assert api_client.get(url).status_code == 200
    response = api_client.get(url)

    assert response.status_code == 429
    assert "wait" not in response.json()


@pytest.mark.django_db
def test_dynamic_metadata_is_html_escaped(client, security_user) -> None:
    payload = '<img src=x onerror="alert(1)">'
    record = FileRecord.objects.create(
        filename="internal.txt",
        original_filename=payload,
        file_path="files/internal.txt",
        file_size=1,
        mime_type="text/plain",
        description=payload,
        uploaded_by=security_user,
    )
    client.force_login(security_user)

    response = client.get(reverse("user_console:file_detail", args=[record.pk]))

    assert response.status_code == 200
    assert payload.encode() not in response.content
    assert b"&lt;img" in response.content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_private_media_has_no_unrestricted_url_mapping(client) -> None:
    response = client.get("/media/files/private-secret.txt")

    assert response.status_code == 404
    assert b"private-secret.txt" not in response.content


@pytest.mark.django_db
def test_download_is_private_non_cacheable(
    client, security_user, temporary_media_root
) -> None:
    record = FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("private.txt", b"private content"),
        owner=security_user,
    )
    client.force_login(security_user)

    response = client.get(reverse("user_console:file_download", args=[record.pk]))

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_storage_exception_detail_is_not_logged(security_user, caplog) -> None:
    secret = "database-password=highly-sensitive-value"
    record = FileRecord.objects.create(
        filename="stored.txt",
        original_filename="stored.txt",
        file_path="files/stored.txt",
        file_size=1,
        mime_type="text/plain",
        uploaded_by=security_user,
    )

    with (
        patch("files.services.default_storage.exists", return_value=True),
        patch("files.services.default_storage.open", side_effect=OSError(secret)),
        pytest.raises(FileStorageOperationError),
    ):
        FileStorageService.open_file(record)

    assert "storage_open_failure" in caplog.text
    assert "OSError" in caplog.text
    assert secret not in caplog.text


def test_security_headers_are_added_to_normal_and_error_responses(client) -> None:
    normal_response = client.get(reverse("core:index"))
    missing_response = client.get("/missing-security-header-check/")

    for response in (normal_response, missing_response):
        assert "default-src 'self'" in response["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
        assert response["Permissions-Policy"] == (
            "camera=(), geolocation=(), microphone=()"
        )
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_session_and_csrf_cookie_defaults_are_hardened(settings) -> None:
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"


@pytest.mark.django_db
def test_download_filename_cannot_inject_response_headers(
    client, security_user, temporary_media_root
) -> None:
    record = FileStorageService().create_file(
        uploaded_file=SimpleUploadedFile("safe.txt", b"content"),
        owner=security_user,
    )
    record.original_filename = "report.txt\r\nX-Injected: yes"
    record.save(update_fields=["original_filename"])
    client.force_login(security_user)

    response = client.get(reverse("user_console:file_download", args=[record.pk]))

    assert response.status_code == 200
    assert "X-Injected" not in response.headers
    assert "\r" not in response["Content-Disposition"]
    assert "\n" not in response["Content-Disposition"]
