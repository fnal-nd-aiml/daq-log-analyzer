"""
File: __init__.py
Purpose: Persona module - investigation phase personas and prompt templates.
Category: Config
Author: artdaq team
Depends: prompts
Exports: get_system_prompt, get_user_prompt, get_persona_prompt
Complexity: Medium | Lines: 29
"""

from srcs.prompts import PromptLoader, PromptTemplate, SystemPromptType, UserPromptType
from srcs.prompts import get_system_prompt as _get_system_prompt
from srcs.prompts import get_user_prompt as _get_user_prompt
from .archivist import ArchivistPersona
from .base import BasePersona, Contribution, Critique, Discussion, InvestigationContext, Reflection, Resolution, Summary
from .capabilities import BUILTIN_CAPABILITIES, Capability, CapabilityRegistry, get_capability_registry, register_tools
from .chronicler import ChroniclerPersona
from .detective import DetectivePersona
from .judge import JudgePersona
from .learner import LearnerPersona
from .logician import LogicianPersona
from .orchestrator import PanelOrchestrator
from .personas import PERSONAS, PHASE_ARCHIVIST, PHASE_CHRONICLER, PHASE_DETECTIVE, PHASE_JUDGE, PHASE_LEARNER, PHASE_LOGICIAN, PHASE_NAMES, PHASE_SKEPTIC, PHASE_SYNTHESIZER, PHASE_THEORIST, Persona, get_all_llm_personas, get_persona, get_persona_by_name, get_phase_name, get_prompt_key, is_llm_phase
from .skeptic import SkepticPersona
from .synthesizer import SynthesizerPersona
from .theorist import TheoristPersona

def get_system_prompt(persona: str) -> str:
    return _get_system_prompt(SystemPromptType(persona))

def get_user_prompt(task: str) -> PromptTemplate:
    return _get_user_prompt(UserPromptType(task))

def get_persona_prompt(phase: int) -> str | None:
    prompt_key = get_prompt_key(phase)
    if prompt_key is None:
        return None
    return get_system_prompt(prompt_key)
__all__ = ['PHASE_CHRONICLER', 'PHASE_ARCHIVIST', 'PHASE_THEORIST', 'PHASE_DETECTIVE', 'PHASE_LOGICIAN', 'PHASE_SKEPTIC', 'PHASE_JUDGE', 'PHASE_SYNTHESIZER', 'PHASE_LEARNER', 'Persona', 'PERSONAS', 'PHASE_NAMES', 'get_persona', 'get_phase_name', 'get_prompt_key', 'is_llm_phase', 'get_all_llm_personas', 'get_persona_by_name', 'PromptLoader', 'PromptTemplate', 'get_system_prompt', 'get_user_prompt', 'get_persona_prompt', 'Capability', 'CapabilityRegistry', 'BUILTIN_CAPABILITIES', 'get_capability_registry', 'register_tools', 'BasePersona', 'Contribution', 'InvestigationContext', 'Reflection', 'Critique', 'Discussion', 'Resolution', 'Summary', 'PanelOrchestrator', 'ChroniclerPersona', 'ArchivistPersona', 'TheoristPersona', 'DetectivePersona', 'LogicianPersona', 'SkepticPersona', 'JudgePersona', 'SynthesizerPersona', 'LearnerPersona']