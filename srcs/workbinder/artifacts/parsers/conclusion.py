"""
File: conclusion.py
Purpose: Conclusion parser for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: models, artifacts_types, pydantic
Exports: SubCauseItem, KeyFileItem, ConclusionItem, ConclusionResponse, ConclusionParser
Complexity: High | Lines: 47
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
    description: str
    probability: float = 0.0
    evidence_summary: str = ''

class KeyFileItem(BaseModel):
    file_path: str
    purpose: str
    line_range: str | None = None

class ConclusionItem(BaseModel):
    root_cause: str
    confidence: float = 0.0
    caveats: List[str] = []
    code_snippet: str = ''
    code_location: str = ''
    sub_causes: List[SubCauseItem] = []
    data_flow: str = ''
    key_files: List[KeyFileItem] = []
    debugging_steps: List[str] = []

class ConclusionResponse(BaseModel):
    conclusion: ConclusionItem

class ConclusionParser(BaseParser[ConclusionResponse, InvestigationConclusion, ConclusionArtifact]):

    def parse_llm_response(self, raw_json: str) -> ConclusionResponse:
        return parse_json_response(raw_json, ConclusionResponse)

    def to_domain_model(self, item: ConclusionItem, calibrated_confidence: float | None=None, **context: Any) -> InvestigationConclusion:
        from srcs.models import KeyFile, SubCause
        sub_causes = [SubCause(description=sc.description, probability=sc.probability, evidence_summary=sc.evidence_summary or None) for sc in item.sub_causes]
        key_files = [KeyFile(file_path=kf.file_path, purpose=kf.purpose, line_range=kf.line_range) for kf in item.key_files]
        return InvestigationConclusion(root_cause=item.root_cause, confidence=CalibratedConfidence(raw=item.confidence, calibrated=calibrated_confidence or item.confidence), caveats=item.caveats, code_snippet=item.code_snippet or None, code_location=item.code_location or None, sub_causes=sub_causes, data_flow=item.data_flow or None, key_files=key_files, debugging_steps=item.debugging_steps)

    def to_artifact(self, domain_model: InvestigationConclusion, created_by: str, phase: int, outcome: str='CONFIDENT', llm_request_id: str | None=None, **kwargs: Any) -> ConclusionArtifact:
        return ConclusionArtifact(root_cause=domain_model.root_cause, confidence_raw=domain_model.confidence.raw, confidence_calibrated=domain_model.confidence.calibrated, outcome=outcome, code_location=domain_model.code_location, code_snippet=domain_model.code_snippet, data_flow=domain_model.data_flow, caveats=domain_model.caveats, debugging_steps=domain_model.debugging_steps, created_by=created_by, phase=phase, llm_request_id=llm_request_id)