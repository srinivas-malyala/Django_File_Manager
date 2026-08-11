"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def temporary_media_root(settings, tmp_path):
    """Keep all upload tests isolated from development and production media."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path
