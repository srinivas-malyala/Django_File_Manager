"""Consistent API envelope helpers."""

from datetime import datetime, timezone


def envelope(data=None, message: str = "Request completed successfully") -> dict:
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
