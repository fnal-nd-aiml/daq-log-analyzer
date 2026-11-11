"""
File: hypothesis.py
Purpose: Hypothesis parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: models, artifacts_types, pydantic
Exports: HypothesisItem, HypothesisResponse, HypothesisParser
Complexity: Medium | Lines: 43
"""

from __future__ import annotations
from typing import TYPE_CHECKING, List
from pydantic import BaseModel
from srcs.models import Hypothesis
from srcs.workbinder.artifacts_types import HypothesisArtifact
from .base import BaseParser
from .json_utils import parse_json_response
if TYPE_CHECKING:
    pass

class HypothesisItem(BaseModel):
    description: str
    category: str
    prior: float
    confirming_evidence: str = ''
    refuting_evidence: str = ''

class HypothesisResponse(BaseModel):
    hypotheses: List[HypothesisItem]

class HypothesisParser(BaseParser[HypothesisResponse, Hypothesis, HypothesisArtifact]):

    def parse_llm_response(self, raw_json: str) -> HypothesisResponse:
        return parse_json_response(raw_json, HypothesisResponse)

    def to_domain_model(self, item: HypothesisItem, source_prefix: str='fresh', max_prior: float | None=None, **context: object) -> Hypothesis:
        prior_value = item.prior
        if max_prior is not None:
            prior_value = min(max_prior, item.prior)
        return Hypothesis(description=item.description, source=f'{source_prefix}:{item.category}', prior=prior_value, score=prior_value, category=item.category, confirming_evidence_design=item.confirming_evidence or None, refuting_evidence_design=item.refuting_evidence or None)

    def to_artifact(self, domain_model: Hypothesis, created_by: str, phase: int, rank: int=0, llm_request_id: str | None=None, **kwargs: object) -> HypothesisArtifact:
        return HypothesisArtifact(description=domain_model.description, source=domain_model.source, prior_probability=domain_model.prior, score=domain_model.score, rank=rank, created_by=created_by, phase=phase, llm_request_id=llm_request_id, category=getattr(domain_model, 'category', None), confirming_evidence=getattr(domain_model, 'confirming_evidence_design', None), refuting_evidence=getattr(domain_model, 'refuting_evidence_design', None))

    def parse_and_convert(self, raw_json: str, source_prefix: str='fresh', max_prior: float | None=None, exclude_descriptions: set[str] | None=None) -> list[Hypothesis]:
        exclude = exclude_descriptions or set()
        response = self.parse_llm_response(raw_json)
        hypotheses = []
        for item in response.hypotheses:
            if item.description not in exclude:
                hypothesis = self.to_domain_model(item, source_prefix=source_prefix, max_prior=max_prior)
                hypotheses.append(hypothesis)
        return hypotheses