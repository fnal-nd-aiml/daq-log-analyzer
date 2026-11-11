"""
File: binder_handler.py
Purpose: Workbinder command handling for Slack.
Category: Utility
Author: artdaq team
Depends: client
Exports: WorkbinderResponse, handle_workbinder_command
Complexity: Medium | Lines: 519
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from srcs.api.client import AgentClient
from .binder_formatter import format_binder_list
logger = logging.getLogger(__name__)

@dataclass
class WorkbinderResponse:
    blocks: list[dict] = field(default_factory=list)
    file_content: str | None = None
    file_name: str | None = None
    file_title: str | None = None

async def handle_workbinder_command(subcommand: str, binder_id: str | None, investigation_id: str | None, artifact_type: str | None, phase: int | None, persona: str | None, limit: int, query: str | None, api_url: str) -> WorkbinderResponse:
    async with AgentClient(api_url) as client:
        if investigation_id and (not binder_id):
            try:
                result = await client.get_binder_by_investigation(investigation_id)
                binder_id = result['binder_id']
            except Exception:
                return _error_response(f'No binder found for investigation: {investigation_id}')
        if binder_id and subcommand in ('show', 'artifacts', 'search', 'history', 'audit'):
            try:
                await client.get_binder(binder_id)
            except Exception:
                try:
                    result = await client.get_binder_by_investigation(binder_id)
                    binder_id = result['binder_id']
                except Exception:
                    pass
        try:
            if subcommand == 'list':
                blocks = await _handle_list(client, limit)
                return WorkbinderResponse(blocks=blocks)
            elif subcommand == 'show':
                if not binder_id:
                    return _error_response('Missing ID. Usage: `workbinder show <id>`')
                blocks = await _handle_show(client, binder_id)
                return WorkbinderResponse(blocks=blocks)
            elif subcommand == 'artifacts':
                if not binder_id:
                    return _error_response('Missing ID. Usage: `workbinder artifacts <id> [type=T] [phase=N]`')
                blocks = await _handle_artifacts(client, binder_id, artifact_type, phase, limit)
                return WorkbinderResponse(blocks=blocks)
            elif subcommand == 'artifact':
                if binder_id == 'all':
                    if not investigation_id:
                        return _error_response('Missing investigation ID. Usage: `workbinder artifact all inv=<id>`')
                    try:
                        result = await client.get_binder_by_investigation(investigation_id)
                        resolved_binder_id = result['binder_id']
                    except Exception:
                        return _error_response(f'No binder found for investigation: {investigation_id}')
                    return await _handle_artifact_all(client, resolved_binder_id, investigation_id, artifact_type, phase, limit)
                if not binder_id:
                    return _error_response('Missing artifact ID. Usage: `workbinder artifact <artifact_id>`')
                return await _handle_artifact(client, binder_id)
            elif subcommand == 'search':
                if not binder_id:
                    return _error_response('Missing ID. Usage: `workbinder search <id> "query"`')
                if not query:
                    return _error_response('Missing search query. Usage: `workbinder search <id> "query"`')
                blocks = await _handle_search(client, binder_id, query, artifact_type)
                return WorkbinderResponse(blocks=blocks)
            elif subcommand == 'history':
                if not binder_id:
                    return _error_response('Missing ID. Usage: `workbinder history <id>`')
                blocks = await _handle_history(client, binder_id, limit)
                return WorkbinderResponse(blocks=blocks)
            elif subcommand == 'audit':
                if not binder_id:
                    return _error_response('Missing ID. Usage: `workbinder audit <id> [persona=P]`')
                blocks = await _handle_audit(client, binder_id, persona, phase, limit)
                return WorkbinderResponse(blocks=blocks)
            elif subcommand == 'help':
                return WorkbinderResponse(blocks=_help_blocks())
            else:
                return _error_response(f'Unknown subcommand: {subcommand}. Use `workbinder help` for available commands.')
        except Exception as e:
            logger.exception(f'Error handling workbinder command: {e}')
            return _error_response(f'Error: {e}')

async def _handle_list(client: AgentClient, limit: int) -> list[dict]:
    response = await client.list_binders(limit=limit)
    binders = response.get('binders', [])
    if not binders:
        return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_No binders found_'}}]
    binder_data = []
    for b in binders:
        binder_data.append({'id': b.get('binder_id', b.get('id', '')), 'investigation_id': b.get('investigation_id', ''), 'status': b.get('status', 'unknown'), 'created_at': b.get('created_at', ''), 'updated_at': b.get('updated_at', ''), 'artifact_count': b.get('artifact_count', 0)})
    return format_binder_list(binder_data)

async def _handle_show(client: AgentClient, binder_id: str) -> list[dict]:
    try:
        binder = await client.get_binder(binder_id)
    except Exception:
        return _error_blocks(f'Binder not found: {binder_id}')
    try:
        summary = await client.get_binder_summary(binder_id)
    except Exception:
        summary = {}
    try:
        audit_summary = await client.get_binder_audit_summary(binder_id)
        audit_count = audit_summary.get('total_entries', 0)
    except Exception:
        audit_count = 0
    artifact_counts = binder.get('artifact_counts', {})
    current_phase = summary.get('current_phase', 0)
    outcome = summary.get('outcome', 'N/A')
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'Binder: {binder_id[:16]}'}}]
    info_text = f"*Investigation ID:* `{binder.get('investigation_id', 'N/A')}`\n*Status:* {binder.get('status', 'unknown')}\n*Current Phase:* {current_phase}\n*Outcome:* {outcome}\n*Created:* {binder.get('created_at', 'N/A')}\n*Updated:* {binder.get('updated_at', 'N/A')}\n"
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': info_text}})
    blocks.append({'type': 'divider'})
    if artifact_counts:
        breakdown_text = '*Artifacts by Type:*\n'
        for art_type, count in sorted(artifact_counts.items()):
            breakdown_text += f'• `{art_type}`: {count}\n'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': breakdown_text}})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'Audit log entries: {audit_count}'}]})
    return blocks

async def _handle_artifacts(client: AgentClient, binder_id: str, artifact_type: str | None, phase: int | None, limit: int) -> list[dict]:
    response = await client.query_binder_artifacts(binder_id, artifact_type=artifact_type, phase=phase, limit=limit)
    artifacts = response.get('artifacts', [])
    if not artifacts:
        return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_No artifacts found matching criteria_'}}]
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'Artifacts ({len(artifacts)})'}}]
    by_type: dict[str, list[dict]] = {}
    for artifact in artifacts:
        type_name = artifact.get('artifact_type', 'unknown')
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(artifact)
    for type_name, type_artifacts in sorted(by_type.items()):
        text_lines = [f'*{type_name}* ({len(type_artifacts)}):']
        for art in type_artifacts[:10]:
            art_id = art.get('id', '')[:8]
            art_phase = art.get('phase')
            phase_str = f'P{art_phase}' if art_phase is not None else ''
            summary = _get_artifact_dict_summary(art)
            text_lines.append(f'  • `{art_id}` {phase_str} - {summary}')
        if len(type_artifacts) > 10:
            text_lines.append(f'  _... and {len(type_artifacts) - 10} more_')
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(text_lines)}})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'Binder: `{binder_id[:8]}` | Use `@bot workbinder artifact <id>` for details'}]})
    return blocks

async def _handle_artifact(client: AgentClient, artifact_id: str) -> WorkbinderResponse:
    response = await client.list_binders(limit=100)
    binders = response.get('binders', [])
    for b in binders:
        b_id = b.get('binder_id', b.get('id', ''))
        art_response = await client.query_binder_artifacts(b_id, limit=1000)
        artifacts = art_response.get('artifacts', [])
        for artifact in artifacts:
            if artifact.get('id') == artifact_id:
                blocks = _format_artifact_detail_from_dict(artifact)
                file_content = _format_artifact_file_content_from_dict(artifact)
                art_type = artifact.get('artifact_type', 'unknown')
                return WorkbinderResponse(blocks=blocks, file_content=file_content, file_name=f'artifact_{artifact_id[:8]}.md', file_title=f'Artifact {artifact_id[:8]} ({art_type})')
    return _error_response(f'Artifact not found: {artifact_id}')

async def _handle_artifact_all(client: AgentClient, binder_id: str, investigation_id: str, artifact_type: str | None, phase: int | None, limit: int) -> WorkbinderResponse:
    response = await client.query_binder_artifacts(binder_id, artifact_type=artifact_type, phase=phase, limit=limit)
    artifacts = response.get('artifacts', [])
    if not artifacts:
        return _error_response('No artifacts found matching criteria')
    lines = [f'# All Artifacts for Investigation {investigation_id[:8]}', '', f'**Binder ID:** `{binder_id}`', f'**Total Artifacts:** {len(artifacts)}', '']
    type_counts: dict[str, int] = {}
    for a in artifacts:
        t = a.get('artifact_type', 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1
    lines.append('## Summary by Type')
    lines.append('')
    lines.append('| Type | Count |')
    lines.append('|------|-------|')
    for t, count in sorted(type_counts.items()):
        lines.append(f'| {t} | {count} |')
    lines.append('')
    lines.append('---')
    lines.append('')
    for artifact in artifacts:
        lines.append(_format_artifact_file_content_from_dict(artifact))
        lines.append('')
        lines.append('---')
        lines.append('')
    file_content = '\n'.join(lines)
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'All Artifacts: {investigation_id[:8]}'}}, {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*Total:* {len(artifacts)} artifacts\n' + '\n'.join((f'• `{t}`: {c}' for t, c in sorted(type_counts.items())))}}, {'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': ':page_facing_up: Full content attached as markdown file'}]}]
    return WorkbinderResponse(blocks=blocks, file_content=file_content, file_name=f'artifacts_{investigation_id[:8]}_all.md', file_title=f'All Artifacts for {investigation_id[:8]}')

async def _handle_search(client: AgentClient, binder_id: str, query: str, artifact_types: str | None) -> list[dict]:
    type_list = [artifact_types] if artifact_types else None
    response = await client.search_binder_artifacts(binder_id, query, type_list)
    artifacts = response.get('artifacts', [])
    if not artifacts:
        return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'_No artifacts found matching: {query}_'}}]
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'Search: "{query}" ({len(artifacts)} results)'}}]
    for artifact in artifacts[:15]:
        summary = _get_artifact_dict_summary(artifact)
        art_type = artifact.get('artifact_type', 'unknown')
        art_id = artifact.get('id', '')[:8]
        art_phase = artifact.get('phase')
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f"`{art_type}` | `{art_id}` | P{art_phase or '?'}\n  {summary}"}})
    if len(artifacts) > 15:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'_Showing 15 of {len(artifacts)} results_'}]})
    return blocks

async def _handle_history(client: AgentClient, binder_id: str, limit: int) -> list[dict]:
    try:
        await client.get_binder(binder_id)
    except Exception:
        return _error_blocks(f'Binder not found: {binder_id}')
    entries = await client.get_binder_audit_log(binder_id, limit=limit)
    if not entries:
        return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_No history entries found_'}}]
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'History for {binder_id[:8]}'}}]
    history_text = ''
    for entry in entries[-20:]:
        operation = entry.get('operation_type', 'unknown')
        persona = entry.get('persona_name', 'unknown')
        artifact_id = entry.get('artifact_id', '')
        art_id_short = artifact_id[:8] if artifact_id else 'N/A'
        timestamp = entry.get('timestamp', '')
        if isinstance(timestamp, str) and len(timestamp) > 16:
            timestamp = timestamp[:16].replace('T', ' ')
        history_text += f'• `{operation}` by {persona} on `{art_id_short}` at {timestamp}\n'
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': history_text or '_No entries_'}})
    return blocks

async def _handle_audit(client: AgentClient, binder_id: str, persona: str | None, phase: int | None, limit: int) -> list[dict]:
    entries = await client.get_binder_audit_log(binder_id, persona_name=persona, phase_number=phase, limit=limit)
    if not entries:
        return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': '_No audit log entries found_'}}]
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'Audit Log ({len(entries)} entries)'}}]
    text_lines = []
    for entry in entries[:30]:
        op_type = entry.get('operation_type', '')
        op_emoji = ':inbox_tray:' if op_type == 'store' else ':outbox_tray:'
        timestamp = entry.get('timestamp', '')
        if isinstance(timestamp, str) and 'T' in timestamp:
            time_str = timestamp.split('T')[1][:8]
        elif isinstance(timestamp, str) and ' ' in timestamp:
            time_str = timestamp.split(' ')[1][:8]
        else:
            time_str = str(timestamp)[:8]
        phase_num = entry.get('phase_number')
        text_lines.append(f"{op_emoji} `{time_str}` P{phase_num or '?'} | {entry.get('persona_name', '')} | `{entry.get('method_name', '')}` | {entry.get('artifact_type', '')} ({entry.get('result_count', 0)})")
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(text_lines) or '_No entries_'}})
    if len(entries) > 30:
        blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'_Showing 30 of {len(entries)} entries_'}]})
    blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': f'Binder: `{binder_id[:8]}`'}]})
    return blocks

def _error_response(message: str) -> WorkbinderResponse:
    blocks: list[dict[str, Any]] = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':x: *Error:* {message}'}}]
    return WorkbinderResponse(blocks=blocks)

def _error_blocks(message: str) -> list[dict]:
    return [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f':x: *Error:* {message}'}}]

def _truncate(text: str, max_len: int=200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + '...'

def _get_artifact_dict_summary(artifact: dict) -> str:
    art_type = artifact.get('artifact_type', '')
    content = artifact.get('content', {})
    if art_type == 'hypothesis':
        return _truncate(content.get('description', ''), 60)
    elif art_type == 'evidence':
        strength = content.get('strength', '')
        text = content.get('content', '')
        return f'[{strength}] {_truncate(text, 50)}'
    elif art_type == 'finding':
        return _truncate(content.get('content', ''), 60)
    elif art_type == 'code_snippet':
        fp = content.get('file_path', '')
        sl = content.get('start_line', '')
        return f'`{fp}:{sl}`'
    elif art_type == 'call_graph':
        return f"`{content.get('center_function', '')}()` call graph"
    elif art_type == 'llm_request':
        return f"{content.get('persona', '')} - {content.get('prompt_key', '')}"
    elif art_type == 'llm_response':
        tokens = content.get('tokens_used', 0) or 0
        latency = content.get('latency_ms', 0) or 0
        return f'{tokens} tokens, {latency:.0f}ms'
    elif art_type == 'error_context':
        return _truncate(content.get('error_message', ''), 60)
    elif art_type == 'source_location':
        fp = content.get('file_path', '')
        ln = content.get('line_number', '')
        return f'`{fp}:{ln}`'
    else:
        return str(art_type)

def _format_artifact_detail_from_dict(artifact: dict) -> list[dict]:
    art_id = artifact.get('id', '')
    art_type = artifact.get('artifact_type', 'unknown')
    content = artifact.get('content', {})
    blocks: list[dict[str, Any]] = [{'type': 'header', 'text': {'type': 'plain_text', 'text': f'Artifact: {art_id[:16]}'}}]
    phase = artifact.get('phase')
    info_text = f"*Type:* `{art_type}`\n*Created by:* {artifact.get('created_by', 'N/A')}\n*Phase:* {(phase if phase is not None else 'N/A')}\n*Created:* {artifact.get('created_at', 'N/A')}\n"
    tags = artifact.get('tags', [])
    if tags:
        info_text += f"*Tags:* {', '.join(tags)}\n"
    blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': info_text}})
    blocks.append({'type': 'divider'})
    if art_type == 'hypothesis':
        text = f"*Description:*\n{content.get('description', '')}\n\n*Source:* {content.get('source', '')}\n*Score:* {content.get('score', 0):.2f}\n*Prior Probability:* {content.get('prior_probability', 0):.2f}\n"
        supp = content.get('supporting_evidence_ids', [])
        if supp:
            text += f'*Supporting Evidence:* {len(supp)} items\n'
        contra = content.get('contradicting_evidence_ids', [])
        if contra:
            text += f'*Contradicting Evidence:* {len(contra)} items\n'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    elif art_type == 'evidence':
        text = f"*Type:* {content.get('evidence_type', '')}\n*Strength:* {content.get('strength', '')}\n*Source:* {content.get('source', '')}\n\n*Content:*\n{_truncate(content.get('content', ''), 500)}\n"
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    elif art_type == 'code_snippet':
        fp = content.get('file_path', '')
        sl = content.get('start_line', '')
        el = content.get('end_line', '')
        text = f'*File:* `{fp}`\n*Lines:* {sl}-{el}\n'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
        code = _truncate(content.get('content', ''), 2000)
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'```\n{code}\n```'}})
    elif art_type == 'llm_request':
        text = f"*Persona:* {content.get('persona', '')}\n*Prompt Key:* {content.get('prompt_key', '')}\n*Model:* {content.get('model', '')}\n*Temperature:* {content.get('temperature', '')}\n"
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
        sys_prompt = content.get('system_prompt', '')
        if sys_prompt:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*System Prompt:*\n```\n{_truncate(sys_prompt, 800)}\n```'}})
        user_prompt = content.get('user_prompt', '')
        if user_prompt:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*User Prompt:*\n```\n{_truncate(user_prompt, 800)}\n```'}})
    elif art_type == 'llm_response':
        req_id = content.get('linked_request_id', '')
        req_id_short = req_id[:8] if req_id else 'N/A'
        latency = content.get('latency_ms', 0) or 0
        text = f"*Request ID:* `{req_id_short}`\n*Tokens Used:* {content.get('tokens_used', 'N/A')}\n*Latency:* {latency:.0f}ms\n*Parse Success:* {('Yes' if content.get('parse_success') else 'No')}\n"
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
        raw = content.get('raw_response', '')
        if raw:
            blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*Response:*\n```\n{_truncate(raw, 1500)}\n```'}})
    else:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'_Artifact type `{art_type}` details not available_'}})
    return blocks

def _format_artifact_file_content_from_dict(artifact: dict) -> str:
    art_id = artifact.get('id', '')
    art_type = artifact.get('artifact_type', 'unknown')
    content = artifact.get('content', {})
    lines = [f'# Artifact: {art_id}', '', '## Metadata', '', '| Field | Value |', '|-------|-------|', f'| **Type** | `{art_type}` |', f"| **Created by** | {artifact.get('created_by', 'N/A')} |", f"| **Phase** | {(artifact.get('phase') if artifact.get('phase') is not None else 'N/A')} |", f"| **Created** | {artifact.get('created_at', 'N/A')} |", f"| **Updated** | {artifact.get('updated_at', 'N/A')} |"]
    tags = artifact.get('tags', [])
    if tags:
        lines.append(f"| **Tags** | {', '.join((f'`{t}`' for t in tags))} |")
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## Content')
    lines.append('')
    if art_type == 'hypothesis':
        lines.append('### Description')
        lines.append('')
        lines.append(content.get('description', ''))
        lines.append('')
        lines.append(f"**Source:** {content.get('source', '')}")
        lines.append(f"**Score:** {content.get('score', 0):.4f}")
        lines.append(f"**Prior Probability:** {content.get('prior_probability', 0):.4f}")
        supp = content.get('supporting_evidence_ids', [])
        if supp:
            lines.append('')
            lines.append('### Supporting Evidence')
            lines.append('')
            for eid in supp:
                lines.append(f'- `{eid}`')
        contra = content.get('contradicting_evidence_ids', [])
        if contra:
            lines.append('')
            lines.append('### Contradicting Evidence')
            lines.append('')
            for eid in contra:
                lines.append(f'- `{eid}`')
    elif art_type == 'evidence':
        lines.append(f"**Evidence Type:** {content.get('evidence_type', '')}")
        lines.append(f"**Strength:** {content.get('strength', '')}")
        lines.append(f"**Source:** {content.get('source', '')}")
        lines.append('')
        lines.append('### Content')
        lines.append('')
        lines.append(content.get('content', ''))
    elif art_type == 'finding':
        lines.append(f"**Finding Type:** {content.get('finding_type', '')}")
        lines.append(f"**Persona:** {content.get('persona', '')}")
        lines.append(f"**Confidence:** {content.get('confidence', 0):.4f}")
        lines.append('')
        lines.append('### Content')
        lines.append('')
        lines.append(content.get('content', ''))
    elif art_type == 'code_snippet':
        lines.append(f"**File:** `{content.get('file_path', '')}`")
        lines.append(f"**Lines:** {content.get('start_line', '')}-{content.get('end_line', '')}")
        lines.append('')
        lines.append('### Code')
        lines.append('')
        lines.append('```cpp')
        lines.append(content.get('content', ''))
        lines.append('```')
    elif art_type == 'call_graph':
        lines.append(f"**Center Function:** `{content.get('center_function', '')}()`")
        lines.append('')
        callers = content.get('callers', [])
        if callers:
            lines.append(f'### Callers ({len(callers)})')
            lines.append('')
            for c in callers:
                name = c.get('caller_name', '') if isinstance(c, dict) else str(c)
                lines.append(f'- `{name}()`')
            lines.append('')
        callees = content.get('callees', [])
        if callees:
            lines.append(f'### Callees ({len(callees)})')
            lines.append('')
            for c in callees:
                name = c.get('callee_name', '') if isinstance(c, dict) else str(c)
                lines.append(f'- `{name}()`')
            lines.append('')
        diagram = content.get('diagram', '')
        if diagram:
            lines.append('### Diagram')
            lines.append('')
            lines.append('```')
            lines.append(diagram)
            lines.append('```')
    elif art_type == 'llm_request':
        lines.append(f"**Persona:** {content.get('persona', '')}")
        lines.append(f"**Prompt Key:** {content.get('prompt_key', '')}")
        lines.append(f"**Model:** {content.get('model', '')}")
        lines.append(f"**Temperature:** {content.get('temperature', '')}")
        lines.append('')
        sys_prompt = content.get('system_prompt', '')
        if sys_prompt:
            lines.append('### System Prompt')
            lines.append('')
            lines.append('```')
            lines.append(sys_prompt)
            lines.append('```')
            lines.append('')
        user_prompt = content.get('user_prompt', '')
        if user_prompt:
            lines.append('### User Prompt')
            lines.append('')
            lines.append('```')
            lines.append(user_prompt)
            lines.append('```')
    elif art_type == 'llm_response':
        req_id = content.get('linked_request_id', 'N/A')
        lines.append(f'**Request ID:** `{req_id}`')
        lines.append(f"**Tokens Used:** {content.get('tokens_used', 'N/A')}")
        latency = content.get('latency_ms', 0) or 0
        lines.append(f'**Latency:** {latency:.0f}ms')
        lines.append(f"**Parse Success:** {('Yes' if content.get('parse_success') else 'No')}")
        lines.append('')
        raw = content.get('raw_response', '')
        if raw:
            lines.append('### Raw Response')
            lines.append('')
            lines.append('```')
            lines.append(raw)
            lines.append('```')
    elif art_type == 'error_context':
        lines.append('### Error Message')
        lines.append('')
        lines.append('```')
        lines.append(content.get('error_message', ''))
        lines.append('```')
        lines.append('')
        lines.append(f"**Error Level:** {content.get('error_level', '')}")
        context_logs = content.get('context_logs', [])
        if context_logs:
            lines.append('')
            lines.append(f'### Context Logs ({len(context_logs)})')
            lines.append('')
            for log in context_logs:
                lines.append(f'- {log}')
    elif art_type == 'source_location':
        lines.append(f"**File:** `{content.get('file_path', '')}`")
        lines.append(f"**Line:** {content.get('line_number', '')}")
        lines.append(f"**Match Score:** {content.get('match_score', 0):.4f}")
        func_name = content.get('function_name', '')
        if func_name:
            lines.append(f'**Function:** `{func_name}`')
    else:
        lines.append(f'*Raw artifact type: `{art_type}`*')
        lines.append('')
        try:
            lines.append('```json')
            lines.append(json.dumps(content, indent=2, default=str))
            lines.append('```')
        except Exception:
            lines.append('*(Could not serialize content)*')
    return '\n'.join(lines)

def _help_blocks() -> list[dict]:
    return [{'type': 'header', 'text': {'type': 'plain_text', 'text': 'Workbinder Commands'}}, {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '''*Available subcommands:*
â¢ `list [limit=N]` - List all binders
â¢ `show <id>` - Show binder details
â¢ `artifacts <id> [type=T] [phase=N]` - List artifacts
â¢ `artifact <artifact_id>` - View single artifact
â¢ `artifact all inv=<id> [type=T] [phase=N]` - Export all artifacts
â¢ `search <id> "query"` - Search artifacts
â¢ `history <id> [limit=N]` - View modification history
â¢ `audit <id> [persona=P]` - View audit log
'''}}, {'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': ':bulb: `<id>` can be either a binder ID or investigation ID'}]}]