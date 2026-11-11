"""
File: progress.py
Purpose: Real-time progress reporting for Slack investigations.
Category: Utility
Author: artdaq team
Depends: callbacks, persona
Exports: PhaseState, ProgressReporter, SLACK_FILE_MAX_LENGTH
Complexity: High | Lines: 497
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent, PhaseEvent
from srcs.persona import PERSONAS
from .formatter import PHASE_TO_PERSONA, PhaseMetrics, ThreadState, format_causal_chain_thread, format_challenges_consolidated, format_evidence_round_thread, format_hypotheses_consolidated, format_investigation_header, format_pattern_thread, format_phase_card, format_phase_event, format_similar_cases_consolidated, format_source_location_thread, get_persona_references
if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient
logger = logging.getLogger(__name__)
SLACK_FILE_MAX_LENGTH = 20000

def _split_markdown(content: str, max_length: int) -> list[str]:
    if len(content) <= max_length:
        return [content]
    parts: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= max_length:
            parts.append(remaining)
            break
        split_at = remaining.rfind('\n\n', 0, max_length)
        if split_at < max_length // 3:
            split_at = remaining.rfind('\n', 0, max_length)
        if split_at < max_length // 3:
            split_at = max_length
        parts.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip('\n')
    return parts

@dataclass
class PhaseState:
    phase: int
    message_ts: str | None = None
    start_time_ms: int = 0
    metrics: PhaseMetrics = field(default_factory=PhaseMetrics)
    status: str = 'pending'
    summary_text: str = ''
    thread_reply_count: int = 0
    llm_event_count: int = 0
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    evidence_rounds: list[dict[str, Any]] = field(default_factory=list)
    challenges: list[dict[str, Any]] = field(default_factory=list)
    similar_cases: list[dict[str, Any]] = field(default_factory=list)
    source_locations: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    causal_chains: list[dict[str, Any]] = field(default_factory=list)

@dataclass
class ProgressReporter:
    say: Callable[..., Any]
    verbose: bool = False
    client: AsyncWebClient | None = None
    channel: str | None = None
    investigation_id: str | None = None
    _queue: asyncio.Queue[PhaseEvent | LLMEvent | DataRetrievalEvent | None] = field(default_factory=asyncio.Queue, repr=False)
    _consumer_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _thread_state: ThreadState = field(default_factory=ThreadState, repr=False)
    _phase_states: dict[int, PhaseState] = field(default_factory=dict, repr=False)
    _investigation_started: bool = field(default=False, repr=False)

    @property
    def _use_rich_mode(self) -> bool:
        return self.client is not None and self.channel is not None

    def start(self) -> None:
        if self.verbose:
            self._thread_state = ThreadState(start_time_ms=int(time.time() * 1000))
            self._phase_states = {}
            self._investigation_started = False
            self._consumer_task = asyncio.create_task(self._consume())

    def on_phase_event(self, event: PhaseEvent) -> None:
        if self.verbose:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning('Progress queue full, dropping event')

    def on_llm_event(self, event: LLMEvent) -> None:
        if self.verbose and self._use_rich_mode:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning('Progress queue full, dropping LLM event')

    def on_data_event(self, event: DataRetrievalEvent) -> None:
        if self.verbose and self._use_rich_mode:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning('Progress queue full, dropping data event')

    async def post_investigation_header(self, error_message: str, error_location: str | None=None, error_function: str | None=None) -> str | None:
        if not self._use_rich_mode:
            return None
        start_time = time.strftime('%H:%M:%S')
        blocks = format_investigation_header(error_message=error_message, error_location=error_location, error_function=error_function, start_time=start_time)
        try:
            assert self.channel is not None
            response = await self.client.chat_postMessage(channel=self.channel, text=f':microscope: Investigation started: {error_message[:100]}', blocks=blocks)
            ts = response.get('ts')
            self._thread_state.root_ts = ts if isinstance(ts, str) else None
            self._investigation_started = True
            return self._thread_state.root_ts
        except Exception as e:
            logger.warning('Failed to post investigation header: %s', e)
            return None

    async def stop(self) -> None:
        if not self._consumer_task:
            return
        self._queue.put_nowait(None)
        try:
            await asyncio.wait_for(self._consumer_task, timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning('Progress consumer timed out, cancelling')
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

    async def _consume(self) -> None:
        while True:
            try:
                event = await self._queue.get()
                if event is None:
                    break
                if isinstance(event, PhaseEvent):
                    await self._handle_phase_event(event)
                elif isinstance(event, LLMEvent):
                    await self._handle_llm_event(event)
                elif isinstance(event, DataRetrievalEvent):
                    await self._handle_data_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception('Error in progress consumer: %s', e)

    async def _handle_phase_event(self, event: PhaseEvent) -> None:
        if self._use_rich_mode:
            await self._handle_phase_event_rich(event)
        else:
            await self._handle_phase_event_simple(event)

    async def _handle_phase_event_simple(self, event: PhaseEvent) -> None:
        text = format_phase_event(event)
        if text:
            try:
                await self.say(text=text)
            except Exception as e:
                logger.warning('Failed to send progress message: %s', e)

    async def _handle_phase_event_rich(self, event: PhaseEvent) -> None:
        phase = event.phase
        if phase not in self._phase_states:
            self._phase_states[phase] = PhaseState(phase=phase, start_time_ms=int(time.time() * 1000))
        state = self._phase_states[phase]
        if event.event_type == 'start':
            if self.investigation_id is None and event.data.get('investigation_id'):
                self.investigation_id = event.data['investigation_id']
            await self._post_phase_card(state, event)
        elif event.event_type == 'item':
            self._update_metrics_from_item(state, event)
            if state.message_ts and state.metrics.count % 3 == 0:
                await self._update_phase_card(state)
        elif event.event_type == 'progress':
            state.summary_text = event.message or state.summary_text
            if state.message_ts:
                await self._update_phase_card(state)
        elif event.event_type == 'complete':
            state.status = 'complete'
            state.metrics.duration_ms = int(time.time() * 1000) - state.start_time_ms
            state.summary_text = self._extract_completion_summary(event)
            self._update_metrics_from_complete(state, event)
            if state.message_ts:
                await self._update_phase_card(state)
                await self._post_phase_artifacts(state)
        elif event.event_type == 'error':
            state.status = 'error'
            state.summary_text = event.message or 'An error occurred'
            if state.message_ts:
                await self._update_phase_card(state)

    async def _post_phase_card(self, state: PhaseState, event: PhaseEvent) -> None:
        state.status = 'in_progress'
        persona = PERSONAS.get(state.phase)
        state.summary_text = persona.thinking_phrase if persona else 'Working...'
        mentions = get_persona_references(state.phase)
        blocks = format_phase_card(phase=state.phase, status=state.status, summary_text=state.summary_text, metrics=state.metrics, mentions=mentions, investigation_id=self.investigation_id)
        try:
            assert self.channel is not None
            response = await self.client.chat_postMessage(channel=self.channel, text=f"Phase {state.phase}: {PHASE_TO_PERSONA.get(state.phase, 'Unknown')}", blocks=blocks)
            ts = response.get('ts')
            state.message_ts = ts if isinstance(ts, str) else None
            if state.message_ts:
                self._thread_state.phase_ts[state.phase] = state.message_ts
        except Exception as e:
            logger.warning('Failed to post phase card: %s', e)

    async def _update_phase_card(self, state: PhaseState) -> None:
        if not state.message_ts:
            return
        mentions = get_persona_references(state.phase)
        blocks = format_phase_card(phase=state.phase, status=state.status, summary_text=state.summary_text, metrics=state.metrics, mentions=mentions, thread_reply_count=state.thread_reply_count, investigation_id=self.investigation_id)
        try:
            assert self.channel is not None
            await self.client.chat_update(channel=self.channel, ts=state.message_ts, text=f"Phase {state.phase}: {PHASE_TO_PERSONA.get(state.phase, 'Unknown')}", blocks=blocks)
        except Exception as e:
            logger.warning('Failed to update phase card: %s', e)

    async def _post_thread_reply(self, phase: int, text: str, blocks: list[dict[str, Any]] | None=None) -> None:
        thread_ts = self._thread_state.phase_ts.get(phase)
        if not thread_ts:
            return
        try:
            assert self.channel is not None
            await self.client.chat_postMessage(channel=self.channel, text=text, blocks=blocks, thread_ts=thread_ts)
            if phase in self._phase_states:
                self._phase_states[phase].thread_reply_count += 1
        except Exception as e:
            logger.warning('Failed to post thread reply: %s', e)

    async def _handle_llm_event(self, event: LLMEvent) -> None:
        if not self._use_rich_mode:
            return
        phase = event.phase
        persona_name = PHASE_TO_PERSONA.get(phase, 'Unknown')
        if phase not in self._phase_states:
            self._phase_states[phase] = PhaseState(phase=phase, start_time_ms=int(time.time() * 1000))
        state = self._phase_states[phase]
        state.llm_event_count += 1
        md_content = self._format_llm_event_markdown(event, persona_name)
        event_num = state.llm_event_count
        event_type = event.event_type.capitalize()
        if len(md_content) <= SLACK_FILE_MAX_LENGTH:
            filename = f'{persona_name}_{event_num:02d}_{event_type}.md'
            await self._upload_file_to_thread(phase=phase, content=md_content, filename=filename, title=f'{persona_name} LLM {event_type}')
        else:
            parts = _split_markdown(md_content, SLACK_FILE_MAX_LENGTH)
            for i, part in enumerate(parts, 1):
                suffix = f'_part{i}'
                filename = f'{persona_name}_{event_num:02d}_{event_type}{suffix}.md'
                await self._upload_file_to_thread(phase=phase, content=part, filename=filename, title=f'{persona_name} LLM {event_type} ({i}/{len(parts)})')

    def _format_llm_event_markdown(self, event: LLMEvent, persona_name: str) -> str:
        lines: list[str] = []
        event_type = event.event_type.capitalize()
        lines.append(f'# {persona_name} - LLM {event_type}')
        lines.append('')
        lines.append(f'**Model:** `{event.model_name}`')
        if event.response_model:
            lines.append(f'**Response Schema:** `{event.response_model}`')
        lines.append('')
        if event.event_type == 'request':
            if event.system_prompt:
                lines.append('## System Prompt')
                lines.append('')
                lines.append('```')
                lines.append(event.system_prompt)
                lines.append('```')
                lines.append('')
            if event.user_prompt:
                lines.append('## User Prompt')
                lines.append('')
                lines.append('```')
                lines.append(event.user_prompt)
                lines.append('```')
        elif event.parse_failed:
            lines.append('## :warning: Response (PARSE FAILED)')
            lines.append('')
            lines.append('> **Expected:** Valid JSON response matching the schema below')
            lines.append('> **Actual:** Malformed or non-JSON response')
            if event.parse_error:
                lines.append(f'> **Error:** `{event.parse_error}`')
            lines.append('')
            if event.expected_schema:
                lines.append('### Expected JSON Schema')
                lines.append('')
                lines.append('```json')
                lines.append(event.expected_schema)
                lines.append('```')
                lines.append('')
            lines.append('### Raw Response (Malformed)')
            lines.append('')
            lines.append('```text')
            lines.append(event.response or '(empty response)')
            lines.append('```')
        else:
            lines.append('## Response')
            lines.append('')
            if event.response:
                response = event.response.strip()
                if response.startswith('{') or response.startswith('['):
                    lines.append('```json')
                else:
                    lines.append('```')
                lines.append(event.response)
                lines.append('```')
        return '\n'.join(lines)

    async def _upload_file_to_thread(self, phase: int, content: str, filename: str, title: str) -> None:
        thread_ts = self._thread_state.phase_ts.get(phase)
        if not thread_ts or not self.channel:
            return
        if not content or not content.strip():
            return
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.client.files_upload_v2(channel=self.channel, content=content, filename=filename, title=title, thread_ts=thread_ts)
                if phase in self._phase_states:
                    self._phase_states[phase].thread_reply_count += 1
                return
            except Exception as e:
                if attempt < max_retries - 1 and 'file_update_failed' in str(e):
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                logger.warning('Failed to upload file to thread: %s', e)

    async def _handle_data_event(self, event: DataRetrievalEvent) -> None:
        if not self._use_rich_mode:
            return
        phase = event.phase
        if event.event_type == 'query':
            text = f':mag: *{event.operation}* | {event.source}'
        else:
            text = f':package: *Result* | {event.source}'
            if event.result_count is not None:
                text += f' ({event.result_count} results)'
            if event.result_summary:
                text += f'\n_{event.result_summary}_'
        await self._post_thread_reply(phase, text)

    def _update_metrics_from_item(self, state: PhaseState, event: PhaseEvent) -> None:
        data = event.data
        item_type = data.get('type', '')
        state.metrics.count += 1
        if item_type == 'hypothesis':
            prior = data.get('prior', 0)
            if prior > state.metrics.top_score:
                state.metrics.top_score = prior
            state.hypotheses.append(data)
        elif item_type == 'evidence':
            strength = data.get('strength', 'WEAK')
            if strength == 'STRONG':
                state.metrics.strong += 1
            elif strength == 'MODERATE':
                state.metrics.moderate += 1
            else:
                state.metrics.weak += 1
            state.evidence_rounds.append(data)
        elif item_type == 'source_location':
            state.metrics.strong += 1
            state.source_locations.append(data)
        elif item_type == 'similar_case':
            state.similar_cases.append(data)
        elif item_type == 'pattern':
            state.patterns.append(data)
        elif item_type == 'challenge':
            severity = data.get('severity', 'MEDIUM')
            if severity == 'HIGH':
                state.metrics.challenges_high += 1
            elif severity == 'MEDIUM':
                state.metrics.challenges_medium += 1
            else:
                state.metrics.challenges_low += 1
            state.challenges.append(data)
        elif item_type == 'causal_chain':
            state.causal_chains.append(data)
        elif item_type == 'round':
            state.metrics.current_round = data.get('round', 0)
            state.metrics.rounds = data.get('total', 0)

    def _update_metrics_from_complete(self, state: PhaseState, event: PhaseEvent) -> None:
        data = event.data
        phase = state.phase
        if phase == 0:
            state.metrics.count = data.get('similar_cases', 0)
            state.metrics.strong = data.get('source_locations', 0)
            state.metrics.moderate = data.get('patterns_found', 0)
        elif phase == 1:
            state.metrics.count = data.get('hypotheses_count', 0)
        elif phase == 2:
            state.metrics.count = data.get('evidence_count', 0)
        elif phase == 3:
            state.metrics.count = data.get('chains_count', data.get('causal_chains_count', 0))
            state.metrics.strong = data.get('evidence_cited', 0)
        elif phase == 4:
            state.metrics.count = data.get('challenges_count', 0)
        elif phase == 5:
            state.metrics.top_score = float(data.get('outcome_confidence', 0) or 0)
        elif phase == 6:
            state.metrics.top_score = data.get('confidence', 0)

    def _extract_completion_summary(self, event: PhaseEvent) -> str:
        data = event.data
        phase = event.phase
        if phase == 0:
            patterns = data.get('patterns_found', 0)
            cases = data.get('similar_cases', 0)
            sources = data.get('source_locations', 0)
            if patterns or cases or sources:
                return "I've searched our archives and found relevant history."
            return 'No prior knowledge found for this error.'
        elif phase == 1:
            count = data.get('hypotheses_count', 0)
            if count > 0:
                return "Based on the evidence, I've formed several theories."
            return 'Unable to generate hypotheses from the available data.'
        elif phase == 2:
            count = data.get('evidence_count', 0)
            if count > 0:
                return "I've investigated the hypotheses through code analysis."
            return 'Unable to gather evidence for the hypotheses.'
        elif phase == 3:
            count = data.get('chains_count', data.get('causal_chains_count', 0))
            if count > 0:
                return "I've traced the reasoning paths for the top hypotheses."
            return 'Unable to construct causal chains.'
        elif phase == 4:
            count = data.get('challenges_count', 0)
            if count > 0:
                return 'I have some concerns about these conclusions.'
            return 'No significant challenges to the conclusions.'
        elif phase == 5:
            outcome = data.get('outcome', 'unknown')
            return f"After reviewing all evidence, I've reached a verdict: {outcome}."
        elif phase == 6:
            outcome = data.get('outcome', 'unknown')
            return "Here's my final analysis and recommendations."
        elif phase == 7:
            count = data.get('patterns_learned', 0)
            if count > 0:
                return "I've recorded new patterns for future investigations."
            return 'No new patterns to learn from this investigation.'
        return ''

    async def _post_phase_artifacts(self, state: PhaseState) -> None:
        phase = state.phase
        if phase == 0:
            await self._post_archivist_artifacts(state)
        elif phase == 1:
            await self._post_theorist_artifacts(state)
        elif phase == 2:
            await self._post_detective_artifacts(state)
        elif phase == 3:
            await self._post_logician_artifacts(state)
        elif phase == 4:
            await self._post_advocate_artifacts(state)

    async def _post_archivist_artifacts(self, state: PhaseState) -> None:
        valid_cases = [c for c in state.similar_cases if c.get('root_cause')]
        if valid_cases:
            blocks = format_similar_cases_consolidated(valid_cases)
            text = f'Similar cases ({len(valid_cases)} found)'
            await self._post_thread_reply(state.phase, text, blocks)
        for loc in state.source_locations:
            file_display = loc.get('file_path') or loc.get('file') or 'unknown'
            if file_display == 'unknown':
                continue
            blocks = format_source_location_thread(loc)
            text = f'Source: {file_display}'
            await self._post_thread_reply(state.phase, text, blocks)
        for pattern in state.patterns:
            blocks = format_pattern_thread(pattern)
            text = f"Pattern: {pattern.get('name', 'unknown')}"
            await self._post_thread_reply(state.phase, text, blocks)

    async def _post_theorist_artifacts(self, state: PhaseState) -> None:
        min_display_prior = 0.15
        meaningful = [hyp for hyp in state.hypotheses if hyp.get('prior', 0) >= min_display_prior or hyp.get('score', 0) >= min_display_prior]
        if meaningful:
            blocks = format_hypotheses_consolidated(meaningful)
            text = f'Hypotheses ({len(meaningful)} generated)'
            await self._post_thread_reply(state.phase, text, blocks)

    async def _post_detective_artifacts(self, state: PhaseState) -> None:
        for evidence in state.evidence_rounds:
            blocks = format_evidence_round_thread(evidence)
            text = f"Evidence: {evidence.get('description', 'Analysis')[:50]}..."
            await self._post_thread_reply(state.phase, text, blocks)

    async def _post_logician_artifacts(self, state: PhaseState) -> None:
        for chain in state.causal_chains:
            blocks = format_causal_chain_thread(chain)
            text = f"Causal chain: {chain.get('hypothesis_id', 'Unknown')[:50]}..."
            await self._post_thread_reply(state.phase, text, blocks)

    async def _post_advocate_artifacts(self, state: PhaseState) -> None:
        if state.challenges:
            blocks = format_challenges_consolidated(state.challenges)
            text = f'Challenges ({len(state.challenges)} raised)'
            await self._post_thread_reply(state.phase, text, blocks)