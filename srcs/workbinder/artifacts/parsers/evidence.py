"""
File: evidence.py
Purpose: Evidence query parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: models, artifacts_types, pydantic
Exports: QueryItem, QueryResponse, EvidenceQueryParser
Complexity: Medium | Lines: 33
"""

from __future__ import annotations
from typing import Any, List
from pydantic import BaseModel
from srcs.models import EvidenceItem
from srcs.workbinder.artifacts_types import EvidenceArtifact
from .base import BaseParser
from .json_utils import parse_json_response

class QueryItem(BaseModel):
    query_type: str
    query: str
    targets_hypothesis_id: str = ''
    expected_if_true: str = ''
    expected_if_false: str = ''
    full_source: bool = False

class QueryResponse(BaseModel):
    queries: List[QueryItem]

class EvidenceQueryParser(BaseParser[QueryResponse, dict[str, Any], EvidenceArtifact]):

    def parse_llm_response(self, raw_json: str) -> QueryResponse:
        return parse_json_response(raw_json, QueryResponse)

    def to_domain_model(self, item: QueryItem, **context: object) -> dict[str, Any]:
        return item.model_dump()

    def to_artifact(self, domain_model: EvidenceItem, created_by: str, phase: int, llm_request_id: str | None=None, **kwargs: object) -> EvidenceArtifact:
        return EvidenceArtifact(evidence_type=domain_model.evidence_type, content=domain_model.content, source=domain_model.source, strength=domain_model.strength, found=domain_model.found, created_by=created_by, phase=phase, llm_request_id=llm_request_id, targets_hypothesis_id=domain_model.targets_hypothesis_id, expected_if_true=domain_model.expected_if_true, expected_if_false=domain_model.expected_if_false)

    def parse_to_queries(self, raw_json: str) -> list[dict[str, Any]]:
        response = self.parse_llm_response(raw_json)
        return [self.to_domain_model(q) for q in response.queries]