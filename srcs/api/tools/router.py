"""
File: router.py
Purpose: Tool dispatch router for the agentic API.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: ToolContext, ToolRequest, ToolListEntry, register_tool, list_tools, ...
Complexity: Medium | Lines: 85
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from ..dependencies import get_session_store
from ..errors import AgentAPIError, tool_execution_error, tool_not_found, validation_error
from ..sessions import Session, SessionStore, ToolInvocation
logger = logging.getLogger(__name__)
router = APIRouter()

@dataclass
class ToolContext:
    session: Session
    request_body: dict[str, Any]
    raw_request: Request
ToolHandler = Callable[[ToolContext], Awaitable[dict[str, Any] | StreamingResponse]]
TOOL_REGISTRY: dict[str, ToolHandler] = {}
SESSION_LESS_TOOLS: set[str] = set()

def register_tool(name: str, *, session_less: bool=False) -> Callable[[ToolHandler], ToolHandler]:

    def decorator(fn: ToolHandler) -> ToolHandler:
        TOOL_REGISTRY[name] = fn
        if session_less:
            SESSION_LESS_TOOLS.add(name)
        return fn
    return decorator

class ToolRequest(BaseModel):
    session_id: str | None = Field(default=None, description='Session ID (required for most tools)')
    params: dict[str, Any] = Field(default_factory=dict, description='Tool-specific parameters')

class ToolListEntry(BaseModel):
    name: str
    requires_session: bool

@router.get('/tools', response_model=list[ToolListEntry])
async def list_tools() -> list[ToolListEntry]:
    return [ToolListEntry(name=name, requires_session=name not in SESSION_LESS_TOOLS) for name in sorted(TOOL_REGISTRY)]

@router.post('/tools/{tool_name}', response_model=None)
async def invoke_tool(tool_name: str, request: Request, store: SessionStore=Depends(get_session_store)) -> JSONResponse | StreamingResponse:
    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        raise tool_not_found(tool_name)
    try:
        body = await request.json()
    except ValueError:
        raise validation_error('Invalid JSON in request body', {'tool_name': tool_name})
    session_id = body.get('session_id')
    session: Session | None = None
    if tool_name not in SESSION_LESS_TOOLS:
        if not session_id:
            raise validation_error(f"Tool '{tool_name}' requires a session_id.", {'tool_name': tool_name})
        session = await store.get_or_raise(session_id)
    ctx = ToolContext(session=session, request_body=body, raw_request=request)
    start = time.time()
    invocation = ToolInvocation(tool_name=tool_name)
    try:
        result = await handler(ctx)
    except AgentAPIError:
        raise
    except Exception as e:
        logger.exception("Tool '%s' failed", tool_name)
        invocation.success = False
        invocation.error = str(e)
        if session is not None:
            invocation.duration_ms = (time.time() - start) * 1000
            session.record_tool_invocation(invocation)
        raise tool_execution_error(tool_name, str(e))
    elapsed_ms = (time.time() - start) * 1000
    invocation.duration_ms = elapsed_ms
    if isinstance(result, StreamingResponse):
        invocation.summary = 'streaming'
        if session is not None:
            session.record_tool_invocation(invocation)
        return result
    invocation.summary = f'{len(result)} keys returned'
    if session is not None:
        session.record_tool_invocation(invocation)
    return JSONResponse(content=result)