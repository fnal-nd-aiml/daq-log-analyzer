"""
File: theorist.py
Purpose: Theorist persona - Phase 1: Hypothesis Generation.
Category: Utility
Author: artdaq team
Depends: dataflow, knowledge, llm, token_utils, models, ...
Exports: DeduplicationResponse, TheoristPersona
Complexity: High | Lines: 966
"""

from __future__ import annotations
import logging
import re
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from srcs.models.investigation_config import HypothesisConfig
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts.parsers import HypothesisResponse
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_THEORIST, Persona
if TYPE_CHECKING:
    from srcs.knowledge import KnowledgeBase
    from srcs.llm import LLMProvider
    from srcs.models.question import QuestionContext
    from srcs.workbinder import WorkBinder
from srcs.models import Log, PriorKnowledge
from srcs.models.hypothesis_report import CategoryCoverage, CategoryCoverageAnalysis, DeduplicationReport, MergedGroup, PriorAdjustment, PriorJustification, PriorJustificationReport, TierBreakdown, TierGenerationReport
from srcs.models.investigation import Hypothesis
logger = logging.getLogger(__name__)

class DeduplicationResponse(BaseModel):
    groups: list[list[int]] = Field(default_factory=list, description='Groups of hypothesis indices (1-based) that are semantically equivalent')
    distinct: list[int] = Field(default_factory=list, description='Indices (1-based) of hypotheses that are unique/distinct')

class TheoristPersona(CollaborativePersona):

    def __init__(self) -> None:
        self._llm: LLMProvider | None = None
        self._kb: KnowledgeBase | None = None
        self._config: HypothesisConfig | None = None
        self._generated_hypotheses: list[Hypothesis] = []
        self._tier_counts: dict[str, list[str]] = {}
        self._tier_priors: dict[str, list[float]] = {}
        self._merged_groups: list[MergedGroup] = []
        self._dedup_method: str = 'none'
        self._original_count: int = 0
        self._fast_path_triggered: bool = False
        self._fast_path_reason: str = ''

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_THEORIST]

    @property
    def traits(self) -> list[str]:
        return ['creative', 'speculative', 'multi-perspective', 'probabilistic', 'generative']

    @property
    def thinking_style(self) -> str:
        return 'Divergent thinking - generates multiple competing explanations, considers unlikely possibilities, assigns probabilities based on evidence strength, ensures coverage across failure categories'

    async def prepare(self, context: InvestigationContext) -> None:
        if context.config is not None:
            self._config = getattr(context.config, 'hypothesis_config', None)
        if self._config is None:
            self._config = HypothesisConfig()
        if context.llm is not None and context.kb is not None:
            self._llm = context.llm
            self._kb = context.kb
        else:
            logger.warning('LLM or KB not available - hypothesis generation will be limited')
            self._llm = None
            self._kb = None

    async def contribute(self, context: InvestigationContext) -> Contribution:
        hypotheses = await self._generate_hypotheses(context)
        self._generated_hypotheses = hypotheses
        context.hypotheses = hypotheses
        content = self._build_content_dict(hypotheses)
        confidence = self._calculate_confidence(hypotheses)
        return Contribution(persona_id='theorist', phase=PHASE_THEORIST, content=content, confidence=confidence, reasoning=self._build_reasoning(hypotheses))

    async def _generate_hypotheses(self, context: InvestigationContext) -> list[Hypothesis]:
        if context.hypotheses:
            return context.hypotheses
        if self._llm is None:
            await self.prepare(context)
        if self._llm is None:
            logger.warning('Cannot generate hypotheses - LLM not initialized')
            return []
        prior = context.prior_knowledge
        if prior is None:
            prior = PriorKnowledge(matched_patterns=[], similar_investigations=[], recommended_hypotheses=[], recommended_queries=[])
        binder = context.binder
        try:
            hypotheses: list[Hypothesis] = await self._generate(error=context.error, context_logs=context.context_logs, prior=prior, binder=binder)
            return hypotheses
        except Exception as e:
            logger.warning(f'Hypothesis generation failed: {e}')
            return []

    def _build_content_dict(self, hypotheses: list[Hypothesis]) -> dict[str, Any]:
        tier_report = self._build_tier_report(hypotheses)
        dedup_report = self._build_dedup_report(hypotheses)
        coverage_analysis = self._build_coverage_analysis(hypotheses)
        prior_report = self._build_prior_report(hypotheses)
        content: dict[str, Any] = {'hypotheses': [{'id': h.id, 'description': h.description, 'source': h.source, 'prior': h.prior, 'score': h.score} for h in hypotheses], 'count': len(hypotheses), 'categories': list(self._extract_categories(hypotheses)), 'has_code_hints': any((h.source.startswith('code_hint:') for h in hypotheses)), 'has_pattern_match': any((h.source.startswith('pattern:') for h in hypotheses))}
        content['tier_generation_report'] = {'tiers': [{'tier_name': t.tier_name, 'count': t.count, 'hypothesis_ids': t.hypothesis_ids, 'avg_prior': t.avg_prior, 'best_prior': t.best_prior} for t in tier_report.tiers], 'total_before_dedup': tier_report.total_before_dedup, 'total_after_dedup': tier_report.total_after_dedup, 'fast_path_triggered': tier_report.fast_path_triggered, 'fast_path_reason': tier_report.fast_path_reason, 'primary_tier': tier_report.primary_tier}
        content['deduplication_report'] = {'method_used': dedup_report.method_used, 'original_count': dedup_report.original_count, 'final_count': dedup_report.final_count, 'merged_groups': [{'kept_hypothesis_id': g.kept_hypothesis_id, 'merged_hypothesis_ids': g.merged_hypothesis_ids, 'similarity_scores': g.similarity_scores, 'merge_reason': g.merge_reason, 'combined_prior': g.combined_prior} for g in dedup_report.merged_groups], 'merge_threshold': dedup_report.merge_threshold}
        content['category_coverage_analysis'] = {'categories': [{'category': c.category, 'is_covered': c.is_covered, 'hypothesis_count': c.hypothesis_count, 'best_prior': c.best_prior} for c in coverage_analysis.categories], 'covered_count': coverage_analysis.covered_count, 'missing_categories': coverage_analysis.missing_categories, 'coverage_score': coverage_analysis.coverage_score, 'suggestions': coverage_analysis.suggestions}
        content['prior_justification_report'] = {'justifications': [{'hypothesis_id': j.hypothesis_id, 'base_rate': j.base_rate, 'adjustments': [{'reason': a.reason, 'delta': a.delta} for a in j.adjustments], 'final_prior': j.final_prior, 'normalization_factor': j.normalization_factor, 'normalized_prior': j.normalized_prior} for j in prior_report.justifications], 'normalization_mode': prior_report.normalization_mode, 'code_hint_share': prior_report.code_hint_share, 'total_raw_prior': prior_report.total_raw_prior}
        return content

    def _extract_categories(self, hypotheses: list[Hypothesis]) -> set[str]:
        categories = set()
        for h in hypotheses:
            desc_lower = h.description.lower()
            if 'hardware' in desc_lower:
                categories.add('hardware')
            elif 'config' in desc_lower:
                categories.add('configuration')
            elif 'timing' in desc_lower or 'timeout' in desc_lower:
                categories.add('timing')
            elif 'resource' in desc_lower or 'memory' in desc_lower:
                categories.add('resource')
            elif 'null' in desc_lower or 'pointer' in desc_lower:
                categories.add('null_pointer')
            elif 'race' in desc_lower or 'thread' in desc_lower:
                categories.add('concurrency')
            else:
                categories.add('software')
        return categories

    def _build_tier_report(self, hypotheses: list[Hypothesis]) -> TierGenerationReport:
        tiers: list[TierBreakdown] = []
        for tier_name, hypothesis_ids in self._tier_counts.items():
            priors = self._tier_priors.get(tier_name, [])
            avg_prior = sum(priors) / len(priors) if priors else 0.0
            best_prior = max(priors) if priors else 0.0
            tiers.append(TierBreakdown(tier_name=tier_name, count=len(hypothesis_ids), hypothesis_ids=hypothesis_ids, avg_prior=avg_prior, best_prior=best_prior))
        tiers.sort(key=lambda t: t.count, reverse=True)
        primary_tier = tiers[0].tier_name if tiers else ''
        return TierGenerationReport(tiers=tiers, total_before_dedup=self._original_count, total_after_dedup=len(hypotheses), fast_path_triggered=self._fast_path_triggered, fast_path_reason=self._fast_path_reason, primary_tier=primary_tier)

    def _build_dedup_report(self, hypotheses: list[Hypothesis]) -> DeduplicationReport:
        return DeduplicationReport(method_used=self._dedup_method, original_count=self._original_count, final_count=len(hypotheses), merged_groups=self._merged_groups, distinct_hypotheses=[h.id for h in hypotheses], merge_threshold=self._config.merge_similarity_threshold if self._config else 0.8)

    def _build_coverage_analysis(self, hypotheses: list[Hypothesis]) -> CategoryCoverageAnalysis:
        expected_categories = ['hardware', 'configuration', 'timing', 'resource', 'software', 'concurrency']
        categories_data: list[CategoryCoverage] = []
        covered_categories: set[str] = set()
        category_hypotheses: dict[str, list[Hypothesis]] = {}
        for h in hypotheses:
            cat = self._get_hypothesis_category(h)
            if cat not in category_hypotheses:
                category_hypotheses[cat] = []
            category_hypotheses[cat].append(h)
        for category in expected_categories:
            hypos = category_hypotheses.get(category, [])
            is_covered = len(hypos) > 0
            if is_covered:
                covered_categories.add(category)
            categories_data.append(CategoryCoverage(category=category, is_covered=is_covered, hypothesis_count=len(hypos), best_prior=max((h.prior for h in hypos), default=0.0), hypothesis_ids=[h.id for h in hypos]))
        missing_categories = [c for c in expected_categories if c not in covered_categories]
        suggestions = [f'Consider adding a {cat} hypothesis' for cat in missing_categories[:3]]
        coverage_score = len(covered_categories) / len(expected_categories)
        return CategoryCoverageAnalysis(categories=categories_data, covered_count=len(covered_categories), missing_categories=missing_categories, coverage_score=coverage_score, suggestions=suggestions)

    def _get_hypothesis_category(self, hypothesis: Hypothesis) -> str:
        desc_lower = hypothesis.description.lower()
        if 'hardware' in desc_lower:
            return 'hardware'
        if 'config' in desc_lower:
            return 'configuration'
        if 'timing' in desc_lower or 'timeout' in desc_lower:
            return 'timing'
        if 'resource' in desc_lower or 'memory' in desc_lower:
            return 'resource'
        if 'race' in desc_lower or 'thread' in desc_lower:
            return 'concurrency'
        return 'software'

    def _build_prior_report(self, hypotheses: list[Hypothesis]) -> PriorJustificationReport:
        justifications: list[PriorJustification] = []
        code_hints = [h for h in hypotheses if h.source.startswith('code_hint:')]
        normalization_mode = 'two_tier' if code_hints else 'single_tier'
        code_hint_share = self._config.code_hint_probability_share if self._config else 0.5
        for h in hypotheses:
            base_rate = self._get_base_rate_for_source(h.source)
            adjustments: list[PriorAdjustment] = []
            if '+merged' in h.source:
                merge_count = self._extract_merge_count(h.source)
                adjustments.append(PriorAdjustment(reason=f'merged_{merge_count}_similar', delta=merge_count * 0.05))
            if ':llm_merged' in h.source:
                adjustments.append(PriorAdjustment(reason='llm_deduplication_merge', delta=0.05))
            total_raw = sum((self._get_base_rate_for_source(hyp.source) for hyp in hypotheses))
            normalization_factor = 1.0 / total_raw if total_raw > 0 else 1.0
            justifications.append(PriorJustification(hypothesis_id=h.id, base_rate=base_rate, adjustments=adjustments, final_prior=base_rate + sum((a.delta for a in adjustments)), normalization_factor=normalization_factor, normalized_prior=h.prior))
        return PriorJustificationReport(justifications=justifications, normalization_mode=normalization_mode, code_hint_share=code_hint_share, total_raw_prior=sum((j.final_prior for j in justifications)))

    def _get_base_rate_for_source(self, source: str) -> float:
        if source.startswith('numeric_analysis'):
            return 0.75
        if source.startswith('code_hint:explicit_cause'):
            return 0.85
        if source.startswith('code_hint:'):
            return 0.75
        if source.startswith('pattern:'):
            return 0.7
        if source.startswith('similar:'):
            return 0.4
        if source.startswith('fresh:'):
            return 0.2
        if source.startswith('alternative:'):
            return 0.1
        return 0.2

    def _extract_merge_count(self, source: str) -> int:
        import re
        match = re.search('\\+merged\\((\\d+)\\)', source)
        if match:
            return int(match.group(1))
        return 0

    def _track_hypothesis_tier(self, hypothesis: Hypothesis, tier_name: str) -> None:
        if tier_name not in self._tier_counts:
            self._tier_counts[tier_name] = []
            self._tier_priors[tier_name] = []
        self._tier_counts[tier_name].append(hypothesis.id)
        self._tier_priors[tier_name].append(hypothesis.prior)

    def _get_max_tokens(self) -> int:
        if self._llm is not None and hasattr(self._llm, 'config'):
            return self._llm.config.max_tokens or 50000
        return 50000

    def _calculate_confidence(self, hypotheses: list[Hypothesis]) -> float:
        if not hypotheses:
            return 0.3
        confidence = 0.5
        code_hints = [h for h in hypotheses if h.source.startswith('code_hint:')]
        if code_hints:
            best_hint = max((h.prior for h in code_hints))
            confidence = max(confidence, best_hint * 0.95)
        pattern_matches = [h for h in hypotheses if h.source.startswith('pattern:')]
        if pattern_matches:
            confidence = max(confidence, 0.7)
        categories = self._extract_categories(hypotheses)
        if len(categories) >= 3:
            confidence = max(confidence, 0.6)
        if hypotheses and hypotheses[0].prior > 0.3:
            confidence = max(confidence, 0.65)
        return min(confidence, 0.95)

    def _build_reasoning(self, hypotheses: list[Hypothesis]) -> str:
        if not hypotheses:
            return 'No hypotheses generated - missing prior knowledge or LLM'
        parts = []
        code_hints = [h for h in hypotheses if h.source.startswith('code_hint:')]
        pattern_matches = [h for h in hypotheses if h.source.startswith('pattern:')]
        similar_cases = [h for h in hypotheses if h.source.startswith('similar:')]
        fresh = [h for h in hypotheses if h.source.startswith('fresh:')]
        alternatives = [h for h in hypotheses if h.source.startswith('alternative:')]
        sources = []
        if code_hints:
            auth = sum((1 for h in code_hints if 'explicit_cause' in h.source))
            if auth:
                sources.append(f'{auth} authoritative code hints')
            else:
                sources.append(f'{len(code_hints)} code hints')
        if pattern_matches:
            sources.append(f'{len(pattern_matches)} pattern matches')
        if similar_cases:
            sources.append(f'{len(similar_cases)} from similar cases')
        if fresh:
            sources.append(f'{len(fresh)} fresh LLM')
        if alternatives:
            sources.append(f'{len(alternatives)} alternatives')
        parts.append(f'Generated {len(hypotheses)} hypotheses')
        if sources:
            parts.append(f"Sources: {', '.join(sources)}")
        categories = self._extract_categories(hypotheses)
        parts.append(f"Categories: {', '.join(sorted(categories))}")
        if hypotheses:
            top = hypotheses[0]
            parts.append(f'Top hypothesis ({top.prior:.0%}): {top.description[:60]}...')
        return '; '.join(parts)

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights = []
        uncertainties = []
        suggestions = []
        hypotheses = self._generated_hypotheses or context.hypotheses
        if hypotheses:
            high_prior = [h for h in hypotheses if h.prior > 0.3]
            low_prior = [h for h in hypotheses if h.prior < 0.1]
            if high_prior:
                insights.append(f'{len(high_prior)} hypothesis(es) have strong prior support (>30%)')
            code_hints = [h for h in hypotheses if h.source.startswith('code_hint:')]
            if code_hints:
                insights.append(f'Found {len(code_hints)} code hint(s) from source analysis')
                auth_hints = [h for h in code_hints if 'explicit_cause' in h.source]
                if auth_hints:
                    insights.append('Authoritative developer explanation found - high confidence')
            if not low_prior:
                uncertainties.append('May be missing low-probability but important alternatives')
                suggestions.append('Consider generating deliberate alternative hypotheses')
            sources = {h.source.split(':')[0] for h in hypotheses}
            insights.append(f'Hypotheses from {len(sources)} different source types')
            categories = self._extract_categories(hypotheses)
            if len(categories) < 3:
                uncertainties.append(f'Limited category coverage ({len(categories)} categories)')
                missing = {'hardware', 'configuration', 'timing', 'software'} - categories
                if missing:
                    suggestions.append(f"Consider hypotheses in categories: {', '.join(missing)}")
        else:
            uncertainties.append('No hypotheses have been generated')
            suggestions.append('Proceed with hypothesis generation')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f'Interesting perspective, {other.metadata.name}. What if we also consider an alternative explanation? There might be multiple paths that lead to this error.'

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        content_str = str(contribution.content).lower()
        reasoning_str = str(contribution.reasoning).lower()
        if 'only' in content_str or 'must be' in content_str:
            issues.append('Conclusion appears overly certain - have alternatives been considered?')
            recommendations.append('Generate at least one alternative hypothesis before concluding')
        if 'multiple' in content_str or 'possibilities' in content_str:
            strengths.append('Good consideration of multiple possibilities')
        if 'code_hint' in reasoning_str or 'authoritative' in reasoning_str:
            strengths.append('Grounded in code analysis')
        if contribution.confidence > 0.9 and 'alternative' not in content_str:
            issues.append('Very high confidence without mentioning alternatives')
            recommendations.append('Consider what evidence would contradict this conclusion')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='MEDIUM' if issues else 'LOW', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        content_str = str(contribution.content).lower()
        considers_alternatives = any((term in content_str for term in ['alternative', 'possible', 'may', 'could', 'hypothesis']))
        return considers_alternatives or contribution.confidence <= 0.8

    async def _generate(self, error: Log, context_logs: list[Log], prior: PriorKnowledge, binder: 'WorkBinder') -> list[Hypothesis]:
        if self._config is None:
            self._config = HypothesisConfig()
        self._tier_counts = {}
        self._tier_priors = {}
        self._merged_groups = []
        self._dedup_method = 'none'
        self._fast_path_triggered = False
        self._fast_path_reason = ''
        hypotheses: list[Hypothesis] = []
        seen: set[str] = set()
        for rh in prior.recommended_hypotheses:
            if rh.source.startswith('numeric_analysis') and rh.description not in seen:
                h = Hypothesis(description=rh.description, source=rh.source, prior=rh.prior, score=rh.prior)
                hypotheses.append(h)
                seen.add(rh.description)
                self._track_hypothesis_tier(h, 'numeric_analysis')
        for rh in prior.recommended_hypotheses:
            if rh.source.startswith('code_hint:') and rh.description not in seen:
                h = Hypothesis(description=rh.description, source=rh.source, prior=rh.prior, score=rh.prior)
                hypotheses.append(h)
                seen.add(rh.description)
                self._track_hypothesis_tier(h, 'code_hints')
        for rh in prior.recommended_hypotheses:
            if rh.source.startswith('pattern:') and rh.description not in seen:
                h = Hypothesis(description=rh.description, source=rh.source, prior=rh.prior, score=rh.prior)
                hypotheses.append(h)
                seen.add(rh.description)
                self._track_hypothesis_tier(h, 'patterns')
        for rh in prior.recommended_hypotheses:
            if rh.source.startswith('similar:') and rh.description not in seen:
                h = Hypothesis(description=rh.description, source=rh.source, prior=rh.prior, score=rh.prior)
                hypotheses.append(h)
                seen.add(rh.description)
                self._track_hypothesis_tier(h, 'similar')
        if self._config.enable_llm_deduplication and len(hypotheses) >= self._config.llm_dedup_min_hypotheses:
            try:
                pre_dedup_count = len(hypotheses)
                self._original_count = pre_dedup_count
                hypotheses = await self._deduplicate_with_llm(hypotheses)
                self._dedup_method = 'llm'
                seen = {h.description for h in hypotheses}
                logger.info(f'LLM deduplication: {pre_dedup_count} -> {len(hypotheses)} hypotheses')
            except Exception as e:
                logger.warning(f'LLM deduplication failed: {e}')
        has_authoritative_hints = self._has_high_confidence_code_hints(hypotheses)
        if has_authoritative_hints:
            self._fast_path_triggered = True
            self._fast_path_reason = 'authoritative_code_hint'
        try:
            fresh = await self._generate_fresh(error, context_logs, prior, seen, binder)
            if has_authoritative_hints:
                fresh = fresh[:self._config.max_fresh_if_code_hints]
            hypotheses.extend(fresh)
            for h in fresh:
                seen.add(h.description)
                self._track_hypothesis_tier(h, 'fresh')
        except Exception as e:
            logger.warning(f'Failed to generate fresh hypotheses: {e}')
        alternatives = self._generate_alternatives(error, hypotheses)
        hypotheses.extend(alternatives)
        for h in alternatives:
            self._track_hypothesis_tier(h, 'alternatives')
        if self._original_count == 0:
            self._original_count = len(hypotheses)
        hypotheses = self._merge_similar_hypotheses(hypotheses)
        if self._dedup_method == 'none' and len(hypotheses) < self._original_count:
            self._dedup_method = 'keyword'
        if len(hypotheses) > 8:
            pre_count = len(hypotheses)
            hypotheses = self._merge_similar_hypotheses(hypotheses, similarity_threshold=0.5)
            if len(hypotheses) < pre_count and self._dedup_method == 'keyword':
                self._dedup_method = 'keyword+aggressive'
        hypotheses = self._normalize_priors(hypotheses)
        for h in hypotheses:
            h.score = h.prior
        hypotheses.sort(key=lambda h: h.prior, reverse=True)
        if binder is not None:
            for rank, h in enumerate(hypotheses):
                artifact_id = binder.add_hypothesis(description=h.description, source=h.source, prior_probability=h.prior, score=h.score, rank=rank, created_by='Theorist', phase=1)
                h.binder_artifact_id = artifact_id
        return hypotheses

    async def _generate_fresh(self, error: Log, context_logs: list[Log], prior: PriorKnowledge, exclude: set[str], binder: 'WorkBinder') -> list[Hypothesis]:
        if self._llm is None or self._config is None:
            return []
        error_function: str | None = error.function
        error_component: str | None = error.component
        if not error_function or error_function.lower() == 'unknown':
            error_function = self._get_function_from_source_locations(prior)
        if not error_component or error_component.lower() == 'unknown':
            error_component = self._get_component_from_source_locations(prior)
        binder_context = ''
        try:
            from srcs.workbinder.relevance import render_selected_artifacts
            binder_context = render_selected_artifacts(binder, 'theorist')
            if binder_context:
                binder_context = '''=== BINDER ARTIFACTS (selected by relevance) ===

''' + binder_context + '''

## Artifact-Theory Relevance
For each hypothesis, identify which artifacts above support or contradict it.'''
        except Exception as e:
            logger.debug(f'Failed to render binder artifacts: {e}')
        numeric_context = self._get_numeric_analysis_from_binder(binder)
        if not numeric_context:
            numeric_context = self._format_numeric_analysis(error.message)
        template = get_user_prompt(UserPromptType.HYPOTHESIS_GENERATION)
        prompt = template.format(error_message=error.message, error_component=error_component or 'Unknown', error_function=error_function or 'unknown', error_timestamp=error.timestamp.isoformat(), context_logs=self._format_logs(context_logs), prior_knowledge=self._format_prior(prior), code_context=self._format_code_context(prior), chronicler_context=self._format_chronicler_context(binder), prior_case_intelligence=self._format_prior_case_intelligence(prior, binder))
        if numeric_context:
            prompt = f'{prompt}\n\n{numeric_context}'
        if binder_context:
            prompt = f'{prompt}\n\n{binder_context}'
        try:
            system_prompt = get_system_prompt(SystemPromptType.THEORIST)
            response = await self._llm.generate_structured(prompt, HypothesisResponse, system_prompt=system_prompt)
        except Exception as e:
            logger.warning(f'Structured generation failed, trying plain text: {e}')
            system_prompt = get_system_prompt(SystemPromptType.THEORIST)
            response_text = await self._llm.generate(prompt, system_prompt=system_prompt)
            return self._parse_text_response(response_text, exclude)
        hypotheses = []
        for item in response.hypotheses:
            if item.description not in exclude:
                prior_value = min(self._config.fresh_prior_max, item.prior)
                h = Hypothesis(description=item.description, source=f'fresh:{item.category}', prior=prior_value, score=prior_value, category=item.category or None, confirming_evidence_design=item.confirming_evidence or None, refuting_evidence_design=item.refuting_evidence or None)
                hypotheses.append(h)
        return hypotheses

    def _parse_text_response(self, response: str, exclude: set[str]) -> list[Hypothesis]:
        hypotheses = []
        lines = response.split('\n')
        for line in lines:
            match = re.match('^[\\d\\.\\-\\*\\s]+(.+)', line.strip())
            if match:
                desc = match.group(1).strip()
                if desc and len(desc) > 10 and (desc not in exclude):
                    hypotheses.append(Hypothesis(description=desc[:500], source='fresh:parsed', prior=0.2, score=0.2))
        return hypotheses[:5]

    def _has_high_confidence_code_hints(self, hypotheses: list[Hypothesis]) -> bool:
        if self._config is None:
            return False
        for h in hypotheses:
            if h.source.startswith('numeric_analysis'):
                if h.prior >= self._config.authoritative_hint_threshold:
                    return True
            if h.source.startswith('code_hint:'):
                if h.source == 'code_hint:explicit_cause' or h.prior >= self._config.authoritative_hint_threshold:
                    return True
        return False

    def _generate_alternatives(self, error: Log, existing: list[Hypothesis]) -> list[Hypothesis]:
        if self._config is None:
            return []
        alternatives = []
        categories_seen: set[str] = set()
        for h in existing:
            if ':' in h.source:
                category = h.source.split(':')[1]
                categories_seen.add(category.lower())
        common_categories = [('hardware', 'Hardware failure or communication issue'), ('configuration', 'Misconfiguration or invalid settings'), ('timing', 'Timing or synchronization issue'), ('resource', 'Resource exhaustion (memory, disk, network)'), ('software', 'Software bug or logic error')]
        for cat, description in common_categories:
            if cat not in categories_seen:
                alternatives.append(Hypothesis(description=f'{description} causing: {error.message}', source=f'alternative:{cat}', prior=self._config.alternative_prior, score=self._config.alternative_prior))
        return alternatives[:self._config.max_alternatives]

    def _merge_similar_hypotheses(self, hypotheses: list[Hypothesis], similarity_threshold: float | None=None) -> list[Hypothesis]:
        if len(hypotheses) <= 1 or self._config is None:
            return hypotheses
        if similarity_threshold is None:
            similarity_threshold = self._config.merge_similarity_threshold

        def extract_terms(text: str) -> set[str]:
            text_lower = text.lower()
            stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'which', 'with', 'from', 'for', 'and', 'or', 'not', 'problem', 'issue', 'error', 'caused', 'cause', 'likely', 'most', 'probably', 'possibly', 'due', 'to', 'by', 'in'}
            words: set[str] = set()
            for word in text_lower.split():
                word = word.strip('.,!?()[]{}"\':;')
                if len(word) > 3 and word not in stopwords:
                    words.add(word)
            return words

        def compute_similarity(terms1: set[str], terms2: set[str]) -> float:
            if not terms1 or not terms2:
                return 0.0
            intersection = len(terms1 & terms2)
            union = len(terms1 | terms2)
            return intersection / union if union > 0 else 0.0
        term_sets = [extract_terms(h.description) for h in hypotheses]
        merged_indices: set[int] = set()
        result: list[Hypothesis] = []
        for i, h in enumerate(hypotheses):
            if i in merged_indices:
                continue
            similar_indices = [i]
            for j in range(i + 1, len(hypotheses)):
                if j in merged_indices:
                    continue
                similarity = compute_similarity(term_sets[i], term_sets[j])
                if similarity >= similarity_threshold:
                    similar_indices.append(j)
                    merged_indices.add(j)
            if len(similar_indices) == 1:
                result.append(h)
            else:
                similar_hypos = [hypotheses[idx] for idx in similar_indices]
                best = max(similar_hypos, key=lambda x: x.prior)
                other_priors = sum((hypo.prior for hypo in similar_hypos if hypo.id != best.id))
                combined_prior = min(self._config.merge_prior_cap, best.prior + other_priors * self._config.merge_other_prior_factor)
                merged = Hypothesis(description=best.description, source=f'{best.source}+merged({len(similar_indices) - 1})', prior=combined_prior)
                result.append(merged)
        return result

    async def _deduplicate_with_llm(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        if len(hypotheses) <= 3 or self._llm is None or self._config is None:
            return hypotheses
        hypothesis_list = '\n'.join([f'{i + 1}. [{h.source}] (prior={h.prior:.2f}) {h.description}' for i, h in enumerate(hypotheses)])
        prompt = f'Analyze these root cause hypotheses for semantic duplicates.\n\nHypotheses:\n{hypothesis_list}\n\nIdentify groups of hypotheses that describe the SAME underlying root cause with different wording.\nTwo hypotheses are duplicates if fixing one would also fix the other.\n\nReturn JSON:\n{{"groups": [[1, 3], [2, 5]], "distinct": [4, 6, 7]}}\n\nWhere:\n- "groups": Lists of hypothesis numbers (1-based) that are semantically equivalent\n- "distinct": Hypothesis numbers that are unique/distinct\n\nRules:\n- Only group hypotheses if they truly describe the same root cause\n- Different symptoms of the same cause should be grouped\n- Different causes should NOT be grouped even if related\n- If unsure, keep hypotheses separate (add to distinct)'
        try:
            response = await self._llm.generate_structured(prompt=prompt, response_model=DeduplicationResponse, system_prompt='You are an expert at identifying duplicate root cause hypotheses. Be conservative - only merge hypotheses that clearly describe the same underlying cause.')
            merged_indices: set[int] = set()
            result: list[Hypothesis] = []
            for group in response.groups:
                if len(group) < 2:
                    continue
                indices = [i - 1 for i in group if 0 < i <= len(hypotheses)]
                if len(indices) < 2:
                    continue
                group_hypotheses = [hypotheses[i] for i in indices]
                best = max(group_hypotheses, key=lambda h: h.prior)
                combined_prior = best.prior
                for h in group_hypotheses:
                    if h is not best:
                        combined_prior += h.prior * self._config.merge_other_prior_factor
                combined_prior = min(combined_prior, self._config.merge_prior_cap)
                merged = Hypothesis(description=best.description, source=f'{best.source}:llm_merged', prior=combined_prior, score=best.score)
                result.append(merged)
                merged_indices.update(indices)
            for i, h in enumerate(hypotheses):
                if i not in merged_indices:
                    result.append(h)
            min_after_dedup = 2
            if len(result) < min_after_dedup and len(hypotheses) >= min_after_dedup:
                merged_away = [hypotheses[i] for i in sorted(merged_indices) if hypotheses[i] not in result]
                merged_away.sort(key=lambda h: h.prior, reverse=True)
                for h in merged_away:
                    if len(result) >= min_after_dedup:
                        break
                    existing_descs = {r.description for r in result}
                    if h.description not in existing_descs:
                        result.append(h)
                        logger.info(f'Re-added hypothesis after dedup to maintain minimum {min_after_dedup}: {h.description[:60]}...')
            return result
        except Exception as e:
            logger.warning(f'LLM deduplication parsing failed: {e}')
            return hypotheses

    def _normalize_priors(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        if not hypotheses or self._config is None:
            return hypotheses
        code_hints = [h for h in hypotheses if h.source.startswith('code_hint:')]
        others = [h for h in hypotheses if not h.source.startswith('code_hint:')]
        max_hint_share = self._config.code_hint_probability_share
        if code_hints:
            avg_prior = sum((h.prior for h in code_hints)) / len(code_hints)
            quality_scale = max(0.0, min(1.0, (avg_prior - 0.3) / (0.85 - 0.3)))
            hint_share = quality_scale * max_hint_share
        else:
            hint_share = 0.0
        other_share = 1.0 - hint_share
        if code_hints:
            hint_total = sum((h.prior for h in code_hints))
            if hint_total > 0:
                for h in code_hints:
                    h.prior = h.prior / hint_total * hint_share
            other_total = sum((h.prior for h in others))
            if other_total > 0:
                for h in others:
                    h.prior = h.prior / other_total * other_share
            elif others:
                even_prior = other_share / len(others)
                for h in others:
                    h.prior = even_prior
        else:
            total = sum((h.prior for h in hypotheses))
            if total > 0:
                for h in hypotheses:
                    h.prior = h.prior / total
        return hypotheses

    def _get_function_from_source_locations(self, prior: PriorKnowledge) -> str | None:
        if not prior.source_locations:
            return None
        sorted_locs = sorted(prior.source_locations, key=lambda loc: loc.match_score or 0, reverse=True)
        for loc in sorted_locs:
            if loc.function_name:
                return loc.function_name
        return None

    def _get_component_from_source_locations(self, prior: PriorKnowledge) -> str | None:
        if not prior.source_locations:
            return None
        sorted_locs = sorted(prior.source_locations, key=lambda loc: loc.match_score or 0, reverse=True)
        for loc in sorted_locs:
            if loc.class_name:
                return loc.class_name
            if loc.file_path:
                import os
                filename = os.path.basename(loc.file_path)
                name, _ = os.path.splitext(filename)
                return name
        return None

    def _format_code_context(self, prior: PriorKnowledge) -> str:
        if not prior.source_locations:
            return 'No source code context available.'
        lines = ['Source locations found:']
        for i, loc in enumerate(prior.source_locations[:5], 1):
            lines.append(f'[{i}] {loc.file_path}:{loc.line_number}')
            if loc.function_name:
                lines.append(f'    Function: {loc.function_name}')
            if loc.class_name:
                lines.append(f'    Class: {loc.class_name}')
            if loc.callers:
                caller_names = [c.get('caller_name', c.get('name', '?')) for c in loc.callers[:3]]
                lines.append(f"    Callers: {', '.join(caller_names)}")
            if loc.callees:
                callee_names = [c.get('callee_name', '?') for c in loc.callees[:3]]
                lines.append(f"    Callees: {', '.join(callee_names)}")
        return '\n'.join(lines)

    def _get_numeric_analysis_from_binder(self, binder: 'WorkBinder') -> str:
        try:
            numeric_findings = binder.get_by_tag('numeric_analysis')
            if not numeric_findings:
                return ''
            from srcs.workbinder.artifacts import Finding
            for finding in numeric_findings:
                if isinstance(finding, Finding) and finding.content:
                    return f'## Numeric Analysis (from Phase 0 - Archivist)\n\n{finding.content}\n\nIMPORTANT: Use these specific numeric values in your hypotheses. Cite the exact\nnumbers when describing timeouts, latencies, or gaps.\n'
        except Exception as e:
            logger.debug(f'Failed to get numeric analysis from binder: {e}')
        return ''

    def _format_numeric_analysis(self, error_message: str) -> str:
        from srcs.agent.dataflow import NumericExtractor
        extractor = NumericExtractor()
        analysis = extractor.analyze(error_message)
        if not analysis.values:
            return ''
        return extractor.format_for_hypothesis(analysis)

    def _format_logs(self, logs: list[Log]) -> str:
        recent = logs[-20:]
        lines = []
        for log in recent:
            lines.append(f'[{log.timestamp}] {log.level} {log.component}: {log.message}')
        return '\n'.join(lines) if lines else 'No context logs available'

    def _format_chronicler_context(self, binder: 'WorkBinder') -> str:
        if binder is None:
            return 'Not available (single-file investigation)'
        log_bundle = binder.get_log_bundle()
        if log_bundle is None:
            return 'Not available (single-file investigation)'
        parts: list[str] = []
        narrative = getattr(log_bundle, 'annotated_narrative', '')
        if narrative:
            parts.append(f'### Narrative\n{narrative}')
        cascade_desc = getattr(log_bundle, 'cascade_description', '')
        if cascade_desc:
            parts.append(f'### Cascade Description\n{cascade_desc}')
        boards = getattr(log_bundle, 'affected_boards', [])
        if boards:
            board_lines = []
            for b in boards:
                line = f'- {b.board_name} ({b.role})'
                if getattr(b, 'failure_mode', None):
                    line += f': {b.failure_mode}'
                if getattr(b, 'key_error_message', None):
                    line += f' — Key error: {b.key_error_message}'
                board_lines.append(line)
            parts.append('### Affected Boards\n' + '\n'.join(board_lines))
        chain = getattr(log_bundle, 'cascade_chain', [])
        if chain:
            chain_lines = []
            for link in chain:
                chain_lines.append(f'- {link.from_board} → {link.to_board}: {link.mechanism}')
            parts.append('### Cascade Chain\n' + '\n'.join(chain_lines))
        primary_error = getattr(log_bundle, 'primary_error', None)
        if primary_error:
            msg = getattr(primary_error, 'message', '')
            fname = getattr(primary_error, 'filename', '')
            if msg:
                pe_text = msg
                if fname:
                    pe_text += f' (file: {fname})'
                parts.append(f'### Primary Error\n{pe_text}')
        clues = getattr(log_bundle, 'clues', [])
        if clues:
            clue_lines = []
            for clue in clues[:5]:
                desc = getattr(clue, 'description', '')
                search = getattr(clue, 'suggested_search', '')
                if desc:
                    line = f'- {desc}'
                    if search:
                        line += f' (search: {search})'
                    clue_lines.append(line)
            if clue_lines:
                parts.append('### Investigation Clues\n' + '\n'.join(clue_lines))
        br_id = binder.get_boardreader_identification()
        if br_id is not None:
            br_lines = []
            br_types = getattr(br_id, 'boardreader_types', [])
            if br_types:
                br_lines.append(f"Boardreader types: {', '.join(br_types)}")
            components = getattr(br_id, 'components', [])
            if components:
                br_lines.append(f"Components: {', '.join(components)}")
            if br_lines:
                parts.append('### Identified Components\n' + '\n'.join(br_lines))
        timeline = binder.get_merged_timeline()
        if timeline is not None:
            stat_lines = []
            total = getattr(timeline, 'total_entries', 0)
            if total:
                stat_lines.append(f'Total entries: {total}')
            errors = getattr(timeline, 'total_errors', 0)
            if errors:
                stat_lines.append(f'Errors: {errors}')
            warnings = getattr(timeline, 'total_warnings', 0)
            if warnings:
                stat_lines.append(f'Warnings: {warnings}')
            fc = getattr(timeline, 'file_count', 0)
            if fc:
                stat_lines.append(f'Files: {fc}')
            earliest = getattr(timeline, 'earliest_timestamp', '')
            latest = getattr(timeline, 'latest_timestamp', '')
            if earliest and latest:
                stat_lines.append(f'Time span: {earliest} → {latest}')
            if stat_lines:
                parts.append('### Timeline Statistics\n' + '\n'.join(stat_lines))
        return '\n\n'.join(parts) if parts else 'Not available (single-file investigation)'

    def _format_prior_case_intelligence(self, prior: PriorKnowledge, binder: 'WorkBinder') -> str:
        parts: list[str] = []
        if prior.enriched_case_summaries:
            parts.append('### Past Investigation Summaries')
            for summary in prior.enriched_case_summaries:
                parts.append(summary)
        if binder is not None:
            try:
                from srcs.workbinder.artifacts import ArtifactType
                from srcs.workbinder.binder import BinderQuery
                contributions = binder.query(BinderQuery(artifact_type=ArtifactType.PERSONA_CONTRIBUTION, phase=0))
                for artifact in contributions:
                    content = getattr(artifact, 'content_json', {})
                    if isinstance(content, dict):
                        llm_summary = content.get('llm_summary', '')
                        if llm_summary:
                            parts.append(f'### Archivist Analysis\n{llm_summary}')
                            break
            except Exception:
                pass
        if prior.matched_patterns:
            pattern_lines = []
            for match in prior.matched_patterns[:3]:
                p = match.pattern
                accuracy = p.times_correct / max(1, p.times_correct + p.times_incorrect)
                pattern_lines.append(f'- {p.name} (confidence: {p.pattern_confidence:.0%}, accuracy: {accuracy:.0%}, seen {p.times_seen}x)')
            parts.append('### Matched Patterns\n' + '\n'.join(pattern_lines))
        if prior.similar_investigations and (not prior.enriched_case_summaries):
            sim_lines = []
            for sim in prior.similar_investigations[:3]:
                if sim.root_cause:
                    correct = '✓' if sim.was_correct else '✗' if sim.was_correct is False else '?'
                    sim_lines.append(f'- [{correct}] {sim.root_cause}')
            if sim_lines:
                parts.append('### Similar Cases\n' + '\n'.join(sim_lines))
        return '\n\n'.join(parts) if parts else 'No prior cases found'

    def _format_prior(self, prior: PriorKnowledge) -> str:
        parts = []
        if prior.recommended_hypotheses:
            parts.append('Recommended hypotheses from prior knowledge:')
            for rh in prior.recommended_hypotheses[:3]:
                parts.append(f'  - {rh.description} (prior: {rh.prior:.1%})')
        if prior.source_locations:
            num_locations = len(prior.source_locations)
            if num_locations > 1:
                parts.append(f'\nSOURCE LOCATIONS ({num_locations} CANDIDATE LOCATIONS):')
            else:
                parts.append('\nSOURCE LOCATION (from code analysis):')
            for i, loc in enumerate(prior.source_locations[:5], 1):
                loc_info = f'  [{i}] {loc.file_path}:{loc.line_number}'
                if loc.function_name:
                    loc_info += f' in {loc.function_name}()'
                if loc.match_score:
                    loc_info += f' (score: {loc.match_score:.0%})'
                parts.append(loc_info)
                if loc.function_signature:
                    parts.append(f'      Signature: {loc.function_signature}')
                if loc.class_name:
                    parts.append(f'      Class: {loc.class_name}')
                if loc.function_summary:
                    parts.append(f'      Summary: {loc.function_summary}')
                if loc.call_graph_diagram:
                    parts.append(loc.call_graph_diagram)
                if loc.callers:
                    parts.append('      CALLERS:')
                    for c in loc.callers[:3]:
                        caller_name = c.get('caller_name', c.get('name', '?'))
                        parts.append(f'        - {caller_name}')
                if loc.callees:
                    parts.append('      CALLEES:')
                    for c in loc.callees[:3]:
                        callee_name = c.get('callee_name', '?')
                        parts.append(f'        - {callee_name}')
                if loc.function_body:
                    from srcs.llm.token_utils import truncate_if_needed
                    body = truncate_if_needed(loc.function_body, max_tokens=self._get_max_tokens() // 10, label='theorist function body')
                    parts.append(f'      Function Body:\n      ```cpp\n{body}\n      ```')
        if prior.resolution_digest:
            parts.append('''
RESOLUTION HISTORY FROM SIMILAR CASES:''')
            for rd in prior.resolution_digest[:3]:
                if rd.resolution_action:
                    parts.append(f'  - Case {rd.investigation_id[:8]}: {rd.resolution_action}')
                    if rd.resolution_category != 'unknown':
                        parts.append(f'    Category: {rd.resolution_category}')
                    if rd.applicability_notes:
                        parts.append(f'    Note: {rd.applicability_notes}')
        if prior.configuration_context:
            cc = prior.configuration_context
            parts.append(f'\nCONFIGURATION CONTEXT for {cc.component}:')
            if cc.relevant_params:
                for param in cc.relevant_params[:5]:
                    parts.append(f"  - {param.name}: {param.current_value or 'unknown'}")
                    if param.note:
                        parts.append(f'    ({param.note})')
            if cc.deviation_flags:
                parts.append('  DEVIATIONS FROM SUCCESSFUL CASES:')
                for flag in cc.deviation_flags:
                    parts.append(f'    - {flag}')
        if prior.diagnostic_history:
            dh = prior.diagnostic_history
            parts.append('''
DIAGNOSTIC HISTORY for this error type:''')
            parts.append(f'  - Seen {dh.total_occurrences} times, {dh.resolved_count} resolved')
            parts.append(f'  - Resolution rate: {dh.resolution_rate:.0%}')
            if dh.common_root_causes:
                parts.append('  - Common root causes:')
                for cause, freq in dh.common_root_causes[:3]:
                    parts.append(f'      {cause} ({freq:.0%})')
        if prior.documentation_context:
            parts.append('''
COMPONENT DOCUMENTATION (from data/docs/):
These are verified error-to-root-cause mappings. Matched Error-to-Root-Cause entries should get prior 0.85+. Cascade Chains show propagation paths.
''' + prior.documentation_context)
        if prior.feedback_from_similar:
            parts.append('''
USER FEEDBACK FROM SIMILAR PAST INVESTIGATIONS:''')
            parts.append('These are real user corrections from similar cases. Use them to avoid repeating past mistakes and to prioritize hypotheses that align with actual root causes.')
            for fb in prior.feedback_from_similar[:5]:
                verdict = 'CORRECT' if fb.was_correct else 'INCORRECT'
                parts.append(f'  - Case {fb.investigation_id[:8]}: {verdict}')
                if fb.actual_cause:
                    parts.append(f'    Actual cause: {fb.actual_cause}')
                if fb.what_was_wrong:
                    parts.append(f'    What was wrong: {fb.what_was_wrong}')
                if fb.suggestions:
                    parts.append(f'    Suggestion: {fb.suggestions}')
                if fb.additional_notes:
                    parts.append(f'    Note: {fb.additional_notes}')
        return '\n'.join(parts) if parts else 'No prior knowledge available'

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        question_type = context.question_type
        content: dict[str, Any] = {'possible_explanations': [], 'interpretations': [], 'key_points': [], 'answer': ''}
        from srcs.models.question import QuestionType
        if question_type == QuestionType.WHY:
            content['answer'] = self._generate_why_answer(question, context)
            content['possible_explanations'] = self._generate_explanations(question)
        elif question_type == QuestionType.TROUBLESHOOT:
            content['answer'] = self._generate_troubleshoot_theory(question, context)
            content['possible_explanations'] = self._generate_root_cause_theories(question)
        elif question_type == QuestionType.HOW_TO:
            content['answer'] = self._generate_approach_theory(question, context)
            content['interpretations'] = ['There may be multiple valid approaches depending on your context']
        else:
            content['answer'] = self._generate_general_theory(question, context)
        if content['answer']:
            content['key_points'] = self._extract_key_points(content['answer'])
        reasoning = f"Generated {len(content['possible_explanations'])} possible explanations from theoretical analysis of the question"
        confidence = 0.6
        return Contribution(persona_id='theorist', phase=PHASE_THEORIST, content=content, confidence=confidence, reasoning=reasoning)

    def _generate_why_answer(self, question: str, context: 'QuestionContext') -> str:
        question_lower = question.lower()
        if 'timeout' in question_lower:
            return 'Timeouts in artdaq typically occur due to one of several factors: 1) Hardware communication delays exceeding configured thresholds, 2) System resource contention (CPU, memory, network), 3) Incorrect timing parameters in configuration, or 4) Synchronization issues between components. The specific cause depends on which component is timing out and the operational context.'
        if 'fail' in question_lower or 'error' in question_lower:
            return 'Failures in DAQ systems can stem from multiple theoretical causes: hardware malfunctions, configuration mismatches, resource exhaustion, timing violations, or software bugs. Understanding the failure mode and checking logs for specific error codes helps narrow down the cause.'
        return 'This is an interesting question that could have multiple explanations. In DAQ systems, behaviors often result from the interaction of hardware, software configuration, and operational conditions.'

    def _generate_troubleshoot_theory(self, question: str, context: 'QuestionContext') -> str:
        return 'When troubleshooting this issue, consider multiple hypotheses: it could be a configuration problem, a hardware issue, a timing problem, or a resource constraint. Each hypothesis should be tested systematically by gathering evidence from logs, metrics, and configuration files.'

    def _generate_approach_theory(self, question: str, context: 'QuestionContext') -> str:
        return 'There are typically multiple valid approaches to this task. The best approach depends on your specific requirements, existing infrastructure, and operational constraints. Consider the trade-offs between simplicity, performance, and maintainability.'

    def _generate_general_theory(self, question: str, context: 'QuestionContext') -> str:
        return 'From a theoretical perspective, this involves understanding the underlying mechanisms and their interactions. Consider the system architecture and how different components communicate and depend on each other.'

    def _generate_explanations(self, question: str) -> list[str]:
        return ['This could be due to timing or synchronization issues', 'Resource constraints may be a contributing factor', 'Configuration settings might need adjustment', 'There may be hardware-software interaction effects']

    def _generate_root_cause_theories(self, question: str) -> list[str]:
        return ['Hardware malfunction or degradation', 'Configuration mismatch or error', 'Resource exhaustion (memory, CPU, network)', 'Timing or synchronization failure', 'Software bug or edge case']

    def _extract_key_points(self, answer: str) -> list[str]:
        points: list[str] = []
        for part in answer.split('. '):
            if len(part) > 20 and len(points) < 5:
                points.append(part.strip().rstrip('.'))
        return points