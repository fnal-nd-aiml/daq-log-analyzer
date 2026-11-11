"""
File: skeptic.py
Purpose: Skeptic persona - Phase 4: Adversarial Review.
Category: Utility
Author: artdaq team
Depends: llm, models, investigation, question, prompts, ...
Exports: SkepticPersona, MAX_HYPOTHESES_TO_REVIEW, MIN_REVIEW_SCORE
Complexity: High | Lines: 397
"""

from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING, Any
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_SKEPTIC, Persona
if TYPE_CHECKING:
    from srcs.llm import LLMProvider
    from srcs.models.question import QuestionContext
    from srcs.workbinder import WorkBinder
from srcs.models import CausalChain, Evidence, Hypothesis, PriorKnowledge
from srcs.models.investigation import Challenge
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts.parsers import CausalChainParser, ChallengeResponse
logger = logging.getLogger(__name__)
MAX_HYPOTHESES_TO_REVIEW = 3
MIN_REVIEW_SCORE = 0.2

class SkepticPersona(CollaborativePersona):

    def __init__(self) -> None:
        self._llm: LLMProvider | None = None
        self._generated_challenges: list[Challenge] = []
        self._documentation_context: str = ''

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_SKEPTIC]

    @property
    def traits(self) -> list[str]:
        return ['skeptical', 'challenging', 'contrarian', 'thorough', 'critical']

    @property
    def thinking_style(self) -> str:
        return 'Adversarial analysis - challenges assumptions, identifies weaknesses, proposes alternative explanations, stress-tests conclusions before acceptance'

    async def prepare(self, context: InvestigationContext) -> None:
        if context.llm is not None:
            self._llm = context.llm
        else:
            logger.warning('LLM not available - adversarial review will be limited')
            self._llm = None

    async def contribute(self, context: InvestigationContext) -> Contribution:
        challenges = await self._conduct_review(context)
        self._generated_challenges = challenges
        content = self._build_content_dict(challenges)
        confidence = self._calculate_confidence(challenges)
        return Contribution(persona_id='skeptic', phase=PHASE_SKEPTIC, content=content, confidence=confidence, reasoning=self._build_reasoning_from_challenges(challenges))

    async def _conduct_review(self, context: InvestigationContext) -> list[Challenge]:
        if self._llm is None:
            await self.prepare(context)
        if context.prior_knowledge and context.prior_knowledge.documentation_context:
            self._documentation_context = context.prior_knowledge.documentation_context
        else:
            self._documentation_context = '(no component documentation available)'
        binder = context.binder
        try:
            challenges: list[Challenge] = await self._review_from_binder(binder=binder)
            return challenges
        except Exception as e:
            logger.warning(f'Adversarial review failed: {e}')
            return []

    def _build_content_dict(self, challenges: list[Challenge]) -> dict[str, Any]:
        if not challenges:
            return {'challenges_raised': 0, 'high_severity': 0, 'medium_severity': 0, 'low_severity': 0, 'challenge_types': [], 'unresolved': 0, 'resolved': 0}
        high_severity = sum((1 for c in challenges if c.severity == 'HIGH'))
        medium_severity = sum((1 for c in challenges if c.severity == 'MEDIUM'))
        low_severity = sum((1 for c in challenges if c.severity == 'LOW'))
        resolved = sum((1 for c in challenges if c.resolved))
        unresolved = len(challenges) - resolved
        challenge_types = list({c.challenge_type for c in challenges})
        return {'challenges_raised': len(challenges), 'high_severity': high_severity, 'medium_severity': medium_severity, 'low_severity': low_severity, 'challenge_types': challenge_types, 'unresolved': unresolved, 'resolved': resolved, 'challenge_details': [{'type': c.challenge_type, 'severity': c.severity, 'resolved': c.resolved, 'content_preview': c.content[:100] if c.content else ''} for c in challenges[:5]]}

    def _calculate_confidence(self, challenges: list[Challenge]) -> float:
        if not challenges:
            return 0.5
        high_count = sum((1 for c in challenges if c.severity == 'HIGH'))
        medium_count = sum((1 for c in challenges if c.severity == 'MEDIUM'))
        if high_count >= 2:
            return 0.85
        elif high_count >= 1:
            return 0.75
        elif medium_count >= 2:
            return 0.65
        elif challenges:
            return 0.55
        else:
            return 0.5

    def _build_reasoning_from_challenges(self, challenges: list[Challenge]) -> str:
        if not challenges:
            return 'No major challenges identified - conclusions appear sound'
        parts: list[str] = []
        parts.append(f'Raised {len(challenges)} challenge(s)')
        high_count = sum((1 for c in challenges if c.severity == 'HIGH'))
        medium_count = sum((1 for c in challenges if c.severity == 'MEDIUM'))
        low_count = sum((1 for c in challenges if c.severity == 'LOW'))
        severity_parts = []
        if high_count > 0:
            severity_parts.append(f'{high_count} HIGH')
        if medium_count > 0:
            severity_parts.append(f'{medium_count} MEDIUM')
        if low_count > 0:
            severity_parts.append(f'{low_count} LOW')
        if severity_parts:
            parts.append(f"severity: {', '.join(severity_parts)}")
        resolved = sum((1 for c in challenges if c.resolved))
        unresolved = len(challenges) - resolved
        if unresolved > 0:
            parts.append(f'{unresolved} require(s) resolution')
        types = list({c.challenge_type for c in challenges})
        if types:
            parts.append(f"types: {', '.join(types)}")
        return '; '.join(parts)

    async def _review(self, hypothesis: Hypothesis, chain: CausalChain, evidence: Evidence, prior: PriorKnowledge, binder: 'WorkBinder', code_context: str='') -> list[Challenge]:
        challenges = []
        try:
            llm_challenges = await self._generate_challenges(hypothesis, chain, evidence, code_context=code_context)
            challenges.extend(llm_challenges)
        except Exception as e:
            logger.warning(f'Failed to generate LLM challenges: {e}')
        structural = self._check_structural_issues(chain, evidence)
        existing_types = {c.challenge_type for c in challenges}
        for sc in structural:
            if sc.challenge_type not in existing_types:
                challenges.append(sc)
                existing_types.add(sc.challenge_type)
        for challenge in challenges:
            if challenge.requires_response or challenge.severity == 'MEDIUM':
                resolution = self._attempt_resolution(challenge, hypothesis, chain, evidence)
                if resolution:
                    challenge.resolution = resolution
                    challenge.resolved = True
        for challenge in challenges:
            binder.add_challenge(target_hypothesis_id=hypothesis.id, challenge_type=challenge.challenge_type, content=challenge.content, severity=challenge.severity, requires_response=challenge.requires_response, resolved=challenge.resolved, resolution=challenge.resolution, created_by='Skeptic', phase=4)
        return challenges

    async def _review_from_binder(self, binder: 'WorkBinder') -> list[Challenge]:
        hypothesis_artifacts = binder.get_hypotheses()
        if not hypothesis_artifacts:
            logger.warning('No hypotheses found in binder for adversarial review')
            return []
        hypothesis_artifacts.sort(key=lambda h: h.score, reverse=True)
        to_review = [ha for ha in hypothesis_artifacts[:MAX_HYPOTHESES_TO_REVIEW] if ha.score >= MIN_REVIEW_SCORE]
        if not to_review:
            to_review = [hypothesis_artifacts[0]]
        chain_artifacts = binder.get_causal_chains()
        chains_by_hypothesis: dict[str, CausalChain] = {}
        for ca in chain_artifacts:
            if ca.hypothesis_id not in chains_by_hypothesis:
                chains_by_hypothesis[ca.hypothesis_id] = CausalChainParser.chain_from_artifact(ca)
        evidence_artifacts = binder.get_evidence_items()
        evidence = Evidence()
        for ea in evidence_artifacts:
            from srcs.models import EvidenceItem
            item = EvidenceItem(id=ea.id, evidence_type=ea.evidence_type, content=ea.content, source=ea.source, strength=ea.strength, found=True)
            evidence.add(item)
        prior = PriorKnowledge()
        code_context = self._format_code_context(binder)

        async def _review_one(ha: Any) -> list[Challenge]:
            hypothesis = Hypothesis(id=ha.id, description=ha.description, source=ha.source, prior=ha.prior_probability, score=ha.score, supporting_evidence_ids=ha.supporting_evidence_ids, contradicting_evidence_ids=ha.contradicting_evidence_ids, binder_artifact_id=ha.id)
            chain = chains_by_hypothesis.get(ha.id, CausalChain(hypothesis_id=ha.id))
            return await self._review(hypothesis, chain, evidence, prior, binder=binder, code_context=code_context)
        results = await asyncio.gather(*(_review_one(ha) for ha in to_review), return_exceptions=True)
        all_challenges: list[Challenge] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning('Adversarial review of a hypothesis failed: %s', result)
            else:
                all_challenges.extend(result)
        return all_challenges

    async def _generate_challenges(self, hypothesis: Hypothesis, chain: CausalChain, evidence: Evidence, code_context: str='') -> list[Challenge]:
        if self._llm is None:
            return []
        available_types = set((e.evidence_type for e in evidence.items.values())) if evidence.items else set()
        evidence_availability_parts = []
        if 'log' not in available_types:
            evidence_availability_parts.append('- Log files: NOT AVAILABLE (do not challenge for missing logs)')
        else:
            evidence_availability_parts.append('- Log files: Available')
        if 'code' in available_types:
            evidence_availability_parts.append('- Code analysis: Available')
        else:
            evidence_availability_parts.append('- Code analysis: NOT AVAILABLE')
        if 'numeric' in available_types or 'timeout' in available_types:
            evidence_availability_parts.append('- Numeric/timeout analysis: Available')
        evidence_availability_str = '\n'.join(evidence_availability_parts) if evidence_availability_parts else 'All evidence types available'
        template = get_user_prompt(UserPromptType.ADVERSARIAL_REVIEW)
        prompt = template.format(hypothesis=hypothesis.description, chain=self._format_chain(chain), evidence=evidence.summary(), evidence_availability=evidence_availability_str, documentation_context=self._documentation_context)
        if code_context:
            prompt += f'\n\n## Code Context for Claim Validation\nUse the following code artifacts to verify claims in the causal chain:\n{code_context}'
        try:
            system_prompt = get_system_prompt(SystemPromptType.SKEPTIC)
            response = await self._llm.generate_structured(prompt, ChallengeResponse, system_prompt=system_prompt)
        except Exception as e:
            logger.warning(f'Structured challenge generation failed: {e}')
            return []
        challenges = []
        for item in response.challenges:
            challenge_type = item.type
            if challenge_type == 'missing':
                challenge_type = 'missing_evidence'
            challenges.append(Challenge(challenge_type=challenge_type, content=item.content, severity=item.severity, requires_response=item.severity == 'HIGH'))
        return challenges

    def _check_structural_issues(self, chain: CausalChain, evidence: Evidence) -> list[Challenge]:
        challenges = []
        if chain.evidence_coverage < 0.5:
            challenges.append(Challenge(challenge_type='weak_evidence', content=f'Only {chain.evidence_coverage:.0%} of chain steps have evidence. This indicates significant gaps in the causal reasoning.', severity='HIGH', requires_response=True))
        assumption_count = len(chain.gaps)
        if assumption_count > len(chain.steps) / 2:
            challenges.append(Challenge(challenge_type='missing_evidence', content=f"Chain has {assumption_count} assumptions out of {len(chain.steps)} steps. Key gaps: {', '.join(chain.gaps[:3])}", severity='MEDIUM', requires_response=True))
        if chain.logical_validity < 0.5:
            challenges.append(Challenge(challenge_type='logical_flaw', content=f'Only {chain.logical_validity:.0%} of steps have explanatory mechanisms. The causal reasoning may be incomplete.', severity='MEDIUM', requires_response=False))
        strong_evidence = evidence.get_strong_evidence()
        if not strong_evidence:
            challenges.append(Challenge(challenge_type='weak_evidence', content='No strong evidence found supporting the conclusion. All evidence is weak or moderate strength.', severity='MEDIUM', requires_response=False))
        return challenges

    def _attempt_resolution(self, challenge: Challenge, hypothesis: Hypothesis, chain: CausalChain, evidence: Evidence) -> str | None:
        strong = evidence.get_strong_evidence()
        moderate = [e for e in evidence.items.values() if e.strength == 'MODERATE']
        if challenge.challenge_type == 'weak_evidence':
            if strong:
                return f'Strong evidence exists: {strong[0].content} This provides solid support for the conclusion.'
            if len(moderate) >= 3:
                return f'While no single piece of strong evidence exists, {len(moderate)} pieces of moderate evidence provide cumulative support.'
        if challenge.challenge_type == 'alternative':
            if hypothesis.score > 0.6:
                return f'The hypothesis score of {hypothesis.score:.0%} indicates strong evidence support relative to alternatives.'
        if challenge.challenge_type == 'logical_flaw':
            if chain.logical_validity > 0.7:
                return f'Chain logical validity is {chain.logical_validity:.0%}, indicating well-explained causal mechanisms.'
        if challenge.challenge_type == 'missing_evidence':
            if strong:
                return f'Strong evidence available ({len(strong)} items) compensates for assumptions in the chain.'
            if hypothesis.score > 0.6 and len(moderate) >= 2:
                return f'Hypothesis score ({hypothesis.score:.0%}) with {len(moderate)} moderate evidence items provides sufficient support despite chain assumptions.'
        if challenge.severity == 'MEDIUM' and hypothesis.score > 0.7:
            if strong or len(moderate) >= 3:
                evidence_desc = f'{len(strong)} strong' if strong else f'{len(moderate)} moderate'
                return f'Hypothesis score ({hypothesis.score:.0%}) with {evidence_desc} evidence items addresses this concern.'
        return None

    def _format_chain(self, chain: CausalChain) -> str:
        lines = []
        for s in chain.steps:
            evidence_str = f'evidence: {s.evidence_strength}'
            if s.is_assumption:
                evidence_str = 'ASSUMPTION'
            lines.append(f'{s.step_order}. {s.claim} ({evidence_str})')
            if s.mechanism:
                lines.append(f'   Mechanism: {s.mechanism[:80]}')
        return '\n'.join(lines) if lines else 'No chain steps'

    def _format_code_context(self, binder: 'WorkBinder') -> str:
        from srcs.workbinder.relevance import render_selected_artifacts
        return render_selected_artifacts(binder, 'skeptic')

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights: list[str] = []
        uncertainties: list[str] = []
        suggestions: list[str] = []
        challenges = self._generated_challenges
        if challenges:
            high_severity = [c for c in challenges if c.severity == 'HIGH']
            if high_severity:
                insights.append(f'Identified {len(high_severity)} high-severity issue(s) that could undermine the conclusion')
            resolved = [c for c in challenges if c.resolved]
            unresolved = [c for c in challenges if not c.resolved]
            if resolved:
                insights.append(f'{len(resolved)} challenge(s) were successfully resolved')
            if unresolved:
                unresolved_high = [c for c in unresolved if c.severity == 'HIGH']
                if unresolved_high:
                    uncertainties.append(f'{len(unresolved_high)} HIGH-severity challenge(s) remain unresolved')
                    suggestions.append('Additional evidence needed to address critical challenges')
                else:
                    uncertainties.append(f'{len(unresolved)} challenge(s) remain unresolved')
            evidence_challenges = [c for c in challenges if 'evidence' in c.challenge_type.lower()]
            logic_challenges = [c for c in challenges if 'logic' in c.challenge_type.lower()]
            if evidence_challenges:
                insights.append(f'Evidence quality challenged {len(evidence_challenges)} time(s)')
            if logic_challenges:
                insights.append(f'Logical reasoning challenged {len(logic_challenges)} time(s)')
        else:
            if context.contributions:
                high_confidence = [c for c in context.contributions if c.confidence > 0.8]
                if high_confidence:
                    insights.append(f'{len(high_confidence)} high-confidence claims passed scrutiny')
                else:
                    insights.append('Conclusions appropriately cautious - no major challenges needed')
            else:
                uncertainties.append('Nothing to challenge yet')
            if context.hypotheses:
                rejected = [h for h in context.hypotheses if h.status == 'rejected']
                if not rejected:
                    uncertainties.append('No hypotheses were rejected during investigation')
                    suggestions.append('Consider whether all hypotheses received adequate scrutiny')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f'But wait, {other.metadata.name}. Have you considered what happens if your assumption is wrong? Let me challenge that assumption...'

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        if contribution.confidence > 0.9:
            issues.append('Extremely high confidence - what would prove this wrong?')
            recommendations.append('Identify falsification criteria for this conclusion')
        if contribution.confidence > 0.7:
            issues.append("Consider: what alternative explanations haven't been ruled out?")
        content_str = str(contribution.content).lower()
        if 'certain' in content_str or 'definite' in content_str:
            issues.append('Certainty language may be premature')
            recommendations.append('Acknowledge remaining uncertainty')
        if 'alternative' in content_str or 'however' in content_str:
            strengths.append('Shows awareness of alternative views')
        if 'caveat' in content_str or 'limitation' in content_str:
            strengths.append('Acknowledges limitations')
        severity = 'HIGH' if contribution.confidence > 0.9 else 'MEDIUM'
        return Critique(target_contribution=contribution, issues=issues if issues else ['No major issues, but maintain vigilance'], strengths=strengths, severity=severity if issues else 'LOW', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        content_str = str(contribution.content).lower()
        reasoning_str = str(contribution.reasoning).lower()
        shows_humility = any((term in content_str or term in reasoning_str for term in ['may', 'possible', 'caveat', 'limitation', 'uncertain']))
        return shows_humility and contribution.confidence < 0.9

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        content: dict = {'caveats': [], 'edge_cases': [], 'alternative_considerations': [], 'answer': '', 'potential_issues': []}
        prior_issues = self._analyze_prior_contributions(context)
        content['potential_issues'] = prior_issues
        content['caveats'] = self._generate_caveats(question, context)
        content['edge_cases'] = self._identify_edge_cases(question)
        content['alternative_considerations'] = self._suggest_alternatives(question, context)
        content['answer'] = self._formulate_critical_answer(question, context)
        reasoning = f"Identified {len(content['caveats'])} caveats and {len(content['edge_cases'])} edge cases to consider"
        confidence = 0.7
        return Contribution(persona_id='skeptic', phase=PHASE_SKEPTIC, content=content, confidence=confidence, reasoning=reasoning)

    def _analyze_prior_contributions(self, context: 'QuestionContext') -> list[str]:
        issues = []
        for contrib in context.contributions:
            if contrib.confidence > 0.8:
                issues.append(f'High confidence ({contrib.confidence:.0%}) from {contrib.persona_id} may be premature')
            content_str = str(contrib.content).lower()
            if 'caveat' not in content_str and 'however' not in content_str:
                issues.append(f"{contrib.persona_id}'s contribution lacks caveats")
        return issues[:3]

    def _generate_caveats(self, question: str, context: 'QuestionContext') -> list[str]:
        caveats = []
        question_lower = question.lower()
        caveats.append('Answers may vary depending on specific artdaq version and configuration')
        if 'timeout' in question_lower:
            caveats.append('Timeout values that work in one environment may not work in another')
            caveats.append('Increasing timeouts may mask underlying performance issues')
        if 'config' in question_lower:
            caveats.append('Configuration changes should be tested in a non-production environment first')
        if 'error' in question_lower or 'fail' in question_lower:
            caveats.append('The visible error may be a symptom of a deeper underlying issue')
        if not context.related_logs:
            caveats.append('Without log data, root cause identification is speculative')
        return caveats[:4]

    def _identify_edge_cases(self, question: str) -> list[str]:
        edge_cases = []
        question_lower = question.lower()
        edge_cases.append('High data rate scenarios')
        edge_cases.append('System startup/shutdown transitions')
        edge_cases.append('Network congestion or interruption')
        if 'boardreader' in question_lower:
            edge_cases.append('Hardware that intermittently fails')
        if 'eventbuilder' in question_lower:
            edge_cases.append('Missing or delayed fragments from some sources')
        return edge_cases[:4]

    def _suggest_alternatives(self, question: str, context: 'QuestionContext') -> list[str]:
        alternatives = []
        alternatives.append('Consider whether the question itself is framed correctly')
        alternatives.append("The actual root cause might be different from what's assumed")
        alternatives.append('There may be multiple contributing factors, not a single cause')
        return alternatives

    def _formulate_critical_answer(self, question: str, context: 'QuestionContext') -> str:
        _ = context.get_prior_contributions_summary()
        return "While the panel has provided useful perspectives, it's important to note several caveats. The answers provided assume standard operating conditions and may not account for all edge cases. Additionally, DAQ systems are complex and issues often have multiple contributing factors. Before acting on these recommendations, verify they apply to your specific situation."