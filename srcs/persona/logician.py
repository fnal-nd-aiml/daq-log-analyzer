"""
File: logician.py
Purpose: Logician persona - Phase 3: Causal Chain Construction.
Category: Utility
Author: artdaq team
Depends: llm, models, investigation, question, prompts, ...
Exports: LogicianPersona
Complexity: High | Lines: 460
"""

from __future__ import annotations
import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_LOGICIAN, Persona
if TYPE_CHECKING:
    from srcs.llm import LLMProvider
    from srcs.models.question import QuestionContext
    from srcs.workbinder import WorkBinder
from srcs.models import CausalStep, Evidence, Hypothesis
from srcs.models.investigation import CausalChain
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts.parsers import ChainResponse
logger = logging.getLogger(__name__)

class LogicianPersona(CollaborativePersona):

    def __init__(self) -> None:
        self._llm: LLMProvider | None = None
        self._max_hypotheses: int = 3
        self._min_score: float = 0.2
        self._built_chains: list[CausalChain] = []
        self._documentation_context: str = ''

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_LOGICIAN]

    @property
    def traits(self) -> list[str]:
        return ['rigorous', 'systematic', 'causal', 'precise', 'mechanism-focused']

    @property
    def thinking_style(self) -> str:
        return 'Causal reasoning - builds explicit cause-effect chains, requires mechanisms for each step, identifies assumptions, verifies temporal ordering'

    async def prepare(self, context: InvestigationContext) -> None:
        if context.config is not None:
            self._max_hypotheses = getattr(context.config, 'max_chains', 3)
            self._min_score = getattr(context.config, 'min_chain_score', 0.2)
        if context.llm is not None:
            self._llm = context.llm
        else:
            logger.warning('LLM not available - causal chain building will be limited')
            self._llm = None

    async def contribute(self, context: InvestigationContext) -> Contribution:
        if context.prior_knowledge and context.prior_knowledge.documentation_context:
            self._documentation_context = context.prior_knowledge.documentation_context
        else:
            self._documentation_context = '(no component documentation available)'
        chains = await self._build_chains(context)
        self._built_chains = chains
        content = self._build_content_dict(chains)
        confidence = self._calculate_confidence(chains)
        return Contribution(persona_id='logician', phase=PHASE_LOGICIAN, content=content, confidence=confidence, reasoning=self._build_reasoning_from_chains(chains))

    async def _build_chains(self, context: InvestigationContext) -> list[CausalChain]:
        if self._llm is None:
            await self.prepare(context)
        if not context.hypotheses:
            logger.warning('Cannot build chains - no hypotheses available')
            return []
        binder = context.binder
        try:
            chains: list[CausalChain] = await self._build_all(binder=binder, max_hypotheses=self._max_hypotheses, min_score=self._min_score)
            return chains
        except Exception as e:
            logger.warning(f'Causal chain building failed: {e}')
            return []

    def _build_content_dict(self, chains: list[CausalChain]) -> dict[str, Any]:
        if not chains:
            return {'chains_built': 0, 'average_validity': 0.0, 'average_coverage': 0.0, 'total_steps': 0, 'assumptions_made': 0, 'gaps_identified': []}
        total_steps = sum((len(c.steps) for c in chains))
        assumptions_made = sum((sum((1 for s in c.steps if s.is_assumption)) for c in chains))
        all_gaps: list[str] = []
        for c in chains:
            all_gaps.extend(c.gaps)
        avg_validity = sum((c.logical_validity for c in chains)) / len(chains)
        avg_coverage = sum((c.evidence_coverage for c in chains)) / len(chains)
        return {'chains_built': len(chains), 'average_validity': avg_validity, 'average_coverage': avg_coverage, 'total_steps': total_steps, 'assumptions_made': assumptions_made, 'gaps_identified': all_gaps[:10], 'chain_details': [{'hypothesis_id': c.hypothesis_id, 'steps_count': len(c.steps), 'validity': c.logical_validity, 'coverage': c.evidence_coverage, 'assumptions': len(c.assumptions)} for c in chains]}

    def _calculate_confidence(self, chains: list[CausalChain]) -> float:
        if not chains:
            return 0.2
        avg_validity = sum((c.logical_validity for c in chains)) / len(chains)
        avg_coverage = sum((c.evidence_coverage for c in chains)) / len(chains)
        score = avg_validity * 0.6 + avg_coverage * 0.4
        if len(chains) >= 3:
            score += 0.1
        elif len(chains) >= 2:
            score += 0.05
        return min(0.9, max(0.2, score))

    def _build_reasoning_from_chains(self, chains: list[CausalChain]) -> str:
        if not chains:
            return 'No causal chains could be constructed'
        parts: list[str] = []
        parts.append(f'Constructed {len(chains)} causal chain(s)')
        total_steps = sum((len(c.steps) for c in chains))
        parts.append(f'{total_steps} total steps')
        avg_validity = sum((c.logical_validity for c in chains)) / len(chains)
        parts.append(f'average validity: {avg_validity:.0%}')
        avg_coverage = sum((c.evidence_coverage for c in chains)) / len(chains)
        parts.append(f'evidence coverage: {avg_coverage:.0%}')
        assumptions = sum((len(c.assumptions) for c in chains))
        if assumptions > 0:
            parts.append(f'{assumptions} assumptions required')
        gaps = sum((len(c.gaps) for c in chains))
        if gaps > 0:
            parts.append(f'{gaps} gaps identified')
        return '; '.join(parts)

    async def _build(self, hypothesis: Hypothesis, evidence: Evidence, binder: 'WorkBinder') -> CausalChain:
        chain = await self._construct(hypothesis, evidence, binder=binder)
        chain = self._verify(chain, evidence)
        chain = self._calculate_scores(chain)
        steps = [{'step_order': s.step_order, 'claim': s.claim, 'mechanism': s.mechanism, 'evidence_ids': s.evidence_ids, 'is_assumption': s.is_assumption, 'assumption_note': s.assumption_note, 'evidence_strength': s.evidence_strength} for s in chain.steps]
        hypothesis_binder_id = hypothesis.binder_artifact_id
        if not hypothesis_binder_id:
            raise ValueError(f"Hypothesis '{hypothesis.id}' has no binder_artifact_id set. Cannot create causal chain with invalid artifact reference.")
        binder.add_causal_chain(hypothesis_id=hypothesis_binder_id, steps=steps, created_by='Logician', phase=3, logical_validity=chain.logical_validity, evidence_coverage=chain.evidence_coverage, gaps=chain.gaps, assumptions=chain.assumptions)
        return chain

    async def _build_all(self, binder: 'WorkBinder', max_hypotheses: int=3, min_score: float=0.2) -> list[CausalChain]:
        hypothesis_artifacts = binder.get_hypotheses()
        if not hypothesis_artifacts:
            logger.warning('No hypotheses found in binder')
            return []
        hypothesis_artifacts.sort(key=lambda h: h.score, reverse=True)
        top_hypotheses = [h for h in hypothesis_artifacts[:max_hypotheses] if h.score > min_score]
        evidence_artifacts = binder.get_evidence_items()
        evidence = Evidence()
        for ea in evidence_artifacts:
            from srcs.models import EvidenceItem
            item = EvidenceItem(id=ea.id, evidence_type=ea.evidence_type, content=ea.content, source=ea.source, strength=ea.strength, found=True)
            evidence.add(item)

        async def _build_for(ha: Any) -> CausalChain:
            hypothesis = Hypothesis(id=ha.id, description=ha.description, source=ha.source, prior=ha.prior_probability, score=ha.score, supporting_evidence_ids=ha.supporting_evidence_ids, contradicting_evidence_ids=ha.contradicting_evidence_ids, binder_artifact_id=ha.id)
            return await self._build(hypothesis, evidence, binder=binder)
        results = await asyncio.gather(*(_build_for(ha) for ha in top_hypotheses), return_exceptions=True)
        chains = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning(f'Failed to build chain for hypothesis: {result}')
            else:
                chains.append(result)
        return chains

    async def _construct(self, hypothesis: Hypothesis, evidence: Evidence, binder: 'WorkBinder | None'=None) -> CausalChain:
        if self._llm is None:
            return self._create_fallback_chain(hypothesis, evidence)
        evidence_list = self._format_evidence_list(evidence)
        code_context = self._format_code_context(binder) if binder else ''
        chronicler_context = self._format_chronicler_context(binder)
        template = get_user_prompt(UserPromptType.CAUSAL_CHAIN_WITH_EVIDENCE)
        prompt = template.format(hypothesis=hypothesis.description, evidence_list=evidence_list, documentation_context=self._documentation_context, chronicler_context=chronicler_context)
        if code_context:
            prompt += f'\n\n## Code Context\n{code_context}'
        chain = CausalChain(hypothesis_id=hypothesis.id)
        try:
            system_prompt = get_system_prompt(SystemPromptType.LOGICIAN)
            response = await self._llm.generate_structured(prompt, ChainResponse, system_prompt=system_prompt)
            for i, step_data in enumerate(response.steps):
                step = CausalStep(step_order=i, claim=step_data.claim, mechanism=step_data.mechanism, evidence_ids=step_data.evidence, is_assumption=step_data.is_assumption)
                chain.steps.append(step)
        except Exception as e:
            logger.warning(f'Structured chain generation failed: {e}')
            chain = self._create_fallback_chain(hypothesis, evidence)
        return chain

    def _format_evidence_list(self, evidence: Evidence) -> str:
        lines = []
        for item_id, item in evidence.items.items():
            if not item.found:
                continue
            lines.append(f'- {item_id} [{item.strength}]: {item.evidence_type} - {item.content}')
        if not lines:
            return 'No evidence collected (all steps will be assumptions)'
        return '\n'.join(lines)

    def _format_code_context(self, binder: 'WorkBinder') -> str:
        from srcs.workbinder.relevance import render_selected_artifacts
        return render_selected_artifacts(binder, 'logician')

    def _format_chronicler_context(self, binder: 'WorkBinder | None') -> str:
        if binder is None:
            return '(no Chronicler context — single-file investigation)'
        log_bundle = binder.get_log_bundle()
        if log_bundle is None:
            return '(no Chronicler context — single-file investigation)'
        parts: list[str] = []
        primary_error = getattr(log_bundle, 'primary_error', None)
        if primary_error:
            msg = getattr(primary_error, 'message', '')
            fname = getattr(primary_error, 'filename', '')
            if msg:
                pe_text = msg
                if fname:
                    pe_text += f' (file: {fname})'
                parts.append(f'### Primary Error\n{pe_text}')
        cascade_desc = getattr(log_bundle, 'cascade_description', '')
        if cascade_desc:
            parts.append(f'### Cascade Description\n{cascade_desc}')
        chain = getattr(log_bundle, 'cascade_chain', [])
        if chain:
            chain_lines = []
            for link in chain:
                chain_lines.append(f'- {link.from_board} → {link.to_board}: {link.mechanism}')
            parts.append('### Cascade Chain\n' + '\n'.join(chain_lines))
        boards = getattr(log_bundle, 'affected_boards', [])
        if boards:
            board_lines = []
            for b in boards:
                line = f'- {b.board_name} ({b.role})'
                if getattr(b, 'failure_mode', None):
                    line += f': {b.failure_mode}'
                if getattr(b, 'key_error_message', None):
                    line += f' — {b.key_error_message}'
                board_lines.append(line)
            parts.append('### Affected Boards\n' + '\n'.join(board_lines))
        if not parts:
            return '(no Chronicler context — single-file investigation)'
        return '\n\n'.join(parts)

    def _create_fallback_chain(self, hypothesis: Hypothesis, evidence: Evidence) -> CausalChain:
        hypothesis_ref_id = hypothesis.binder_artifact_id or hypothesis.id
        chain = CausalChain(hypothesis_id=hypothesis_ref_id)
        chain.steps.append(CausalStep(step_order=0, claim=f'Root cause: {hypothesis.description}', mechanism='Mechanism requires further investigation', evidence_ids=list(hypothesis.supporting_evidence_ids)[:3], is_assumption=len(hypothesis.supporting_evidence_ids) == 0))
        chain.steps.append(CausalStep(step_order=1, claim='This caused the observed error', mechanism='Direct causation', evidence_ids=[], is_assumption=True, assumption_note='Causal link assumed pending verification'))
        return chain

    def _verify(self, chain: CausalChain, evidence: Evidence) -> CausalChain:
        invalid_refs: list[str] = []
        for step in chain.steps:
            valid_evidence = []
            for eid in step.evidence_ids:
                if eid in evidence.items:
                    item = evidence.items[eid]
                    if item.found:
                        valid_evidence.append(eid)
                        if self._strength_rank(item.strength) > self._strength_rank(step.evidence_strength):
                            step.evidence_strength = item.strength
                    else:
                        invalid_refs.append(f'{eid} (not found)')
                else:
                    invalid_refs.append(f'{eid} (does not exist)')
            linked_evidence = self._link_evidence_to_step(step, evidence)
            for eid in linked_evidence:
                if eid not in valid_evidence:
                    valid_evidence.append(eid)
                    item = evidence.items[eid]
                    if self._strength_rank(item.strength) > self._strength_rank(step.evidence_strength):
                        step.evidence_strength = item.strength
            step.evidence_ids = valid_evidence
            if not valid_evidence:
                if not step.is_assumption:
                    step.is_assumption = True
                    if invalid_refs:
                        step.assumption_note = f"Cited evidence not found: {', '.join(invalid_refs[-3:])}"
                    else:
                        step.assumption_note = 'No supporting evidence available'
            if step.evidence_strength == 'NONE' and valid_evidence:
                step.evidence_strength = 'WEAK'
        if invalid_refs:
            logger.debug(f"Chain had {len(invalid_refs)} invalid evidence references: {invalid_refs[:5]}{('...' if len(invalid_refs) > 5 else '')}")
        return chain

    def _link_evidence_to_step(self, step: CausalStep, evidence: Evidence) -> list[str]:
        linked = []
        claim_lower = step.claim.lower()
        mechanism_lower = (step.mechanism or '').lower()
        for item_id, item in evidence.items.items():
            if not item.found:
                continue
            if item.evidence_type != 'code':
                continue
            content_lower = item.content.lower()
            if any((term in claim_lower for term in ['null', 'nullptr', 'pointer', 'invalid'])):
                if re.search('nullptr|NULL|==\\s*null|!=\\s*null', content_lower):
                    linked.append(item_id)
                    continue
            if any((term in claim_lower for term in ['exception', 'throw', 'catch', 'error'])):
                if re.search('catch\\s*\\(|throw\\s+|try\\s*\\{', content_lower):
                    linked.append(item_id)
                    continue
            if any((term in claim_lower for term in ['timeout', 'timing', 'delay', 'deadline'])):
                if re.search('timeout|deadline|duration|elapsed', content_lower):
                    linked.append(item_id)
                    continue
            if any((term in claim_lower for term in ['config', 'parameter', 'setting'])):
                if re.search('config|param|fhicl|pset', content_lower):
                    linked.append(item_id)
                    continue
            func_matches = re.findall('(\\w+::\\w+)\\s*\\(', claim_lower)
            for func in func_matches:
                if func in content_lower:
                    linked.append(item_id)
                    break
            if mechanism_lower:
                func_matches = re.findall('(\\w+::\\w+)\\s*\\(', mechanism_lower)
                for func in func_matches:
                    if func in content_lower and item_id not in linked:
                        linked.append(item_id)
                        break
        return linked

    def _strength_rank(self, strength: str) -> int:
        return {'STRONG': 3, 'MODERATE': 2, 'WEAK': 1, 'NONE': 0}.get(strength, 0)

    def _calculate_scores(self, chain: CausalChain) -> CausalChain:
        if not chain.steps:
            return chain
        with_mechanism = sum((1 for s in chain.steps if s.mechanism))
        chain.logical_validity = with_mechanism / len(chain.steps)
        non_assumption = sum((1 for s in chain.steps if not s.is_assumption))
        chain.evidence_coverage = non_assumption / len(chain.steps)
        chain.gaps = [f'Step {s.step_order}: {s.claim[:50]}...' for s in chain.steps if s.is_assumption]
        chain.assumptions = [s.assumption_note or s.claim[:50] for s in chain.steps if s.is_assumption and s.assumption_note]
        return chain

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights: list[str] = []
        uncertainties: list[str] = []
        suggestions: list[str] = []
        chains = self._built_chains
        if chains:
            high_validity = [c for c in chains if c.logical_validity > 0.7]
            if high_validity:
                insights.append(f'{len(high_validity)} chain(s) have high logical validity (>70%)')
            high_coverage = [c for c in chains if c.evidence_coverage > 0.7]
            if high_coverage:
                insights.append(f'{len(high_coverage)} chain(s) have high evidence coverage (>70%)')
            for chain in chains:
                assumption_ratio = len([s for s in chain.steps if s.is_assumption]) / len(chain.steps) if chain.steps else 0
                if assumption_ratio > 0.5:
                    uncertainties.append(f'Chain for hypothesis {chain.hypothesis_id[:8]} relies heavily on assumptions ({assumption_ratio:.0%})')
            total_gaps = sum((len(c.gaps) for c in chains))
            if total_gaps > 0:
                uncertainties.append(f'{total_gaps} gap(s) identified across chains')
                suggestions.append('Additional evidence may be needed to fill reasoning gaps')
            chains_with_strong_evidence = [c for c in chains if any((s.evidence_strength == 'STRONG' for s in c.steps))]
            if chains_with_strong_evidence:
                insights.append(f'{len(chains_with_strong_evidence)} chain(s) linked to strong evidence')
            elif chains:
                suggestions.append('No chains linked to strong evidence - consider additional investigation')
        else:
            if not context.hypotheses:
                uncertainties.append('No hypotheses available for chain construction')
                suggestions.append('Hypothesis generation must complete first')
            elif not context.evidence or not context.evidence.items:
                uncertainties.append('Limited evidence for chain construction')
                suggestions.append('Chains may require assumptions due to evidence gaps')
            else:
                uncertainties.append('Chains could not be constructed')
                suggestions.append('Review hypotheses and evidence for chain construction')
            if context.hypotheses:
                hypotheses_with_evidence = [h for h in context.hypotheses if h.supporting_evidence_ids]
                if hypotheses_with_evidence:
                    insights.append(f'{len(hypotheses_with_evidence)} hypothesis(es) have supporting evidence')
                else:
                    uncertainties.append('No hypotheses have supporting evidence')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f"I need to understand the mechanism, {other.metadata.name}. How exactly does A lead to B in this chain? What's the causal pathway?"

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        content_str = str(contribution.content).lower()
        reasoning_str = str(contribution.reasoning).lower()
        if 'because' in reasoning_str or 'leads to' in reasoning_str:
            strengths.append('Reasoning includes causal connections')
        else:
            issues.append('Reasoning lacks explicit causal links')
            recommendations.append('Articulate the mechanism: how does A cause B?')
        if 'assume' in reasoning_str or 'assumption' in content_str:
            issues.append('Conclusion relies on assumptions')
            recommendations.append('Identify evidence to verify assumptions')
        if 'always' in content_str or 'never' in content_str:
            issues.append('Absolute terms may indicate overgeneralization')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='MEDIUM' if issues else 'LOW', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        reasoning_str = str(contribution.reasoning).lower()
        has_causal_reasoning = any((term in reasoning_str for term in ['because', 'causes', 'leads to', 'results in', 'mechanism']))
        return has_causal_reasoning or contribution.confidence > 0.7

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        question_type = context.question_type
        content: dict = {'causal_analysis': [], 'logical_steps': [], 'answer': '', 'key_points': [], 'assumptions': []}
        from srcs.models.question import QuestionType
        if question_type == QuestionType.WHY:
            content['answer'] = self._build_why_logic(question, context)
            content['causal_analysis'] = self._analyze_causation(question)
        elif question_type == QuestionType.TROUBLESHOOT:
            content['answer'] = self._build_diagnostic_logic(question, context)
            content['logical_steps'] = self._build_diagnostic_steps(question)
        elif question_type == QuestionType.HOW_TO:
            content['answer'] = self._build_procedural_logic(question, context)
            content['logical_steps'] = self._build_procedure_steps(question)
        else:
            content['answer'] = self._build_general_logic(question, context)
        content['key_points'] = self._extract_logical_points(content['answer'])
        content['assumptions'] = self._identify_assumptions(question, context)
        reasoning = f"Applied logical analysis with {len(content['logical_steps'])} steps; identified {len(content['assumptions'])} assumptions"
        confidence = 0.65
        return Contribution(persona_id='logician', phase=PHASE_LOGICIAN, content=content, confidence=confidence, reasoning=reasoning)

    def _build_why_logic(self, question: str, context: 'QuestionContext') -> str:
        question_lower = question.lower()
        if 'timeout' in question_lower:
            return 'Logically, timeouts occur when: 1) A wait operation exceeds its configured threshold, 2) The expected response or data does not arrive in time. This leads to the following causal chain: slow hardware/network → delayed response → threshold exceeded → timeout error. Therefore, the solution involves either increasing the threshold or reducing the response time.'
        return 'From a logical perspective, this behavior follows from the interaction of system components according to their design. Each component responds to its inputs based on its configuration and the current system state.'

    def _build_diagnostic_logic(self, question: str, context: 'QuestionContext') -> str:
        return 'To diagnose this issue logically: First, identify the exact symptoms and when they occur. Then, trace backwards from the symptom to potential causes. Each potential cause should be verified or eliminated systematically. The root cause is the earliest point in the causal chain that can be addressed.'

    def _build_procedural_logic(self, question: str, context: 'QuestionContext') -> str:
        return 'The logical approach to this task involves: 1) Understanding the prerequisites and starting state, 2) Identifying the sequence of operations required, 3) Executing each step while verifying intermediate results, 4) Confirming the final outcome matches expectations.'

    def _build_general_logic(self, question: str, context: 'QuestionContext') -> str:
        return 'Analyzing this logically, we need to consider the underlying principles and how they apply to this specific case. The relationship between cause and effect governs the behavior.'

    def _analyze_causation(self, question: str) -> list[str]:
        return ['Input conditions determine initial system state', 'Component interactions follow defined protocols', 'Errors propagate through connected components', 'Outcomes result from the cumulative effect of all factors']

    def _build_diagnostic_steps(self, question: str) -> list[str]:
        return ['Identify the specific error message or symptom', 'Determine when the issue first appeared', 'Check for recent changes to configuration or environment', 'Examine logs for correlated events', 'Test each hypothesis by verifying or eliminating']

    def _build_procedure_steps(self, question: str) -> list[str]:
        return ['Verify prerequisites are met', 'Prepare the necessary configuration', 'Execute the required operations in sequence', 'Verify each step completed successfully', 'Confirm the final result']

    def _extract_logical_points(self, answer: str) -> list[str]:
        points = []
        for i in range(1, 6):
            marker = f'{i})'
            if marker in answer:
                start = answer.find(marker)
                end = answer.find(f'{i + 1})') if i < 5 else len(answer)
                point = answer[start + 2:end].strip().rstrip(',.')
                if point:
                    points.append(point)
        return points if points else ['Logical analysis applied']

    def _identify_assumptions(self, question: str, context: 'QuestionContext') -> list[str]:
        assumptions = []
        if 'config' not in question.lower():
            assumptions.append('Configuration is correct and complete')
        if not context.related_logs:
            assumptions.append('No log data provided for verification')
        assumptions.append('System is functioning within normal parameters')
        return assumptions