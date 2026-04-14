"""
File: errors.py
Purpose: Structured error types for the agentic API.
Category: Utility
Author: artdaq team
Depends: None
Exports: AgentAPIError, session_not_found, session_closed, tool_not_found, tool_execution_error, ...
Complexity: Low | Lines: 70
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from fastapi.responses import JSONResponse


@dataclass
class AgentAPIError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)
    recovery_hint: str | None = None

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def session_not_found(session_id: str) -> AgentAPIError:
    return AgentAPIError(
        code="SESSION_NOT_FOUND",
        message=f"Session '{session_id}' does not exist or has expired.",
        status_code=404,
        recovery_hint="Create a new session with POST /api/v1/agent/sessions.",
    )


def session_closed(session_id: str) -> AgentAPIError:
    return AgentAPIError(
        code="SESSION_CLOSED",
        message=f"Session '{session_id}' has been closed.",
        status_code=409,
        recovery_hint="Create a new session with POST /api/v1/agent/sessions.",
    )


def tool_not_found(tool_name: str) -> AgentAPIError:
    return AgentAPIError(
        code="TOOL_NOT_FOUND",
        message=f"Tool '{tool_name}' is not registered.",
        status_code=404,
        details={"tool_name": tool_name},
        recovery_hint="Use GET /api/v1/agent/tools to list available tools.",
    )


def tool_execution_error(tool_name: str, detail: str) -> AgentAPIError:
    return AgentAPIError(
        code="TOOL_EXECUTION_ERROR",
        message=f"Tool '{tool_name}' failed: {detail}",
        status_code=500,
        details={"tool_name": tool_name},
    )


def validation_error(message: str, details: dict[str, Any] | None = None) -> AgentAPIError:
    return AgentAPIError(code="VALIDATION_ERROR", message=message, status_code=422, details=details or {})


def internal_error(message: str) -> AgentAPIError:
    return AgentAPIError(code="INTERNAL_ERROR", message=message, status_code=500)


def agent_error_response(exc: AgentAPIError) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
    if exc.details:
        body["error"]["details"] = exc.details
    if exc.recovery_hint:
        body["error"]["recovery_hint"] = exc.recovery_hint
    return JSONResponse(status_code=exc.status_code, content=body)
