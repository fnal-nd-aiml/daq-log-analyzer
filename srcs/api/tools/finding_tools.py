"""
File: finding_tools.py
Purpose: Finding and hypothesis tools for the agentic API (session-state only).
Category: Utility
Author: artdaq team
Depends: None
Exports: record_finding, record_hypothesis, update_hypothesis, get_findings_summary
Complexity: Low | Lines: 61
"""

from __future__ import annotations
from typing import Any, cast
from ..errors import validation_error
from ..sessions import SessionFinding, SessionHypothesis
from .router import ToolContext, register_tool

@register_tool('record_finding')
async def record_finding(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    category = params.get('category')
    description = params.get('description')
    if not category or not description:
        raise validation_error("'category' and 'description' are required for record_finding.")
    finding = SessionFinding(category=category, description=description, severity=params.get('severity', 'medium'), evidence=params.get('evidence', []), source_tool=params.get('source_tool'))
    ctx.session.state.findings.append(finding)
    return {'finding_id': finding.id, 'total_findings': len(ctx.session.state.findings)}

@register_tool('record_hypothesis')
async def record_hypothesis(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    description = params.get('description')
    if not description:
        raise validation_error("'description' is required for record_hypothesis.")
    hypothesis = SessionHypothesis(description=description, confidence=params.get('confidence', 0.5), supporting_evidence=params.get('supporting_evidence', []), contradicting_evidence=params.get('contradicting_evidence', []))
    ctx.session.state.hypotheses.append(hypothesis)
    return {'hypothesis_id': hypothesis.id, 'total_hypotheses': len(ctx.session.state.hypotheses)}

@register_tool('update_hypothesis')
async def update_hypothesis(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get('params', {})
    hypothesis_id = params.get('hypothesis_id')
    if not hypothesis_id:
        raise validation_error("'hypothesis_id' is required for update_hypothesis.")
    target = None
    for h in ctx.session.state.hypotheses:
        if h.id == hypothesis_id:
            target = h
            break
    if target is None:
        raise validation_error(f"Hypothesis '{hypothesis_id}' not found in session.")
    if 'confidence' in params:
        target.confidence = params['confidence']
    if 'status' in params:
        target.status = params['status']
    if 'supporting_evidence' in params:
        target.supporting_evidence.extend(params['supporting_evidence'])
    if 'contradicting_evidence' in params:
        target.contradicting_evidence.extend(params['contradicting_evidence'])
    return {'hypothesis_id': target.id, 'confidence': target.confidence, 'status': target.status}

@register_tool('get_findings_summary')
async def get_findings_summary(ctx: ToolContext) -> dict[str, Any]:
    findings = ctx.session.state.findings
    hypotheses = ctx.session.state.hypotheses
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for f in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
    ranked_hypotheses = sorted([{'id': h.id, 'description': h.description, 'confidence': h.confidence, 'status': h.status, 'supporting_count': len(h.supporting_evidence), 'contradicting_count': len(h.contradicting_evidence)} for h in hypotheses], key=lambda x: cast(float, x['confidence']), reverse=True)
    return {'total_findings': len(findings), 'total_hypotheses': len(hypotheses), 'findings_by_category': by_category, 'findings_by_severity': by_severity, 'ranked_hypotheses': ranked_hypotheses, 'active_hypotheses': sum((1 for h in hypotheses if h.status == 'active'))}