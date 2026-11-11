"""
File: synthesizer.py
Purpose: Synthesizer persona - Phase 6: Final Synthesis.
Category: Utility
Author: artdaq team
Depends: knowledge, calibration, models, question, prompts, ...
Exports: RootCauseInfo, KeyEvidence, DebuggingStep, ConfidenceInfo, SynthesisResponse, ...
Complexity: High | Lines: 855
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
from pydantic import BaseModel
from srcs.knowledge.calibration import calculate_calibrated_confidence
from srcs.models import CalibratedConfidence, CausalChain, Challenge, Evidence, Hypothesis, HypothesisSummary, Investigation, InvestigationConclusion, InvestigationOutcome, InvestigationResult, KeyFile, PriorKnowledge, SubCause
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts.parsers import CausalChainParser
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_SYNTHESIZER, Persona
if TYPE_CHECKING:
    from srcs.knowledge import KnowledgeBase
    from srcs.models.question import QuestionContext
    from srcs.workbinder import WorkBinder
logger = logging.getLogger(__name__)

class RootCauseInfo(BaseModel):
    description: str
    code_location: str = ''
    mechanism: str = ''

class KeyEvidence(BaseModel):
    type: str
    content: str
    significance: str

class DebuggingStep(BaseModel):
    action: str
    purpose: str
    expected_result: str = ''

class ConfidenceInfo(BaseModel):
    level: str
    raw_score: float
    calibrated_score: float = 0.0
    reasoning: str = ''

class SynthesisResponse(BaseModel):
    executive_summary: str
    root_cause: Optional[RootCauseInfo] = None
    causal_narrative: List[str] = []
    key_evidence: List[KeyEvidence] = []
    debugging_steps: List[DebuggingStep] = []
    caveats: List[str] = []
    confidence: ConfidenceInfo
    discrimination_needed: List[str] = []

class SynthesizerPersona(CollaborativePersona):

    def __init__(self) -> None:
        self._llm_synthesis: SynthesisResponse | None = None
        self._kb: KnowledgeBase | None = None

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_SYNTHESIZER]

    @property
    def traits(self) -> list[str]:
        return ['integrative', 'holistic', 'communicative', 'action-oriented', 'clear']

    @property
    def thinking_style(self) -> str:
        return 'Integrative synthesis - combines diverse inputs, creates coherent narrative, ensures actionability, communicates clearly for the intended audience'

    async def prepare(self, context: InvestigationContext) -> None:
        pass

    async def contribute(self, context: InvestigationContext) -> Contribution:
        if context.llm is not None:
            llm_synthesis = await self._synthesize_with_llm(context)
            if llm_synthesis is not None:
                self._llm_synthesis = llm_synthesis
                content = self._build_content_from_llm(llm_synthesis)
                return Contribution(persona_id='synthesizer', phase=PHASE_SYNTHESIZER, content=content, confidence=llm_synthesis.confidence.raw_score, reasoning=llm_synthesis.executive_summary)
        synthesis = self._synthesize_rules(context)
        confidence_val = synthesis.get('confidence', 0.5)
        confidence = float(confidence_val) if isinstance(confidence_val, (int, float)) else 0.5
        return Contribution(persona_id='synthesizer', phase=PHASE_SYNTHESIZER, content=synthesis, confidence=confidence, reasoning=self._build_reasoning_rules(synthesis))

    async def _synthesize_with_llm(self, context: InvestigationContext) -> SynthesisResponse | None:
        binder = context.binder
        investigation_id = binder.id[:8] if hasattr(binder, 'id') else 'unknown'
        error_message = context.error.message if context.error else 'Unknown error'
        error_component = context.error.component if context.error else 'Unknown'
        started_at = datetime.now().isoformat()
        duration = 'N/A'
        outcome = 'INSUFFICIENT'
        raw_confidence = 0.5
        judge_contributions = binder.get_persona_contributions(persona_id='judge')
        if judge_contributions:
            latest = judge_contributions[-1]
            if isinstance(latest.content, dict):
                outcome = latest.content.get('outcome', 'INSUFFICIENT')
                raw_confidence = latest.confidence
        hypotheses_artifacts = binder.get_hypotheses()
        evidence_artifacts = binder.get_evidence_items()
        if hypotheses_artifacts:
            hypotheses_artifacts.sort(key=lambda h: h.score, reverse=True)
            alignment = self._check_evidence_alignment(hypotheses_artifacts[:5], evidence_artifacts)
            ranked_lines = []
            for i, h in enumerate(hypotheses_artifacts[:5], 1):
                align_score = alignment.get(h.description, 0.0)
                ranked_lines.append(f'{i}. [score={h.score:.2f}, evidence={align_score:.2f}] {h.description} (source: {h.source})')
            hypotheses_ranked = '\n'.join(ranked_lines)
        else:
            hypotheses_ranked = 'No hypotheses generated'
        evidence_lines = []
        for e in evidence_artifacts[:10]:
            evidence_lines.append(f'- [{e.strength}] {e.evidence_type}: {e.content}')
        evidence_summary = '\n'.join(evidence_lines) if evidence_lines else 'No evidence collected'
        chain_artifacts = binder.get_causal_chains()
        if chain_artifacts:
            chain = chain_artifacts[0]
            chain_lines = []
            for step in chain.steps:
                step_data = step if isinstance(step, dict) else {'claim': str(step)}
                claim = step_data.get('claim', str(step_data))
                chain_lines.append(f'- {claim}')
            causal_chain = '\n'.join(chain_lines)
        else:
            causal_chain = 'No causal chain constructed'
        challenge_artifacts = binder.get_challenges()
        challenge_lines = []
        for c in challenge_artifacts:
            status = 'resolved' if c.resolved else 'unresolved'
            challenge_lines.append(f'- [{c.severity}] {c.content} ({status})')
        challenges_summary = '\n'.join(challenge_lines) if challenge_lines else 'No challenges'
        source_locations = binder.get_source_locations()
        source_lines = []
        for loc in source_locations[:3]:
            line = f'- {loc.file_path}:{loc.line_number}'
            if loc.function_name:
                line += f' (function: {loc.function_name})'
            if loc.match_score:
                line += f' [match: {loc.match_score:.0%}]'
            source_lines.append(line)
        source_locations_text = '\n'.join(source_lines) if source_lines else 'No source locations identified'
        from srcs.workbinder.artifacts import Finding
        numeric_findings = binder.get_by_tag('numeric_analysis')
        numeric_lines = []
        for f in numeric_findings:
            if isinstance(f, Finding) and f.content:
                numeric_lines.append(f'- {f.content}')
        numeric_context = '\n'.join(numeric_lines) if numeric_lines else 'No numeric analysis available'
        try:
            from srcs.workbinder.relevance import render_selected_artifacts
            code_context = render_selected_artifacts(binder, 'synthesizer')
            if not code_context:
                code_context = 'No code context available'
        except Exception:
            code_context = 'No code context available'
        judge_evidence_gaps = 'None identified'
        judge_criteria_not_met = 'None identified'
        if judge_contributions:
            latest = judge_contributions[-1]
            if isinstance(latest.content, dict):
                gaps = latest.content.get('evidence_gaps')
                if gaps:
                    if isinstance(gaps, list):
                        judge_evidence_gaps = '\n'.join((f'- {g}' for g in gaps))
                    else:
                        judge_evidence_gaps = str(gaps)
                criteria = latest.content.get('criteria_not_met')
                if criteria:
                    if isinstance(criteria, list):
                        judge_criteria_not_met = '\n'.join((f'- {c}' for c in criteria))
                    else:
                        judge_criteria_not_met = str(criteria)
        doc_context = ''
        if context.prior_knowledge and context.prior_knowledge.documentation_context:
            doc_context = context.prior_knowledge.documentation_context
        if not doc_context:
            doc_context = '(no component documentation available)'
        chronicler_context = self._format_chronicler_context(binder)
        try:
            user_prompt_template = get_user_prompt(UserPromptType.FINAL_SYNTHESIS)
            prompt = user_prompt_template.format(investigation_id=investigation_id, error_message=error_message, error_component=error_component, started_at=started_at, duration=duration, outcome=outcome, confidence=f'{raw_confidence:.2f}', hypotheses_ranked=hypotheses_ranked, evidence_summary=evidence_summary, causal_chain=causal_chain, challenges_summary=challenges_summary, source_locations=source_locations_text, numeric_context=numeric_context, code_context=code_context, judge_evidence_gaps=judge_evidence_gaps, judge_criteria_not_met=judge_criteria_not_met, documentation_context=doc_context, chronicler_context=chronicler_context)
        except Exception as e:
            logger.warning(f'Failed to format synthesis prompt: {e}')
            return None
        try:
            system_prompt = get_system_prompt(SystemPromptType.SYNTHESIZER)
            response = await self._call_llm_structured(context=context, prompt=prompt, response_model=SynthesisResponse, system_prompt=system_prompt, prompt_key='final_synthesis')
            return response
        except Exception as e:
            logger.warning(f'LLM synthesis failed: {e}')
            return None

    def _build_content_from_llm(self, synthesis: SynthesisResponse) -> dict[str, Any]:
        content: dict[str, Any] = {'executive_summary': synthesis.executive_summary, 'causal_narrative': synthesis.causal_narrative, 'key_evidence': [{'type': e.type, 'content': e.content, 'significance': e.significance} for e in synthesis.key_evidence], 'debugging_steps': [{'action': s.action, 'purpose': s.purpose, 'expected_result': s.expected_result} for s in synthesis.debugging_steps], 'caveats': synthesis.caveats, 'confidence': {'level': synthesis.confidence.level, 'raw_score': synthesis.confidence.raw_score, 'calibrated_score': synthesis.confidence.calibrated_score, 'reasoning': synthesis.confidence.reasoning}, 'discrimination_needed': synthesis.discrimination_needed, 'synthesis_method': 'llm'}
        if synthesis.root_cause is not None:
            content['root_cause'] = {'description': synthesis.root_cause.description, 'code_location': synthesis.root_cause.code_location, 'mechanism': synthesis.root_cause.mechanism}
        return content

    def _format_chronicler_context(self, binder: 'WorkBinder') -> str:
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
        narrative = getattr(log_bundle, 'annotated_narrative', '')
        if narrative:
            parts.append(f'### Analytical Narrative\n{narrative}')
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
                    line += f' — Key error: {b.key_error_message}'
                board_lines.append(line)
            parts.append('### Affected Boards\n' + '\n'.join(board_lines))
        if not parts:
            return '(no Chronicler context — single-file investigation)'
        return '\n\n'.join(parts)

    def _synthesize_rules(self, context: InvestigationContext) -> dict[str, str | float | list[str] | None]:
        recommendations: list[str] = []
        caveats: list[str] = []
        synthesis: dict[str, str | float | list[str] | None] = {'outcome': 'INSUFFICIENT', 'confidence': 0.5, 'root_cause': None, 'summary': '', 'evidence_summary': '', 'recommendations': recommendations, 'caveats': caveats, 'synthesis_method': 'rules'}
        judge_contributions = context.binder.get_persona_contributions(persona_id='judge') if context.binder else []
        if judge_contributions:
            latest_judgment = judge_contributions[-1]
            if isinstance(latest_judgment.content, dict):
                synthesis['outcome'] = latest_judgment.content.get('outcome', 'INSUFFICIENT')
                synthesis['confidence'] = latest_judgment.confidence
        root_cause: str | None = None
        if context.hypotheses:
            accepted = [h for h in context.hypotheses if h.status == 'accepted']
            candidates = accepted if accepted else list(context.hypotheses)
            alignment = self._check_evidence_alignment(candidates, context.evidence)
            by_score = sorted(candidates, key=lambda h: h.score, reverse=True)
            if by_score:
                top = by_score[0]
                top_align = alignment.get(top.description, 0.0)
                if top_align < 0.3 and len(by_score) > 1:
                    for alt in by_score[1:]:
                        alt_align = alignment.get(alt.description, 0.0)
                        if alt_align > top_align + 0.2:
                            root_cause = alt.description
                            break
                if root_cause is None:
                    root_cause = top.description
        synthesis['root_cause'] = root_cause
        summary_parts = []
        if root_cause:
            summary_parts.append(f'Root cause: {root_cause}')
        if context.evidence and context.evidence.items:
            strong = context.evidence.get_strong_evidence()
            evidence_summary = f'{len(context.evidence.items)} evidence items ({len(strong)} strong)'
            synthesis['evidence_summary'] = evidence_summary
            summary_parts.append(evidence_summary)
        synthesis['summary'] = '. '.join(summary_parts)
        if root_cause:
            root_cause_lower = root_cause.lower()
            if 'config' in root_cause_lower:
                recommendations.append('Review and update configuration settings')
            if 'timing' in root_cause_lower:
                recommendations.append('Investigate timing parameters and synchronization')
            if 'resource' in root_cause_lower:
                recommendations.append('Check resource allocation and limits')
            if not recommendations:
                recommendations.append('Investigate identified root cause in detail')
        confidence = synthesis.get('confidence', 0.5)
        if isinstance(confidence, float) and confidence < 0.7:
            caveats.append('Conclusion has moderate confidence - consider additional verification')
        devil_contributions = [c for c in context.contributions if c.persona_id == 'skeptic']
        if devil_contributions:
            for contrib in devil_contributions:
                if isinstance(contrib.content, dict):
                    if contrib.content.get('unresolved', 0) > 0:
                        caveats.append('Some challenges remain unresolved')
        return synthesis

    def _build_reasoning_rules(self, synthesis: dict) -> str:
        parts = []
        if synthesis['root_cause']:
            parts.append(f"Identified root cause with {synthesis['outcome']} outcome")
        else:
            parts.append('No definitive root cause identified')
        if synthesis['evidence_summary']:
            parts.append(synthesis['evidence_summary'])
        if synthesis['caveats']:
            parts.append(f"{len(synthesis['caveats'])} caveat(s) noted")
        return '; '.join(parts) if parts else 'Synthesis in progress'

    def _check_evidence_alignment(self, hypotheses: list[Any], evidence: Any) -> dict[str, float]:
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'which', 'with', 'from', 'for', 'and', 'or', 'not', 'in', 'on', 'at', 'to', 'of', 'by', 'as', 'if', 'but', 'so', 'no', 'it', 'its', 'error', 'cause', 'issue', 'problem'}

        def extract_keywords(text: str) -> set[str]:
            words = set(text.lower().split())
            return {w for w in words if len(w) > 2 and w not in stopwords}
        evidence_items: list[Any] = []
        if evidence is not None:
            if isinstance(evidence, list):
                evidence_items = evidence
            elif hasattr(evidence, 'items') and evidence.items:
                evidence_items = list(evidence.items.values())
        if not evidence_items:
            return {h.description: 0.0 for h in hypotheses}
        total = len(evidence_items)
        evidence_keywords = [extract_keywords(e.content) for e in evidence_items]
        alignment: dict[str, float] = {}
        for h in hypotheses:
            h_keywords = extract_keywords(h.description)
            if not h_keywords:
                alignment[h.description] = 0.0
                continue
            supporting = sum((1 for ek in evidence_keywords if h_keywords & ek))
            alignment[h.description] = supporting / max(total, 1)
        return alignment

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights: list[str] = []
        uncertainties: list[str] = []
        suggestions: list[str] = []
        if self._llm_synthesis is not None:
            synthesis = self._llm_synthesis
            if synthesis.root_cause is not None and synthesis.root_cause.description:
                insights.append('Root cause successfully identified and explained')
                if synthesis.root_cause.mechanism:
                    insights.append('Causal mechanism clearly articulated')
                if synthesis.root_cause.code_location:
                    insights.append(f'Code location identified: {synthesis.root_cause.code_location}')
            if synthesis.key_evidence:
                insights.append(f'Highlighted {len(synthesis.key_evidence)} key evidence items')
            if synthesis.debugging_steps:
                insights.append(f'Provided {len(synthesis.debugging_steps)} actionable debugging steps')
            else:
                suggestions.append('Consider adding specific debugging steps')
            for caveat in synthesis.caveats[:3]:
                uncertainties.append(caveat)
            if synthesis.confidence.level == 'high':
                insights.append('High-confidence conclusion reached')
            elif synthesis.confidence.level == 'low':
                uncertainties.append('Low confidence in conclusion')
                suggestions.append('Additional investigation may be warranted')
        else:
            rule_synthesis = self._synthesize_rules(context)
            if rule_synthesis['root_cause']:
                insights.append('Root cause successfully identified')
                if rule_synthesis['outcome'] == 'CONFIDENT':
                    insights.append('High-confidence conclusion reached')
            else:
                uncertainties.append('Could not identify definitive root cause')
            caveats = rule_synthesis.get('caveats', [])
            if isinstance(caveats, list):
                for caveat in caveats:
                    uncertainties.append(str(caveat))
            recommendations = rule_synthesis.get('recommendations', [])
            if not recommendations or not isinstance(recommendations, list):
                suggestions.append('Consider adding specific action items')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f"Thank you, {other.metadata.name}. I'll incorporate your perspective into the final synthesis to ensure a complete and actionable result."

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        if contribution.reasoning and len(contribution.reasoning) > 20:
            strengths.append('Well-documented reasoning')
        else:
            issues.append('Reasoning could be more complete')
            recommendations.append('Provide fuller explanation of conclusions')
        content_str = str(contribution.content).lower()
        if any((term in content_str for term in ['recommend', 'action', 'next', 'should'])):
            strengths.append('Includes actionable guidance')
        else:
            recommendations.append('Consider adding actionable recommendations')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='LOW' if not issues else 'MEDIUM', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        has_reasoning = bool(contribution.reasoning)
        has_content = bool(contribution.content)
        return has_reasoning and has_content

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        content: dict = {'answer': '', 'key_points': [], 'action_items': [], 'sources': [], 'summary': ''}
        synthesis = self._synthesize_contributions(context)
        content['answer'] = synthesis['answer']
        content['key_points'] = synthesis['key_points']
        content['action_items'] = synthesis['action_items']
        content['sources'] = synthesis['sources']
        content['summary'] = synthesis['summary']
        reasoning = f"Synthesized {len(context.contributions)} contributions into coherent answer with {len(content['key_points'])} key points"
        confidence = self._calculate_synthesis_confidence(context)
        return Contribution(persona_id='synthesizer', phase=PHASE_SYNTHESIZER, content=content, confidence=confidence, reasoning=reasoning)

    def _synthesize_contributions(self, context: 'QuestionContext') -> dict:
        all_answers: list[str] = []
        all_key_points: list[str] = []
        all_sources: list[str] = []
        all_caveats: list[str] = []
        for contrib in context.contributions:
            content = contrib.content
            if isinstance(content, dict):
                if 'answer' in content and content['answer']:
                    all_answers.append(content['answer'])
                elif 'response' in content:
                    all_answers.append(content['response'])
                if 'key_points' in content:
                    all_key_points.extend(content['key_points'])
                if 'sources' in content:
                    all_sources.extend(content['sources'])
                if 'caveats' in content:
                    all_caveats.extend(content['caveats'])
            elif isinstance(content, str) and content:
                all_answers.append(content)
        if all_answers:
            unified_answer = self._merge_answers(all_answers)
        else:
            unified_answer = "Based on the panel's analysis, no definitive answer could be formulated. Please provide more specific details."
        key_points = list(dict.fromkeys(all_key_points))[:10]
        sources = list(dict.fromkeys(all_sources))
        action_items = self._generate_action_items(context)
        summary = self._build_summary(unified_answer, key_points, all_caveats)
        return {'answer': unified_answer, 'key_points': key_points, 'sources': sources, 'action_items': action_items, 'summary': summary}

    def _merge_answers(self, answers: list[str]) -> str:
        if not answers:
            return ''
        if len(answers) == 1:
            return answers[0]
        merged_parts: list[str] = []
        seen_concepts: set[str] = set()
        for answer in answers:
            answer_words = set(answer.lower().split())
            new_words = answer_words - seen_concepts
            if len(new_words) > 5:
                merged_parts.append(answer)
                seen_concepts.update(answer_words)
        if merged_parts:
            return '\n\n'.join(merged_parts[:3])
        else:
            return answers[0]

    def _generate_action_items(self, context: 'QuestionContext') -> list[str]:
        items = []
        question_lower = context.question.lower()
        from srcs.models.question import QuestionType
        if context.question_type == QuestionType.HOW_TO:
            items.append('Follow the steps outlined above')
            items.append('Verify the result after implementation')
        elif context.question_type == QuestionType.TROUBLESHOOT:
            items.append('Check the logs for the specific error messages mentioned')
            items.append('Verify configuration settings')
            items.append('Test changes in a non-production environment first')
        elif context.question_type == QuestionType.WHY:
            items.append('Review the causal factors identified')
            items.append('Address root causes rather than symptoms')
        if 'config' in question_lower or 'fcl' in question_lower:
            items.append('Back up current configuration before making changes')
        return items[:5]

    def _build_summary(self, answer: str, key_points: list[str], caveats: list[str]) -> str:
        summary_parts = []
        if key_points:
            summary_parts.append(f"Key points: {'; '.join(key_points[:3])}")
        if caveats:
            summary_parts.append(f'Note: {caveats[0]}')
        if summary_parts:
            return ' '.join(summary_parts)
        else:
            first_sentence = answer.split('.')[0] if answer else ''
            return first_sentence[:200]

    def _calculate_synthesis_confidence(self, context: 'QuestionContext') -> float:
        if not context.contributions:
            return 0.3
        total_confidence = sum((c.confidence for c in context.contributions))
        avg_confidence = total_confidence / len(context.contributions)
        diversity_bonus = min(0.1 * len(context.contributions), 0.2)
        return min(avg_confidence + diversity_bonus, 0.9)

    async def synthesize(self, investigation: Investigation, outcome: InvestigationOutcome, hypotheses: list[Hypothesis], chains: list[CausalChain], evidence: Evidence, prior: PriorKnowledge, binder: 'WorkBinder') -> InvestigationResult:
        result = InvestigationResult(investigation_id=investigation.id, outcome=outcome)
        detective_contribution = None
        detective_contributions = binder.get_persona_contributions(persona_id='detective')
        if detective_contributions:
            detective_contribution = detective_contributions[-1].content
        if outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
            result = await self._synthesize_confident(result, hypotheses[0] if hypotheses else None, chains[0] if chains else None, evidence, investigation.challenges, prior, hypotheses)
        elif outcome == InvestigationOutcome.UNCERTAIN:
            result = self._synthesize_uncertain(result, hypotheses, evidence)
        elif outcome == InvestigationOutcome.INSUFFICIENT:
            result = self._synthesize_insufficient(result, hypotheses, evidence, detective_contribution)
        elif outcome == InvestigationOutcome.CONTRADICTORY:
            result = self._synthesize_contradictory(result, hypotheses, evidence)
        result.evidence_summary = evidence.summary()
        result.duration_seconds = (investigation.completed_at - investigation.started_at).total_seconds() if investigation.completed_at else 0.0
        result.alternatives = [HypothesisSummary(description=h.description, score=h.score) for h in hypotheses[1:4] if h.score > 0.1]
        challenges = binder.get_challenges()
        unresolved = [c.content for c in challenges if not c.resolved and c.severity == 'HIGH']
        if result.root_cause:
            binder.add_conclusion(root_cause=result.root_cause.root_cause, confidence_raw=result.root_cause.confidence.raw, confidence_calibrated=result.root_cause.confidence.calibrated, outcome=outcome.value, code_location=result.root_cause.code_location, code_snippet=result.root_cause.code_snippet, data_flow=result.root_cause.data_flow, caveats=result.root_cause.caveats, debugging_steps=result.root_cause.debugging_steps, unresolved_challenges=unresolved, created_by='Synthesizer', phase=6)
        else:
            binder.add_conclusion(root_cause=result.insufficient_reason or 'Unable to determine root cause', confidence_raw=0.0, confidence_calibrated=0.0, outcome=outcome.value, code_location=None, code_snippet=None, data_flow=None, caveats=result.missing_evidence or [], debugging_steps=['Gather additional evidence as listed in caveats'], unresolved_challenges=unresolved, created_by='Synthesizer', phase=6)
        return result

    async def synthesize_from_binder(self, binder: 'WorkBinder', investigation: Investigation, outcome: InvestigationOutcome) -> InvestigationResult:
        hypothesis_artifacts = binder.get_hypotheses()
        hypotheses = []
        for ha in hypothesis_artifacts:
            h = Hypothesis(id=ha.id, description=ha.description, source=ha.source, prior=ha.prior_probability, score=ha.score, supporting_evidence_ids=ha.supporting_evidence_ids, contradicting_evidence_ids=ha.contradicting_evidence_ids, binder_artifact_id=ha.id)
            hypotheses.append(h)
        hypotheses.sort(key=lambda h: h.score, reverse=True)
        evidence_artifacts = binder.get_evidence_items()
        evidence = Evidence()
        from srcs.models import EvidenceItem
        for ea in evidence_artifacts:
            item = EvidenceItem(id=ea.id, evidence_type=ea.evidence_type, content=ea.content, source=ea.source, strength=ea.strength, found=True)
            evidence.add(item)
        chain_artifacts = binder.get_causal_chains()
        chains = [CausalChainParser.chain_from_artifact(ca) for ca in chain_artifacts]
        challenge_artifacts = binder.get_challenges()
        challenges = []
        for chal_artifact in challenge_artifacts:
            c = Challenge(challenge_type=chal_artifact.severity, content=chal_artifact.content, severity=chal_artifact.severity, requires_response=chal_artifact.requires_response, resolved=chal_artifact.resolved, resolution=chal_artifact.resolution)
            challenges.append(c)
        investigation.challenges = challenges
        prior = PriorKnowledge()
        source_locations = binder.get_source_locations()
        if source_locations:
            from srcs.models import SourceLocation
            prior.source_locations = [SourceLocation(file_path=sl.file_path, line_number=sl.line_number, matched_line=sl.matched_line or '', match_score=sl.match_score, function_name=sl.function_name) for sl in source_locations]
        return await self.synthesize(investigation, outcome, hypotheses, chains, evidence, prior, binder=binder)

    async def _synthesize_confident(self, result: InvestigationResult, hypothesis: Hypothesis | None, chain: CausalChain | None, evidence: Evidence, challenges: list[Challenge] | None=None, prior: PriorKnowledge | None=None, all_hypotheses: list[Hypothesis] | None=None) -> InvestigationResult:
        if not hypothesis:
            result.outcome = InvestigationOutcome.INSUFFICIENT
            result.insufficient_reason = 'No viable hypothesis found'
            return result
        raw_confidence = self._calculate_raw_confidence(hypothesis, chain, evidence, challenges or [])
        try:
            calibration = await self._kb.get_calibration('default') if self._kb else None
        except Exception as e:
            logger.warning(f'Failed to get calibration: {e}')
            calibration = None
        calibrated, notes = calculate_calibrated_confidence(raw_confidence, calibration)
        code_snippet = None
        code_location = None
        data_flow = None
        sub_causes: list[SubCause] = []
        key_files: list[KeyFile] = []
        debugging_steps: list[str] = []
        if prior:
            code_snippet, code_location, data_flow = self._extract_code_context(prior)
            key_files = self._extract_key_files(prior, evidence)
            debugging_steps = self._generate_debugging_steps(hypothesis, prior, evidence)
        sub_causes = self._generate_sub_causes(hypothesis, all_hypotheses or [], evidence)
        result.root_cause = InvestigationConclusion(root_cause=hypothesis.description, confidence=CalibratedConfidence(raw=raw_confidence, calibrated=calibrated, derivation={'hypothesis_score': hypothesis.score, 'supporting_evidence': len(hypothesis.supporting_evidence_ids), 'contradicting_evidence': len(hypothesis.contradicting_evidence_ids)}, calibration_notes=notes), caveats=self._generate_caveats(hypothesis, chain, evidence), code_snippet=code_snippet, code_location=code_location, sub_causes=sub_causes, data_flow=data_flow, key_files=key_files, debugging_steps=debugging_steps)
        result.causal_chain = chain
        result.recommendations = self._generate_recommendations(hypothesis, chain)
        return result

    def _synthesize_uncertain(self, result: InvestigationResult, hypotheses: list[Hypothesis], evidence: Evidence) -> InvestigationResult:
        viable = [h for h in hypotheses if h.score > 0.2]
        result.viable_hypotheses = [HypothesisSummary(description=h.description, score=h.score) for h in viable]
        if len(viable) >= 2:
            result.discrimination_needed = [f'Need evidence to distinguish: {viable[0].description} vs {viable[1].description}']
        log_evidence = [e for e in evidence.items.values() if e.evidence_type == 'log' and e.found]
        code_evidence = [e for e in evidence.items.values() if e.evidence_type == 'code' and e.found]
        if not log_evidence:
            result.recommendations = self._generate_code_only_recommendations(hypotheses, code_evidence)
        else:
            result.recommendations = ['Collect additional context logs', 'Check for related errors in other components', 'Review recent configuration changes']
        return result

    def _generate_code_only_recommendations(self, hypotheses: list[Hypothesis], code_evidence: list) -> list[str]:
        recommendations = ['Investigation limited to static code analysis (no runtime logs available)']
        code_locations = []
        for item in code_evidence[:5]:
            if item.source and ':' in item.source:
                code_locations.append(item.source)
        if code_locations:
            recommendations.append(f"Consider adding instrumentation/logging at: {', '.join(code_locations[:3])}")
        for h in hypotheses[:2]:
            desc_lower = h.description.lower()
            if any((term in desc_lower for term in ['race', 'thread', 'concurrency'])):
                recommendations.append('Run with thread sanitizer (TSAN) to detect race conditions')
            elif any((term in desc_lower for term in ['null', 'pointer', 'invalid'])):
                recommendations.append('Run with address sanitizer (ASAN) to detect memory issues')
            elif any((term in desc_lower for term in ['config', 'parameter'])):
                recommendations.append('Verify FCL configuration values match expected ranges')
            elif any((term in desc_lower for term in ['timeout', 'timing'])):
                recommendations.append('Add timing instrumentation to measure actual vs expected durations')
        recommendations.append('Reproduce the error with verbose logging enabled to gather runtime data')
        return recommendations[:5]

    def _synthesize_insufficient(self, result: InvestigationResult, hypotheses: list[Hypothesis], evidence: Evidence, detective_contribution: dict | None=None) -> InvestigationResult:
        log_evidence = [e for e in evidence.items.values() if e.evidence_type == 'log' and e.found]
        code_evidence = [e for e in evidence.items.values() if e.evidence_type == 'code' and e.found]
        if not hypotheses:
            result.insufficient_reason = 'Unable to generate viable hypotheses'
        elif all((h.score < 0.2 for h in hypotheses)):
            if not log_evidence:
                result.insufficient_reason = 'Static code analysis alone cannot discriminate between hypotheses; runtime data needed'
            else:
                result.insufficient_reason = 'Evidence does not strongly support any hypothesis'
        elif not log_evidence:
            result.insufficient_reason = 'Code-only investigation: insufficient discriminating evidence from static analysis'
        else:
            result.insufficient_reason = 'Insufficient evidence to reach confident conclusion'
        if detective_contribution and isinstance(detective_contribution, dict):
            alt_paths = detective_contribution.get('alternative_paths', {})
            paths = alt_paths.get('paths', [])
            if paths:
                result.missing_evidence = []
                for path in paths[:5]:
                    description = path.get('description', '')
                    expected_benefit = path.get('expected_benefit', '')
                    if description:
                        suggestion = description
                        if expected_benefit:
                            suggestion += f' ({expected_benefit})'
                        result.missing_evidence.append(suggestion)
                if len(result.missing_evidence) < 3:
                    generic = ['Additional context logs around the error time', 'Configuration state at time of error']
                    for g in generic:
                        if len(result.missing_evidence) < 3:
                            result.missing_evidence.append(g)
                if hypotheses:
                    result.viable_hypotheses = [HypothesisSummary(description=h.description, score=h.score) for h in hypotheses[:3]]
                return result
        if not log_evidence:
            result.missing_evidence = ['Runtime logs from the error occurrence', 'Stack trace or core dump from failure point', 'Timing data showing sequence of events', 'Memory/resource usage at time of error']
            if code_evidence:
                result.missing_evidence.append('Instrumentation at key code points identified in analysis')
        else:
            result.missing_evidence = ['Additional context logs around the error time', 'Configuration state at time of error', 'System resource metrics', 'Related errors from other components']
        if hypotheses:
            result.viable_hypotheses = [HypothesisSummary(description=h.description, score=h.score) for h in hypotheses[:3]]
        return result

    def _synthesize_contradictory(self, result: InvestigationResult, hypotheses: list[Hypothesis], evidence: Evidence) -> InvestigationResult:
        result.insufficient_reason = 'Evidence contradicts itself - multiple incompatible explanations'
        result.missing_evidence = ['Clarification of error sequence', 'Verification of log timestamps', 'Additional corroborating evidence']
        if hypotheses:
            result.viable_hypotheses = [HypothesisSummary(description=h.description, score=h.score) for h in hypotheses[:3]]
        return result

    def _calculate_raw_confidence(self, hypothesis: Hypothesis, chain: CausalChain | None, evidence: Evidence, challenges: list[Challenge] | None=None) -> float:
        base = 0.3 + hypothesis.score * 0.3 + hypothesis.prior * 0.1
        supporting = len(hypothesis.supporting_evidence_ids)
        contradicting = len(hypothesis.contradicting_evidence_ids)
        strong_support = sum((1 for eid in hypothesis.supporting_evidence_ids if eid in evidence.items and evidence.items[eid].strength == 'STRONG'))
        confidence = base + strong_support * 0.1 + supporting * 0.02 - contradicting * 0.08
        if chain:
            confidence += chain.evidence_coverage * 0.1
            confidence += chain.logical_validity * 0.05
        max_confidence = 0.95
        if challenges:
            high_unresolved = sum((1 for c in challenges if c.severity == 'HIGH' and (not c.resolved)))
            medium_unresolved = sum((1 for c in challenges if c.severity == 'MEDIUM' and (not c.resolved)))
            penalty = high_unresolved * 0.15 + medium_unresolved * 0.05
            max_confidence = max(0.3, 0.95 - penalty)
            if penalty > 0:
                logger.debug(f'Confidence penalty from challenges: -{penalty:.0%} ({high_unresolved} HIGH, {medium_unresolved} MEDIUM unresolved)')
        return max(0.1, min(max_confidence, confidence))

    def _generate_caveats(self, hypothesis: Hypothesis, chain: CausalChain | None, evidence: Evidence) -> list[str]:
        caveats = []
        if hypothesis.contradicting_evidence_ids:
            caveats.append(f'{len(hypothesis.contradicting_evidence_ids)} piece(s) of contradicting evidence were found but outweighed by supporting evidence')
        if chain:
            if chain.evidence_coverage < 0.7:
                caveats.append(f'Causal chain has {len(chain.gaps)} steps based on assumptions')
        strong_count = len(evidence.get_strong_evidence())
        if strong_count == 0:
            caveats.append('Conclusion based on moderate and weak evidence only')
        return caveats

    def _generate_recommendations(self, hypothesis: Hypothesis, chain: CausalChain | None) -> list[str]:
        recommendations = []
        desc = hypothesis.description.lower()
        if 'timeout' in desc or 'timing' in desc:
            recommendations.append('Check for network latency or hardware communication issues')
            recommendations.append('Review timeout configuration values')
        if 'configuration' in desc or 'config' in desc:
            recommendations.append('Review recent configuration changes')
            recommendations.append('Verify configuration consistency across components')
        if 'resource' in desc or 'memory' in desc or 'disk' in desc:
            recommendations.append('Monitor system resource usage')
            recommendations.append('Check for resource leaks in long-running processes')
        if 'hardware' in desc:
            recommendations.append('Check hardware status and connections')
            recommendations.append('Review hardware diagnostic logs')
        if 'software' in desc or 'bug' in desc:
            recommendations.append('Review recent code changes')
            recommendations.append('Check for known issues in software version')
        if not recommendations:
            recommendations.append('Review system logs for additional context')
            recommendations.append('Monitor for recurrence of this error')
        return recommendations[:4]

    def _extract_code_context(self, prior: PriorKnowledge) -> tuple[str | None, str | None, str | None]:
        if not prior.source_locations:
            return (None, None, None)
        best = max(prior.source_locations, key=lambda s: s.match_score)
        snippet_lines = []
        if best.context_before:
            snippet_lines.extend(best.context_before[-3:])
        snippet_lines.append(f'>>> {best.matched_line}')
        if best.context_after:
            snippet_lines.extend(best.context_after[:3])
        code_snippet = '\n'.join(snippet_lines) if snippet_lines else best.function_body
        location = f'{best.file_path}:{best.line_number}'
        if best.function_name:
            location += f' in {best.function_name}()'
        data_flow = best.call_graph_diagram
        if not data_flow and best.function_name:
            flow_parts = []
            if best.callers:
                caller_names = [c.get('caller_name', '') for c in best.callers[:2] if c.get('caller_name')]
                if caller_names:
                    flow_parts.append(' -> '.join((f'{n}()' for n in caller_names)))
            flow_parts.append(f'[{best.function_name}()]')
            if best.callees:
                callee_names = [c.get('callee_name', '') for c in best.callees[:2] if c.get('callee_name')]
                if callee_names:
                    flow_parts.append(' -> '.join((f'{n}()' for n in callee_names)))
            if len(flow_parts) > 1:
                data_flow = ' -> '.join(flow_parts)
        return (code_snippet, location, data_flow)

    def _generate_sub_causes(self, hypothesis: Hypothesis, all_hypotheses: list[Hypothesis], evidence: Evidence) -> list[SubCause]:
        sub_causes: list[SubCause] = []
        desc_lower = hypothesis.description.lower()
        if 'fragment' in desc_lower or 'generator' in desc_lower:
            sub_causes = [SubCause(description='Fragment Generator exception/logic error', probability=0.55, evidence_summary='Generator code throws or returns null'), SubCause(description='Race condition in fragment processing', probability=0.15, evidence_summary='Concurrent access to shared fragment state'), SubCause(description='Configuration mismatch', probability=0.1, evidence_summary="FCL parameters don't match expected values"), SubCause(description='Hardware communication failure', probability=0.08, evidence_summary='Device read/write operation failed'), SubCause(description='Resource exhaustion', probability=0.07, evidence_summary='Buffer or memory limits exceeded'), SubCause(description='Timing constraints violated', probability=0.05, evidence_summary='Operation exceeded deadline')]
        elif 'timeout' in desc_lower or 'timing' in desc_lower:
            sub_causes = [SubCause(description='Network latency/packet loss', probability=0.35, evidence_summary='Network delays exceeding timeout thresholds'), SubCause(description='Hardware response delay', probability=0.25, evidence_summary='Device taking too long to respond'), SubCause(description='CPU/resource starvation', probability=0.2, evidence_summary='System overload causing processing delays'), SubCause(description='Incorrect timeout configuration', probability=0.15, evidence_summary='Timeout values too aggressive for operation'), SubCause(description='Deadlock or blocking wait', probability=0.05, evidence_summary='Thread blocked waiting for unavailable resource')]
        elif 'null' in desc_lower or 'pointer' in desc_lower or 'nullptr' in desc_lower:
            sub_causes = [SubCause(description='Uninitialized pointer', probability=0.4, evidence_summary='Pointer used before assignment'), SubCause(description='Object destroyed prematurely', probability=0.25, evidence_summary='Object lifetime ended before use'), SubCause(description='Failed allocation', probability=0.15, evidence_summary='Memory allocation returned null'), SubCause(description='Missing null check', probability=0.1, evidence_summary='Code path lacks null validation'), SubCause(description='Race condition on shared pointer', probability=0.1, evidence_summary='Concurrent modification of pointer')]
        elif 'config' in desc_lower or 'parameter' in desc_lower or 'fcl' in desc_lower:
            sub_causes = [SubCause(description='Missing required parameter', probability=0.35, evidence_summary='Required FCL parameter not set'), SubCause(description='Invalid parameter value', probability=0.3, evidence_summary='Parameter value outside valid range'), SubCause(description='Parameter type mismatch', probability=0.15, evidence_summary="Parameter type doesn't match expected type"), SubCause(description='Conflicting parameters', probability=0.1, evidence_summary='Multiple parameters with incompatible values'), SubCause(description='Environment variable override', probability=0.1, evidence_summary='Environment overriding FCL setting')]
        elif 'exception' in desc_lower or 'throw' in desc_lower:
            sub_causes = [SubCause(description='Uncaught exception propagation', probability=0.4, evidence_summary='Exception thrown without handler'), SubCause(description='Exception in callback/handler', probability=0.25, evidence_summary='Exception thrown during event handling'), SubCause(description='Assertion failure', probability=0.2, evidence_summary='Runtime assertion check failed'), SubCause(description='Library/framework exception', probability=0.15, evidence_summary='Third-party code threw exception')]
        else:
            for h in all_hypotheses[:5]:
                if h.id != hypothesis.id and h.score > 0.1:
                    sub_causes.append(SubCause(description=h.description, probability=min(0.3, h.score * 0.5), evidence_summary=f'Alternative hypothesis (score: {h.score:.2f})'))
        if sub_causes:
            total = sum((sc.probability for sc in sub_causes))
            if total > 1.0:
                for sc in sub_causes:
                    sc.probability = sc.probability / total
        return sub_causes[:6]

    def _extract_key_files(self, prior: PriorKnowledge, evidence: Evidence) -> list[KeyFile]:
        files: list[KeyFile] = []
        seen_paths: set[str] = set()
        for loc in prior.source_locations[:3]:
            if loc.file_path not in seen_paths:
                purpose = 'Error location'
                if loc.function_name:
                    purpose = f'Error in {loc.function_name}()'
                line_range = None
                if loc.function_start_line and loc.function_end_line:
                    line_range = f'lines {loc.function_start_line}-{loc.function_end_line}'
                files.append(KeyFile(file_path=loc.file_path, purpose=purpose, line_range=line_range))
                seen_paths.add(loc.file_path)
                if loc.callers:
                    for caller in loc.callers[:2]:
                        caller_file = caller.get('caller_file', '')
                        caller_name = caller.get('caller_name', '')
                        if caller_file and caller_file not in seen_paths:
                            files.append(KeyFile(file_path=caller_file, purpose=f'Caller: {caller_name}()' if caller_name else 'Caller function', line_range=None))
                            seen_paths.add(caller_file)
        for item in evidence.items.values():
            if item.evidence_type == 'code' and item.found and item.source:
                if ':' in item.source:
                    parts = item.source.split(':')
                    if len(parts) >= 2:
                        file_path = parts[1] if parts[0] == 'code' else parts[0]
                        if file_path and file_path not in seen_paths:
                            files.append(KeyFile(file_path=file_path, purpose='Evidence location', line_range=None))
                            seen_paths.add(file_path)
                            if len(files) >= 5:
                                break
        return files[:5]

    def _generate_debugging_steps(self, hypothesis: Hypothesis, prior: PriorKnowledge, evidence: Evidence) -> list[str]:
        steps: list[str] = []
        desc_lower = hypothesis.description.lower()
        func_name = None
        if prior.source_locations:
            func_name = prior.source_locations[0].function_name
        if 'fragment' in desc_lower or 'generator' in desc_lower:
            steps.append('Search logs for "exception caught in getNext" from CommandableFragmentGenerator')
            if func_name:
                steps.append(f'Check if generator_ptr_->exception() is true after error in {func_name}')
            steps.append('Verify hardware status via checkHWStatus_() return value')
            steps.append('Examine fragment_count_ in error message - early count (0-10) suggests initialization issue')
        elif 'timeout' in desc_lower or 'timing' in desc_lower:
            steps.append('Check network latency with ping/traceroute to remote endpoints')
            steps.append('Review timeout configuration in FCL files')
            steps.append('Add timing instrumentation to measure actual vs expected durations')
            steps.append('Check system load (top/htop) for CPU/memory pressure')
        elif 'null' in desc_lower or 'pointer' in desc_lower:
            steps.append('Run with AddressSanitizer (ASAN) to detect memory issues')
            if func_name:
                steps.append(f'Add null checks before dereference in {func_name}')
            steps.append('Check object lifecycle - ensure no use-after-free')
            steps.append('Review recent changes to pointer initialization')
        elif 'config' in desc_lower or 'parameter' in desc_lower:
            steps.append('Verify FCL configuration values match expected ranges')
            steps.append('Check for missing required parameters in configuration')
            steps.append('Compare working vs failing configuration files')
            steps.append('Check environment variable overrides')
        elif 'race' in desc_lower or 'thread' in desc_lower or 'concurrent' in desc_lower:
            steps.append('Run with ThreadSanitizer (TSAN) to detect race conditions')
            steps.append('Review locking strategy around shared data')
            steps.append('Check for missing mutex/lock guards')
            steps.append('Look for atomic operations that should be protected')
        elif 'exception' in desc_lower:
            steps.append('Enable verbose exception logging')
            steps.append('Add try-catch blocks around suspected code')
            steps.append('Check exception handling in callbacks and event handlers')
            steps.append('Review stack trace for exception origin')
        else:
            if func_name:
                steps.append(f'Add diagnostic logging in {func_name}')
            steps.append('Enable TRACE/debug logging for the component')
            steps.append('Check for related errors in other components')
        if prior.source_locations:
            best = prior.source_locations[0]
            steps.append(f'Review source code at {best.file_path}:{best.line_number}')
        steps.append('Reproduce the issue with verbose logging enabled')
        return steps[:7]