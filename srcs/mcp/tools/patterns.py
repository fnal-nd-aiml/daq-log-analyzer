"""
File: patterns.py
Purpose: Learned error patterns and matching.
Category: Utility
Author: artdaq team
Depends: knowledge, llm, models, workbinder
Exports: register
Complexity: Medium | Lines: 131
"""

from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING
from mcp.server.fastmcp import FastMCP
from srcs.workbinder import BinderStore
from ..context import _json_default, get_db_path
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def list_patterns(active_only: bool=True, min_confidence: float | None=None, min_times_seen: int | None=None, limit: int=50, offset: int=0) -> str:
        store = BinderStore(get_db_path())
        patterns, total = await store.list_patterns(active_only=active_only, min_confidence=min_confidence, min_times_seen=min_times_seen, limit=limit, offset=offset)
        return json.dumps({'patterns': patterns, 'total': total, 'limit': limit, 'offset': offset}, default=_json_default, indent=2)

    @mcp.tool()
    async def get_pattern(pattern_id: str) -> str:
        store = BinderStore(get_db_path())
        pattern = await store.get_pattern(pattern_id)
        if not pattern:
            return json.dumps({'error': f'Pattern not found: {pattern_id}'})
        return json.dumps(pattern, default=_json_default, indent=2)

    @mcp.tool()
    async def get_pattern_statistics() -> str:
        store = BinderStore(get_db_path())
        stats = await store.get_pattern_statistics()
        return json.dumps(stats, default=_json_default, indent=2)

    @mcp.tool()
    async def get_pattern_root_causes(pattern_id: str) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            root_causes = await kb.sqlite.get_pattern_root_causes(pattern_id)
            return json.dumps([{'id': rc.id, 'error_pattern_id': rc.error_pattern_id, 'description': rc.description, 'frequency': rc.frequency} for rc in root_causes], default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get pattern root causes')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def match_pattern(message_pattern: str, function: str | None=None, level: str='ERROR', component: str | None=None) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        from srcs.models import ErrorSignature
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            signature = ErrorSignature(function=function, message_pattern=message_pattern, level=level, component=component)
            match = await kb.find_pattern(signature)
            if not match:
                return json.dumps({'matched': False, 'pattern': None, 'confidence': 0.0, 'matched_fields': [], 'root_causes': []}, indent=2)
            root_causes = await kb.sqlite.get_pattern_root_causes(match.pattern.id)
            return json.dumps({'matched': True, 'pattern': {'id': match.pattern.id, 'name': match.pattern.name, 'description': match.pattern.description, 'signature_function': match.pattern.signature_function, 'signature_message_pattern': match.pattern.signature_message_pattern, 'signature_level': match.pattern.signature_level, 'times_seen': match.pattern.times_seen, 'times_correct': match.pattern.times_correct, 'times_incorrect': match.pattern.times_incorrect, 'pattern_confidence': match.pattern.pattern_confidence, 'is_active': match.pattern.is_active}, 'confidence': match.confidence, 'matched_fields': match.matched_fields, 'root_causes': [{'id': rc.id, 'error_pattern_id': rc.error_pattern_id, 'description': rc.description, 'frequency': rc.frequency} for rc in root_causes]}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to match pattern')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_pattern_accuracy_trend(pattern_id: str, limit: int=30) -> str:
        import aiosqlite
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            pattern = await kb.sqlite.get_pattern_by_id(pattern_id)
            if not pattern:
                return json.dumps({'error': f'Pattern not found: {pattern_id}'})
            times_seen = pattern.times_seen or 0
            times_correct = pattern.times_correct or 0
            current_accuracy = times_correct / times_seen if times_seen > 0 else 0.0
            async with aiosqlite.connect(kb.config.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute('''
                    SELECT
                        date(f.submitted_at) as feedback_date,
                        SUM(CASE WHEN f.was_correct = 1 THEN 1 ELSE 0 END)
                            as correct,
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
                trend.append({'timestamp': row['feedback_date'], 'accuracy': accuracy, 'sample_count': running_total})
            trend_direction = 'stable'
            if len(trend) >= 3:
                third = len(trend) // 3
                early_acc = sum((t['accuracy'] for t in trend[:third])) / third
                late_acc = sum((t['accuracy'] for t in trend[-third:])) / third
                diff = late_acc - early_acc
                if diff > 0.05:
                    trend_direction = 'improving'
                elif diff < -0.05:
                    trend_direction = 'declining'
            return json.dumps({'pattern_id': pattern_id, 'pattern_name': pattern.name, 'current_accuracy': current_accuracy, 'current_sample_count': times_seen, 'trend': trend, 'trend_direction': trend_direction}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get pattern accuracy trend')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def deactivate_pattern(pattern_id: str) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            deactivated = await kb.sqlite.deactivate_pattern(pattern_id)
            if not deactivated:
                return json.dumps({'error': f'Pattern not found: {pattern_id}'})
            return json.dumps({'message': f'Pattern {pattern_id} deactivated'})
        except Exception as e:
            logger.exception('Failed to deactivate pattern')
            return json.dumps({'error': str(e)}, indent=2)