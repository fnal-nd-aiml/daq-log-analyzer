"""Conclusion parser for LLM response parsing.

Parses synthesis responses and converts them to
domain models and WorkBinder artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from pydantic import BaseModel

from srcs.models import CalibratedConfidence, InvestigationConclusion
from srcs.workbinder.artifacts_types import ConclusionArtifact

from .base import BaseParser
from .json_utils import parse_json_response

if TYPE_CHECKING:
    pass


class SubCauseItem(BaseModel):
    """Single sub-cause from LLM response.

    Attributes:
        description: Sub-cause description
        probability: Probability estimate (0.0-1.0)
        evidence_summary: Optional summary of supporting evidence
    """

    description: str
    probability: float = 0.0
    evidence_summary: str = ""


class KeyFileItem(BaseModel):
    """Key file from LLM response.

    Attributes:
        file_path: Path to the file
        purpose: Why this file is important
        line_range: Optional line range (e.g., "lines 480-520")
    """

    file_path: str
    purpose: str
    line_range: str | None = None


class ConclusionItem(BaseModel):
    """Conclusion from LLM synthesis response.

    Attributes:
        root_cause: Final root cause determination
        confidence: Confidence level (0.0-1.0)
        caveats: List of caveats and limitations
        code_snippet: Relevant code at error location
        code_location: File:line of error
        sub_causes: Ranked breakdown of sub-causes
        data_flow: ASCII visualization of call chain
        key_files: Key files to examine
        debugging_steps: Specific debugging steps
    """

    root_cause: str
    confidence: float = 0.0
    caveats: List[str] = []
    code_snippet: str = ""
    code_location: str = ""
    sub_causes: List[SubCauseItem] = []
    data_flow: str = ""
    key_files: List[KeyFileItem] = []
    debugging_steps: List[str] = []


class ConclusionResponse(BaseModel):
    """LLM response for synthesis.

    Contains the conclusion and its components.
    """

    conclusion: ConclusionItem


class ConclusionParser(
    BaseParser[ConclusionResponse, InvestigationConclusion, ConclusionArtifact]
):
    """Parser for synthesis LLM responses.

    Implements two-stage conversion:
    1. LLM Response -> InvestigationConclusion domain model
    2. InvestigationConclusion -> ConclusionArtifact

    Example:
        >>> parser = ConclusionParser()
        >>> response = parser.parse_llm_response(raw_json)
        >>> conclusion = parser.to_domain_model(response.conclusion)
        >>> artifact = parser.to_artifact(conclusion, "Synthesizer", 6)
    """

    def parse_llm_response(self, raw_json: str) -> ConclusionResponse:
        """Parse raw LLM response JSON into ConclusionResponse.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed ConclusionResponse

        Raises:
            ValueError: If JSON cannot be parsed
        """
        return parse_json_response(raw_json, ConclusionResponse)

    def to_domain_model(
        self,
        item: ConclusionItem,
        calibrated_confidence: float | None = None,
        **context: Any,
    ) -> InvestigationConclusion:
        """Convert ConclusionItem to InvestigationConclusion domain model.

        Args:
            item: ConclusionItem from LLM response
            calibrated_confidence: Optional calibrated confidence value
            **context: Additional context (unused)

        Returns:
            InvestigationConclusion domain model instance
        """
        from srcs.models import KeyFile, SubCause

        # Convert sub_causes
        sub_causes = [
            SubCause(
                description=sc.description,
                probability=sc.probability,
                evidence_summary=sc.evidence_summary or None,
            )
            for sc in item.sub_causes
        ]

        # Convert key_files
        key_files = [
            KeyFile(
                file_path=kf.file_path,
                purpose=kf.purpose,
                line_range=kf.line_range,
            )
            for kf in item.key_files
        ]

        return InvestigationConclusion(
            root_cause=item.root_cause,
            confidence=CalibratedConfidence(
                raw=item.confidence,
                calibrated=calibrated_confidence or item.confidence,
            ),
            caveats=item.caveats,
            code_snippet=item.code_snippet or None,
            code_location=item.code_location or None,
            sub_causes=sub_causes,
            data_flow=item.data_flow or None,
            key_files=key_files,
            debugging_steps=item.debugging_steps,
        )

    def to_artifact(
        self,
        domain_model: InvestigationConclusion,
        created_by: str,
        phase: int,
        outcome: str = "CONFIDENT",
        llm_request_id: str | None = None,
        **kwargs: Any,
    ) -> ConclusionArtifact:
        """Convert InvestigationConclusion to ConclusionArtifact.

        Args:
            domain_model: InvestigationConclusion domain model
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            outcome: Investigation outcome (default "CONFIDENT")
            llm_request_id: Optional LLM request ID for traceability
            **kwargs: Additional artifact fields

        Returns:
            ConclusionArtifact instance
        """
        return ConclusionArtifact(
            root_cause=domain_model.root_cause,
            confidence_raw=domain_model.confidence.raw,
            confidence_calibrated=domain_model.confidence.calibrated,
            outcome=outcome,
            code_location=domain_model.code_location,
            code_snippet=domain_model.code_snippet,
            data_flow=domain_model.data_flow,
            caveats=domain_model.caveats,
            debugging_steps=domain_model.debugging_steps,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
        )
