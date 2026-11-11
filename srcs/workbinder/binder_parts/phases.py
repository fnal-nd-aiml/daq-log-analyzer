"""
File: phases.py
Purpose: Investigation and per-phase state machine.
Category: Utility
Author: artdaq team
Depends: None
Exports: PhaseStateMixin
Complexity: Medium | Lines: 100
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from ..artifacts import EvidenceArtifact, Finding, HypothesisArtifact, InvestigationStateArtifact, PhaseStateArtifact
from ._state import BinderState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class PhaseStateMixin(BinderState):

    def get_investigation_state(self) -> InvestigationStateArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, InvestigationStateArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def update_investigation_state(self, modified_by: str='system', **updates: Any) -> bool:
        state = self.get_investigation_state()
        if not state:
            return False
        return self.update_artifact(state.id, updates, modified_by)

    def get_phase_state(self, phase: int) -> PhaseStateArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, PhaseStateArtifact) and artifact.phase_number == phase and (not artifact.is_deleted):
                return artifact
        return None

    def start_phase(self, phase: int, persona_name: str) -> str:
        existing = self.get_phase_state(phase)
        if existing:
            self.update_artifact(existing.id, {'status': 'in_progress', 'started_at': datetime.now()}, persona_name)
            return existing.id
        artifact = PhaseStateArtifact(phase_number=phase, persona_name=persona_name, status='in_progress', started_at=datetime.now(), created_by=persona_name, phase=phase)
        return self.add_artifact(artifact)

    def complete_phase(self, phase: int, output_ids: list[str], modified_by: str='system') -> None:
        state = self.get_phase_state(phase)
        if state:
            self.update_artifact(state.id, {'status': 'completed', 'completed_at': datetime.now(), 'output_artifact_ids': output_ids}, modified_by)
        inv_state = self.get_investigation_state()
        if inv_state and inv_state.current_phase == phase:
            self.update_artifact(inv_state.id, {'current_phase': phase + 1}, modified_by)

    def fail_phase(self, phase: int, error_message: str, modified_by: str='system') -> None:
        state = self.get_phase_state(phase)
        if state:
            self.update_artifact(state.id, {'status': 'failed', 'completed_at': datetime.now(), 'error_message': error_message}, modified_by)

    def pause_investigation(self, reason: str, modified_by: str='system') -> None:
        inv_state = self.get_investigation_state()
        if inv_state:
            self.update_artifact(inv_state.id, {'status': 'paused', 'paused_at': datetime.now(), 'pause_reason': reason}, modified_by)
        self.status = 'paused'

    def can_resume(self) -> bool:
        state = self.get_investigation_state()
        return state is not None and state.status == 'paused'

    def get_resume_point(self) -> tuple[int, dict[str, Any]]:
        if not self.can_resume():
            raise ValueError('Investigation cannot be resumed - not in paused state')
        inv_state = self.get_investigation_state()
        if not inv_state:
            raise ValueError('No investigation state found')
        resume_phase = inv_state.current_phase
        current_phase_state = self.get_phase_state(resume_phase)
        if current_phase_state and current_phase_state.status == 'in_progress':
            pass
        elif resume_phase > 0:
            prev_state = self.get_phase_state(resume_phase - 1)
            if prev_state and prev_state.status != 'completed':
                resume_phase = resume_phase - 1
        resume_context = self._build_resume_context(resume_phase)
        return (resume_phase, resume_context)

    def _build_resume_context(self, phase: int) -> dict[str, Any]:
        context: dict[str, Any] = {'phase': phase, 'hypotheses': [], 'evidence': [], 'findings': []}
        for artifact in self._artifacts.values():
            if artifact.is_deleted:
                continue
            if isinstance(artifact, HypothesisArtifact):
                context['hypotheses'].append(artifact.model_dump())
            elif isinstance(artifact, EvidenceArtifact):
                context['evidence'].append(artifact.model_dump())
            elif isinstance(artifact, Finding):
                context['findings'].append(artifact.model_dump())
        return context

    def resume_investigation(self, modified_by: str='system') -> int:
        if not self.can_resume():
            raise ValueError('Investigation cannot be resumed')
        resume_phase, _ = self.get_resume_point()
        inv_state = self.get_investigation_state()
        if inv_state:
            self.update_artifact(inv_state.id, {'status': 'active', 'paused_at': None, 'pause_reason': None, 'resume_count': inv_state.resume_count + 1}, modified_by)
        self.status = 'active'
        return resume_phase