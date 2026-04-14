"""
File: provider.py
Purpose: Abstract LLM provider interface.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: ModelTier, AnthropicModels, AnthropicProviderConfig, OpenRouterModels, OpenRouterProviderConfig, ...
Complexity: Medium | Lines: 147
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TypeVar
from pydantic import BaseModel, model_validator


class ModelTier(str, Enum):
    DEFAULT = "default"
    SMALL_FAST = "small_fast"
    HAIKU = "haiku"
    OPUS = "opus"


class AnthropicModels(BaseModel):
    default: str = "claude-3-5-sonnet-20241022"
    small_fast: str | None = None
    haiku: str | None = None
    opus: str | None = None

    def get_model(self, tier: ModelTier = ModelTier.DEFAULT) -> str:
        model_map = {
            ModelTier.DEFAULT: self.default,
            ModelTier.SMALL_FAST: self.small_fast,
            ModelTier.HAIKU: self.haiku,
            ModelTier.OPUS: self.opus,
        }
        return model_map.get(tier) or self.default


class AnthropicProviderConfig(BaseModel):
    base_url: str | None = None
    auth_token: str | None = None
    api_key: str | None = None
    models: AnthropicModels = AnthropicModels()


class OpenRouterModels(BaseModel):
    default: str = "anthropic/claude-3.5-sonnet"
    small_fast: str | None = None
    haiku: str | None = None
    opus: str | None = None

    def get_model(self, tier: ModelTier = ModelTier.DEFAULT) -> str:
        model_map = {
            ModelTier.DEFAULT: self.default,
            ModelTier.SMALL_FAST: self.small_fast,
            ModelTier.HAIKU: self.haiku,
            ModelTier.OPUS: self.opus,
        }
        return model_map.get(tier) or self.default


class OpenRouterProviderConfig(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None
    models: OpenRouterModels = OpenRouterModels()


class OllamaProviderConfig(BaseModel):
    host: str = "http://localhost:11434"
    model: str = "gpt-oss:120b"


class EmbeddingConfig(BaseModel):
    provider: str = "ollama"
    model: str = "nomic-embed-text"
    host: str = "http://localhost:11434"


class ProvidersConfig(BaseModel):
    ollama: OllamaProviderConfig = OllamaProviderConfig()
    anthropic: AnthropicProviderConfig = AnthropicProviderConfig()
    openrouter: OpenRouterProviderConfig = OpenRouterProviderConfig()


class LLMConfig(BaseModel):
    provider: str = "ollama"
    temperature: float = 0.1
    max_tokens: int = 4096
    embedding: EmbeddingConfig = EmbeddingConfig()
    providers: ProvidersConfig = ProvidersConfig()
    model: str | None = None
    embedding_model: str | None = None
    ollama_host: str | None = None
    anthropic_api_key: str | None = None

    @model_validator(mode="after")
    def migrate_legacy_fields(self) -> "LLMConfig":
        if self.ollama_host:
            self.providers.ollama.host = self.ollama_host
            self.embedding.host = self.ollama_host
        if self.model:
            self.providers.ollama.model = self.model
        if self.embedding_model:
            self.embedding.model = self.embedding_model
        if self.anthropic_api_key:
            self.providers.anthropic.api_key = self.anthropic_api_key
        return self

    def get_model(self) -> str:
        if self.provider == "ollama":
            return self.providers.ollama.model
        elif self.provider == "anthropic":
            return self.providers.anthropic.models.default
        elif self.provider == "openrouter":
            return self.providers.openrouter.models.default
        return self.model or "gpt-oss:120b"

    def get_embedding_model(self) -> str:
        return self.embedding.model

    def get_ollama_host(self) -> str:
        return self.embedding.host


T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> str:
        pass

    @abstractmethod
    async def generate_structured(
        self, prompt: str, response_model: type[T], system_prompt: str | None = None, max_tokens: int | None = None
    ) -> T:
        pass

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass
