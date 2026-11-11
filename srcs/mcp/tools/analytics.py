"""
File: analytics.py
Purpose: Quality metrics and meta-learning readouts.
Category: Utility
Author: artdaq team
Depends: config, indexer, summarizer, knowledge, learning, ...
Exports: register
Complexity: Medium | Lines: 183
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from mcp.server.fastmcp import FastMCP
from ..context import _get_agent_client, _json_default, get_client_session_id
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_query_effectiveness(error_type: str | None=None, min_samples: int=5) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner
        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            query_types = await meta_learner.get_best_query_types(error_type, min_samples)
            if not query_types:
                return json.dumps({'query_types': [], 'total_queries': 0, 'overall_usefulness_rate': 0.0}, indent=2)
            stats = [{'query_type': q['query_type'], 'times_used': q['times_used'], 'times_useful': int(q['usefulness_rate'] * q['times_used']), 'usefulness_rate': q['usefulness_rate'], 'avg_evidence_strength': q['avg_evidence_strength'], 'avg_result_count': q['avg_result_count']} for q in query_types]
            total_queries = sum((s['times_used'] for s in stats))
            total_useful = sum((s['times_useful'] for s in stats))
            overall_rate = total_useful / total_queries if total_queries > 0 else 0.0
            return json.dumps({'query_types': stats, 'total_queries': total_queries, 'overall_usefulness_rate': overall_rate}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get query effectiveness')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_quality_metrics(period: str='week') -> str:
        import aiosqlite
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner
        try:
            from datetime import timedelta
            config = StorageConfig()
            end_date = datetime.now()
            if period == 'day':
                start_date = end_date - timedelta(days=1)
            elif period == 'month':
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date - timedelta(weeks=1)
            async with aiosqlite.connect(config.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN outcome IN ('CONFIDENT', 'PROBABLE')
                            THEN 1 ELSE 0 END) as successful,
                        AVG(CASE
                            WHEN hypotheses_json IS NOT NULL
                            THEN json_extract(
                                hypotheses_json, '$[0].score')
                            ELSE NULL
                        END) as avg_confidence
                    FROM investigations
                    WHERE timestamp >= ?
                    """, (start_date.isoformat(),)) as cursor:
                    inv_row = await cursor.fetchone()
                total = inv_row['total'] or 0 if inv_row else 0
                successful = inv_row['successful'] or 0 if inv_row else 0
                avg_confidence = inv_row['avg_confidence'] or 0.0 if inv_row else 0.0
                async with conn.execute('''
                    SELECT
                        COUNT(*) as feedback_count,
                        SUM(CASE WHEN was_correct = 1
                            THEN 1 ELSE 0 END) as correct_count
                    FROM investigation_feedback
                    WHERE submitted_at >= ?
                    ''', (start_date.isoformat(),)) as cursor:
                    fb_row = await cursor.fetchone()
                feedback_count = fb_row['feedback_count'] or 0 if fb_row else 0
                correct_count = fb_row['correct_count'] or 0 if fb_row else 0
                accuracy = correct_count / feedback_count if feedback_count > 0 else None
            meta_learner = MetaLearner(config.sqlite_path)
            strategies = await meta_learner.get_best_strategies(min_samples=3)
            query_types = await meta_learner.get_best_query_types(min_samples=3)
            success_rate = total and successful / total or 0.0
            top_strategies = [{'strategy': s['strategy'], 'times_used': s['times_used'], 'times_correct': int(s['success_rate'] * s['times_used']), 'success_rate': s['success_rate'], 'avg_confidence': s['avg_confidence'], 'avg_rank': s['avg_rank']} for s in strategies[:5]]
            top_query_types = [{'query_type': q['query_type'], 'times_used': q['times_used'], 'times_useful': int(q['usefulness_rate'] * q['times_used']), 'usefulness_rate': q['usefulness_rate'], 'avg_evidence_strength': q['avg_evidence_strength'], 'avg_result_count': q['avg_result_count']} for q in query_types[:5]]
            return json.dumps({'period': period, 'start_date': start_date, 'end_date': end_date, 'total_investigations': total, 'successful_investigations': successful, 'success_rate': success_rate, 'avg_confidence': avg_confidence, 'feedback_count': feedback_count, 'accuracy_from_feedback': accuracy, 'top_strategies': top_strategies, 'top_query_types': top_query_types}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get quality metrics')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def summarize_function(name: str, file_filter: str | None=None) -> str:
        try:
            client = await _get_agent_client()
            session_id = get_client_session_id()
            if client and session_id:
                result = await client.summarize_function(session_id, name, file_filter=file_filter)
                return json.dumps(result, default=_json_default, indent=2)
            from srcs.config import load_config
            from srcs.extraction.indexer import CodeIndex, CodeIndexConfig
            from srcs.extraction.summarizer import FunctionSummarizer
            from srcs.llm import create_llm_provider
            config = load_config()
            source_config = config.source
            source_roots = []
            if source_config and source_config.has_repositories():
                from srcs.source import RepositoryManager
                manager = RepositoryManager(source_config)
                source_roots = manager.get_existing_repo_paths()
            if not source_roots:
                return json.dumps({'error': 'No source repositories available. Run init_knowledge_base with source sync first.'})
            index_path = Path(os.environ.get('ARTDAQ_DATA_DIR', './data')) / 'code_index.db'
            idx_config = CodeIndexConfig(source_roots=source_roots, index_path=index_path)
            code_index = CodeIndex(idx_config)
            functions = code_index.find_function(name, file_filter=file_filter)
            if not functions:
                return json.dumps({'error': f"Function '{name}' not found", 'functions': [], 'total': 0})
            func = functions[0]
            source = ''
            try:
                func_path = Path(func.file_path)
                if func_path.exists() and func.start_line and func.end_line:
                    lines = func_path.read_text().splitlines()
                    source = '\n'.join(lines[func.start_line - 1:func.end_line])
            except Exception as e:
                logger.warning('Failed to read source for %s: %s', name, e)
            if not source:
                return json.dumps({'name': func.name, 'file_path': str(func.file_path), 'summary': f'Function {name} (source unavailable)'})
            ext = Path(func.file_path).suffix.lower()
            lang_map = {'.py': 'python', '.cpp': 'cpp', '.cc': 'cpp', '.c': 'c', '.h': 'cpp', '.hpp': 'cpp'}
            language = lang_map.get(ext, 'cpp')
            llm = create_llm_provider(config.llm)
            summarizer = FunctionSummarizer(llm)
            summary = await summarizer.summarize_function(source, name, str(func.file_path), language)
            return json.dumps({'name': func.name, 'file_path': str(func.file_path), 'start_line': func.start_line, 'end_line': func.end_line, 'signature': func.signature, 'class_name': func.class_name, 'summary': summary}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to summarize function')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_strategy_weights(error_type: str | None=None) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner
        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            weights = await meta_learner.suggest_strategy_weights(error_type)
            return json.dumps({'weights': weights, 'error_type': error_type}, indent=2)
        except Exception as e:
            logger.exception('Failed to get strategy weights')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_query_priority(error_type: str | None=None) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner
        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            priority = await meta_learner.suggest_query_priority(error_type)
            return json.dumps({'priority': priority, 'error_type': error_type}, indent=2)
        except Exception as e:
            logger.exception('Failed to get query priority')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_strategy_recommendations(error_type: str | None=None) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner
        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            weights = await meta_learner.suggest_strategy_weights(error_type)
            priority = await meta_learner.suggest_query_priority(error_type)
            strategies = await meta_learner.get_best_strategies(error_type, min_samples=3)
            stats = await meta_learner.get_meta_learning_statistics()
            top_strategies = [{'strategy': s['strategy'], 'times_used': s['times_used'], 'times_correct': int(s['success_rate'] * s['times_used']), 'success_rate': s['success_rate'], 'avg_confidence': s['avg_confidence'], 'avg_rank': s['avg_rank']} for s in strategies[:10]]
            return json.dumps({'weights': weights, 'query_priority': priority, 'top_strategies': top_strategies, 'stats': stats, 'error_type': error_type}, indent=2)
        except Exception as e:
            logger.exception('Failed to get strategy recommendations')
            return json.dumps({'error': str(e)}, indent=2)