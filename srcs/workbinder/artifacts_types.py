"""
File: artifacts_types.py
Purpose: Artifact types for Work Binder.
Category: Utility
Author: artdaq team
Depends: base, pydantic
Exports: ArtifactType, Priority, FindingType, AnnotationType, Artifact, ...
Complexity: High | Lines: 418
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from srcs.models.base import generate_id


class ArtifactType(str, Enum):
    CALL_GRAPH = "call_graph"
    CODE_SNIPPET = "code_snippet"
    FINDING = "finding"
    ANNOTATION = "annotation"
    SOURCE_LOCATION = "source_location"
    HYPOTHESIS = "hypothesis"
    EVIDENCE = "evidence"
    ERROR_CONTEXT = "error_context"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    FLOW_CONFIG = "flow_config"
    PHASE_STATE = "phase_state"
    INVESTIGATION_STATE = "investigation_state"
    PERSONA_CONTRIBUTION = "persona_contribution"
    HYPOTHESIS_ARTIFACT = "hypothesis_artifact"
    EVIDENCE_ARTIFACT = "evidence_artifact"
    CAUSAL_CHAIN = "causal_chain"
    CHALLENGE = "challenge"
    CONCLUSION = "conclusion"
    FUNCTION_SUMMARY = "function_summary"
    LOG_BUNDLE = "log_bundle"
    MERGED_TIMELINE = "merged_timeline"
    BOARDREADER_IDENTIFICATION = "boardreader_identification"
    FEEDBACK = "feedback"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(str, Enum):
    OBSERVATION = "observation"
    QUESTION = "question"
    CONCLUSION = "conclusion"
    WARNING = "warning"
    RECOMMENDATION = "recommendation"


class AnnotationType(str, Enum):
    COMMENT = "comment"
    HIGHLIGHT = "highlight"
    QUESTION = "question"
    CORRECTION = "correction"


class Artifact(BaseModel):
    id: str = Field(default_factory=generate_id)
    artifact_type: ArtifactType
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)
    phase: int | None = None
    function_name: str | None = None
    priority: Priority = Priority.NORMAL
    is_deleted: bool = False
    deleted_by: str | None = None
    deleted_reason: str | None = None


class CallerInfo(BaseModel):
    caller_name: str
    caller_file: str | None = None
    caller_line: int | None = None
    call_line: int | None = None
    summary: str | None = None
    body: str | None = None
    relationship: str | None = None


class CalleeInfo(BaseModel):
    callee_name: str
    callee_file: str | None = None
    callee_line: int | None = None
    callee_signature: str | None = None
    summary: str | None = None
    body: str | None = None
    relationship: str | None = None


class CallGraphNode(Artifact):
    artifact_type: ArtifactType = ArtifactType.CALL_GRAPH
    center_function: str
    callers: list[CallerInfo] = Field(default_factory=list)
    callees: list[CalleeInfo] = Field(default_factory=list)
    depth_explored: int = 1
    diagram: str | None = None


class CodeSnippet(Artifact):
    artifact_type: ArtifactType = ArtifactType.CODE_SNIPPET
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str = "cpp"
    snippet_function_name: str | None = None
    summary: str | None = None
    match_score: float | None = None


class Finding(Artifact):
    artifact_type: ArtifactType = ArtifactType.FINDING
    persona: str
    finding_type: FindingType
    content: str
    related_artifacts: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Annotation(Artifact):
    artifact_type: ArtifactType = ArtifactType.ANNOTATION
    target_artifact_id: str
    annotation_type: AnnotationType
    annotation_content: str


class SourceLocationArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.SOURCE_LOCATION
    file_path: str
    line_number: int
    matched_line: str | None = None
    match_score: float = 0.0
    is_log_statement: bool = False
    function_signature: str | None = None
    function_body: str | None = None
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class ErrorContextArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.ERROR_CONTEXT
    error_message: str
    error_level: str = "ERROR"
    error_component: str | None = None
    error_function: str | None = None
    error_timestamp: datetime | None = None
    context_logs: list[dict[str, Any]] = Field(default_factory=list)


class ArtifactHistory(BaseModel):
    id: str = Field(default_factory=generate_id)
    artifact_id: str
    modified_by: str
    modified_at: datetime = Field(default_factory=datetime.now)
    action: str
    changes: dict[str, Any] = Field(default_factory=dict)


class LLMRequestArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.LLM_REQUEST
    persona: str
    prompt_key: str
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float = 0.1
    max_tokens: int = 4096
    request_timestamp: datetime = Field(default_factory=datetime.now)
    linked_response_id: str | None = None


class LLMResponseArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.LLM_RESPONSE
    linked_request_id: str
    raw_response: str
    parsed_content: dict[str, Any] | None = None
    tokens_used: int = 0
    latency_ms: float = 0.0
    response_timestamp: datetime = Field(default_factory=datetime.now)
    parse_success: bool = True
    parse_errors: list[str] = Field(default_factory=list)


class FlowConfigArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.FLOW_CONFIG
    investigation_config: dict[str, Any] = Field(default_factory=dict)
    llm_config: dict[str, Any] = Field(default_factory=dict)
    source_config: dict[str, Any] | None = None
    pipeline_config: dict[str, Any] | None = None
    enabled_phases: list[int] = Field(default_factory=lambda: list(range(8)))
    phase_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PhaseStateArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.PHASE_STATE
    phase_number: int
    persona_name: str
    status: str = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    error_message: str | None = None


class InvestigationStateArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.INVESTIGATION_STATE
    investigation_id: str
    trigger_error_artifact_id: str | None = None
    current_phase: int = 0
    outcome: str | None = None
    status: str = "active"
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    paused_at: datetime | None = None
    pause_reason: str | None = None
    resume_count: int = 0


class PersonaContributionArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.PERSONA_CONTRIBUTION
    persona_id: str
    contribution_phase: int
    content: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.5
    reasoning: str = ""


class HypothesisArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.HYPOTHESIS_ARTIFACT
    description: str
    source: str = "fresh"
    prior_probability: float = 0.5
    score: float = 0.5
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    rank: int = 0
    llm_request_id: str | None = None
    category: str | None = None
    confirming_evidence: str | None = None
    refuting_evidence: str | None = None


class EvidenceArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.EVIDENCE_ARTIFACT
    evidence_type: str
    content: str
    source: str
    strength: str = "MODERATE"
    supports_hypothesis_ids: list[str] = Field(default_factory=list)
    contradicts_hypothesis_ids: list[str] = Field(default_factory=list)
    llm_request_id: str | None = None
    found: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)
    targets_hypothesis_id: str | None = None
    expected_if_true: str | None = None
    expected_if_false: str | None = None


class CausalChainArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.CAUSAL_CHAIN
    hypothesis_id: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    completeness_score: float = 0.0
    logical_validity: float = 0.0
    evidence_coverage: float = 0.0
    gaps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    llm_request_id: str | None = None


class ChallengeArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.CHALLENGE
    target_hypothesis_id: str
    challenge_type: str = "unknown"
    content: str
    severity: str = "MEDIUM"
    requires_response: bool = True
    resolved: bool = False
    resolution: str | None = None
    llm_request_id: str | None = None


class ConclusionArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.CONCLUSION
    root_cause: str
    confidence_raw: float = 0.0
    confidence_calibrated: float = 0.0
    outcome: str = "UNCERTAIN"
    code_location: str | None = None
    code_snippet: str | None = None
    data_flow: str | None = None
    caveats: list[str] = Field(default_factory=list)
    debugging_steps: list[str] = Field(default_factory=list)
    unresolved_challenges: list[str] = Field(default_factory=list)
    llm_request_id: str | None = None


class FunctionSummaryArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.FUNCTION_SUMMARY
    file_path: str | None = None
    purpose: str
    mechanism: str
    data_flow: str
    error_paths: str
    error_line_relevance: str
    center_function: str
    role: str


class LogBundleErrorEntry(BaseModel):
    filename: str
    line_number: int | None = None
    timestamp: datetime | None = None
    level: str = "ERROR"
    component: str | None = None
    message: str
    is_primary: bool = False


class LogBundleClue(BaseModel):
    clue_type: str
    description: str
    source_file: str
    relevance: str = "HIGH"
    suggested_search: str | None = None


class BoardAnalysis(BaseModel):
    board_name: str
    filename: str = ""
    role: str = "unknown"
    failure_mode: str = ""
    key_error_message: str = ""
    source_location: str = ""
    error_count: int = 0
    warning_count: int = 0


class CascadeLink(BaseModel):
    from_board: str
    to_board: str
    mechanism: str
    evidence: str = ""


class LogBundleArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.LOG_BUNDLE
    source_files: list[dict[str, Any]] = Field(default_factory=list)
    merged_timeline: str = ""
    annotated_narrative: str = ""
    primary_error: LogBundleErrorEntry | None = None
    error_timeline: list[LogBundleErrorEntry] = Field(default_factory=list)
    cascade_description: str = ""
    clues: list[LogBundleClue] = Field(default_factory=list)
    affected_boards: list[BoardAnalysis] = Field(default_factory=list)
    cascade_chain: list[CascadeLink] = Field(default_factory=list)
    documentation_reference: str = ""


class MergedTimelineEntry(BaseModel):
    timestamp: str = ""
    source_file: str = ""
    board_name: str = ""
    level: str = "info"
    component: str = ""
    message: str = ""
    source_location: str = ""


class MergedTimelineArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.MERGED_TIMELINE
    entries: list[MergedTimelineEntry] = Field(default_factory=list)
    total_entries: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    total_info: int = 0
    file_count: int = 0
    earliest_timestamp: str = ""
    latest_timestamp: str = ""


class BoardReaderIdentificationArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.BOARDREADER_IDENTIFICATION
    boardreader_types: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    llm_request_id: str | None = None


class FeedbackArtifact(Artifact):
    artifact_type: ArtifactType = ArtifactType.FEEDBACK
    investigation_id: str
    was_correct: bool
    actual_cause: str | None = None
    feedback_source: str = "api"
    user_id: str | None = None
    what_was_helpful: str | None = None
    what_was_wrong: str | None = None
    suggestions: str | None = None
    additional_notes: str | None = None


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=generate_id)
    persona_name: str
    phase_number: int | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    access_sequence: int
    operation_type: str
    artifact_type: str
    artifact_id: str | None = None
    method_name: str
    result_count: int = 1
    success: bool = True
