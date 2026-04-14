"""
File: personas.py
Purpose: Centralized persona library for investigation phases.
Category: Utility
Author: artdaq team
Depends: None
Exports: Persona, get_persona, get_phase_name, get_prompt_key, is_llm_phase, ...
Complexity: Medium | Lines: 182
"""

from dataclasses import dataclass

PHASE_CHRONICLER = -1
PHASE_ARCHIVIST = 0
PHASE_THEORIST = 1
PHASE_DETECTIVE = 2
PHASE_LOGICIAN = 3
PHASE_SKEPTIC = 4
PHASE_JUDGE = 5
PHASE_SYNTHESIZER = 6
PHASE_LEARNER = 7
PHASE_REVIEWER = 8


@dataclass(frozen=True)
class Persona:
    phase: int
    name: str
    role: str
    color: str
    thinking_phrase: str
    prompt_key: str | None
    uses_llm: bool
    description: str


PERSONAS: dict[int, Persona] = {
    PHASE_CHRONICLER: Persona(
        phase=PHASE_CHRONICLER,
        name="Chronicler",
        role="Multi-File Log Triage",
        color="bright_blue",
        thinking_phrase="Reading the chronicles...",
        prompt_key="chronicler",
        uses_llm=True,
        description="Merges multi-file logs chronologically, identifies primary error and cascade",
    ),
    PHASE_ARCHIVIST: Persona(
        phase=PHASE_ARCHIVIST,
        name="Archivist",
        role="Prior Knowledge Retrieval",
        color="blue",
        thinking_phrase="Searching the archives...",
        prompt_key="archivist",
        uses_llm=True,
        description="Retrieves historical patterns, similar cases, source locations, and summarizes call graphs",
    ),
    PHASE_THEORIST: Persona(
        phase=PHASE_THEORIST,
        name="Theorist",
        role="Hypothesis Generation",
        color="magenta",
        thinking_phrase="What if...",
        prompt_key="theorist",
        uses_llm=True,
        description="Generates root cause hypotheses from multiple tiers",
    ),
    PHASE_DETECTIVE: Persona(
        phase=PHASE_DETECTIVE,
        name="Detective",
        role="Evidence Seeking",
        color="cyan",
        thinking_phrase="Let me check...",
        prompt_key="detective",
        uses_llm=True,
        description="Iteratively seeks discriminating evidence for hypotheses",
    ),
    PHASE_LOGICIAN: Persona(
        phase=PHASE_LOGICIAN,
        name="Logician",
        role="Causal Chain Construction",
        color="green",
        thinking_phrase="Following the chain of events...",
        prompt_key="logician",
        uses_llm=True,
        description="Builds explicit causal chains from evidence",
    ),
    PHASE_SKEPTIC: Persona(
        phase=PHASE_SKEPTIC,
        name="Skeptic",
        role="Adversarial Review",
        color="red",
        thinking_phrase="But wait...",
        prompt_key="skeptic",
        uses_llm=True,
        description="Challenges conclusions through critical analysis",
    ),
    PHASE_JUDGE: Persona(
        phase=PHASE_JUDGE,
        name="Judge",
        role="Insufficiency Check",
        color="yellow",
        thinking_phrase="Weighing the evidence...",
        prompt_key="judge",
        uses_llm=True,
        description="Assesses whether evidence is sufficient for conclusion",
    ),
    PHASE_SYNTHESIZER: Persona(
        phase=PHASE_SYNTHESIZER,
        name="Synthesizer",
        role="Final Synthesis",
        color="white",
        thinking_phrase="Bringing it all together...",
        prompt_key="synthesizer",
        uses_llm=True,
        description="Synthesizes final investigation result",
    ),
    PHASE_LEARNER: Persona(
        phase=PHASE_LEARNER,
        name="Learner",
        role="Pattern Learning",
        color="dim",
        thinking_phrase="Remembering for next time...",
        prompt_key="learner",
        uses_llm=True,
        description="Extracts and stores patterns for future investigations",
    ),
    PHASE_REVIEWER: Persona(
        phase=PHASE_REVIEWER,
        name="Reviewer",
        role="User Feedback",
        color="bright_green",
        thinking_phrase="Your feedback helps me learn...",
        prompt_key=None,
        uses_llm=False,
        description="Solicits user feedback on investigation results and incorporates corrections",
    ),
}
PHASE_NAMES: dict[int, str] = {p.phase: p.role for p in PERSONAS.values()}


def get_persona(phase: int) -> Persona:
    if phase not in PERSONAS:
        raise KeyError(f"Invalid phase number: {phase}. Valid phases are -1 to 8.")
    return PERSONAS[phase]


def get_phase_name(phase: int) -> str:
    return get_persona(phase).role


def get_prompt_key(phase: int) -> str | None:
    return get_persona(phase).prompt_key


def is_llm_phase(phase: int) -> bool:
    return get_persona(phase).uses_llm


def get_all_llm_personas() -> list[Persona]:
    return [p for p in PERSONAS.values() if p.uses_llm]


def get_persona_by_name(name: str) -> Persona | None:
    name_lower = name.lower()
    for persona in PERSONAS.values():
        if persona.name.lower() == name_lower:
            return persona
    return None


__all__ = [
    "PHASE_CHRONICLER",
    "PHASE_ARCHIVIST",
    "PHASE_THEORIST",
    "PHASE_DETECTIVE",
    "PHASE_LOGICIAN",
    "PHASE_SKEPTIC",
    "PHASE_JUDGE",
    "PHASE_SYNTHESIZER",
    "PHASE_LEARNER",
    "PHASE_REVIEWER",
    "Persona",
    "PERSONAS",
    "PHASE_NAMES",
    "get_persona",
    "get_phase_name",
    "get_prompt_key",
    "is_llm_phase",
    "get_all_llm_personas",
    "get_persona_by_name",
]
