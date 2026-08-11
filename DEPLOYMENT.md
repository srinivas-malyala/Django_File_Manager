# Production deployment

This application is infrastructure-neutral. It needs Python 3.12+, PostgreSQL, durable private file storage, an SMTP service, and a TLS-terminating reverse proxy or load balancer. The included Dockerfile is optional; no cloud-specific services are assumed.

## Required configuration

Create runtime environment variables from `.env.example`. Never commit the resulting `.env` file.

At minimum, production must set:

```text
DEBUG=False
SECRET_KEY=<random value of at least 50 characters>
ALLOWED_HOSTS=files.example.com
DATABASE_URL=postgresql://user:percent-encoded-password@host:5432/database?sslmode=require
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<smtp host>
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<smtp user>
EMAIL_HOST_PASSWORD=<smtp secret>
DEFAULT_FROM_EMAIL=noreply@example.com
STATIC_ROOT=/app/staticfiles
MEDIA_ROOT=/app/uploads
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
LOG_FORMAT=json
```

Use `CSRF_TRUSTED_ORIGINS=https://files.example.com` when browser POST requests use that origin. Comma-separate multiple hosts or origins. Percent-encode reserved characters in PostgreSQL usernames and passwords.

### Reverse proxy trust

The app does not trust forwarded-protocol headers by default. If a known reverse proxy terminates TLS, set `TRUST_X_FORWARDED_PROTO=True` and configure the proxy to replace—not append or preserve—`X-Forwarded-Proto`. Restrict `GUNICORN_FORWARDED_ALLOW_IPS` to the proxy addresses. Enable `USE_X_FORWARDED_HOST` only when the proxy replaces and validates the forwarded host.

Do not enable HSTS preload or include subdomains until every applicable host is permanently HTTPS-ready. HSTS is difficult to reverse after browsers cache it. Django's deployment check will continue to warn about these two intentionally disabled settings; evaluate those warnings instead of enabling them mechanically.

## PostgreSQL

Install runtime dependencies from `requirements-prod.txt`; the Psycopg 3 driver is included. `requirements.txt` additionally installs the test and formatting toolchain for development and CI. The settings accept `postgres://` and `postgresql://` URLs and pass query options such as `sslmode=require` to Psycopg. Configure database backups, encryption, least-privilege credentials, connection limits, and restore testing outside the application.

SQLite remains the default only when `DATABASE_URL` is empty and is intended for local development.

## Release procedure

Run these once for each release, before shifting traffic:

```bash
python manage.py check
python manage.py check --deploy
python manage.py migrate --noinput
python manage.py collectstatic --noinput
pytest
```

Serve `STATIC_ROOT` through the reverse proxy or a dedicated static-file service. Never expose `MEDIA_ROOT` as a public URL. Uploaded files must remain on durable private storage and be downloaded only through the authorization-aware application endpoints.

Start the web process with:

```bash
gunicorn --config gunicorn.conf.py
```

The application logs to the process streams. Production defaults to one-line JSON with reset links, bearer credentials, and common secret key/value fields redacted. Gunicorn access logging is disabled by default because request paths can contain password-reset tokens; enable it only behind an equivalent URL-redaction policy.

## Docker

Build and run the non-root image:

```bash
docker build --tag django-filemanager:1.0 .
docker run --rm --env-file .env --publish 8000:8000 \
  --mount type=volume,source=filemanager-uploads,target=/app/uploads \
  django-filemanager:1.0
```

Run migrations and static collection as release tasks using the same image and environment. Do not run concurrent automatic migrations in every web replica.

## Production checklist

- [ ] `DEBUG=False`; long random `SECRET_KEY`; explicit `ALLOWED_HOSTS`.
- [ ] PostgreSQL uses TLS, least privilege, backups, and a tested restore process.
- [ ] Migrations and `collectstatic` completed successfully for the release.
- [ ] TLS is enforced; secure cookies are enabled; proxy trust is narrowly scoped.
- [ ] HSTS scope and duration were reviewed before enabling subdomains or preload.
- [ ] SMTP credentials are supplied only through the runtime environment.
- [ ] `MEDIA_ROOT` is durable, private, backed up, and separate from `STATIC_ROOT`.
- [ ] Static files are served from `STATIC_ROOT`, never from the Django development server.
- [ ] Rate-limit cache behavior is appropriate for the deployment topology. For multiple replicas, use a shared Django cache backend before relying on cross-replica throttling.
- [ ] `/api/health/` is monitored; `503` removes an unhealthy instance from service.
- [ ] JSON logs are collected with retention and access controls; reset-token URLs are redacted at every proxy layer.
- [ ] A rollback plan covers both application code and backward-compatible database migrations.
- [ ] A non-production environment has exercised registration, sessions, JWTs, upload, search, preview, download, delete, batch operations, reset email, statistics, and health checks.
