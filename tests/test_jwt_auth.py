"""Phase 2 JWT authentication and refresh-token lifecycle tests."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()
PASSWORD = "JWT-Secure-Passphrase-42"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def jwt_user(db):
    return User.objects.create_user(
        username="jwt-user",
        email="jwt-user@example.com",
        password=PASSWORD,
    )


def obtain_token_pair(api_client: APIClient, jwt_user) -> dict[str, str]:
    response = api_client.post(
        reverse("account_api:token_obtain_pair"),
        {"username": jwt_user.username, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.django_db
def test_token_creation_returns_access_and_refresh_tokens(api_client, jwt_user) -> None:
    tokens = obtain_token_pair(api_client, jwt_user)

    assert tokens["access"]
    assert tokens["refresh"]
    assert tokens["access"] != tokens["refresh"]


@pytest.mark.django_db
def test_token_creation_rejects_invalid_credentials(api_client, jwt_user) -> None:
    response = api_client.post(
        reverse("account_api:token_obtain_pair"),
        {"username": jwt_user.username, "password": "incorrect-password"},
        format="json",
    )

    assert response.status_code == 401
    assert "access" not in response.json()
    assert "refresh" not in response.json()


@pytest.mark.django_db
def test_protected_endpoint_requires_authentication(api_client) -> None:
    response = api_client.get(reverse("account_api:status"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_access_token_authenticates_protected_endpoint(api_client, jwt_user) -> None:
    tokens = obtain_token_pair(api_client, jwt_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.get(reverse("account_api:status"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == {"id": jwt_user.pk, "username": jwt_user.username}
    assert payload["message"] == "Authentication successful"
    assert payload["timestamp"]


@pytest.mark.django_db
def test_refresh_rotates_token_and_blacklists_previous_refresh(
    api_client, jwt_user
) -> None:
    tokens = obtain_token_pair(api_client, jwt_user)
    refresh_url = reverse("account_api:token_refresh")

    response = api_client.post(
        refresh_url, {"refresh": tokens["refresh"]}, format="json"
    )

    assert response.status_code == 200
    rotated_tokens = response.json()
    assert rotated_tokens["access"]
    assert rotated_tokens["refresh"]
    assert rotated_tokens["refresh"] != tokens["refresh"]

    rejected_response = api_client.post(
        refresh_url,
        {"refresh": tokens["refresh"]},
        format="json",
    )
    assert rejected_response.status_code == 401

    accepted_response = api_client.post(
        refresh_url,
        {"refresh": rotated_tokens["refresh"]},
        format="json",
    )
    assert accepted_response.status_code == 200


@pytest.mark.django_db
def test_blacklisted_refresh_token_cannot_be_used(api_client, jwt_user) -> None:
    tokens = obtain_token_pair(api_client, jwt_user)

    blacklist_response = api_client.post(
        reverse("account_api:token_blacklist"),
        {"refresh": tokens["refresh"]},
        format="json",
    )

    assert blacklist_response.status_code == 200
    refresh_response = api_client.post(
        reverse("account_api:token_refresh"),
        {"refresh": tokens["refresh"]},
        format="json",
    )
    assert refresh_response.status_code == 401


@pytest.mark.django_db
def test_session_authentication_is_still_available_for_api_status(
    api_client, jwt_user
) -> None:
    assert api_client.login(username=jwt_user.username, password=PASSWORD) is True

    response = api_client.get(reverse("account_api:status"))

    assert response.status_code == 200
    assert response.json()["data"]["username"] == jwt_user.username
