"""
File: factory.py
Purpose: Factory for creating LLM providers.
Category: Utility
Author: artdaq team
Depends: None
Exports: create_llm_provider
Complexity: Low | Lines: 21
"""

from .anthropic import AnthropicProvider
from .ollama import OllamaProvider
from .openrouter import OpenRouterProvider
from .provider import LLMConfig, LLMProvider


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    if config.provider == "ollama":
        return OllamaProvider(config)
    elif config.provider == "anthropic":
        anthro_cfg = config.providers.anthropic
        if not anthro_cfg.api_key and (not anthro_cfg.auth_token) and (not config.anthropic_api_key):
            raise ValueError("Anthropic provider requires either api_key or auth_token")
        return AnthropicProvider(config)
    elif config.provider == "openrouter":
        openrouter_cfg = config.providers.openrouter
        if not openrouter_cfg.api_key:
            raise ValueError("OpenRouter provider requires api_key")
        return OpenRouterProvider(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
