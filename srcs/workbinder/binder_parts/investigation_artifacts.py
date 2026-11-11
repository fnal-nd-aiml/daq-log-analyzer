"""
File: investigation_artifacts.py
Purpose: Typed builders for investigation artifacts.
Category: Utility
Author: artdaq team
Depends: None
Exports: InvestigationArtifactsMixin
Complexity: Medium | Lines: 87
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from ..artifacts import Artifact, CausalChainArtifact, ChallengeArtifact, EvidenceArtifact, FlowConfigArtifact, HypothesisArtifact, InvestigationStateArtifact, PersonaContributionArtifact
from ._state import BinderState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class InvestigationArtifactsMixin(BinderState):

    def add_hypothesis(self, description: str, source: str='fresh', prior_probability: float=0.5, score: float=0.5, rank: int=0, llm_request_id: str | None=None, created_by: str='system', phase: int | None=None) -> str:
        artifact = HypothesisArtifact(description=description, source=source, prior_probability=prior_probability, score=score, rank=rank, llm_request_id=llm_request_id, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='hypothesis_artifact', method_name='add_hypothesis', artifact_id=artifact_id)
        return artifact_id

    def add_evidence(self, evidence_type: str, content: str, source: str, strength: str='MODERATE', llm_request_id: str | None=None, created_by: str='system', phase: int | None=None, found: bool=True, targets_hypothesis_id: str | None=None, expected_if_true: str | None=None, expected_if_false: str | None=None, tags: list[str] | None=None) -> str:
        artifact = EvidenceArtifact(evidence_type=evidence_type, content=content, source=source, strength=strength, llm_request_id=llm_request_id, created_by=created_by, phase=phase, found=found, targets_hypothesis_id=targets_hypothesis_id, expected_if_true=expected_if_true, expected_if_false=expected_if_false, tags=tags or [])
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='evidence_artifact', method_name='add_evidence', artifact_id=artifact_id)
        return artifact_id

    def artifact_exists(self, artifact_id: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        return artifact is not None and (not artifact.is_deleted)

    def validate_artifact_reference(self, artifact_id: str, expected_type: type[Artifact] | None=None, context: str='') -> Artifact:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ValueError(f"Invalid artifact reference: '{artifact_id}' does not exist{(f' ({context})' if context else '')}")
        if artifact.is_deleted:
            raise ValueError(f"Invalid artifact reference: '{artifact_id}' has been deleted{(f' ({context})' if context else '')}")
        if expected_type is not None and (not isinstance(artifact, expected_type)):
            raise ValueError(f"Invalid artifact reference: '{artifact_id}' is {type(artifact).__name__}, expected {expected_type.__name__}{(f' ({context})' if context else '')}")
        return artifact

    def link_evidence_to_hypothesis(self, evidence_id: str, hypothesis_id: str, relationship: str, modified_by: str='system') -> None:
        evidence_artifact = self.validate_artifact_reference(evidence_id, EvidenceArtifact, f'linking evidence to hypothesis {hypothesis_id}')
        hypothesis_artifact = self.validate_artifact_reference(hypothesis_id, HypothesisArtifact, f'linking hypothesis to evidence {evidence_id}')
        assert isinstance(evidence_artifact, EvidenceArtifact)
        assert isinstance(hypothesis_artifact, HypothesisArtifact)
        if relationship == 'supports':
            supports = list(evidence_artifact.supports_hypothesis_ids)
            if hypothesis_id not in supports:
                supports.append(hypothesis_id)
                self.update_artifact(evidence_id, {'supports_hypothesis_ids': supports}, modified_by)
            supporting = list(hypothesis_artifact.supporting_evidence_ids)
            if evidence_id not in supporting:
                supporting.append(evidence_id)
                self.update_artifact(hypothesis_id, {'supporting_evidence_ids': supporting}, modified_by)
        elif relationship == 'contradicts':
            contradicts = list(evidence_artifact.contradicts_hypothesis_ids)
            if hypothesis_id not in contradicts:
                contradicts.append(hypothesis_id)
                self.update_artifact(evidence_id, {'contradicts_hypothesis_ids': contradicts}, modified_by)
            contradicting = list(hypothesis_artifact.contradicting_evidence_ids)
            if evidence_id not in contradicting:
                contradicting.append(evidence_id)
                self.update_artifact(hypothesis_id, {'contradicting_evidence_ids': contradicting}, modified_by)

    def add_causal_chain(self, hypothesis_id: str, steps: list[dict[str, Any]], completeness_score: float=0.0, logical_validity: float=0.0, evidence_coverage: float=0.0, gaps: list[str] | None=None, assumptions: list[str] | None=None, llm_request_id: str | None=None, created_by: str='system', phase: int | None=None) -> str:
        self.validate_artifact_reference(hypothesis_id, HypothesisArtifact, 'creating causal chain')
        artifact = CausalChainArtifact(hypothesis_id=hypothesis_id, steps=steps, completeness_score=completeness_score, logical_validity=logical_validity, evidence_coverage=evidence_coverage, gaps=gaps or [], assumptions=assumptions or [], llm_request_id=llm_request_id, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='causal_chain', method_name='add_causal_chain', artifact_id=artifact_id)
        return artifact_id

    def add_challenge(self, target_hypothesis_id: str, content: str, challenge_type: str='unknown', severity: str='MEDIUM', requires_response: bool=True, resolved: bool=False, resolution: str | None=None, llm_request_id: str | None=None, created_by: str='system', phase: int | None=None) -> str:
        self.validate_artifact_reference(target_hypothesis_id, HypothesisArtifact, 'creating challenge')
        artifact = ChallengeArtifact(target_hypothesis_id=target_hypothesis_id, challenge_type=challenge_type, content=content, severity=severity, requires_response=requires_response, resolved=resolved, resolution=resolution, llm_request_id=llm_request_id, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='challenge', method_name='add_challenge', artifact_id=artifact_id)
        return artifact_id

    def add_flow_config(self, investigation_config: dict[str, Any], llm_config: dict[str, Any], source_config: dict[str, Any] | None=None, pipeline_config: dict[str, Any] | None=None, enabled_phases: list[int] | None=None, phase_parameters: dict[str, dict[str, Any]] | None=None, created_by: str='system') -> str:
        artifact = FlowConfigArtifact(investigation_config=investigation_config, llm_config=llm_config, source_config=source_config, pipeline_config=pipeline_config, enabled_phases=enabled_phases or list(range(8)), phase_parameters=phase_parameters or {}, created_by=created_by, phase=0)
        return self.add_artifact(artifact)

    def add_investigation_state(self, investigation_id: str, trigger_error_artifact_id: str | None=None, created_by: str='system') -> str:
        artifact = InvestigationStateArtifact(investigation_id=investigation_id, trigger_error_artifact_id=trigger_error_artifact_id, current_phase=0, status='active', started_at=datetime.now(), created_by=created_by, phase=0)
        return self.add_artifact(artifact)

    def add_persona_contribution(self, persona_id: str, contribution_phase: int, content: dict[str, Any], confidence: float=0.5, reasoning: str='', created_by: str | None=None) -> str:
        artifact = PersonaContributionArtifact(persona_id=persona_id, contribution_phase=contribution_phase, content=content, confidence=confidence, reasoning=reasoning, created_by=created_by or persona_id, phase=contribution_phase)
        return self.add_artifact(artifact)