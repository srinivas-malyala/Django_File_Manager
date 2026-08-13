from .conftest import register_and_login


def upload(client, headers, name="notes.txt", content=b"private notes"):
    return client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": (name, content, "text/plain")},
        data={"description": "Initial description"},
    )


def test_file_routes_require_authentication(client):
    assert client.get("/api/files").status_code == 401
    assert (
        client.post("/api/files/upload", files={"file": ("a.txt", b"a")}).status_code
        == 401
    )


def test_upload_list_detail_update_download_delete(client, auth_headers):
    created = upload(client, auth_headers)
    assert created.status_code == 201, created.text
    file_id = created.json()["data"]["id"]
    assert created.json()["data"]["original_filename"] == "notes.txt"

    listing = client.get("/api/files?search=notes", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["count"] == 1

    detail = client.get(f"/api/files/{file_id}", headers=auth_headers)
    assert detail.status_code == 200

    updated = client.put(
        f"/api/files/{file_id}", headers=auth_headers, json={"description": "Updated"}
    )
    assert updated.json()["data"]["description"] == "Updated"

    downloaded = client.get(f"/api/files/{file_id}/download", headers=auth_headers)
    assert downloaded.status_code == 200
    assert downloaded.content == b"private notes"
    assert downloaded.headers["cache-control"] == "private, no-store"

    assert (
        client.delete(f"/api/files/{file_id}", headers=auth_headers).status_code == 200
    )
    assert client.get(f"/api/files/{file_id}", headers=auth_headers).status_code == 404


def test_files_are_owner_scoped(client, auth_headers):
    created = upload(client, auth_headers).json()["data"]
    bob = register_and_login(client, "bob")
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    assert (
        client.get(f"/api/files/{created['id']}", headers=bob_headers).status_code
        == 404
    )
    assert client.get("/api/files", headers=bob_headers).json()["data"]["count"] == 0


def test_upload_rejects_unsafe_extension_and_empty_content(client, auth_headers):
    unsafe = upload(client, auth_headers, "payload.html", b"<script>alert(1)</script>")
    empty = upload(client, auth_headers, "empty.txt", b"")
    assert unsafe.status_code == 400
    assert empty.status_code == 400


def test_update_rejects_immutable_metadata(client, auth_headers):
    file_id = upload(client, auth_headers).json()["data"]["id"]
    response = client.put(
        f"/api/files/{file_id}",
        headers=auth_headers,
        json={"original_filename": "changed.txt"},
    )
    assert response.status_code == 422
