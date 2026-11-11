"""
File: audit.py
Purpose: Binder audit log search and summaries.
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
    async def search_audit_log(binder_id: str, persona_name: str | None=None, phase_number: int | None=None, operation_type: str | None=None, limit: int=100) -> str:
        store = BinderStore(get_db_path())
        entries = await store.get_audit_log(binder_id=binder_id, persona_name=persona_name, phase_number=phase_number, operation_type=operation_type, limit=limit)
        return json.dumps([e.model_dump(mode='json') for e in entries], default=_json_default, indent=2)

    @mcp.tool()
    async def get_artifact_audit_trail(binder_id: str, artifact_id: str) -> str:
        store = BinderStore(get_db_path())
        entries = await store.get_audit_log(binder_id=binder_id, limit=10000)
        artifact_entries = [e for e in entries if e.artifact_id == artifact_id]
        return json.dumps([e.model_dump(mode='json') for e in artifact_entries], default=_json_default, indent=2)

    @mcp.tool()
    async def get_audit_summary(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        entries = await store.get_audit_log(binder_id=binder_id, limit=100000)
        by_persona: dict[str, int] = {}
        by_phase: dict[int, int] = {}
        by_operation: dict[str, int] = {}
        for entry in entries:
            by_persona[entry.persona_name] = by_persona.get(entry.persona_name, 0) + 1
            if entry.phase_number is not None:
                by_phase[entry.phase_number] = by_phase.get(entry.phase_number, 0) + 1
            by_operation[entry.operation_type] = by_operation.get(entry.operation_type, 0) + 1
        return json.dumps({'total_entries': len(entries), 'by_persona': by_persona, 'by_phase': {str(k): v for k, v in sorted(by_phase.items())}, 'by_operation': by_operation}, default=_json_default, indent=2)