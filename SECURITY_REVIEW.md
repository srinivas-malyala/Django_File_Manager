# Phase 10 security review

This review covers the Phase 0–9 implementation and records the controls verified or strengthened in Phase 10.

## Findings and controls

- **Authorization and IDOR:** All REST, console, preview, download, delete, batch, search, AJAX, and aggregate file access starts from an authenticated owner-scoped query. Missing and foreign UUIDs consistently return `404` without confirming existence.
- **Path traversal and unsafe filenames:** Client filenames are reduced to a basename, NULs and unsafe characters are removed, length is bounded, and physical names are generated from server-side UUIDs. ZIP entries are independently sanitized and deduplicated.
- **CSRF:** Django CSRF middleware remains enabled. Browser mutations use POST forms with CSRF tokens; logout, deletion, batch operations, upload, account changes, and password-reset requests are covered by regression tests.
- **XSS:** Django template auto-escaping remains enabled, previews render text as escaped text, and live search uses `textContent`. A restrictive Content Security Policy, frame protection, and permissions policy now provide defense in depth.
- **MIME spoofing:** Upload validation ignores the client-provided content type, inspects content with `python-magic` where available, blocks executable/script MIME types, and rejects reliable image, PDF, text, and CSV extension mismatches.
- **Upload limits:** Files are bounded to 50 MB by the application validator. Django request-memory and form-field limits are explicitly bounded and configurable through environment variables.
- **Token handling:** JWTs rotate and old refresh tokens are blacklisted. Password reset tokens are signed, expire after one hour by default, become invalid after password change, and are not emitted by application logging.
- **Session security:** Session cookies are HTTP-only and SameSite `Lax`; CSRF cookies are SameSite `Lax`. Content sniffing protection, referrer policy, and clickjacking protection are explicit.
- **Private file serving:** No unrestricted `/media/` URL is registered. Downloads and previews pass through authentication and ownership checks, stream content, suppress sniffing, and use `private, no-store` cache policy.
- **Rate limiting:** Login, registration, reset requests, browser upload/search, JWT endpoints, API upload, and API search have configurable cache/DRF throttles. Browser identity uses authenticated user IDs or the server-provided remote address, not spoofable forwarding headers.
- **Error and logging leakage:** Public errors remain generic. Storage/database exception messages and tracebacks are no longer copied into application logs; events retain user/file identifiers and exception type only.

## Production-specific deployment warnings

Phase 12 added environment-driven production defaults and fail-closed startup validation for these deployment concerns:

- Production rejects the development `SECRET_KEY` and secrets shorter than 50 characters.
- Production requires an explicit `ALLOWED_HOSTS` value.
- `DEBUG=False` defaults HTTPS redirects, secure session/CSRF cookies, HSTS, manifest static files, persistent database health checks, and JSON logs on.
- Proxy-header trust, HSTS subdomains, and HSTS preload remain explicit opt-ins because they depend on the deployment topology and domain policy.

A fully configured production profile passes `python manage.py check --deploy --fail-level WARNING`. See `DEPLOYMENT.md` for the reviewed configuration and rollout checklist.

Private uploads must continue to be served only through the authorization-aware application endpoints or an equivalently protected reverse-proxy delegation. They must never be mounted as public static media.
