"""
File: boardreader_identification.py
Purpose: Boardreader identification parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: chronicler, artifacts_types, pydantic
Exports: BoardReaderIdentificationItem, BoardReaderIdentificationResponse, BoardReaderIdentificationParser
Complexity: Medium | Lines: 53
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
    boardreader_types: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    error_messages: List[str] = Field(default_factory=list)


class BoardReaderIdentificationResponse(BaseModel):
    boardreader_types: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    error_messages: List[str] = Field(default_factory=list)


class BoardReaderIdentificationParser(
    BaseParser[BoardReaderIdentificationResponse, Any, BoardReaderIdentificationArtifact]
):

    def parse_llm_response(self, raw_json: str) -> BoardReaderIdentificationResponse:
        return parse_json_response(raw_json, BoardReaderIdentificationResponse)

    def to_domain_model(self, item: BoardReaderIdentificationResponse, **context: object) -> BoardReaderIdentification:
        from srcs.persona.chronicler import BoardReaderIdentification as _BoardReaderIdentification

        return _BoardReaderIdentification(
            boardreader_types=item.boardreader_types, components=item.components, error_messages=item.error_messages
        )

    def to_artifact(
        self,
        domain_model: BoardReaderIdentification,
        created_by: str,
        phase: int,
        llm_request_id: str | None = None,
        **kwargs: object,
    ) -> BoardReaderIdentificationArtifact:
        return BoardReaderIdentificationArtifact(
            boardreader_types=domain_model.boardreader_types,
            components=domain_model.components,
            error_messages=domain_model.error_messages,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
        )
