"""
File: results.py
Purpose: Investigation result models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: CalibratedConfidence, SubCause, KeyFile, InvestigationConclusion, HypothesisSummary, ...
Complexity: Medium | Lines: 66
"""

from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field
from .investigation import CausalChain, InvestigationOutcome

if TYPE_CHECKING:
    from .investigation import Hypothesis


class CalibratedConfidence(BaseModel):
    raw: float
    calibrated: float
    derivation: dict = Field(default_factory=dict)
    calibration_notes: list[str] = Field(default_factory=list)


class SubCause(BaseModel):
    description: str
    probability: float = Field(ge=0.0, le=1.0)
    evidence_summary: str | None = None


class KeyFile(BaseModel):
    file_path: str
    purpose: str
    line_range: str | None = None


class InvestigationConclusion(BaseModel):
    root_cause: str
    confidence: CalibratedConfidence
    caveats: list[str] = Field(default_factory=list)
    code_snippet: str | None = Field(default=None, description="Source code where error originates with context")
    code_location: str | None = Field(default=None, description="File:line in function_name() format")
    sub_causes: list[SubCause] = Field(default_factory=list, description="Ranked breakdown of probable sub-causes")
    data_flow: str | None = Field(default=None, description="ASCII visualization of call chain/data flow")
    key_files: list[KeyFile] = Field(default_factory=list, description="Key files to examine during debugging")
    debugging_steps: list[str] = Field(default_factory=list, description="Specific actionable debugging steps")


class HypothesisSummary(BaseModel):
    description: str
    score: float


class InvestigationResult(BaseModel):
    investigation_id: str
    outcome: InvestigationOutcome
    timestamp: datetime = Field(default_factory=datetime.now)
    root_cause: InvestigationConclusion | None = None
    causal_chain: CausalChain | None = None
    recommendations: list[str] = Field(default_factory=list)
    viable_hypotheses: list[HypothesisSummary] = Field(default_factory=list)
    discrimination_needed: list[str] = Field(default_factory=list)
    insufficient_reason: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_summary: str = ""
    duration_seconds: float = 0.0
    alternatives: list[HypothesisSummary] = Field(default_factory=list)
    processing_tier: int = Field(default=3, description="Processing tier used: 1=fast path, 2=heuristic, 3=full LLM")
    pattern_match_used: bool = Field(default=False, description="Whether a cached pattern match was used")
    executive_summary: str = Field(default="", description="Executive summary from the synthesis phase")
    explanation: str = Field(default="", description="Human-readable explanation of the result")
    confidence: float = Field(default=0.0, description="Simple confidence score (0.0-1.0)")
    primary_hypothesis: Hypothesis | None = Field(default=None, description="Primary hypothesis for fast-path results")
