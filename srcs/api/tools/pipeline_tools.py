"""
File: pipeline_tools.py
Purpose: Pipeline tools for investigation and expert Q&A.
Category: Utility
Author: artdaq team
Depends: agent, dependencies, knowledge, logging_wrapper, llm, ...
Exports: investigate, investigate_stream, ask_experts
Complexity: Medium | Lines: 164
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncGenerator
from fastapi.responses import StreamingResponse
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent, PhaseEvent
from srcs.models.log_parser import extract_error_and_context, parse_log_content
from srcs.models.logs import Log, SourceFile
from ..errors import validation_error
from ..sse import SSEEvent, data_retrieval_event_to_sse, format_sse, llm_event_to_sse, phase_event_to_sse
from .router import ToolContext, register_tool
logger = logging.getLogger(__name__)

def _parse_source_files(params: dict[str, Any]) -> list[SourceFile] | None:
    raw = params.get('source_files')
    if not raw:
        return None
    return [SourceFile(**f) for f in raw]

def _build_error_log(ctx: ToolContext) -> tuple[Log, list[Log]]:
    params = ctx.request_body.get('params', {})
    source_files = _parse_source_files(params)
    if source_files:
        logs = parse_log_content(source_files[0].content)
        if logs:
            return extract_error_and_context(logs, source_files[0].error_line, 60)
    error_message = params.get('error_message')
    if error_message:
        error = Log(timestamp=datetime.now(), level=params.get('level', 'ERROR'), component=params.get('component', 'Unknown'), message=error_message)
        return (error, [])
    parsed = ctx.session.state.parsed_logs
    if not parsed:
        raise validation_error("Either provide 'error_message' or call parse_logs first.")
    errors = [e for e in parsed if e.get('level') == 'ERROR']
    if not errors:
        raise validation_error('No ERROR entries found in parsed logs.')
    trigger = errors[0]
    error = Log(timestamp=datetime.fromisoformat(trigger['timestamp']) if trigger.get('timestamp') else datetime.now(), level=trigger.get('level', 'ERROR'), component=trigger.get('component', 'Unknown'), function=trigger.get('function'), message=trigger.get('message', ''), raw_line=trigger.get('raw_line'), line=trigger.get('line'))
    context_logs: list[Log] = []
    for entry in parsed:
        if entry is trigger:
            break
        try:
            context_logs.append(Log(timestamp=datetime.fromisoformat(entry['timestamp']) if entry.get('timestamp') else datetime.now(), level=entry.get('level', 'INFO'), component=entry.get('component', 'Unknown'), function=entry.get('function'), message=entry.get('message', ''), raw_line=entry.get('raw_line'), line=entry.get('line')))
        except (KeyError, ValueError, TypeError) as e:
            logger.debug('Skipping unparseable context log entry: %s', e)
            continue
    return (error, context_logs[-60:])

async def _get_coordinator() -> Any:
    from srcs.api.dependencies import get_llm_config, get_settings, get_source_config, get_storage_config
    settings = get_settings()
    llm_config = get_llm_config(settings)
    from srcs.llm import create_llm_provider
    llm = create_llm_provider(llm_config)
    storage_config = get_storage_config(settings)
    from srcs.knowledge import KnowledgeBase
    kb = KnowledgeBase(storage_config, llm)
    await kb.initialize()
    source_config = get_source_config(settings)
    from srcs.agent import InvestigationConfig, InvestigationCoordinator
    from srcs.api.dependencies import get_pipeline_config
    config = InvestigationConfig(max_hypotheses=settings.max_hypotheses, max_evidence_iterations=settings.max_evidence_iterations)
    coordinator = InvestigationCoordinator(kb, llm, config, source_config=source_config)
    pipeline_config = get_pipeline_config()
    coordinator.configure_pipeline(pipeline_config)
    return coordinator

@register_tool('investigate')
async def investigate(ctx: ToolContext) -> dict[str, Any]:
    error, context = _build_error_log(ctx)
    params = ctx.request_body.get('params', {})
    source_files = _parse_source_files(params)
    coordinator = await _get_coordinator()
    result = await coordinator.investigate(error, context, source_files=source_files)
    result_dict = result.model_dump(mode='json')
    ctx.session.state.investigation_result = result_dict
    return {'outcome': result.outcome.value if hasattr(result.outcome, 'value') else str(result.outcome), 'confidence': result.confidence, 'root_cause': result.root_cause.model_dump(mode='json') if result.root_cause and hasattr(result.root_cause, 'model_dump') else str(result.root_cause) if result.root_cause else None, 'executive_summary': result.executive_summary, 'explanation': result.explanation, 'recommendations': result.recommendations}

@register_tool('investigate_stream')
async def investigate_stream(ctx: ToolContext) -> StreamingResponse:
    error, context = _build_error_log(ctx)
    params = ctx.request_body.get('params', {})
    verbose = params.get('verbose', False)
    source_files = _parse_source_files(params)
    coordinator = await _get_coordinator()
    queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()

    def on_phase_event(event: PhaseEvent) -> None:
        sse = phase_event_to_sse(event)
        queue.put_nowait(sse)

    def on_llm_event(event: LLMEvent) -> None:
        sse = llm_event_to_sse(event)
        queue.put_nowait(sse)

    def on_data_event(event: DataRetrievalEvent) -> None:
        sse = data_retrieval_event_to_sse(event)
        queue.put_nowait(sse)
    if verbose:
        try:
            from srcs.knowledge.logging_wrapper import LoggingKnowledgeBase
            from srcs.llm.logging_wrapper import LoggingLLMProvider
            if hasattr(coordinator, 'llm') and coordinator.llm is not None:
                wrapped_llm = LoggingLLMProvider(coordinator.llm, on_llm_event)
                coordinator.llm = wrapped_llm
                if hasattr(coordinator, '_pipeline_engine') and coordinator._pipeline_engine is not None:
                    coordinator._pipeline_engine._llm = wrapped_llm
            if hasattr(coordinator, 'kb') and coordinator.kb is not None:
                wrapped_kb = LoggingKnowledgeBase(coordinator.kb, on_data_event)
                coordinator.kb = wrapped_kb
                if hasattr(coordinator, '_pipeline_engine') and coordinator._pipeline_engine is not None:
                    coordinator._pipeline_engine._kb = wrapped_kb
        except ImportError:
            pass

    async def run_investigation() -> None:
        try:
            result = await coordinator.investigate(error, context, callback=on_phase_event, source_files=source_files)
            result_dict = result.model_dump(mode='json')
            ctx.session.state.investigation_result = result_dict
            queue.put_nowait(SSEEvent(event='investigation_complete', data=result_dict))
        except Exception as e:
            queue.put_nowait(SSEEvent(event='error', data={'message': str(e)}))
        finally:
            queue.put_nowait(None)

    async def event_generator() -> AsyncGenerator[str, None]:
        task = asyncio.create_task(run_investigation())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield format_sse(event)
        finally:
            if not task.done():
                task.cancel()
    return StreamingResponse(event_generator(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})

@register_tool('ask_experts')
async def ask_experts(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    question = params.get('question')
    if not question:
        raise validation_error("'question' is required for ask_experts.")
    from srcs.llm import create_llm_provider
    from srcs.persona.orchestrator import PanelOrchestrator
    from ..dependencies import get_llm_config, get_settings
    settings = get_settings()
    llm_config = get_llm_config(settings)
    llm = create_llm_provider(llm_config)
    orchestrator = PanelOrchestrator(llm_provider=llm)
    related_logs: list[Log] = []
    parsed = ctx.session.state.parsed_logs
    if parsed:
        for entry in parsed[:20]:
            try:
                related_logs.append(Log(timestamp=datetime.fromisoformat(entry['timestamp']) if entry.get('timestamp') else datetime.now(), level=entry.get('level', 'INFO'), component=entry.get('component', 'Unknown'), message=entry.get('message', '')))
            except (KeyError, ValueError, TypeError):
                continue
    result = await orchestrator.answer(question, related_logs=related_logs or None)
    return {'answer': result.answer, 'confidence': result.confidence, 'key_points': result.key_points, 'caveats': result.caveats}