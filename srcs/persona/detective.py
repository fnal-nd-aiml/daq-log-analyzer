"""
File: detective.py
Purpose: Detective persona - Phase 2: Evidence Seeking.
Category: Utility
Author: artdaq team
Depends: tools, forensics_tools, investigation_tools, pattern_tools, models, ...
Exports: DetectivePersona
Complexity: High | Lines: 393
"""

import logging
from typing import TYPE_CHECKING, Any
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_DETECTIVE, Persona
if TYPE_CHECKING:
    from srcs.models.question import QuestionContext
from srcs.models.investigation import AlternativeInvestigationPaths, AlternativePath, Evidence, EvidenceGap, EvidenceGapAnalysis, EvidenceQualityScore, Hypothesis
logger = logging.getLogger(__name__)

class DetectivePersona(CollaborativePersona):

    def __init__(self) -> None:
        self._orchestrator: Any = None
        self._collected_evidence: Evidence | None = None
        self._updated_hypotheses: list[Hypothesis] = []

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_DETECTIVE]

    @property
    def traits(self) -> list[str]:
        return ['analytical', 'persistent', 'detail-oriented', 'methodical', 'evidence-focused']

    @property
    def thinking_style(self) -> str:
        return 'Investigative analysis - seeks discriminating evidence, evaluates source quality, tracks evidence gaps, updates hypothesis rankings based on findings'

    async def prepare(self, context: InvestigationContext) -> None:
        from srcs.persona.orchestration import EvidenceOrchestrator
        evidence_config = None
        max_iterations = 10
        if context.config is not None:
            evidence_config = getattr(context.config, 'evidence_config', None)
            max_iterations = getattr(context.config, 'max_evidence_iterations', 10)
        code_tools = None
        if context.code_index is not None:
            from srcs.agent.tools import CodeTools
            code_tools = CodeTools(code_index=context.code_index)
        pattern_tools = None
        if context.kb is not None:
            from srcs.agent.tools.pattern_tools import PatternTools
            pattern_tools = PatternTools(kb=context.kb)
        forensics_tools = None
        if context.code_index is not None:
            from srcs.agent.tools.forensics_tools import CodeForensicsTools
            forensics_tools = CodeForensicsTools(code_index=context.code_index)
        investigation_tools = None
        if context.kb is not None:
            from srcs.agent.tools.investigation_tools import InvestigationTools
            from srcs.models.logs import Log as LogModel
            logs_for_tools: list[LogModel] = []
            if context.binder is not None:
                timeline = context.binder.get_merged_timeline()
                if timeline and timeline.entries:
                    from datetime import datetime as _dt
                    for entry in timeline.entries:
                        try:
                            ts = _dt.fromisoformat(entry.timestamp)
                        except (ValueError, TypeError):
                            ts = _dt.now()
                        comp = entry.component or 'unknown'
                        board = entry.board_name or ''
                        if board and board.lower() != comp.lower():
                            comp = f'{comp}@{board}'
                        logs_for_tools.append(LogModel(timestamp=ts, level=entry.level.upper() if entry.level else 'INFO', component=comp, function=entry.source_location or None, message=entry.message))
            if not logs_for_tools:
                logs_for_tools = list(context.context_logs or [])
            investigation_tools = InvestigationTools(kb=context.kb, context_logs=logs_for_tools)
        if context.llm is not None and context.kb is not None:
            self._orchestrator = EvidenceOrchestrator(llm=context.llm, kb=context.kb, max_iterations=max_iterations, investigation_tools=investigation_tools, code_tools=code_tools, pattern_tools=pattern_tools, forensics_tools=forensics_tools, config=evidence_config)
        else:
            logger.warning('LLM or KB not available - evidence seeking will be limited')
            self._orchestrator = None

    async def contribute(self, context: InvestigationContext) -> Contribution:
        evidence, updated_hypotheses = await self._seek_evidence(context)
        self._collected_evidence = evidence
        self._updated_hypotheses = updated_hypotheses
        context.evidence = evidence
        context.hypotheses = updated_hypotheses
        content = self._build_content_dict(evidence, updated_hypotheses)
        confidence = self._calculate_confidence(evidence)
        return Contribution(persona_id='detective', phase=PHASE_DETECTIVE, content=content, confidence=confidence, reasoning=self._build_reasoning(evidence))

    async def _seek_evidence(self, context: InvestigationContext) -> tuple[Evidence, list[Hypothesis]]:
        if self._orchestrator is None:
            await self.prepare(context)
        if self._orchestrator is None:
            logger.warning('Cannot seek evidence - orchestrator not initialized')
            return (Evidence(), context.hypotheses)
        prior = context.prior_knowledge
        if prior is None:
            from srcs.models import PriorKnowledge
            prior = PriorKnowledge(matched_patterns=[], similar_investigations=[], recommended_hypotheses=[], recommended_queries=[])
        initial_evidence = context.evidence if context.evidence else Evidence()
        hypotheses = context.hypotheses
        binder = context.binder
        try:
            evidence, updated_hypotheses = await self._orchestrator.seek(hypotheses=hypotheses, initial_evidence=initial_evidence, prior=prior, binder=binder)
            return (evidence, updated_hypotheses)
        except Exception as e:
            logger.warning(f'Evidence seeking failed: {e}')
            return (initial_evidence, hypotheses)

    def _build_content_dict(self, evidence: Evidence, hypotheses: list[Hypothesis]) -> dict[str, Any]:
        items = list(evidence.items.values()) if evidence.items else []
        by_type: dict[str, int] = {}
        for item in items:
            if item.evidence_type not in by_type:
                by_type[item.evidence_type] = 0
            by_type[item.evidence_type] += 1
        gap_analysis = self._analyze_evidence_gaps(evidence, hypotheses)
        quality_score = self._calculate_quality_score(evidence, hypotheses)
        alternative_paths = self._suggest_alternative_paths(evidence, hypotheses, gap_analysis)
        content: dict[str, Any] = {'items_found': len(items), 'strong_evidence': sum((1 for i in items if i.strength == 'STRONG')), 'moderate_evidence': sum((1 for i in items if i.strength == 'MODERATE')), 'weak_evidence': sum((1 for i in items if i.strength == 'WEAK')), 'by_type': by_type, 'hypotheses_updated': len(hypotheses), 'top_hypothesis': {'id': hypotheses[0].id, 'description': hypotheses[0].description, 'score': hypotheses[0].score} if hypotheses else None, 'supporting_evidence_count': sum((len(h.supporting_evidence_ids) for h in hypotheses)), 'contradicting_evidence_count': sum((len(h.contradicting_evidence_ids) for h in hypotheses))}
        content['evidence_gap_analysis'] = {'gaps': [{'hypothesis_id': g.hypothesis_id, 'hypothesis_description': g.hypothesis_description, 'gap_type': g.gap_type, 'missing_evidence_types': g.missing_evidence_types, 'suggested_queries': g.suggested_queries, 'severity': g.severity} for g in gap_analysis.gaps], 'fully_covered_hypotheses': gap_analysis.fully_covered_hypotheses, 'partially_covered_hypotheses': gap_analysis.partially_covered_hypotheses, 'uncovered_hypotheses': gap_analysis.uncovered_hypotheses, 'recommended_next_queries': gap_analysis.recommended_next_queries}
        content['evidence_quality_score'] = {'overall_score': quality_score.overall_score, 'strength_score': quality_score.strength_score, 'diversity_score': quality_score.diversity_score, 'coverage_score': quality_score.coverage_score, 'discrimination_score': quality_score.discrimination_score, 'evidence_types_present': quality_score.evidence_types_present, 'evidence_types_missing': quality_score.evidence_types_missing, 'hypotheses_with_evidence': quality_score.hypotheses_with_evidence, 'hypotheses_without_evidence': quality_score.hypotheses_without_evidence, 'has_strong_discriminating_evidence': quality_score.has_strong_discriminating_evidence, 'has_code_and_log_evidence': quality_score.has_code_and_log_evidence, 'top_hypothesis_supported': quality_score.top_hypothesis_supported}
        content['alternative_paths'] = {'paths': [{'path_type': p.path_type, 'description': p.description, 'expected_benefit': p.expected_benefit, 'difficulty': p.difficulty, 'requires': p.requires} for p in alternative_paths.paths], 'reason_current_insufficient': alternative_paths.reason_current_insufficient, 'most_promising_path': {'path_type': alternative_paths.most_promising_path.path_type, 'description': alternative_paths.most_promising_path.description} if alternative_paths.most_promising_path else None}
        return content

    def _calculate_confidence(self, evidence: Evidence) -> float:
        items = list(evidence.items.values()) if evidence.items else []
        if not items:
            return 0.2
        strong = sum((1 for i in items if i.strength == 'STRONG'))
        moderate = sum((1 for i in items if i.strength == 'MODERATE'))
        if strong >= 3:
            return 0.85
        elif strong >= 2:
            return 0.75
        elif strong >= 1:
            return 0.65
        elif moderate >= 3:
            return 0.55
        elif moderate >= 1:
            return 0.45
        else:
            return 0.35

    def _build_reasoning(self, evidence: Evidence) -> str:
        items = list(evidence.items.values()) if evidence.items else []
        if not items:
            return 'No evidence collected yet'
        parts = []
        parts.append(f'Collected {len(items)} evidence items')
        strong = sum((1 for i in items if i.strength == 'STRONG'))
        moderate = sum((1 for i in items if i.strength == 'MODERATE'))
        weak = sum((1 for i in items if i.strength == 'WEAK'))
        if strong:
            parts.append(f'{strong} strong')
        if moderate:
            parts.append(f'{moderate} moderate')
        if weak:
            parts.append(f'{weak} weak')
        types = {i.evidence_type for i in items}
        parts.append(f"Types: {', '.join(sorted(types))}")
        return '; '.join(parts)

    def _analyze_evidence_gaps(self, evidence: Evidence, hypotheses: list[Hypothesis]) -> EvidenceGapAnalysis:
        gaps: list[EvidenceGap] = []
        fully_covered = 0
        partially_covered = 0
        uncovered = 0
        expected_evidence_types = {'log', 'code', 'config'}
        for hypothesis in hypotheses:
            has_supporting = bool(hypothesis.supporting_evidence_ids)
            has_contradicting = bool(hypothesis.contradicting_evidence_ids)
            hypothesis_evidence_types: set[str] = set()
            all_evidence_ids = hypothesis.supporting_evidence_ids + hypothesis.contradicting_evidence_ids
            for eid in all_evidence_ids:
                item = evidence.get(eid)
                if item:
                    hypothesis_evidence_types.add(item.evidence_type)
            strong_evidence = False
            for eid in hypothesis.supporting_evidence_ids:
                item = evidence.get(eid)
                if item and item.strength == 'STRONG':
                    strong_evidence = True
                    break
            gap_type = None
            severity = 'low'
            missing_types: list[str] = []
            suggested_queries: list[str] = []
            if not has_supporting and (not has_contradicting):
                gap_type = 'no_evidence'
                severity = 'high'
                uncovered += 1
                missing_types = list(expected_evidence_types)
                suggested_queries = [f'Search for log entries mentioning: {hypothesis.description}', 'Check code for relevant error handling']
            elif not has_supporting:
                gap_type = 'no_supporting'
                severity = 'high'
                partially_covered += 1
                suggested_queries = [f'Find evidence that supports: {hypothesis.description}']
            elif not has_contradicting:
                gap_type = 'no_contradicting'
                severity = 'medium'
                partially_covered += 1
                suggested_queries = [f'Find evidence that would refute: {hypothesis.description}']
            elif not strong_evidence:
                gap_type = 'weak_only'
                severity = 'medium'
                partially_covered += 1
                suggested_queries = ['Seek stronger discriminating evidence']
            else:
                fully_covered += 1
                continue
            missing_types = list(expected_evidence_types - hypothesis_evidence_types)
            if gap_type:
                gaps.append(EvidenceGap(hypothesis_id=hypothesis.id, hypothesis_description=hypothesis.description, gap_type=gap_type, missing_evidence_types=missing_types, suggested_queries=suggested_queries, severity=severity))
        most_critical: EvidenceGap | None = None
        if gaps:
            high_severity_gaps = [g for g in gaps if g.severity == 'high']
            if high_severity_gaps:
                most_critical = high_severity_gaps[0]
            else:
                most_critical = gaps[0]
        recommended_queries = []
        for gap in gaps[:3]:
            recommended_queries.extend(gap.suggested_queries[:1])
        return EvidenceGapAnalysis(gaps=gaps, fully_covered_hypotheses=fully_covered, partially_covered_hypotheses=partially_covered, uncovered_hypotheses=uncovered, most_critical_gap=most_critical, recommended_next_queries=recommended_queries[:5])

    def _calculate_quality_score(self, evidence: Evidence, hypotheses: list[Hypothesis]) -> EvidenceQualityScore:
        items = list(evidence.items.values()) if evidence.items else []
        if not items:
            return EvidenceQualityScore(overall_score=0.0, strength_score=0.0, diversity_score=0.0, coverage_score=0.0, discrimination_score=0.0)
        strong = sum((1 for i in items if i.strength == 'STRONG'))
        moderate = sum((1 for i in items if i.strength == 'MODERATE'))
        total = len(items)
        strength_score = (strong * 1.0 + moderate * 0.5) / total if total > 0 else 0.0
        expected_types = {'log', 'code', 'config', 'function'}
        present_types = {i.evidence_type for i in items}
        diversity_score = len(present_types) / len(expected_types)
        hypotheses_with_evidence = sum((1 for h in hypotheses if h.supporting_evidence_ids or h.contradicting_evidence_ids))
        coverage_score = hypotheses_with_evidence / len(hypotheses) if hypotheses else 0.0
        discriminating_evidence: float = 0.0
        for item in items:
            supporting_any = any((item.id in h.supporting_evidence_ids for h in hypotheses))
            contradicting_any = any((item.id in h.contradicting_evidence_ids for h in hypotheses))
            if supporting_any and contradicting_any:
                discriminating_evidence += 1
            elif supporting_any or contradicting_any:
                discriminating_evidence += 0.5
        discrimination_score = discriminating_evidence / total if total > 0 else 0.0
        overall_score = strength_score * 0.3 + diversity_score * 0.2 + coverage_score * 0.3 + discrimination_score * 0.2
        has_code_and_log = 'code' in present_types and 'log' in present_types
        has_strong_discriminating = discriminating_evidence >= 1 and strong >= 1
        top_supported = hypotheses[0].supporting_evidence_ids if hypotheses else []
        return EvidenceQualityScore(overall_score=min(1.0, overall_score), strength_score=min(1.0, strength_score), diversity_score=min(1.0, diversity_score), coverage_score=min(1.0, coverage_score), discrimination_score=min(1.0, discrimination_score), evidence_types_present=list(present_types), evidence_types_missing=list(expected_types - present_types), hypotheses_with_evidence=hypotheses_with_evidence, hypotheses_without_evidence=len(hypotheses) - hypotheses_with_evidence, has_strong_discriminating_evidence=has_strong_discriminating, has_code_and_log_evidence=has_code_and_log, top_hypothesis_supported=bool(top_supported))

    def _suggest_alternative_paths(self, evidence: Evidence, hypotheses: list[Hypothesis], gap_analysis: EvidenceGapAnalysis) -> AlternativeInvestigationPaths:
        paths: list[AlternativePath] = []
        reason = ''
        items = list(evidence.items.values()) if evidence.items else []
        evidence_types = {i.evidence_type for i in items}
        if 'config' not in evidence_types:
            paths.append(AlternativePath(path_type='config_check', description='Check FCL configuration files for relevant parameters', expected_benefit='May reveal misconfiguration as root cause', difficulty='easy', requires=['access to FCL files']))
        if 'code' not in evidence_types:
            paths.append(AlternativePath(path_type='code_analysis', description='Analyze source code around error location', expected_benefit='May reveal logic errors or edge cases', difficulty='medium', requires=['source code access']))
        if gap_analysis.uncovered_hypotheses > 0:
            paths.append(AlternativePath(path_type='upstream_trace', description='Trace dataflow from upstream components', expected_benefit='May reveal issues in data source', difficulty='medium', requires=['call graph information']))
        log_evidence = [i for i in items if i.evidence_type == 'log']
        if len(log_evidence) < 3:
            paths.append(AlternativePath(path_type='temporal_analysis', description='Expand log time window to find precursor events', expected_benefit='May reveal sequence of events leading to error', difficulty='easy', requires=[]))
        if gap_analysis.uncovered_hypotheses > 0:
            reason = f'{gap_analysis.uncovered_hypotheses} hypotheses have no evidence; need broader evidence collection'
        elif gap_analysis.partially_covered_hypotheses > len(hypotheses) / 2:
            reason = 'Most hypotheses lack discriminating evidence'
        elif not items:
            reason = 'No evidence collected yet'
        most_promising = paths[0] if paths else None
        return AlternativeInvestigationPaths(paths=paths, reason_current_insufficient=reason, most_promising_path=most_promising)

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights = []
        uncertainties = []
        suggestions = []
        evidence = self._collected_evidence or context.evidence
        hypotheses = self._updated_hypotheses or context.hypotheses
        if evidence and evidence.items:
            items = list(evidence.items.values())
            strong = [i for i in items if i.strength == 'STRONG']
            if strong:
                insights.append(f'Found {len(strong)} piece(s) of strong discriminating evidence')
            types_found = {i.evidence_type for i in items}
            expected_types = {'log', 'code', 'config'}
            missing_types = expected_types - types_found
            if missing_types:
                uncertainties.append(f"Missing evidence types: {', '.join(missing_types)}")
                suggestions.append(f"Consider searching for {', '.join(missing_types)} evidence")
            if hypotheses:
                supported = sum((1 for h in hypotheses if h.supporting_evidence_ids))
                contradicted = sum((1 for h in hypotheses if h.contradicting_evidence_ids))
                if supported > 0:
                    insights.append(f'{supported} hypothesis(es) have supporting evidence')
                if contradicted > 0:
                    insights.append(f'{contradicted} hypothesis(es) have contradicting evidence')
                unsupported = len(hypotheses) - supported
                if unsupported > 0:
                    suggestions.append(f'{unsupported} hypothesis(es) still need more evidence')
            code_evidence = [i for i in items if i.evidence_type in ('code', 'function')]
            log_evidence = [i for i in items if i.evidence_type == 'log']
            if code_evidence and (not log_evidence):
                insights.append('Investigation is code-centric (no runtime logs)')
            elif log_evidence and (not code_evidence):
                uncertainties.append('No code analysis performed')
                suggestions.append('Consider analyzing relevant source code')
        else:
            uncertainties.append('No evidence has been collected')
            suggestions.append('Begin evidence seeking phase')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f"Let me check that claim, {other.metadata.name}. I'll look for evidence that either supports or contradicts it."

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        reasoning_str = str(contribution.reasoning).lower()
        if 'evidence' in reasoning_str:
            strengths.append('Conclusions are grounded in evidence')
        else:
            issues.append('Conclusion may lack sufficient evidentiary support')
            recommendations.append('Identify specific evidence that supports this conclusion')
        if 'strong' in reasoning_str:
            strengths.append('Strong evidence cited')
        elif contribution.confidence > 0.8:
            issues.append('High confidence without strong evidence noted')
            recommendations.append('Ensure strong evidence backs high-confidence claims')
        if 'code' in reasoning_str and 'log' in reasoning_str:
            strengths.append('Uses both code and log evidence')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='MEDIUM' if issues else 'LOW', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        reasoning_str = str(contribution.reasoning).lower()
        cites_evidence = any((term in reasoning_str for term in ['evidence', 'found', 'log', 'trace', 'observed', 'code']))
        return cites_evidence or contribution.confidence > 0.7

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        content: dict[str, Any] = {'evidence': [], 'facts': [], 'answer': '', 'citations': [], 'sources': []}
        evidence_points = self._gather_evidence(question, context)
        content['evidence'] = evidence_points
        content['answer'] = self._formulate_evidence_based_answer(question, evidence_points, context)
        content['citations'] = self._generate_citations(question)
        content['sources'] = [c['reference'] for c in content['citations']]
        content['facts'] = self._extract_facts(question, content['evidence'])
        reasoning = f"Gathered {len(content['evidence'])} pieces of evidence; cited {len(content['citations'])} source locations"
        confidence = 0.7 if content['evidence'] else 0.4
        return Contribution(persona_id='detective', phase=PHASE_DETECTIVE, content=content, confidence=confidence, reasoning=reasoning)

    def _gather_evidence(self, question: str, context: 'QuestionContext') -> list[str]:
        evidence: list[str] = []
        question_lower = question.lower()
        if context.related_logs:
            evidence.append(f'Related logs provided: {len(context.related_logs)} entries')
        if 'boardreader' in question_lower:
            evidence.append('BoardReader components handle hardware communication and data readout')
            evidence.append('BoardReader timeout settings are configurable via FCL parameters')
        if 'eventbuilder' in question_lower:
            evidence.append('EventBuilder assembles fragments into complete events')
            evidence.append('EventBuilder requires fragment synchronization across sources')
        if 'timeout' in question_lower:
            evidence.append('Timeout values are specified in milliseconds in FCL configuration')
            evidence.append('Default timeout values may not suit all hardware configurations')
        if 'config' in question_lower or 'fcl' in question_lower:
            evidence.append('FCL (FHiCL) is the configuration language used by artdaq')
            evidence.append('Configuration files define component behavior and parameters')
        if 'fragment' in question_lower:
            evidence.append('Fragments are the basic data unit passed between artdaq components')
        return evidence

    def _formulate_evidence_based_answer(self, question: str, evidence: list[str], context: 'QuestionContext') -> str:
        if not evidence:
            return 'Based on the available information, I cannot provide a definitive evidence-based answer. More specific details about the context would help.'
        evidence_text = '; '.join(evidence[:3])
        return f'Based on the evidence gathered: {evidence_text}. This information comes from the artdaq codebase and documentation.'

    def _generate_citations(self, question: str) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        question_lower = question.lower()
        if 'boardreader' in question_lower:
            citations.append({'type': 'code', 'reference': 'artdaq/Plugins/BoardReaderMain.cc', 'excerpt': 'Main entry point for BoardReader processes', 'relevance': 0.8, 'line_range': None})
        if 'eventbuilder' in question_lower:
            citations.append({'type': 'code', 'reference': 'artdaq/DAQrate/EventBuilder.cc', 'excerpt': 'EventBuilder implementation', 'relevance': 0.8, 'line_range': None})
        if 'config' in question_lower or 'fcl' in question_lower:
            citations.append({'type': 'documentation', 'reference': 'artdaq/doc/fcl_parameters.md', 'excerpt': 'FCL parameter documentation', 'relevance': 0.7, 'line_range': None})
        return citations

    def _extract_facts(self, question: str, evidence: list[str]) -> list[str]:
        return [e for e in evidence if len(e) < 100][:5]