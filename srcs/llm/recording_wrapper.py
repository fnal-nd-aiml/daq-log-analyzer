"""
File: recording_wrapper.py
Purpose: Recording wrapper for LLM providers.
Category: Utility
Author: artdaq team
Depends: workbinder, pydantic
Exports: RecordingLLMProvider, T
Complexity: Medium | Lines: 174
"""

from __future__ import annotations
import time
from typing import TYPE_CHECKING, TypeVar
from pydantic import BaseModel
from .errors import StructuredOutputError
from .provider import LLMProvider, ModelTier

if TYPE_CHECKING:
    from srcs.workbinder import WorkBinder
T = TypeVar("T", bound=BaseModel)


class RecordingLLMProvider(LLMProvider):

    def __init__(self, provider: LLMProvider, binder: "WorkBinder | None" = None):
        super().__init__(provider.config)
        self._provider = provider
        self._binder: "WorkBinder | None" = binder
        self._current_phase = 0
        self._current_persona = "system"
        self._prompt_key = "unknown"

    def set_binder(self, binder: "WorkBinder") -> None:
        self._binder = binder

    @property
    def has_binder(self) -> bool:
        return self._binder is not None

    def set_phase(self, phase: int) -> None:
        self._current_phase = phase

    def set_persona(self, persona: str) -> None:
        self._current_persona = persona

    def set_prompt_key(self, prompt_key: str) -> None:
        self._prompt_key = prompt_key

    def set_context(self, phase: int, persona: str, prompt_key: str) -> None:
        self._current_phase = phase
        self._current_persona = persona
        self._prompt_key = prompt_key

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_tier: ModelTier = ModelTier.DEFAULT,
    ) -> str:
        if self._binder is None:
            return await self._provider.generate(prompt, system_prompt, temperature, max_tokens, model_tier)
        request_id = self._binder.record_llm_request(
            persona=self._current_persona,
            prompt_key=self._prompt_key,
            system_prompt=system_prompt or "",
            user_prompt=prompt,
            model=self._provider.config.get_model(),
            temperature=temperature or self._provider.config.temperature,
            max_tokens=max_tokens or self._provider.config.max_tokens,
            phase=self._current_phase,
        )
        start_time = time.perf_counter()
        try:
            response = await self._provider.generate(prompt, system_prompt, temperature, max_tokens, model_tier)
            latency_ms = (time.perf_counter() - start_time) * 1000
            parse_success = True
            parse_errors: list[str] = []
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._binder.record_llm_response(
                request_id=request_id,
                raw_response=str(e),
                parsed_content=None,
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=False,
                parse_errors=[str(e)],
                phase=self._current_phase,
            )
            raise
        self._binder.record_llm_response(
            request_id=request_id,
            raw_response=response,
            parsed_content=None,
            tokens_used=self._estimate_tokens(response),
            latency_ms=latency_ms,
            parse_success=parse_success,
            parse_errors=parse_errors,
            phase=self._current_phase,
        )
        return response

    async def generate_structured(
        self, prompt: str, response_model: type[T], system_prompt: str | None = None, max_tokens: int | None = None
    ) -> T:
        if self._binder is None:
            return await self._provider.generate_structured(
                prompt, response_model, system_prompt, max_tokens=max_tokens
            )
        prompt_key = f"{self._prompt_key}:{response_model.__name__}"
        request_id = self._binder.record_llm_request(
            persona=self._current_persona,
            prompt_key=prompt_key,
            system_prompt=system_prompt or "",
            user_prompt=prompt,
            model=self._provider.config.get_model(),
            temperature=self._provider.config.temperature,
            max_tokens=self._provider.config.max_tokens,
            phase=self._current_phase,
        )
        start_time = time.perf_counter()
        try:
            result = await self._provider.generate_structured(
                prompt, response_model, system_prompt, max_tokens=max_tokens
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            parse_success = True
            parse_errors: list[str] = []
            try:
                parsed_content = result.model_dump(mode="json")
            except Exception:
                parsed_content = {"raw": str(result)}
            try:
                raw_response = result.model_dump_json(indent=2)
            except Exception:
                raw_response = str(result)
        except StructuredOutputError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._binder.record_llm_response(
                request_id=request_id,
                raw_response=e.raw_response,
                parsed_content=None,
                tokens_used=self._estimate_tokens(e.raw_response),
                latency_ms=latency_ms,
                parse_success=False,
                parse_errors=[str(e.args[0])],
                phase=self._current_phase,
            )
            raise
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._binder.record_llm_response(
                request_id=request_id,
                raw_response=str(e),
                parsed_content=None,
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=False,
                parse_errors=[str(e)],
                phase=self._current_phase,
            )
            raise
        self._binder.record_llm_response(
            request_id=request_id,
            raw_response=raw_response,
            parsed_content=parsed_content,
            tokens_used=self._estimate_tokens(raw_response),
            latency_ms=latency_ms,
            parse_success=parse_success,
            parse_errors=parse_errors,
            phase=self._current_phase,
        )
        return result

    async def embed(self, text: str) -> list[float]:
        return await self._provider.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._provider.embed_batch(texts)

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4
