"""Minimal MCP stdio adapter for the five Phase 6A Human Gateway tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from graph_engineering.service import MCP_TOOLS_VERSION, ServiceClient, ServiceError

MIN_CODEX_VERSION = "0.147.0"
_COMMON_ID = {"type": "string", "minLength": 1, "maxLength": 256}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "start",
        "description": "Start or resume a persistent Graph Engineering Human Conversation.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_id", "actor_id"],
            "properties": {
                "project_id": _COMMON_ID,
                "actor_id": _COMMON_ID,
                "conversation_id": _COMMON_ID,
            },
        },
    },
    {
        "name": "message",
        "description": "Persist a HumanMessage and route it through the Intent Compiler.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["conversation_id", "content"],
            "properties": {
                "conversation_id": _COMMON_ID,
                "content": {"type": "string", "minLength": 1, "maxLength": 65536},
                "message_id": _COMMON_ID,
                "run_id": _COMMON_ID,
                "project_id": _COMMON_ID,
                "actor_id": _COMMON_ID,
            },
        },
    },
    {
        "name": "confirm",
        "description": "Confirm one persisted, authorized, compatible, unexpired pending action.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["conversation_id", "confirmation_id", "content"],
            "properties": {
                "conversation_id": _COMMON_ID,
                "confirmation_id": _COMMON_ID,
                "content": {"type": "string", "minLength": 1, "maxLength": 65536},
                "message_id": _COMMON_ID,
                "project_id": _COMMON_ID,
                "actor_id": _COMMON_ID,
            },
        },
    },
    {
        "name": "status",
        "description": "Read persisted Run status without changing execution state.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"run_id": _COMMON_ID, "conversation_id": _COMMON_ID},
            "anyOf": [{"required": ["run_id"]}, {"required": ["conversation_id"]}],
        },
    },
    {
        "name": "report",
        "description": "Read the latest immutable delivery report without mutation.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"run_id": _COMMON_ID, "conversation_id": _COMMON_ID},
            "anyOf": [{"required": ["run_id"]}, {"required": ["conversation_id"]}],
        },
    },
]


class MCPServer:
    def __init__(self, project_root: Path) -> None:
        self.client = ServiceClient(project_root)

    def serve(self) -> None:
        for line in sys.stdin.buffer:
            if not line.strip():
                continue
            response: dict[str, Any] | None
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                response = self._error(None, -32700, "invalid JSON")
            else:
                response = self.handle(request)
            if response is not None:
                encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
                sys.stdout.write(encoded + "\n")
                sys.stdout.flush()

    def handle(self, request: object) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return self._error(None, -32600, "invalid JSON-RPC request")
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None and isinstance(method, str) and method.startswith("notifications/"):
            return None
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return self._error(request_id, -32600, "invalid JSON-RPC request")
        if method == "initialize":
            params = request.get("params")
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            client_info = params.get("clientInfo") if isinstance(params, dict) else None
            if (
                isinstance(client_info, dict)
                and "codex" in str(client_info.get("name", "")).casefold()
            ):
                client_version = str(client_info.get("version", "0"))
                if self._version_tuple(client_version) < self._version_tuple(MIN_CODEX_VERSION):
                    return self._error(
                        request_id,
                        -32001,
                        f"Codex host {MIN_CODEX_VERSION} or newer is required",
                    )
            return self._result(
                request_id,
                {
                    "protocolVersion": requested or "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "graph-engineering",
                        "version": MCP_TOOLS_VERSION,
                    },
                },
            )
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict) or params.get("name") not in {
                tool["name"] for tool in TOOLS
            }:
                return self._error(request_id, -32602, "unknown Graph Engineering tool")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                return self._error(request_id, -32602, "tool arguments must be an object")
            tool = next(tool for tool in TOOLS if tool["name"] == params["name"])
            problem = self._validate_arguments(tool["inputSchema"], arguments)
            if problem is not None:
                return self._error(request_id, -32602, problem)
            try:
                result = self.client.call(str(params["name"]), arguments)
                return self._result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False, sort_keys=True),
                            }
                        ],
                        "isError": False,
                    },
                )
            except (ServiceError, ConnectionError, RuntimeError) as exc:
                return self._result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": str(exc)[:1000]}],
                        "isError": True,
                    },
                )
        return self._error(request_id, -32601, "method not found")

    @staticmethod
    def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return "invalid internal tool schema"
        unknown = set(arguments) - set(properties)
        if unknown:
            return "tool arguments contain unsupported fields"
        required = schema.get("required", [])
        if any(name not in arguments for name in required):
            return "tool arguments are missing a required field"
        any_of = schema.get("anyOf")
        if isinstance(any_of, list) and not any(
            all(name in arguments for name in choice.get("required", []))
            for choice in any_of
            if isinstance(choice, dict)
        ):
            return "tool arguments are missing a target identity"
        for name, value in arguments.items():
            rule = properties[name]
            if not isinstance(value, str) or not value:
                return f"{name} must be a non-empty string"
            if isinstance(rule, dict) and len(value) > int(rule.get("maxLength", 65536)):
                return f"{name} exceeded its character limit"
        return None

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, int, int]:
        try:
            pieces = tuple(int(piece) for piece in value.split(".")[:3])
        except ValueError:
            return (0, 0, 0)
        padded = [*pieces, 0, 0, 0]
        return (padded[0], padded[1], padded[2])

    @staticmethod
    def _result(request_id: object, value: object) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": value}

    @staticmethod
    def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def run_mcp_server(project_root: Path) -> None:
    MCPServer(project_root.resolve()).serve()
