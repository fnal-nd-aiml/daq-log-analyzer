"""
File: serializer.py
Purpose: Binder Serializer - Smart serialization for LLM prompts.
Category: Utility
Author: artdaq team
Depends: None
Exports: BinderSerializer
Complexity: Medium | Lines: 270
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from .artifact_renderer import render_artifact
from .artifacts import ArtifactType, CallGraphNode, CausalChainArtifact, ChallengeArtifact, CodeSnippet, ConclusionArtifact, ErrorContextArtifact, EvidenceArtifact, Finding, FunctionSummaryArtifact, HypothesisArtifact, LogBundleArtifact, PersonaContributionArtifact, SourceLocationArtifact
from .binder import WorkBinder
if TYPE_CHECKING:
    pass

class BinderSerializer:
    CHARS_PER_TOKEN = 4

    def serialize_for_prompt(self, binder: WorkBinder, persona: str | None=None, max_tokens: int=4000, focus_artifacts: list[str] | None=None, include_tool_instructions: bool=True, include_index: bool=True, include_recent_findings: bool=True) -> str:
        parts = []
        parts.append('=== WORK BINDER ===')
        parts.append('')
        parts.append('Investigation artifacts collected so far:')
        if include_tool_instructions:
            parts.append('Browse the index below and use tools to retrieve full content.')
        parts.append('')
        if focus_artifacts:
            focused = self._serialize_focused_artifacts(binder, focus_artifacts)
            if focused:
                parts.append('FOCUSED ARTIFACTS:')
                parts.append('-' * 40)
                parts.append(focused)
                parts.append('')
        if include_index:
            index = self._generate_index(binder)
            parts.append(index)
            parts.append('')
        if include_recent_findings:
            findings = self._serialize_recent_findings(binder, persona, limit=5)
            if findings:
                parts.append('RECENT FINDINGS FROM OTHER PERSONAS:')
                parts.append('-' * 40)
                parts.append(findings)
                parts.append('')
        if include_tool_instructions:
            parts.append(self._get_tool_instructions())
            parts.append('')
        return '\n'.join(parts)

    def _generate_index(self, binder: WorkBinder) -> str:
        counts = binder.count_by_type()
        total = sum(counts.values())
        lines = [f'BINDER INDEX ({total} artifacts):', '+' + '-' * 60 + '+']
        type_artifacts: dict[ArtifactType, list] = {}
        for artifact in binder._artifacts.values():
            if artifact.is_deleted:
                continue
            if artifact.artifact_type not in type_artifacts:
                type_artifacts[artifact.artifact_type] = []
            type_artifacts[artifact.artifact_type].append(artifact)
        if ArtifactType.CALL_GRAPH in type_artifacts:
            cgs = type_artifacts[ArtifactType.CALL_GRAPH]
            lines.append(f'| CALL GRAPHS ({len(cgs)})')
            for cg in cgs[:5]:
                if isinstance(cg, CallGraphNode):
                    callers = len(cg.callers)
                    callees = len(cg.callees)
                    lines.append(f'|   [{cg.id}] {cg.center_function}() - {callers} callers, {callees} callees')
            if len(cgs) > 5:
                lines.append(f'|   ... ({len(cgs) - 5} more)')
            lines.append('|' + '-' * 60)
        if ArtifactType.CODE_SNIPPET in type_artifacts:
            snippets = type_artifacts[ArtifactType.CODE_SNIPPET]
            lines.append(f'| CODE SNIPPETS ({len(snippets)})')
            for snippet in snippets[:5]:
                if isinstance(snippet, CodeSnippet):
                    fname = snippet.snippet_function_name or 'unknown'
                    loc = f'{snippet.file_path}:{snippet.start_line}-{snippet.end_line}'
                    lines.append(f'|   [{snippet.id}] {fname}() body - {loc}')
            if len(snippets) > 5:
                lines.append(f'|   ... ({len(snippets) - 5} more)')
            lines.append('|' + '-' * 60)
        if ArtifactType.FINDING in type_artifacts:
            findings = type_artifacts[ArtifactType.FINDING]
            lines.append(f'| FINDINGS ({len(findings)})')
            for finding in findings[:5]:
                if isinstance(finding, Finding):
                    persona_tag = f'[{finding.persona}]'
                    lines.append(f'|   [{finding.id}] {persona_tag} {finding.content}')
            if len(findings) > 5:
                lines.append(f'|   ... ({len(findings) - 5} more)')
            lines.append('|' + '-' * 60)
        if ArtifactType.SOURCE_LOCATION in type_artifacts:
            locations = type_artifacts[ArtifactType.SOURCE_LOCATION]
            lines.append(f'| SOURCE LOCATIONS ({len(locations)})')
            for loc in locations[:5]:
                if isinstance(loc, SourceLocationArtifact):
                    score_pct = int(loc.match_score * 100)
                    loc_str = f'{loc.file_path}:{loc.line_number}'
                    primary = 'primary' if score_pct > 80 else 'secondary'
                    lines.append(f'|   [{loc.id}] {loc_str} - {primary} match ({score_pct}%)')
            if len(locations) > 5:
                lines.append(f'|   ... ({len(locations) - 5} more)')
            lines.append('|' + '-' * 60)
        if ArtifactType.FUNCTION_SUMMARY in type_artifacts:
            fsums = type_artifacts[ArtifactType.FUNCTION_SUMMARY]
            lines.append(f'| FUNCTION SUMMARIES ({len(fsums)})')
            for fs in fsums[:5]:
                if isinstance(fs, FunctionSummaryArtifact):
                    role_tag = f'[{fs.role}]' if fs.role else ''
                    lines.append(f'|   [{fs.id}] {fs.function_name}() {role_tag} {fs.purpose}')
            if len(fsums) > 5:
                lines.append(f'|   ... ({len(fsums) - 5} more)')
            lines.append('|' + '-' * 60)
        if ArtifactType.ERROR_CONTEXT in type_artifacts:
            contexts = type_artifacts[ArtifactType.ERROR_CONTEXT]
            lines.append(f'| ERROR CONTEXT ({len(contexts)})')
            for ctx in contexts[:2]:
                if isinstance(ctx, ErrorContextArtifact):
                    lines.append(f'|   [{ctx.id}] {ctx.error_message}')
        if ArtifactType.PERSONA_CONTRIBUTION in type_artifacts:
            contribs = type_artifacts[ArtifactType.PERSONA_CONTRIBUTION]
            lines.append('|' + '-' * 60)
            lines.append(f'| PERSONA CONTRIBUTIONS ({len(contribs)})')
            for pc in contribs[:5]:
                if isinstance(pc, PersonaContributionArtifact):
                    lines.append(f'|   [{pc.id}] [{pc.persona_id}] Phase {pc.contribution_phase}')
            if len(contribs) > 5:
                lines.append(f'|   ... ({len(contribs) - 5} more)')
        if ArtifactType.LOG_BUNDLE in type_artifacts:
            bundles = type_artifacts[ArtifactType.LOG_BUNDLE]
            lines.append('|' + '-' * 60)
            lines.append(f'| LOG BUNDLES ({len(bundles)})')
            for lb in bundles[:2]:
                if isinstance(lb, LogBundleArtifact):
                    lines.append(f'|   [{lb.id}] {len(lb.source_files)} files merged')
                    if lb.affected_boards:
                        for b in lb.affected_boards[:5]:
                            lines.append(f'|     [{b.role}] {b.board_name}')
                    if lb.cascade_chain:
                        for link in lb.cascade_chain[:3]:
                            lines.append(f'|     {link.from_board}->{link.to_board}: {link.mechanism}')
        if ArtifactType.HYPOTHESIS_ARTIFACT in type_artifacts:
            hyps = type_artifacts[ArtifactType.HYPOTHESIS_ARTIFACT]
            lines.append('|' + '-' * 60)
            lines.append(f'| HYPOTHESES ({len(hyps)})')
            for h in hyps[:5]:
                if isinstance(h, HypothesisArtifact):
                    lines.append(f'|   [{h.id}] (score={h.score:.2f}) {h.description}')
            if len(hyps) > 5:
                lines.append(f'|   ... ({len(hyps) - 5} more)')
        if ArtifactType.EVIDENCE_ARTIFACT in type_artifacts:
            evs = type_artifacts[ArtifactType.EVIDENCE_ARTIFACT]
            lines.append('|' + '-' * 60)
            lines.append(f'| EVIDENCE ({len(evs)})')
            for e in evs[:5]:
                if isinstance(e, EvidenceArtifact):
                    lines.append(f'|   [{e.id}] [{e.strength}] {e.evidence_type}: {e.content}')
            if len(evs) > 5:
                lines.append(f'|   ... ({len(evs) - 5} more)')
        if ArtifactType.CAUSAL_CHAIN in type_artifacts:
            chains = type_artifacts[ArtifactType.CAUSAL_CHAIN]
            lines.append('|' + '-' * 60)
            lines.append(f'| CAUSAL CHAINS ({len(chains)})')
            for cc in chains[:5]:
                if isinstance(cc, CausalChainArtifact):
                    lines.append(f'|   [{cc.id}] hypothesis {cc.hypothesis_id}: {len(cc.steps)} steps, validity {cc.logical_validity:.0%}')
        if ArtifactType.CHALLENGE in type_artifacts:
            chs = type_artifacts[ArtifactType.CHALLENGE]
            lines.append('|' + '-' * 60)
            lines.append(f'| CHALLENGES ({len(chs)})')
            for ch in chs[:5]:
                if isinstance(ch, ChallengeArtifact):
                    status = 'resolved' if ch.resolved else 'unresolved'
                    lines.append(f'|   [{ch.id}] [{ch.severity}] ({status}) {ch.content}')
            if len(chs) > 5:
                lines.append(f'|   ... ({len(chs) - 5} more)')
        if ArtifactType.CONCLUSION in type_artifacts:
            concs = type_artifacts[ArtifactType.CONCLUSION]
            lines.append('|' + '-' * 60)
            lines.append(f'| CONCLUSIONS ({len(concs)})')
            for c in concs[:2]:
                if isinstance(c, ConclusionArtifact):
                    lines.append(f'|   [{c.id}] ({c.outcome}) {c.root_cause}')
        lines.append('+' + '-' * 60 + '+')
        return '\n'.join(lines)

    def _serialize_focused_artifacts(self, binder: WorkBinder, artifact_ids: list[str]) -> str:
        parts = []
        for aid in artifact_ids:
            artifact = binder.get_artifact(aid)
            if not artifact:
                continue
            parts.append(render_artifact(artifact))
            parts.append('')
        return '\n'.join(parts)

    def _serialize_recent_findings(self, binder: WorkBinder, current_persona: str | None, limit: int=5) -> str:
        findings = []
        for artifact in binder._artifacts.values():
            if artifact.is_deleted:
                continue
            if not isinstance(artifact, Finding):
                continue
            if current_persona and artifact.persona == current_persona:
                continue
            findings.append(artifact)
        findings.sort(key=lambda f: f.created_at, reverse=True)
        parts = []
        for finding in findings[:limit]:
            phase_str = f'[Phase {finding.phase}]' if finding.phase is not None else ''
            parts.append(f'- [{finding.id}] {phase_str} [{finding.persona}] ({finding.finding_type.value}): {finding.content}')
        return '\n'.join(parts)

    def _get_tool_instructions(self) -> str:
        return 'BINDER TOOLS:\n\n  READ:\n  - get_artifact(id): Retrieve full content of artifact by ID\n  - list_artifacts(type, tags, phase, function): Filter and list artifacts\n  - search_binder(query): Full-text search artifact contents\n  - get_artifact_history(id): View modification history\n\n  WRITE:\n  - add_artifact(type, content, tags): Add new artifact to binder\n  - add_finding(content, confidence): Record your observation\n  - expand_call_graph(function, direction): Add callers/callees to binder\n  - get_function_source(name): Add function body to binder\n\n  UPDATE:\n  - update_artifact(id, updates): Modify artifact fields\n  - annotate(artifact_id, note): Add note to existing artifact\n\n  DELETE:\n  - mark_deleted(id, reason): Soft-delete artifact (still visible, flagged)\n  - restore_artifact(id): Restore soft-deleted artifact'

    def serialize_call_graph_detail(self, call_graph: CallGraphNode) -> str:
        lines = [f'Call Graph for {call_graph.center_function}():', '']
        if call_graph.callers:
            lines.append('CALLERS (pass data TO this function):')
            for i, caller in enumerate(call_graph.callers, 1):
                lines.append(f'  {i}. {caller.caller_name}()')
                if caller.caller_file:
                    lines.append(f'     File: {caller.caller_file}')
                if caller.summary:
                    lines.append(f'     Summary: {caller.summary}')
                if caller.body:
                    lines.append('     ```cpp')
                    lines.append(caller.body)
                    lines.append('     ```')
                lines.append('')
        if call_graph.callees:
            lines.append('CALLEES (called BY this function):')
            for i, callee in enumerate(call_graph.callees, 1):
                lines.append(f'  {i}. {callee.callee_name}()')
                if callee.callee_file:
                    lines.append(f'     File: {callee.callee_file}')
                if callee.callee_signature:
                    lines.append(f'     Signature: {callee.callee_signature}')
                if callee.summary:
                    lines.append(f'     Summary: {callee.summary}')
                if callee.body:
                    lines.append('     ```cpp')
                    lines.append(callee.body)
                    lines.append('     ```')
                lines.append('')
        return '\n'.join(lines)

    def serialize_for_investigation_start(self, binder: WorkBinder, max_tokens: int=2000) -> str:
        parts = []
        error_contexts = binder.get_by_type(ArtifactType.ERROR_CONTEXT)
        if error_contexts:
            ctx = error_contexts[0]
            if isinstance(ctx, ErrorContextArtifact):
                parts.append('ERROR UNDER INVESTIGATION:')
                parts.append(f'  Message: {ctx.error_message}')
                if ctx.error_component:
                    parts.append(f'  Component: {ctx.error_component}')
                if ctx.error_function:
                    parts.append(f'  Function: {ctx.error_function}')
                parts.append('')
        locations = binder.get_by_type(ArtifactType.SOURCE_LOCATION)
        if locations:
            parts.append(f'SOURCE LOCATIONS FOUND ({len(locations)}):')
            for loc in locations[:3]:
                if isinstance(loc, SourceLocationArtifact):
                    score_pct = int(loc.match_score * 100)
                    parts.append(f'  - {loc.file_path}:{loc.line_number} ({score_pct}% match)')
            parts.append('')
        counts = binder.count_by_type()
        if counts:
            parts.append('BINDER CONTENTS:')
            for atype, count in counts.items():
                parts.append(f'  - {atype}: {count}')
            parts.append('')
        return '\n'.join(parts)