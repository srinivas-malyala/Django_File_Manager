# TLS/HTTPS setup for Django and FastAPI

This guide configures HTTPS for both services in this repository without exposing either application server directly to the internet. All hostnames, usernames, addresses, credentials, and filesystem paths below are anonymous placeholders.

## Recommended architecture

```text
Internet
   |
   | TCP 80/443
   v
Caddy reverse proxy and TLS termination
   |-- https://files.example.test --> http://127.0.0.1:8000 (Django/Gunicorn)
   `-- https://api.example.test   --> http://127.0.0.1:8001 (FastAPI/Uvicorn)
```

Caddy owns the public certificates, redirects HTTP to HTTPS, and forwards requests to application processes bound only to the loopback interface. Replace the reserved documentation domain `example.test` with domains you control.

## Placeholder reference

| Placeholder | Meaning | Example used below |
| --- | --- | --- |
| Django hostname | Public browser-console domain | `files.example.test` |
| FastAPI hostname | Public standalone API domain | `api.example.test` |
| Application root | Repository location on the server | `/opt/filemanager/app` |
| Runtime user | Unprivileged operating-system account | `appuser` |
| Django data root | Static and private Django data | `/srv/filemanager-django` |
| FastAPI data root | Database and private FastAPI data | `/srv/filemanager-fastapi` |
| Proxy address | Only address allowed to supply forwarding headers | `127.0.0.1` |

Never copy example secrets into production. Never commit populated environment files, private keys, database passwords, SMTP credentials, or JWT signing keys.

## Prerequisites

Before starting, provide:

- A Linux server with a public IP address.
- Two DNS names that resolve to that server.
- Inbound TCP ports `80` and `443` open.
- The repository installed at an application path such as `/opt/filemanager/app`.
- A Python virtual environment at `/opt/filemanager/app/.venv`.
- An unprivileged runtime account such as `appuser`.
- Caddy installed from its official distribution.

Do not expose application ports `8000` and `8001` through the public firewall.

## 1. Configure DNS

Create DNS records with your DNS provider:

```text
files.example.test  A     192.0.2.10
api.example.test    A     192.0.2.10
```

`192.0.2.10` is a documentation-only address. Replace it with the server's public address. Add `AAAA` records only when IPv6 routing and the IPv6 firewall are ready.

Verify resolution:

```bash
dig +short files.example.test
dig +short api.example.test
```

Certificate issuance will fail if the names do not resolve to the TLS proxy.

## 2. Configure the firewall

Allow SSH and public web traffic while leaving the application ports private. On a host using UFW:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

The expected public ports are:

| Port | Access | Purpose |
| --- | --- | --- |
| `22/tcp` | Restricted where possible | Administration |
| `80/tcp` | Public | ACME validation and HTTPS redirects |
| `443/tcp` | Public | HTTPS |
| `8000/tcp` | Loopback only | Django/Gunicorn upstream |
| `8001/tcp` | Loopback only | FastAPI/Uvicorn upstream |

## 3. Create runtime directories

The following example keeps application code, generated static files, and private uploads separate:

```bash
sudo mkdir -p /srv/filemanager-django/staticfiles
sudo mkdir -p /srv/filemanager-django/uploads
sudo mkdir -p /srv/filemanager-fastapi/uploads
sudo mkdir -p /etc/filemanager

sudo chown -R appuser:appuser /srv/filemanager-django
sudo chown -R appuser:appuser /srv/filemanager-fastapi
sudo chown root:root /etc/filemanager
sudo chmod 750 /etc/filemanager
```

Private upload directories must not be configured as public Caddy file roots.

## 4. Configure Django

Create `/etc/filemanager/django.env`:

```dotenv
DEBUG=False
SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_VALUE
ALLOWED_HOSTS=files.example.test
CSRF_TRUSTED_ORIGINS=https://files.example.test

DATABASE_URL=postgresql://DB_USER:PERCENT_ENCODED_PASSWORD@DB_HOST:5432/DB_NAME?sslmode=require

STATIC_ROOT=/srv/filemanager-django/staticfiles
MEDIA_ROOT=/srv/filemanager-django/uploads

SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
TRUST_X_FORWARDED_PROTO=True
USE_X_FORWARDED_HOST=False
GUNICORN_FORWARDED_ALLOW_IPS=127.0.0.1

SECURE_HSTS_SECONDS=300
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=SMTP_HOST
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=SMTP_USER
EMAIL_HOST_PASSWORD=SMTP_PASSWORD
DEFAULT_FROM_EMAIL=noreply@example.test
```

Generate a Django secret instead of inventing one manually:

```bash
openssl rand -base64 64
```

Secure the environment file:

```bash
sudo chown root:appuser /etc/filemanager/django.env
sudo chmod 640 /etc/filemanager/django.env
```

### Why the proxy settings matter

The browser connects to Caddy over HTTPS, but Caddy connects to Gunicorn over loopback HTTP. The repository already maps `TRUST_X_FORWARDED_PROTO=True` to:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

This allows Django to recognize the original request as secure. Only enable this setting when:

1. Django cannot be reached directly from an untrusted network.
2. The reverse proxy replaces `X-Forwarded-Proto` with its own value.
3. Gunicorn trusts forwarding headers only from the proxy address.

Incorrect proxy trust can allow header spoofing. Omitting the setting while `SECURE_SSL_REDIRECT=True` can cause redirect loops.

### HSTS rollout

Start with:

```dotenv
SECURE_HSTS_SECONDS=300
```

After HTTPS has worked reliably for every route, increase it to:

```dotenv
SECURE_HSTS_SECONDS=31536000
```

Do not enable `SECURE_HSTS_INCLUDE_SUBDOMAINS` or `SECURE_HSTS_PRELOAD` until every relevant subdomain is permanently HTTPS-only. Browsers cache HSTS and a mistake can make a site inaccessible for the configured duration.

## 5. Prepare and verify Django

From the application root:

```bash
cd /opt/filemanager/app

set -a
source /etc/filemanager/django.env
set +a

.venv/bin/python manage.py check
.venv/bin/python manage.py check --deploy
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
```

Review every deployment-check warning. The production server must use Gunicorn, not Django's development server.

Test Gunicorn manually:

```bash
GUNICORN_BIND=127.0.0.1:8000 \
  .venv/bin/gunicorn --config gunicorn.conf.py
```

In another terminal, simulate the proxy:

```bash
curl -I http://127.0.0.1:8000/ \
  -H 'Host: files.example.test' \
  -H 'X-Forwarded-Proto: https'
```

Stop the manual process after verification.

## 6. Configure FastAPI

Create `/etc/filemanager/fastapi.env`:

```dotenv
FASTAPI_ENV=production
FASTAPI_SECRET_KEY=REPLACE_WITH_AN_INDEPENDENT_RANDOM_VALUE
FASTAPI_DATABASE_URL=sqlite:////srv/filemanager-fastapi/filemanager.db
FASTAPI_UPLOAD_DIR=/srv/filemanager-fastapi/uploads
FASTAPI_ACCESS_TOKEN_MINUTES=15
FASTAPI_REFRESH_TOKEN_DAYS=7
FASTAPI_MAX_FILE_SIZE=52428800
```

Generate an independent JWT secret:

```bash
openssl rand -hex 32
```

Do not reuse Django's `SECRET_KEY`. Secure the FastAPI environment file:

```bash
sudo chown root:appuser /etc/filemanager/fastapi.env
sudo chmod 640 /etc/filemanager/fastapi.env
```

SQLite is suitable for local development and small single-host use. A production deployment with multiple instances should use PostgreSQL and a managed schema-migration workflow.

Test Uvicorn manually:

```bash
cd /opt/filemanager/app

set -a
source /etc/filemanager/fastapi.env
set +a

.venv/bin/uvicorn fastapi_service.app.main:app \
  --host 127.0.0.1 \
  --port 8001 \
  --proxy-headers \
  --forwarded-allow-ips 127.0.0.1 \
  --workers 2
```

Verify the private upstream from another terminal:

```bash
curl http://127.0.0.1:8001/api/health
```

Expected result:

```json
{"status":"healthy","service":"fastapi-file-manager"}
```

Never set `--forwarded-allow-ips '*'` unless network isolation makes it impossible for untrusted clients to connect to Uvicorn.

## 7. Configure Caddy

Create or replace `/etc/caddy/Caddyfile`:

```caddyfile
files.example.test {
    encode zstd gzip

    handle_path /static/* {
        root * /srv/filemanager-django/staticfiles
        file_server
    }

    reverse_proxy 127.0.0.1:8000 {
        header_up Host {host}
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-Proto {scheme}
    }
}

api.example.test {
    encode zstd gzip

    header Strict-Transport-Security "max-age=300"

    reverse_proxy 127.0.0.1:8001 {
        header_up Host {host}
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

Django emits its own HSTS header through `SecurityMiddleware`. Caddy supplies HSTS for FastAPI. Keep their initial HSTS values aligned during rollout.

There is intentionally no public `/media/` or `/uploads/` mapping. Both applications stream private downloads only after authorization.

Validate and activate Caddy:

```bash
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable caddy
sudo systemctl restart caddy
sudo systemctl status caddy
```

With valid public DNS and reachable ports 80 and 443, Caddy automatically obtains certificates, renews them, and redirects HTTP to HTTPS.

Inspect certificate and proxy logs without exposing them publicly:

```bash
sudo journalctl -u caddy -n 100 --no-pager
```

## 8. Run both applications with systemd

### Django unit

Create `/etc/systemd/system/filemanager-django.service`:

```ini
[Unit]
Description=File Manager Django service
After=network.target

[Service]
User=appuser
Group=appuser
WorkingDirectory=/opt/filemanager/app
EnvironmentFile=/etc/filemanager/django.env
Environment=GUNICORN_BIND=127.0.0.1:8000
ExecStart=/opt/filemanager/app/.venv/bin/gunicorn --config gunicorn.conf.py
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

### FastAPI unit

Create `/etc/systemd/system/filemanager-fastapi.service`:

```ini
[Unit]
Description=File Manager FastAPI service
After=network.target

[Service]
User=appuser
Group=appuser
WorkingDirectory=/opt/filemanager/app
EnvironmentFile=/etc/filemanager/fastapi.env
ExecStart=/opt/filemanager/app/.venv/bin/uvicorn fastapi_service.app.main:app --host 127.0.0.1 --port 8001 --proxy-headers --forwarded-allow-ips 127.0.0.1 --workers 2
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

Enable the services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now filemanager-django
sudo systemctl enable --now filemanager-fastapi

sudo systemctl status filemanager-django
sudo systemctl status filemanager-fastapi
```

Read service logs:

```bash
sudo journalctl -u filemanager-django -f
sudo journalctl -u filemanager-fastapi -f
```

## 9. Verify public HTTPS

### HTTP redirects

```bash
curl -I http://files.example.test/
curl -I http://api.example.test/api/health
```

Both responses should redirect to an `https://` URL.

### HTTPS responses

```bash
curl -I https://files.example.test/
curl https://api.example.test/api/health
curl -I https://api.example.test/docs
```

### Certificate chains

```bash
openssl s_client \
  -connect files.example.test:443 \
  -servername files.example.test \
  -verify_return_error </dev/null

openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_return_error </dev/null
```

Look for a successful verification result and a certificate whose subject alternative names include the requested hostname.

### Security headers

```bash
curl -sS -D - -o /dev/null https://files.example.test/ \
  | grep -Ei 'strict-transport-security|content-security-policy|x-content-type-options'

curl -sS -D - -o /dev/null https://api.example.test/api/health \
  | grep -Ei 'strict-transport-security|x-content-type-options'
```

### Application workflows

Exercise these operations over HTTPS before directing production traffic to the services:

- Django registration, login, logout, password reset, upload, preview, download, and deletion.
- Django administration login at `https://files.example.test/admin/`.
- FastAPI registration, token acquisition, token refresh, logout, upload, search, download, and deletion.
- Cross-user attempts that must return `404` or `401` as appropriate.

## 10. Test FastAPI authentication over HTTPS

Register a non-production test account:

```bash
curl -X POST https://api.example.test/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "testuser",
    "email": "testuser@example.test",
    "password": "replace-with-a-temporary-strong-password"
  }'
```

Obtain a token pair:

```bash
curl -X POST https://api.example.test/api/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=testuser' \
  --data-urlencode 'password=replace-with-a-temporary-strong-password'
```

Avoid placing real access or refresh tokens in shell history, CI logs, screenshots, tickets, or chat messages. Prefer a secure API client or read credentials from protected environment variables when testing real accounts.

## 11. Cross-origin browser access

HTTPS and CORS solve different problems. If browser JavaScript loaded from `https://files.example.test` calls `https://api.example.test`, FastAPI must explicitly allow that origin.

Add `CORSMiddleware` in the FastAPI application factory only if this browser-to-API workflow is required:

```python
from fastapi.middleware.cors import CORSMiddleware

application.add_middleware(
    CORSMiddleware,
    allow_origins=["https://files.example.test"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

Use exact trusted origins. Do not use `allow_origins=["*"]` for authenticated browser workflows. CORS is unnecessary for server-to-server clients, command-line clients, native applications, or the documentation hosted on the FastAPI origin itself.

## 12. Local-development HTTPS

For development, keep both Python servers on loopback HTTP and place local Caddy in front of them:

```caddyfile
django.localhost {
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-Proto {scheme}
    }
}

api.localhost {
    reverse_proxy 127.0.0.1:8001 {
        header_up X-Forwarded-Proto {scheme}
    }
}
```

Trust Caddy's local development CA and start the proxy:

```bash
caddy trust
caddy run --config ./Caddyfile
```

Use these Django development settings:

```dotenv
ALLOWED_HOSTS=django.localhost
CSRF_TRUSTED_ORIGINS=https://django.localhost
TRUST_X_FORWARDED_PROTO=True
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Open:

```text
https://django.localhost/
https://api.localhost/docs
```

If local CA installation is not acceptable, Uvicorn can serve a locally generated certificate directly:

```bash
.venv/bin/uvicorn fastapi_service.app.main:app \
  --host 127.0.0.1 \
  --port 8444 \
  --ssl-keyfile /path/to/local-certificate-key.pem \
  --ssl-certfile /path/to/local-certificate.pem
```

Direct application-server TLS is reasonable for local testing. A TLS-terminating reverse proxy remains the preferred production design.

## Troubleshooting

### Redirect loop in Django

Check all three conditions:

1. Caddy sends `X-Forwarded-Proto: https` for HTTPS requests.
2. Django has `TRUST_X_FORWARDED_PROTO=True`.
3. Only the proxy can reach Gunicorn.

Do not disable `SECURE_SSL_REDIRECT` as the permanent production fix.

### Django returns `400 Bad Request`

Verify:

```dotenv
ALLOWED_HOSTS=files.example.test
CSRF_TRUSTED_ORIGINS=https://files.example.test
```

Do not include URL schemes in `ALLOWED_HOSTS`. Do include `https://` in `CSRF_TRUSTED_ORIGINS`.

### Caddy cannot obtain a certificate

Confirm that:

- DNS resolves to this proxy.
- Both IPv4 and IPv6 records are correct.
- Ports 80 and 443 are reachable.
- No other process is using ports 80 or 443.
- The hostname is a real public domain, not `example.test`.

Review:

```bash
sudo journalctl -u caddy -n 200 --no-pager
```

### Caddy returns `502 Bad Gateway`

Check the private upstreams:

```bash
curl -I http://127.0.0.1:8000/ -H 'Host: files.example.test'
curl http://127.0.0.1:8001/api/health
sudo systemctl status filemanager-django
sudo systemctl status filemanager-fastapi
```

### Django static assets return `404`

Run:

```bash
cd /opt/filemanager/app
set -a
source /etc/filemanager/django.env
set +a
.venv/bin/python manage.py collectstatic --noinput
```

Then verify Caddy can read `/srv/filemanager-django/staticfiles`. Do not solve static-file errors by exposing the private upload directory.

### Uploads fail through the proxy

Confirm directory ownership, free disk space, and the 50 MB application limit. If adding proxy request-size limits, keep them at least as large as the application limit plus multipart overhead.

## Security checklist

- [ ] Public DNS names resolve only to intended TLS endpoints.
- [ ] Only ports 80 and 443 expose the web services publicly.
- [ ] Gunicorn and Uvicorn bind to loopback or a private socket.
- [ ] Forwarded headers are trusted only from the known proxy.
- [ ] Django has secure session and CSRF cookies enabled.
- [ ] Django recognizes the original HTTPS scheme without redirect loops.
- [ ] Django and FastAPI use different random application secrets.
- [ ] Environment files are outside the repository with restricted permissions.
- [ ] Caddy certificates renew successfully.
- [ ] HSTS starts with a short duration and increases only after validation.
- [ ] Private uploads are never served as a public directory.
- [ ] HTTP redirects to HTTPS for both hostnames.
- [ ] Authentication and file workflows pass over HTTPS.
- [ ] Logs do not contain passwords, JWTs, reset tokens, or private filenames.
- [ ] Database connections use TLS where the database is remote.
- [ ] Backups, restore tests, monitoring, and certificate-expiry alerting are configured.

## Operational verification commands

Use these after deployments or proxy changes:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl is-active caddy filemanager-django filemanager-fastapi
curl -fsS https://api.example.test/api/health
curl -fsSI https://files.example.test/
```

For Django releases, also run with the production environment loaded:

```bash
.venv/bin/python manage.py check --deploy
```

Keep TLS termination, forwarded-header trust, application security settings, and network isolation synchronized. Changing only one layer can create redirect loops, spoofable request metadata, broken CSRF validation, or accidentally exposed application ports.

## References

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django security settings](https://docs.djangoproject.com/en/5.2/ref/settings/#security)
- [Uvicorn deployment and HTTPS](https://www.uvicorn.org/deployment/)
- [Uvicorn proxy and TLS settings](https://www.uvicorn.org/settings/)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
