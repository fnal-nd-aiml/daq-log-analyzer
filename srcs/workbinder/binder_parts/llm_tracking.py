"""
File: llm_tracking.py
Purpose: Recording LLM requests, responses and exchanges.
Category: Utility
Author: artdaq team
Depends: None
Exports: LlmTrackingMixin
Complexity: Low | Lines: 41
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from ..artifacts import LLMRequestArtifact, LLMResponseArtifact
from ._state import BinderState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class LlmTrackingMixin(BinderState):

    def record_llm_request(self, persona: str, prompt_key: str, system_prompt: str, user_prompt: str, model: str, temperature: float=0.1, max_tokens: int=4096, phase: int | None=None) -> str:
        artifact = LLMRequestArtifact(persona=persona, prompt_key=prompt_key, system_prompt=system_prompt, user_prompt=user_prompt, model=model, temperature=temperature, max_tokens=max_tokens, request_timestamp=datetime.now(), created_by=persona, phase=phase)
        return self.add_artifact(artifact)

    def record_llm_response(self, request_id: str, raw_response: str, parsed_content: dict[str, Any] | None, tokens_used: int, latency_ms: float, parse_success: bool, parse_errors: list[str] | None=None, phase: int | None=None) -> str:
        request = self.get_artifact(request_id)
        persona = request.persona if isinstance(request, LLMRequestArtifact) else 'system'
        artifact = LLMResponseArtifact(linked_request_id=request_id, raw_response=raw_response, parsed_content=parsed_content, tokens_used=tokens_used, latency_ms=latency_ms, response_timestamp=datetime.now(), parse_success=parse_success, parse_errors=parse_errors or [], created_by=persona, phase=phase)
        response_id = self.add_artifact(artifact)
        if request:
            self.update_artifact(request_id, {'linked_response_id': response_id}, persona)
        return response_id

    def get_llm_exchanges(self, phase: int | None=None) -> list[tuple[LLMRequestArtifact, LLMResponseArtifact | None]]:
        exchanges: list[tuple[LLMRequestArtifact, LLMResponseArtifact | None]] = []
        requests: list[LLMRequestArtifact] = []
        for artifact in self._artifacts.values():
            if isinstance(artifact, LLMRequestArtifact) and (not artifact.is_deleted):
                if phase is None or artifact.phase == phase:
                    requests.append(artifact)
        requests.sort(key=lambda r: r.request_timestamp)
        for request in requests:
            response = None
            if request.linked_response_id:
                resp_artifact = self.get_artifact(request.linked_response_id)
                if isinstance(resp_artifact, LLMResponseArtifact):
                    response = resp_artifact
            exchanges.append((request, response))
        return exchanges