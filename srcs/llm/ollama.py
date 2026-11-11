"""
File: ollama.py
Purpose: Ollama LLM provider implementation.
Category: Utility
Author: artdaq team
Depends: prompts, parsers, pydantic
Exports: OllamaProvider, T
Complexity: Medium | Lines: 64
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

class OllamaProvider(LLMProvider):
    provider_name = 'ollama'

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: Any = None
        self._ollama_config = config.providers.ollama

    @property
    def client(self) -> Any:
        if self._client is None:
            import ollama
            self._client = ollama.AsyncClient(host=self._ollama_config.host, timeout=self.config.timeout_seconds or None)
        return self._client

    async def generate(self, prompt: str, system_prompt: str | None=None, temperature: float | None=None, max_tokens: int | None=None, model_tier: ModelTier=ModelTier.DEFAULT) -> str:

        async def call() -> Any:
            return await self.client.chat(model=self._ollama_config.model, messages=[{'role': 'system', 'content': system_prompt or get_default_system_prompt()}, {'role': 'user', 'content': prompt}], options={'temperature': temperature if temperature is not None else self.config.temperature, 'num_predict': max_tokens if max_tokens is not None else self.config.max_tokens})
        response = await self._resilient(call, 'generate')
        return str(response['message']['content'])

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

        async def call() -> Any:
            return await self.client.embeddings(model=self.config.get_embedding_model(), prompt=text)
        response = await self._resilient(call, 'embed', timeout=self.config.embedding_timeout_seconds)
        return list(response['embedding'])

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embed_batch_bounded(texts)