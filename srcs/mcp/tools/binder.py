"""
File: binder.py
Purpose: Workbinder artifacts: listing, retrieval and typed artifact getters.
Category: Utility
Author: artdaq team
Depends: workbinder
Exports: register
Complexity: Medium | Lines: 241
"""

from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING
from mcp.server.fastmcp import FastMCP
from srcs.workbinder import BinderStore
from ..context import _enum_or_str, _json_default, get_db_path
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_binders(status: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        binders = await store.list_binders(status=status, limit=limit)
        return json.dumps(binders, default=_json_default, indent=2)

    @mcp.tool()
    async def get_binder(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        binder = await store.load_binder(binder_id)
        if not binder:
            return json.dumps({'error': f'Binder not found: {binder_id}'})
        counts = await store.get_artifact_count(binder_id)
        return json.dumps({'id': binder.id, 'investigation_id': binder.investigation_id, 'status': binder.status, 'created_at': binder.created_at.isoformat(), 'updated_at': binder.updated_at.isoformat(), 'artifact_counts': counts}, default=_json_default, indent=2)

    @mcp.tool()
    async def get_binder_summary(investigation_id: str) -> str:
        store = BinderStore(get_db_path())
        summary = await store.get_investigation_summary(investigation_id)
        if not summary:
            return json.dumps({'error': f'No binder found for investigation: {investigation_id}'})
        return json.dumps(summary, default=_json_default, indent=2)

    @mcp.tool()
    async def get_binder_by_investigation(investigation_id: str) -> str:
        store = BinderStore(get_db_path())
        binder = await store.load_binder_for_investigation(investigation_id)
        if not binder:
            return json.dumps({'error': f'No binder found for investigation: {investigation_id}'})
        return json.dumps({'binder_id': binder.id, 'investigation_id': binder.investigation_id, 'status': binder.status}, default=_json_default, indent=2)

    @mcp.tool()
    async def search_artifacts(binder_id: str, artifact_type: str | None=None, phase: int | None=None, function_name: str | None=None, tags: str | None=None, include_deleted: bool=False, limit: int=100, offset: int=0) -> str:
        store = BinderStore(get_db_path())
        tag_list = [t.strip() for t in tags.split(',')] if tags else None
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type=artifact_type, phase=phase, function_name=function_name, tags=tag_list, include_deleted=include_deleted, limit=limit, offset=offset)
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_artifact(binder_id: str, artifact_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, include_deleted=True, limit=1000)
        for artifact in artifacts:
            if artifact.id == artifact_id:
                return json.dumps(artifact.model_dump(mode='json'), default=_json_default, indent=2)
        return json.dumps({'error': f'Artifact not found: {artifact_id}'})

    @mcp.tool()
    async def get_artifact_history(binder_id: str, artifact_id: str) -> str:
        store = BinderStore(get_db_path())
        binder = await store.load_binder(binder_id)
        if not binder:
            return json.dumps({'error': f'Binder not found: {binder_id}'})
        history = [h for h in binder._history if h.artifact_id == artifact_id]
        return json.dumps([h.model_dump(mode='json') for h in history], default=_json_default, indent=2)

    @mcp.tool()
    async def search_artifact_content(binder_id: str, query: str, artifact_types: str | None=None) -> str:
        store = BinderStore(get_db_path())
        type_list = [t.strip() for t in artifact_types.split(',')] if artifact_types else None
        artifacts = await store.search_artifacts(binder_id=binder_id, query=query, artifact_types=type_list)
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_investigation_state(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        state = await store.get_investigation_state_artifact(binder_id)
        if not state:
            return json.dumps({'error': f'No investigation state found for binder: {binder_id}'})
        return json.dumps(state.model_dump(mode='json'), default=_json_default, indent=2)

    @mcp.tool()
    async def get_phase_states(binder_id: str, status: str | None=None) -> str:
        store = BinderStore(get_db_path())
        states = await store.get_phase_states(binder_id=binder_id, status=status)
        return json.dumps([s.model_dump(mode='json') for s in states], default=_json_default, indent=2)

    @mcp.tool()
    async def list_investigations_with_state(outcome: str | None=None, status: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        investigations = await store.list_investigations_with_state(outcome=outcome, status=status, limit=limit)
        return json.dumps(investigations, default=_json_default, indent=2)

    @mcp.tool()
    async def get_error_context(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='error_context', limit=1)
        if not artifacts:
            return json.dumps({'error': f'No error context found for binder: {binder_id}'})
        return json.dumps(artifacts[0].model_dump(mode='json'), default=_json_default, indent=2)

    @mcp.tool()
    async def get_flow_config(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='flow_config', limit=1)
        if not artifacts:
            return json.dumps({'error': f'No flow config found for binder: {binder_id}'})
        return json.dumps(artifacts[0].model_dump(mode='json'), default=_json_default, indent=2)

    @mcp.tool()
    async def get_log_bundle(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='log_bundle', limit=1)
        if not artifacts:
            return json.dumps({'error': f'No log bundle found for binder: {binder_id}'})
        return json.dumps(artifacts[0].model_dump(mode='json'), default=_json_default, indent=2)

    @mcp.tool()
    async def get_merged_timeline(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='merged_timeline', limit=1)
        if not artifacts:
            return json.dumps({'error': f'No merged timeline found for binder: {binder_id}'})
        return json.dumps(artifacts[0].model_dump(mode='json'), default=_json_default, indent=2)

    @mcp.tool()
    async def get_findings(binder_id: str, persona: str | None=None, finding_type: str | None=None, min_confidence: float | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='finding', limit=limit)
        if persona:
            artifacts = [a for a in artifacts if getattr(a, 'persona', None) == persona]
        if finding_type:
            artifacts = [a for a in artifacts if _enum_or_str(getattr(a, 'finding_type', None)) == finding_type]
        if min_confidence is not None:
            artifacts = [a for a in artifacts if getattr(a, 'confidence', 0.0) >= min_confidence]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_contributions(binder_id: str, persona_id: str | None=None, contribution_phase: int | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='persona_contribution', limit=limit)
        if persona_id:
            artifacts = [a for a in artifacts if getattr(a, 'persona_id', None) == persona_id]
        if contribution_phase is not None:
            artifacts = [a for a in artifacts if getattr(a, 'contribution_phase', None) == contribution_phase]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_source_locations(binder_id: str, file_path: str | None=None, min_match_score: float | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='source_location', limit=limit)
        if file_path:
            artifacts = [a for a in artifacts if file_path in getattr(a, 'file_path', '')]
        if min_match_score is not None:
            artifacts = [a for a in artifacts if getattr(a, 'match_score', 0.0) >= min_match_score]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_code_snippets(binder_id: str, file_path: str | None=None, language: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='code_snippet', limit=limit)
        if file_path:
            artifacts = [a for a in artifacts if file_path in getattr(a, 'file_path', '')]
        if language:
            artifacts = [a for a in artifacts if getattr(a, 'language', '') == language]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_call_graphs(binder_id: str, center_function: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='call_graph', limit=limit)
        if center_function:
            artifacts = [a for a in artifacts if getattr(a, 'center_function', None) == center_function]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_function_summaries(binder_id: str, center_function: str | None=None, role: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='function_summary', limit=limit)
        if center_function:
            artifacts = [a for a in artifacts if getattr(a, 'center_function', None) == center_function]
        if role:
            artifacts = [a for a in artifacts if getattr(a, 'role', None) == role]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_annotations(binder_id: str, target_artifact_id: str | None=None, annotation_type: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='annotation', limit=limit)
        if target_artifact_id:
            artifacts = [a for a in artifacts if getattr(a, 'target_artifact_id', None) == target_artifact_id]
        if annotation_type:
            artifacts = [a for a in artifacts if _enum_or_str(getattr(a, 'annotation_type', None)) == annotation_type]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_boardreader_identifications(binder_id: str, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='boardreader_identification', limit=limit)
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_feedback(binder_id: str, was_correct: bool | None=None, feedback_source: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='feedback', limit=limit)
        if was_correct is not None:
            artifacts = [a for a in artifacts if getattr(a, 'was_correct', None) == was_correct]
        if feedback_source:
            artifacts = [a for a in artifacts if getattr(a, 'feedback_source', None) == feedback_source]
        return json.dumps([a.model_dump(mode='json') for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def list_resumable_investigations() -> str:
        store = BinderStore(get_db_path())
        try:
            resumable = await store.list_resumable_investigations()
            return json.dumps(resumable, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to list resumable investigations')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def validate_binder(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        try:
            binder = await store.load_binder(binder_id)
            if not binder:
                return json.dumps({'error': f'Binder not found: {binder_id}'})
            try:
                await store.validate_references(binder_id)
                return json.dumps({'binder_id': binder_id, 'valid': True, 'errors': []}, indent=2)
            except ValueError as e:
                error_lines = str(e).split('\n')
                errors = [line.strip().lstrip('- ') for line in error_lines[1:] if line.strip().startswith('-')]
                return json.dumps({'binder_id': binder_id, 'valid': False, 'errors': errors}, indent=2)
        except Exception as e:
            logger.exception('Failed to validate binder')
            return json.dumps({'error': str(e)}, indent=2)