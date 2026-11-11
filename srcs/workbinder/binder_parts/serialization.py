"""
File: serialization.py
Purpose: Binder <-> dict serialization.
Category: Utility
Author: artdaq team
Depends: None
Exports: SerializationMixin
Complexity: Low | Lines: 33
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from ..artifacts import Artifact, ArtifactHistory, ArtifactType
from ._state import BinderState
if TYPE_CHECKING:
    from ..binder import WorkBinder
logger = logging.getLogger(__name__)

class SerializationMixin(BinderState):

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'investigation_id': self.investigation_id, 'created_at': self.created_at.isoformat(), 'updated_at': self.updated_at.isoformat(), 'status': self.status, 'artifacts': {aid: artifact.model_dump() for aid, artifact in self._artifacts.items()}, 'history': [h.model_dump() for h in self._history]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'WorkBinder':
        artifact_classes: dict[ArtifactType, type[Artifact]] = cls._get_artifact_classes()
        binder = cls(id=data['id'], investigation_id=data['investigation_id'], created_at=datetime.fromisoformat(data['created_at']), updated_at=datetime.fromisoformat(data['updated_at']), status=data['status'])
        for artifact_data in data.get('artifacts', {}).values():
            artifact_type = ArtifactType(artifact_data['artifact_type'])
            artifact_class = artifact_classes.get(artifact_type)
            if artifact_class:
                artifact = artifact_class.model_validate(artifact_data)
                binder.add_artifact(artifact, record_history=False)
        for history_data in data.get('history', []):
            binder._history.append(ArtifactHistory.model_validate(history_data))
        return binder

    @staticmethod
    def _get_artifact_classes() -> dict[ArtifactType, type[Artifact]]:
        from ..artifacts import Annotation, BoardReaderIdentificationArtifact, CallGraphNode, CausalChainArtifact, ChallengeArtifact, CodeSnippet, ConclusionArtifact, ErrorContextArtifact, EvidenceArtifact, Finding, FlowConfigArtifact, FunctionSummaryArtifact, HypothesisArtifact, InvestigationStateArtifact, LLMRequestArtifact, LLMResponseArtifact, LogBundleArtifact, MergedTimelineArtifact, PersonaContributionArtifact, PhaseStateArtifact, SourceLocationArtifact
        return {ArtifactType.CALL_GRAPH: CallGraphNode, ArtifactType.CODE_SNIPPET: CodeSnippet, ArtifactType.FINDING: Finding, ArtifactType.ANNOTATION: Annotation, ArtifactType.SOURCE_LOCATION: SourceLocationArtifact, ArtifactType.ERROR_CONTEXT: ErrorContextArtifact, ArtifactType.LLM_REQUEST: LLMRequestArtifact, ArtifactType.LLM_RESPONSE: LLMResponseArtifact, ArtifactType.FLOW_CONFIG: FlowConfigArtifact, ArtifactType.PHASE_STATE: PhaseStateArtifact, ArtifactType.INVESTIGATION_STATE: InvestigationStateArtifact, ArtifactType.PERSONA_CONTRIBUTION: PersonaContributionArtifact, ArtifactType.HYPOTHESIS_ARTIFACT: HypothesisArtifact, ArtifactType.EVIDENCE_ARTIFACT: EvidenceArtifact, ArtifactType.CAUSAL_CHAIN: CausalChainArtifact, ArtifactType.CHALLENGE: ChallengeArtifact, ArtifactType.CONCLUSION: ConclusionArtifact, ArtifactType.FUNCTION_SUMMARY: FunctionSummaryArtifact, ArtifactType.LOG_BUNDLE: LogBundleArtifact, ArtifactType.MERGED_TIMELINE: MergedTimelineArtifact, ArtifactType.BOARDREADER_IDENTIFICATION: BoardReaderIdentificationArtifact}