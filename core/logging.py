"""Structured production logging with conservative credential redaction."""

import json
import logging
import re
from datetime import UTC, datetime


class SensitiveDataFilter(logging.Filter):
    """Redact reset links, bearer credentials, and key/value secrets."""

    patterns = (
        (
            re.compile(r"(/password/reset/confirm/[^/\s]+/)[^/?\s]+"),
            r"\1[REDACTED]",
        ),
        (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]+"), "Bearer [REDACTED]"),
        (
            re.compile(
                r"(?i)\b(password|secret|token|authorization|api[_-]?key)=" r"[^\s&,;]+"
            ),
            r"\1=[REDACTED]",
        ),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in self.patterns:
            message = pattern.sub(replacement, message)
        record.msg = message
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Emit one predictable JSON object per event to stdout/stderr."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
