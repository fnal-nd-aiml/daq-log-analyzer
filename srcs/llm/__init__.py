"""
File: __init__.py
Purpose: LLM module - re-export public interface.
Category: Config
Author: artdaq team
Depends: persona
Exports: None
Complexity: Medium | Lines: 85
"""

from srcs.persona import (
    PERSONAS,
    PHASE_ARCHIVIST,
    PHASE_DETECTIVE,
    PHASE_JUDGE,
    PHASE_LEARNER,
    PHASE_LOGICIAN,
    PHASE_NAMES,
    PHASE_SKEPTIC,
    PHASE_SYNTHESIZER,
    PHASE_THEORIST,
    Persona,
    get_all_llm_personas,
    get_persona,
    get_persona_by_name,
    get_phase_name,
    get_prompt_key,
    is_llm_phase,
)
from .anthropic import AnthropicProvider
from .errors import EmbeddingError, GenerationError, LLMError, ProviderError, StructuredOutputError
from .factory import create_llm_provider
from .ollama import OllamaProvider
from .openrouter import OpenRouterProvider
from .prompt_builder import PromptBuilder, PromptContext
from .provider import (
    AnthropicModels,
    AnthropicProviderConfig,
    EmbeddingConfig,
    LLMConfig,
    LLMProvider,
    ModelTier,
    OllamaProviderConfig,
    OpenRouterModels,
    OpenRouterProviderConfig,
    ProvidersConfig,
)
from .recording_wrapper import RecordingLLMProvider
from .token_utils import CHARS_PER_TOKEN, estimate_tokens, truncate_if_needed, truncate_middle_if_needed

__all__ = [
    "LLMProvider",
    "LLMConfig",
    "create_llm_provider",
    "OllamaProvider",
    "AnthropicProvider",
    "OpenRouterProvider",
    "RecordingLLMProvider",
    "ModelTier",
    "AnthropicModels",
    "AnthropicProviderConfig",
    "OpenRouterModels",
    "OpenRouterProviderConfig",
    "OllamaProviderConfig",
    "EmbeddingConfig",
    "ProvidersConfig",
    "LLMError",
    "ProviderError",
    "GenerationError",
    "EmbeddingError",
    "StructuredOutputError",
    "Persona",
    "PERSONAS",
    "PHASE_NAMES",
    "PHASE_ARCHIVIST",
    "PHASE_THEORIST",
    "PHASE_DETECTIVE",
    "PHASE_LOGICIAN",
    "PHASE_SKEPTIC",
    "PHASE_JUDGE",
    "PHASE_SYNTHESIZER",
    "PHASE_LEARNER",
    "get_persona",
    "get_phase_name",
    "get_prompt_key",
    "is_llm_phase",
    "get_all_llm_personas",
    "get_persona_by_name",
    "PromptBuilder",
    "PromptContext",
    "CHARS_PER_TOKEN",
    "estimate_tokens",
    "truncate_if_needed",
    "truncate_middle_if_needed",
]
