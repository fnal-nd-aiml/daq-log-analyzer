"""
File: judge.py
Purpose: Judge persona - Phase 5: Insufficiency Check.
Category: Utility
Author: artdaq team
Depends: question, prompts, artifact_renderer, artifacts_types, relevance, ...
Exports: OutcomeAssessment, JudgePersona
Complexity: High | Lines: 376
"""

import logging
from typing import TYPE_CHECKING, Any, List
from pydantic import BaseModel
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts_types import ArtifactType
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_JUDGE, Persona
if TYPE_CHECKING:
    from srcs.models.question import QuestionContext
logger = logging.getLogger(__name__)

class OutcomeAssessment(BaseModel):
    outcome: str
    confidence_score: float
    reasoning: str
    criteria_met: List[str] = []
    criteria_not_met: List[str] = []
    evidence_gaps: List[str] = []
    unresolved_concerns: List[str] = []
    recommendation: str = ''

class JudgePersona(CollaborativePersona):

    def __init__(self) -> None:
        self._llm_assessment: OutcomeAssessment | None = None

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_JUDGE]

    @property
    def traits(self) -> list[str]:
        return ['impartial', 'evaluative', 'decisive', 'fair', 'standards-driven']

    @property
    def thinking_style(self) -> str:
        return 'Judicial evaluation - applies consistent standards, weighs evidence objectively, renders verdicts based on sufficiency of proof, distinguishes certainty from probability'

    async def prepare(self, context: InvestigationContext) -> None:
        pass

    async def contribute(self, context: InvestigationContext) -> Contribution:
        if context.llm is not None:
            llm_assessment = await self._assess_with_llm(context)
            if llm_assessment is not None:
                self._llm_assessment = llm_assessment
                content = self._build_content_from_llm(llm_assessment)
                return Contribution(persona_id='judge', phase=PHASE_JUDGE, content=content, confidence=llm_assessment.confidence_score, reasoning=llm_assessment.reasoning)
        assessment = self._assess_sufficiency_rules(context)
        confidence_val = assessment.get('confidence', 0.5)
        confidence = float(confidence_val) if isinstance(confidence_val, (int, float)) else 0.5
        return Contribution(persona_id='judge', phase=PHASE_JUDGE, content=assessment, confidence=confidence, reasoning=self._build_reasoning_rules(assessment))

    async def _assess_with_llm(self, context: InvestigationContext) -> OutcomeAssessment | None:
        binder = context.binder
        from srcs.workbinder.artifact_renderer import render_challenge as _render_ch
        from srcs.workbinder.artifact_renderer import render_evidence as _render_e
        from srcs.workbinder.artifact_renderer import render_hypothesis as _render_h
        from srcs.workbinder.relevance import select_artifacts as select_relevant
        hypotheses_artifacts = binder.get_hypotheses()
        if hypotheses_artifacts:
            hypotheses_artifacts.sort(key=lambda h: h.score, reverse=True)
            top_hypothesis = hypotheses_artifacts[0].description
            top_score = hypotheses_artifacts[0].score
            selected_hyps = select_relevant(binder, 'judge', ArtifactType.HYPOTHESIS_ARTIFACT)
            if selected_hyps:
                hypotheses_summary = '\n'.join([_render_h(h) for h in selected_hyps])
            else:
                hypotheses_summary = '\n'.join([f'- {h.description} (score: {h.score:.2f})' for h in hypotheses_artifacts[:5]])
        else:
            hypotheses_summary = 'No hypotheses generated'
            top_hypothesis = 'N/A'
            top_score = 0.0
        evidence_artifacts = binder.get_evidence_items()
        strong_count = sum((1 for e in evidence_artifacts if e.strength == 'STRONG'))
        moderate_count = sum((1 for e in evidence_artifacts if e.strength == 'MODERATE'))
        weak_count = sum((1 for e in evidence_artifacts if e.strength == 'WEAK'))
        selected_evs = select_relevant(binder, 'judge', ArtifactType.EVIDENCE_ARTIFACT)
        if selected_evs:
            evidence_details = '\n'.join([_render_e(e) for e in selected_evs])
        elif evidence_artifacts:
            evidence_details = '\n'.join([f'- [{e.strength}] {e.evidence_type}: {e.content}' for e in evidence_artifacts[:10]])
        else:
            evidence_details = 'No evidence collected'
        chain_artifacts = binder.get_causal_chains()
        if chain_artifacts:
            chains_summary = '\n'.join([f'- Hypothesis {c.hypothesis_id[:8]}: {len(c.steps)} steps, validity {c.logical_validity:.0%}, coverage {c.evidence_coverage:.0%}' for c in chain_artifacts])
        else:
            chains_summary = 'No causal chains constructed'
        challenge_artifacts = binder.get_challenges()
        unresolved_high = sum((1 for c in challenge_artifacts if c.severity == 'HIGH' and (not c.resolved)))
        unresolved_medium = sum((1 for c in challenge_artifacts if c.severity == 'MEDIUM' and (not c.resolved)))
        selected_chs = select_relevant(binder, 'judge', ArtifactType.CHALLENGE)
        if selected_chs:
            challenges_summary = '\n'.join([_render_ch(c) for c in selected_chs])
        elif challenge_artifacts:
            challenges_summary = '\n'.join([f"- [{c.severity}] {c.content} ({('resolved' if c.resolved else 'unresolved')})" for c in challenge_artifacts])
        else:
            challenges_summary = 'No adversarial challenges raised'
        error_message = context.error.message if context.error else 'Unknown error'
        has_context_logs = any((e.evidence_type == 'log' for e in evidence_artifacts))
        evidence_mode = 'FULL-CONTEXT' if has_context_logs else 'LIMITED-INPUT'
        detective_contribution = None
        detective_contributions = binder.get_persona_contributions(persona_id='detective')
        if detective_contributions:
            detective_contribution = detective_contributions[-1].content
        evidence_quality_score = 'N/A'
        quality_strength_score = 'N/A'
        quality_diversity_score = 'N/A'
        quality_coverage_score = 'N/A'
        quality_discrimination_score = 'N/A'
        evidence_types_present = 'N/A'
        evidence_types_missing = 'N/A'
        if detective_contribution and isinstance(detective_contribution, dict):
            qs = detective_contribution.get('evidence_quality_score', {})
            if qs:
                evidence_quality_score = f"{qs.get('overall_score', 0):.2f}"
                quality_strength_score = f"{qs.get('strength_score', 0):.0%}"
                quality_diversity_score = f"{qs.get('diversity_score', 0):.0%}"
                quality_coverage_score = f"{qs.get('coverage_score', 0):.0%}"
                quality_discrimination_score = f"{qs.get('discrimination_score', 0):.0%}"
                types_present = qs.get('evidence_types_present', [])
                types_missing = qs.get('evidence_types_missing', [])
                evidence_types_present = ', '.join(types_present) if types_present else 'none'
                evidence_types_missing = ', '.join(types_missing) if types_missing else 'none'
        evidence_gap_analysis = 'No gap analysis available'
        evidence_gap_count = 0
        most_critical_gap = 'N/A'
        if detective_contribution and isinstance(detective_contribution, dict):
            gap_info = detective_contribution.get('evidence_gap_analysis', {})
            if gap_info:
                gaps = gap_info.get('gaps', [])
                evidence_gap_count = len(gaps)
                gap_lines = []
                for gap in gaps[:5]:
                    h_desc = gap.get('hypothesis_description', 'Unknown')
                    gap_type = gap.get('gap_type', 'unknown')
                    severity = gap.get('severity', 'low')
                    gap_lines.append(f'- [{severity.upper()}] {h_desc}: {gap_type}')
                evidence_gap_analysis = '\n'.join(gap_lines) if gap_lines else 'No gaps identified'
                high_gaps = [g for g in gaps if g.get('severity') == 'high']
                if high_gaps:
                    critical = high_gaps[0]
                    most_critical_gap = f"{critical.get('hypothesis_description', 'Unknown')} has {critical.get('gap_type', 'unknown')}"
                elif gaps:
                    first_gap = gaps[0]
                    most_critical_gap = f"{first_gap.get('hypothesis_description', 'Unknown')} has {first_gap.get('gap_type', 'unknown')}"
        alternative_paths = 'No alternative paths suggested'
        if detective_contribution and isinstance(detective_contribution, dict):
            alt_info = detective_contribution.get('alternative_paths', {})
            if alt_info:
                paths = alt_info.get('paths', [])
                if paths:
                    path_lines = []
                    for path in paths[:5]:
                        desc = path.get('description', '')
                        benefit = path.get('expected_benefit', '')
                        difficulty = path.get('difficulty', '')
                        line = f'- {desc}'
                        if benefit:
                            line += f' ({benefit})'
                        if difficulty:
                            line += f' [Difficulty: {difficulty}]'
                        path_lines.append(line)
                    alternative_paths = '\n'.join(path_lines)
        try:
            user_prompt_template = get_user_prompt(UserPromptType.OUTCOME_ASSESSMENT)
            prompt = user_prompt_template.format(error_message=error_message, hypotheses_summary=hypotheses_summary, top_hypothesis=top_hypothesis, top_score=f'{top_score:.2f}', evidence_count=len(evidence_artifacts), strong_evidence_count=strong_count, moderate_evidence_count=moderate_count, weak_evidence_count=weak_count, evidence_details=evidence_details, causal_chains_summary=chains_summary, challenges_summary=challenges_summary, unresolved_high_count=unresolved_high, unresolved_medium_count=unresolved_medium, has_context_logs='Yes' if has_context_logs else 'No', evidence_mode=evidence_mode, evidence_quality_score=evidence_quality_score, quality_strength_score=quality_strength_score, quality_diversity_score=quality_diversity_score, quality_coverage_score=quality_coverage_score, quality_discrimination_score=quality_discrimination_score, evidence_types_present=evidence_types_present, evidence_types_missing=evidence_types_missing, evidence_gap_analysis=evidence_gap_analysis, evidence_gap_count=str(evidence_gap_count), most_critical_gap=most_critical_gap, alternative_paths=alternative_paths)
        except Exception as e:
            logger.warning(f'Failed to format outcome prompt: {e}')
            return None
        try:
            system_prompt = get_system_prompt(SystemPromptType.JUDGE)
            response = await self._call_llm_structured(context=context, prompt=prompt, response_model=OutcomeAssessment, system_prompt=system_prompt, prompt_key='outcome_assessment')
            return response
        except Exception as e:
            logger.warning(f'LLM outcome assessment failed: {e}')
            return None

    def _build_content_from_llm(self, assessment: OutcomeAssessment) -> dict[str, Any]:
        return {'outcome': assessment.outcome, 'confidence': assessment.confidence_score, 'reasoning': assessment.reasoning, 'criteria_met': assessment.criteria_met, 'criteria_not_met': assessment.criteria_not_met, 'evidence_gaps': assessment.evidence_gaps, 'unresolved_concerns': assessment.unresolved_concerns, 'recommendation': assessment.recommendation, 'assessment_method': 'llm'}

    def _assess_sufficiency_rules(self, context: InvestigationContext) -> dict[str, str | float | int | bool | list[str]]:
        reasoning_gaps: list[str] = []
        assessment: dict[str, str | float | int | bool | list[str]] = {'outcome': 'INSUFFICIENT', 'confidence': 0.5, 'strong_evidence_count': 0, 'hypothesis_support': 0.0, 'challenges_resolved': True, 'reasoning_gaps': reasoning_gaps, 'assessment_method': 'rules'}
        strong_evidence_count = 0
        if context.evidence and context.evidence.items:
            strong = context.evidence.get_strong_evidence()
            strong_evidence_count = len(strong)
            assessment['strong_evidence_count'] = strong_evidence_count
        if context.hypotheses:
            supported = [h for h in context.hypotheses if h.supporting_evidence_ids and h.score > 0.5]
            if context.hypotheses:
                assessment['hypothesis_support'] = len(supported) / len(context.hypotheses)
            if supported:
                best = max(supported, key=lambda h: h.score)
                if best.score > 0.7 and strong_evidence_count >= 2:
                    assessment['outcome'] = 'CONFIDENT'
                    assessment['confidence'] = 0.85
                elif best.score > 0.5:
                    assessment['outcome'] = 'PROBABLE'
                    assessment['confidence'] = 0.65
        challenge_artifacts = context.binder.get_challenges() if context.binder else []
        if challenge_artifacts:
            unresolved_high = sum((1 for c in challenge_artifacts if c.severity == 'HIGH' and (not c.resolved)))
            unresolved_medium = sum((1 for c in challenge_artifacts if c.severity == 'MEDIUM' and (not c.resolved)))
            unresolved_total = sum((1 for c in challenge_artifacts if not c.resolved))
            if unresolved_total > 0:
                assessment['challenges_resolved'] = False
            if unresolved_high > 0:
                if assessment['outcome'] == 'CONFIDENT':
                    assessment['outcome'] = 'PROBABLE'
                    assessment['confidence'] = 0.6
            if assessment['outcome'] == 'CONFIDENT' and unresolved_medium >= 3:
                assessment['outcome'] = 'PROBABLE'
                assessment['confidence'] = 0.65
        if not context.evidence or not context.evidence.items:
            reasoning_gaps.append('No evidence collected')
        if not context.hypotheses:
            reasoning_gaps.append('No hypotheses generated')
        return assessment

    def _build_reasoning_rules(self, assessment: dict) -> str:
        parts = [f"Outcome: {assessment['outcome']}"]
        parts.append(f"Strong evidence: {assessment['strong_evidence_count']} pieces")
        if assessment['hypothesis_support'] > 0:
            parts.append(f"Hypothesis support: {assessment['hypothesis_support']:.0%}")
        if not assessment['challenges_resolved']:
            parts.append('Unresolved challenges remain')
        if assessment['reasoning_gaps']:
            parts.append(f"Gaps: {', '.join(assessment['reasoning_gaps'])}")
        return '; '.join(parts)

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights: list[str] = []
        uncertainties: list[str] = []
        suggestions: list[str] = []
        if self._llm_assessment is not None:
            assessment = self._llm_assessment
            if assessment.outcome == 'CONFIDENT':
                insights.append('Evidence meets threshold for confident conclusion')
                if assessment.criteria_met:
                    insights.append(f'Met {len(assessment.criteria_met)} decision criteria')
            elif assessment.outcome == 'PROBABLE':
                insights.append('Evidence supports probable conclusion')
                suggestions.append('Additional evidence could strengthen confidence')
            elif assessment.outcome == 'UNCERTAIN':
                uncertainties.append('Multiple hypotheses remain viable')
                suggestions.append('Seek discriminating evidence')
            elif assessment.outcome == 'CONTRADICTORY':
                uncertainties.append('Contradicting evidence present')
                suggestions.append('Resolve conflicting evidence before concluding')
            elif assessment.outcome == 'INSUFFICIENT':
                uncertainties.append('Evidence insufficient for conclusion')
                suggestions.append('Additional investigation required')
            for gap in assessment.evidence_gaps[:3]:
                uncertainties.append(f'Gap: {gap}')
            for concern in assessment.unresolved_concerns[:3]:
                uncertainties.append(f'Concern: {concern}')
            if assessment.recommendation:
                suggestions.append(assessment.recommendation)
        else:
            rule_assessment = self._assess_sufficiency_rules(context)
            if rule_assessment['outcome'] == 'CONFIDENT':
                insights.append('Evidence meets threshold for confident conclusion')
            elif rule_assessment['outcome'] == 'PROBABLE':
                insights.append('Evidence supports probable conclusion')
                suggestions.append('Additional evidence could strengthen confidence')
            elif rule_assessment['outcome'] == 'INSUFFICIENT':
                uncertainties.append('Evidence insufficient for conclusion')
                suggestions.append('Additional investigation may be needed')
            reasoning_gaps = rule_assessment.get('reasoning_gaps', [])
            if isinstance(reasoning_gaps, list):
                for gap in reasoning_gaps:
                    uncertainties.append(str(gap))
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f'I will consider your input, {other.metadata.name}. However, my assessment must be based on the evidence presented and the standards we apply consistently.'

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        if contribution.confidence > 0.8:
            if 'evidence' not in str(contribution.reasoning).lower():
                issues.append('High confidence claim lacks explicit evidence citation')
                recommendations.append('Claims should be supported by cited evidence')
        content_str = str(contribution.content).lower()
        if 'certain' in content_str and contribution.confidence < 0.9:
            issues.append('Certainty language inconsistent with confidence level')
        if contribution.reasoning:
            strengths.append('Reasoning provided for assessment')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='MEDIUM' if issues else 'LOW', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        has_reasoning = bool(contribution.reasoning)
        appropriate_confidence = contribution.confidence <= 0.9
        return has_reasoning and appropriate_confidence

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        content: dict = {'quality_assessment': {}, 'reliability_score': 0.0, 'answer': '', 'key_points': [], 'recommendations': []}
        assessment = self._assess_contributions(context)
        content['quality_assessment'] = assessment
        content['reliability_score'] = self._calculate_reliability(assessment)
        content['recommendations'] = self._generate_recommendations(assessment, context)
        content['answer'] = self._formulate_balanced_answer(question, assessment, context)
        content['key_points'] = self._extract_key_points(assessment)
        reasoning = f"Assessed {len(context.contributions)} contributions; reliability score: {content['reliability_score']:.0%}"
        confidence = content['reliability_score']
        return Contribution(persona_id='judge', phase=PHASE_JUDGE, content=content, confidence=confidence, reasoning=reasoning)

    def _assess_contributions(self, context: 'QuestionContext') -> dict[str, dict]:
        assessment: dict[str, dict] = {}
        for contrib in context.contributions:
            persona_id = contrib.persona_id
            assessment[persona_id] = {'confidence': contrib.confidence, 'has_reasoning': bool(contrib.reasoning), 'has_evidence': self._check_evidence(contrib), 'has_caveats': self._check_caveats(contrib), 'quality_score': self._score_contribution(contrib)}
        return assessment

    def _check_evidence(self, contrib: Contribution) -> bool:
        content_str = str(contrib.content).lower()
        reasoning_str = str(contrib.reasoning).lower()
        evidence_terms = ['evidence', 'found', 'observed', 'shows', 'indicates']
        return any((term in content_str or term in reasoning_str for term in evidence_terms))

    def _check_caveats(self, contrib: Contribution) -> bool:
        content_str = str(contrib.content).lower()
        caveat_terms = ['caveat', 'however', 'note that', 'limitation', 'assuming']
        return any((term in content_str for term in caveat_terms))

    def _score_contribution(self, contrib: Contribution) -> float:
        score = 0.5
        if contrib.reasoning:
            score += 0.1
        if self._check_evidence(contrib):
            score += 0.15
        if 0.3 <= contrib.confidence <= 0.8:
            score += 0.1
        if self._check_caveats(contrib):
            score += 0.1
        return min(score, 1.0)

    def _calculate_reliability(self, assessment: dict[str, dict]) -> float:
        if not assessment:
            return 0.3
        scores = [float(a['quality_score']) for a in assessment.values()]
        return sum(scores) / len(scores)

    def _generate_recommendations(self, assessment: dict[str, dict], context: 'QuestionContext') -> list[str]:
        recommendations = []
        has_evidence_contrib = any((a['has_evidence'] for a in assessment.values()))
        has_caveats_contrib = any((a['has_caveats'] for a in assessment.values()))
        if not has_evidence_contrib:
            recommendations.append('Consider seeking additional evidence to support the answer')
        if not has_caveats_contrib:
            recommendations.append('Note any important caveats or limitations')
        if len(assessment) < 3:
            recommendations.append('More perspectives would increase confidence')
        return recommendations

    def _formulate_balanced_answer(self, question: str, assessment: dict[str, dict], context: 'QuestionContext') -> str:
        reliability = self._calculate_reliability(assessment)
        if reliability > 0.7:
            return 'The panel has provided high-quality responses with good evidence and reasoning. The combined answer should be reliable for standard use cases, though verification is recommended for critical applications.'
        elif reliability > 0.5:
            return "The panel's responses are reasonably reliable but could benefit from additional evidence or verification. Use the provided information as a starting point and validate in your specific context."
        else:
            return "The available information is limited. The panel's responses should be treated as preliminary guidance. Consider seeking additional sources or expert consultation for important decisions."

    def _extract_key_points(self, assessment: dict[str, dict]) -> list[str]:
        points = []
        best_scores = sorted([(pid, a['quality_score']) for pid, a in assessment.items()], key=lambda x: x[1], reverse=True)
        for pid, score in best_scores[:2]:
            points.append(f'Strong contribution from {pid} (score: {score:.0%})')
        return points