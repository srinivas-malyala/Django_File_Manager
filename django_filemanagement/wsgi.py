"""WSGI config for django_filemanagement."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_filemanagement.settings")

application = get_wsgi_application()
