# FastAPI File Manager Service

This folder contains an independent FastAPI implementation of authentication and private file operations. It uses its own SQLAlchemy database and storage directory; it does not read or mutate Django models.

## Features

- Argon2 password hashing
- OAuth2 password login with signed JWT access and refresh tokens
- Refresh-token rotation and server-side revocation
- Registration, login, refresh, logout, and authentication status
- Owner-scoped file upload, search/list, detail, description update, download, and delete
- Generated storage names, filename normalization, 50 MB streaming limit, and MIME inspection
- SQLite development default with database configuration through an environment variable
- Interactive OpenAPI documentation at `/docs`

## Start the service

From the repository root:

```bash
python -m pip install -r fastapi_service/requirements.txt
export FASTAPI_SECRET_KEY="$(openssl rand -hex 32)"
uvicorn fastapi_service.app.main:app --reload --port 8001
```

Open <http://127.0.0.1:8001/docs>. Tables and the private upload directory are created at startup. Use Alembic migrations before evolving an established production database schema.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Register a user with JSON credentials |
| `POST` | `/api/auth/token` | Obtain tokens using OAuth2 form fields |
| `POST` | `/api/auth/token/refresh` | Rotate a refresh token |
| `POST` | `/api/auth/logout` | Revoke a refresh token |
| `GET` | `/api/auth/status` | Return the authenticated account |
| `GET` | `/api/files` | Search and paginate the current user's files |
| `GET` | `/api/files/my-files` | Alias for the same personal collection |
| `POST` | `/api/files/upload` | Upload multipart `file` and optional `description` |
| `GET` | `/api/files/{id}` | Return owner-scoped metadata |
| `PUT` | `/api/files/{id}` | Update `description` only |
| `GET` | `/api/files/{id}/download` | Stream an authorized private download |
| `DELETE` | `/api/files/{id}` | Delete content and metadata |

Register and log in:

```bash
curl -X POST http://127.0.0.1:8001/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"correct-horse-battery-staple"}'

curl -X POST http://127.0.0.1:8001/api/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=alice&password=correct-horse-battery-staple'
```

Upload and list files:

```bash
curl -X POST http://127.0.0.1:8001/api/files/upload \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -F 'file=@report.pdf' -F 'description=Quarterly report'

curl 'http://127.0.0.1:8001/api/files?search=report&page=1&page_size=20' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

## Configuration

Copy `.env.example` values into your process environment. Production mode refuses to start with the development secret. Use PostgreSQL by installing its SQLAlchemy driver and setting `FASTAPI_DATABASE_URL` to the corresponding SQLAlchemy URL.

## Tests

```bash
python -m pytest fastapi_service/tests -q
```
