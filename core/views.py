"""Core public views."""

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

errors_logger = logging.getLogger("errors")


def index(request: HttpRequest) -> HttpResponse:
    """Render an authentication-aware entry point into the file workflow."""
    return render(request, "core/index.html")


def custom_404(request: HttpRequest, exception=None) -> HttpResponse:
    """Render a safe not-found page without reflecting exception details."""
    return render(request, "errors/404.html", status=404)


def custom_500(request: HttpRequest) -> HttpResponse:
    """Render a generic server-error page without exposing internals."""
    errors_logger.error("unhandled_server_error")
    return render(request, "errors/500.html", status=500)
