"""
File: patterns.py
Purpose: Pattern management endpoints.
Category: Utility
Author: artdaq team
Depends: knowledge, models, pydantic
Exports: PatternResponse, PatternListResponse, RootCauseResponse, PatternMatchRequest, PatternMatchResponse, ...
Complexity: High | Lines: 173
"""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from srcs.knowledge import KnowledgeBase, PatternLearner
from srcs.models import ErrorSignature
from ..dependencies import get_knowledge_base, get_pattern_learner
router = APIRouter()

class PatternResponse(BaseModel):
    id: str
    name: str
    description: str | None
    signature_function: str | None
    signature_message_pattern: str | None
    signature_level: str
    times_seen: int
    times_correct: int
    times_incorrect: int
    pattern_confidence: float
    is_active: bool

class PatternListResponse(BaseModel):
    patterns: list[PatternResponse]
    total: int

class RootCauseResponse(BaseModel):
    id: str
    error_pattern_id: str
    description: str
    frequency: float

class PatternMatchRequest(BaseModel):
    function: str | None = None
    message_pattern: str = Field(..., description='Error message pattern')
    level: str = Field(default='ERROR')
    component: str | None = None

class PatternMatchResponse(BaseModel):
    matched: bool
    pattern: PatternResponse | None = None
    confidence: float
    matched_fields: list[str]
    root_causes: list[RootCauseResponse]

class PatternStatsResponse(BaseModel):
    total_patterns: int
    active_patterns: int
    average_confidence: float
    high_accuracy_patterns: int
    low_accuracy_patterns: int
    root_cause_patterns: int

@router.get('/patterns', response_model=PatternListResponse)
async def list_patterns(active_only: bool=Query(default=True, description='Only return active patterns'), limit: int=Query(default=50, ge=1, le=1000, description='Maximum patterns to return'), offset: int=Query(default=0, ge=0, description='Number of patterns to skip'), kb: KnowledgeBase=Depends(get_knowledge_base)) -> PatternListResponse:
    try:
        patterns_list, total = await kb.sqlite.list_patterns(active_only=active_only, limit=limit, offset=offset)
        patterns = [PatternResponse(id=p.id, name=p.name, description=p.description, signature_function=p.signature_function, signature_message_pattern=p.signature_message_pattern, signature_level=p.signature_level, times_seen=p.times_seen, times_correct=p.times_correct, times_incorrect=p.times_incorrect, pattern_confidence=p.pattern_confidence, is_active=p.is_active) for p in patterns_list]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to list patterns: {str(e)}')
    return PatternListResponse(patterns=patterns, total=total)

@router.post('/patterns/match', response_model=PatternMatchResponse)
async def match_pattern(request: PatternMatchRequest, kb: KnowledgeBase=Depends(get_knowledge_base)) -> PatternMatchResponse:
    signature = ErrorSignature(function=request.function, message_pattern=request.message_pattern, level=request.level, component=request.component)
    try:
        match = await kb.find_pattern(signature)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Pattern matching failed: {str(e)}')
    if not match:
        return PatternMatchResponse(matched=False, pattern=None, confidence=0.0, matched_fields=[], root_causes=[])
    root_causes = await kb.sqlite.get_pattern_root_causes(match.pattern.id)
    return PatternMatchResponse(matched=True, pattern=PatternResponse(id=match.pattern.id, name=match.pattern.name, description=match.pattern.description, signature_function=match.pattern.signature_function, signature_message_pattern=match.pattern.signature_message_pattern, signature_level=match.pattern.signature_level, times_seen=match.pattern.times_seen, times_correct=match.pattern.times_correct, times_incorrect=match.pattern.times_incorrect, pattern_confidence=match.pattern.pattern_confidence, is_active=match.pattern.is_active), confidence=match.confidence, matched_fields=match.matched_fields, root_causes=[RootCauseResponse(id=rc.id, error_pattern_id=rc.error_pattern_id, description=rc.description, frequency=rc.frequency) for rc in root_causes])

@router.get('/patterns/stats', response_model=PatternStatsResponse)
async def get_pattern_statistics(learner: Annotated[PatternLearner, Depends(get_pattern_learner)]) -> PatternStatsResponse:
    try:
        stats = await learner.get_pattern_statistics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get stats: {str(e)}')
    return PatternStatsResponse(total_patterns=stats.get('total_patterns', 0), active_patterns=stats.get('active_patterns', 0), average_confidence=stats.get('average_confidence', 0.0), high_accuracy_patterns=stats.get('high_accuracy_patterns', 0), low_accuracy_patterns=stats.get('low_accuracy_patterns', 0), root_cause_patterns=stats.get('root_cause_patterns', 0))

@router.get('/patterns/{pattern_id}', response_model=PatternResponse)
async def get_pattern(pattern_id: str, kb: KnowledgeBase=Depends(get_knowledge_base)) -> PatternResponse:
    try:
        pattern = await kb.sqlite.get_pattern_by_id(pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail='Pattern not found')
        return PatternResponse(id=pattern.id, name=pattern.name, description=pattern.description, signature_function=pattern.signature_function, signature_message_pattern=pattern.signature_message_pattern, signature_level=pattern.signature_level, times_seen=pattern.times_seen, times_correct=pattern.times_correct, times_incorrect=pattern.times_incorrect, pattern_confidence=pattern.pattern_confidence, is_active=pattern.is_active)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get pattern: {str(e)}')

@router.get('/patterns/{pattern_id}/root-causes', response_model=list[RootCauseResponse])
async def get_pattern_root_causes(pattern_id: str, kb: KnowledgeBase=Depends(get_knowledge_base)) -> list[RootCauseResponse]:
    try:
        root_causes = await kb.sqlite.get_pattern_root_causes(pattern_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get root causes: {str(e)}')
    return [RootCauseResponse(id=rc.id, error_pattern_id=rc.error_pattern_id, description=rc.description, frequency=rc.frequency) for rc in root_causes]

class AccuracyDataPoint(BaseModel):
    timestamp: str
    accuracy: float
    sample_count: int

class PatternAccuracyTrendResponse(BaseModel):
    pattern_id: str
    pattern_name: str
    current_accuracy: float
    current_sample_count: int
    trend: list[AccuracyDataPoint]
    trend_direction: str

@router.get('/patterns/{pattern_id}/accuracy-trend', response_model=PatternAccuracyTrendResponse)
async def get_pattern_accuracy_trend(pattern_id: str, limit: int=Query(default=30, ge=1, le=365, description='Maximum data points to return'), kb: KnowledgeBase=Depends(get_knowledge_base)) -> PatternAccuracyTrendResponse:
    import aiosqlite
    try:
        pattern = await kb.sqlite.get_pattern_by_id(pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail='Pattern not found')
        times_seen = pattern.times_seen or 0
        times_correct = pattern.times_correct or 0
        current_accuracy = times_correct / times_seen if times_seen > 0 else 0.0
        async with aiosqlite.connect(kb.config.sqlite_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('''
                SELECT
                    date(f.submitted_at) as feedback_date,
                    SUM(CASE WHEN f.was_correct = 1 THEN 1 ELSE 0 END) as correct,
                    COUNT(*) as total
                FROM investigation_feedback f
                JOIN investigations i ON f.investigation_id = i.id
                WHERE i.matched_pattern_id = ?
                GROUP BY date(f.submitted_at)
                ORDER BY feedback_date DESC
                LIMIT ?
                ''', (pattern_id, limit)) as cursor:
                trend_rows = await cursor.fetchall()
            trend = []
            running_correct = 0
            running_total = 0
            for row in reversed(list(trend_rows)):
                running_correct += row['correct']
                running_total += row['total']
                accuracy = running_correct / running_total if running_total > 0 else 0.0
                trend.append(AccuracyDataPoint(timestamp=row['feedback_date'], accuracy=accuracy, sample_count=running_total))
            trend_direction = 'stable'
            if len(trend) >= 3:
                early_accuracy = sum((t.accuracy for t in trend[:len(trend) // 3])) / (len(trend) // 3)
                late_accuracy = sum((t.accuracy for t in trend[-len(trend) // 3:])) / (len(trend) // 3)
                diff = late_accuracy - early_accuracy
                if diff > 0.05:
                    trend_direction = 'improving'
                elif diff < -0.05:
                    trend_direction = 'declining'
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get accuracy trend: {str(e)}')
    return PatternAccuracyTrendResponse(pattern_id=pattern_id, pattern_name=pattern.name, current_accuracy=current_accuracy, current_sample_count=times_seen, trend=trend, trend_direction=trend_direction)

@router.delete('/patterns/{pattern_id}')
async def deactivate_pattern(pattern_id: str, kb: KnowledgeBase=Depends(get_knowledge_base)) -> dict:
    try:
        deactivated = await kb.sqlite.deactivate_pattern(pattern_id)
        if not deactivated:
            raise HTTPException(status_code=404, detail='Pattern not found')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to deactivate pattern: {str(e)}')
    return {'message': f'Pattern {pattern_id} deactivated'}