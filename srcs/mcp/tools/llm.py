"""
File: llm.py
Purpose: Recorded LLM requests, responses and usage statistics.
Category: Utility
Author: artdaq team
Depends: workbinder
Exports: register
Complexity: Low | Lines: 39
"""

from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING
from mcp.server.fastmcp import FastMCP
from srcs.workbinder import BinderStore
from ..context import _json_default, get_db_path
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_llm_requests(binder_id: str, persona: str | None=None, phase: int | None=None, prompt_key: str | None=None, limit: int=100) -> str:
        store = BinderStore(get_db_path())
        requests = await store.get_llm_requests(binder_id=binder_id, persona=persona, phase=phase, prompt_key=prompt_key, limit=limit)
        return json.dumps([r.model_dump(mode='json') for r in requests], default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_responses(binder_id: str, request_id: str | None=None, phase: int | None=None, parse_success: bool | None=None, limit: int=100) -> str:
        store = BinderStore(get_db_path())
        responses = await store.get_llm_responses(binder_id=binder_id, request_id=request_id, phase=phase, parse_success=parse_success, limit=limit)
        return json.dumps([r.model_dump(mode='json') for r in responses], default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_exchanges(binder_id: str, phase: int | None=None) -> str:
        store = BinderStore(get_db_path())
        exchanges = await store.get_llm_exchanges(binder_id=binder_id, phase=phase)
        result = []
        for req, resp in exchanges:
            result.append({'request': req.model_dump(mode='json'), 'response': resp.model_dump(mode='json') if resp else None})
        return json.dumps(result, default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_statistics(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        stats = await store.get_llm_statistics(binder_id)
        return json.dumps(stats, default=_json_default, indent=2)