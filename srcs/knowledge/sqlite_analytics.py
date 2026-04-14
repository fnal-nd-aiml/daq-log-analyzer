"""
File: sqlite_analytics.py
Purpose: SQLite analytics and meta-learning operations.
Category: Utility
Author: artdaq team
Depends: models
Exports: SQLiteAnalyticsMixin
Complexity: Medium | Lines: 264
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
import aiosqlite

if TYPE_CHECKING:
    from pathlib import Path


class SQLiteAnalyticsMixin:
    db_path: "Path"

    async def _ensure_initialized(self) -> None:
        raise NotImplementedError

    async def update_strategy_performance(
        self, strategy_name: str, was_correct: bool, confidence: float, rank: int, error_type: str | None = None
    ) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """
                SELECT * FROM hypothesis_strategy_performance
                WHERE strategy_name = ? AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                """,
                (strategy_name, error_type, error_type),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                new_times_used = row[3] + 1
                new_times_correct = row[4] + (1 if was_correct else 0)
                new_avg_confidence = (row[5] * row[3] + confidence) / new_times_used
                new_avg_rank = (row[6] * row[3] + rank) / new_times_used
                await conn.execute(
                    """
                    UPDATE hypothesis_strategy_performance
                    SET times_used = ?, times_correct = ?, avg_confidence = ?,
                        avg_rank = ?, last_used = ?
                    WHERE strategy_name = ? AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                    """,
                    (
                        new_times_used,
                        new_times_correct,
                        new_avg_confidence,
                        new_avg_rank,
                        datetime.now().isoformat(),
                        strategy_name,
                        error_type,
                        error_type,
                    ),
                )
            else:
                from srcs.models import generate_id

                await conn.execute(
                    """
                    INSERT INTO hypothesis_strategy_performance (
                        id, strategy_name, error_type, times_used, times_correct,
                        avg_confidence, avg_rank, last_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        generate_id(),
                        strategy_name,
                        error_type,
                        1,
                        1 if was_correct else 0,
                        confidence,
                        float(rank),
                        datetime.now().isoformat(),
                    ),
                )
            await conn.commit()

    async def update_query_effectiveness(
        self,
        query_type: str,
        was_useful: bool,
        evidence_strength: float,
        result_count: int,
        error_type: str | None = None,
    ) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """
                SELECT * FROM query_type_effectiveness
                WHERE query_type = ? AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                """,
                (query_type, error_type, error_type),
            ) as cursor:
                row = await cursor.fetchone()
            if row:
                new_times_used = row[3] + 1
                new_times_useful = row[4] + (1 if was_useful else 0)
                new_avg_strength = (row[5] * row[3] + evidence_strength) / new_times_used
                new_avg_count = (row[6] * row[3] + result_count) / new_times_used
                await conn.execute(
                    """
                    UPDATE query_type_effectiveness
                    SET times_used = ?, times_useful = ?, avg_evidence_strength = ?,
                        avg_result_count = ?, last_used = ?
                    WHERE query_type = ? AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                    """,
                    (
                        new_times_used,
                        new_times_useful,
                        new_avg_strength,
                        new_avg_count,
                        datetime.now().isoformat(),
                        query_type,
                        error_type,
                        error_type,
                    ),
                )
            else:
                from srcs.models import generate_id

                await conn.execute(
                    """
                    INSERT INTO query_type_effectiveness (
                        id, query_type, error_type, times_used, times_useful,
                        avg_evidence_strength, avg_result_count, last_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        generate_id(),
                        query_type,
                        error_type,
                        1,
                        1 if was_useful else 0,
                        evidence_strength,
                        float(result_count),
                        datetime.now().isoformat(),
                    ),
                )
            await conn.commit()

    async def get_strategy_performance(self, error_type: str | None = None) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = """
                    SELECT * FROM hypothesis_strategy_performance
                    WHERE error_type = ?
                    ORDER BY times_correct DESC
                """
                params: tuple[str, ...] = (error_type,)
            else:
                query = """
                    SELECT * FROM hypothesis_strategy_performance
                    ORDER BY times_correct DESC
                """
                params = ()
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "strategy_name": row["strategy_name"],
                        "error_type": row["error_type"],
                        "times_used": row["times_used"],
                        "times_correct": row["times_correct"],
                        "accuracy": row["times_correct"] / row["times_used"] if row["times_used"] > 0 else 0,
                        "avg_confidence": row["avg_confidence"],
                        "avg_rank": row["avg_rank"],
                        "last_used": row["last_used"],
                    }
                    for row in rows
                ]

    async def get_query_effectiveness(self, error_type: str | None = None) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = """
                    SELECT * FROM query_type_effectiveness
                    WHERE error_type = ?
                    ORDER BY times_useful DESC
                """
                params: tuple[str, ...] = (error_type,)
            else:
                query = """
                    SELECT * FROM query_type_effectiveness
                    ORDER BY times_useful DESC
                """
                params = ()
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "query_type": row["query_type"],
                        "error_type": row["error_type"],
                        "times_used": row["times_used"],
                        "times_useful": row["times_useful"],
                        "usefulness_rate": row["times_useful"] / row["times_used"] if row["times_used"] > 0 else 0,
                        "avg_evidence_strength": row["avg_evidence_strength"],
                        "avg_result_count": row["avg_result_count"],
                        "last_used": row["last_used"],
                    }
                    for row in rows
                ]

    async def get_hypothesis_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            stats: dict[str, Any] = {}
            async with conn.execute("SELECT COUNT(*) FROM hypotheses") as cursor:
                row = await cursor.fetchone()
                stats["total_hypotheses"] = row[0] if row else 0
            async with conn.execute(
                """
                SELECT AVG(cnt) FROM (
                    SELECT COUNT(*) as cnt FROM hypotheses GROUP BY investigation_id
                )
                """
            ) as cursor:
                row = await cursor.fetchone()
                stats["avg_hypotheses_per_investigation"] = (row[0] if row else None) or 0
            async with conn.execute(
                """
                SELECT source, COUNT(*) as cnt
                FROM hypotheses
                WHERE source IS NOT NULL
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 10
                """
            ) as cursor:
                rows = await cursor.fetchall()
                stats["hypothesis_sources"] = {row[0]: row[1] for row in rows}
            async with conn.execute("SELECT AVG(score) FROM hypotheses WHERE rank = 0") as cursor:
                row = await cursor.fetchone()
                stats["avg_winning_score"] = (row[0] if row else None) or 0
            return stats

    async def get_evidence_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            stats: dict[str, Any] = {}
            async with conn.execute("SELECT COUNT(*) FROM evidence_items") as cursor:
                row = await cursor.fetchone()
                stats["total_evidence_items"] = row[0] if row else 0
            async with conn.execute(
                """
                SELECT evidence_type, COUNT(*) as cnt
                FROM evidence_items
                GROUP BY evidence_type
                ORDER BY cnt DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                stats["evidence_by_type"] = {row[0]: row[1] for row in rows}
            async with conn.execute(
                """
                SELECT strength, COUNT(*) as cnt
                FROM evidence_items
                GROUP BY strength
                ORDER BY cnt DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                stats["evidence_by_strength"] = {row[0]: row[1] for row in rows}
            return stats
