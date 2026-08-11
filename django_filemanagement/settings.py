"""Django settings for the Enterprise File Manager project."""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    """Read a conventional boolean value from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable."""
    return [
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    ]


def env_path(name: str, default: Path) -> Path:
    """Read a path while treating an unset or empty value as the default."""
    value = os.environ.get(name, "").strip()
    return Path(value) if value else default


def env_int(name: str, default: int) -> int:
    """Read an integer while treating an unset or empty value as the default."""
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def database_config_from_url(value: str) -> dict:
    """Build a Django database config without coupling to a hosting provider."""
    if not value:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme in {"postgres", "postgresql"}:
        database_name = unquote(parsed.path.lstrip("/"))
        if not database_name:
            raise ImproperlyConfigured("DATABASE_URL must include a database name.")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ImproperlyConfigured(
                "DATABASE_URL contains an invalid port."
            ) from exc
        config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": database_name,
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(port or ""),
        }
        options = dict(parse_qsl(parsed.query, keep_blank_values=False))
        if options:
            config["OPTIONS"] = options
        return config

    if scheme == "sqlite":
        if parsed.netloc:
            raise ImproperlyConfigured("SQLite DATABASE_URL must not include a host.")
        raw_path = unquote(parsed.path)
        if raw_path in {"/:memory:", ":memory:"}:
            name = ":memory:"
        elif raw_path.startswith("//"):
            name = raw_path[1:]
        else:
            name = BASE_DIR / raw_path.lstrip("/")
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name}

    raise ImproperlyConfigured(
        "DATABASE_URL must use postgresql://, postgres://, or sqlite://."
    )


DEVELOPMENT_SECRET_KEY = "django-insecure-development-only-change-before-production"
SECRET_KEY = os.environ.get("SECRET_KEY", DEVELOPMENT_SECRET_KEY)
DEBUG = env_bool("DEBUG", default=True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
APPLICATION_VERSION = os.environ.get("APPLICATION_VERSION", "1.0")

if not DEBUG:
    if SECRET_KEY == DEVELOPMENT_SECRET_KEY or len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            "Production requires a SECRET_KEY of at least 50 characters."
        )
    if not os.environ.get("ALLOWED_HOSTS", "").strip():
        raise ImproperlyConfigured("Production requires an explicit ALLOWED_HOSTS.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "accounts.apps.AccountsConfig",
    "files.apps.FilesConfig",
    "user_console.apps.UserConsoleConfig",
    "core.apps.CoreConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_filemanagement.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "django_filemanagement.wsgi.application"
ASGI_APPLICATION = "django_filemanagement.asgi.application"

DATABASES = {"default": database_config_from_url(os.environ.get("DATABASE_URL", ""))}
DATABASES["default"]["CONN_MAX_AGE"] = env_int(
    "DATABASE_CONN_MAX_AGE", 60 if not DEBUG else 0
)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = env_bool(
    "DATABASE_CONN_HEALTH_CHECKS", default=not DEBUG
)

CACHES = {
    "default": {
        "BACKEND": os.environ.get(
            "CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"
        ),
        "LOCATION": os.environ.get("CACHE_LOCATION", "file-manager-cache"),
        "TIMEOUT": env_int("CACHE_TIMEOUT", 300),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:profile"
LOGOUT_REDIRECT_URL = "accounts:login"
PASSWORD_RESET_TIMEOUT = env_int("PASSWORD_RESET_TIMEOUT", 60 * 60)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31_536_000 if not DEBUG else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False
)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=False)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", default=False)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env_bool("TRUST_X_FORWARDED_PROTO", default=False)
    else None
)

DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 2_621_440)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 2_621_440)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env_int("DATA_UPLOAD_MAX_NUMBER_FIELDS", 1_000)

SECURITY_RATE_LIMITS = {
    "registration": (env_int("REGISTRATION_RATE_LIMIT", 20), 300),
    "login": (env_int("LOGIN_RATE_LIMIT", 20), 300),
    "password_reset": (env_int("PASSWORD_RESET_RATE_LIMIT", 20), 3600),
    "file_upload": (env_int("FILE_UPLOAD_RATE_LIMIT", 60), 60),
    "file_search": (env_int("FILE_SEARCH_RATE_LIMIT", 120), 60),
}

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_RATES": {
        "token": os.environ.get("TOKEN_API_THROTTLE_RATE", "20/minute"),
        "file_upload": os.environ.get("FILE_UPLOAD_API_THROTTLE_RATE", "60/minute"),
        "file_search": os.environ.get("FILE_SEARCH_API_THROTTLE_RATE", "120/minute"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = env_path("STATIC_ROOT", BASE_DIR / "staticfiles")
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        )
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = env_path("MEDIA_ROOT", BASE_DIR / "uploads")

static_root_resolved = STATIC_ROOT.resolve()
media_root_resolved = MEDIA_ROOT.resolve()
if static_root_resolved == media_root_resolved or (
    static_root_resolved.is_relative_to(media_root_resolved)
    or media_root_resolved.is_relative_to(static_root_resolved)
):
    raise ImproperlyConfigured("STATIC_ROOT and MEDIA_ROOT must not overlap.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOG_FORMAT = os.environ.get("LOG_FORMAT", "standard" if DEBUG else "json").lower()
if LOG_FORMAT not in {"standard", "json"}:
    raise ImproperlyConfigured("LOG_FORMAT must be 'standard' or 'json'.")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
        "json": {"()": "core.logging.JsonFormatter"},
    },
    "filters": {
        "redact_sensitive": {"()": "core.logging.SensitiveDataFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "filters": ["redact_sensitive"],
        }
    },
    "loggers": {
        category: {
            "handlers": ["console"],
            "level": os.environ.get("LOG_LEVEL", "INFO"),
            "propagate": False,
        }
        for category in (
            "authentication",
            "file_operations",
            "security",
            "performance",
            "errors",
            "admin",
        )
    }
    | {
        "django.request": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
    },
}
