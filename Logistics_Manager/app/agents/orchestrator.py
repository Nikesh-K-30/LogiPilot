from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from app.agents.loadlink import build_loadlink_agent
from app.agents.routewise import build_routewise_agent
from app.config import get_settings


def _instruction() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "orchestrator.md"
    return path.read_text(encoding="utf-8")


def build_orchestrator() -> LlmAgent:
    settings = get_settings()
    loadlink = build_loadlink_agent()
    routewise = build_routewise_agent()
    return LlmAgent(
        name="logistics_orchestrator",
        model=settings.gemini_model,
        description="Routes logistics requests to LoadLink and RouteWise specialists.",
        instruction=_instruction(),
        sub_agents=[loadlink, routewise],
    )
