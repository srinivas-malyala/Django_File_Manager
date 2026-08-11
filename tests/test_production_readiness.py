"""Phase 12 provider-neutral production configuration tests."""

import importlib.util
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings

from core.logging import JsonFormatter, SensitiveDataFilter
from django_filemanagement.settings import database_config_from_url


def test_postgresql_database_url_supports_encoded_credentials_and_options() -> None:
    config = database_config_from_url(
        "postgresql://file%20user:p%40ss%2Fword@db.example:5433/files"
        "?sslmode=require&application_name=filemanager"
    )

    assert config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "files",
        "USER": "file user",
        "PASSWORD": "p@ss/word",
        "HOST": "db.example",
        "PORT": "5433",
        "OPTIONS": {
            "sslmode": "require",
            "application_name": "filemanager",
        },
    }


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_both_postgresql_url_schemes_are_supported(scheme: str) -> None:
    config = database_config_from_url(f"{scheme}://user:pass@db/database")

    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "database"


def test_sqlite_database_url_supports_memory_and_absolute_paths(tmp_path) -> None:
    in_memory = database_config_from_url("sqlite:///:memory:")
    absolute = database_config_from_url(
        f"sqlite:////{str(tmp_path).lstrip('/')}/db.sqlite3"
    )

    assert in_memory["NAME"] == ":memory:"
    assert Path(absolute["NAME"]) == tmp_path / "db.sqlite3"


@pytest.mark.parametrize(
    "database_url",
    (
        "mysql://user:pass@db/database",
        "postgresql://user:pass@db",
        "postgresql://user:pass@db:not-a-port/database",
        "sqlite://remote-host/database",
    ),
)
def test_invalid_database_urls_fail_with_safe_configuration_error(
    database_url: str,
) -> None:
    with pytest.raises(ImproperlyConfigured) as exc_info:
        database_config_from_url(database_url)

    assert "pass" not in str(exc_info.value)


def _production_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DEBUG": "False",
            "SECRET_KEY": "8mV!2rQ#9xP@4sL$7nK%5cD&1hG*6jT(3wF)0zB-2yU_9iE+4oA",
            "ALLOWED_HOSTS": "files.example.com",
            "LOG_FORMAT": "json",
            "SECURE_SSL_REDIRECT": "True",
            "SESSION_COOKIE_SECURE": "True",
            "CSRF_COOKIE_SECURE": "True",
            "SECURE_HSTS_SECONDS": "31536000",
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": "True",
            "SECURE_HSTS_PRELOAD": "True",
        }
    )
    environment.pop("DATABASE_URL", None)
    return environment


def test_production_configuration_passes_django_deployment_checks() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "check",
            "--deploy",
            "--fail-level",
            "WARNING",
        ],
        cwd=settings.BASE_DIR,
        env=_production_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


def test_production_configuration_fails_closed_without_secret() -> None:
    environment = _production_environment()
    environment.pop("SECRET_KEY")

    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "Production requires a SECRET_KEY" in result.stderr
    assert settings.SECRET_KEY not in result.stderr


def test_production_configuration_fails_closed_without_allowed_hosts() -> None:
    environment = _production_environment()
    environment.pop("ALLOWED_HOSTS")

    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=settings.BASE_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert "Production requires an explicit ALLOWED_HOSTS" in result.stderr


def test_sensitive_log_filter_redacts_tokens_and_credentials() -> None:
    record = logging.LogRecord(
        name="security",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=(
            "GET /accounts/password/reset/confirm/MQ/private-reset-token/ "
            "Authorization=secret-header Bearer private.jwt.value password=hunter2"
        ),
        args=(),
        exc_info=None,
    )

    assert SensitiveDataFilter().filter(record) is True
    message = record.getMessage()
    assert "private-reset-token" not in message
    assert "private.jwt.value" not in message
    assert "secret-header" not in message
    assert "hunter2" not in message
    assert message.count("[REDACTED]") == 4


def test_json_formatter_emits_parseable_minimal_event() -> None:
    record = logging.LogRecord(
        name="file_operations",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="upload_success user_id=7 file_id=abc",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "file_operations"
    assert payload["message"] == "upload_success user_id=7 file_id=abc"
    assert payload["timestamp"].endswith("+00:00")
    assert set(payload) == {"timestamp", "level", "logger", "message"}


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        },
    }
)
def test_collectstatic_builds_manifest_without_touching_private_media(
    tmp_path, settings
) -> None:
    static_root = tmp_path / "collected-static"
    media_root = tmp_path / "private-uploads"
    settings.STATIC_ROOT = static_root
    settings.MEDIA_ROOT = media_root

    call_command("collectstatic", interactive=False, verbosity=0, clear=True)

    assert (static_root / "staticfiles.json").is_file()
    assert list(static_root.glob("console/js/file-search.*.js"))
    assert media_root.exists() is False


def test_static_and_private_media_roots_are_separate() -> None:
    assert settings.STATIC_ROOT.resolve() != settings.MEDIA_ROOT.resolve()
    assert not settings.MEDIA_ROOT.resolve().is_relative_to(
        settings.STATIC_ROOT.resolve()
    )
    assert not settings.STATIC_ROOT.resolve().is_relative_to(
        settings.MEDIA_ROOT.resolve()
    )


def test_gunicorn_configuration_has_bounded_provider_neutral_defaults() -> None:
    config_path = settings.BASE_DIR / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("gunicorn_config", config_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.bind == "0.0.0.0:8000"
    assert module.workers > 0
    assert module.threads > 0
    assert module.timeout > 0
    assert module.max_requests > 0
    assert module.accesslog is None
    assert module.wsgi_app == "django_filemanagement.wsgi:application"


def test_container_and_dependency_artifacts_are_safe_and_complete() -> None:
    dockerfile = (settings.BASE_DIR / "Dockerfile").read_text()
    dockerignore = (settings.BASE_DIR / ".dockerignore").read_text().splitlines()
    requirements = (settings.BASE_DIR / "requirements.txt").read_text()
    production_requirements = (settings.BASE_DIR / "requirements-prod.txt").read_text()

    assert "USER app" in dockerfile
    assert 'CMD ["gunicorn", "--config", "gunicorn.conf.py"]' in dockerfile
    assert "python:3.12-slim" in dockerfile
    assert ".env" in dockerignore
    assert "db.sqlite3" in dockerignore
    assert "uploads" in dockerignore
    assert "-r requirements-prod.txt" in requirements
    assert "pytest" not in production_requirements
    assert "black" not in production_requirements
    assert "gunicorn" in production_requirements
    assert "psycopg[binary]" in production_requirements
