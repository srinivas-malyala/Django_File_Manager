"""ASGI config for django_filemanagement."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_filemanagement.settings")

application = get_asgi_application()
