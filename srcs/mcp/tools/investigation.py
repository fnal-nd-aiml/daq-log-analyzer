"""
File: investigation.py
Purpose: Running investigations and reading their results.
Category: Utility
Author: artdaq team
Depends: agent, knowledge, llm, models, callbacks, ...
Exports: register
Complexity: High | Lines: 235
"""

from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING, Any
from mcp.server.fastmcp import Context, FastMCP
from srcs.workbinder import BinderStore
from ..context import _get_agent_client, _json_default, get_client_session_id, get_coordinator, get_db_path
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    async def get_hypotheses(binder_id: str, min_score: float | None=None, source: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        hypotheses = await store.get_hypotheses(binder_id=binder_id, min_score=min_score, source=source, limit=limit)
        return json.dumps([h.model_dump(mode='json') for h in hypotheses], default=_json_default, indent=2)

    @mcp.tool()
    async def get_evidence(binder_id: str, evidence_type: str | None=None, strength: str | None=None, limit: int=100) -> str:
        store = BinderStore(get_db_path())
        evidence = await store.get_evidence_items(binder_id=binder_id, evidence_type=evidence_type, strength=strength, limit=limit)
        return json.dumps([e.model_dump(mode='json') for e in evidence], default=_json_default, indent=2)

    @mcp.tool()
    async def get_causal_chains(binder_id: str, hypothesis_id: str | None=None, limit: int=20) -> str:
        store = BinderStore(get_db_path())
        chains = await store.get_causal_chains(binder_id=binder_id, hypothesis_id=hypothesis_id, limit=limit)
        return json.dumps([c.model_dump(mode='json') for c in chains], default=_json_default, indent=2)

    @mcp.tool()
    async def get_challenges(binder_id: str, resolved: bool | None=None, severity: str | None=None, limit: int=50) -> str:
        store = BinderStore(get_db_path())
        challenges = await store.get_challenges(binder_id=binder_id, resolved=resolved, severity=severity, limit=limit)
        return json.dumps([c.model_dump(mode='json') for c in challenges], default=_json_default, indent=2)

    @mcp.tool()
    async def find_similar_investigations(error_function: str | None=None, error_message_pattern: str | None=None, limit: int=10) -> str:
        store = BinderStore(get_db_path())
        similar = await store.get_similar_investigations(error_function=error_function, error_message_pattern=error_message_pattern, limit=limit)
        return json.dumps(similar, default=_json_default, indent=2)

    @mcp.tool()
    async def get_conclusion(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type='conclusion', limit=1)
        if not artifacts:
            return json.dumps({'error': f'No conclusion found for binder: {binder_id}'})
        return json.dumps(artifacts[0].model_dump(mode='json'), default=_json_default, indent=2)

    @mcp.tool()
    async def investigate_error(error_message: str, log_content: str | None=None, error_line: int | None=None, context_lines: int=60, additional_files: str | None=None, ctx: Context | None=None) -> str:
        from srcs.models import Log
        from srcs.models.callbacks import PhaseEvent
        from srcs.models.log_parser import create_log_from_message, extract_error_and_context, parse_log_content
        phase_names = ['Prior Knowledge Retrieval', 'Hypothesis Generation', 'Evidence Seeking', 'Causal Chain Construction', 'Adversarial Review', 'Insufficiency Check', 'Synthesis', 'Pattern Learning']
        import asyncio

        async def _safe_progress(coro: Any) -> None:
            try:
                await coro
            except Exception:
                pass

        def on_phase(event: PhaseEvent) -> None:
            if ctx:
                phase_name = phase_names[event.phase] if event.phase < len(phase_names) else f'Phase {event.phase}'
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_safe_progress(ctx.report_progress(progress=event.phase + 1, total=8)))
                    loop.create_task(_safe_progress(ctx.info(f'Phase {event.phase}: {phase_name}')))
                except RuntimeError:
                    pass
        try:
            agent = await _get_agent_client()
            session_id = get_client_session_id()
            if agent is not None and session_id is not None:
                result_data = await agent.investigate(session_id, error_message=error_message)
                return json.dumps(result_data, default=_json_default, indent=2)
            coordinator = await get_coordinator()
            context_logs: list[Log] = []
            if log_content:
                logs = parse_log_content(log_content)
                if logs:
                    error, context_logs = extract_error_and_context(logs, error_line, context_lines)
                else:
                    error = create_log_from_message(error_message)
            else:
                error = create_log_from_message(error_message)
            source_files = None
            if additional_files:
                from srcs.models.logs import SourceFile
                try:
                    files_data = json.loads(additional_files)
                    source_files_list = []
                    if log_content:
                        source_files_list.append(SourceFile(filename='primary.log', content=log_content, error_line=error_line))
                    for fd in files_data:
                        source_files_list.append(SourceFile(filename=fd.get('filename', 'unknown.log'), content=fd.get('content', ''), error_line=fd.get('error_line')))
                    if len(source_files_list) > 1:
                        source_files = source_files_list
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f'Failed to parse additional_files JSON: {e}')
            result = await coordinator.investigate(error, context_logs, callback=on_phase, source_files=source_files)
            return json.dumps(result.model_dump(mode='json'), default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Investigation failed')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def analyze_message(message: str, ctx: Context | None=None) -> str:
        result: str = await investigate_error(error_message=message, log_content=None, error_line=None, context_lines=60, ctx=ctx)
        return result

    @mcp.tool()
    async def submit_feedback(investigation_id: str, correct: bool, actual_cause: str | None=None, corrected_summary: str | None=None, feedback_source: str='mcp') -> str:
        from srcs.knowledge import KnowledgeBase, PatternLearner, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigation = await kb.get_investigation(investigation_id)
            if not investigation:
                return json.dumps({'success': False, 'error': f'Investigation {investigation_id} not found'}, indent=2)
            stated_confidence = 0.5
            if investigation.hypotheses and investigation.hypotheses[0].score > 0:
                stated_confidence = min(0.95, 0.3 + investigation.hypotheses[0].score * 0.5)
            await kb.update_calibration('default', stated_confidence, correct)
            learner = PatternLearner(str(kb.config.sqlite_path))
            learning_updates = await learner.apply_feedback(investigation_id, correct, actual_cause, feedback_source=feedback_source)
            return json.dumps({'success': True, 'message': 'Feedback recorded successfully', 'stated_confidence': stated_confidence, 'correct': correct, 'actual_cause': actual_cause, 'feedback_source': feedback_source, 'patterns_updated': learning_updates.get('patterns_updated', []), 'patterns_created': learning_updates.get('patterns_created', [])}, indent=2)
        except Exception as e:
            logger.exception('Failed to submit feedback')
            return json.dumps({'success': False, 'error': str(e)}, indent=2)

    @mcp.tool()
    async def list_investigations(limit: int=20, offset: int=0, outcome: str | None=None) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigations = await kb.get_recent_investigations(limit, offset)
            filtered = investigations
            if outcome:
                filtered = [inv for inv in filtered if inv.outcome and inv.outcome.value == outcome]
            summaries = []
            for inv in filtered:
                root_cause = None
                confidence = None
                if inv.hypotheses and inv.hypotheses[0].score > 0:
                    root_cause = inv.hypotheses[0].description
                    confidence = inv.hypotheses[0].score
                summaries.append({'investigation_id': inv.id, 'outcome': inv.outcome.value if inv.outcome else 'UNKNOWN', 'root_cause': root_cause, 'confidence': confidence, 'duration_seconds': (inv.completed_at - inv.started_at).total_seconds() if inv.completed_at else 0.0, 'timestamp': inv.started_at})
            return json.dumps({'investigations': summaries, 'total': len(investigations)}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to list investigations')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_investigation(investigation_id: str) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigation = await kb.get_investigation(investigation_id)
            if not investigation:
                return json.dumps({'error': f'Investigation not found: {investigation_id}'})
            return json.dumps({'id': investigation.id, 'trigger_error': {'timestamp': investigation.trigger_error.timestamp, 'level': investigation.trigger_error.level, 'component': investigation.trigger_error.component, 'function': investigation.trigger_error.function, 'message': investigation.trigger_error.message}, 'outcome': investigation.outcome.value if investigation.outcome else None, 'started_at': investigation.started_at.isoformat(), 'completed_at': investigation.completed_at.isoformat() if investigation.completed_at else None, 'hypotheses': [{'id': h.id, 'description': h.description, 'score': h.score, 'status': h.status} for h in investigation.hypotheses], 'evidence_count': len(investigation.evidence.items), 'causal_chains_count': len(investigation.causal_chains), 'challenges_count': len(investigation.challenges)}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get investigation')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def get_investigation_quality(investigation_id: str) -> str:
        from srcs.agent import QualityAnalyzer, format_quality_report
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigation = await kb.get_investigation(investigation_id)
            if not investigation:
                return json.dumps({'error': f'Investigation not found: {investigation_id}'})
            analyzer = QualityAnalyzer()
            report = analyzer.analyze(investigation)
            return json.dumps({'investigation_id': investigation_id, 'quality_level': report.quality_level.value, 'overall_score': report.overall_score, 'report_text': format_quality_report(report)}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception('Failed to get investigation quality')
            return json.dumps({'error': str(e)}, indent=2)

    @mcp.tool()
    async def resume_investigation(investigation_id: str, ctx: Context | None=None) -> str:
        import asyncio
        client = await _get_agent_client()
        if client:
            try:
                client_payload = await client.resume_investigation(investigation_id)
                return json.dumps(client_payload, default=_json_default, indent=2)
            except Exception as e:
                logger.warning('REST resume failed, trying direct: %s', e)
        try:
            coordinator = await get_coordinator()
            phase_names = ['Prior Knowledge Retrieval', 'Hypothesis Generation', 'Evidence Seeking', 'Causal Chain Construction', 'Adversarial Review', 'Insufficiency Check', 'Synthesis', 'Pattern Learning']

            async def _safe_progress(coro: Any) -> None:
                try:
                    await coro
                except Exception:
                    pass
            from srcs.models.callbacks import PhaseEvent

            def on_phase(event: PhaseEvent) -> None:
                if ctx:
                    phase_name = phase_names[event.phase] if event.phase < len(phase_names) else f'Phase {event.phase}'
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(_safe_progress(ctx.report_progress(progress=event.phase + 1, total=8)))
                        loop.create_task(_safe_progress(ctx.info(f'Phase {event.phase}: {phase_name}')))
                    except RuntimeError:
                        pass
            if ctx:
                await _safe_progress(ctx.info(f'Resuming investigation {investigation_id}'))
            result = await coordinator.resume_investigation(investigation_id, callback=on_phase)
            confidence = 0.0
            if result.root_cause and result.root_cause.confidence:
                confidence = result.root_cause.confidence.calibrated
            return json.dumps({'investigation_id': investigation_id, 'outcome': result.outcome.value if result.outcome else 'UNKNOWN', 'confidence': confidence}, default=_json_default, indent=2)
        except ValueError as e:
            return json.dumps({'error': str(e)})
        except Exception as e:
            logger.exception('Failed to resume investigation')
            return json.dumps({'error': str(e)}, indent=2)