from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fastapi_service.app.config import Settings
from fastapi_service.app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        secret_key="test-secret-with-enough-random-looking-material",
        access_token_minutes=15,
        refresh_token_days=7,
        max_file_size=1024 * 1024,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def register_and_login(client: TestClient, username: str = "alice") -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201
    response = client.post(
        "/api/auth/token",
        data={"username": username, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def tokens(client):
    return register_and_login(client)


@pytest.fixture
def auth_headers(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}
