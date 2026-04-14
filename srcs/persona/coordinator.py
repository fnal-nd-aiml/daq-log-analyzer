"""
File: coordinator.py
Purpose: Coordinator persona for orchestrating the collaborative investigati...
Category: Utility
Author: artdaq team
Depends: None
Exports: CoordinatorPersona
Complexity: Medium | Lines: 172
"""

from .base import BasePersona, Contribution, Critique, Discussion, InvestigationContext, Reflection, Resolution, Summary
from .personas import PERSONAS, Persona


class CoordinatorPersona(BasePersona):

    def __init__(self) -> None:
        self._panel: list[BasePersona] = []

    @property
    def metadata(self) -> Persona:
        return Persona(
            phase=-1,
            name="Coordinator",
            role="Panel Orchestration",
            color="bold white",
            thinking_phrase="Orchestrating the panel...",
            prompt_key="coordinator",
            uses_llm=False,
            description="Orchestrates the collaborative investigation panel",
        )

    @property
    def traits(self) -> list[str]:
        return ["diplomatic", "organized", "decisive", "impartial", "synthesizing"]

    @property
    def thinking_style(self) -> str:
        return "Systematic orchestration - manages flow, facilitates collaboration, synthesizes diverse perspectives, and ensures thorough investigation"

    async def prepare(self, context: InvestigationContext) -> None:
        pass

    async def contribute(self, context: InvestigationContext) -> Contribution:
        summary = await self.synthesize_contributions([c for c in context.contributions])
        return Contribution(
            persona_id="coordinator",
            phase=-1,
            content=summary,
            confidence=0.8,
            reasoning="Synthesized contributions from the investigation panel",
        )

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights: list[str] = []
        uncertainties: list[str] = []
        suggestions: list[str] = []
        phases_with_contributions = {c.phase for c in context.contributions}
        expected_phases = {0, 1, 2, 3, 4, 5, 6}
        missing_phases = expected_phases - phases_with_contributions
        if missing_phases:
            suggestions.append(f"Missing contributions from phases: {missing_phases}")
        if len(context.contributions) > 1:
            insights.append(f"Coordinated {len(context.contributions)} contributions")
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f"Thank you, {other.metadata.name}. I've noted your input and will incorporate it into the investigation flow."

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        if contribution.confidence < 0.3:
            issues.append("Low confidence may indicate insufficient analysis")
            recommendations.append("Consider gathering more evidence")
        if contribution.reasoning:
            strengths.append("Well-reasoned contribution")
        return Critique(
            target_contribution=contribution,
            issues=issues,
            strengths=strengths,
            severity="LOW" if not issues else "MEDIUM",
            recommendations=recommendations,
        )

    async def endorse(self, contribution: Contribution) -> bool:
        return bool(contribution.reasoning) and contribution.confidence > 0.3

    async def assemble_panel(self, phases: list[int]) -> list[BasePersona]:
        from .archivist import ArchivistPersona
        from .detective import DetectivePersona
        from .skeptic import SkepticPersona
        from .judge import JudgePersona
        from .learner import LearnerPersona
        from .logician import LogicianPersona
        from .synthesizer import SynthesizerPersona
        from .theorist import TheoristPersona

        persona_classes: dict[int, type[BasePersona]] = {
            0: ArchivistPersona,
            1: TheoristPersona,
            2: DetectivePersona,
            3: LogicianPersona,
            4: SkepticPersona,
            5: JudgePersona,
            6: SynthesizerPersona,
            7: LearnerPersona,
        }
        self._panel = []
        for phase in phases:
            if phase in persona_classes:
                self._panel.append(persona_classes[phase]())
        return self._panel

    async def facilitate_discussion(self, topic: str, participants: list[BasePersona] | None = None) -> Discussion:
        panel = participants or self._panel
        participant_ids = [p.metadata.name.lower() for p in panel]
        discussion = Discussion(topic=topic, participants=participant_ids)
        discussion.add_exchange("coordinator", f"Let's discuss: {topic}. I'd like to hear from each of you.")
        for persona in panel:
            discussion.add_exchange(
                persona.metadata.name.lower(), f"From my perspective as the {persona.metadata.name}..."
            )
        return discussion

    async def request_contribution(self, persona: BasePersona, context: InvestigationContext) -> Contribution:
        await persona.prepare(context)
        return await persona.contribute(context)

    async def synthesize_contributions(self, contributions: list[Contribution]) -> Summary:
        key_points = []
        areas_of_agreement = []
        areas_of_disagreement = []
        for contribution in contributions:
            if contribution.persona_id != "coordinator":
                persona_name = PERSONAS.get(contribution.phase)
                name = persona_name.name if persona_name else contribution.persona_id
                key_points.append(f"{name}: {contribution.reasoning}")
        high_confidence = [c for c in contributions if c.confidence > 0.7]
        if len(high_confidence) > 1:
            areas_of_agreement.append("Multiple personas have high confidence in their contributions")
        low_confidence = [c for c in contributions if c.confidence < 0.4]
        if low_confidence:
            areas_of_disagreement.append("Some personas have low confidence, indicating uncertainty")
        return Summary(
            key_points=key_points,
            areas_of_agreement=areas_of_agreement,
            areas_of_disagreement=areas_of_disagreement,
            overall_assessment=f"Synthesized {len(contributions)} contributions from the panel",
        )

    async def determine_next_phase(self, context: InvestigationContext) -> int:
        completed_phases = {c.phase for c in context.contributions}
        phase_order = [0, 1, 2, 3, 4, 5, 6, 7]
        for phase in phase_order:
            if phase not in completed_phases:
                return phase
        return -1

    async def should_reconvene(self, context: InvestigationContext) -> bool:
        critical_phases = {1, 2, 3}
        critical_contributions = [c for c in context.contributions if c.phase in critical_phases]
        if any((c.confidence < 0.4 for c in critical_contributions)):
            return True
        return False

    async def escalate_disagreement(self, personas: list[BasePersona], topic: str) -> Resolution:
        discussion = await self.facilitate_discussion(topic, personas)
        if not discussion.consensus_reached:
            return Resolution(
                disagreement_summary=topic,
                resolution_type="coordinator_decision",
                resolution="Based on the evidence and arguments presented, I recommend proceeding with the approach that has stronger evidentiary support.",
                dissenting_views=[f"{p.metadata.name} expressed reservations" for p in personas],
            )
        return Resolution(
            disagreement_summary=topic,
            resolution_type="consensus",
            resolution=discussion.conclusion or "Consensus reached through discussion",
            dissenting_views=[],
        )
