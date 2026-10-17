from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from app.agents.mcp_tools import LOADLINK_TOOLS, logistics_mcp_toolset
from app.config import get_settings


def _instruction() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "loadlink.md"
    return path.read_text(encoding="utf-8")


def build_loadlink_agent() -> LlmAgent:
    settings = get_settings()
    return LlmAgent(
        name="loadlink_agent",
        model=settings.gemini_model,
        description=(
            "Matches shipments to vehicles and spare corridor capacity "
            "(logistics pooling / LoadLink)."
        ),
        instruction=_instruction(),
        tools=[logistics_mcp_toolset(tool_filter=LOADLINK_TOOLS)],
    )
