"""
File: _state.py
Purpose: Attribute and cross-mixin declarations shared by the WorkBinder mix...
Category: Utility
Author: artdaq team
Depends: None
Exports: BinderState
Complexity: Low | Lines: 44
"""

from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from ..artifacts import Artifact, ArtifactHistory, ArtifactType, AuditLogEntry, InvestigationStateArtifact, PhaseStateArtifact

class BinderState:
    id: str
    investigation_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    _artifacts: dict[str, Artifact]
    _history: list[ArtifactHistory]
    _tags_index: dict[str, set[str]]
    _function_index: dict[str, set[str]]
    _audit_log: list[AuditLogEntry]
    _access_sequence: int
    _audit_persona: str | None
    _audit_phase: int | None

    def add_artifact(self, artifact: Artifact, record_history: bool=True) -> str:
        raise NotImplementedError

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        raise NotImplementedError

    def update_artifact(self, artifact_id: str, updates: dict[str, Any], modified_by: str) -> bool:
        raise NotImplementedError

    def get_by_type(self, artifact_type: ArtifactType) -> list[Artifact]:
        raise NotImplementedError

    def _log_access(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError

    def _get_audit_context(self) -> tuple[str, int | None]:
        raise NotImplementedError

    def get_investigation_state(self) -> InvestigationStateArtifact | None:
        raise NotImplementedError

    def get_phase_state(self, phase: int) -> PhaseStateArtifact | None:
        raise NotImplementedError