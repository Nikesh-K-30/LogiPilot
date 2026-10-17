from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings


def ok(data: Any, *, source: str = "logistics_database") -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "data": data,
        "error": None,
        "source": source,
        "trace_id": str(uuid.uuid4()),
        "data_class": settings.data_class,
    }


def err(code: str, message: str, *, source: str = "logistics_database") -> dict:
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message},
        "source": source,
        "trace_id": str(uuid.uuid4()),
        "data_class": get_settings().data_class,
    }
