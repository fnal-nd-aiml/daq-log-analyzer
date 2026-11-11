"""
File: llm.py
Purpose: Recorded LLM requests, responses, exchanges and statistics.
Category: Utility
Author: artdaq team
Depends: None
Exports: LlmTraceabilityMixin
Complexity: Low | Lines: 75
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from ..artifacts import Artifact
from ._state import StoreState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class LlmTraceabilityMixin(StoreState):

    async def get_llm_requests(self, binder_id: str, persona: str | None=None, phase: int | None=None, prompt_key: str | None=None, limit: int=100) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='llm_request', phase=phase, limit=limit)
        result = []
        for artifact in artifacts:
            if persona is not None and hasattr(artifact, 'persona'):
                if artifact.persona != persona:
                    continue
            if prompt_key is not None and hasattr(artifact, 'prompt_key'):
                if artifact.prompt_key != prompt_key:
                    continue
            result.append(artifact)
        return result

    async def get_llm_responses(self, binder_id: str, request_id: str | None=None, phase: int | None=None, parse_success: bool | None=None, limit: int=100) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='llm_response', phase=phase, limit=limit)
        result = []
        for artifact in artifacts:
            if request_id is not None and hasattr(artifact, 'request_id'):
                if artifact.request_id != request_id:
                    continue
            if parse_success is not None and hasattr(artifact, 'parse_success'):
                if artifact.parse_success != parse_success:
                    continue
            result.append(artifact)
        return result

    async def get_llm_exchanges(self, binder_id: str, phase: int | None=None) -> list[tuple[Artifact, Artifact | None]]:
        requests = await self.get_llm_requests(binder_id, phase=phase, limit=500)
        responses = await self.get_llm_responses(binder_id, phase=phase, limit=500)
        response_map: dict[str, Artifact] = {}
        for resp in responses:
            if hasattr(resp, 'request_id') and resp.request_id:
                response_map[resp.request_id] = resp
        exchanges: list[tuple[Artifact, Artifact | None]] = []
        for req in requests:
            matched_resp: Artifact | None = response_map.get(req.id)
            exchanges.append((req, matched_resp))
        return exchanges

    async def get_llm_statistics(self, binder_id: str) -> dict[str, Any]:
        requests = await self.get_llm_requests(binder_id, limit=1000)
        responses = await self.get_llm_responses(binder_id, limit=1000)
        by_persona: dict[str, int] = {}
        by_phase: dict[int, int] = {}
        total_tokens = 0
        total_latency = 0.0
        parse_successes = 0
        parse_failures = 0
        for req in requests:
            if hasattr(req, 'persona'):
                by_persona[req.persona] = by_persona.get(req.persona, 0) + 1
            if req.phase is not None:
                by_phase[req.phase] = by_phase.get(req.phase, 0) + 1
        for resp in responses:
            if hasattr(resp, 'tokens_used') and resp.tokens_used:
                total_tokens += resp.tokens_used
            if hasattr(resp, 'latency_ms') and resp.latency_ms:
                total_latency += resp.latency_ms
            if hasattr(resp, 'parse_success'):
                if resp.parse_success:
                    parse_successes += 1
                else:
                    parse_failures += 1
        return {'total_requests': len(requests), 'total_responses': len(responses), 'total_tokens_used': total_tokens, 'total_latency_ms': total_latency, 'average_latency_ms': total_latency / len(responses) if responses else 0, 'by_persona': by_persona, 'by_phase': {str(k): v for k, v in sorted(by_phase.items())}, 'parse_successes': parse_successes, 'parse_failures': parse_failures}