from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_engineering.mcp_server import TOOLS, MCPServer


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((operation, payload))
        return {"operation": operation, "persisted": True}


def test_mcp_exposes_exactly_five_bounded_tools(tmp_path: Path) -> None:
    server = MCPServer(tmp_path)
    incompatible = server.handle(
        {
            "jsonrpc": "2.0",
            "id": "old-codex",
            "method": "initialize",
            "params": {"clientInfo": {"name": "codex", "version": "0.146.0"}},
        }
    )
    assert incompatible is not None
    assert incompatible["error"]["code"] == -32001
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response is not None
    tools = response["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["start", "message", "confirm", "status", "report"]
    assert tools == TOOLS
    assert all(tool["inputSchema"]["additionalProperties"] is False for tool in tools)


def test_mcp_routes_tool_call_to_service_client_without_authoritative_state(
    tmp_path: Path, load_fixture: object
) -> None:
    server = MCPServer(tmp_path)
    fake = FakeClient()
    server.client = fake  # type: ignore[assignment]
    assert callable(load_fixture)
    request = load_fixture("phase6a/mcp-start-call.json")
    response = server.handle(request)
    assert fake.calls == [
        (
            "start",
            {
                "project_id": "project",
                "actor_id": "human",
                "conversation_id": "project-main",
            },
        )
    ]
    assert response is not None
    assert response["result"]["isError"] is False


def test_mcp_rejects_unknown_missing_and_oversized_arguments(tmp_path: Path) -> None:
    server = MCPServer(tmp_path)
    for arguments in (
        {"conversation_id": "c", "content": "status", "shell": "whoami"},
        {"conversation_id": "c"},
        {"conversation_id": "c", "content": "x" * 65537},
    ):
        response = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "message", "arguments": arguments},
            }
        )
        assert response is not None
        assert response["error"]["code"] == -32602


def test_plugin_manifest_skill_and_mcp_configuration_are_repository_owned() -> None:
    root = Path(__file__).parents[1] / "plugins" / "graph-engineering"
    manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    skill = (root / "skills" / "graph-engineering" / "SKILL.md").read_text(encoding="utf-8")

    assert manifest["name"] == "graph-engineering"
    assert manifest["version"] == "0.1.0"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert mcp["mcpServers"]["graph-engineering"]["command"] == "ge"
    assert mcp["mcpServers"]["graph-engineering"]["args"] == [
        "mcp-server",
        "--project-root",
        ".",
    ]
    assert "Never edit `.ge` SQLite" in skill
    assert not (root / "state.db").exists()
