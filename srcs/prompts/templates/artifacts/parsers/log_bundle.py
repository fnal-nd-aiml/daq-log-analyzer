"""Log bundle parser for LLM response parsing.

Parses log bundle analysis responses (Phase -1 Step 2) and converts
them to domain models and WorkBinder artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from pydantic import BaseModel, Field

from srcs.workbinder.artifacts_types import (
    BoardAnalysis,
    CascadeLink,
    LogBundleArtifact,
    LogBundleClue,
    LogBundleErrorEntry,
)

from .base import BaseParser
from .json_utils import parse_json_response

if TYPE_CHECKING:
    from srcs.persona.chronicler import ChroniclerNarrativeResponse


class AffectedBoardItem(BaseModel):
    """Per-board analysis item from LLM response.

    Attributes:
        board_name: Short board identifier (e.g., "wwtop03")
        filename: Source log filename
        role: Board role (primary_failure, secondary_cascade, downstream_effect)
        failure_mode: One-sentence failure description
        key_error_message: Most significant error message
        source_location: Source code location from MSG header
        error_count: Number of errors for this board
        warning_count: Number of warnings for this board
    """

    board_name: str = ""
    filename: str = ""
    role: str = "unknown"
    failure_mode: str = ""
    key_error_message: str = ""
    source_location: str = ""
    error_count: int = 0
    warning_count: int = 0


class CascadeLinkItem(BaseModel):
    """Cascade link item from LLM response.

    Attributes:
        from_board: Board where cause originated
        to_board: Board that was affected
        mechanism: How failure propagated
        evidence: Key numeric evidence for the link
    """

    from_board: str = ""
    to_board: str = ""
    mechanism: str = ""
    evidence: str = ""


class ClueItem(BaseModel):
    """Clue item from LLM response.

    Attributes:
        clue_type: Type of clue (error_pattern, component_interaction, etc.)
        description: What to investigate
        source_file: Filename where clue was found
        relevance: Relevance level (HIGH, MEDIUM, LOW)
        suggested_search: Function or pattern to search for
    """

    clue_type: str = "error_pattern"
    description: str = ""
    source_file: str = ""
    relevance: str = "HIGH"
    suggested_search: str | None = None


class LogBundleResponse(BaseModel):
    """LLM response for log bundle analysis.

    Top-level response matching the log_bundle_analysis schema.
    """

    annotated_narrative: str = ""
    primary_error_file: str = ""
    primary_error_message: str = ""
    primary_error_line: int | None = None
    cascade_description: str = ""
    clues: List[ClueItem] = Field(default_factory=list)
    affected_boards: List[AffectedBoardItem] = Field(default_factory=list)
    cascade_chain: List[CascadeLinkItem] = Field(default_factory=list)


class LogBundleParser(
    BaseParser[LogBundleResponse, dict[str, Any], LogBundleArtifact]
):
    """Parser for log bundle analysis LLM responses.

    Implements two-stage conversion:
    - LLM JSON -> LogBundleResponse
    - ChroniclerNarrativeResponse -> dict of typed domain objects
    - Domain dict -> LogBundleArtifact

    The to_domain_model() method accepts a ChroniclerNarrativeResponse
    (already parsed by _call_llm_structured) and converts the untyped
    dict fields into typed domain objects (LogBundleErrorEntry,
    LogBundleClue, BoardAnalysis, CascadeLink).

    Example:
        >>> parser = LogBundleParser()
        >>> parsed = parser.to_domain_model(response)
        >>> primary_error = parsed["primary_error"]
        >>> clues = parsed["clues"]
    """

    def parse_llm_response(self, raw_json: str) -> LogBundleResponse:
        """Parse raw LLM response JSON into LogBundleResponse.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed LogBundleResponse

        Raises:
            ValueError: If JSON cannot be parsed
        """
        return parse_json_response(raw_json, LogBundleResponse)

    def to_domain_model(
        self,
        item: ChroniclerNarrativeResponse,
        **context: object,
    ) -> dict[str, Any]:
        """Convert ChroniclerNarrativeResponse to typed domain objects.

        Converts the untyped list[dict] fields in the response into
        typed domain models: LogBundleErrorEntry, LogBundleClue,
        BoardAnalysis, and CascadeLink.

        Args:
            item: ChroniclerNarrativeResponse from _call_llm_structured
            **context: Additional context (unused)

        Returns:
            Dict with typed domain objects:
                - primary_error: LogBundleErrorEntry | None
                - clues: list[LogBundleClue]
                - affected_boards: list[BoardAnalysis]
                - cascade_chain: list[CascadeLink]
                - annotated_narrative: str
                - cascade_description: str
        """
        # Build primary error entry
        primary_error: LogBundleErrorEntry | None = None
        if item.primary_error_message:
            primary_error = LogBundleErrorEntry(
                filename=item.primary_error_file,
                line_number=item.primary_error_line,
                message=item.primary_error_message,
                is_primary=True,
            )

        # Build clues list
        clues: list[LogBundleClue] = []
        for clue_data in item.clues:
            clues.append(LogBundleClue(
                clue_type=clue_data.get("clue_type", "error_pattern"),
                description=clue_data.get("description", ""),
                source_file=clue_data.get("source_file", ""),
                relevance=clue_data.get("relevance", "HIGH"),
                suggested_search=clue_data.get("suggested_search"),
            ))

        # Build per-board analysis list
        board_analyses: list[BoardAnalysis] = []
        for board_data in item.affected_boards:
            board_analyses.append(BoardAnalysis(
                board_name=board_data.get("board_name", ""),
                filename=board_data.get("filename", ""),
                role=board_data.get("role", "unknown"),
                failure_mode=board_data.get("failure_mode", ""),
                key_error_message=board_data.get("key_error_message", ""),
                source_location=board_data.get("source_location", ""),
                error_count=board_data.get("error_count", 0),
                warning_count=board_data.get("warning_count", 0),
            ))

        # Build cascade links
        cascade_links: list[CascadeLink] = []
        for link_data in item.cascade_chain:
            cascade_links.append(CascadeLink(
                from_board=link_data.get("from_board", ""),
                to_board=link_data.get("to_board", ""),
                mechanism=link_data.get("mechanism", ""),
                evidence=link_data.get("evidence", ""),
            ))

        return {
            "primary_error": primary_error,
            "clues": clues,
            "affected_boards": board_analyses,
            "cascade_chain": cascade_links,
            "annotated_narrative": item.annotated_narrative,
            "cascade_description": item.cascade_description,
        }

    def to_artifact(
        self,
        domain_model: dict[str, Any],
        created_by: str,
        phase: int,
        **kwargs: Any,
    ) -> LogBundleArtifact:
        """Convert domain dict to LogBundleArtifact.

        Args:
            domain_model: Dict from to_domain_model()
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            **kwargs: Additional artifact fields (source_files,
                merged_timeline, error_timeline, documentation_reference)

        Returns:
            LogBundleArtifact instance
        """
        return LogBundleArtifact(
            source_files=kwargs.get("source_files", []),
            merged_timeline=kwargs.get("merged_timeline", ""),
            annotated_narrative=domain_model.get("annotated_narrative", ""),
            primary_error=domain_model.get("primary_error"),
            error_timeline=kwargs.get("error_timeline", []),
            cascade_description=domain_model.get("cascade_description", ""),
            clues=domain_model.get("clues", []),
            affected_boards=domain_model.get("affected_boards", []),
            cascade_chain=domain_model.get("cascade_chain", []),
            documentation_reference=kwargs.get(
                "documentation_reference", ""
            ),
            created_by=created_by,
            phase=phase,
        )
