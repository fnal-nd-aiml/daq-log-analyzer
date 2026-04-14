"""
File: binder_formatter.py
Purpose: Slack mrkdwn formatting for workbinder data.
Category: Utility
Author: artdaq team
Depends: None
Exports: truncate, format_binder_list, format_binder_detail, format_artifact_list, format_artifact_detail, ...
Complexity: Medium | Lines: 499
"""

from typing import Any

SlackBlock = dict[str, Any]


def _context_block(text: str) -> SlackBlock:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def format_binder_list(binders: list[dict[str, Any]]) -> list[SlackBlock]:
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Work Binders ({len(binders)})"}}]
    if not binders:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_No binders found_"}})
        return blocks
    text_lines = []
    for b in binders[:20]:
        binder_id = b["id"][:8]
        inv_id = b.get("investigation_id", "")[:8]
        status = b.get("status", "unknown")
        count = b.get("artifact_count", 0)
        if status == "completed":
            status_emoji = ":white_check_mark:"
        elif status == "active":
            status_emoji = ":hourglass:"
        elif status == "paused":
            status_emoji = ":pause_button:"
        else:
            status_emoji = ":question:"
        text_lines.append(f"{status_emoji} `{binder_id}` | inv: `{inv_id}` | {count} artifacts")
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(text_lines)}})
    blocks.append(_context_block("Use `@bot workbinder show <id>` for details"))
    return blocks


def format_binder_detail(binder: dict[str, Any], artifact_counts: dict[str, int], audit_count: int) -> list[SlackBlock]:
    binder_id = binder.get("id", "")
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Binder: {binder_id[:16]}"}}]
    state = binder.get("investigation_state", {})
    current_phase = state.get("current_phase", 0) if state else 0
    outcome = state.get("outcome", "N/A") if state else "N/A"
    investigation_id = binder.get("investigation_id", "")
    status = binder.get("status", "unknown")
    created_at = binder.get("created_at", "")
    updated_at = binder.get("updated_at", "")
    if hasattr(created_at, "strftime"):
        created_at = created_at.strftime("%Y-%m-%d %H:%M")
    if hasattr(updated_at, "strftime"):
        updated_at = updated_at.strftime("%Y-%m-%d %H:%M")
    info_text = f"*Investigation ID:* `{investigation_id}`\n*Status:* {status}\n*Current Phase:* {current_phase}\n*Outcome:* {outcome}\n*Created:* {created_at}\n*Updated:* {updated_at}\n"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": info_text}})
    blocks.append({"type": "divider"})
    if artifact_counts:
        breakdown_text = "*Artifacts by Type:*\n"
        for art_type, count in sorted(artifact_counts.items()):
            breakdown_text += f"• `{art_type}`: {count}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": breakdown_text}})
    blocks.append(_context_block(f"Audit log entries: {audit_count}"))
    return blocks


def format_artifact_list(artifacts: list[dict[str, Any]], binder_id: str) -> list[SlackBlock]:
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Artifacts ({len(artifacts)})"}}]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        type_name = artifact.get("artifact_type", "unknown")
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(artifact)
    for type_name, type_artifacts in sorted(by_type.items()):
        text_lines = [f"*{type_name}* ({len(type_artifacts)}):"]
        for art in type_artifacts[:10]:
            summary = _get_artifact_summary(art)
            phase = art.get("phase")
            phase_str = f"P{phase}" if phase is not None else ""
            art_id = art.get("id", "")[:8]
            text_lines.append(f"  • `{art_id}` {phase_str} - {summary}")
        if len(type_artifacts) > 10:
            text_lines.append(f"  _... and {len(type_artifacts) - 10} more_")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(text_lines)}})
    blocks.append(_context_block(f"Binder: `{binder_id[:8]}` | Use `@bot workbinder artifact <id>` for details"))
    return blocks


def _get_artifact_summary(artifact: dict[str, Any]) -> str:
    artifact_type = artifact.get("artifact_type", "")
    if artifact_type == "hypothesis":
        return truncate(artifact.get("description", ""), 60)
    elif artifact_type == "evidence":
        strength = artifact.get("strength", "")
        content = artifact.get("content", "")
        return f"[{strength}] {truncate(content, 50)}"
    elif artifact_type == "finding":
        return truncate(artifact.get("content", ""), 60)
    elif artifact_type == "code_snippet":
        file_path = artifact.get("file_path", "")
        start_line = artifact.get("start_line", "")
        return f"`{file_path}:{start_line}`"
    elif artifact_type == "call_graph":
        center_function = artifact.get("center_function", "")
        return f"`{center_function}()` call graph"
    elif artifact_type == "llm_request":
        persona = artifact.get("persona", "")
        prompt_key = artifact.get("prompt_key", "")
        return f"{persona} - {prompt_key}"
    elif artifact_type == "llm_response":
        tokens = artifact.get("tokens_used") or 0
        latency = artifact.get("latency_ms", 0)
        return f"{tokens} tokens, {latency:.0f}ms"
    elif artifact_type == "error_context":
        return truncate(artifact.get("error_message", ""), 60)
    elif artifact_type == "source_location":
        file_path = artifact.get("file_path", "")
        line_number = artifact.get("line_number", "")
        return f"`{file_path}:{line_number}`"
    else:
        return artifact_type


def format_artifact_detail(artifact: dict[str, Any]) -> list[SlackBlock]:
    artifact_id = artifact.get("id", "")
    artifact_type = artifact.get("artifact_type", "unknown")
    created_by = artifact.get("created_by", "")
    phase = artifact.get("phase")
    created_at = artifact.get("created_at", "")
    tags = artifact.get("tags", [])
    if hasattr(created_at, "strftime"):
        created_at = created_at.strftime("%Y-%m-%d %H:%M")
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Artifact: {artifact_id[:16]}"}}]
    info_text = f"*Type:* `{artifact_type}`\n*Created by:* {created_by}\n*Phase:* {(phase if phase is not None else 'N/A')}\n*Created:* {created_at}\n"
    if tags:
        info_text += f"*Tags:* {', '.join(tags)}\n"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": info_text}})
    blocks.append({"type": "divider"})
    content_blocks = _format_artifact_content(artifact)
    blocks.extend(content_blocks)
    return blocks


def _format_artifact_content(artifact: dict[str, Any]) -> list[SlackBlock]:
    blocks: list[SlackBlock] = []
    artifact_type = artifact.get("artifact_type", "")
    if artifact_type == "hypothesis":
        description = artifact.get("description", "")
        source = artifact.get("source", "")
        score = artifact.get("score", 0)
        prior_probability = artifact.get("prior_probability", 0)
        supporting = artifact.get("supporting_evidence_ids", [])
        contradicting = artifact.get("contradicting_evidence_ids", [])
        text = f"*Description:*\n{description}\n\n*Source:* {source}\n*Score:* {score:.2f}\n*Prior Probability:* {prior_probability:.2f}\n"
        if supporting:
            text += f"*Supporting Evidence:* {len(supporting)} items\n"
        if contradicting:
            text += f"*Contradicting Evidence:* {len(contradicting)} items\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    elif artifact_type == "evidence":
        evidence_type = artifact.get("evidence_type", "")
        strength = artifact.get("strength", "")
        source = artifact.get("source", "")
        content = artifact.get("content", "")
        text = f"*Type:* {evidence_type}\n*Strength:* {strength}\n*Source:* {source}\n\n*Content:*\n{truncate(content, 500)}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    elif artifact_type == "finding":
        finding_type = artifact.get("finding_type", "")
        persona = artifact.get("persona", "")
        confidence = artifact.get("confidence", 0)
        content = artifact.get("content", "")
        text = f"*Type:* {finding_type}\n*Persona:* {persona}\n*Confidence:* {confidence:.2f}\n\n*Content:*\n{truncate(content, 500)}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
    elif artifact_type == "code_snippet":
        file_path = artifact.get("file_path", "")
        start_line = artifact.get("start_line", "")
        end_line = artifact.get("end_line", "")
        content = artifact.get("content", "")
        text = f"*File:* `{file_path}`\n*Lines:* {start_line}-{end_line}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        code = truncate(content, 2000)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"```\n{code}\n```"}})
    elif artifact_type == "call_graph":
        center_function = artifact.get("center_function", "")
        callers = artifact.get("callers", [])
        callees = artifact.get("callees", [])
        diagram = artifact.get("diagram", "")
        text = f"*Center Function:* `{center_function}()`\n"
        if callers:
            caller_names = [c.get("caller_name", "") if isinstance(c, dict) else str(c) for c in callers[:5]]
            text += f"*Callers:* {', '.join(caller_names)}\n"
        if callees:
            callee_names = [c.get("callee_name", "") if isinstance(c, dict) else str(c) for c in callees[:5]]
            text += f"*Callees:* {', '.join(callee_names)}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        if diagram:
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": f"```\n{truncate(diagram, 1500)}\n```"}}
            )
    elif artifact_type == "llm_request":
        persona = artifact.get("persona", "")
        prompt_key = artifact.get("prompt_key", "")
        model = artifact.get("model", "")
        temperature = artifact.get("temperature", "")
        system_prompt = artifact.get("system_prompt", "")
        user_prompt = artifact.get("user_prompt", "")
        text = f"*Persona:* {persona}\n*Prompt Key:* {prompt_key}\n*Model:* {model}\n*Temperature:* {temperature}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        if system_prompt:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*System Prompt:*\n```\n{truncate(system_prompt, 800)}\n```"},
                }
            )
        if user_prompt:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*User Prompt:*\n```\n{truncate(user_prompt, 800)}\n```"},
                }
            )
    elif artifact_type == "llm_response":
        linked_request_id = artifact.get("linked_request_id", "")
        req_id = linked_request_id[:8] if linked_request_id else "N/A"
        tokens_used = artifact.get("tokens_used")
        latency_ms = artifact.get("latency_ms", 0)
        parse_success = artifact.get("parse_success", False)
        raw_response = artifact.get("raw_response", "")
        text = f"*Request ID:* `{req_id}`\n*Tokens Used:* {tokens_used or 'N/A'}\n*Latency:* {latency_ms:.0f}ms\n*Parse Success:* {('Yes' if parse_success else 'No')}\n"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        if raw_response:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Response:*\n```\n{truncate(raw_response, 1500)}\n```"},
                }
            )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"_Artifact type `{artifact_type}` details not available_"},
            }
        )
    return blocks


def format_search_results(artifacts: list[dict[str, Any]], query: str) -> list[SlackBlock]:
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f'Search: "{query}" ({len(artifacts)} results)'}}
    ]
    for artifact in artifacts[:15]:
        summary = _get_artifact_summary(artifact)
        artifact_type = artifact.get("artifact_type", "unknown")
        artifact_id = artifact.get("id", "")[:8]
        phase = artifact.get("phase")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"`{artifact_type}` | `{artifact_id}` | P{phase or '?'}\n  {summary}",
                },
            }
        )
    if len(artifacts) > 15:
        blocks.append(_context_block(f"_Showing 15 of {len(artifacts)} results_"))
    return blocks


def format_audit_log(entries: list[dict[str, Any]], binder_id: str) -> list[SlackBlock]:
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Audit Log ({len(entries)} entries)"}}]
    text_lines = []
    for entry in entries[:30]:
        operation_type = entry.get("operation_type", "")
        op_emoji = ":inbox_tray:" if operation_type == "store" else ":outbox_tray:"
        timestamp = entry.get("timestamp", "")
        if hasattr(timestamp, "strftime"):
            time_str = timestamp.strftime("%H:%M:%S")
        else:
            time_str = str(timestamp)
        phase_number = entry.get("phase_number")
        persona_name = entry.get("persona_name", "")
        method_name = entry.get("method_name", "")
        artifact_type = entry.get("artifact_type", "")
        result_count = entry.get("result_count", 0)
        text_lines.append(
            f"{op_emoji} `{time_str}` P{phase_number or '?'} | {persona_name} | `{method_name}` | {artifact_type} ({result_count})"
        )
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(text_lines) or "_No entries_"}})
    if len(entries) > 30:
        blocks.append(_context_block(f"_Showing 30 of {len(entries)} entries_"))
    blocks.append(_context_block(f"Binder: `{binder_id[:8]}`"))
    return blocks


def format_artifact_file_content(artifact: dict[str, Any]) -> str:
    artifact_id = artifact.get("id", "")
    artifact_type = artifact.get("artifact_type", "unknown")
    created_by = artifact.get("created_by", "")
    phase = artifact.get("phase")
    created_at = artifact.get("created_at", "")
    updated_at = artifact.get("updated_at", "")
    tags = artifact.get("tags", [])
    created_at_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else str(created_at)
    updated_at_str = updated_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(updated_at, "strftime") else str(updated_at)
    lines = [
        f"# Artifact: {artifact_id}",
        "",
        "## Metadata",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Type** | `{artifact_type}` |",
        f"| **Created by** | {created_by} |",
        f"| **Phase** | {(phase if phase is not None else 'N/A')} |",
        f"| **Created** | {created_at_str} |",
        f"| **Updated** | {updated_at_str} |",
    ]
    if tags:
        lines.append(f"| **Tags** | {', '.join((f'`{t}`' for t in tags))} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Content")
    lines.append("")
    if artifact_type == "hypothesis":
        description = artifact.get("description", "")
        source = artifact.get("source", "")
        score = artifact.get("score", 0)
        prior_probability = artifact.get("prior_probability", 0)
        supporting = artifact.get("supporting_evidence_ids", [])
        contradicting = artifact.get("contradicting_evidence_ids", [])
        lines.append("### Description")
        lines.append("")
        lines.append(description)
        lines.append("")
        lines.append(f"**Source:** {source}")
        lines.append(f"**Score:** {score:.4f}")
        lines.append(f"**Prior Probability:** {prior_probability:.4f}")
        if supporting:
            lines.append("")
            lines.append("### Supporting Evidence")
            lines.append("")
            for eid in supporting:
                lines.append(f"- `{eid}`")
        if contradicting:
            lines.append("")
            lines.append("### Contradicting Evidence")
            lines.append("")
            for eid in contradicting:
                lines.append(f"- `{eid}`")
    elif artifact_type == "evidence":
        evidence_type = artifact.get("evidence_type", "")
        strength = artifact.get("strength", "")
        source = artifact.get("source", "")
        content = artifact.get("content", "")
        lines.append(f"**Evidence Type:** {evidence_type}")
        lines.append(f"**Strength:** {strength}")
        lines.append(f"**Source:** {source}")
        lines.append("")
        lines.append("### Content")
        lines.append("")
        lines.append(content)
    elif artifact_type == "finding":
        finding_type = artifact.get("finding_type", "")
        persona = artifact.get("persona", "")
        confidence = artifact.get("confidence", 0)
        content = artifact.get("content", "")
        lines.append(f"**Finding Type:** {finding_type}")
        lines.append(f"**Persona:** {persona}")
        lines.append(f"**Confidence:** {confidence:.4f}")
        lines.append("")
        lines.append("### Content")
        lines.append("")
        lines.append(content)
    elif artifact_type == "code_snippet":
        file_path = artifact.get("file_path", "")
        start_line = artifact.get("start_line", "")
        end_line = artifact.get("end_line", "")
        content = artifact.get("content", "")
        lines.append(f"**File:** `{file_path}`")
        lines.append(f"**Lines:** {start_line}-{end_line}")
        lines.append("")
        lines.append("### Code")
        lines.append("")
        lines.append("```cpp")
        lines.append(content)
        lines.append("```")
    elif artifact_type == "call_graph":
        center_function = artifact.get("center_function", "")
        callers = artifact.get("callers", [])
        callees = artifact.get("callees", [])
        diagram = artifact.get("diagram", "")
        lines.append(f"**Center Function:** `{center_function}()`")
        lines.append("")
        if callers:
            lines.append(f"### Callers ({len(callers)})")
            lines.append("")
            for c in callers:
                caller_name = c.get("caller_name", "") if isinstance(c, dict) else str(c)
                lines.append(f"- `{caller_name}()`")
            lines.append("")
        if callees:
            lines.append(f"### Callees ({len(callees)})")
            lines.append("")
            for c in callees:
                callee_name = c.get("callee_name", "") if isinstance(c, dict) else str(c)
                lines.append(f"- `{callee_name}()`")
            lines.append("")
        if diagram:
            lines.append("### Diagram")
            lines.append("")
            lines.append("```")
            lines.append(diagram)
            lines.append("```")
    elif artifact_type == "llm_request":
        persona = artifact.get("persona", "")
        prompt_key = artifact.get("prompt_key", "")
        model = artifact.get("model", "")
        temperature = artifact.get("temperature", "")
        system_prompt = artifact.get("system_prompt", "")
        user_prompt = artifact.get("user_prompt", "")
        lines.append(f"**Persona:** {persona}")
        lines.append(f"**Prompt Key:** {prompt_key}")
        lines.append(f"**Model:** {model}")
        lines.append(f"**Temperature:** {temperature}")
        lines.append("")
        if system_prompt:
            lines.append("### System Prompt")
            lines.append("")
            lines.append("```")
            lines.append(system_prompt)
            lines.append("```")
            lines.append("")
        if user_prompt:
            lines.append("### User Prompt")
            lines.append("")
            lines.append("```")
            lines.append(user_prompt)
            lines.append("```")
    elif artifact_type == "llm_response":
        linked_request_id = artifact.get("linked_request_id", "")
        tokens_used = artifact.get("tokens_used")
        latency_ms = artifact.get("latency_ms", 0)
        parse_success = artifact.get("parse_success", False)
        raw_response = artifact.get("raw_response", "")
        lines.append(f"**Request ID:** `{linked_request_id or 'N/A'}`")
        lines.append(f"**Tokens Used:** {tokens_used or 'N/A'}")
        lines.append(f"**Latency:** {latency_ms:.0f}ms")
        lines.append(f"**Parse Success:** {('Yes' if parse_success else 'No')}")
        lines.append("")
        if raw_response:
            lines.append("### Raw Response")
            lines.append("")
            lines.append("```")
            lines.append(raw_response)
            lines.append("```")
    elif artifact_type == "error_context":
        error_message = artifact.get("error_message", "")
        error_level = artifact.get("error_level", "")
        context_logs = artifact.get("context_logs", [])
        lines.append("### Error Message")
        lines.append("")
        lines.append("```")
        lines.append(error_message)
        lines.append("```")
        lines.append("")
        lines.append(f"**Error Level:** {error_level}")
        if context_logs:
            lines.append("")
            lines.append(f"### Context Logs ({len(context_logs)})")
            lines.append("")
            for log in context_logs:
                lines.append(f"- {log}")
    elif artifact_type == "source_location":
        file_path = artifact.get("file_path", "")
        line_number = artifact.get("line_number", "")
        match_score = artifact.get("match_score", 0)
        function_name = artifact.get("function_name", "")
        lines.append(f"**File:** `{file_path}`")
        lines.append(f"**Line:** {line_number}")
        lines.append(f"**Match Score:** {match_score:.4f}")
        if function_name:
            lines.append(f"**Function:** `{function_name}`")
    else:
        lines.append(f"*Raw artifact type: `{artifact_type}`*")
        lines.append("")
        import json

        try:
            lines.append("```json")
            lines.append(json.dumps(artifact, indent=2, default=str))
            lines.append("```")
        except Exception:
            lines.append("*(Could not serialize content)*")
    return "\n".join(lines)
