"""
File: sse.py
Purpose: Server-Sent Events support for streaming investigation progress.
Category: Utility
Author: artdaq team
Depends: callbacks
Exports: SSEEvent, format_sse, phase_event_to_sse, llm_event_to_sse, data_retrieval_event_to_sse
Complexity: Low | Lines: 66
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent, PhaseEvent

@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {'event': self.event, 'data': self.data}
        if self.id is not None:
            d['id'] = self.id
        return d

def format_sse(event: SSEEvent) -> str:
    lines: list[str] = []
    lines.append(f'event: {event.event}')
    if event.id is not None:
        lines.append(f'id: {event.id}')
    lines.append(f'data: {json.dumps(event.data, default=str)}')
    lines.append('')
    return '\n'.join(lines) + '\n'

def phase_event_to_sse(evt: PhaseEvent) -> SSEEvent:
    event_type = f'phase_{evt.event_type}'
    data: dict[str, Any] = {'phase': evt.phase, 'phase_name': evt.phase_name}
    if evt.message:
        data['message'] = evt.message
    if evt.data:
        data.update(evt.data)
    return SSEEvent(event=event_type, data=data)

def llm_event_to_sse(evt: LLMEvent) -> SSEEvent:
    event_type = f'llm_{evt.event_type}'
    data: dict[str, Any] = {'phase': evt.phase, 'model_name': evt.model_name}
    if evt.event_type == 'request':
        if evt.system_prompt:
            data['system_prompt'] = evt.system_prompt
        if evt.user_prompt:
            data['user_prompt'] = evt.user_prompt
    elif evt.event_type == 'response':
        if evt.response:
            data['response'] = evt.response
        if evt.response_model:
            data['response_model'] = evt.response_model
        if evt.parse_failed:
            data['parse_failed'] = True
            if evt.parse_error:
                data['parse_error'] = evt.parse_error
    return SSEEvent(event=event_type, data=data)

def data_retrieval_event_to_sse(evt: DataRetrievalEvent) -> SSEEvent:
    event_type = f'data_{evt.event_type}'
    data: dict[str, Any] = {'phase': evt.phase, 'source': evt.source, 'operation': evt.operation}
    if evt.event_type == 'query' and evt.query_params:
        data['query_params'] = evt.query_params
    elif evt.event_type == 'result':
        if evt.result_summary:
            data['result_summary'] = evt.result_summary
        if evt.result_count is not None:
            data['result_count'] = evt.result_count
    return SSEEvent(event=event_type, data=data)