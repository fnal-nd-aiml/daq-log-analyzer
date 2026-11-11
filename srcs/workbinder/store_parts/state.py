"""
File: state.py
Purpose: Queries over investigation and per-phase state.
Category: Utility
Author: artdaq team
Depends: None
Exports: InvestigationStateQueriesMixin
Complexity: Low | Lines: 69
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from ..artifacts import Artifact
from ._state import StoreState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class InvestigationStateQueriesMixin(StoreState):

    async def get_investigation_state_artifact(self, binder_id: str) -> Artifact | None:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='investigation_state', limit=1)
        return artifacts[0] if artifacts else None

    async def get_phase_states(self, binder_id: str, status: str | None=None) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='phase_state', limit=20)
        if status is not None:
            result = []
            for artifact in artifacts:
                if hasattr(artifact, 'status') and artifact.status == status:
                    result.append(artifact)
            return result
        return artifacts

    async def list_investigations_with_state(self, outcome: str | None=None, status: str | None=None, limit: int=50) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        binders = await self.list_binders(status=status, limit=limit)
        results = []
        for binder_info in binders:
            binder_id = binder_info['id']
            state = await self.get_investigation_state_artifact(binder_id)
            state_info: dict[str, Any] = {'binder_id': binder_id, 'investigation_id': binder_info['investigation_id'], 'binder_status': binder_info['status'], 'created_at': binder_info['created_at'], 'updated_at': binder_info['updated_at']}
            if state:
                if hasattr(state, 'current_phase'):
                    state_info['current_phase'] = state.current_phase
                if hasattr(state, 'status'):
                    state_info['investigation_status'] = state.status
                if hasattr(state, 'outcome'):
                    state_info['outcome'] = state.outcome
            if outcome is not None:
                if state_info.get('outcome') != outcome:
                    continue
            results.append(state_info)
        return results

    async def get_similar_investigations(self, error_function: str | None=None, error_message_pattern: str | None=None, limit: int=10) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        all_binders = await self.list_binders(limit=200)
        similar = []
        for binder_info in all_binders:
            binder_id = binder_info['id']
            artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='error_context', limit=1)
            if not artifacts:
                continue
            artifact = artifacts[0]
            match_score = 0.0
            if error_function and hasattr(artifact, 'error_function'):
                if artifact.error_function == error_function:
                    match_score += 0.5
                elif error_function in str(getattr(artifact, 'error_function', '')):
                    match_score += 0.25
            if error_message_pattern and hasattr(artifact, 'error_message'):
                if error_message_pattern in str(getattr(artifact, 'error_message', '')):
                    match_score += 0.5
            if match_score > 0:
                similar.append({'binder_id': binder_id, 'investigation_id': binder_info['investigation_id'], 'match_score': match_score, 'created_at': binder_info['created_at']})
        similar.sort(key=lambda x: x['match_score'], reverse=True)
        return similar[:limit]