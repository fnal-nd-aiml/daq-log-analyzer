"""
File: meta_learner.py
Purpose: Meta-learning for strategy and query optimization.
Category: Utility
Author: artdaq team
Depends: models
Exports: MetaLearner
Complexity: Medium | Lines: 190
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
import aiosqlite
from srcs.models import Investigation
from .row_mappers import scalar
if TYPE_CHECKING:
    from .store_interface import StructuredStore
logger = logging.getLogger(__name__)

class MetaLearner:

    def __init__(self, db_path: str | None=None, store: 'StructuredStore | None'=None):
        self._store = store
        self.db_path = db_path or './data/knowledge.db'

    @classmethod
    def from_store(cls, store: 'StructuredStore') -> 'MetaLearner':
        return cls(db_path=None, store=store)

    async def record_hypothesis_outcome(self, investigation_id: str, hypothesis_source: str, was_correct: bool, confidence: float, rank: int, error_type: str | None=None) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute('''
                SELECT id, times_used, times_correct, avg_confidence, avg_rank
                FROM hypothesis_strategy_performance
                WHERE strategy_name = ?
                AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                ''', (hypothesis_source, error_type, error_type)) as cursor:
                row = await cursor.fetchone()
            if row:
                new_times_used = row[1] + 1
                new_times_correct = row[2] + (1 if was_correct else 0)
                new_avg_confidence = (row[3] * row[1] + confidence) / new_times_used
                new_avg_rank = (row[4] * row[1] + rank) / new_times_used
                await conn.execute('''
                    UPDATE hypothesis_strategy_performance
                    SET times_used = ?, times_correct = ?, avg_confidence = ?,
                        avg_rank = ?, last_used = ?
                    WHERE id = ?
                    ''', (new_times_used, new_times_correct, new_avg_confidence, new_avg_rank, datetime.now().isoformat(), row[0]))
            else:
                from srcs.models import generate_id
                await conn.execute('''
                    INSERT INTO hypothesis_strategy_performance (
                        id, strategy_name, error_type, times_used, times_correct,
                        avg_confidence, avg_rank, last_used
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                    ''', (generate_id(), hypothesis_source, error_type, 1 if was_correct else 0, confidence, float(rank), datetime.now().isoformat()))
            await conn.commit()

    async def record_query_outcome(self, query_type: str, was_useful: bool, evidence_strength: float, result_count: int, error_type: str | None=None) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute('''
                SELECT id, times_used, times_useful, avg_evidence_strength, avg_result_count
                FROM query_type_effectiveness
                WHERE query_type = ?
                AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                ''', (query_type, error_type, error_type)) as cursor:
                row = await cursor.fetchone()
            if row:
                new_times_used = row[1] + 1
                new_times_useful = row[2] + (1 if was_useful else 0)
                new_avg_strength = (row[3] * row[1] + evidence_strength) / new_times_used
                new_avg_count = (row[4] * row[1] + result_count) / new_times_used
                await conn.execute('''
                    UPDATE query_type_effectiveness
                    SET times_used = ?, times_useful = ?, avg_evidence_strength = ?,
                        avg_result_count = ?, last_used = ?
                    WHERE id = ?
                    ''', (new_times_used, new_times_useful, new_avg_strength, new_avg_count, datetime.now().isoformat(), row[0]))
            else:
                from srcs.models import generate_id
                await conn.execute('''
                    INSERT INTO query_type_effectiveness (
                        id, query_type, error_type, times_used, times_useful,
                        avg_evidence_strength, avg_result_count, last_used
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                    ''', (generate_id(), query_type, error_type, 1 if was_useful else 0, evidence_strength, float(result_count), datetime.now().isoformat()))
            await conn.commit()

    async def get_best_strategies(self, error_type: str | None=None, min_samples: int=5) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = '''
                    SELECT strategy_name, times_used, times_correct, avg_confidence, avg_rank
                    FROM hypothesis_strategy_performance
                    WHERE (error_type = ? OR error_type IS NULL)
                    AND times_used >= ?
                    ORDER BY CAST(times_correct AS REAL) / times_used DESC
                '''
                params: tuple[Any, ...] = (error_type, min_samples)
            else:
                query = '''
                    SELECT strategy_name, times_used, times_correct, avg_confidence, avg_rank
                    FROM hypothesis_strategy_performance
                    WHERE times_used >= ?
                    ORDER BY CAST(times_correct AS REAL) / times_used DESC
                '''
                params = (min_samples,)
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            return [{'strategy': row['strategy_name'], 'success_rate': row['times_correct'] / row['times_used'], 'times_used': row['times_used'], 'avg_confidence': row['avg_confidence'], 'avg_rank': row['avg_rank']} for row in rows]

    async def get_best_query_types(self, error_type: str | None=None, min_samples: int=5) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = '''
                    SELECT query_type, times_used, times_useful,
                           avg_evidence_strength, avg_result_count
                    FROM query_type_effectiveness
                    WHERE (error_type = ? OR error_type IS NULL)
                    AND times_used >= ?
                    ORDER BY CAST(times_useful AS REAL) / times_used DESC
                '''
                params: tuple[Any, ...] = (error_type, min_samples)
            else:
                query = '''
                    SELECT query_type, times_used, times_useful,
                           avg_evidence_strength, avg_result_count
                    FROM query_type_effectiveness
                    WHERE times_used >= ?
                    ORDER BY CAST(times_useful AS REAL) / times_used DESC
                '''
                params = (min_samples,)
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            return [{'query_type': row['query_type'], 'usefulness_rate': row['times_useful'] / row['times_used'], 'times_used': row['times_used'], 'avg_evidence_strength': row['avg_evidence_strength'], 'avg_result_count': row['avg_result_count']} for row in rows]

    async def suggest_strategy_weights(self, error_type: str | None=None) -> dict[str, float]:
        strategies = await self.get_best_strategies(error_type, min_samples=3)
        if not strategies:
            return {}
        weights = {}
        total_rate = sum((s['success_rate'] for s in strategies))
        if total_rate == 0:
            return {}
        for strategy in strategies:
            weight = strategy['success_rate'] / total_rate
            weight = max(0.1, weight)
            weights[strategy['strategy']] = weight
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}

    async def suggest_query_priority(self, error_type: str | None=None) -> list[str]:
        queries = await self.get_best_query_types(error_type, min_samples=3)
        if not queries:
            return []
        return [q['query_type'] for q in queries]

    async def learn_from_investigation(self, investigation: Investigation, was_correct: bool) -> dict[str, Any]:
        results: dict[str, Any] = {'strategies_recorded': 0, 'queries_recorded': 0}
        error_type = None
        if investigation.trigger_error.component:
            error_type = investigation.trigger_error.component
        for rank, hypothesis in enumerate(investigation.hypotheses):
            hyp_correct = was_correct and rank == 0
            if hypothesis.source:
                await self.record_hypothesis_outcome(investigation_id=investigation.id, hypothesis_source=hypothesis.source, was_correct=hyp_correct, confidence=hypothesis.score, rank=rank, error_type=error_type)
                results['strategies_recorded'] += 1
        evidence_by_source: dict[str, list] = {}
        for item in investigation.evidence.items.values():
            source_type = item.source.split(':')[0] if ':' in item.source else item.source
            if source_type not in evidence_by_source:
                evidence_by_source[source_type] = []
            evidence_by_source[source_type].append(item)
        strength_map = {'STRONG': 1.0, 'MODERATE': 0.5, 'WEAK': 0.25}
        for query_type, items in evidence_by_source.items():
            avg_strength = sum((strength_map.get(i.strength, 0.25) for i in items)) / len(items)
            was_useful = avg_strength > 0.4 or any((i.strength == 'STRONG' for i in items))
            await self.record_query_outcome(query_type=query_type, was_useful=was_useful, evidence_strength=avg_strength, result_count=len(items), error_type=error_type)
            results['queries_recorded'] += 1
        return results

    async def get_meta_learning_statistics(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as conn:
            stats: dict[str, Any] = {}
            async with conn.execute('SELECT COUNT(*), SUM(times_used), AVG(CAST(times_correct AS REAL) / times_used) FROM hypothesis_strategy_performance WHERE times_used > 0') as cursor:
                row = await cursor.fetchone()
                stats['total_strategies'] = scalar(row, 0)
                stats['total_strategy_samples'] = scalar(row, 1)
                stats['avg_strategy_success_rate'] = scalar(row, 2, default=0.0)
            async with conn.execute('SELECT COUNT(*), SUM(times_used), AVG(CAST(times_useful AS REAL) / times_used) FROM query_type_effectiveness WHERE times_used > 0') as cursor:
                row = await cursor.fetchone()
                stats['total_query_types'] = scalar(row, 0)
                stats['total_query_samples'] = scalar(row, 1)
                stats['avg_query_usefulness_rate'] = scalar(row, 2, default=0.0)
            return stats