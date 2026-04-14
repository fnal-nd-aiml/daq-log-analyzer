"""
File: base.py
Purpose: Base persona class and supporting models for collaborative investig...
Category: Utility
Author: artdaq team
Depends: coordinator, extraction, knowledge, llm, investigation, ...
Exports: Contribution, InvestigationContext, Reflection, Critique, Discussion, ...
Complexity: High | Lines: 307
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar
from pydantic import BaseModel

if TYPE_CHECKING:
    from srcs.agent.coordinator import InvestigationConfig
    from srcs.extraction import CodeIndex, SourceLocator
    from srcs.knowledge import KnowledgeBase
    from srcs.llm import LLMProvider
    from srcs.models.investigation import Evidence, Hypothesis
    from srcs.models.knowledge import PriorKnowledge
    from srcs.models.logs import Log
    from srcs.models.question import QuestionContext
    from srcs.workbinder import WorkBinder
    from .personas import Persona
T = TypeVar("T", bound=BaseModel)


@dataclass
class Contribution:
    persona_id: str
    phase: int
    content: Any
    confidence: float
    reasoning: str


@dataclass
class InvestigationContext:
    error: "Log"
    context_logs: list["Log"] = field(default_factory=list)
    binder: "WorkBinder" = field(default=None)
    prior_knowledge: "PriorKnowledge | None" = None
    hypotheses: list["Hypothesis"] = field(default_factory=list)
    evidence: "Evidence | None" = None
    contributions: list[Contribution] = field(default_factory=list)
    source_files: list[Any] | None = None
    llm: "LLMProvider | None" = None
    kb: "KnowledgeBase | None" = None
    code_index: "CodeIndex | None" = None
    source_locator: "SourceLocator | None" = None
    config: "InvestigationConfig | None" = None

    def get_contributions_by_persona(self, persona_id: str) -> list[Contribution]:
        return [c for c in self.contributions if c.persona_id == persona_id]

    def get_contributions_by_phase(self, phase: int) -> list[Contribution]:
        return [c for c in self.contributions if c.phase == phase]

    def add_contribution(self, contribution: Contribution) -> None:
        self.contributions.append(contribution)

    def get_hypotheses_from_binder(self) -> list[Any]:
        if self.binder is None:
            return []
        return self.binder.get_hypotheses()

    def get_evidence_from_binder(self) -> list[Any]:
        if self.binder is None:
            return []
        return self.binder.get_evidence_items()

    def get_contributions_from_binder(self, persona_id: str | None = None, phase: int | None = None) -> list[Any]:
        if self.binder is None:
            return []
        return self.binder.get_persona_contributions(persona_id, phase)

    def get_findings_from_binder(self, persona_id: str | None = None) -> list[Any]:
        if self.binder is None:
            return []
        from srcs.workbinder.artifacts import ArtifactType, Finding

        findings = self.binder.get_by_type(ArtifactType.FINDING)
        if persona_id is not None:
            findings = [f for f in findings if isinstance(f, Finding) and f.persona == persona_id]
        return findings

    def get_causal_chains_from_binder(self) -> list[Any]:
        if self.binder is None:
            return []
        return self.binder.get_causal_chains()

    def get_challenges_from_binder(self) -> list[Any]:
        if self.binder is None:
            return []
        return self.binder.get_challenges()

    def get_llm_exchanges_from_binder(self, phase: int | None = None) -> list[tuple[Any, Any | None]]:
        if self.binder is None:
            return []
        return self.binder.get_llm_exchanges(phase)

    def has_binder(self) -> bool:
        return self.binder is not None

    def require_llm(self) -> "LLMProvider":
        if self.llm is None:
            raise RuntimeError("LLM provider required but not available in context")
        return self.llm

    def require_kb(self) -> "KnowledgeBase":
        if self.kb is None:
            raise RuntimeError("KnowledgeBase required but not available in context")
        return self.kb

    def require_code_index(self) -> "CodeIndex":
        if self.code_index is None:
            raise RuntimeError("CodeIndex required but not available in context")
        return self.code_index

    def require_source_locator(self) -> "SourceLocator":
        if self.source_locator is None:
            raise RuntimeError("SourceLocator required but not available in context")
        return self.source_locator

    def require_binder(self) -> "WorkBinder":
        if self.binder is None:
            raise RuntimeError("WorkBinder required but not available in context")
        return self.binder


@dataclass
class Reflection:
    insights: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class Critique:
    target_contribution: Contribution
    issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    severity: str = "MEDIUM"
    recommendations: list[str] = field(default_factory=list)


@dataclass
class Discussion:
    topic: str
    participants: list[str] = field(default_factory=list)
    exchanges: list[tuple[str, str]] = field(default_factory=list)
    conclusion: str | None = None
    consensus_reached: bool = False

    def add_exchange(self, persona_id: str, message: str) -> None:
        self.exchanges.append((persona_id, message))


@dataclass
class Resolution:
    disagreement_summary: str
    resolution_type: str
    resolution: str
    dissenting_views: list[str] = field(default_factory=list)


@dataclass
class Summary:
    key_points: list[str] = field(default_factory=list)
    areas_of_agreement: list[str] = field(default_factory=list)
    areas_of_disagreement: list[str] = field(default_factory=list)
    overall_assessment: str = ""


class BasePersona(ABC):

    @property
    @abstractmethod
    def metadata(self) -> "Persona": ...

    @property
    @abstractmethod
    def traits(self) -> list[str]: ...

    @property
    @abstractmethod
    def thinking_style(self) -> str: ...

    @abstractmethod
    async def prepare(self, context: InvestigationContext) -> None: ...

    @abstractmethod
    async def contribute(self, context: InvestigationContext) -> Contribution: ...

    @abstractmethod
    async def reflect(self, context: InvestigationContext) -> Reflection: ...

    @abstractmethod
    async def respond_to(self, other: "BasePersona", message: str) -> str: ...

    @abstractmethod
    async def critique(self, contribution: Contribution) -> Critique: ...

    @abstractmethod
    async def endorse(self, contribution: Contribution) -> bool: ...

    @abstractmethod
    async def answer_question(self, context: "QuestionContext") -> Contribution: ...

    def exhibit_trait(self, trait: str, context: Any) -> str:
        if trait not in self.traits:
            return ""
        trait_exhibitions = {
            "methodical": "Let me proceed step by step...",
            "thorough": "I should examine this from all angles...",
            "creative": "What if we consider an unexpected possibility...",
            "skeptical": "I'm not convinced. Let me challenge this...",
            "analytical": "Looking at the data patterns...",
            "integrative": "Bringing together the various threads...",
            "observant": "I notice something interesting here...",
        }
        return trait_exhibitions.get(trait, "")

    async def _call_llm(self, context: InvestigationContext, prompt: str, system_prompt: str, prompt_key: str) -> str:
        llm = context.require_llm()
        binder = context.require_binder()
        phase = self.metadata.phase
        persona = self.metadata.name
        request_id = binder.record_llm_request(
            persona=persona,
            prompt_key=prompt_key,
            system_prompt=system_prompt,
            user_prompt=prompt,
            model=llm.config.model or "unknown",
            temperature=llm.config.temperature,
            phase=phase,
        )
        start_time = time.time()
        try:
            response = await llm.generate(prompt, system_prompt)
            latency_ms = (time.time() - start_time) * 1000
            binder.record_llm_response(
                request_id=request_id,
                raw_response=response,
                parsed_content=None,
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=True,
                phase=phase,
            )
            return response
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            binder.record_llm_response(
                request_id=request_id,
                raw_response=str(e),
                parsed_content=None,
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=False,
                parse_errors=[str(e)],
                phase=phase,
            )
            raise

    async def _call_llm_structured(
        self,
        context: InvestigationContext,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        prompt_key: str,
        max_tokens: int | None = None,
    ) -> T:
        llm = context.require_llm()
        binder = context.require_binder()
        phase = self.metadata.phase
        persona = self.metadata.name
        request_id = binder.record_llm_request(
            persona=persona,
            prompt_key=prompt_key,
            system_prompt=system_prompt,
            user_prompt=prompt,
            model=llm.config.model or "unknown",
            temperature=llm.config.temperature,
            phase=phase,
        )
        start_time = time.time()
        try:
            result = await llm.generate_structured(prompt, response_model, system_prompt, max_tokens=max_tokens)
            latency_ms = (time.time() - start_time) * 1000
            binder.record_llm_response(
                request_id=request_id,
                raw_response="",
                parsed_content=result.model_dump() if hasattr(result, "model_dump") else None,
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=True,
                phase=phase,
            )
            return result
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            binder.record_llm_response(
                request_id=request_id,
                raw_response=str(e),
                parsed_content=None,
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=False,
                parse_errors=[str(e)],
                phase=phase,
            )
            raise
