"""Challenge parser for LLM response parsing.

Parses adversarial review responses and converts them to
domain models and WorkBinder artifacts.
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
    """Single challenge from LLM response.

    Note: The LLM returns 'type' for challenge type, which maps
    to 'challenge_type' in the domain model.

    Attributes:
        type: Type of challenge (logical_flaw, weak_evidence, etc.)
        content: Challenge content/description
        severity: Severity level (HIGH, MEDIUM, LOW)
    """

    type: str  # Maps to challenge_type in domain model
    content: str
    severity: str = "MEDIUM"


class ChallengeResponse(BaseModel):
    """LLM response for adversarial review.

    Contains a list of challenges to the investigation conclusions.
    """

    challenges: List[ChallengeItem]


class ChallengeParser(BaseParser[ChallengeResponse, Challenge, ChallengeArtifact]):
    """Parser for adversarial review LLM responses.

    Implements two-stage conversion with field mapping:
    - 'type' (LLM) -> 'challenge_type' (domain model)
    - 'missing' (type value) -> 'missing_evidence' (normalized)

    Example:
        >>> parser = ChallengeParser()
        >>> response = parser.parse_llm_response(raw_json)
        >>> for item in response.challenges:
        ...     challenge = parser.to_domain_model(item)
        ...     artifact = parser.to_artifact(
        ...         challenge, "Skeptic", 4, target_hypothesis_id="hyp-001"
        ...     )
    """

    def parse_llm_response(self, raw_json: str) -> ChallengeResponse:
        """Parse raw LLM response JSON into ChallengeResponse.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed ChallengeResponse

        Raises:
            ValueError: If JSON cannot be parsed
        """
        return parse_json_response(raw_json, ChallengeResponse)

    def to_domain_model(
        self,
        item: ChallengeItem,
        **context: object,
    ) -> Challenge:
        """Convert ChallengeItem to Challenge domain model.

        Handles field mapping from LLM response format:
        - 'type' -> 'challenge_type'
        - 'missing' type value -> 'missing_evidence' (normalized)

        Args:
            item: ChallengeItem from LLM response
            **context: Additional context (unused)

        Returns:
            Challenge domain model instance
        """
        # Normalize challenge type: 'missing' -> 'missing_evidence'
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
        """Convert Challenge to ChallengeArtifact.

        Args:
            domain_model: Challenge domain model
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            target_hypothesis_id: ID of hypothesis being challenged
            llm_request_id: Optional LLM request ID for traceability
            **kwargs: Additional artifact fields

        Returns:
            ChallengeArtifact instance
        """
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

    def parse_and_convert(
        self,
        raw_json: str,
    ) -> list[Challenge]:
        """Convenience method to parse and convert in one step.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            List of Challenge domain models
        """
        response = self.parse_llm_response(raw_json)
        return [self.to_domain_model(item) for item in response.challenges]
