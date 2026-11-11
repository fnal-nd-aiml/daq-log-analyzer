"""
File: binders.py
Purpose: Workbinder access endpoints.
Category: Utility
Author: artdaq team
Depends: config, workbinder, pydantic
Exports: BinderSummaryResponse, BinderDetailResponse, BinderInvestigationSummaryResponse, ArtifactResponse, ArtifactHistoryEntryResponse, ...
Complexity: High | Lines: 513
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from srcs.workbinder import BinderStore
from ..dependencies import Settings, get_settings
logger = logging.getLogger(__name__)
router = APIRouter()

class BinderSummaryResponse(BaseModel):
    binder_id: str
    investigation_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    artifact_count: int | None = None

class BinderDetailResponse(BaseModel):
    id: str
    investigation_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    artifact_counts: dict[str, int]

class BinderInvestigationSummaryResponse(BaseModel):
    binder_id: str
    investigation_id: str
    status: str
    current_phase: int
    outcome: str | None
    resume_count: int
    artifact_counts: dict[str, int]
    created_at: datetime
    updated_at: datetime

class ArtifactResponse(BaseModel):
    id: str
    artifact_type: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    phase: int | None
    function_name: str | None
    priority: str
    tags: list[str]
    is_deleted: bool
    content: dict[str, Any]

class ArtifactHistoryEntryResponse(BaseModel):
    id: str
    artifact_id: str
    modified_by: str
    modified_at: datetime
    action: str
    changes: dict[str, Any]

class AuditLogEntryResponse(BaseModel):
    id: str
    persona_name: str
    phase_number: int | None
    timestamp: datetime
    access_sequence: int
    operation_type: str
    artifact_type: str
    artifact_id: str | None
    method_name: str
    result_count: int
    success: bool

class AuditSummaryResponse(BaseModel):
    total_entries: int
    by_persona: dict[str, int]
    by_phase: dict[str, int]
    by_operation: dict[str, int]

class BinderListResponse(BaseModel):
    binders: list[BinderSummaryResponse]
    total: int

class ArtifactListResponse(BaseModel):
    artifacts: list[ArtifactResponse]
    total: int

class ArtifactSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description='Search query string')
    artifact_types: list[str] | None = Field(default=None, description='Filter by artifact types')

class LLMExchangeResponse(BaseModel):
    request: ArtifactResponse
    response: ArtifactResponse | None

class LLMStatisticsResponse(BaseModel):
    total_requests: int
    total_responses: int
    total_tokens_used: int
    total_latency_ms: float
    average_latency_ms: float
    by_persona: dict[str, int]
    by_phase: dict[str, int]
    parse_successes: int
    parse_failures: int

class SingleArtifactResponse(BaseModel):
    artifact: ArtifactResponse

class InvestigationStateResponse(BaseModel):
    artifact: ArtifactResponse

class ValidationResponse(BaseModel):
    binder_id: str
    valid: bool
    errors: list[str]

class SimilarInvestigationRequest(BaseModel):
    error_function: str | None = Field(default=None, description='Function name to match')
    error_message_pattern: str | None = Field(default=None, description='Message pattern substring to match')
    limit: int = Field(default=10, ge=1, le=100, description='Maximum results')

class InvestigationWithStateResponse(BaseModel):
    binder_id: str
    investigation_id: str
    binder_status: str
    created_at: str
    updated_at: str
    current_phase: int | None = None
    investigation_status: str | None = None
    outcome: str | None = None

class ResumableInvestigationResponse(BaseModel):
    binder_id: str
    investigation_id: str
    created_at: str
    updated_at: str
    status: str

class ResumeInvestigationResponse(BaseModel):
    investigation_id: str
    outcome: str
    confidence: float
    resumed_from_phase: int

def get_binder_store(settings: Annotated[Settings, Depends(get_settings)]) -> BinderStore:
    data_dir = Path(settings.data_dir)
    return BinderStore(data_dir / 'knowledge.db')

class BinderByInvestigationResponse(BaseModel):
    binder_id: str
    investigation_id: str

@router.get('/binders/by-investigation/{investigation_id}', response_model=BinderByInvestigationResponse)
async def get_binder_by_investigation(investigation_id: str, store: BinderStore=Depends(get_binder_store)) -> BinderByInvestigationResponse:
    binder_id = await store.get_binder_id_for_investigation(investigation_id)
    if not binder_id:
        raise HTTPException(status_code=404, detail=f'No binder found for investigation: {investigation_id}')
    return BinderByInvestigationResponse(binder_id=binder_id, investigation_id=investigation_id)

@router.get('/binders/resumable', response_model=list[ResumableInvestigationResponse])
async def list_resumable_investigations(store: BinderStore=Depends(get_binder_store)) -> list[ResumableInvestigationResponse]:
    resumable = await store.list_resumable_investigations()
    return [ResumableInvestigationResponse(binder_id=r['binder_id'], investigation_id=r['investigation_id'], created_at=r['created_at'], updated_at=r['updated_at'], status=r['status']) for r in resumable]

@router.post('/binders/{investigation_id}/resume', response_model=ResumeInvestigationResponse, status_code=200)
async def resume_investigation(investigation_id: str, store: BinderStore=Depends(get_binder_store)) -> ResumeInvestigationResponse:
    binder = await store.load_binder_for_investigation(investigation_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'No binder found for investigation: {investigation_id}')
    if not binder.can_resume():
        raise HTTPException(status_code=409, detail=f'Investigation {investigation_id} is not in paused state')
    resume_phase, _ = binder.get_resume_point()
    try:
        from srcs.config import CoordinatorFactory, load_config
        config = load_config()
        coordinator = CoordinatorFactory.create(config)
        result = await coordinator.resume_investigation(investigation_id)
    except ValueError as e:
        if 'not found' in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        if 'not in paused state' in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception('Failed to resume investigation')
        raise HTTPException(status_code=500, detail=f'Failed to resume investigation: {str(e)}')
    confidence = 0.0
    if result.root_cause and result.root_cause.confidence:
        confidence = result.root_cause.confidence.calibrated
    return ResumeInvestigationResponse(investigation_id=investigation_id, outcome=result.outcome.value if result.outcome else 'UNKNOWN', confidence=confidence, resumed_from_phase=resume_phase)

@router.get('/binders/investigations', response_model=list[InvestigationWithStateResponse])
async def list_investigations_with_state(outcome: str | None=Query(default=None, description='Filter by outcome (CONFIDENT, PROBABLE, UNCERTAIN, etc.)'), status: str | None=Query(default=None, description='Filter by binder status (active, paused, archived)'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> list[InvestigationWithStateResponse]:
    investigations = await store.list_investigations_with_state(outcome=outcome, status=status, limit=limit)
    return [InvestigationWithStateResponse(**inv) for inv in investigations]

@router.post('/binders/similar', response_model=list[dict[str, Any]])
async def find_similar_investigations(request: SimilarInvestigationRequest, store: BinderStore=Depends(get_binder_store)) -> list[dict[str, Any]]:
    return await store.get_similar_investigations(error_function=request.error_function, error_message_pattern=request.error_message_pattern, limit=request.limit)

@router.get('/binders', response_model=BinderListResponse)
async def list_binders(status: str | None=Query(default=None, description='Filter by status'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> BinderListResponse:
    binders = await store.list_binders(status=status, limit=limit)
    return BinderListResponse(binders=[BinderSummaryResponse(binder_id=b['id'], investigation_id=b['investigation_id'], status=b['status'], created_at=datetime.fromisoformat(b['created_at']), updated_at=datetime.fromisoformat(b['updated_at'])) for b in binders], total=len(binders))

@router.get('/binders/{binder_id}', response_model=BinderDetailResponse)
async def get_binder(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> BinderDetailResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    counts = await store.get_artifact_count(binder_id)
    return BinderDetailResponse(id=binder.id, investigation_id=binder.investigation_id, status=binder.status, created_at=binder.created_at, updated_at=binder.updated_at, artifact_counts=counts)

@router.get('/binders/{binder_id}/summary', response_model=BinderInvestigationSummaryResponse)
async def get_binder_summary(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> BinderInvestigationSummaryResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    summary = await store.get_investigation_summary(binder.investigation_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f'No summary found for binder: {binder_id}')
    return BinderInvestigationSummaryResponse(binder_id=summary['binder_id'], investigation_id=summary['investigation_id'], status=summary['status'], current_phase=summary['current_phase'], outcome=summary['outcome'], resume_count=summary['resume_count'], artifact_counts=summary['artifact_counts'], created_at=datetime.fromisoformat(summary['created_at']), updated_at=datetime.fromisoformat(summary['updated_at']))

@router.get('/binders/{binder_id}/hypotheses', response_model=ArtifactListResponse)
async def get_hypotheses(binder_id: str, min_score: float | None=Query(default=None, ge=0.0, le=1.0, description='Minimum hypothesis score'), source: str | None=Query(default=None, description='Filter by source (pattern, similar, fresh, alternative)'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    hypotheses = await store.get_hypotheses(binder_id=binder_id, min_score=min_score, source=source, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in hypotheses], total=len(hypotheses))

@router.get('/binders/{binder_id}/evidence', response_model=ArtifactListResponse)
async def get_evidence(binder_id: str, evidence_type: str | None=Query(default=None, description='Filter by type (code, log, pattern, etc.)'), strength: str | None=Query(default=None, description='Filter by strength (STRONG, MODERATE, WEAK)'), limit: int=Query(default=100, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    evidence = await store.get_evidence_items(binder_id=binder_id, evidence_type=evidence_type, strength=strength, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in evidence], total=len(evidence))

@router.get('/binders/{binder_id}/chains', response_model=ArtifactListResponse)
async def get_causal_chains(binder_id: str, hypothesis_id: str | None=Query(default=None, description='Filter by linked hypothesis ID'), limit: int=Query(default=20, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    chains = await store.get_causal_chains(binder_id=binder_id, hypothesis_id=hypothesis_id, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in chains], total=len(chains))

@router.get('/binders/{binder_id}/challenges', response_model=ArtifactListResponse)
async def get_challenges(binder_id: str, resolved: bool | None=Query(default=None, description='Filter by resolution status'), severity: str | None=Query(default=None, description='Filter by severity (LOW, MEDIUM, HIGH)'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    challenges = await store.get_challenges(binder_id=binder_id, resolved=resolved, severity=severity, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in challenges], total=len(challenges))

@router.get('/binders/{binder_id}/llm/requests', response_model=ArtifactListResponse)
async def get_llm_requests(binder_id: str, persona: str | None=Query(default=None, description='Filter by persona name'), phase: int | None=Query(default=None, ge=0, le=7, description='Filter by phase number'), prompt_key: str | None=Query(default=None, description='Filter by prompt key'), limit: int=Query(default=100, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    requests = await store.get_llm_requests(binder_id=binder_id, persona=persona, phase=phase, prompt_key=prompt_key, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in requests], total=len(requests))

@router.get('/binders/{binder_id}/llm/responses', response_model=ArtifactListResponse)
async def get_llm_responses(binder_id: str, request_id: str | None=Query(default=None, description='Filter by specific request ID'), phase: int | None=Query(default=None, ge=0, le=7, description='Filter by phase number'), parse_success: bool | None=Query(default=None, description='Filter by parse success status'), limit: int=Query(default=100, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    responses = await store.get_llm_responses(binder_id=binder_id, request_id=request_id, phase=phase, parse_success=parse_success, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in responses], total=len(responses))

@router.get('/binders/{binder_id}/llm/exchanges', response_model=list[LLMExchangeResponse])
async def get_llm_exchanges(binder_id: str, phase: int | None=Query(default=None, ge=0, le=7, description='Filter by phase number'), store: BinderStore=Depends(get_binder_store)) -> list[LLMExchangeResponse]:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    exchanges = await store.get_llm_exchanges(binder_id=binder_id, phase=phase)
    return [LLMExchangeResponse(request=_artifact_to_response(req), response=_artifact_to_response(resp) if resp else None) for req, resp in exchanges]

@router.get('/binders/{binder_id}/llm/statistics', response_model=LLMStatisticsResponse)
async def get_llm_statistics(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> LLMStatisticsResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    stats = await store.get_llm_statistics(binder_id)
    return LLMStatisticsResponse(total_requests=stats['total_requests'], total_responses=stats['total_responses'], total_tokens_used=stats['total_tokens_used'], total_latency_ms=stats['total_latency_ms'], average_latency_ms=stats['average_latency_ms'], by_persona=stats['by_persona'], by_phase=stats['by_phase'], parse_successes=stats['parse_successes'], parse_failures=stats['parse_failures'])

@router.get('/binders/{binder_id}/state', response_model=InvestigationStateResponse)
async def get_investigation_state(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> InvestigationStateResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    state = await store.get_investigation_state_artifact(binder_id)
    if not state:
        raise HTTPException(status_code=404, detail=f'No investigation state found for binder: {binder_id}')
    return InvestigationStateResponse(artifact=_artifact_to_response(state))

@router.get('/binders/{binder_id}/phases', response_model=ArtifactListResponse)
async def get_phase_states(binder_id: str, status: str | None=Query(default=None, description='Filter by status (pending, running, completed, failed)'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    phases = await store.get_phase_states(binder_id=binder_id, status=status)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in phases], total=len(phases))

@router.get('/binders/{binder_id}/validate', response_model=ValidationResponse)
async def validate_references(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> ValidationResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    try:
        await store.validate_references(binder_id)
        return ValidationResponse(binder_id=binder_id, valid=True, errors=[])
    except ValueError as e:
        error_lines = str(e).split('\n')
        errors = [line.strip().lstrip('- ') for line in error_lines[1:] if line.strip().startswith('-')]
        return ValidationResponse(binder_id=binder_id, valid=False, errors=errors)

async def _query_typed_artifacts(binder_id: str, artifact_type: str, store: BinderStore, limit: int=50, offset: int=0) -> list[Any]:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    return await store.query_artifacts(binder_id=binder_id, artifact_type=artifact_type, limit=limit, offset=offset)

@router.get('/binders/{binder_id}/conclusion', response_model=SingleArtifactResponse)
async def get_conclusion(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> SingleArtifactResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'conclusion', store, limit=1)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f'No conclusion found for binder: {binder_id}')
    return SingleArtifactResponse(artifact=_artifact_to_response(artifacts[0]))

@router.get('/binders/{binder_id}/feedback', response_model=ArtifactListResponse)
async def get_feedback(binder_id: str, limit: int=Query(default=50, ge=1, le=500), offset: int=Query(default=0, ge=0), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'feedback', store, limit=limit, offset=offset)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/error-context', response_model=SingleArtifactResponse)
async def get_error_context(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> SingleArtifactResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'error_context', store, limit=1)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f'No error context found for binder: {binder_id}')
    return SingleArtifactResponse(artifact=_artifact_to_response(artifacts[0]))

@router.get('/binders/{binder_id}/config', response_model=SingleArtifactResponse)
async def get_flow_config(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> SingleArtifactResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'flow_config', store, limit=1)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f'No flow config found for binder: {binder_id}')
    return SingleArtifactResponse(artifact=_artifact_to_response(artifacts[0]))

@router.get('/binders/{binder_id}/log-bundle', response_model=SingleArtifactResponse)
async def get_log_bundle(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> SingleArtifactResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'log_bundle', store, limit=1)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f'No log bundle found for binder: {binder_id}')
    return SingleArtifactResponse(artifact=_artifact_to_response(artifacts[0]))

@router.get('/binders/{binder_id}/merged-timeline', response_model=SingleArtifactResponse)
async def get_merged_timeline(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> SingleArtifactResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'merged_timeline', store, limit=1)
    if not artifacts:
        raise HTTPException(status_code=404, detail=f'No merged timeline found for binder: {binder_id}')
    return SingleArtifactResponse(artifact=_artifact_to_response(artifacts[0]))

@router.get('/binders/{binder_id}/findings', response_model=ArtifactListResponse)
async def get_findings(binder_id: str, persona: str | None=Query(default=None, description='Filter by persona name'), finding_type: str | None=Query(default=None, description='Filter by type (observation, question, conclusion, warning, recommendation)'), min_confidence: float | None=Query(default=None, ge=0.0, le=1.0, description='Minimum confidence score'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'finding', store, limit=limit)
    if persona:
        artifacts = [a for a in artifacts if getattr(a, 'persona', None) == persona]
    if finding_type:

        def _match_finding_type(a: Any) -> bool:
            ft = getattr(a, 'finding_type', None)
            if ft is None:
                return False
            ft_str: str = ft.value if hasattr(ft, 'value') else str(ft)
            return ft_str == finding_type
        artifacts = [a for a in artifacts if _match_finding_type(a)]
    if min_confidence is not None:
        artifacts = [a for a in artifacts if getattr(a, 'confidence', 0.0) >= min_confidence]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/contributions', response_model=ArtifactListResponse)
async def get_contributions(binder_id: str, persona_id: str | None=Query(default=None, description='Filter by persona identifier'), contribution_phase: int | None=Query(default=None, ge=0, le=7, description='Filter by contribution phase'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'persona_contribution', store, limit=limit)
    if persona_id:
        artifacts = [a for a in artifacts if getattr(a, 'persona_id', None) == persona_id]
    if contribution_phase is not None:
        artifacts = [a for a in artifacts if getattr(a, 'contribution_phase', None) == contribution_phase]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/source-locations', response_model=ArtifactListResponse)
async def get_source_locations(binder_id: str, file_path: str | None=Query(default=None, description='Filter by file path substring'), min_match_score: float | None=Query(default=None, ge=0.0, le=1.0, description='Minimum match score'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'source_location', store, limit=limit)
    if file_path:
        artifacts = [a for a in artifacts if file_path in getattr(a, 'file_path', '')]
    if min_match_score is not None:
        artifacts = [a for a in artifacts if getattr(a, 'match_score', 0.0) >= min_match_score]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/code-snippets', response_model=ArtifactListResponse)
async def get_code_snippets(binder_id: str, file_path: str | None=Query(default=None, description='Filter by file path substring'), language: str | None=Query(default=None, description='Filter by language (e.g. cpp, python)'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'code_snippet', store, limit=limit)
    if file_path:
        artifacts = [a for a in artifacts if file_path in getattr(a, 'file_path', '')]
    if language:
        artifacts = [a for a in artifacts if getattr(a, 'language', '') == language]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/call-graphs', response_model=ArtifactListResponse)
async def get_call_graphs(binder_id: str, center_function: str | None=Query(default=None, description='Filter by center function name'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'call_graph', store, limit=limit)
    if center_function:
        artifacts = [a for a in artifacts if getattr(a, 'center_function', None) == center_function]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/function-summaries', response_model=ArtifactListResponse)
async def get_function_summaries(binder_id: str, center_function: str | None=Query(default=None, description='Filter by center function name'), role: str | None=Query(default=None, description='Filter by role (CALLER or CALLEE)'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'function_summary', store, limit=limit)
    if center_function:
        artifacts = [a for a in artifacts if getattr(a, 'center_function', None) == center_function]
    if role:
        artifacts = [a for a in artifacts if getattr(a, 'role', None) == role]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/annotations', response_model=ArtifactListResponse)
async def get_annotations(binder_id: str, target_artifact_id: str | None=Query(default=None, description='Filter by target artifact ID'), annotation_type: str | None=Query(default=None, description='Filter by type (comment, highlight, question, correction)'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'annotation', store, limit=limit)
    if target_artifact_id:
        artifacts = [a for a in artifacts if getattr(a, 'target_artifact_id', None) == target_artifact_id]
    if annotation_type:

        def _match_annotation_type(a: Any) -> bool:
            at = getattr(a, 'annotation_type', None)
            if at is None:
                return False
            at_str: str = at.value if hasattr(at, 'value') else str(at)
            return at_str == annotation_type
        artifacts = [a for a in artifacts if _match_annotation_type(a)]
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/boardreader-ids', response_model=ArtifactListResponse)
async def get_boardreader_identifications(binder_id: str, limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    artifacts = await _query_typed_artifacts(binder_id, 'boardreader_identification', store, limit=limit)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/artifacts', response_model=ArtifactListResponse)
async def search_artifacts(binder_id: str, artifact_type: str | None=Query(default=None, description='Filter by type'), phase: int | None=Query(default=None, ge=0, le=7, description='Filter by phase'), function_name: str | None=Query(default=None, description='Filter by function'), tags: list[str]=Query(default=[], description='Filter by tags (all must match)'), include_deleted: bool=Query(default=False, description='Include deleted artifacts'), limit: int=Query(default=50, ge=1, le=500, description='Maximum results'), offset: int=Query(default=0, ge=0, description='Pagination offset'), store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type=artifact_type, phase=phase, function_name=function_name, tags=tags if tags else None, include_deleted=include_deleted, limit=limit, offset=offset)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/artifacts/{artifact_id}', response_model=ArtifactResponse)
async def get_artifact(binder_id: str, artifact_id: str, store: BinderStore=Depends(get_binder_store)) -> ArtifactResponse:
    artifact = await store.get_artifact_by_id(binder_id, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f'Artifact not found: {artifact_id}')
    return _artifact_to_response(artifact)

@router.get('/binders/{binder_id}/artifacts/{artifact_id}/history', response_model=list[ArtifactHistoryEntryResponse])
async def get_artifact_history(binder_id: str, artifact_id: str, store: BinderStore=Depends(get_binder_store)) -> list[ArtifactHistoryEntryResponse]:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    history = [h for h in binder._history if h.artifact_id == artifact_id]
    return [ArtifactHistoryEntryResponse(id=h.id, artifact_id=h.artifact_id, modified_by=h.modified_by, modified_at=h.modified_at, action=h.action, changes=h.changes) for h in history]

@router.post('/binders/{binder_id}/artifacts/search', response_model=ArtifactListResponse)
async def search_artifact_content(binder_id: str, request: ArtifactSearchRequest, store: BinderStore=Depends(get_binder_store)) -> ArtifactListResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    artifacts = await store.search_artifacts(binder_id=binder_id, query=request.query, artifact_types=request.artifact_types)
    return ArtifactListResponse(artifacts=[_artifact_to_response(a) for a in artifacts], total=len(artifacts))

@router.get('/binders/{binder_id}/audit', response_model=list[AuditLogEntryResponse])
async def search_audit_log(binder_id: str, persona_name: str | None=Query(default=None, description='Filter by persona'), phase_number: int | None=Query(default=None, ge=0, le=7, description='Filter by phase'), operation_type: str | None=Query(default=None, description='Filter by operation (store/retrieve)'), limit: int=Query(default=100, ge=1, le=1000, description='Maximum entries'), store: BinderStore=Depends(get_binder_store)) -> list[AuditLogEntryResponse]:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    entries = await store.get_audit_log(binder_id=binder_id, persona_name=persona_name, phase_number=phase_number, operation_type=operation_type, limit=limit)
    return [AuditLogEntryResponse(id=e.id, persona_name=e.persona_name, phase_number=e.phase_number, timestamp=e.timestamp, access_sequence=e.access_sequence, operation_type=e.operation_type, artifact_type=e.artifact_type, artifact_id=e.artifact_id, method_name=e.method_name, result_count=e.result_count, success=e.success) for e in entries]

@router.get('/binders/{binder_id}/audit/summary', response_model=AuditSummaryResponse)
async def get_audit_summary(binder_id: str, store: BinderStore=Depends(get_binder_store)) -> AuditSummaryResponse:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    entries = await store.get_audit_log(binder_id=binder_id, limit=100000)
    by_persona: dict[str, int] = {}
    by_phase: dict[int, int] = {}
    by_operation: dict[str, int] = {}
    for entry in entries:
        by_persona[entry.persona_name] = by_persona.get(entry.persona_name, 0) + 1
        if entry.phase_number is not None:
            by_phase[entry.phase_number] = by_phase.get(entry.phase_number, 0) + 1
        by_operation[entry.operation_type] = by_operation.get(entry.operation_type, 0) + 1
    return AuditSummaryResponse(total_entries=len(entries), by_persona=by_persona, by_phase={str(k): v for k, v in sorted(by_phase.items())}, by_operation=by_operation)

@router.get('/binders/{binder_id}/artifacts/{artifact_id}/audit', response_model=list[AuditLogEntryResponse])
async def get_artifact_audit_trail(binder_id: str, artifact_id: str, store: BinderStore=Depends(get_binder_store)) -> list[AuditLogEntryResponse]:
    binder = await store.load_binder(binder_id)
    if not binder:
        raise HTTPException(status_code=404, detail=f'Binder not found: {binder_id}')
    entries = await store.get_audit_log(binder_id=binder_id, limit=10000)
    artifact_entries = [e for e in entries if e.artifact_id == artifact_id]
    return [AuditLogEntryResponse(id=e.id, persona_name=e.persona_name, phase_number=e.phase_number, timestamp=e.timestamp, access_sequence=e.access_sequence, operation_type=e.operation_type, artifact_type=e.artifact_type, artifact_id=e.artifact_id, method_name=e.method_name, result_count=e.result_count, success=e.success) for e in artifact_entries]

def _artifact_to_response(artifact: Any) -> ArtifactResponse:
    content = artifact.model_dump(exclude={'id', 'artifact_type', 'created_by', 'created_at', 'updated_at', 'phase', 'function_name', 'priority', 'tags', 'is_deleted', 'deleted_by', 'deleted_reason'}, mode='json')
    return ArtifactResponse(id=artifact.id, artifact_type=artifact.artifact_type.value if hasattr(artifact.artifact_type, 'value') else str(artifact.artifact_type), created_by=artifact.created_by, created_at=artifact.created_at, updated_at=artifact.updated_at, phase=artifact.phase, function_name=artifact.function_name, priority=artifact.priority.value if hasattr(artifact.priority, 'value') else str(artifact.priority), tags=artifact.tags, is_deleted=artifact.is_deleted, content=content)