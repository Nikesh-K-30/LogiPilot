from __future__ import annotations

import pytest

from app.config import get_settings
from app.db import Database, reset_db_singleton
from database.seed import seed


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("LOGIPILOT_DATABASE_PATH", str(path))
    get_settings.cache_clear()
    reset_db_singleton()
    database = Database(path=path)
    seed(db=database, reset=True)
    reset_db_singleton()
    yield Database(path=path)
    get_settings.cache_clear()
    reset_db_singleton()
