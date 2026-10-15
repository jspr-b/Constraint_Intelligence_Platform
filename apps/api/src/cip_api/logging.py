"""Structured JSON logs. Logs carry ids, counts and timings, never plant data values (ADR-0005)."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

ALLOWED_EXTRA = ("method", "path", "status", "duration_ms", "tenant_id", "request_id")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "at": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in ALLOWED_EXTRA:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("cip")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
