"""Phase 9 password reset, support-page, and safe error-page tests."""

import re
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, RequestFactory, override_settings
from django.urls import get_resolver, reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.views import custom_500

User = get_user_model()

OLD_PASSWORD = "Original-Secure-Passphrase-42"
NEW_PASSWORD = "Updated-Secure-Passphrase-84"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="reset-user",
        email="reset@example.com",
        password=OLD_PASSWORD,
    )


@pytest.fixture
def reset_url(client, user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    response = client.post(
        reverse("accounts:password_reset_request"),
        {"email": user.email},
    )
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    match = re.search(
        r"http://testserver(/accounts/password/reset/confirm/[^\s<]+)",
        mail.outbox[0].body,
    )
    assert match is not None
    return match.group(1)


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_request_sends_time_limited_link(client, user) -> None:
    response = client.post(
        reverse("accounts:password_reset_request"),
        {"email": user.email},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    assert "password reset" in mail.outbox[0].subject.lower()
    assert "/accounts/password/reset/confirm/" in mail.outbox[0].body


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_unknown_email_has_same_response_without_sending_email(client) -> None:
    response = client.post(
        reverse("accounts:password_reset_request"),
        {"email": "unknown@example.com"},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_reset_link_updates_password_and_cannot_be_reused(
    client, user, reset_url
) -> None:
    initial_response = client.get(reset_url)
    assert initial_response.status_code == 302
    confirmation_url = initial_response.url

    response = client.post(
        confirmation_url,
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_complete")
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)

    reused_response = client.get(reset_url, follow=True)
    assert reused_response.status_code == 200
    assert b"invalid or has expired" in reused_response.content


@pytest.mark.django_db
def test_reset_confirmation_applies_password_validators(
    client, user, reset_url
) -> None:
    confirmation_response = client.get(reset_url)

    response = client.post(
        confirmation_response.url,
        {"new_password1": "password", "new_password2": "password"},
    )

    assert response.status_code == 200
    assert response.context["form"].errors
    user.refresh_from_db()
    assert user.check_password(OLD_PASSWORD)


@pytest.mark.django_db
@override_settings(PASSWORD_RESET_TIMEOUT=3600)
def test_expired_reset_token_is_rejected(client, user) -> None:
    expired_at = datetime.now() - timedelta(hours=2)
    with patch.object(default_token_generator, "_now", return_value=expired_at):
        token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    url = reverse(
        "accounts:password_reset_confirm",
        kwargs={"uidb64": uid, "token": token},
    )

    response = client.get(url)

    assert response.status_code == 200
    assert b"invalid or has expired" in response.content


@pytest.mark.django_db
def test_password_reset_request_requires_csrf(user) -> None:
    csrf_client = Client(enforce_csrf_checks=True)

    response = csrf_client.post(
        reverse("accounts:password_reset_request"),
        {"email": user.email},
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_password_reset_token_is_not_logged(client, user, reset_url, caplog) -> None:
    token = reset_url.rstrip("/").rsplit("/", 1)[-1]
    caplog.clear()

    response = client.get(reset_url)
    client.post(
        response.url,
        {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
    )

    assert token not in caplog.text


SUPPORT_ROUTES = (
    "user_console:support_contact",
    "user_console:support_help",
    "user_console:support_terms",
)


@pytest.mark.django_db
@pytest.mark.parametrize("route_name", SUPPORT_ROUTES)
def test_support_pages_require_authentication(client, route_name) -> None:
    url = reverse(route_name)

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={url}"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route_name", "expected_text"),
    (
        ("user_console:support_contact", b"Contact support"),
        ("user_console:support_help", b"File Manager help"),
        ("user_console:support_terms", b"Terms of use"),
    ),
)
def test_authenticated_support_pages_render(
    client, user, route_name, expected_text
) -> None:
    client.force_login(user)

    response = client.get(reverse(route_name))

    assert response.status_code == 200
    assert expected_text in response.content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_custom_404_is_generic_and_does_not_reflect_path(client) -> None:
    sensitive_path = "/missing/private-reset-token-value/"

    response = client.get(sensitive_path)

    assert response.status_code == 404
    assert b"Page not found" in response.content
    assert b"private-reset-token-value" not in response.content
    assert "errors/404.html" in [template.name for template in response.templates]


@pytest.mark.django_db
def test_custom_500_handler_is_generic() -> None:
    assert get_resolver().resolve_error_handler(500) is custom_500
    request = RequestFactory().get("/internal-error/")

    response = custom_500(request)

    assert response.status_code == 500
    assert b"Something went wrong" in response.content
    assert b"Traceback" not in response.content
