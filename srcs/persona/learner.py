"""
File: learner.py
Purpose: Learner persona - Phase 7: Pattern Learning.
Category: Utility
Author: artdaq team
Depends: question, prompts, artifact_renderer, artifacts_types, relevance, ...
Exports: ErrorPatternInfo, RootCausePatternInfo, EvidencePatternInfo, StrategyInfo, CalibrationInfo, ...
Complexity: High | Lines: 388
"""

import logging
from typing import TYPE_CHECKING, Any, List
from pydantic import BaseModel
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_LEARNER, Persona
if TYPE_CHECKING:
    from srcs.models.question import QuestionContext
logger = logging.getLogger(__name__)

class ErrorPatternInfo(BaseModel):
    signature: str = ''
    message_template: str = ''
    contextual_indicators: List[str] = []
    false_positive_risk: str = 'medium'

class RootCausePatternInfo(BaseModel):
    description_template: str = ''
    category: str = ''
    confirming_evidence: List[str] = []
    refuting_evidence: List[str] = []

class EvidencePatternInfo(BaseModel):
    type: str
    query_template: str = ''
    strength: str = 'MODERATE'
    usefulness_score: float = 0.5

class StrategyInfo(BaseModel):
    preferred_approach: str = 'hybrid'
    key_queries: List[str] = []
    shortcuts: List[str] = []
    pitfalls: List[str] = []

class CalibrationInfo(BaseModel):
    stated_confidence: float = 0.5
    actual_accuracy: str = 'unknown'
    calibration_adjustment: str = 'maintain'
    sample_size_note: str = ''

class PatternExtractionResponse(BaseModel):
    error_pattern: ErrorPatternInfo
    root_cause_pattern: RootCausePatternInfo
    evidence_patterns: List[EvidencePatternInfo] = []
    strategy_recommendations: StrategyInfo
    calibration: CalibrationInfo
    lessons_learned: List[str] = []

class LearnerPersona(CollaborativePersona):

    def __init__(self) -> None:
        self._llm_extraction: PatternExtractionResponse | None = None

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_LEARNER]

    @property
    def traits(self) -> list[str]:
        return ['observant', 'pattern-seeking', 'adaptive', 'reflective', 'forward-looking']

    @property
    def thinking_style(self) -> str:
        return 'Pattern extraction - identifies recurring patterns, extracts lessons learned, updates knowledge base, improves future investigation efficiency'

    async def prepare(self, context: InvestigationContext) -> None:
        pass

    async def contribute(self, context: InvestigationContext) -> Contribution:
        should_learn = self._should_extract_patterns(context)
        if not should_learn:
            return Contribution(persona_id='learner', phase=PHASE_LEARNER, content={'patterns_learned': 0, 'reason': 'Investigation outcome insufficient'}, confidence=0.3, reasoning='Skipping pattern extraction - insufficient confidence')
        if context.llm is not None:
            llm_extraction = await self._extract_with_llm(context)
            if llm_extraction is not None:
                self._llm_extraction = llm_extraction
                content = self._build_content_from_llm(llm_extraction)
                return Contribution(persona_id='learner', phase=PHASE_LEARNER, content=content, confidence=0.7, reasoning=self._build_reasoning_from_llm(llm_extraction))
        patterns = self._extract_patterns_rules(context)
        confidence_val = patterns.get('confidence', 0.5)
        confidence = float(confidence_val) if isinstance(confidence_val, (int, float)) else 0.5
        return Contribution(persona_id='learner', phase=PHASE_LEARNER, content=patterns, confidence=confidence, reasoning=self._build_reasoning_rules(patterns))

    def _should_extract_patterns(self, context: InvestigationContext) -> bool:
        _skip_outcomes = {'INSUFFICIENT', 'UNCERTAIN', 'CONTRADICTORY'}
        synthesizer_contributions = [c for c in context.contributions if c.persona_id == 'synthesizer']
        if synthesizer_contributions:
            latest = synthesizer_contributions[-1]
            if latest.confidence < 0.4:
                return False
        judge_contributions = [c for c in context.contributions if c.persona_id == 'judge']
        if judge_contributions:
            latest = judge_contributions[-1]
            if isinstance(latest.content, dict):
                outcome = latest.content.get('outcome', 'INSUFFICIENT')
                if outcome in _skip_outcomes:
                    return False
        if not judge_contributions and context.binder is not None:
            binder_judge = context.binder.get_persona_contributions(persona_id='judge')
            if binder_judge:
                latest_binder = binder_judge[-1]
                if isinstance(latest_binder.content, dict):
                    outcome = latest_binder.content.get('outcome', 'INSUFFICIENT')
                    if outcome in _skip_outcomes:
                        return False
        return True

    async def _extract_with_llm(self, context: InvestigationContext) -> PatternExtractionResponse | None:
        binder = context.binder
        investigation_id = binder.id[:8] if hasattr(binder, 'id') else 'unknown'
        outcome = 'UNKNOWN'
        confidence = 0.5
        judge_contributions = [c for c in context.contributions if c.persona_id == 'judge']
        if judge_contributions:
            latest = judge_contributions[-1]
            if isinstance(latest.content, dict):
                outcome = latest.content.get('outcome', 'UNKNOWN')
            confidence = latest.confidence
        hypotheses_artifacts = binder.get_hypotheses()
        if hypotheses_artifacts:
            hypotheses_artifacts.sort(key=lambda h: h.score, reverse=True)
            root_cause = hypotheses_artifacts[0].description
        else:
            root_cause = 'Unable to determine'
        error_message = context.error.message if context.error else 'Unknown'
        error_component = context.error.component if context.error else 'Unknown'
        error_function = context.error.function if context.error else 'Unknown'
        from srcs.workbinder.artifact_renderer import render_evidence as _render_e
        from srcs.workbinder.artifact_renderer import render_hypothesis as _render_h
        from srcs.workbinder.artifacts_types import ArtifactType
        from srcs.workbinder.relevance import select_artifacts as select_relevant
        selected_hyps = select_relevant(binder, 'learner', ArtifactType.HYPOTHESIS_ARTIFACT)
        if selected_hyps:
            hypotheses_summary = '\n'.join([_render_h(h) for h in selected_hyps])
        elif hypotheses_artifacts:
            hypotheses_summary = '\n'.join([f'- {h.description} (score: {h.score:.2f}, source: {h.source})' for h in hypotheses_artifacts[:5]])
        else:
            hypotheses_summary = 'No hypotheses generated'
        evidence_artifacts = binder.get_evidence_items()
        selected_evs = select_relevant(binder, 'learner', ArtifactType.EVIDENCE_ARTIFACT)
        if selected_evs:
            evidence_summary = '\n'.join([_render_e(e) for e in selected_evs])
        elif evidence_artifacts:
            evidence_summary = '\n'.join([f'- [{e.strength}] {e.evidence_type}: {e.content}' for e in evidence_artifacts[:10]])
        else:
            evidence_summary = 'No evidence collected'
        what_worked = []
        what_didnt_work = []
        chain_artifacts = binder.get_causal_chains()
        if chain_artifacts:
            for chain in chain_artifacts:
                if chain.logical_validity > 0.7:
                    what_worked.append(f'Causal chain for {chain.hypothesis_id[:8]} had high validity')
                else:
                    what_didnt_work.append(f'Causal chain for {chain.hypothesis_id[:8]} had low validity')
        strong_evidence = [e for e in evidence_artifacts if e.strength == 'STRONG']
        if strong_evidence:
            what_worked.append(f'Found {len(strong_evidence)} pieces of strong evidence')
        else:
            what_didnt_work.append('No strong evidence was found')
        what_worked_text = '\n'.join([f'- {w}' for w in what_worked]) if what_worked else 'None identified'
        what_didnt_work_text = '\n'.join([f'- {w}' for w in what_didnt_work]) if what_didnt_work else 'None identified'
        try:
            user_prompt_template = get_user_prompt(UserPromptType.PATTERN_EXTRACTION)
            prompt = user_prompt_template.format(investigation_id=investigation_id, outcome=outcome, confidence=f'{confidence:.2f}', root_cause=root_cause, error_message=error_message, error_component=error_component, error_function=error_function, hypotheses_summary=hypotheses_summary, evidence_summary=evidence_summary, what_worked=what_worked_text, what_didnt_work=what_didnt_work_text)
        except Exception as e:
            logger.warning(f'Failed to format pattern extraction prompt: {e}')
            return None
        try:
            system_prompt = get_system_prompt(SystemPromptType.LEARNER)
            response = await self._call_llm_structured(context=context, prompt=prompt, response_model=PatternExtractionResponse, system_prompt=system_prompt, prompt_key='pattern_extraction')
            return response
        except Exception as e:
            logger.warning(f'LLM pattern extraction failed: {e}')
            return None

    def _build_content_from_llm(self, extraction: PatternExtractionResponse) -> dict[str, Any]:
        return {'error_pattern': {'signature': extraction.error_pattern.signature, 'message_template': extraction.error_pattern.message_template, 'contextual_indicators': extraction.error_pattern.contextual_indicators, 'false_positive_risk': extraction.error_pattern.false_positive_risk}, 'root_cause_pattern': {'description_template': extraction.root_cause_pattern.description_template, 'category': extraction.root_cause_pattern.category, 'confirming_evidence': extraction.root_cause_pattern.confirming_evidence, 'refuting_evidence': extraction.root_cause_pattern.refuting_evidence}, 'evidence_patterns': [{'type': e.type, 'query_template': e.query_template, 'strength': e.strength, 'usefulness_score': e.usefulness_score} for e in extraction.evidence_patterns], 'strategy_recommendations': {'preferred_approach': extraction.strategy_recommendations.preferred_approach, 'key_queries': extraction.strategy_recommendations.key_queries, 'shortcuts': extraction.strategy_recommendations.shortcuts, 'pitfalls': extraction.strategy_recommendations.pitfalls}, 'calibration': {'stated_confidence': extraction.calibration.stated_confidence, 'actual_accuracy': extraction.calibration.actual_accuracy, 'calibration_adjustment': extraction.calibration.calibration_adjustment, 'sample_size_note': extraction.calibration.sample_size_note}, 'lessons_learned': extraction.lessons_learned, 'patterns_learned': (1 if extraction.error_pattern.signature else 0) + (1 if extraction.root_cause_pattern.description_template else 0) + len(extraction.evidence_patterns), 'extraction_method': 'llm'}

    def _build_reasoning_from_llm(self, extraction: PatternExtractionResponse) -> str:
        parts: list[str] = []
        if extraction.error_pattern.signature:
            parts.append('Extracted error signature pattern')
        if extraction.root_cause_pattern.description_template:
            parts.append(f'Identified {extraction.root_cause_pattern.category} root cause pattern')
        if extraction.evidence_patterns:
            parts.append(f'Noted {len(extraction.evidence_patterns)} evidence patterns')
        if extraction.lessons_learned:
            parts.append(f'{len(extraction.lessons_learned)} lessons learned')
        if extraction.strategy_recommendations.shortcuts:
            parts.append(f'{len(extraction.strategy_recommendations.shortcuts)} shortcuts identified')
        return '; '.join(parts) if parts else 'Pattern extraction complete'

    def _extract_patterns_rules(self, context: InvestigationContext) -> dict[str, dict | list | float | str | None]:
        evidence_patterns: list[dict[str, str]] = []
        lessons_learned: list[str] = []
        patterns: dict[str, dict | list | float | str | None] = {'error_pattern': None, 'root_cause_pattern': None, 'evidence_patterns': evidence_patterns, 'calibration_update': None, 'lessons_learned': lessons_learned, 'confidence': 0.5, 'extraction_method': 'rules'}
        if context.error:
            patterns['error_pattern'] = {'component': context.error.component, 'function': context.error.function, 'message_fragment': context.error.message if context.error.message else None}
        if context.hypotheses:
            accepted = [h for h in context.hypotheses if h.status == 'accepted']
            if accepted:
                best = max(accepted, key=lambda h: h.score)
                patterns['root_cause_pattern'] = {'description': best.description, 'source': best.source, 'final_score': best.score}
                patterns['confidence'] = 0.7
        if context.evidence and context.evidence.items:
            strong = context.evidence.get_strong_evidence()
            for item in strong:
                evidence_patterns.append({'type': item.evidence_type, 'source': item.source, 'strength': item.strength})
        lessons_learned.extend(self._generate_lessons_rules(context))
        synthesizer_contributions = [c for c in context.contributions if c.persona_id == 'synthesizer']
        if synthesizer_contributions:
            latest = synthesizer_contributions[-1]
            if isinstance(latest.content, dict):
                stated_confidence = latest.confidence
                outcome = latest.content.get('outcome')
                if outcome:
                    patterns['calibration_update'] = {'stated_confidence': stated_confidence, 'outcome': outcome}
        return patterns

    def _generate_lessons_rules(self, context: InvestigationContext) -> list[str]:
        lessons = []
        if not context.evidence or not context.evidence.items:
            lessons.append('Investigation proceeded without significant evidence - early evidence gathering is crucial')
        if context.hypotheses:
            sources = {h.source.split(':')[0] for h in context.hypotheses}
            if len(sources) < 2:
                lessons.append('Hypotheses came from limited sources - consider diversifying hypothesis generation')
        high_confidence_contributions = [c for c in context.contributions if c.confidence > 0.8]
        if high_confidence_contributions:
            lessons.append(f'{len(high_confidence_contributions)} high-confidence contributions - track actual accuracy for calibration')
        return lessons

    def _build_reasoning_rules(self, patterns: dict) -> str:
        parts = []
        if patterns['error_pattern']:
            parts.append('Extracted error signature pattern')
        if patterns['root_cause_pattern']:
            parts.append('Identified root cause pattern for future matching')
        if patterns['evidence_patterns']:
            parts.append(f"Noted {len(patterns['evidence_patterns'])} useful evidence patterns")
        if patterns['lessons_learned']:
            parts.append(f"{len(patterns['lessons_learned'])} lessons extracted")
        return '; '.join(parts) if parts else 'Pattern extraction complete'

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights: list[str] = []
        uncertainties: list[str] = []
        suggestions: list[str] = []
        if self._llm_extraction is not None:
            extraction = self._llm_extraction
            if extraction.error_pattern.signature:
                insights.append('Extracted generalizable error signature pattern')
                if extraction.error_pattern.false_positive_risk == 'high':
                    uncertainties.append('Error pattern has high false positive risk')
            if extraction.root_cause_pattern.description_template:
                insights.append(f'Identified {extraction.root_cause_pattern.category} root cause pattern')
            if extraction.evidence_patterns:
                strong_patterns = [e for e in extraction.evidence_patterns if e.strength == 'STRONG']
                if strong_patterns:
                    insights.append(f'{len(strong_patterns)} strong evidence patterns identified')
            if extraction.strategy_recommendations.shortcuts:
                for shortcut in extraction.strategy_recommendations.shortcuts[:2]:
                    insights.append(f'Shortcut: {shortcut}')
            if extraction.strategy_recommendations.pitfalls:
                for pitfall in extraction.strategy_recommendations.pitfalls[:2]:
                    uncertainties.append(f'Pitfall to avoid: {pitfall}')
            if extraction.calibration.calibration_adjustment == 'decrease':
                uncertainties.append('Confidence was overstated - adjust calibration')
            elif extraction.calibration.calibration_adjustment == 'increase':
                insights.append('Confidence was understated - can be more confident')
            for lesson in extraction.lessons_learned[:3]:
                suggestions.append(f'Lesson: {lesson}')
        else:
            patterns = self._extract_patterns_rules(context)
            if patterns['root_cause_pattern']:
                insights.append('Root cause pattern captured for future pattern matching')
            evidence_patterns = patterns.get('evidence_patterns', [])
            if isinstance(evidence_patterns, list) and evidence_patterns:
                insights.append(f'{len(evidence_patterns)} evidence patterns recorded')
            if not patterns['error_pattern']:
                uncertainties.append('Could not extract clear error signature')
                suggestions.append('Consider standardizing error message formats')
            lessons_learned = patterns.get('lessons_learned', [])
            if isinstance(lessons_learned, list):
                for lesson in lessons_learned:
                    suggestions.append(f'Lesson: {lesson}')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f"I'll remember that, {other.metadata.name}. This insight will help with future investigations."

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        reasoning_str = str(contribution.reasoning).lower()
        if 'pattern' in reasoning_str or 'recurring' in reasoning_str:
            strengths.append('Identifies patterns for future reference')
        if contribution.confidence > 0:
            strengths.append('Confidence level provides calibration data')
        content_str = str(contribution.content).lower()
        if 'unique' in content_str or 'unprecedented' in content_str:
            issues.append('Claims of uniqueness limit pattern learning')
            recommendations.append('Consider what general lessons apply even to unique cases')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='LOW', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        reasoning_str = str(contribution.reasoning).lower()
        has_learning_value = any((term in reasoning_str for term in ['pattern', 'lesson', 'future', 'similar', 'recurring']))
        return has_learning_value or bool(contribution.reasoning)

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        content: dict = {'learning_opportunities': [], 'related_topics': [], 'resources': [], 'answer': '', 'follow_up_questions': []}
        content['learning_opportunities'] = self._identify_learning(question, context)
        content['related_topics'] = self._suggest_related_topics(question)
        content['resources'] = self._recommend_resources(question)
        content['follow_up_questions'] = self._suggest_followups(question, context)
        content['answer'] = self._formulate_learning_answer(question, context)
        reasoning = f"Identified {len(content['learning_opportunities'])} learning opportunities and {len(content['related_topics'])} related topics"
        confidence = 0.6
        return Contribution(persona_id='learner', phase=PHASE_LEARNER, content=content, confidence=confidence, reasoning=reasoning)

    def _identify_learning(self, question: str, context: 'QuestionContext') -> list[str]:
        opportunities = []
        question_lower = question.lower()
        from srcs.models.question import QuestionType
        if context.question_type == QuestionType.WHY:
            opportunities.append('Understanding the underlying mechanisms helps with future troubleshooting')
        if context.question_type == QuestionType.TROUBLESHOOT:
            opportunities.append('Document this issue and solution for future reference')
            opportunities.append('Similar issues may have common root causes')
        if 'timeout' in question_lower:
            opportunities.append('Learn about timing parameters and their interactions')
        if 'config' in question_lower or 'fcl' in question_lower:
            opportunities.append('Understanding FCL configuration patterns improves efficiency')
        if 'fragment' in question_lower or 'event' in question_lower:
            opportunities.append('Study the artdaq data model (fragments, events, runs)')
        return opportunities[:4]

    def _suggest_related_topics(self, question: str) -> list[str]:
        topics = []
        question_lower = question.lower()
        topics.append('artdaq system architecture')
        topics.append('Component communication patterns')
        if 'boardreader' in question_lower:
            topics.append('Hardware interface design')
            topics.append('Data acquisition timing')
        if 'eventbuilder' in question_lower:
            topics.append('Event building algorithms')
            topics.append('Fragment synchronization')
        if 'config' in question_lower:
            topics.append('FHiCL parameter reference')
            topics.append('Configuration best practices')
        return topics[:5]

    def _recommend_resources(self, question: str) -> list[str]:
        resources = ['artdaq documentation (GitHub wiki)', 'artdaq source code examples', 'Fermilab DAQ workshops and tutorials']
        question_lower = question.lower()
        if 'config' in question_lower or 'fcl' in question_lower:
            resources.append('FHiCL language reference')
        if 'debug' in question_lower or 'troubleshoot' in question_lower:
            resources.append('artdaq debugging guide')
        return resources[:4]

    def _suggest_followups(self, question: str, context: 'QuestionContext') -> list[str]:
        followups = []
        question_lower = question.lower()
        if 'how' in question_lower:
            followups.append('What are common pitfalls to avoid?')
            followups.append('How does this relate to other components?')
        if 'why' in question_lower:
            followups.append('What would happen if conditions were different?')
            followups.append('How can this be prevented in the future?')
        if 'error' in question_lower or 'fail' in question_lower:
            followups.append('What monitoring can detect this early?')
            followups.append('What are related failure modes?')
        followups.append('What are best practices for this scenario?')
        return followups[:4]

    def _formulate_learning_answer(self, question: str, context: 'QuestionContext') -> str:
        opportunities = self._identify_learning(question, context)
        if opportunities:
            opp_text = '; '.join(opportunities[:2])
            return f'This question presents several learning opportunities: {opp_text}. Consider documenting the answer and solution for future reference, as similar questions may arise. The related topics listed can help build deeper understanding of the underlying concepts.'
        else:
            return 'This Q&A session can be valuable for future reference. Consider noting the key insights and any follow-up areas for further investigation.'