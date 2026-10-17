from __future__ import annotations

import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

ROOT = Path(__file__).resolve().parents[2]


def logistics_mcp_toolset(*, tool_filter: list[str] | None = None) -> McpToolset:
    """Connect ADK agents to the local logistics MCP server (stdio)."""
    server = ROOT / "mcp_servers" / "logistics_server.py"
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[str(server)],
                cwd=str(ROOT),
                env=None,
            ),
            timeout=30,
        ),
        tool_filter=tool_filter,
    )


LOADLINK_TOOLS = [
    "get_vehicle",
    "list_available_vehicles",
    "get_shipment",
    "list_unassigned_shipments",
    "list_shipments",
    "get_route",
    "get_distance_matrix",
    "match_shipments_to_vehicles",
    "estimate_match_cost",
    "create_match_run",
    "assign_shipment_to_vehicle",
]

ROUTEWISE_TOOLS = [
    "get_delivery_stops",
    "get_vehicle",
    "get_route",
    "get_distance_matrix",
    "optimize_route",
    "compare_routes",
]
