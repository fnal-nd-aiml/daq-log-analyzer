"""
File: registry.py
Purpose: Executor-id -> persona class registry.
Category: Utility
Author: artdaq team
Depends: None
Exports: executor_id_for_phase, get_persona_class, known_executor_ids
Complexity: Medium | Lines: 30
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from .personas import PERSONAS
if TYPE_CHECKING:
    from .base import BasePersona

def _persona_classes() -> dict[str, tuple[int, type['BasePersona']]]:
    from .archivist import ArchivistPersona
    from .chronicler import ChroniclerPersona
    from .detective import DetectivePersona
    from .judge import JudgePersona
    from .learner import LearnerPersona
    from .logician import LogicianPersona
    from .skeptic import SkepticPersona
    from .synthesizer import SynthesizerPersona
    from .theorist import TheoristPersona
    by_phase: dict[int, type[BasePersona]] = {-1: ChroniclerPersona, 0: ArchivistPersona, 1: TheoristPersona, 2: DetectivePersona, 3: LogicianPersona, 4: SkepticPersona, 5: JudgePersona, 6: SynthesizerPersona, 7: LearnerPersona}
    return {executor_id_for_phase(phase): (phase, cls) for phase, cls in by_phase.items()}

def executor_id_for_phase(phase: int) -> str:
    return PERSONAS[phase].name.lower().replace("'", '').replace(' ', '_')

def get_persona_class(executor_id: str) -> tuple[int, type['BasePersona']]:
    classes = _persona_classes()
    if executor_id not in classes:
        raise KeyError(f"Unknown pipeline executor '{executor_id}'. Known executors: {', '.join(sorted(classes))}")
    return classes[executor_id]

def known_executor_ids() -> set[str]:
    return set(_persona_classes())