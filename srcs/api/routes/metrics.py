"""
File: metrics.py
Purpose: Metrics and analytics endpoints.
Category: Utility
Author: artdaq team
Depends: learning, row_mappers, pydantic
Exports: TimePeriod, QueryEffectivenessStats, QueryEffectivenessResponse, StrategyStats, QualityMetrics, ...
Complexity: High | Lines: 167
"""

from datetime import datetime, timedelta
from enum import Enum
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from srcs.knowledge.learning import MetaLearner
from srcs.knowledge.row_mappers import scalar_column
from ..dependencies import StorageConfig, get_storage_config
router = APIRouter()

class TimePeriod(str, Enum):
    DAY = 'day'
    WEEK = 'week'
    MONTH = 'month'

class QueryEffectivenessStats(BaseModel):
    query_type: str
    times_used: int
    times_useful: int
    usefulness_rate: float
    avg_evidence_strength: float
    avg_result_count: float

class QueryEffectivenessResponse(BaseModel):
    query_types: list[QueryEffectivenessStats]
    total_queries: int
    overall_usefulness_rate: float

class StrategyStats(BaseModel):
    strategy: str
    times_used: int
    times_correct: int
    success_rate: float
    avg_confidence: float
    avg_rank: float

class QualityMetrics(BaseModel):
    period: str
    start_date: datetime
    end_date: datetime
    total_investigations: int
    successful_investigations: int
    success_rate: float
    avg_confidence: float
    feedback_count: int
    accuracy_from_feedback: float | None
    top_strategies: list[StrategyStats]
    top_query_types: list[QueryEffectivenessStats]

class StrategyWeightsResponse(BaseModel):
    weights: dict[str, float]
    error_type: str | None

class QueryPriorityResponse(BaseModel):
    priority: list[str]
    error_type: str | None

class MetaLearningStats(BaseModel):
    total_strategies: int
    total_strategy_samples: int
    avg_strategy_success_rate: float
    total_query_types: int
    total_query_samples: int
    avg_query_usefulness_rate: float

class StrategyRecommendationsResponse(BaseModel):
    weights: dict[str, float]
    query_priority: list[str]
    top_strategies: list[StrategyStats]
    stats: MetaLearningStats
    error_type: str | None

@router.get('/strategies/weights', response_model=StrategyWeightsResponse)
async def get_strategy_weights(error_type: str | None=None, storage_config: StorageConfig=Depends(get_storage_config)) -> StrategyWeightsResponse:
    try:
        meta_learner = MetaLearner(storage_config.sqlite_path)
        weights = await meta_learner.suggest_strategy_weights(error_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get strategy weights: {str(e)}')
    return StrategyWeightsResponse(weights=weights, error_type=error_type)

@router.get('/strategies/query-priority', response_model=QueryPriorityResponse)
async def get_query_priority(error_type: str | None=None, storage_config: StorageConfig=Depends(get_storage_config)) -> QueryPriorityResponse:
    try:
        meta_learner = MetaLearner(storage_config.sqlite_path)
        priority = await meta_learner.suggest_query_priority(error_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get query priority: {str(e)}')
    return QueryPriorityResponse(priority=priority, error_type=error_type)

@router.get('/strategies/recommendations', response_model=StrategyRecommendationsResponse)
async def get_strategy_recommendations(error_type: str | None=None, storage_config: StorageConfig=Depends(get_storage_config)) -> StrategyRecommendationsResponse:
    try:
        meta_learner = MetaLearner(storage_config.sqlite_path)
        weights = await meta_learner.suggest_strategy_weights(error_type)
        priority = await meta_learner.suggest_query_priority(error_type)
        strategies = await meta_learner.get_best_strategies(error_type, min_samples=3)
        raw_stats = await meta_learner.get_meta_learning_statistics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get strategy recommendations: {str(e)}')
    top_strategies = [StrategyStats(strategy=s['strategy'], times_used=s['times_used'], times_correct=int(s['success_rate'] * s['times_used']), success_rate=s['success_rate'], avg_confidence=s['avg_confidence'], avg_rank=s['avg_rank']) for s in strategies[:10]]
    stats = MetaLearningStats(total_strategies=raw_stats.get('total_strategies', 0), total_strategy_samples=raw_stats.get('total_strategy_samples', 0), avg_strategy_success_rate=raw_stats.get('avg_strategy_success_rate', 0.0), total_query_types=raw_stats.get('total_query_types', 0), total_query_samples=raw_stats.get('total_query_samples', 0), avg_query_usefulness_rate=raw_stats.get('avg_query_usefulness_rate', 0.0))
    return StrategyRecommendationsResponse(weights=weights, query_priority=priority, top_strategies=top_strategies, stats=stats, error_type=error_type)

@router.get('/queries/effectiveness', response_model=QueryEffectivenessResponse)
async def get_query_effectiveness(error_type: str | None=None, min_samples: int=5, storage_config: StorageConfig=Depends(get_storage_config)) -> QueryEffectivenessResponse:
    try:
        meta_learner = MetaLearner(storage_config.sqlite_path)
        query_types = await meta_learner.get_best_query_types(error_type, min_samples)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get query effectiveness: {str(e)}')
    if not query_types:
        return QueryEffectivenessResponse(query_types=[], total_queries=0, overall_usefulness_rate=0.0)
    stats = [QueryEffectivenessStats(query_type=q['query_type'], times_used=q['times_used'], times_useful=int(q['usefulness_rate'] * q['times_used']), usefulness_rate=q['usefulness_rate'], avg_evidence_strength=q['avg_evidence_strength'], avg_result_count=q['avg_result_count']) for q in query_types]
    total_queries = sum((s.times_used for s in stats))
    total_useful = sum((s.times_useful for s in stats))
    overall_rate = total_useful / total_queries if total_queries > 0 else 0.0
    return QueryEffectivenessResponse(query_types=stats, total_queries=total_queries, overall_usefulness_rate=overall_rate)

@router.get('/metrics/{period}', response_model=QualityMetrics)
async def get_quality_metrics(period: TimePeriod, storage_config: StorageConfig=Depends(get_storage_config)) -> QualityMetrics:
    end_date = datetime.now()
    if period == TimePeriod.DAY:
        start_date = end_date - timedelta(days=1)
    elif period == TimePeriod.WEEK:
        start_date = end_date - timedelta(weeks=1)
    else:
        start_date = end_date - timedelta(days=30)
    try:
        async with aiosqlite.connect(storage_config.sqlite_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome IN ('CONFIDENT', 'PROBABLE') THEN 1 ELSE 0 END) as successful,
                    AVG(CASE
                        WHEN hypotheses_json IS NOT NULL
                        THEN json_extract(hypotheses_json, '$[0].score')
                        ELSE NULL
                    END) as avg_confidence
                FROM investigations
                WHERE timestamp >= ?
                """, (start_date.isoformat(),)) as cursor:
                inv_row = await cursor.fetchone()
            total_investigations = scalar_column(inv_row, 'total')
            successful_investigations = scalar_column(inv_row, 'successful')
            avg_confidence = scalar_column(inv_row, 'avg_confidence', default=0.0)
            async with conn.execute('''
                SELECT
                    COUNT(*) as feedback_count,
                    SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as correct_count
                FROM investigation_feedback
                WHERE submitted_at >= ?
                ''', (start_date.isoformat(),)) as cursor:
                fb_row = await cursor.fetchone()
            feedback_count = scalar_column(fb_row, 'feedback_count')
            correct_count = scalar_column(fb_row, 'correct_count')
            accuracy_from_feedback = correct_count / feedback_count if feedback_count > 0 else None
        meta_learner = MetaLearner(storage_config.sqlite_path)
        strategies = await meta_learner.get_best_strategies(min_samples=3)
        query_types = await meta_learner.get_best_query_types(min_samples=3)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get metrics: {str(e)}')
    success_rate = successful_investigations / total_investigations if total_investigations > 0 else 0.0
    top_strategies = [StrategyStats(strategy=s['strategy'], times_used=s['times_used'], times_correct=int(s['success_rate'] * s['times_used']), success_rate=s['success_rate'], avg_confidence=s['avg_confidence'], avg_rank=s['avg_rank']) for s in strategies[:5]]
    top_query_types = [QueryEffectivenessStats(query_type=q['query_type'], times_used=q['times_used'], times_useful=int(q['usefulness_rate'] * q['times_used']), usefulness_rate=q['usefulness_rate'], avg_evidence_strength=q['avg_evidence_strength'], avg_result_count=q['avg_result_count']) for q in query_types[:5]]
    return QualityMetrics(period=period.value, start_date=start_date, end_date=end_date, total_investigations=total_investigations, successful_investigations=successful_investigations, success_rate=success_rate, avg_confidence=avg_confidence, feedback_count=feedback_count, accuracy_from_feedback=accuracy_from_feedback, top_strategies=top_strategies, top_query_types=top_query_types)