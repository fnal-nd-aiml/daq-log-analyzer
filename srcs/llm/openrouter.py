"""
File: openrouter.py
Purpose: OpenRouter LLM provider implementation.
Category: Utility
Author: artdaq team
Depends: prompts, parsers, pydantic
Exports: OpenRouterProvider, T
Complexity: Medium | Lines: 76
"""

import json
import logging
from typing import Any, TypeVar
from pydantic import BaseModel
from srcs.prompts import get_default_system_prompt
from srcs.workbinder.artifacts.parsers import extract_json, fix_json
from .provider import LLMConfig, LLMProvider, ModelTier
logger = logging.getLogger(__name__)
T = TypeVar('T', bound=BaseModel)

class OpenRouterProvider(LLMProvider):
    provider_name = 'openrouter'

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None
        self._ollama_client: Any = None
        self._embed_client: Any = None
        self._openrouter_config = config.providers.openrouter

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(base_url=self._openrouter_config.base_url, api_key=self._openrouter_config.api_key, timeout=self.config.timeout_seconds or None, max_retries=0)
        return self._client

    async def generate(self, prompt: str, system_prompt: str | None=None, temperature: float | None=None, max_tokens: int | None=None, model_tier: ModelTier=ModelTier.DEFAULT) -> str:
        model = self._openrouter_config.models.get_model(model_tier)
        extra: dict[str, Any] = {}
        if self._openrouter_config.reasoning_effort:
            extra['reasoning_effort'] = self._openrouter_config.reasoning_effort

        async def call() -> Any:
            return await self.client.chat.completions.create(**extra, model=model, max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens, messages=[{'role': 'system', 'content': system_prompt or get_default_system_prompt()}, {'role': 'user', 'content': prompt}], temperature=temperature if temperature is not None else self.config.temperature)
        response = await self._resilient(call, 'generate')
        return str(response.choices[0].message.content or '')

    async def generate_structured(self, prompt: str, response_model: type[T], system_prompt: str | None=None, max_tokens: int | None=None) -> T:
        schema = response_model.model_json_schema()
        json_prompt = f'{prompt}\n\nRespond with ONLY valid JSON matching this schema (no markdown, no explanation):\n{json.dumps(schema, indent=2)}'
        response = await self.generate(json_prompt, system_prompt, max_tokens=max_tokens)
        json_str = extract_json(response)
        try:
            return response_model.model_validate_json(json_str)
        except Exception as e:
            logger.warning(f'Failed to parse JSON response: {e}')
            logger.debug(f'Response was: {response}')
            fixed_json = fix_json(json_str)
            return response_model.model_validate_json(fixed_json)

    async def embed(self, text: str) -> list[float]:
        if self.config.embedding.provider == 'openai':
            return await self._embed_openai(text)
        if self._ollama_client is None:
            import ollama
            self._ollama_client = ollama.AsyncClient(host=self.config.get_ollama_host(), timeout=self.config.embedding_timeout_seconds or None)

        async def call() -> Any:
            return await self._ollama_client.embeddings(model=self.config.get_embedding_model(), prompt=text)
        response = await self._resilient(call, 'embed', timeout=self.config.embedding_timeout_seconds)
        return list(response['embedding'])

    async def _embed_openai(self, text: str) -> list[float]:
        if self._embed_client is None:
            import openai
            emb_cfg = self.config.embedding
            self._embed_client = openai.AsyncOpenAI(base_url=emb_cfg.host, api_key=emb_cfg.api_key or self._openrouter_config.api_key, timeout=self.config.embedding_timeout_seconds or None, max_retries=0)

        async def call() -> Any:
            return await self._embed_client.embeddings.create(model=self.config.get_embedding_model(), input=text)
        response = await self._resilient(call, 'embed', timeout=self.config.embedding_timeout_seconds)
        return list(response.data[0].embedding)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embed_batch_bounded(texts)