"""
File: anthropic.py
Purpose: Anthropic Claude LLM provider implementation.
Category: Utility
Author: artdaq team
Depends: prompts, parsers, pydantic
Exports: AnthropicProvider, T
Complexity: Medium | Lines: 93
"""

import json
import logging
from typing import TypeVar
from pydantic import BaseModel
from srcs.prompts import get_default_system_prompt
from srcs.workbinder.artifacts.parsers import extract_json, fix_json
from .errors import StructuredOutputError
from .provider import LLMConfig, LLMProvider, ModelTier

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AnthropicProvider(LLMProvider):

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._ollama_client = None
        self._anthropic_config = config.providers.anthropic

    @property
    def client(self):
        if self._client is None:
            import anthropic

            cfg = self._anthropic_config
            client_kwargs = {}
            if cfg.base_url:
                client_kwargs["base_url"] = cfg.base_url
            if cfg.auth_token:
                client_kwargs["api_key"] = cfg.auth_token
            elif cfg.api_key:
                client_kwargs["api_key"] = cfg.api_key
            self._client = anthropic.AsyncAnthropic(**client_kwargs)
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> str:
        model = self._anthropic_config.models.get_model(model_tier)
        response = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens or self.config.max_tokens,
            system=system_prompt or get_default_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature or self.config.temperature,
        )
        return response.content[0].text

    async def generate_structured(
        self, prompt: str, response_model: type[T], system_prompt: str | None = None, max_tokens: int | None = None
    ) -> T:
        schema = response_model.model_json_schema()
        json_prompt = f"{prompt}\n\nRespond with ONLY valid JSON matching this schema (no markdown, no explanation):\n{json.dumps(schema, indent=2)}"
        response = await self.generate(json_prompt, system_prompt, max_tokens=max_tokens)
        json_str = extract_json(response)
        try:
            return response_model.model_validate_json(json_str)
        except Exception as e:
            logger.debug(f"Direct JSON parse failed: {e}")
        fixed_json = fix_json(json_str)
        try:
            return response_model.model_validate_json(fixed_json)
        except Exception as e:
            logger.debug(f"Fixed JSON parse failed: {e}")
        try:
            data = json.loads(fixed_json)
            return response_model.model_validate(data)
        except Exception as e:
            logger.warning(f"All JSON parse attempts failed: {e}")
            logger.warning(f"Response (first 500 chars): {response[:500]}")
            raise StructuredOutputError(
                message=f"Failed to parse JSON response after all attempts: {e}",
                raw_response=response,
                expected_schema=json.dumps(schema, indent=2),
            ) from e

    async def embed(self, text: str) -> list[float]:
        if self._ollama_client is None:
            import ollama

            self._ollama_client = ollama.AsyncClient(host=self.config.get_ollama_host())
        response = await self._ollama_client.embeddings(model=self.config.get_embedding_model(), prompt=text)
        return response["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]
