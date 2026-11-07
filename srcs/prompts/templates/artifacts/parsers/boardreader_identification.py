"""Boardreader identification parser for LLM response parsing.

Parses boardreader identification responses and converts them to
domain models and WorkBinder artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from pydantic import BaseModel, Field

from srcs.workbinder.artifacts_types import BoardReaderIdentificationArtifact

from .base import BaseParser
from .json_utils import parse_json_response

if TYPE_CHECKING:
    from srcs.persona.chronicler import BoardReaderIdentification


class BoardReaderIdentificationItem(BaseModel):
    """Single boardreader identification from LLM response.

    Attributes:
        boardreader_types: Boardreader/component types identified
        components: Additional component names found in logs
        error_messages: Key error messages to match against documentation
    """

    boardreader_types: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    error_messages: List[str] = Field(default_factory=list)


class BoardReaderIdentificationResponse(BaseModel):
    """LLM response for boardreader identification.

    Wraps the identification result.
    """

    boardreader_types: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    error_messages: List[str] = Field(default_factory=list)


class BoardReaderIdentificationParser(
    BaseParser[
        BoardReaderIdentificationResponse,
        Any,
        BoardReaderIdentificationArtifact,
    ]
):
    """Parser for boardreader identification LLM responses.

    Implements two-stage conversion:
    - LLM JSON -> BoardReaderIdentificationResponse
    - Response -> BoardReaderIdentification domain model
    - Domain model -> BoardReaderIdentificationArtifact

    Example:
        >>> parser = BoardReaderIdentificationParser()
        >>> response = parser.parse_llm_response(raw_json)
        >>> domain = parser.to_domain_model(response)
        >>> artifact = parser.to_artifact(domain, "Chronicler", -1)
    """

    def parse_llm_response(
        self, raw_json: str
    ) -> BoardReaderIdentificationResponse:
        """Parse raw LLM response JSON into BoardReaderIdentificationResponse.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed BoardReaderIdentificationResponse

        Raises:
            ValueError: If JSON cannot be parsed
        """
        return parse_json_response(raw_json, BoardReaderIdentificationResponse)

    def to_domain_model(
        self,
        item: BoardReaderIdentificationResponse,
        **context: object,
    ) -> BoardReaderIdentification:
        """Convert response to BoardReaderIdentification domain model.

        Args:
            item: BoardReaderIdentificationResponse from LLM
            **context: Additional context (unused)

        Returns:
            BoardReaderIdentification domain model instance
        """
        from srcs.persona.chronicler import (
            BoardReaderIdentification as _BoardReaderIdentification,
        )

        return _BoardReaderIdentification(
            boardreader_types=item.boardreader_types,
            components=item.components,
            error_messages=item.error_messages,
        )

    def to_artifact(
        self,
        domain_model: BoardReaderIdentification,
        created_by: str,
        phase: int,
        llm_request_id: str | None = None,
        **kwargs: object,
    ) -> BoardReaderIdentificationArtifact:
        """Convert BoardReaderIdentification to artifact.

        Args:
            domain_model: BoardReaderIdentification domain model
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            llm_request_id: Optional LLM request ID for traceability
            **kwargs: Additional artifact fields

        Returns:
            BoardReaderIdentificationArtifact instance
        """
        return BoardReaderIdentificationArtifact(
            boardreader_types=domain_model.boardreader_types,
            components=domain_model.components,
            error_messages=domain_model.error_messages,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
        )
