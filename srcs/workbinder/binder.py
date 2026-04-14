"""
File: binder.py
Purpose: Work Binder - Interactive Investigation Container.
Category: Utility
Author: artdaq team
Depends: models, base
Exports: BinderQuery, WorkBinder
Complexity: High | Lines: 1384
"""

from __future__ import annotations
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generator
from srcs.models.base import generate_id
from .artifacts import (
    Annotation,
    AnnotationType,
    Artifact,
    ArtifactHistory,
    ArtifactType,
    AuditLogEntry,
    BoardAnalysis,
    BoardReaderIdentificationArtifact,
    CalleeInfo,
    CallerInfo,
    CallGraphNode,
    CascadeLink,
    CausalChainArtifact,
    ChallengeArtifact,
    CodeSnippet,
    ConclusionArtifact,
    ErrorContextArtifact,
    EvidenceArtifact,
    FeedbackArtifact,
    Finding,
    FindingType,
    FlowConfigArtifact,
    FunctionSummaryArtifact,
    HypothesisArtifact,
    InvestigationStateArtifact,
    LLMRequestArtifact,
    LLMResponseArtifact,
    LogBundleArtifact,
    LogBundleClue,
    LogBundleErrorEntry,
    MergedTimelineArtifact,
    MergedTimelineEntry,
    PersonaContributionArtifact,
    PhaseStateArtifact,
    Priority,
    SourceLocationArtifact,
)

if TYPE_CHECKING:
    from srcs.models import Log
logger = logging.getLogger(__name__)


@dataclass
class BinderQuery:
    artifact_type: ArtifactType | None = None
    created_by: str | None = None
    tags: list[str] | None = None
    phase: int | None = None
    function_name: str | None = None
    priority: Priority | None = None
    include_deleted: bool = False
    limit: int = 100
    offset: int = 0


@dataclass
class WorkBinder:
    id: str = field(default_factory=generate_id)
    investigation_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: str = "active"
    _artifacts: dict[str, Artifact] = field(default_factory=dict)
    _history: list[ArtifactHistory] = field(default_factory=list)
    _tags_index: dict[str, set[str]] = field(default_factory=dict)
    _function_index: dict[str, set[str]] = field(default_factory=dict)
    _audit_log: list[AuditLogEntry] = field(default_factory=list)
    _access_sequence: int = 0
    _audit_persona: str | None = None
    _audit_phase: int | None = None

    @contextmanager
    def audit_context(self, persona_name: str, phase: int | None = None) -> Generator[None, None, None]:
        old_persona = self._audit_persona
        old_phase = self._audit_phase
        self._audit_persona = persona_name
        self._audit_phase = phase
        try:
            yield
        finally:
            self._audit_persona = old_persona
            self._audit_phase = old_phase

    def _get_audit_context(self) -> tuple[str, int | None]:
        return (self._audit_persona or "Unknown", self._audit_phase)

    def _log_access(
        self,
        persona_name: str,
        phase_number: int | None,
        operation_type: str,
        artifact_type: str,
        method_name: str,
        artifact_id: str | None = None,
        result_count: int = 1,
        success: bool = True,
    ) -> None:
        self._access_sequence += 1
        entry = AuditLogEntry(
            persona_name=persona_name,
            phase_number=phase_number,
            timestamp=datetime.now(),
            access_sequence=self._access_sequence,
            operation_type=operation_type,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            method_name=method_name,
            result_count=result_count,
            success=success,
        )
        self._audit_log.append(entry)

    def get_audit_log(
        self, persona_name: str | None = None, phase_number: int | None = None, operation_type: str | None = None
    ) -> list[AuditLogEntry]:
        entries = self._audit_log
        if persona_name:
            entries = [e for e in entries if e.persona_name == persona_name]
        if phase_number is not None:
            entries = [e for e in entries if e.phase_number == phase_number]
        if operation_type:
            entries = [e for e in entries if e.operation_type == operation_type]
        return entries

    def add_artifact(self, artifact: Artifact, record_history: bool = True) -> str:
        self._artifacts[artifact.id] = artifact
        self.updated_at = datetime.now()
        for tag in artifact.tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = set()
            self._tags_index[tag].add(artifact.id)
        if artifact.function_name:
            if artifact.function_name not in self._function_index:
                self._function_index[artifact.function_name] = set()
            self._function_index[artifact.function_name].add(artifact.id)
        if record_history:
            self._history.append(
                ArtifactHistory(
                    artifact_id=artifact.id,
                    modified_by=artifact.created_by,
                    action="create",
                    changes={"artifact": artifact.model_dump()},
                )
            )
        return artifact.id

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def update_artifact(self, artifact_id: str, updates: dict[str, Any], modified_by: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        before = {}
        after = {}
        for field_name, new_value in updates.items():
            if hasattr(artifact, field_name):
                before[field_name] = getattr(artifact, field_name)
                setattr(artifact, field_name, new_value)
                after[field_name] = new_value
        artifact.updated_at = datetime.now()
        self.updated_at = datetime.now()
        if "tags" in updates:
            for tag in before.get("tags", []):
                if tag in self._tags_index:
                    self._tags_index[tag].discard(artifact_id)
            for tag in updates["tags"]:
                if tag not in self._tags_index:
                    self._tags_index[tag] = set()
                self._tags_index[tag].add(artifact_id)
        if "function_name" in updates:
            old_func = before.get("function_name")
            new_func = updates["function_name"]
            if old_func and old_func in self._function_index:
                self._function_index[old_func].discard(artifact_id)
            if new_func:
                if new_func not in self._function_index:
                    self._function_index[new_func] = set()
                self._function_index[new_func].add(artifact_id)
        self._history.append(
            ArtifactHistory(
                artifact_id=artifact_id,
                modified_by=modified_by,
                action="update",
                changes={"before": before, "after": after},
            )
        )
        return True

    def mark_deleted(self, artifact_id: str, deleted_by: str, reason: str | None = None) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        artifact.is_deleted = True
        artifact.deleted_by = deleted_by
        artifact.deleted_reason = reason
        artifact.updated_at = datetime.now()
        self.updated_at = datetime.now()
        self._history.append(
            ArtifactHistory(
                artifact_id=artifact_id, modified_by=deleted_by, action="delete", changes={"reason": reason}
            )
        )
        return True

    def restore_artifact(self, artifact_id: str, restored_by: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        artifact.is_deleted = False
        artifact.deleted_by = None
        artifact.deleted_reason = None
        artifact.updated_at = datetime.now()
        self.updated_at = datetime.now()
        self._history.append(
            ArtifactHistory(artifact_id=artifact_id, modified_by=restored_by, action="restore", changes={})
        )
        return True

    def query(self, query: BinderQuery) -> list[Artifact]:
        results = []
        for artifact in self._artifacts.values():
            if artifact.is_deleted and (not query.include_deleted):
                continue
            if query.artifact_type and artifact.artifact_type != query.artifact_type:
                continue
            if query.created_by and artifact.created_by != query.created_by:
                continue
            if query.phase is not None and artifact.phase != query.phase:
                continue
            if query.function_name and artifact.function_name != query.function_name:
                continue
            if query.priority and artifact.priority != query.priority:
                continue
            if query.tags:
                if not all((tag in artifact.tags for tag in query.tags)):
                    continue
            results.append(artifact)
        return results[query.offset : query.offset + query.limit]

    def get_by_type(self, artifact_type: ArtifactType) -> list[Artifact]:
        return self.query(BinderQuery(artifact_type=artifact_type))

    def get_by_tag(self, tag: str) -> list[Artifact]:
        artifact_ids = self._tags_index.get(tag, set())
        return [
            self._artifacts[aid]
            for aid in artifact_ids
            if aid in self._artifacts and (not self._artifacts[aid].is_deleted)
        ]

    def get_by_function(self, function_name: str) -> list[Artifact]:
        artifact_ids = self._function_index.get(function_name, set())
        return [
            self._artifacts[aid]
            for aid in artifact_ids
            if aid in self._artifacts and (not self._artifacts[aid].is_deleted)
        ]

    def get_history(self, artifact_id: str | None = None) -> list[ArtifactHistory]:
        if artifact_id:
            return [h for h in self._history if h.artifact_id == artifact_id]
        return list(self._history)

    def get_annotations(self, artifact_id: str) -> list[Annotation]:
        annotations = []
        for artifact in self._artifacts.values():
            if (
                isinstance(artifact, Annotation)
                and artifact.target_artifact_id == artifact_id
                and (not artifact.is_deleted)
            ):
                annotations.append(artifact)
        return annotations

    def get_related_artifacts(self, artifact_id: str) -> list[Artifact]:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return []
        related = set()
        for a in self._artifacts.values():
            if a.is_deleted or a.id == artifact_id:
                continue
            if isinstance(a, Finding) and artifact_id in a.related_artifacts:
                related.add(a.id)
            if isinstance(a, Annotation) and a.target_artifact_id == artifact_id:
                related.add(a.id)
            if artifact.function_name and a.function_name == artifact.function_name:
                related.add(a.id)
        return [self._artifacts[aid] for aid in related]

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for artifact in self._artifacts.values():
            if artifact.is_deleted:
                continue
            type_name = artifact.artifact_type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts

    def get_all_tags(self) -> list[str]:
        return list(self._tags_index.keys())

    def add_call_graph(
        self,
        center_function: str,
        callers: list[dict[str, Any]],
        callees: list[dict[str, Any]],
        created_by: str,
        phase: int | None = None,
        diagram: str | None = None,
        depth: int = 1,
    ) -> str:
        caller_infos = [CallerInfo(**c) for c in callers]
        callee_infos = [CalleeInfo(**c) for c in callees]
        artifact = CallGraphNode(
            center_function=center_function,
            callers=caller_infos,
            callees=callee_infos,
            created_by=created_by,
            phase=phase,
            function_name=center_function,
            diagram=diagram,
            depth_explored=depth,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="call_graph",
            method_name="add_call_graph",
            artifact_id=artifact_id,
        )
        logger.info(f"Stored call graph: {center_function} ({len(callers)} callers, {len(callees)} callees)")
        return artifact_id

    def add_function_summary(
        self,
        function_name: str,
        purpose: str,
        mechanism: str,
        data_flow: str,
        error_paths: str,
        error_line_relevance: str,
        center_function: str,
        role: str,
        created_by: str,
        phase: int | None = None,
        file_path: str | None = None,
    ) -> str:
        artifact = FunctionSummaryArtifact(
            function_name=function_name,
            file_path=file_path,
            purpose=purpose,
            mechanism=mechanism,
            data_flow=data_flow,
            error_paths=error_paths,
            error_line_relevance=error_line_relevance,
            center_function=center_function,
            role=role,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="function_summary",
            method_name="add_function_summary",
            artifact_id=artifact_id,
        )
        logger.info(f"Stored function summary: {function_name} ({role} of {center_function})")
        return artifact_id

    def add_code_snippet(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        content: str,
        created_by: str,
        language: str = "cpp",
        function_name: str | None = None,
        summary: str | None = None,
        phase: int | None = None,
        match_score: float | None = None,
    ) -> str:
        artifact = CodeSnippet(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            content=content,
            created_by=created_by,
            language=language,
            snippet_function_name=function_name,
            function_name=function_name,
            summary=summary,
            phase=phase,
            match_score=match_score,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="code_snippet",
            method_name="add_code_snippet",
            artifact_id=artifact_id,
        )
        func_info = f" ({function_name})" if function_name else ""
        logger.info(f"Stored code snippet: {file_path}:{start_line}-{end_line}{func_info} ({len(content)} chars)")
        return artifact_id

    def add_finding(
        self,
        persona: str,
        finding_type: FindingType | str,
        content: str,
        confidence: float = 0.5,
        related_artifacts: list[str] | None = None,
        phase: int | None = None,
        tags: list[str] | None = None,
    ) -> str:
        if isinstance(finding_type, str):
            finding_type = FindingType(finding_type)
        artifact = Finding(
            persona=persona,
            finding_type=finding_type,
            content=content,
            confidence=confidence,
            related_artifacts=related_artifacts or [],
            created_by=persona,
            phase=phase,
            tags=tags or [],
        )
        return self.add_artifact(artifact)

    def add_annotation(
        self, target_artifact_id: str, annotation_type: AnnotationType | str, content: str, created_by: str
    ) -> str:
        if isinstance(annotation_type, str):
            annotation_type = AnnotationType(annotation_type)
        artifact = Annotation(
            target_artifact_id=target_artifact_id,
            annotation_type=annotation_type,
            annotation_content=content,
            created_by=created_by,
        )
        return self.add_artifact(artifact)

    def add_source_location(
        self,
        file_path: str,
        line_number: int,
        created_by: str,
        matched_line: str | None = None,
        match_score: float = 0.0,
        is_log_statement: bool = False,
        function_name: str | None = None,
        function_signature: str | None = None,
        function_body: str | None = None,
        context_before: list[str] | None = None,
        context_after: list[str] | None = None,
        phase: int | None = None,
    ) -> str:
        artifact = SourceLocationArtifact(
            file_path=file_path,
            line_number=line_number,
            matched_line=matched_line,
            match_score=match_score,
            is_log_statement=is_log_statement,
            function_name=function_name,
            function_signature=function_signature,
            function_body=function_body,
            context_before=context_before or [],
            context_after=context_after or [],
            created_by=created_by,
            phase=phase,
            priority=Priority.HIGH if match_score > 0.8 else Priority.NORMAL,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="source_location",
            method_name="add_source_location",
            artifact_id=artifact_id,
        )
        func_info = f", function={function_name}" if function_name else ""
        logger.info(f"Stored source location: {file_path}:{line_number} (score={match_score:.2f}{func_info})")
        return artifact_id

    def add_error_context(self, error: "Log", context_logs: list["Log"], created_by: str) -> str:
        artifact = ErrorContextArtifact(
            error_message=error.message,
            error_level=error.level,
            error_component=error.component,
            error_function=error.function,
            error_timestamp=error.timestamp,
            context_logs=[log.model_dump() for log in context_logs],
            created_by=created_by,
            phase=0,
            priority=Priority.CRITICAL,
        )
        return self.add_artifact(artifact)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "investigation_id": self.investigation_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "artifacts": {aid: artifact.model_dump() for aid, artifact in self._artifacts.items()},
            "history": [h.model_dump() for h in self._history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkBinder":
        artifact_classes: dict[ArtifactType, type[Artifact]] = cls._get_artifact_classes()
        binder = cls(
            id=data["id"],
            investigation_id=data["investigation_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            status=data["status"],
        )
        for artifact_data in data.get("artifacts", {}).values():
            artifact_type = ArtifactType(artifact_data["artifact_type"])
            artifact_class = artifact_classes.get(artifact_type)
            if artifact_class:
                artifact = artifact_class.model_validate(artifact_data)
                binder.add_artifact(artifact, record_history=False)
        for history_data in data.get("history", []):
            binder._history.append(ArtifactHistory.model_validate(history_data))
        return binder

    @staticmethod
    def _get_artifact_classes() -> dict[ArtifactType, type[Artifact]]:
        from .artifacts import (
            Annotation,
            BoardReaderIdentificationArtifact,
            CallGraphNode,
            CausalChainArtifact,
            ChallengeArtifact,
            CodeSnippet,
            ConclusionArtifact,
            ErrorContextArtifact,
            EvidenceArtifact,
            Finding,
            FlowConfigArtifact,
            FunctionSummaryArtifact,
            HypothesisArtifact,
            InvestigationStateArtifact,
            LLMRequestArtifact,
            LLMResponseArtifact,
            LogBundleArtifact,
            MergedTimelineArtifact,
            PersonaContributionArtifact,
            PhaseStateArtifact,
            SourceLocationArtifact,
        )

        return {
            ArtifactType.CALL_GRAPH: CallGraphNode,
            ArtifactType.CODE_SNIPPET: CodeSnippet,
            ArtifactType.FINDING: Finding,
            ArtifactType.ANNOTATION: Annotation,
            ArtifactType.SOURCE_LOCATION: SourceLocationArtifact,
            ArtifactType.ERROR_CONTEXT: ErrorContextArtifact,
            ArtifactType.LLM_REQUEST: LLMRequestArtifact,
            ArtifactType.LLM_RESPONSE: LLMResponseArtifact,
            ArtifactType.FLOW_CONFIG: FlowConfigArtifact,
            ArtifactType.PHASE_STATE: PhaseStateArtifact,
            ArtifactType.INVESTIGATION_STATE: InvestigationStateArtifact,
            ArtifactType.PERSONA_CONTRIBUTION: PersonaContributionArtifact,
            ArtifactType.HYPOTHESIS_ARTIFACT: HypothesisArtifact,
            ArtifactType.EVIDENCE_ARTIFACT: EvidenceArtifact,
            ArtifactType.CAUSAL_CHAIN: CausalChainArtifact,
            ArtifactType.CHALLENGE: ChallengeArtifact,
            ArtifactType.CONCLUSION: ConclusionArtifact,
            ArtifactType.FUNCTION_SUMMARY: FunctionSummaryArtifact,
            ArtifactType.LOG_BUNDLE: LogBundleArtifact,
            ArtifactType.MERGED_TIMELINE: MergedTimelineArtifact,
            ArtifactType.BOARDREADER_IDENTIFICATION: BoardReaderIdentificationArtifact,
        }

    def get_investigation_state(self) -> InvestigationStateArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, InvestigationStateArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def update_investigation_state(self, modified_by: str = "system", **updates: Any) -> bool:
        state = self.get_investigation_state()
        if not state:
            return False
        return self.update_artifact(state.id, updates, modified_by)

    def get_phase_state(self, phase: int) -> PhaseStateArtifact | None:
        for artifact in self._artifacts.values():
            if (
                isinstance(artifact, PhaseStateArtifact)
                and artifact.phase_number == phase
                and (not artifact.is_deleted)
            ):
                return artifact
        return None

    def start_phase(self, phase: int, persona_name: str) -> str:
        existing = self.get_phase_state(phase)
        if existing:
            self.update_artifact(existing.id, {"status": "in_progress", "started_at": datetime.now()}, persona_name)
            return existing.id
        artifact = PhaseStateArtifact(
            phase_number=phase,
            persona_name=persona_name,
            status="in_progress",
            started_at=datetime.now(),
            created_by=persona_name,
            phase=phase,
        )
        return self.add_artifact(artifact)

    def complete_phase(self, phase: int, output_ids: list[str], modified_by: str = "system") -> None:
        state = self.get_phase_state(phase)
        if state:
            self.update_artifact(
                state.id,
                {"status": "completed", "completed_at": datetime.now(), "output_artifact_ids": output_ids},
                modified_by,
            )
        inv_state = self.get_investigation_state()
        if inv_state and inv_state.current_phase == phase:
            self.update_artifact(inv_state.id, {"current_phase": phase + 1}, modified_by)

    def fail_phase(self, phase: int, error_message: str, modified_by: str = "system") -> None:
        state = self.get_phase_state(phase)
        if state:
            self.update_artifact(
                state.id,
                {"status": "failed", "completed_at": datetime.now(), "error_message": error_message},
                modified_by,
            )

    def pause_investigation(self, reason: str, modified_by: str = "system") -> None:
        inv_state = self.get_investigation_state()
        if inv_state:
            self.update_artifact(
                inv_state.id, {"status": "paused", "paused_at": datetime.now(), "pause_reason": reason}, modified_by
            )
        self.status = "paused"

    def can_resume(self) -> bool:
        state = self.get_investigation_state()
        return state is not None and state.status == "paused"

    def get_resume_point(self) -> tuple[int, dict[str, Any]]:
        if not self.can_resume():
            raise ValueError("Investigation cannot be resumed - not in paused state")
        inv_state = self.get_investigation_state()
        if not inv_state:
            raise ValueError("No investigation state found")
        resume_phase = inv_state.current_phase
        current_phase_state = self.get_phase_state(resume_phase)
        if current_phase_state and current_phase_state.status == "in_progress":
            pass
        elif resume_phase > 0:
            prev_state = self.get_phase_state(resume_phase - 1)
            if prev_state and prev_state.status != "completed":
                resume_phase = resume_phase - 1
        resume_context = self._build_resume_context(resume_phase)
        return (resume_phase, resume_context)

    def _build_resume_context(self, phase: int) -> dict[str, Any]:
        context: dict[str, Any] = {"phase": phase, "hypotheses": [], "evidence": [], "findings": []}
        for artifact in self._artifacts.values():
            if artifact.is_deleted:
                continue
            if isinstance(artifact, HypothesisArtifact):
                context["hypotheses"].append(artifact.model_dump())
            elif isinstance(artifact, EvidenceArtifact):
                context["evidence"].append(artifact.model_dump())
            elif isinstance(artifact, Finding):
                context["findings"].append(artifact.model_dump())
        return context

    def resume_investigation(self, modified_by: str = "system") -> int:
        if not self.can_resume():
            raise ValueError("Investigation cannot be resumed")
        resume_phase, _ = self.get_resume_point()
        inv_state = self.get_investigation_state()
        if inv_state:
            self.update_artifact(
                inv_state.id,
                {
                    "status": "active",
                    "paused_at": None,
                    "pause_reason": None,
                    "resume_count": inv_state.resume_count + 1,
                },
                modified_by,
            )
        self.status = "active"
        return resume_phase

    def record_llm_request(
        self,
        persona: str,
        prompt_key: str,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        phase: int | None = None,
    ) -> str:
        artifact = LLMRequestArtifact(
            persona=persona,
            prompt_key=prompt_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timestamp=datetime.now(),
            created_by=persona,
            phase=phase,
        )
        return self.add_artifact(artifact)

    def record_llm_response(
        self,
        request_id: str,
        raw_response: str,
        parsed_content: dict[str, Any] | None,
        tokens_used: int,
        latency_ms: float,
        parse_success: bool,
        parse_errors: list[str] | None = None,
        phase: int | None = None,
    ) -> str:
        request = self.get_artifact(request_id)
        persona = request.persona if isinstance(request, LLMRequestArtifact) else "system"
        artifact = LLMResponseArtifact(
            linked_request_id=request_id,
            raw_response=raw_response,
            parsed_content=parsed_content,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            response_timestamp=datetime.now(),
            parse_success=parse_success,
            parse_errors=parse_errors or [],
            created_by=persona,
            phase=phase,
        )
        response_id = self.add_artifact(artifact)
        if request:
            self.update_artifact(request_id, {"linked_response_id": response_id}, persona)
        return response_id

    def get_llm_exchanges(
        self, phase: int | None = None
    ) -> list[tuple[LLMRequestArtifact, LLMResponseArtifact | None]]:
        exchanges: list[tuple[LLMRequestArtifact, LLMResponseArtifact | None]] = []
        requests: list[LLMRequestArtifact] = []
        for artifact in self._artifacts.values():
            if isinstance(artifact, LLMRequestArtifact) and (not artifact.is_deleted):
                if phase is None or artifact.phase == phase:
                    requests.append(artifact)
        requests.sort(key=lambda r: r.request_timestamp)
        for request in requests:
            response = None
            if request.linked_response_id:
                resp_artifact = self.get_artifact(request.linked_response_id)
                if isinstance(resp_artifact, LLMResponseArtifact):
                    response = resp_artifact
            exchanges.append((request, response))
        return exchanges

    def add_hypothesis(
        self,
        description: str,
        source: str = "fresh",
        prior_probability: float = 0.5,
        score: float = 0.5,
        rank: int = 0,
        llm_request_id: str | None = None,
        created_by: str = "system",
        phase: int | None = None,
    ) -> str:
        artifact = HypothesisArtifact(
            description=description,
            source=source,
            prior_probability=prior_probability,
            score=score,
            rank=rank,
            llm_request_id=llm_request_id,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="hypothesis_artifact",
            method_name="add_hypothesis",
            artifact_id=artifact_id,
        )
        return artifact_id

    def add_evidence(
        self,
        evidence_type: str,
        content: str,
        source: str,
        strength: str = "MODERATE",
        llm_request_id: str | None = None,
        created_by: str = "system",
        phase: int | None = None,
        found: bool = True,
        targets_hypothesis_id: str | None = None,
        expected_if_true: str | None = None,
        expected_if_false: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        artifact = EvidenceArtifact(
            evidence_type=evidence_type,
            content=content,
            source=source,
            strength=strength,
            llm_request_id=llm_request_id,
            created_by=created_by,
            phase=phase,
            found=found,
            targets_hypothesis_id=targets_hypothesis_id,
            expected_if_true=expected_if_true,
            expected_if_false=expected_if_false,
            tags=tags or [],
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="evidence_artifact",
            method_name="add_evidence",
            artifact_id=artifact_id,
        )
        return artifact_id

    def artifact_exists(self, artifact_id: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        return artifact is not None and (not artifact.is_deleted)

    def validate_artifact_reference(
        self, artifact_id: str, expected_type: type[Artifact] | None = None, context: str = ""
    ) -> Artifact:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ValueError(
                f"Invalid artifact reference: '{artifact_id}' does not exist{(f' ({context})' if context else '')}"
            )
        if artifact.is_deleted:
            raise ValueError(
                f"Invalid artifact reference: '{artifact_id}' has been deleted{(f' ({context})' if context else '')}"
            )
        if expected_type is not None and (not isinstance(artifact, expected_type)):
            raise ValueError(
                f"Invalid artifact reference: '{artifact_id}' is {type(artifact).__name__}, expected {expected_type.__name__}{(f' ({context})' if context else '')}"
            )
        return artifact

    def link_evidence_to_hypothesis(
        self, evidence_id: str, hypothesis_id: str, relationship: str, modified_by: str = "system"
    ) -> None:
        evidence_artifact = self.validate_artifact_reference(
            evidence_id, EvidenceArtifact, f"linking evidence to hypothesis {hypothesis_id}"
        )
        hypothesis_artifact = self.validate_artifact_reference(
            hypothesis_id, HypothesisArtifact, f"linking hypothesis to evidence {evidence_id}"
        )
        assert isinstance(evidence_artifact, EvidenceArtifact)
        assert isinstance(hypothesis_artifact, HypothesisArtifact)
        if relationship == "supports":
            supports = list(evidence_artifact.supports_hypothesis_ids)
            if hypothesis_id not in supports:
                supports.append(hypothesis_id)
                self.update_artifact(evidence_id, {"supports_hypothesis_ids": supports}, modified_by)
            supporting = list(hypothesis_artifact.supporting_evidence_ids)
            if evidence_id not in supporting:
                supporting.append(evidence_id)
                self.update_artifact(hypothesis_id, {"supporting_evidence_ids": supporting}, modified_by)
        elif relationship == "contradicts":
            contradicts = list(evidence_artifact.contradicts_hypothesis_ids)
            if hypothesis_id not in contradicts:
                contradicts.append(hypothesis_id)
                self.update_artifact(evidence_id, {"contradicts_hypothesis_ids": contradicts}, modified_by)
            contradicting = list(hypothesis_artifact.contradicting_evidence_ids)
            if evidence_id not in contradicting:
                contradicting.append(evidence_id)
                self.update_artifact(hypothesis_id, {"contradicting_evidence_ids": contradicting}, modified_by)

    def add_causal_chain(
        self,
        hypothesis_id: str,
        steps: list[dict[str, Any]],
        completeness_score: float = 0.0,
        logical_validity: float = 0.0,
        evidence_coverage: float = 0.0,
        gaps: list[str] | None = None,
        assumptions: list[str] | None = None,
        llm_request_id: str | None = None,
        created_by: str = "system",
        phase: int | None = None,
    ) -> str:
        self.validate_artifact_reference(hypothesis_id, HypothesisArtifact, "creating causal chain")
        artifact = CausalChainArtifact(
            hypothesis_id=hypothesis_id,
            steps=steps,
            completeness_score=completeness_score,
            logical_validity=logical_validity,
            evidence_coverage=evidence_coverage,
            gaps=gaps or [],
            assumptions=assumptions or [],
            llm_request_id=llm_request_id,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="causal_chain",
            method_name="add_causal_chain",
            artifact_id=artifact_id,
        )
        return artifact_id

    def add_challenge(
        self,
        target_hypothesis_id: str,
        content: str,
        challenge_type: str = "unknown",
        severity: str = "MEDIUM",
        requires_response: bool = True,
        resolved: bool = False,
        resolution: str | None = None,
        llm_request_id: str | None = None,
        created_by: str = "system",
        phase: int | None = None,
    ) -> str:
        self.validate_artifact_reference(target_hypothesis_id, HypothesisArtifact, "creating challenge")
        artifact = ChallengeArtifact(
            target_hypothesis_id=target_hypothesis_id,
            challenge_type=challenge_type,
            content=content,
            severity=severity,
            requires_response=requires_response,
            resolved=resolved,
            resolution=resolution,
            llm_request_id=llm_request_id,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="challenge",
            method_name="add_challenge",
            artifact_id=artifact_id,
        )
        return artifact_id

    def add_flow_config(
        self,
        investigation_config: dict[str, Any],
        llm_config: dict[str, Any],
        source_config: dict[str, Any] | None = None,
        pipeline_config: dict[str, Any] | None = None,
        enabled_phases: list[int] | None = None,
        phase_parameters: dict[str, dict[str, Any]] | None = None,
        created_by: str = "system",
    ) -> str:
        artifact = FlowConfigArtifact(
            investigation_config=investigation_config,
            llm_config=llm_config,
            source_config=source_config,
            pipeline_config=pipeline_config,
            enabled_phases=enabled_phases or list(range(8)),
            phase_parameters=phase_parameters or {},
            created_by=created_by,
            phase=0,
        )
        return self.add_artifact(artifact)

    def add_investigation_state(
        self, investigation_id: str, trigger_error_artifact_id: str | None = None, created_by: str = "system"
    ) -> str:
        artifact = InvestigationStateArtifact(
            investigation_id=investigation_id,
            trigger_error_artifact_id=trigger_error_artifact_id,
            current_phase=0,
            status="active",
            started_at=datetime.now(),
            created_by=created_by,
            phase=0,
        )
        return self.add_artifact(artifact)

    def add_persona_contribution(
        self,
        persona_id: str,
        contribution_phase: int,
        content: dict[str, Any],
        confidence: float = 0.5,
        reasoning: str = "",
        created_by: str | None = None,
    ) -> str:
        artifact = PersonaContributionArtifact(
            persona_id=persona_id,
            contribution_phase=contribution_phase,
            content=content,
            confidence=confidence,
            reasoning=reasoning,
            created_by=created_by or persona_id,
            phase=contribution_phase,
        )
        return self.add_artifact(artifact)

    def get_hypotheses(self) -> list[HypothesisArtifact]:
        hypotheses = [a for a in self._artifacts.values() if isinstance(a, HypothesisArtifact) and (not a.is_deleted)]
        results = sorted(hypotheses, key=lambda h: h.rank)
        persona, phase = self._get_audit_context()
        self._log_access(
            persona_name=persona,
            phase_number=phase,
            operation_type="retrieve",
            artifact_type="hypothesis_artifact",
            method_name="get_hypotheses",
            result_count=len(results),
        )
        return results

    def get_evidence_items(self) -> list[EvidenceArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, EvidenceArtifact) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(
            persona_name=persona,
            phase_number=phase,
            operation_type="retrieve",
            artifact_type="evidence_artifact",
            method_name="get_evidence_items",
            result_count=len(results),
        )
        return results

    def get_causal_chains(self) -> list[CausalChainArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, CausalChainArtifact) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(
            persona_name=persona,
            phase_number=phase,
            operation_type="retrieve",
            artifact_type="causal_chain",
            method_name="get_causal_chains",
            result_count=len(results),
        )
        return results

    def get_challenges(self) -> list[ChallengeArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, ChallengeArtifact) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(
            persona_name=persona,
            phase_number=phase,
            operation_type="retrieve",
            artifact_type="challenge",
            method_name="get_challenges",
            result_count=len(results),
        )
        return results

    def get_flow_config(self) -> FlowConfigArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, FlowConfigArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def get_persona_contributions(
        self, persona_id: str | None = None, phase: int | None = None
    ) -> list[PersonaContributionArtifact]:
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
        locations = [
            a for a in self._artifacts.values() if isinstance(a, SourceLocationArtifact) and (not a.is_deleted)
        ]
        results = sorted(locations, key=lambda loc: loc.match_score, reverse=True)
        persona, phase = self._get_audit_context()
        self._log_access(
            persona_name=persona,
            phase_number=phase,
            operation_type="retrieve",
            artifact_type="source_location",
            method_name="get_source_locations",
            result_count=len(results),
        )
        return results

    def get_call_graphs(self) -> list[CallGraphNode]:
        results = [a for a in self._artifacts.values() if isinstance(a, CallGraphNode) and (not a.is_deleted)]
        persona, phase = self._get_audit_context()
        self._log_access(
            persona_name=persona,
            phase_number=phase,
            operation_type="retrieve",
            artifact_type="call_graph",
            method_name="get_call_graphs",
            result_count=len(results),
        )
        return results

    def get_code_snippets(self) -> list[CodeSnippet]:
        return [a for a in self._artifacts.values() if isinstance(a, CodeSnippet) and (not a.is_deleted)]

    def get_conclusion(self) -> ConclusionArtifact | None:
        for artifact in self._artifacts.values():
            if isinstance(artifact, ConclusionArtifact) and (not artifact.is_deleted):
                return artifact
        return None

    def add_conclusion(
        self,
        root_cause: str,
        confidence_raw: float,
        confidence_calibrated: float,
        outcome: str,
        code_location: str | None = None,
        code_snippet: str | None = None,
        data_flow: str | None = None,
        caveats: list[str] | None = None,
        debugging_steps: list[str] | None = None,
        unresolved_challenges: list[str] | None = None,
        llm_request_id: str | None = None,
        created_by: str = "system",
        phase: int | None = None,
    ) -> str:
        artifact = ConclusionArtifact(
            root_cause=root_cause,
            confidence_raw=confidence_raw,
            confidence_calibrated=confidence_calibrated,
            outcome=outcome,
            code_location=code_location,
            code_snippet=code_snippet,
            data_flow=data_flow,
            caveats=caveats or [],
            debugging_steps=debugging_steps or [],
            unresolved_challenges=unresolved_challenges or [],
            llm_request_id=llm_request_id,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="conclusion",
            method_name="add_conclusion",
            artifact_id=artifact_id,
        )
        return artifact_id

    def get_feedback(self) -> list[FeedbackArtifact]:
        results = [a for a in self._artifacts.values() if isinstance(a, FeedbackArtifact) and (not a.is_deleted)]
        self._log_access(
            persona_name="system",
            phase_number=None,
            operation_type="retrieve",
            artifact_type="feedback",
            method_name="get_feedback",
            result_count=len(results),
        )
        return results

    def add_feedback(
        self,
        investigation_id: str,
        was_correct: bool,
        actual_cause: str | None = None,
        feedback_source: str = "api",
        user_id: str | None = None,
        what_was_helpful: str | None = None,
        what_was_wrong: str | None = None,
        suggestions: str | None = None,
        additional_notes: str | None = None,
        created_by: str = "system",
        phase: int | None = None,
    ) -> str:
        artifact = FeedbackArtifact(
            investigation_id=investigation_id,
            was_correct=was_correct,
            actual_cause=actual_cause,
            feedback_source=feedback_source,
            user_id=user_id,
            what_was_helpful=what_was_helpful,
            what_was_wrong=what_was_wrong,
            suggestions=suggestions,
            additional_notes=additional_notes,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="feedback",
            method_name="add_feedback",
            artifact_id=artifact_id,
        )
        return artifact_id

    def add_log_bundle(
        self,
        source_files: list[dict[str, Any]],
        merged_timeline: str,
        annotated_narrative: str = "",
        primary_error: LogBundleErrorEntry | None = None,
        error_timeline: list[LogBundleErrorEntry] | None = None,
        cascade_description: str = "",
        clues: list[LogBundleClue] | None = None,
        created_by: str = "Chronicler",
        phase: int | None = -1,
        affected_boards: list[BoardAnalysis] | None = None,
        cascade_chain: list[CascadeLink] | None = None,
        documentation_reference: str = "",
    ) -> str:
        artifact = LogBundleArtifact(
            source_files=source_files,
            merged_timeline=merged_timeline,
            annotated_narrative=annotated_narrative,
            primary_error=primary_error,
            error_timeline=error_timeline or [],
            cascade_description=cascade_description,
            clues=clues or [],
            created_by=created_by,
            phase=phase,
            affected_boards=affected_boards or [],
            cascade_chain=cascade_chain or [],
            documentation_reference=documentation_reference,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="log_bundle",
            method_name="add_log_bundle",
            artifact_id=artifact_id,
        )
        return artifact_id

    def get_log_bundle(self) -> LogBundleArtifact | None:
        bundles = self.get_by_type(ArtifactType.LOG_BUNDLE)
        if bundles:
            bundle = bundles[0]
            if isinstance(bundle, LogBundleArtifact):
                return bundle
        return None

    def add_merged_timeline(
        self,
        entries: list[MergedTimelineEntry],
        total_entries: int = 0,
        total_errors: int = 0,
        total_warnings: int = 0,
        total_info: int = 0,
        file_count: int = 0,
        earliest_timestamp: str = "",
        latest_timestamp: str = "",
        created_by: str = "Chronicler",
        phase: int | None = -1,
    ) -> str:
        artifact = MergedTimelineArtifact(
            entries=entries,
            total_entries=total_entries,
            total_errors=total_errors,
            total_warnings=total_warnings,
            total_info=total_info,
            file_count=file_count,
            earliest_timestamp=earliest_timestamp,
            latest_timestamp=latest_timestamp,
            created_by=created_by,
            phase=phase,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="merged_timeline",
            method_name="add_merged_timeline",
            artifact_id=artifact_id,
        )
        return artifact_id

    def get_merged_timeline(self) -> MergedTimelineArtifact | None:
        timelines = self.get_by_type(ArtifactType.MERGED_TIMELINE)
        if timelines:
            timeline = timelines[0]
            if isinstance(timeline, MergedTimelineArtifact):
                return timeline
        return None

    def add_boardreader_identification(
        self,
        boardreader_types: list[str],
        components: list[str],
        error_messages: list[str],
        created_by: str = "Chronicler",
        phase: int | None = -1,
        llm_request_id: str | None = None,
    ) -> str:
        artifact = BoardReaderIdentificationArtifact(
            boardreader_types=boardreader_types,
            components=components,
            error_messages=error_messages,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
        )
        artifact_id = self.add_artifact(artifact)
        self._log_access(
            persona_name=created_by,
            phase_number=phase,
            operation_type="store",
            artifact_type="boardreader_identification",
            method_name="add_boardreader_identification",
            artifact_id=artifact_id,
        )
        logger.info(
            "Stored boardreader identification: %d types, %d components", len(boardreader_types), len(components)
        )
        return artifact_id

    def get_boardreader_identification(self) -> BoardReaderIdentificationArtifact | None:
        artifacts = self.get_by_type(ArtifactType.BOARDREADER_IDENTIFICATION)
        if artifacts:
            artifact = artifacts[0]
            if isinstance(artifact, BoardReaderIdentificationArtifact):
                return artifact
        return None
