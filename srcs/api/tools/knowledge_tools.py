"""
File: knowledge_tools.py
Purpose: Knowledge base tools for the agentic API.
Category: Utility
Author: artdaq team
Depends: dependencies, knowledge, llm, logs
Exports: match_pattern, find_similar_investigations, get_prior_knowledge
Complexity: Medium | Lines: 134
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
from srcs.models.logs import ErrorSignature, Log
from ..dependencies import get_storage_config
from ..errors import validation_error
from .router import ToolContext, register_tool

logger = logging.getLogger(__name__)


async def _get_kb() -> Any:
    from srcs.api.dependencies import get_settings

    settings = get_settings()
    storage_config = get_storage_config(settings)
    from srcs.api.dependencies import get_llm_config

    llm_config = get_llm_config(settings)
    from srcs.llm import create_llm_provider

    llm = create_llm_provider(llm_config)
    from srcs.knowledge import KnowledgeBase

    kb = KnowledgeBase(storage_config, llm)
    await kb.initialize()
    return kb


@register_tool("match_pattern")
async def match_pattern(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    message_pattern = params.get("message_pattern")
    if not message_pattern:
        raise validation_error("'message_pattern' is required for match_pattern.")
    signature = ErrorSignature(
        message_pattern=message_pattern,
        function=params.get("function"),
        level=params.get("level", "ERROR"),
        component=params.get("component"),
    )
    kb = await _get_kb()
    match = await kb.find_pattern(signature)
    if match is None:
        return {"match": None}
    return {
        "match": {
            "pattern_id": match.pattern.id,
            "confidence": match.confidence,
            "message_pattern": match.pattern.message_pattern,
            "typical_root_causes": [
                {"description": rc.description, "frequency": rc.frequency, "confidence": rc.confidence}
                for rc in (match.root_causes if hasattr(match, "root_causes") else [])
            ],
        }
    }


@register_tool("find_similar_investigations")
async def find_similar_investigations(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    error_message = params.get("error_message")
    if not error_message:
        parsed = ctx.session.state.parsed_logs
        if parsed:
            errors = [e for e in parsed if e.get("level") == "ERROR"]
            if errors:
                error_message = errors[0].get("message", "")
    if not error_message:
        raise validation_error("'error_message' is required (or parse_logs must have found errors).")
    error_log = Log(
        timestamp=datetime.now(),
        level=params.get("level", "ERROR"),
        component=params.get("component", "Unknown"),
        message=error_message,
    )
    context_logs: list[Log] = []
    n = params.get("n", 5)
    kb = await _get_kb()
    similar = await kb.find_similar_investigations(error_log, context_logs, n=n)
    return {
        "similar_investigations": [
            {
                "investigation_id": s.investigation_id,
                "similarity": s.similarity,
                "error_message": s.error_message if hasattr(s, "error_message") else None,
                "root_cause": s.root_cause if hasattr(s, "root_cause") else None,
                "outcome": s.outcome if hasattr(s, "outcome") else None,
            }
            for s in similar
        ],
        "total": len(similar),
    }


@register_tool("get_prior_knowledge")
async def get_prior_knowledge(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    error_message = params.get("error_message")
    if not error_message:
        parsed = ctx.session.state.parsed_logs
        if parsed:
            errors = [e for e in parsed if e.get("level") == "ERROR"]
            if errors:
                error_message = errors[0].get("message", "")
    if not error_message:
        raise validation_error("'error_message' is required (or parse_logs must have found errors).")
    error_log = Log(
        timestamp=datetime.now(),
        level=params.get("level", "ERROR"),
        component=params.get("component", "Unknown"),
        message=error_message,
    )
    context_logs: list[Log] = []
    kb = await _get_kb()
    prior = await kb.get_prior_knowledge(error_log, context_logs)
    return {
        "matched_patterns": [
            {"pattern_id": p.pattern.id, "confidence": p.confidence, "message_pattern": p.pattern.message_pattern}
            for p in prior.matched_patterns
        ],
        "similar_investigations": [
            {"investigation_id": s.investigation_id, "similarity": s.similarity} for s in prior.similar_investigations
        ],
        "recommended_hypotheses": [
            {"description": h.description, "source": h.source, "prior_probability": h.prior_probability}
            for h in prior.recommended_hypotheses
        ],
        "recommended_queries": [
            {"query_type": q.query_type, "parameters": q.parameters if hasattr(q, "parameters") else {}}
            for q in prior.recommended_queries
        ],
    }
