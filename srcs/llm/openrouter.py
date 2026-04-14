"""
File: openrouter.py
Purpose: OpenRouter LLM provider implementation.
Category: Utility
Author: artdaq team
Depends: prompts, parsers, pydantic
Exports: OpenRouterProvider, T
Complexity: Medium | Lines: 73
"""

import json
import logging
from typing import TypeVar
from pydantic import BaseModel
from srcs.prompts import get_default_system_prompt
from srcs.workbinder.artifacts.parsers import extract_json, fix_json
from .provider import LLMConfig, LLMProvider, ModelTier

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenRouterProvider(LLMProvider):

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        self._ollama_client = None
        self._openrouter_config = config.providers.openrouter

    @property
    def client(self):
        if self._client is None:
            import openai

            self._client = openai.AsyncOpenAI(
                base_url=self._openrouter_config.base_url, api_key=self._openrouter_config.api_key
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> str:
        model = self._openrouter_config.models.get_model(model_tier)
        response = await self.client.chat.completions.create(
            model=model,
            max_tokens=max_tokens or self.config.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt or get_default_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature or self.config.temperature,
        )
        return response.choices[0].message.content or ""

    async def generate_structured(self, prompt: str, response_model: type[T], system_prompt: str | None = None) -> T:
        schema = response_model.model_json_schema()
        json_prompt = f"{prompt}\n\nRespond with ONLY valid JSON matching this schema (no markdown, no explanation):\n{json.dumps(schema, indent=2)}"
        response = await self.generate(json_prompt, system_prompt)
        json_str = extract_json(response)
        try:
            return response_model.model_validate_json(json_str)
        except Exception as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response was: {response}")
            fixed_json = fix_json(json_str)
            return response_model.model_validate_json(fixed_json)

    async def embed(self, text: str) -> list[float]:
        if self._ollama_client is None:
            import ollama

            self._ollama_client = ollama.AsyncClient(host=self.config.get_ollama_host())
        response = await self._ollama_client.embeddings(model=self.config.get_embedding_model(), prompt=text)
        return response["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]
