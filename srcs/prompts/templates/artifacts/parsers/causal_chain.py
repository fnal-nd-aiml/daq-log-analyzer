"""Causal chain parser for LLM response parsing.

Parses causal chain construction responses and converts them to
domain models and WorkBinder artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from pydantic import BaseModel

from srcs.models import CausalChain, CausalStep
from srcs.workbinder.artifacts_types import CausalChainArtifact

from .base import BaseParser
from .json_utils import parse_json_response

if TYPE_CHECKING:
    pass


class ChainStepItem(BaseModel):
    """Single step in causal chain from LLM response.

    Note: The LLM returns 'evidence' (list of evidence IDs),
    which maps to 'evidence_ids' in the domain model.

    Attributes:
        claim: The causal claim (e.g., "A causes B")
        mechanism: How the cause produces the effect
        evidence: List of evidence IDs supporting this step
        is_assumption: Whether this step is an assumption
    """

    claim: str
    mechanism: str = ""
    evidence: List[str] = []  # Maps to evidence_ids in domain model
    is_assumption: bool = False


class ChainResponse(BaseModel):
    """LLM response for causal chain construction.

    Contains a list of chain steps from root cause to observed error.
    """

    steps: List[ChainStepItem]


class CausalChainParser(BaseParser[ChainResponse, CausalChain, CausalChainArtifact]):
    """Parser for causal chain LLM responses.

    Implements two-stage conversion with field mapping:
    - 'evidence' (LLM) -> 'evidence_ids' (domain model)

    Example:
        >>> parser = CausalChainParser()
        >>> response = parser.parse_llm_response(raw_json)
        >>> chain = parser.to_domain_model(response, hypothesis_id="hyp-001")
        >>> artifact = parser.to_artifact(chain, "Logician", 3)
    """

    def parse_llm_response(self, raw_json: str) -> ChainResponse:
        """Parse raw LLM response JSON into ChainResponse.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed ChainResponse

        Raises:
            ValueError: If JSON cannot be parsed
        """
        return parse_json_response(raw_json, ChainResponse)

    def to_domain_model(
        self,
        item: ChainResponse,
        hypothesis_id: str = "",
        **context: object,
    ) -> CausalChain:
        """Convert ChainResponse to CausalChain domain model.

        Handles field mapping from LLM response format:
        - 'evidence' -> 'evidence_ids'

        Args:
            item: ChainResponse from LLM
            hypothesis_id: ID of the hypothesis this chain supports
            **context: Additional context (unused)

        Returns:
            CausalChain domain model instance
        """
        chain = CausalChain(hypothesis_id=hypothesis_id)

        for i, step_data in enumerate(item.steps):
            step = CausalStep(
                step_order=i,
                claim=step_data.claim,
                mechanism=step_data.mechanism,
                # Field mapping: evidence -> evidence_ids
                evidence_ids=step_data.evidence,
                is_assumption=step_data.is_assumption,
            )
            chain.steps.append(step)

        return chain

    def to_artifact(
        self,
        domain_model: CausalChain,
        created_by: str,
        phase: int,
        llm_request_id: str | None = None,
        **kwargs: object,
    ) -> CausalChainArtifact:
        """Convert CausalChain to CausalChainArtifact.

        Args:
            domain_model: CausalChain domain model
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            llm_request_id: Optional LLM request ID for traceability
            **kwargs: Additional artifact fields

        Returns:
            CausalChainArtifact instance
        """
        # Convert steps to dict format for artifact storage
        steps: list[dict[str, Any]] = [
            {
                "step_order": s.step_order,
                "claim": s.claim,
                "mechanism": s.mechanism,
                "evidence_ids": s.evidence_ids,
                "is_assumption": s.is_assumption,
                "assumption_note": s.assumption_note,
                "evidence_strength": s.evidence_strength,
            }
            for s in domain_model.steps
        ]

        return CausalChainArtifact(
            hypothesis_id=domain_model.hypothesis_id,
            steps=steps,
            logical_validity=domain_model.logical_validity,
            evidence_coverage=domain_model.evidence_coverage,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
        )

    def step_item_to_causal_step(
        self,
        item: ChainStepItem,
        step_order: int,
    ) -> CausalStep:
        """Convert a single ChainStepItem to CausalStep.

        Utility method for converting individual steps.

        Args:
            item: ChainStepItem from LLM response
            step_order: Order of this step in the chain

        Returns:
            CausalStep domain model
        """
        return CausalStep(
            step_order=step_order,
            claim=item.claim,
            mechanism=item.mechanism,
            evidence_ids=item.evidence,  # Field mapping
            is_assumption=item.is_assumption,
        )

    @staticmethod
    def steps_from_dicts(step_dicts: list[dict[str, Any]]) -> list[CausalStep]:
        """Reconstruct CausalStep list from artifact dict format.

        Inverse of the dict conversion in to_artifact(). All 7 stored
        fields are preserved.
        """
        return [
            CausalStep(
                step_order=d.get("step_order", 0),
                claim=d.get("claim", ""),
                mechanism=d.get("mechanism", ""),
                evidence_ids=d.get("evidence_ids", []),
                is_assumption=d.get("is_assumption", False),
                assumption_note=d.get("assumption_note"),
                evidence_strength=d.get("evidence_strength", "NONE"),
            )
            for d in step_dicts
        ]

    @staticmethod
    def chain_from_artifact(artifact: CausalChainArtifact) -> CausalChain:
        """Reconstruct a full CausalChain from a CausalChainArtifact."""
        chain = CausalChain(hypothesis_id=artifact.hypothesis_id)
        chain.steps = CausalChainParser.steps_from_dicts(artifact.steps)
        chain.logical_validity = artifact.logical_validity
        chain.evidence_coverage = artifact.evidence_coverage
        return chain
