from .conftest import register_and_login


def test_registration_hashes_credentials_and_rejects_duplicate(client):
    register_and_login(client)
    duplicate = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "other@example.com",
            "password": "another-secure-password",
        },
    )
    assert duplicate.status_code == 409


def test_login_and_status(client, tokens):
    response = client.get(
        "/api/auth/status",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["username"] == "alice"


def test_invalid_login_is_rejected(client):
    response = client.post(
        "/api/auth/token",
        data={"username": "missing", "password": "incorrect-password"},
    )
    assert response.status_code == 401


def test_refresh_rotates_and_old_refresh_cannot_be_reused(client, tokens):
    rotated = client.post(
        "/api/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    replay = client.post(
        "/api/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


def test_logout_revokes_refresh_token(client, tokens):
    assert (
        client.post(
            "/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/auth/token/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
