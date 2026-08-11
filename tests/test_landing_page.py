"""Authentication-aware landing-page workflow tests."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


def test_anonymous_landing_page_presents_authentication_workflow(client) -> None:
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert "core/index.html" in [template.name for template in response.templates]
    assert b"Your files, organized and protected" in response.content
    assert reverse("accounts:login").encode() in response.content
    assert reverse("accounts:register").encode() in response.content
    assert b"From sign-in to file management" in response.content
    assert b"Open dashboard" not in response.content


@pytest.mark.django_db
def test_authenticated_landing_page_presents_file_operations(client) -> None:
    user = User.objects.create_user(
        username="landing-user",
        email="landing-user@example.com",
        password="Landing-Page-Secure-Passphrase-42",
        first_name="Landing",
        last_name="User",
    )
    client.force_login(user)

    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Welcome back" in response.content
    assert b"Landing User" in response.content
    assert b"Workspace actions" in response.content
    for route_name in (
        "user_console:dashboard",
        "user_console:file_upload",
        "user_console:file_list",
        "user_console:file_advanced",
        "user_console:profile",
    ):
        assert reverse(route_name).encode() in response.content
    assert b"Create an account" not in response.content
