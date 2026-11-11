"""
File: artifact_renderer.py
Purpose: Artifact Renderer - Verbatim rendering of binder artifacts for LLM ...
Category: Utility
Author: artdaq team
Depends: None
Exports: render_hypothesis, render_evidence, render_causal_chain, render_challenge, render_code_snippet, ...
Complexity: Medium | Lines: 251
"""

from __future__ import annotations
from collections.abc import Callable
from typing import Any
from .artifacts_types import Artifact, ArtifactType, CallGraphNode, CausalChainArtifact, ChallengeArtifact, CodeSnippet, ConclusionArtifact, ErrorContextArtifact, EvidenceArtifact, FeedbackArtifact, Finding, FunctionSummaryArtifact, HypothesisArtifact, LogBundleArtifact, MergedTimelineArtifact, PersonaContributionArtifact, SourceLocationArtifact

def render_hypothesis(h: HypothesisArtifact) -> str:
    lines = [f'[{h.id}] HYPOTHESIS (rank #{h.rank}, score={h.score:.2f})', f'  Source: {h.source}', f'  Prior probability: {h.prior_probability:.2f}', f'  Description: {h.description}']
    if h.category:
        lines.append(f'  Category: {h.category}')
    if h.confirming_evidence:
        lines.append(f'  Confirming evidence: {h.confirming_evidence}')
    if h.refuting_evidence:
        lines.append(f'  Refuting evidence: {h.refuting_evidence}')
    if h.supporting_evidence_ids:
        lines.append(f"  Supporting evidence IDs: {', '.join(h.supporting_evidence_ids)}")
    if h.contradicting_evidence_ids:
        lines.append(f"  Contradicting evidence IDs: {', '.join(h.contradicting_evidence_ids)}")
    return '\n'.join(lines)

def render_evidence(e: EvidenceArtifact) -> str:
    lines = [f'[{e.id}] EVIDENCE [{e.strength}] ({e.evidence_type})', f'  Source: {e.source}', f'  Content: {e.content}']
    if e.targets_hypothesis_id:
        lines.append(f'  Targets hypothesis: {e.targets_hypothesis_id}')
    if e.expected_if_true:
        lines.append(f'  Expected if true: {e.expected_if_true}')
    if e.expected_if_false:
        lines.append(f'  Expected if false: {e.expected_if_false}')
    if not e.found:
        lines.append('  Found: NO (absence evidence)')
    if e.supports_hypothesis_ids:
        lines.append(f"  Supports: {', '.join(e.supports_hypothesis_ids)}")
    if e.contradicts_hypothesis_ids:
        lines.append(f"  Contradicts: {', '.join(e.contradicts_hypothesis_ids)}")
    return '\n'.join(lines)

def render_causal_chain(c: CausalChainArtifact) -> str:
    lines = [f'[{c.id}] CAUSAL CHAIN for hypothesis {c.hypothesis_id}', f'  Completeness: {c.completeness_score:.0%}', f'  Logical validity: {c.logical_validity:.0%}', f'  Evidence coverage: {c.evidence_coverage:.0%}']
    if c.steps:
        lines.append('  Steps:')
        for i, step in enumerate(c.steps, 1):
            step_data = step if isinstance(step, dict) else {'claim': str(step)}
            claim = step_data.get('claim', str(step_data))
            mechanism = step_data.get('mechanism', '')
            evidence_ids = step_data.get('evidence_ids', [])
            evidence_ref = ', '.join(evidence_ids) if evidence_ids else 'ASSUMPTION'
            lines.append(f'    {i}. {claim}')
            if mechanism:
                lines.append(f'       Mechanism: {mechanism}')
            lines.append(f'       Evidence: {evidence_ref}')
    if c.gaps:
        lines.append(f"  Gaps: {'; '.join(c.gaps)}")
    if c.assumptions:
        lines.append(f"  Assumptions: {'; '.join(c.assumptions)}")
    return '\n'.join(lines)

def render_challenge(ch: ChallengeArtifact) -> str:
    status = 'resolved' if ch.resolved else 'unresolved'
    lines = [f'[{ch.id}] CHALLENGE [{ch.severity}] ({status})', f'  Target hypothesis: {ch.target_hypothesis_id}', f'  Content: {ch.content}']
    if ch.resolution:
        lines.append(f'  Resolution: {ch.resolution}')
    return '\n'.join(lines)

def render_code_snippet(s: CodeSnippet) -> str:
    func_label = f' ({s.snippet_function_name})' if s.snippet_function_name else ''
    lines = [f'[{s.id}] CODE SNIPPET{func_label}', f'  File: {s.file_path}:{s.start_line}-{s.end_line}', f'```{s.language}', s.content, '```']
    if s.summary:
        lines.append(f'  Summary: {s.summary}')
    return '\n'.join(lines)

def render_function_summary(fs: FunctionSummaryArtifact) -> str:
    lines = [f'[{fs.id}] FUNCTION SUMMARY: {fs.function_name}()', f'  Role: {fs.role} of {fs.center_function}']
    if fs.file_path:
        lines.append(f'  File: {fs.file_path}')
    lines.extend([f'  Purpose: {fs.purpose}', f'  Mechanism: {fs.mechanism}', f'  Data flow: {fs.data_flow}', f'  Error paths: {fs.error_paths}', f'  Error line relevance: {fs.error_line_relevance}'])
    return '\n'.join(lines)

def render_call_graph(cg: CallGraphNode) -> str:
    lines = [f'[{cg.id}] CALL GRAPH: {cg.center_function}()', f'  Depth explored: {cg.depth_explored}']
    if cg.diagram:
        lines.append(f'  Diagram:\n{cg.diagram}')
    if cg.callers:
        lines.append('  Callers:')
        for caller in cg.callers:
            loc = f' ({caller.caller_file})' if caller.caller_file else ''
            lines.append(f'    - {caller.caller_name}(){loc}')
            if caller.summary:
                lines.append(f'      Summary: {caller.summary}')
            if caller.body:
                lines.append(f'      ```cpp\n{caller.body}\n      ```')
    if cg.callees:
        lines.append('  Callees:')
        for callee in cg.callees:
            loc = f' ({callee.callee_file})' if callee.callee_file else ''
            lines.append(f'    - {callee.callee_name}(){loc}')
            if callee.summary:
                lines.append(f'      Summary: {callee.summary}')
            if callee.body:
                lines.append(f'      ```cpp\n{callee.body}\n      ```')
    return '\n'.join(lines)

def render_finding(f: Finding) -> str:
    phase_str = f' [Phase {f.phase}]' if f.phase is not None else ''
    lines = [f'[{f.id}] FINDING{phase_str} [{f.persona}] ({f.finding_type.value})', f'  Confidence: {f.confidence:.0%}', f'  Content: {f.content}']
    if f.related_artifacts:
        lines.append(f"  Related artifacts: {', '.join(f.related_artifacts)}")
    return '\n'.join(lines)

def render_persona_contribution(pc: PersonaContributionArtifact) -> str:
    lines = [f'[{pc.id}] PERSONA CONTRIBUTION [{pc.persona_id}] (Phase {pc.contribution_phase})', f'  Confidence: {pc.confidence:.0%}']
    if pc.reasoning:
        lines.append(f'  Reasoning: {pc.reasoning}')
    if isinstance(pc.content, dict):
        for key, value in pc.content.items():
            lines.append(f'  {key}: {value}')
    else:
        lines.append(f'  Content: {pc.content}')
    return '\n'.join(lines)

def render_log_bundle(lb: LogBundleArtifact) -> str:
    lines = [f'[{lb.id}] LOG BUNDLE ({len(lb.source_files)} source files)']
    if lb.source_files:
        lines.append('  Source files:')
        for sf in lb.source_files:
            name = sf.get('filename', sf.get('name', 'unknown'))
            lines.append(f'    - {name}')
    if lb.primary_error:
        lines.append(f'  Primary error: [{lb.primary_error.level}] {lb.primary_error.message} ({lb.primary_error.filename})')
    if lb.annotated_narrative:
        lines.append(f'  Narrative:\n{lb.annotated_narrative}')
    if lb.cascade_description:
        lines.append(f'  Cascade: {lb.cascade_description}')
    if lb.affected_boards:
        lines.append(f'  Boards ({len(lb.affected_boards)}):')
        for b in lb.affected_boards:
            lines.append(f'    [{b.role}] {b.board_name}: {b.failure_mode}')
    if lb.cascade_chain:
        lines.append(f'  Cascade ({len(lb.cascade_chain)} links):')
        for link in lb.cascade_chain:
            lines.append(f'    {link.from_board} -> {link.to_board}: {link.mechanism}')
    if lb.error_timeline:
        lines.append('  Error timeline:')
        for err in lb.error_timeline:
            ts = err.timestamp.isoformat() if err.timestamp else '?'
            primary = ' [PRIMARY]' if err.is_primary else ''
            lines.append(f'    {ts} [{err.level}] {err.message}{primary}')
    if lb.clues:
        lines.append('  Clues:')
        for clue in lb.clues:
            lines.append(f'    - [{clue.relevance}] ({clue.clue_type}) {clue.description}')
    return '\n'.join(lines)

def render_merged_timeline(mt: MergedTimelineArtifact) -> str:
    lines = [f'[{mt.id}] MERGED TIMELINE ({mt.total_entries} entries, {mt.file_count} files)']
    if mt.earliest_timestamp or mt.latest_timestamp:
        lines.append(f'  Time range: {mt.earliest_timestamp} - {mt.latest_timestamp}')
    lines.append(f'  Counts: {mt.total_errors} errors, {mt.total_warnings} warnings, {mt.total_info} info')
    if mt.entries:
        lines.append('  Entries:')
        for entry in mt.entries:
            level_tag = entry.level.upper()
            board = f'[{entry.board_name}] ' if entry.board_name else ''
            loc = f' ({entry.source_location})' if entry.source_location else ''
            msg_lines = entry.message.split('\n') if entry.message else ['']
            lines.append(f'    {board}{entry.timestamp} {level_tag} {entry.component}: {msg_lines[0]}{loc}')
            for cont in msg_lines[1:]:
                if cont.strip():
                    lines.append(f'      {cont}')
    return '\n'.join(lines)

def render_conclusion(c: ConclusionArtifact) -> str:
    lines = [f'[{c.id}] CONCLUSION ({c.outcome})', f'  Root cause: {c.root_cause}', f'  Confidence (raw): {c.confidence_raw:.2f}', f'  Confidence (calibrated): {c.confidence_calibrated:.2f}']
    if c.code_location:
        lines.append(f'  Code location: {c.code_location}')
    if c.code_snippet:
        lines.append(f'  Code snippet:\n```\n{c.code_snippet}\n```')
    if c.data_flow:
        lines.append(f'  Data flow: {c.data_flow}')
    if c.caveats:
        lines.append('  Caveats:')
        for caveat in c.caveats:
            lines.append(f'    - {caveat}')
    if c.debugging_steps:
        lines.append('  Debugging steps:')
        for step in c.debugging_steps:
            lines.append(f'    - {step}')
    if c.unresolved_challenges:
        lines.append('  Unresolved challenges:')
        for uc in c.unresolved_challenges:
            lines.append(f'    - {uc}')
    return '\n'.join(lines)

def render_error_context(ec: ErrorContextArtifact) -> str:
    lines = [f'[{ec.id}] ERROR CONTEXT', f'  Message: {ec.error_message}', f'  Level: {ec.error_level}']
    if ec.error_component:
        lines.append(f'  Component: {ec.error_component}')
    if ec.error_function:
        lines.append(f'  Function: {ec.error_function}')
    if ec.error_timestamp:
        lines.append(f'  Timestamp: {ec.error_timestamp.isoformat()}')
    if ec.context_logs:
        lines.append('  Context logs:')
        for log_entry in ec.context_logs:
            if isinstance(log_entry, dict):
                msg = log_entry.get('message', str(log_entry))
                lines.append(f'    - {msg}')
            else:
                lines.append(f'    - {log_entry}')
    return '\n'.join(lines)

def render_feedback(fb: FeedbackArtifact) -> str:
    verdict = 'CORRECT' if fb.was_correct else 'INCORRECT'
    lines = [f'[{fb.id}] FEEDBACK ({verdict})', f'  Investigation: {fb.investigation_id}', f'  Source: {fb.feedback_source}']
    if fb.user_id:
        lines.append(f'  User: {fb.user_id}')
    if fb.actual_cause:
        lines.append(f'  Actual cause: {fb.actual_cause}')
    if fb.what_was_helpful:
        lines.append(f'  What was helpful: {fb.what_was_helpful}')
    if fb.what_was_wrong:
        lines.append(f'  What was wrong: {fb.what_was_wrong}')
    if fb.suggestions:
        lines.append(f'  Suggestions: {fb.suggestions}')
    if fb.additional_notes:
        lines.append(f'  Notes: {fb.additional_notes}')
    return '\n'.join(lines)

def render_source_location(sl: SourceLocationArtifact) -> str:
    score_pct = int(sl.match_score * 100)
    lines = [f'[{sl.id}] SOURCE LOCATION ({score_pct}% match)', f'  File: {sl.file_path}:{sl.line_number}']
    if sl.matched_line:
        lines.append(f'  Matched line: {sl.matched_line}')
    if sl.function_signature:
        lines.append(f'  Function: {sl.function_signature}')
    if sl.function_body:
        lines.append(f'  Function body:\n```cpp\n{sl.function_body}\n```')
    if sl.context_before:
        lines.append('  Context before:')
        for ctx_line in sl.context_before:
            lines.append(f'    {ctx_line}')
    if sl.context_after:
        lines.append('  Context after:')
        for ctx_line in sl.context_after:
            lines.append(f'    {ctx_line}')
    return '\n'.join(lines)
_RENDERERS: dict[ArtifactType, Callable[[Any], str]] = {ArtifactType.HYPOTHESIS_ARTIFACT: render_hypothesis, ArtifactType.EVIDENCE_ARTIFACT: render_evidence, ArtifactType.CAUSAL_CHAIN: render_causal_chain, ArtifactType.CHALLENGE: render_challenge, ArtifactType.CODE_SNIPPET: render_code_snippet, ArtifactType.FUNCTION_SUMMARY: render_function_summary, ArtifactType.CALL_GRAPH: render_call_graph, ArtifactType.FINDING: render_finding, ArtifactType.PERSONA_CONTRIBUTION: render_persona_contribution, ArtifactType.LOG_BUNDLE: render_log_bundle, ArtifactType.MERGED_TIMELINE: render_merged_timeline, ArtifactType.CONCLUSION: render_conclusion, ArtifactType.FEEDBACK: render_feedback, ArtifactType.ERROR_CONTEXT: render_error_context, ArtifactType.SOURCE_LOCATION: render_source_location}

def render_artifact(artifact: Artifact) -> str:
    renderer = _RENDERERS.get(artifact.artifact_type)
    if renderer:
        return renderer(artifact)
    return f'[{artifact.id}] {artifact.artifact_type.value.upper()} (phase {artifact.phase})'