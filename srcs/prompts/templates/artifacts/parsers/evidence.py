"""Evidence query parser for LLM response parsing.

Parses evidence query responses and converts them to
query dictionaries for execution.
"""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel

from srcs.models import EvidenceItem
from srcs.workbinder.artifacts_types import EvidenceArtifact

from .base import BaseParser
from .json_utils import parse_json_response


class QueryItem(BaseModel):
    """Single evidence query from LLM response.

    Contains query specification for gathering discriminating evidence.

    Attributes:
        query_type: Type of query (log_search, function_lookup, etc.)
        query: Query string or pattern
        targets_hypothesis_id: ID of hypothesis this query targets
        expected_if_true: Expected result if target hypothesis is correct
        expected_if_false: Expected result if target hypothesis is incorrect
        full_source: For function_lookup, request full source without truncation
    """

    query_type: str
    query: str
    targets_hypothesis_id: str = ""
    expected_if_true: str = ""
    expected_if_false: str = ""
    full_source: bool = False


class QueryResponse(BaseModel):
    """LLM response for evidence queries.

    Contains a list of queries to execute for gathering evidence.
    """

    queries: List[QueryItem]


class EvidenceQueryParser(BaseParser[QueryResponse, dict[str, Any], EvidenceArtifact]):
    """Parser for evidence query LLM responses.

    Converts LLM query responses into dictionaries suitable for
    query execution by the evidence seeker.

    Example:
        >>> parser = EvidenceQueryParser()
        >>> response = parser.parse_llm_response(raw_json)
        >>> queries = [parser.to_domain_model(q) for q in response.queries]
        >>> # Execute queries...
        >>> for result in query_results:
        ...     artifact = parser.to_artifact(result, "Detective", 2)
    """

    def parse_llm_response(self, raw_json: str) -> QueryResponse:
        """Parse raw LLM response JSON into QueryResponse.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            Parsed QueryResponse

        Raises:
            ValueError: If JSON cannot be parsed
        """
        return parse_json_response(raw_json, QueryResponse)

    def to_domain_model(
        self,
        item: QueryItem,
        **context: object,
    ) -> dict[str, Any]:
        """Convert QueryItem to query dictionary.

        Args:
            item: QueryItem from LLM response
            **context: Additional context (unused)

        Returns:
            Query dictionary for execution
        """
        return item.model_dump()

    def to_artifact(
        self,
        domain_model: EvidenceItem,
        created_by: str,
        phase: int,
        llm_request_id: str | None = None,
        **kwargs: object,
    ) -> EvidenceArtifact:
        """Convert EvidenceItem to EvidenceArtifact.

        Note: This method takes an EvidenceItem (the result of query
        execution) rather than the query itself.

        Args:
            domain_model: EvidenceItem from query execution
            created_by: Persona name creating the artifact
            phase: Investigation phase number
            llm_request_id: Optional LLM request ID for traceability
            **kwargs: Additional artifact fields

        Returns:
            EvidenceArtifact instance
        """
        return EvidenceArtifact(
            evidence_type=domain_model.evidence_type,
            content=domain_model.content,
            source=domain_model.source,
            strength=domain_model.strength,
            found=domain_model.found,
            created_by=created_by,
            phase=phase,
            llm_request_id=llm_request_id,
            # Targeting fields for discriminating evidence
            targets_hypothesis_id=domain_model.targets_hypothesis_id,
            expected_if_true=domain_model.expected_if_true,
            expected_if_false=domain_model.expected_if_false,
        )

    def parse_to_queries(self, raw_json: str) -> list[dict[str, Any]]:
        """Convenience method to parse and convert to query dicts.

        Args:
            raw_json: Raw JSON string from LLM

        Returns:
            List of query dictionaries ready for execution
        """
        response = self.parse_llm_response(raw_json)
        return [self.to_domain_model(q) for q in response.queries]
