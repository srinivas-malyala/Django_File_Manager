"""Phase 0 project smoke tests."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse


def test_custom_user_model_is_configured() -> None:
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model().__name__ == "User"


def test_project_root_responds(client) -> None:
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Enterprise File Manager Console" in response.content
