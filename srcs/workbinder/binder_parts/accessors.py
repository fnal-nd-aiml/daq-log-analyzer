"""
File: accessors.py
Purpose: Typed accessors and the remaining artifact builders.
Category: Utility
Author: artdaq team
Depends: None
Exports: TypedAccessorsMixin
Complexity: Medium | Lines: 140
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from ..artifacts import ArtifactType, BoardAnalysis, BoardReaderIdentificationArtifact, CallGraphNode, CascadeLink, CausalChainArtifact, ChallengeArtifact, CodeSnippet, ConclusionArtifact, ErrorContextArtifact, EvidenceArtifact, FeedbackArtifact, FlowConfigArtifact, HypothesisArtifact, LogBundleArtifact, LogBundleClue, LogBundleErrorEntry, MergedTimelineArtifact, MergedTimelineEntry, PersonaContributionArtifact, SourceLocationArtifact
from ._state import BinderState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class TypedAccessorsMixin(BinderState):

    def get_hypotheses(self) -> list[HypothesisArtifact]:
        hypotheses = [a for a in self._artifacts.values() if isinstance(a, HypothesisArtifact) and (not a.is_deleted)]
        results = sorted(hypotheses, key=lambda h: h.rank)
        persona, phase = self._get_audit_context()
        self._log_access(persona_name=persona, phase_number=phase, operation_type='retrieve', artifact_type='hypothesis_artifact', method_name='get_hypotheses', result_count=len(results))
        return results

    def get_evidence_items(self) -> list[EvidenceArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, EvidenceArtifact) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(persona_name=persona, phase_number=phase, operation_type='retrieve', artifact_type='evidence_artifact', method_name='get_evidence_items', result_count=len(results))
        return results

    def get_causal_chains(self) -> list[CausalChainArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, CausalChainArtifact) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(persona_name=persona, phase_number=phase, operation_type='retrieve', artifact_type='causal_chain', method_name='get_causal_chains', result_count=len(results))
        return results

    def get_challenges(self) -> list[ChallengeArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, ChallengeArtifact) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(persona_name=persona, phase_number=phase, operation_type='retrieve', artifact_type='challenge', method_name='get_challenges', result_count=len(results))
        return results

    def get_flow_config(self) -> FlowConfigArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, FlowConfigArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def get_persona_contributions(self, persona_id: str | None=None, phase: int | None=None) -> list[PersonaContributionArtifact]:
        contributions = []
        for artifact in self._artifacts.values():
            if isinstance(artifact, PersonaContributionArtifact) and (not artifact.is_deleted):
                if persona_id is not None and artifact.persona_id != persona_id:
                    continue
                if phase is not None and artifact.contribution_phase != phase:
                    continue
                contributions.append(artifact)
        return contributions

    def get_error_context(self) -> ErrorContextArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, ErrorContextArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def get_source_locations(self) -> list[SourceLocationArtifact]:
        locations = [a for a in self._artifacts.values() if isinstance(a, SourceLocationArtifact) and (not a.is_deleted)]
        results = sorted(locations, key=lambda loc: loc.match_score, reverse=True)
        persona, phase = self._get_audit_context()
        self._log_access(persona_name=persona, phase_number=phase, operation_type='retrieve', artifact_type='source_location', method_name='get_source_locations', result_count=len(results))
        return results

    def get_call_graphs(self) -> list[CallGraphNode]:
        results = [a for a in self._artifacts.values() if isinstance(a, CallGraphNode) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(persona_name=persona, phase_number=phase, operation_type='retrieve', artifact_type='call_graph', method_name='get_call_graphs', result_count=len(results))
        return results

    def get_code_snippets(self) -> list[CodeSnippet]:
        return [a for a in self._artifacts.values() if isinstance(a, CodeSnippet) and (not a.is_deleted)]

    def get_conclusion(self) -> ConclusionArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, ConclusionArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def add_conclusion(self, root_cause: str, confidence_raw: float, confidence_calibrated: float, outcome: str, code_location: str | None=None, code_snippet: str | None=None, data_flow: str | None=None, caveats: list[str] | None=None, debugging_steps: list[str] | None=None, unresolved_challenges: list[str] | None=None, llm_request_id: str | None=None, created_by: str='system', phase: int | None=None) -> str:
        artifact = ConclusionArtifact(root_cause=root_cause, confidence_raw=confidence_raw, confidence_calibrated=confidence_calibrated, outcome=outcome, code_location=code_location, code_snippet=code_snippet, data_flow=data_flow, caveats=caveats or [], debugging_steps=debugging_steps or [], unresolved_challenges=unresolved_challenges or [], llm_request_id=llm_request_id, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='conclusion', method_name='add_conclusion', artifact_id=artifact_id)
        return artifact_id

    def get_feedback(self) -> list[FeedbackArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, FeedbackArtifact) and (not a.is_deleted)]
        self._log_access(persona_name='system', phase_number=None, operation_type='retrieve', artifact_type='feedback', method_name='get_feedback', result_count=len(results))
        return results

    def add_feedback(self, investigation_id: str, was_correct: bool, actual_cause: str | None=None, feedback_source: str='api', user_id: str | None=None, what_was_helpful: str | None=None, what_was_wrong: str | None=None, suggestions: str | None=None, additional_notes: str | None=None, created_by: str='system', phase: int | None=None) -> str:
        artifact = FeedbackArtifact(investigation_id=investigation_id, was_correct=was_correct, actual_cause=actual_cause, feedback_source=feedback_source, user_id=user_id, what_was_helpful=what_was_helpful, what_was_wrong=what_was_wrong, suggestions=suggestions, additional_notes=additional_notes, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='feedback', method_name='add_feedback', artifact_id=artifact_id)
        return artifact_id

    def add_log_bundle(self, source_files: list[dict[str, Any]], merged_timeline: str, annotated_narrative: str='', primary_error: LogBundleErrorEntry | None=None, error_timeline: list[LogBundleErrorEntry] | None=None, cascade_description: str='', clues: list[LogBundleClue] | None=None, created_by: str='Chronicler', phase: int | None=-1, affected_boards: list[BoardAnalysis] | None=None, cascade_chain: list[CascadeLink] | None=None, documentation_reference: str='') -> str:
        artifact = LogBundleArtifact(source_files=source_files, merged_timeline=merged_timeline, annotated_narrative=annotated_narrative, primary_error=primary_error, error_timeline=error_timeline or [], cascade_description=cascade_description, clues=clues or [], created_by=created_by, phase=phase, affected_boards=affected_boards or [], cascade_chain=cascade_chain or [], documentation_reference=documentation_reference)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='log_bundle', method_name='add_log_bundle', artifact_id=artifact_id)
        return artifact_id

    def get_log_bundle(self) -> LogBundleArtifact | None:
        bundles = self.get_by_type(ArtifactType.LOG_BUNDLE)
        if bundles:
            bundle = bundles[0]
            if isinstance(bundle, LogBundleArtifact):
                return bundle
        return None

    def add_merged_timeline(self, entries: list[MergedTimelineEntry], total_entries: int=0, total_errors: int=0, total_warnings: int=0, total_info: int=0, file_count: int=0, earliest_timestamp: str='', latest_timestamp: str='', created_by: str='Chronicler', phase: int | None=-1) -> str:
        artifact = MergedTimelineArtifact(entries=entries, total_entries=total_entries, total_errors=total_errors, total_warnings=total_warnings, total_info=total_info, file_count=file_count, earliest_timestamp=earliest_timestamp, latest_timestamp=latest_timestamp, created_by=created_by, phase=phase)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='merged_timeline', method_name='add_merged_timeline', artifact_id=artifact_id)
        return artifact_id

    def get_merged_timeline(self) -> MergedTimelineArtifact | None:
        timelines = self.get_by_type(ArtifactType.MERGED_TIMELINE)
        if timelines:
            timeline = timelines[0]
            if isinstance(timeline, MergedTimelineArtifact):
                return timeline
        return None

    def add_boardreader_identification(self, boardreader_types: list[str], components: list[str], error_messages: list[str], created_by: str='Chronicler', phase: int | None=-1, llm_request_id: str | None=None) -> str:
        artifact = BoardReaderIdentificationArtifact(boardreader_types=boardreader_types, components=components, error_messages=error_messages, created_by=created_by, phase=phase, llm_request_id=llm_request_id)
        artifact_id = self.add_artifact(artifact)
        self._log_access(persona_name=created_by, phase_number=phase, operation_type='store', artifact_type='boardreader_identification', method_name='add_boardreader_identification', artifact_id=artifact_id)
        logger.info('Stored boardreader identification: %d types, %d components', len(boardreader_types), len(components))
        return artifact_id

    def get_boardreader_identification(self) -> BoardReaderIdentificationArtifact | None:
        artifacts = self.get_by_type(ArtifactType.BOARDREADER_IDENTIFICATION)
        if artifacts:
            artifact = artifacts[0]
            if isinstance(artifact, BoardReaderIdentificationArtifact):
                return artifact
        return None