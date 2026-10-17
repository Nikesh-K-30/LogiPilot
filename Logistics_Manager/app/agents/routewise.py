from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from app.agents.mcp_tools import ROUTEWISE_TOOLS, logistics_mcp_toolset
from app.config import get_settings


def _instruction() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "routewise.md"
    return path.read_text(encoding="utf-8")


def build_routewise_agent() -> LlmAgent:
    settings = get_settings()
    return LlmAgent(
        name="routewise_agent",
        model=settings.gemini_model,
        description="Optimizes delivery routes and compares baseline vs optimized metrics.",
        instruction=_instruction(),
        tools=[logistics_mcp_toolset(tool_filter=ROUTEWISE_TOOLS)],
    )
