"""
File: orchestrator.py
Purpose: Panel orchestrator for question answering.
Category: Utility
Author: artdaq team
Depends: logs, question
Exports: PanelOrchestrator
Complexity: High | Lines: 216
"""

import logging
from typing import Any, Callable
from srcs.models.logs import Log
from srcs.models.question import PanelResponse, QuestionContext, QuestionType, SourceCitation, VotingResult
from .base import CollaborativePersona, Contribution, Critique, Discussion
logger = logging.getLogger(__name__)
QAEvent = dict[str, Any]
QACallback = Callable[[QAEvent], None]

class PanelOrchestrator:
    PERSONA_SELECTION: dict[QuestionType, list[int]] = {QuestionType.HOW_TO: [0, 6, 3], QuestionType.WHY: [1, 3, 2], QuestionType.WHAT_IS: [0, 6], QuestionType.TROUBLESHOOT: [0, 1, 2, 3, 4, 5, 6], QuestionType.COMPARE: [0, 4, 5], QuestionType.BEST_PRACTICE: [0, 5, 6]}
    CONSENSUS_THRESHOLD = 0.7
    MAX_DELIBERATION_ROUNDS = 2

    def __init__(self, llm_provider: Any=None) -> None:
        self._llm_provider = llm_provider
        self._personas: dict[int, CollaborativePersona] = {}

    def _get_persona(self, phase: int) -> CollaborativePersona:
        if phase not in self._personas:
            from .archivist import ArchivistPersona
            from .detective import DetectivePersona
            from .judge import JudgePersona
            from .learner import LearnerPersona
            from .logician import LogicianPersona
            from .skeptic import SkepticPersona
            from .synthesizer import SynthesizerPersona
            from .theorist import TheoristPersona
            persona_classes: dict[int, type[CollaborativePersona]] = {0: ArchivistPersona, 1: TheoristPersona, 2: DetectivePersona, 3: LogicianPersona, 4: SkepticPersona, 5: JudgePersona, 6: SynthesizerPersona, 7: LearnerPersona}
            if phase in persona_classes:
                self._personas[phase] = persona_classes[phase]()
            else:
                raise ValueError(f'Unknown persona phase: {phase}')
        return self._personas[phase]

    def _classify_question(self, question: str) -> QuestionType:
        question_lower = question.lower()
        troubleshoot_keywords = ['error', 'fail', 'crash', 'timeout', 'problem', 'issue', 'not working', "doesn't work", 'broken', 'exception']
        if any((kw in question_lower for kw in troubleshoot_keywords)):
            return QuestionType.TROUBLESHOOT
        how_to_patterns = ['how do i', 'how to', 'how can i', 'how should i']
        if any((pattern in question_lower for pattern in how_to_patterns)):
            return QuestionType.HOW_TO
        if question_lower.startswith('why ') or ' why ' in question_lower:
            return QuestionType.WHY
        what_is_patterns = ['what is', 'what are', 'what does', 'explain']
        if any((pattern in question_lower for pattern in what_is_patterns)):
            return QuestionType.WHAT_IS
        compare_patterns = ['difference between', 'compare', 'vs', 'versus', 'which is better', 'pros and cons']
        if any((pattern in question_lower for pattern in compare_patterns)):
            return QuestionType.COMPARE
        best_practice_patterns = ['best practice', 'best way', 'recommended', 'should i', 'is it good to', 'proper way']
        if any((pattern in question_lower for pattern in best_practice_patterns)):
            return QuestionType.BEST_PRACTICE
        return QuestionType.HOW_TO

    async def answer(self, question: str, related_logs: list[Log] | None=None, callback: QACallback | None=None) -> PanelResponse:
        question_type = self._classify_question(question)
        if callback:
            callback({'event': 'classification', 'question_type': question_type.value})
        context = QuestionContext(question=question, question_type=question_type, related_logs=related_logs or [])
        persona_phases = self.PERSONA_SELECTION.get(question_type, [0, 1, 2, 3, 4, 5, 6])
        personas = [self._get_persona(phase) for phase in persona_phases]
        if callback:
            callback({'event': 'panel_selected', 'personas': [p.metadata.name for p in personas]})
        for persona in personas:
            if callback:
                callback({'event': 'contribution_start', 'persona': persona.metadata.name})
            try:
                contribution = await persona.answer_question(context)
                context.add_contribution(contribution)
                if callback:
                    callback({'event': 'contribution_complete', 'persona': persona.metadata.name, 'confidence': contribution.confidence})
            except Exception as e:
                logger.warning(f'Persona {persona.metadata.name} failed to contribute: {e}')
                if callback:
                    callback({'event': 'contribution_error', 'persona': persona.metadata.name, 'error': str(e)})
        voting_results = await self._voting_round(context, personas)
        context.voting_results = voting_results
        if callback:
            callback({'event': 'voting_complete', 'results': {pid: {'score': v.consensus_score, 'endorsements': v.endorsements} for pid, v in voting_results.items()}})
        min_consensus = min((v.consensus_score for v in voting_results.values()), default=1.0)
        if min_consensus < self.CONSENSUS_THRESHOLD and len(context.contributions) > 1:
            if callback:
                callback({'event': 'deliberation_start'})
            await self._deliberation_rounds(context, personas)
            voting_results = await self._voting_round(context, personas)
            context.voting_results = voting_results
            if callback:
                callback({'event': 'deliberation_complete', 'new_consensus': min((v.consensus_score for v in voting_results.values()), default=1.0)})
        response = self._synthesize_response(context, voting_results)
        if callback:
            callback({'event': 'synthesis_complete', 'confidence': response.confidence})
        return response

    async def _voting_round(self, context: QuestionContext, personas: list[CollaborativePersona]) -> dict[str, VotingResult]:
        results: dict[str, VotingResult] = {}
        for contribution in context.contributions:
            endorsements = 0
            critiques: list[Critique] = []
            for persona in personas:
                if persona.metadata.name.lower() == contribution.persona_id:
                    continue
                try:
                    if await persona.endorse(contribution):
                        endorsements += 1
                    else:
                        critique = await persona.critique(contribution)
                        critiques.append(critique)
                except Exception as e:
                    logger.warning(f'Persona {persona.metadata.name} failed to vote: {e}')
            other_count = len(personas) - 1
            consensus_score = endorsements / other_count if other_count > 0 else 1.0
            results[contribution.persona_id] = VotingResult(endorsements=endorsements, critiques=critiques, consensus_score=consensus_score)
        return results

    async def _deliberation_rounds(self, context: QuestionContext, personas: list[CollaborativePersona], max_rounds: int | None=None) -> list[Discussion]:
        max_rounds = max_rounds or self.MAX_DELIBERATION_ROUNDS
        discussions: list[Discussion] = []
        for round_num in range(max_rounds):
            disagreements = self._identify_disagreements(context)
            if not disagreements:
                break
            for topic in disagreements:
                discussion = Discussion(topic=topic, participants=[p.metadata.name.lower() for p in personas])
                for persona in personas:
                    try:
                        response = await persona.respond_to(personas[0], f'Consider this issue: {topic}. How does this affect your contribution?')
                        discussion.add_exchange(persona.metadata.name.lower(), response)
                    except Exception as e:
                        logger.warning(f'Persona {persona.metadata.name} failed in deliberation: {e}')
                discussions.append(discussion)
                context.discussions.append(discussion)
        return discussions

    def _identify_disagreements(self, context: QuestionContext) -> list[str]:
        disagreements: list[str] = []
        for persona_id, result in context.voting_results.items():
            if result.consensus_score < self.CONSENSUS_THRESHOLD:
                for critique in result.critiques:
                    for issue in critique.issues:
                        if issue not in disagreements:
                            disagreements.append(f"{persona_id}'s contribution: {issue}")
        return disagreements[:3]

    def _synthesize_response(self, context: QuestionContext, voting_results: dict[str, VotingResult]) -> PanelResponse:
        scored_contributions: list[tuple[float, Contribution]] = []
        for contrib in context.contributions:
            vote_result = voting_results.get(contrib.persona_id, VotingResult(endorsements=0, consensus_score=0.5))
            combined = vote_result.consensus_score * contrib.confidence
            scored_contributions.append((combined, contrib))
        scored_contributions.sort(key=lambda x: x[0], reverse=True)
        answer_parts: list[str] = []
        key_points: list[str] = []
        sources: list[str] = []
        caveats: list[str] = []
        dissenting_views: list[str] = []
        contributions_summary: dict[str, str] = {}
        all_citations: list[SourceCitation] = []
        for score, contrib in scored_contributions:
            persona_name = contrib.persona_id.title()
            contributions_summary[persona_name] = contrib.reasoning
            content = contrib.content
            if isinstance(content, dict):
                if 'answer' in content:
                    answer_parts.append(content['answer'])
                elif 'response' in content:
                    answer_parts.append(content['response'])
                elif 'analysis' in content:
                    answer_parts.append(content['analysis'])
                if 'key_points' in content:
                    key_points.extend(content['key_points'])
                if 'sources' in content:
                    sources.extend(content['sources'])
                if 'caveats' in content:
                    caveats.extend(content['caveats'])
                if 'citations' in content:
                    for cit in content['citations']:
                        if isinstance(cit, SourceCitation):
                            all_citations.append(cit)
                        elif isinstance(cit, dict):
                            all_citations.append(SourceCitation.from_dict(cit))
            elif isinstance(content, str):
                answer_parts.append(content)
            vote_result_check = voting_results.get(contrib.persona_id)
            if vote_result_check is not None and vote_result_check.consensus_score < self.CONSENSUS_THRESHOLD:
                dissenting_views.append(f'{persona_name}: {contrib.reasoning}')
        if answer_parts:
            answer = '\n\n'.join(answer_parts)
        elif scored_contributions:
            _, best_contrib = scored_contributions[0]
            answer = best_contrib.reasoning
        else:
            answer = 'Unable to formulate an answer with the available information.'
        if scored_contributions:
            total_weight = sum((score for score, _ in scored_contributions))
            if total_weight > 0:
                weighted_confidence = sum((score * contrib.confidence for score, contrib in scored_contributions)) / total_weight
            else:
                weighted_confidence = 0.5
        else:
            weighted_confidence = 0.3
        key_points = list(dict.fromkeys(key_points))[:10]
        sources = list(dict.fromkeys(sources))
        caveats = list(dict.fromkeys(caveats))
        unique_citations = self._aggregate_citations(all_citations)
        return PanelResponse.from_citations(question_id=context.question_id, answer=answer, confidence=weighted_confidence, citations=unique_citations, key_points=key_points, sources=sources, caveats=caveats, dissenting_views=dissenting_views, contributions_summary=contributions_summary)

    def _aggregate_citations(self, citations: list[SourceCitation]) -> list[SourceCitation]:
        unique: dict[tuple[str, str], SourceCitation] = {}
        for citation in citations:
            key = (citation.type, citation.reference)
            if key not in unique or citation.relevance > unique[key].relevance:
                unique[key] = citation
        sorted_citations = sorted(unique.values(), key=lambda c: c.relevance, reverse=True)
        return sorted_citations[:10]