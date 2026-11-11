"""
File: anthropic.py
Purpose: Anthropic Claude LLM provider implementation.
Category: Utility
Author: artdaq team
Depends: prompts, parsers, pydantic
Exports: AnthropicProvider, T
Complexity: Medium | Lines: 85
"""

import json
import logging
from typing import Any, TypeVar
from pydantic import BaseModel
from srcs.prompts import get_default_system_prompt
from srcs.workbinder.artifacts.parsers import extract_json, fix_json
from .errors import StructuredOutputError
from .provider import LLMConfig, LLMProvider, ModelTier
logger = logging.getLogger(__name__)
T = TypeVar('T', bound=BaseModel)

class AnthropicProvider(LLMProvider):
    provider_name = 'anthropic'

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None
        self._ollama_client: Any = None
        self._anthropic_config = config.providers.anthropic

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic
            cfg = self._anthropic_config
            client_kwargs: dict[str, Any] = {}
            if cfg.base_url:
                client_kwargs['base_url'] = cfg.base_url
            if cfg.auth_token:
                client_kwargs['api_key'] = cfg.auth_token
            elif cfg.api_key:
                client_kwargs['api_key'] = cfg.api_key
            if self.config.timeout_seconds:
                client_kwargs['timeout'] = self.config.timeout_seconds
            client_kwargs['max_retries'] = 0
            self._client = anthropic.AsyncAnthropic(**client_kwargs)
        return self._client

    async def generate(self, prompt: str, system_prompt: str | None=None, temperature: float | None=None, max_tokens: int | None=None, model_tier: ModelTier=ModelTier.DEFAULT) -> str:
        model = self._anthropic_config.models.get_model(model_tier)
        system_text = system_prompt or get_default_system_prompt()

        async def call() -> Any:
            return await self.client.messages.create(model=model, max_tokens=max_tokens if max_tokens is not None else self.config.max_tokens, system=[{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}], messages=[{'role': 'user', 'content': prompt}], temperature=temperature if temperature is not None else self.config.temperature)
        response = await self._resilient(call, 'generate')
        for block in response.content:
            text = getattr(block, 'text', None)
            if text is not None:
                return str(text)
        return ''

    async def generate_structured(self, prompt: str, response_model: type[T], system_prompt: str | None=None, max_tokens: int | None=None) -> T:
        schema = response_model.model_json_schema()
        json_prompt = f'{prompt}\n\nRespond with ONLY valid JSON matching this schema (no markdown, no explanation):\n{json.dumps(schema, indent=2)}'
        response = await self.generate(json_prompt, system_prompt, max_tokens=max_tokens)
        json_str = extract_json(response)
        try:
            return response_model.model_validate_json(json_str)
        except Exception as e:
            logger.debug(f'Direct JSON parse failed: {e}')
        fixed_json = fix_json(json_str)
        try:
            return response_model.model_validate_json(fixed_json)
        except Exception as e:
            logger.debug(f'Fixed JSON parse failed: {e}')
        try:
            data = json.loads(fixed_json)
            return response_model.model_validate(data)
        except Exception as e:
            logger.warning(f'All JSON parse attempts failed: {e}')
            logger.warning(f'Response (first 500 chars): {response[:500]}')
            raise StructuredOutputError(message=f'Failed to parse JSON response after all attempts: {e}', raw_response=response, expected_schema=json.dumps(schema, indent=2)) from e

    async def embed(self, text: str) -> list[float]:
        if self._ollama_client is None:
            import ollama
            self._ollama_client = ollama.AsyncClient(host=self.config.get_ollama_host(), timeout=self.config.embedding_timeout_seconds or None)

        async def call() -> Any:
            return await self._ollama_client.embeddings(model=self.config.get_embedding_model(), prompt=text)
        response = await self._resilient(call, 'embed', timeout=self.config.embedding_timeout_seconds)
        return list(response['embedding'])

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embed_batch_bounded(texts)