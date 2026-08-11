"""Provider-neutral Gunicorn configuration driven entirely by environment."""

import os


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = env_int("GUNICORN_WORKERS", 2)
threads = env_int("GUNICORN_THREADS", 2)
worker_class = "gthread"
timeout = env_int("GUNICORN_TIMEOUT", 60)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = env_int("GUNICORN_KEEPALIVE", 5)
max_requests = env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 100)
accesslog = os.environ.get("GUNICORN_ACCESS_LOG") or None
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
wsgi_app = "django_filemanagement.wsgi:application"
