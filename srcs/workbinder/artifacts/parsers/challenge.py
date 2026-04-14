"""
File: challenge.py
Purpose: Challenge parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: models, artifacts_types, pydantic
Exports: ChallengeItem, ChallengeResponse, ChallengeParser
Complexity: Medium | Lines: 62
"""

from __future__ import annotations
from typing import TYPE_CHECKING, List
from pydantic import BaseModel
from srcs.models import Challenge
from srcs.workbinder.artifacts_types import ChallengeArtifact
from .base import BaseParser
from .json_utils import parse_json_response

if TYPE_CHECKING:
    pass


class ChallengeItem(BaseModel):
    type: str
    content: str
    severity: str = "MEDIUM"


class ChallengeResponse(BaseModel):
    challenges: List[ChallengeItem]


class ChallengeParser(BaseParser[ChallengeResponse, Challenge, ChallengeArtifact]):

    def parse_llm_response(self, raw_json: str) -> ChallengeResponse:
        return parse_json_response(raw_json, ChallengeResponse)

    def to_domain_model(self, item: ChallengeItem, **context: object) -> Challenge:
        challenge_type = item.type
        if challenge_type == "missing":
            challenge_type = "missing_evidence"
        return Challenge(
            challenge_type=challenge_type,
            content=item.content,
            severity=item.severity,
            requires_response=item.severity == "HIGH",
        )

    def to_artifact(
        self,
        domain_model: Challenge,
        created_by: str,
        phase: int,
        target_hypothesis_id: str = "",
        llm_request_id: str | None = None,
        **kwargs: object,
    ) -> ChallengeArtifact:
        return ChallengeArtifact(
            target_hypothesis_id=target_hypothesis_id,
            content=domain_model.content,
            severity=domain_model.severity,
            requires_response=domain_model.requires_response,
            resolved=domain_model.resolved,
            resolution=domain_model.resolution,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
        )

    def parse_and_convert(self, raw_json: str) -> list[Challenge]:
        response = self.parse_llm_response(raw_json)
        return [self.to_domain_model(item) for item in response.challenges]
