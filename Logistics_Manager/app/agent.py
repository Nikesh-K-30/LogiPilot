"""ADK entrypoint — `adk web` / `adk run` discover `root_agent` here."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator import build_orchestrator
from app.config import get_settings
from database.seed import seed

_settings = get_settings()
if _settings.use_sample_data and not _settings.database_path.exists():
    seed(reset=True)

root_agent = build_orchestrator()
