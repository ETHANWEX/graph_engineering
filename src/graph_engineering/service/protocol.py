"""Provider-neutral local IPC envelopes and compatibility constants."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RUNTIME_API_VERSION = "1.0"
IPC_VERSION: Literal["1.0"] = "1.0"
MCP_TOOLS_VERSION = "1.0"
MAX_FRAME_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 64 * 1024


class ServiceErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    IDENTITY_MISMATCH = "identity_mismatch"
    INCOMPATIBLE_VERSION = "incompatible_version"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    EXPIRED = "expired"
    UNCERTAIN_EFFECT = "uncertain_effect"
    INTERNAL = "internal"


class ServiceError(RuntimeError):
    def __init__(self, code: ServiceErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class IPCRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal["1.0"]
    request_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=256)
    project_id: str = Field(min_length=1, max_length=256)
    workspace_id: str = Field(min_length=1, max_length=128)
    operation: Literal["health", "start", "message", "confirm", "status", "report", "shutdown"]
    authorization: str = Field(min_length=32, max_length=256, repr=False)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def payload_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_FRAME_BYTES // 2:
            raise ValueError("payload exceeded the byte limit")
        for item in value.values():
            if isinstance(item, str) and len(item) > MAX_TEXT_CHARS:
                raise ValueError("payload string exceeded the character limit")
        return value

    def fingerprint(self) -> str:
        document = self.model_dump(exclude={"authorization", "request_id"})
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


class IPCError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ServiceErrorCode
    message: str


class IPCResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal["1.0"] = IPC_VERSION
    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: IPCError | None = None

    @classmethod
    def success(cls, request_id: str, result: dict[str, Any]) -> IPCResponse:
        return cls(request_id=request_id, ok=True, result=result)

    @classmethod
    def failure(cls, request_id: str, code: ServiceErrorCode, message: str) -> IPCResponse:
        return cls(request_id=request_id, ok=False, error=IPCError(code=code, message=message))


def major(version: str) -> int:
    try:
        return int(version.split(".", 1)[0])
    except (ValueError, IndexError) as exc:
        raise ServiceError(ServiceErrorCode.INCOMPATIBLE_VERSION, "invalid version") from exc
