"""
File: logging_wrapper.py
Purpose: Logging wrapper for LLM providers.
Category: Utility
Author: artdaq team
Depends: callbacks, common, pydantic
Exports: LoggingLLMProvider, T
Complexity: Medium | Lines: 130
"""

from typing import TypeVar
from pydantic import BaseModel
from srcs.agent.callbacks import LLMCallback, LLMEvent
from srcs.common import LoggingWrapperBase
from .errors import StructuredOutputError
from .provider import LLMProvider, ModelTier

T = TypeVar("T", bound=BaseModel)


class LoggingLLMProvider(LLMProvider, LoggingWrapperBase):

    def __init__(self, provider: LLMProvider, callback: LLMCallback):
        LLMProvider.__init__(self, provider.config)
        LoggingWrapperBase.__init__(self, callback)
        self._provider = provider
        self._last_system_prompt: str | None = None

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> str:
        system_to_log = None
        if system_prompt != self._last_system_prompt:
            system_to_log = system_prompt
            self._last_system_prompt = system_prompt
        self._callback(
            LLMEvent(
                phase=self._current_phase,
                event_type="request",
                system_prompt=system_to_log,
                user_prompt=prompt,
                response=None,
                response_model=None,
                model_name=self._provider.config.get_model(),
            )
        )
        response = await self._provider.generate(prompt, system_prompt, temperature, max_tokens, model_tier)
        self._callback(
            LLMEvent(
                phase=self._current_phase,
                event_type="response",
                system_prompt=None,
                user_prompt=None,
                response=response,
                response_model=None,
                model_name=self._provider.config.get_model(),
            )
        )
        return response

    async def generate_structured(
        self, prompt: str, response_model: type[T], system_prompt: str | None = None, max_tokens: int | None = None
    ) -> T:
        system_to_log = None
        if system_prompt != self._last_system_prompt:
            system_to_log = system_prompt
            self._last_system_prompt = system_prompt
        self._callback(
            LLMEvent(
                phase=self._current_phase,
                event_type="request",
                system_prompt=system_to_log,
                user_prompt=prompt,
                response=None,
                response_model=response_model.__name__,
                model_name=self._provider.config.get_model(),
            )
        )
        try:
            result = await self._provider.generate_structured(
                prompt, response_model, system_prompt, max_tokens=max_tokens
            )
        except StructuredOutputError as e:
            self._callback(
                LLMEvent(
                    phase=self._current_phase,
                    event_type="response",
                    system_prompt=None,
                    user_prompt=None,
                    response=e.raw_response,
                    response_model=response_model.__name__,
                    model_name=self._provider.config.get_model(),
                    parse_failed=True,
                    parse_error=str(e.args[0]),
                    expected_schema=e.expected_schema,
                )
            )
            raise
        except Exception as e:
            self._callback(
                LLMEvent(
                    phase=self._current_phase,
                    event_type="response",
                    system_prompt=None,
                    user_prompt=None,
                    response=f"Error: {type(e).__name__}: {e}",
                    response_model=response_model.__name__,
                    model_name=self._provider.config.get_model(),
                    parse_failed=True,
                    parse_error=str(e),
                )
            )
            raise
        try:
            response_json = result.model_dump_json(indent=2)
        except Exception:
            response_json = str(result)
        self._callback(
            LLMEvent(
                phase=self._current_phase,
                event_type="response",
                system_prompt=None,
                user_prompt=None,
                response=response_json,
                response_model=response_model.__name__,
                model_name=self._provider.config.get_model(),
            )
        )
        return result

    async def embed(self, text: str) -> list[float]:
        return await self._provider.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._provider.embed_batch(texts)
