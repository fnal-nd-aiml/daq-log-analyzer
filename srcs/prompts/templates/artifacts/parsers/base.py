"""Base parser abstract class for LLM response parsing.

Defines the two-stage conversion pattern used by all parsers:
1. LLM Response -> Domain Model (for investigation pipeline)
2. Domain Model -> WorkBinder Artifact (for persistence)
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from srcs.workbinder.artifacts_types import Artifact

# Type variables for generic parser
LLMResponseT = TypeVar("LLMResponseT", bound=BaseModel)  # Raw LLM response model
DomainModelT = TypeVar("DomainModelT")  # Domain model (can be dict or BaseModel)
ArtifactT = TypeVar("ArtifactT", bound=Artifact)  # WorkBinder artifact


class BaseParser(ABC, Generic[LLMResponseT, DomainModelT, ArtifactT]):
    """Abstract base class for LLM response parsers.

    Parsers implement a two-stage conversion pattern:

    1. parse_llm_response: Raw JSON -> LLM Response Model
       Extracts and validates the raw LLM output.

    2. to_domain_model: LLM Response Item -> Domain Model
       Converts individual items to domain models used throughout
       the investigation pipeline.

    3. to_artifact: Domain Model -> WorkBinder Artifact
       Converts domain models to artifacts for persistence.

    This separation maintains backward compatibility with existing
    agent code while enabling artifact storage.

    Example:
        >>> parser = HypothesisParser()
        >>> # Stage 1: Parse LLM response
        >>> response = parser.parse_llm_response(raw_json)
        >>> # Stage 2: Convert to domain models
        >>> hypotheses = [parser.to_domain_model(item) for item in response.hypotheses]
        >>> # Stage 3: Convert to artifacts for storage
        >>> artifacts = [parser.to_artifact(h, "Theorist", 1) for h in hypotheses]
    """

    @abstractmethod
    def parse_llm_response(self, raw_json: str) -> LLMResponseT:
        """Parse raw LLM response JSON into response model.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed LLM response model

        Raises:
            ValueError: If JSON cannot be parsed
        """
        ...

    @abstractmethod
    def to_domain_model(self, item: Any, **context: Any) -> DomainModelT:
        """Convert LLM response item to domain model.

        Args:
            item: Single item from LLM response
            **context: Additional context (e.g., investigation_id)

        Returns:
            Domain model instance
        """
        ...

    @abstractmethod
    def to_artifact(
        self,
        domain_model: Any,
        created_by: str,
        phase: int,
        **kwargs: Any,
    ) -> ArtifactT:
        """Convert domain model to WorkBinder artifact.

        Args:
            domain_model: Domain model instance
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            **kwargs: Additional artifact fields

        Returns:
            WorkBinder artifact instance
        """
        ...
