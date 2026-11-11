"""
File: log_tools.py
Purpose: Log analysis tools for the agentic API.
Category: Utility
Author: artdaq team
Depends: log_parser
Exports: parse_logs, search_logs, get_log_context, get_log_summary, correlate_events
Complexity: Medium | Lines: 158
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Any
from srcs.models.log_parser import extract_error_and_context, parse_log_content
from ..errors import validation_error
from ..sessions import MAX_PARSED_LOGS_PER_SESSION, ParsedLogSummary
from .router import ToolContext, register_tool

def _log_to_dict(log: Any) -> dict[str, Any]:
    return {'timestamp': log.timestamp.isoformat() if isinstance(log.timestamp, datetime) else str(log.timestamp), 'level': log.level, 'component': log.component, 'function': log.function, 'message': log.message, 'raw_line': log.raw_line, 'line': log.line}

@register_tool('parse_logs')
async def parse_logs(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    content = params.get('content') or ctx.request_body.get('content')
    if not content:
        raise validation_error("'content' is required for parse_logs.")
    error_line = params.get('error_line') or ctx.request_body.get('error_line')
    context_lines = params.get('context_lines', 60)
    logs = parse_log_content(content, max_lines=MAX_PARSED_LOGS_PER_SESSION)
    if not logs:
        raise validation_error('No parseable log entries found in content.')
    error, context = extract_error_and_context(logs, error_line, context_lines)
    parsed = [_log_to_dict(log) for log in logs]
    ctx.session.state.parsed_logs = parsed
    ctx.session.state._search_cache.clear()
    components = sorted({log.component for log in logs})
    error_count = sum((1 for log in logs if log.level == 'ERROR'))
    warning_count = sum((1 for log in logs if log.level == 'WARNING'))
    timestamps = [log.timestamp for log in logs]
    ctx.session.state.log_summary = ParsedLogSummary(total_entries=len(logs), error_count=error_count, warning_count=warning_count, components=components, time_range_start=min(timestamps).isoformat() if timestamps else None, time_range_end=max(timestamps).isoformat() if timestamps else None)
    return {'trigger_error': _log_to_dict(error), 'context_logs': [_log_to_dict(c) for c in context], 'total_parsed': len(logs), 'summary': ctx.session.state.log_summary.model_dump()}

@register_tool('search_logs')
async def search_logs(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    parsed = ctx.session.state.parsed_logs
    if not parsed:
        raise validation_error('No parsed logs in session. Call parse_logs first.')
    pattern = params.get('pattern')
    severity = params.get('severity')
    component = params.get('component')
    time_start = params.get('time_start')
    time_end = params.get('time_end')
    limit = params.get('limit', 100)
    cache = ctx.session.state._search_cache
    cache_key = repr((len(parsed), pattern, severity, component, time_start, time_end, limit))
    cached: dict[str, Any] | None = cache.get(cache_key)
    if cached is not None:
        return cached
    results = []
    for entry in parsed:
        if severity and entry.get('level', '').upper() != severity.upper():
            continue
        if component and entry.get('component', '').lower() != component.lower():
            continue
        if pattern:
            msg = entry.get('message', '') or ''
            raw = entry.get('raw_line', '') or ''
            if not re.search(pattern, msg, re.IGNORECASE) and (not re.search(pattern, raw, re.IGNORECASE)):
                continue
        if time_start:
            ts = entry.get('timestamp', '')
            if ts and ts < time_start:
                continue
        if time_end:
            ts = entry.get('timestamp', '')
            if ts and ts > time_end:
                continue
        results.append(entry)
        if len(results) >= limit:
            break
    response = {'matches': results, 'total_matches': len(results), 'searched': len(parsed)}
    if len(cache) >= 128:
        cache.pop(next(iter(cache)))
    cache[cache_key] = response
    return response

@register_tool('get_log_context')
async def get_log_context(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    parsed = ctx.session.state.parsed_logs
    if not parsed:
        raise validation_error('No parsed logs in session. Call parse_logs first.')
    target_line = params.get('line')
    if target_line is None:
        raise validation_error("'line' parameter is required for get_log_context.")
    before = params.get('before', 10)
    after = params.get('after', 10)
    target_idx = None
    for i, entry in enumerate(parsed):
        if entry.get('line') == target_line:
            target_idx = i
            break
    if target_idx is None:
        target_idx = min(target_line - 1, len(parsed) - 1)
        if target_idx < 0:
            target_idx = 0
    start = max(0, target_idx - before)
    end = min(len(parsed), target_idx + after + 1)
    return {'target': parsed[target_idx] if target_idx < len(parsed) else None, 'before': parsed[start:target_idx], 'after': parsed[target_idx + 1:end]}

@register_tool('get_log_summary')
async def get_log_summary(ctx: ToolContext) -> dict[str, Any]:
    parsed = ctx.session.state.parsed_logs
    if not parsed:
        raise validation_error('No parsed logs in session. Call parse_logs first.')
    level_counts: dict[str, int] = {}
    component_counts: dict[str, int] = {}
    for entry in parsed:
        level = entry.get('level', 'UNKNOWN')
        comp = entry.get('component', 'Unknown')
        level_counts[level] = level_counts.get(level, 0) + 1
        component_counts[comp] = component_counts.get(comp, 0) + 1
    return {'total_entries': len(parsed), 'level_counts': level_counts, 'component_counts': component_counts, 'summary': ctx.session.state.log_summary.model_dump() if ctx.session.state.log_summary else None}

@register_tool('correlate_events')
async def correlate_events(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    parsed = ctx.session.state.parsed_logs
    if not parsed:
        raise validation_error('No parsed logs in session. Call parse_logs first.')
    by_component: dict[str, list[dict[str, Any]]] = {}
    for entry in parsed:
        comp = entry.get('component', 'Unknown')
        by_component.setdefault(comp, []).append(entry)
    window_seconds = params.get('window_seconds', 5)
    target_level = params.get('level', 'ERROR')
    correlations: list[dict[str, Any]] = []
    for entry in parsed:
        if entry.get('level', '').upper() != target_level.upper():
            continue
        ts_str = entry.get('timestamp', '')
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue
        related: list[dict[str, Any]] = []
        for comp, entries in by_component.items():
            if comp == entry.get('component'):
                continue
            for other in entries:
                other_ts_str = other.get('timestamp', '')
                if not other_ts_str:
                    continue
                try:
                    other_ts = datetime.fromisoformat(other_ts_str)
                except (ValueError, TypeError):
                    continue
                delta = abs((ts - other_ts).total_seconds())
                if delta <= window_seconds:
                    related.append({'entry': other, 'delta_seconds': round(delta, 3)})
        if related:
            correlations.append({'trigger': entry, 'related_events': related[:20]})
    return {'correlations': correlations[:50], 'total_correlations': len(correlations), 'components': list(by_component.keys())}