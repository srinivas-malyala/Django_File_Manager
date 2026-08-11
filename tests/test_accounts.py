"""Phase 1 custom user and browser authentication tests."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse

from accounts.forms import RegistrationForm

User = get_user_model()

OLD_PASSWORD = "Original-Secure-Passphrase-42"
NEW_PASSWORD = "Updated-Secure-Passphrase-84"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password=OLD_PASSWORD,
        first_name="Alice",
        last_name="Example",
    )


@pytest.mark.django_db
def test_user_creation_hashes_password_and_sets_custom_fields() -> None:
    user = User.objects.create_user(
        username="model-user",
        email="model@example.com",
        password=OLD_PASSWORD,
    )

    assert user.email == "model@example.com"
    assert user.check_password(OLD_PASSWORD)
    assert user.is_admin is False
    assert user.created_at is not None


@pytest.mark.django_db
def test_email_is_unique_at_database_level() -> None:
    User.objects.create_user(
        username="first-user",
        email="unique@example.com",
        password=OLD_PASSWORD,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            username="second-user",
            email="unique@example.com",
            password=OLD_PASSWORD,
        )


@pytest.mark.django_db
def test_registration_creates_user_with_hashed_password(client) -> None:
    response = client.post(
        reverse("accounts:register"),
        {
            "username": "new-user",
            "email": "New.User@Example.COM",
            "first_name": "New",
            "last_name": "User",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:login")
    created_user = User.objects.get(username="new-user")
    assert created_user.email == "new.user@example.com"
    assert created_user.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_registration_rejects_email_case_insensitively(user) -> None:
    form = RegistrationForm(
        data={
            "username": "different-user",
            "email": user.email.upper(),
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        }
    )

    assert form.is_valid() is False
    assert "email" in form.errors


@pytest.mark.django_db
def test_registration_requires_csrf_token() -> None:
    from django.test import Client

    csrf_client = Client(enforce_csrf_checks=True)
    response = csrf_client.post(
        reverse("accounts:register"),
        {
            "username": "csrf-user",
            "email": "csrf@example.com",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 403
    assert User.objects.filter(username="csrf-user").exists() is False


@pytest.mark.django_db
def test_login_success_creates_session(client, user) -> None:
    response = client.post(
        reverse("accounts:login"),
        {"username": user.username, "password": OLD_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:profile")
    assert str(user.pk) == client.session["_auth_user_id"]


@pytest.mark.django_db
def test_login_failure_does_not_create_authenticated_session(client, user) -> None:
    response = client.post(
        reverse("accounts:login"),
        {"username": user.username, "password": "incorrect-password"},
    )

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert response.context["form"].errors


@pytest.mark.django_db
def test_logout_ends_session_and_requires_post(client, user) -> None:
    client.force_login(user)

    get_response = client.get(reverse("accounts:logout"))
    assert get_response.status_code == 405
    assert str(user.pk) == client.session["_auth_user_id"]

    post_response = client.post(reverse("accounts:logout"))
    assert post_response.status_code == 302
    assert post_response.url == reverse("accounts:login")
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_profile_displays_authenticated_user(client, user) -> None:
    client.force_login(user)

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 200
    assert response.context["user"] == user
    assert user.username.encode() in response.content
    assert user.email.encode() in response.content


@pytest.mark.django_db
def test_anonymous_profile_access_redirects_to_login(client) -> None:
    profile_url = reverse("accounts:profile")

    response = client.get(profile_url)

    assert response.status_code == 302
    assert response.url == f"{reverse('accounts:login')}?next={profile_url}"


@pytest.mark.django_db
def test_password_change_updates_password_and_retains_session(client, user) -> None:
    client.force_login(user)

    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": OLD_PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:profile")
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert str(user.pk) == client.session["_auth_user_id"]


@pytest.mark.django_db
def test_password_change_rejects_incorrect_current_password(client, user) -> None:
    client.force_login(user)

    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "incorrect-password",
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(OLD_PASSWORD)


def test_custom_user_is_registered_with_admin() -> None:
    assert User in admin.site._registry
