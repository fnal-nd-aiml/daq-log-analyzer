"""
File: causal_chain.py
Purpose: Causal chain parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: models, artifacts_types, pydantic
Exports: ChainStepItem, ChainResponse, CausalChainParser
Complexity: Medium | Lines: 49
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
    claim: str
    mechanism: str = ''
    evidence: List[str] = []
    is_assumption: bool = False

class ChainResponse(BaseModel):
    steps: List[ChainStepItem]

class CausalChainParser(BaseParser[ChainResponse, CausalChain, CausalChainArtifact]):

    def parse_llm_response(self, raw_json: str) -> ChainResponse:
        return parse_json_response(raw_json, ChainResponse)

    def to_domain_model(self, item: ChainResponse, hypothesis_id: str='', **context: object) -> CausalChain:
        chain = CausalChain(hypothesis_id=hypothesis_id)
        for i, step_data in enumerate(item.steps):
            step = CausalStep(step_order=i, claim=step_data.claim, mechanism=step_data.mechanism, evidence_ids=step_data.evidence, is_assumption=step_data.is_assumption)
            chain.steps.append(step)
        return chain

    def to_artifact(self, domain_model: CausalChain, created_by: str, phase: int, llm_request_id: str | None=None, **kwargs: object) -> CausalChainArtifact:
        steps: list[dict[str, Any]] = [{'step_order': s.step_order, 'claim': s.claim, 'mechanism': s.mechanism, 'evidence_ids': s.evidence_ids, 'is_assumption': s.is_assumption, 'assumption_note': s.assumption_note, 'evidence_strength': s.evidence_strength} for s in domain_model.steps]
        return CausalChainArtifact(hypothesis_id=domain_model.hypothesis_id, steps=steps, logical_validity=domain_model.logical_validity, evidence_coverage=domain_model.evidence_coverage, created_by=created_by, phase=phase, llm_request_id=llm_request_id)

    def step_item_to_causal_step(self, item: ChainStepItem, step_order: int) -> CausalStep:
        return CausalStep(step_order=step_order, claim=item.claim, mechanism=item.mechanism, evidence_ids=item.evidence, is_assumption=item.is_assumption)

    @staticmethod
    def steps_from_dicts(step_dicts: list[dict[str, Any]]) -> list[CausalStep]:
        return [CausalStep(step_order=d.get('step_order', 0), claim=d.get('claim', ''), mechanism=d.get('mechanism', ''), evidence_ids=d.get('evidence_ids', []), is_assumption=d.get('is_assumption', False), assumption_note=d.get('assumption_note'), evidence_strength=d.get('evidence_strength', 'NONE')) for d in step_dicts]

    @staticmethod
    def chain_from_artifact(artifact: CausalChainArtifact) -> CausalChain:
        chain = CausalChain(hypothesis_id=artifact.hypothesis_id)
        chain.steps = CausalChainParser.steps_from_dicts(artifact.steps)
        chain.logical_validity = artifact.logical_validity
        chain.evidence_coverage = artifact.evidence_coverage
        return chain