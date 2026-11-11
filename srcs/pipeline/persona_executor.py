"""
File: persona_executor.py
Purpose: Persona-integrated phase executors.
Category: Utility
Author: artdaq team
Depends: models, knowledge, logs, source_location, base, ...
Exports: PersonaExecutor, UnifiedPersonaExecutor
Complexity: High | Lines: 340
"""

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any
from srcs.persona.base import Contribution, InvestigationContext, Reflection
from srcs.persona.personas import PERSONAS
from .executor import PhaseExecutor
if TYPE_CHECKING:
    from srcs.models import InvestigationResult, PriorKnowledge
    from srcs.persona.base import BasePersona
    from srcs.workbinder import WorkBinder
logger = logging.getLogger(__name__)

class PersonaExecutor(PhaseExecutor):

    def __init__(self, persona: 'BasePersona'):
        self._persona = persona

    @property
    def executor_id(self) -> str:
        return self._persona.metadata.name.lower()

    async def execute(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        binder: 'WorkBinder | None' = inputs.get('binder')
        context = self._build_context(inputs)
        try:
            await self._persona.prepare(context)
        except Exception as e:
            logger.debug(f'Persona prepare failed: {e}')
        result = await self._execute_phase(inputs, config)
        self._update_context_with_results(context, result)
        try:
            contribution = await self._persona.contribute(context)
            if binder is not None:
                self._store_contribution(binder, contribution)
        except Exception as e:
            logger.debug(f'Persona contribute failed: {e}')
        try:
            reflection = await self._persona.reflect(context)
            if binder is not None:
                self._store_reflection(binder, reflection)
        except Exception as e:
            logger.debug(f'Persona reflect failed: {e}')
        return result

    @abstractmethod
    async def _execute_phase(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        ...

    def _build_context(self, inputs: dict[str, Any]) -> InvestigationContext:
        from srcs.models.logs import Log
        error = inputs.get('trigger_error')
        if error is None:
            from datetime import datetime
            error = Log(timestamp=datetime(1970, 1, 1), level='ERROR', component='unknown', message='Unknown error')
        binder = inputs.get('binder')
        investigation = inputs.get('investigation')
        if binder is None and investigation is not None:
            binder = getattr(investigation, 'binder', None)
        return InvestigationContext(error=error, context_logs=inputs.get('context_logs', []), binder=binder, prior_knowledge=inputs.get('prior_knowledge'), hypotheses=inputs.get('hypotheses', []), evidence=inputs.get('evidence'), source_files=inputs.get('source_files'), llm=inputs.get('llm'), kb=inputs.get('kb'), code_index=inputs.get('code_index'), source_locator=inputs.get('source_locator'), config=inputs.get('config'))

    def _update_context_with_results(self, context: InvestigationContext, result: dict[str, Any]) -> None:
        if 'hypotheses' in result:
            context.hypotheses = result['hypotheses']
        if 'evidence' in result:
            context.evidence = result['evidence']

    def _store_contribution(self, binder: 'WorkBinder', contribution: Contribution) -> None:
        content = contribution.content
        if not isinstance(content, dict):
            content = {'value': content}
        binder.add_persona_contribution(persona_id=contribution.persona_id, contribution_phase=contribution.phase, content=content, confidence=contribution.confidence, reasoning=contribution.reasoning, created_by=contribution.persona_id)

    def _store_reflection(self, binder: 'WorkBinder', reflection: Reflection) -> None:
        from srcs.workbinder.artifacts import FindingType
        for insight in reflection.insights:
            binder.add_finding(persona=self._persona.metadata.name, finding_type=FindingType.OBSERVATION, content=f'Insight: {insight}', phase=self._persona.metadata.phase)
        for uncertainty in reflection.uncertainties:
            binder.add_finding(persona=self._persona.metadata.name, finding_type=FindingType.QUESTION, content=f'Uncertainty: {uncertainty}', phase=self._persona.metadata.phase)
        for suggestion in reflection.suggestions:
            binder.add_finding(persona=self._persona.metadata.name, finding_type=FindingType.RECOMMENDATION, content=f'Suggestion: {suggestion}', phase=self._persona.metadata.phase)

class UnifiedPersonaExecutor(PhaseExecutor):

    def __init__(self, phase: int, persona_class: type['BasePersona']):
        self._phase = phase
        self._persona_class = persona_class
        self._persona: 'BasePersona | None' = None

    @property
    def executor_id(self) -> str:
        name = PERSONAS[self._phase].name
        return name.lower().replace("'", '').replace(' ', '_')

    async def execute(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        if self._persona is None:
            self._persona = self._persona_class()
        binder: 'WorkBinder | None' = inputs.get('binder')
        investigation = inputs.get('investigation')
        if binder is None and investigation is not None:
            binder = getattr(investigation, 'binder', None)
        context = self._build_context(inputs, binder)
        try:
            await self._persona.prepare(context)
            contribution = await self._persona.contribute(context)
            reflection = await self._persona.reflect(context)
            if binder is not None:
                self._store_contribution(binder, contribution)
                self._store_reflection(binder, reflection)
            return await self._map_outputs(contribution, context)
        except Exception as e:
            logger.error('Persona execution failed for phase %s: %s', self._phase, e, exc_info=True)
            if binder is not None:
                try:
                    binder.fail_phase(self._phase, str(e), modified_by='system')
                except Exception:
                    logger.exception('Failed to record phase failure in binder')
            return self._get_empty_outputs()

    def _build_context(self, inputs: dict[str, Any], binder: 'WorkBinder | None') -> InvestigationContext:
        from srcs.models.logs import Log
        error = inputs.get('trigger_error')
        if error is None:
            from datetime import datetime
            error = Log(timestamp=datetime(1970, 1, 1), level='ERROR', component='unknown', message='Unknown error')
        return InvestigationContext(error=error, context_logs=inputs.get('context_logs', []), binder=binder, prior_knowledge=inputs.get('prior_knowledge'), hypotheses=inputs.get('hypotheses', []), evidence=inputs.get('evidence'), contributions=inputs.get('contributions', []), source_files=inputs.get('source_files'), llm=inputs.get('llm'), kb=inputs.get('kb'), code_index=inputs.get('code_index'), source_locator=inputs.get('source_locator'), config=inputs.get('config'))

    async def _map_outputs(self, contribution: Contribution, context: InvestigationContext) -> dict[str, Any]:
        content = contribution.content
        phase = self._phase
        if phase == -1:
            outputs: dict[str, Any] = {}
            if isinstance(content, dict):
                primary = content.get('primary_error')
                primary_ctx = content.get('primary_context')
                if primary is not None:
                    outputs['trigger_error'] = primary
                if primary_ctx:
                    outputs['context_logs'] = primary_ctx
            return outputs
        if phase == 0:
            if hasattr(content, 'matched_patterns'):
                return {'prior_knowledge': content}
            elif isinstance(content, dict):
                if context.prior_knowledge is not None:
                    return {'prior_knowledge': context.prior_knowledge}
                pk = await self._reconstruct_prior_knowledge(content, context)
                return {'prior_knowledge': pk}
            else:
                from srcs.models import PriorKnowledge
                return {'prior_knowledge': PriorKnowledge()}
        elif phase == 1:
            if context.hypotheses:
                return {'hypotheses': context.hypotheses}
            elif isinstance(content, list):
                return {'hypotheses': content}
            elif isinstance(content, dict) and 'hypotheses' in content:
                return {'hypotheses': content['hypotheses']}
            else:
                return {'hypotheses': []}
        elif phase == 2:
            return {'evidence': context.evidence, 'hypotheses': context.hypotheses}
        elif phase == 3:
            if isinstance(content, dict) and 'chain_details' in content:
                chains = []
                if context.binder is not None:
                    chain_artifacts = context.binder.get_causal_chains()
                    for ca in chain_artifacts:
                        from srcs.models import CausalChain, CausalStep
                        chain = CausalChain(hypothesis_id=ca.hypothesis_id)
                        for step_data in ca.steps:
                            step = CausalStep(step_order=step_data.get('step_order', 0), claim=step_data.get('claim', ''), mechanism=step_data.get('mechanism', ''), evidence_ids=step_data.get('evidence_ids', []), is_assumption=step_data.get('is_assumption', False))
                            chain.steps.append(step)
                        chain.logical_validity = ca.logical_validity
                        chain.evidence_coverage = ca.evidence_coverage
                        chains.append(chain)
                return {'causal_chains': chains}
            return {'causal_chains': []}
        elif phase == 4:
            challenges = []
            if context.binder is not None:
                challenge_artifacts = context.binder.get_challenges()
                for challenge_artifact in challenge_artifacts:
                    from srcs.models import Challenge
                    challenge = Challenge(challenge_type=challenge_artifact.challenge_type, content=challenge_artifact.content, severity=challenge_artifact.severity, requires_response=challenge_artifact.requires_response, resolved=challenge_artifact.resolved, resolution=challenge_artifact.resolution)
                    challenges.append(challenge)
            return {'challenges': challenges}
        elif phase == 5:
            if isinstance(content, dict) and 'outcome' in content:
                outcome_str = content['outcome']
                from srcs.models import InvestigationOutcome
                try:
                    outcome = InvestigationOutcome(outcome_str)
                except ValueError:
                    outcome = InvestigationOutcome.INSUFFICIENT
                judge_outputs: dict[str, Any] = {'outcome': outcome}
                confidence = content.get('confidence')
                if isinstance(confidence, (int, float)) and (not isinstance(confidence, bool)):
                    judge_outputs['outcome_confidence'] = max(0.0, min(1.0, float(confidence)))
                return judge_outputs
            return {'outcome': None}
        elif phase == 6:
            result = self._build_investigation_result(content, context)
            return {'result': result, 'synthesis': content}
        elif phase == 7:
            if isinstance(content, dict):
                return {'patterns': content.get('lessons_learned', [])}
            return {'patterns': []}
        return {'result': content}

    def _get_empty_outputs(self) -> dict[str, Any]:
        phase = self._phase
        if phase == -1:
            return {}
        elif phase == 0:
            from srcs.models import PriorKnowledge
            return {'prior_knowledge': PriorKnowledge()}
        elif phase == 1:
            return {'hypotheses': []}
        elif phase == 2:
            from srcs.models import Evidence
            return {'evidence': Evidence(), 'hypotheses': []}
        elif phase == 3:
            return {'causal_chains': []}
        elif phase == 4:
            return {'challenges': []}
        elif phase == 5:
            from srcs.models import InvestigationOutcome
            return {'outcome': InvestigationOutcome.INSUFFICIENT}
        elif phase == 6:
            return {'result': None}
        elif phase == 7:
            return {'patterns': []}
        return {}

    async def _reconstruct_prior_knowledge(self, content: dict[str, Any], context: InvestigationContext) -> 'PriorKnowledge':
        from srcs.models import PriorKnowledge
        from srcs.models.knowledge import ConfigParam, ConfigurationContext, DiagnosticHistory, ErrorPattern, EvidenceQueryTemplate, PatternMatch, RecommendedHypothesis, ResolutionDigest, SimilarInvestigation
        from srcs.models.source_location import SourceLocation
        matched_patterns: list[PatternMatch] = []
        raw_patterns = content.get('matched_patterns', [])
        if raw_patterns:
            pattern_ids = [p.get('pattern_id', '') for p in raw_patterns if p.get('pattern_id')]
            patterns_by_id: dict[str, ErrorPattern] = {}
            if pattern_ids and context.kb is not None:
                try:
                    db_patterns = await context.kb.get_patterns_by_ids(pattern_ids)
                    patterns_by_id = {p.id: p for p in db_patterns}
                except Exception as e:
                    logger.debug(f'Failed to fetch patterns from DB: {e}')
            for p in raw_patterns:
                pid = p.get('pattern_id', '')
                if pid in patterns_by_id:
                    matched_patterns.append(PatternMatch(pattern=patterns_by_id[pid], confidence=p.get('confidence', 0.0), matched_fields=p.get('matched_fields', ['message'])))
        similar_investigations = [SimilarInvestigation(investigation_id=s.get('investigation_id', ''), similarity_score=s.get('score', s.get('similarity_score', 0.0)), root_cause=s.get('root_cause'), was_correct=s.get('was_correct'), outcome=s.get('outcome')) for s in content.get('similar_investigations', [])]
        source_locations = [SourceLocation(file_path=loc.get('file_path', ''), line_number=loc.get('line_number', 0), matched_line=loc.get('matched_line', ''), function_name=loc.get('function_name'), match_score=loc.get('match_score', 0.0), context_before=loc.get('context_before', []), context_after=loc.get('context_after', []), function_signature=loc.get('function_signature'), function_summary=loc.get('function_summary'), function_body=loc.get('function_body'), call_graph_diagram=loc.get('call_graph_diagram')) for loc in content.get('source_locations', [])]
        recommended_hypotheses = [RecommendedHypothesis(description=h.get('description', ''), source=h.get('source', 'unknown'), prior=h.get('prior', 0.2), is_authoritative=h.get('is_authoritative', False)) for h in content.get('recommended_hypotheses', [])]
        recommended_queries = [EvidenceQueryTemplate(query_type=q.get('query_type', ''), query_template=q.get('query_template', ''), expected_result=q.get('expected_result'), full_source=q.get('full_source', False)) for q in content.get('recommended_queries', [])]
        resolution_digest = [ResolutionDigest(investigation_id=r.get('investigation_id', ''), root_cause=r.get('root_cause'), resolution_action=r.get('resolution_action'), resolution_category=r.get('resolution_category', 'unknown'), resolution_success=r.get('resolution_success'), confidence=r.get('confidence', 0.0), applicability_notes=r.get('applicability_notes', '')) for r in content.get('resolution_digest', [])]
        configuration_context = None
        raw_config = content.get('configuration_context')
        if raw_config and isinstance(raw_config, dict):
            configuration_context = ConfigurationContext(component=raw_config.get('component', ''), relevant_params=[ConfigParam(name=p.get('name', ''), current_value=p.get('current_value'), source=p.get('source', ''), note=p.get('note', '')) for p in raw_config.get('relevant_params', [])], config_from_similar_successes=raw_config.get('config_from_similar_successes', {}), deviation_flags=raw_config.get('deviation_flags', []))
        diagnostic_history = None
        raw_diag = content.get('diagnostic_history')
        if raw_diag and isinstance(raw_diag, dict):
            diagnostic_history = DiagnosticHistory(error_signature=raw_diag.get('error_signature', ''), total_occurrences=raw_diag.get('total_occurrences', 0), resolved_count=raw_diag.get('resolved_count', 0), resolution_rate=raw_diag.get('resolution_rate', 0.0), avg_confidence=raw_diag.get('avg_confidence', 0.0), common_root_causes=[(c.get('cause', ''), c.get('frequency', 0.0)) for c in raw_diag.get('common_root_causes', [])])
        return PriorKnowledge(matched_patterns=matched_patterns, similar_investigations=similar_investigations, source_locations=source_locations, recommended_hypotheses=recommended_hypotheses, recommended_queries=recommended_queries, resolution_digest=resolution_digest, configuration_context=configuration_context, diagnostic_history=diagnostic_history)

    def _build_investigation_result(self, content: Any, context: InvestigationContext) -> 'InvestigationResult':
        from srcs.models import CalibratedConfidence, HypothesisSummary, InvestigationConclusion, InvestigationOutcome, InvestigationResult
        investigation_id = 'unknown'
        if context.binder is not None:
            investigation_id = str(getattr(context.binder, 'investigation_id', None) or getattr(context.binder, 'id', 'unknown'))
        outcome = InvestigationOutcome.INSUFFICIENT
        if isinstance(content, dict):
            outcome_str = content.get('outcome')
            if outcome_str:
                try:
                    outcome = InvestigationOutcome(outcome_str)
                except ValueError:
                    pass
        if context.binder is not None:
            judge_contributions = context.binder.get_persona_contributions(persona_id='judge')
            for contrib in judge_contributions:
                if isinstance(contrib.content, dict):
                    judge_outcome = contrib.content.get('outcome')
                    if judge_outcome:
                        try:
                            outcome = InvestigationOutcome(judge_outcome)
                        except ValueError:
                            pass
        result = InvestigationResult(investigation_id=investigation_id, outcome=outcome)
        if isinstance(content, dict):
            confidence_data = content.get('confidence', {})
            raw_score = 0.5
            calibrated_score = 0.5
            if isinstance(confidence_data, dict):
                raw_score = float(confidence_data.get('raw_score') or 0.5)
                calibrated_score = float(confidence_data.get('calibrated_score') or raw_score)
            if outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
                root_cause_data = content.get('root_cause', {})
                root_cause_desc = 'Unknown'
                code_location = None
                if isinstance(root_cause_data, dict):
                    root_cause_desc = root_cause_data.get('description', 'Unknown')
                    code_location = root_cause_data.get('code_location')
                elif isinstance(root_cause_data, str):
                    root_cause_desc = root_cause_data
                result.root_cause = InvestigationConclusion(root_cause=root_cause_desc, confidence=CalibratedConfidence(raw=raw_score, calibrated=calibrated_score), caveats=content.get('caveats', []), code_location=code_location, debugging_steps=[s.get('action', str(s)) if isinstance(s, dict) else str(s) for s in content.get('debugging_steps', [])])
                result.recommendations = [s.get('action', str(s)) if isinstance(s, dict) else str(s) for s in content.get('debugging_steps', [])[:4]]
            elif outcome == InvestigationOutcome.UNCERTAIN:
                if context.hypotheses:
                    result.viable_hypotheses = [HypothesisSummary(description=h.description, score=h.score) for h in context.hypotheses[:3] if h.score > 0.2]
                result.discrimination_needed = content.get('discrimination_needed', [])
            elif outcome == InvestigationOutcome.INSUFFICIENT:
                result.insufficient_reason = content.get('insufficient_reason', 'Unable to determine root cause from available evidence')
                result.missing_evidence = content.get('missing_evidence', [])
            result.evidence_summary = content.get('evidence_summary', '')
            executive_summary = content.get('executive_summary', '')
            if executive_summary:
                result.executive_summary = executive_summary
                result.explanation = executive_summary
            result.confidence = raw_score
        return result

    def _store_contribution(self, binder: 'WorkBinder', contribution: Contribution) -> None:
        content = contribution.content
        if not isinstance(content, dict):
            content = {'value': content}
        binder.add_persona_contribution(persona_id=contribution.persona_id, contribution_phase=contribution.phase, content=content, confidence=contribution.confidence, reasoning=contribution.reasoning, created_by=contribution.persona_id)

    def _store_reflection(self, binder: 'WorkBinder', reflection: Reflection) -> None:
        from srcs.workbinder.artifacts import FindingType
        persona_name = PERSONAS[self._phase].name
        for insight in reflection.insights:
            binder.add_finding(persona=persona_name, finding_type=FindingType.OBSERVATION, content=f'Insight: {insight}', phase=self._phase)
        for uncertainty in reflection.uncertainties:
            binder.add_finding(persona=persona_name, finding_type=FindingType.QUESTION, content=f'Uncertainty: {uncertainty}', phase=self._phase)
        for suggestion in reflection.suggestions:
            binder.add_finding(persona=persona_name, finding_type=FindingType.RECOMMENDATION, content=f'Suggestion: {suggestion}', phase=self._phase)