"""
File: investigations.py
Purpose: Investigation endpoints.
Category: Utility
Author: artdaq team
Depends: agent, knowledge, models, investigation, log_parser, ...
Exports: LogEntry, InvestigateRequest, InvestigateFromContentRequest, InvestigationSummary, InvestigationListResponse, ...
Complexity: High | Lines: 538
"""

import logging
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from srcs.agent import InvestigationCoordinator, QualityAnalyzer, format_quality_report
from srcs.knowledge import KnowledgeBase, PatternLearner
from srcs.models import Log
from srcs.models.investigation import InvestigationOutcome
from srcs.models.log_parser import extract_error_and_context, parse_log_content
from srcs.workbinder import BinderStore
from ..dependencies import get_investigation_coordinator, get_knowledge_base, get_pattern_learner, get_quality_analyzer
from .binders import get_binder_store

logger = logging.getLogger(__name__)
router = APIRouter()


class LogEntry(BaseModel):
    timestamp: datetime
    level: str = Field(default="ERROR", description="Log level")
    component: str = Field(..., description="Component name")
    function: str | None = Field(default=None, description="Function name")
    message: str = Field(..., description="Log message")


class InvestigateRequest(BaseModel):
    trigger_error: LogEntry = Field(..., description="The error log to investigate")
    context_logs: list[LogEntry] = Field(default_factory=list, description="Context logs before the error")


class InvestigateFromContentRequest(BaseModel):
    content: str = Field(..., description="Raw log text content")
    error_line: int | None = Field(default=None, description="Specific error line number")
    context_lines: int = Field(default=60, description="Number of context lines before error")


class InvestigationSummary(BaseModel):
    investigation_id: str
    outcome: str
    root_cause: str | None = None
    confidence: float | None = None
    duration_seconds: float
    timestamp: datetime


class InvestigationListResponse(BaseModel):
    investigations: list[InvestigationSummary]
    total: int


class FeedbackRequest(BaseModel):
    correct: bool = Field(..., description="Whether diagnosis was correct")
    actual_cause: str | None = Field(default=None, description="Actual root cause if different")
    corrected_summary: str | None = Field(default=None, description="Corrected executive summary")
    feedback_source: str = Field(default="api", description="Source of feedback")
    user_id: str | None = Field(default=None, description="ID of the user providing feedback")
    what_was_helpful: str | None = Field(default=None, description="What was helpful about the diagnosis")
    what_was_wrong: str | None = Field(default=None, description="What was wrong about the diagnosis")
    suggestions: str | None = Field(default=None, description="Suggestions for improvement")
    additional_notes: str | None = Field(default=None, description="Any additional notes")


class FeedbackResponse(BaseModel):
    message: str
    patterns_updated: int
    patterns_created: int
    patterns_updated_ids: list[str] = Field(default_factory=list)
    patterns_created_ids: list[str] = Field(default_factory=list)


class QualityReportResponse(BaseModel):
    investigation_id: str
    quality_level: str
    overall_score: float
    report_text: str


class HypothesisResponse(BaseModel):
    id: str
    description: str
    score: float
    status: str


class HypothesisDetailResponse(BaseModel):
    id: str
    description: str
    score: float
    prior: float
    source: str
    status: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]


class EvidenceItemResponse(BaseModel):
    id: str
    evidence_type: str
    content: str
    source: str
    strength: str
    found: bool
    timestamp: datetime
    targets_hypothesis_id: str | None = None
    expected_if_true: str | None = None
    expected_if_false: str | None = None


class CausalStepResponse(BaseModel):
    id: str
    step_order: int
    claim: str
    mechanism: str | None
    code_reference: str | None
    evidence_ids: list[str]
    evidence_strength: str
    is_assumption: bool
    assumption_note: str | None = None


class CausalChainResponse(BaseModel):
    id: str
    hypothesis_id: str
    logical_validity: float
    evidence_coverage: float
    gaps: list[str]
    assumptions: list[str]
    steps: list[CausalStepResponse]


class ChallengeResponse(BaseModel):
    id: str
    challenge_type: str
    content: str
    severity: str
    requires_response: bool
    resolved: bool
    resolution: str | None = None


class InvestigationDetailResponse(BaseModel):
    id: str
    trigger_error: LogEntry
    outcome: str | None
    started_at: str
    completed_at: str | None
    hypotheses: list[HypothesisResponse]
    evidence_count: int
    causal_chains_count: int
    challenges_count: int


class HypothesesListResponse(BaseModel):
    investigation_id: str
    hypotheses: list[HypothesisDetailResponse]
    total: int


class EvidenceListResponse(BaseModel):
    investigation_id: str
    evidence: list[EvidenceItemResponse]
    total: int


class ChainsListResponse(BaseModel):
    investigation_id: str
    chains: list[CausalChainResponse]
    total: int


class ChallengesListResponse(BaseModel):
    investigation_id: str
    challenges: list[ChallengeResponse]
    total: int


@router.post("/investigations", response_model=InvestigationSummary)
async def run_investigation(
    request: InvestigateRequest,
    background_tasks: BackgroundTasks,
    coordinator: Annotated[InvestigationCoordinator, Depends(get_investigation_coordinator)],
    learner: Annotated[PatternLearner, Depends(get_pattern_learner)],
) -> InvestigationSummary:
    trigger = Log(
        timestamp=request.trigger_error.timestamp,
        level=request.trigger_error.level,
        component=request.trigger_error.component,
        function=request.trigger_error.function,
        message=request.trigger_error.message,
    )
    context = [
        Log(
            timestamp=log.timestamp,
            level=log.level,
            component=log.component,
            function=log.function,
            message=log.message,
        )
        for log in request.context_logs
    ]
    result = await coordinator.investigate(trigger, context)
    background_tasks.add_task(_learn_from_investigation, learner, result.investigation_id)
    return InvestigationSummary(
        investigation_id=result.investigation_id,
        outcome=result.outcome.value,
        root_cause=result.root_cause.root_cause if result.root_cause else None,
        confidence=result.root_cause.confidence.calibrated if result.root_cause else None,
        duration_seconds=result.duration_seconds,
        timestamp=result.timestamp,
    )


async def _learn_from_investigation(learner: PatternLearner, investigation_id: str) -> None:
    try:
        await learner.learn_from_investigation_by_id(investigation_id)
    except Exception:
        logger.exception("Background learning failed for %s", investigation_id)


@router.post("/investigations/from-content", response_model=InvestigationSummary)
async def run_investigation_from_content(
    request: InvestigateFromContentRequest,
    background_tasks: BackgroundTasks,
    coordinator: Annotated[InvestigationCoordinator, Depends(get_investigation_coordinator)],
    learner: Annotated[PatternLearner, Depends(get_pattern_learner)],
) -> InvestigationSummary:
    logs = parse_log_content(request.content)
    if not logs:
        raise HTTPException(status_code=422, detail="No parseable log entries found in content")
    trigger, context = extract_error_and_context(logs, request.error_line, request.context_lines)
    result = await coordinator.investigate(trigger, context)
    background_tasks.add_task(_learn_from_investigation, learner, result.investigation_id)
    return InvestigationSummary(
        investigation_id=result.investigation_id,
        outcome=result.outcome.value,
        root_cause=result.root_cause.root_cause if result.root_cause else None,
        confidence=result.root_cause.confidence.calibrated if result.root_cause else None,
        duration_seconds=result.duration_seconds,
        timestamp=result.timestamp,
    )


class SourceFileRequest(BaseModel):
    filename: str = Field(..., description="Log file name")
    content: str = Field(..., description="Raw log file content")
    error_line: int | None = Field(default=None, description="Specific error line number")


class MultiFileInvestigateRequest(BaseModel):
    files: list[SourceFileRequest] = Field(..., description="Log files to investigate together", min_length=1)
    context_lines: int = Field(default=60, description="Number of context lines before error")


@router.post("/investigations/from-files", response_model=InvestigationSummary)
async def run_investigation_from_files(
    request: MultiFileInvestigateRequest,
    background_tasks: BackgroundTasks,
    coordinator: Annotated[InvestigationCoordinator, Depends(get_investigation_coordinator)],
    learner: Annotated[PatternLearner, Depends(get_pattern_learner)],
) -> InvestigationSummary:
    from srcs.models.logs import SourceFile

    source_files = [SourceFile(filename=f.filename, content=f.content, error_line=f.error_line) for f in request.files]
    first_logs = parse_log_content(request.files[0].content)
    if not first_logs:
        raise HTTPException(
            status_code=422, detail=f"No parseable log entries in first file: {request.files[0].filename}"
        )
    trigger, context = extract_error_and_context(first_logs, request.files[0].error_line, request.context_lines)
    result = await coordinator.investigate(trigger, context, source_files=source_files)
    background_tasks.add_task(_learn_from_investigation, learner, result.investigation_id)
    return InvestigationSummary(
        investigation_id=result.investigation_id,
        outcome=result.outcome.value,
        root_cause=result.root_cause.root_cause if result.root_cause else None,
        confidence=result.root_cause.confidence.calibrated if result.root_cause else None,
        duration_seconds=result.duration_seconds,
        timestamp=result.timestamp,
    )


@router.get("/investigations", response_model=InvestigationListResponse)
async def list_investigations(
    limit: int = Query(default=20, ge=1, le=1000, description="Maximum number to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    outcome: InvestigationOutcome | None = Query(default=None, description="Filter by outcome type"),
    kb: KnowledgeBase = Depends(get_knowledge_base),
) -> InvestigationListResponse:
    investigations = await kb.get_recent_investigations(limit, offset)
    total = await kb.count_investigations()
    if outcome:
        investigations = [inv for inv in investigations if inv.outcome and inv.outcome == outcome]
    summaries = []
    for inv in investigations:
        root_cause = None
        confidence = None
        if inv.hypotheses and inv.hypotheses[0].score > 0:
            root_cause = inv.hypotheses[0].description
            confidence = inv.hypotheses[0].score
        summaries.append(
            InvestigationSummary(
                investigation_id=inv.id,
                outcome=inv.outcome.value if inv.outcome else "UNKNOWN",
                root_cause=root_cause,
                confidence=confidence,
                duration_seconds=(inv.completed_at - inv.started_at).total_seconds() if inv.completed_at else 0.0,
                timestamp=inv.started_at,
            )
        )
    return InvestigationListResponse(investigations=summaries, total=total)


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetailResponse)
async def get_investigation(
    investigation_id: str, kb: KnowledgeBase = Depends(get_knowledge_base)
) -> InvestigationDetailResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return InvestigationDetailResponse(
        id=investigation.id,
        trigger_error=LogEntry(
            timestamp=investigation.trigger_error.timestamp,
            level=investigation.trigger_error.level,
            component=investigation.trigger_error.component,
            function=investigation.trigger_error.function,
            message=investigation.trigger_error.message,
        ),
        outcome=investigation.outcome.value if investigation.outcome else None,
        started_at=investigation.started_at.isoformat(),
        completed_at=investigation.completed_at.isoformat() if investigation.completed_at else None,
        hypotheses=[
            HypothesisResponse(id=h.id, description=h.description, score=h.score, status=h.status)
            for h in investigation.hypotheses
        ],
        evidence_count=len(investigation.evidence.items),
        causal_chains_count=len(investigation.causal_chains),
        challenges_count=len(investigation.challenges),
    )


@router.post("/investigations/{investigation_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    investigation_id: str,
    request: FeedbackRequest,
    learner: Annotated[PatternLearner, Depends(get_pattern_learner)],
    kb: KnowledgeBase = Depends(get_knowledge_base),
    store: BinderStore = Depends(get_binder_store),
) -> FeedbackResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    try:
        result = await learner.apply_feedback(
            investigation_id, request.correct, request.actual_cause, feedback_source=request.feedback_source
        )
        if investigation.hypotheses and investigation.hypotheses[0].score > 0:
            stated_confidence = min(0.95, 0.3 + investigation.hypotheses[0].score * 0.5)
            await kb.update_calibration("default", stated_confidence, request.correct)
        try:
            binder = await store.load_binder_for_investigation(investigation_id)
            if binder:
                binder.add_feedback(
                    investigation_id=investigation_id,
                    was_correct=request.correct,
                    actual_cause=request.actual_cause,
                    feedback_source=request.feedback_source,
                    user_id=request.user_id,
                    what_was_helpful=request.what_was_helpful,
                    what_was_wrong=request.what_was_wrong,
                    suggestions=request.suggestions,
                    additional_notes=request.additional_notes,
                    created_by="Reviewer",
                )
                await store.save_binder(binder)
        except Exception:
            logger.exception("Failed to persist feedback artifact for %s", investigation_id)
    except HTTPException:
        raise
    return FeedbackResponse(
        message="Feedback recorded successfully",
        patterns_updated=len(result.get("patterns_updated", [])),
        patterns_created=len(result.get("patterns_created", [])),
        patterns_updated_ids=result.get("patterns_updated", []),
        patterns_created_ids=result.get("patterns_created", []),
    )


@router.get("/investigations/{investigation_id}/quality", response_model=QualityReportResponse)
async def get_quality_report(
    investigation_id: str,
    kb: KnowledgeBase = Depends(get_knowledge_base),
    analyzer: QualityAnalyzer = Depends(get_quality_analyzer),
) -> QualityReportResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    report = analyzer.analyze(investigation)
    return QualityReportResponse(
        investigation_id=investigation_id,
        quality_level=report.quality_level.value,
        overall_score=report.overall_score,
        report_text=format_quality_report(report),
    )


@router.get("/investigations/{investigation_id}/hypotheses", response_model=HypothesesListResponse)
async def get_investigation_hypotheses(
    investigation_id: str, kb: KnowledgeBase = Depends(get_knowledge_base)
) -> HypothesesListResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return HypothesesListResponse(
        investigation_id=investigation_id,
        hypotheses=[
            HypothesisDetailResponse(
                id=h.id,
                description=h.description,
                score=h.score,
                prior=h.prior,
                source=h.source,
                status=h.status,
                supporting_evidence_ids=h.supporting_evidence_ids,
                contradicting_evidence_ids=h.contradicting_evidence_ids,
            )
            for h in investigation.hypotheses
        ],
        total=len(investigation.hypotheses),
    )


@router.get("/investigations/{investigation_id}/evidence", response_model=EvidenceListResponse)
async def get_investigation_evidence(
    investigation_id: str,
    strength: str | None = Query(default=None, description="Filter by strength (STRONG, MODERATE, WEAK)"),
    evidence_type: str | None = Query(default=None, description="Filter by type (log, code, config, absence)"),
    kb: KnowledgeBase = Depends(get_knowledge_base),
) -> EvidenceListResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    items = list(investigation.evidence.items.values())
    if strength:
        items = [e for e in items if e.strength == strength]
    if evidence_type:
        items = [e for e in items if e.evidence_type == evidence_type]
    return EvidenceListResponse(
        investigation_id=investigation_id,
        evidence=[
            EvidenceItemResponse(
                id=e.id,
                evidence_type=e.evidence_type,
                content=e.content,
                source=e.source,
                strength=e.strength,
                found=e.found,
                timestamp=e.timestamp,
                targets_hypothesis_id=e.targets_hypothesis_id,
                expected_if_true=e.expected_if_true,
                expected_if_false=e.expected_if_false,
            )
            for e in items
        ],
        total=len(items),
    )


@router.get("/investigations/{investigation_id}/chains", response_model=ChainsListResponse)
async def get_investigation_chains(
    investigation_id: str, kb: KnowledgeBase = Depends(get_knowledge_base)
) -> ChainsListResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return ChainsListResponse(
        investigation_id=investigation_id,
        chains=[
            CausalChainResponse(
                id=c.id,
                hypothesis_id=c.hypothesis_id,
                logical_validity=c.logical_validity,
                evidence_coverage=c.evidence_coverage,
                gaps=c.gaps,
                assumptions=c.assumptions,
                steps=[
                    CausalStepResponse(
                        id=s.id,
                        step_order=s.step_order,
                        claim=s.claim,
                        mechanism=s.mechanism,
                        code_reference=s.code_reference,
                        evidence_ids=s.evidence_ids,
                        evidence_strength=s.evidence_strength,
                        is_assumption=s.is_assumption,
                        assumption_note=s.assumption_note,
                    )
                    for s in c.steps
                ],
            )
            for c in investigation.causal_chains
        ],
        total=len(investigation.causal_chains),
    )


@router.get("/investigations/{investigation_id}/challenges", response_model=ChallengesListResponse)
async def get_investigation_challenges(
    investigation_id: str,
    resolved: bool | None = Query(default=None, description="Filter by resolved status"),
    severity: str | None = Query(default=None, description="Filter by severity (HIGH, MEDIUM, LOW)"),
    kb: KnowledgeBase = Depends(get_knowledge_base),
) -> ChallengesListResponse:
    investigation = await kb.get_investigation(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    challenges = investigation.challenges
    if resolved is not None:
        challenges = [c for c in challenges if c.resolved == resolved]
    if severity:
        challenges = [c for c in challenges if c.severity == severity]
    return ChallengesListResponse(
        investigation_id=investigation_id,
        challenges=[
            ChallengeResponse(
                id=c.id,
                challenge_type=c.challenge_type,
                content=c.content,
                severity=c.severity,
                requires_response=c.requires_response,
                resolved=c.resolved,
                resolution=c.resolution,
            )
            for c in challenges
        ],
        total=len(challenges),
    )
