"""
File: investigation.py
Purpose: Investigation-related data models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: InvestigationOutcome, Hypothesis, EvidenceItem, Evidence, CausalStep, ...
Complexity: High | Lines: 212
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from .base import generate_id

if TYPE_CHECKING:
    from .logs import Log


class InvestigationOutcome(str, Enum):
    CONFIDENT = "CONFIDENT"
    PROBABLE = "PROBABLE"
    UNCERTAIN = "UNCERTAIN"
    INSUFFICIENT = "INSUFFICIENT"
    CONTRADICTORY = "CONTRADICTORY"


class Hypothesis(BaseModel):
    id: str = Field(default_factory=generate_id)
    description: str
    source: str
    prior: float = Field(ge=0.0, le=1.0, default=0.2)
    score: float = 0.0
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    status: str = "active"
    binder_artifact_id: str | None = Field(
        default=None, description="ID of corresponding HypothesisArtifact in WorkBinder"
    )
    category: str | None = Field(
        default=None, description="Category classification from LLM (timing, configuration, etc.)"
    )
    confirming_evidence_design: str | None = Field(
        default=None, description="Description of evidence that would confirm this hypothesis"
    )
    refuting_evidence_design: str | None = Field(
        default=None, description="Description of evidence that would refute this hypothesis"
    )


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    evidence_type: str
    content: str
    source: str
    strength: str = "WEAK"
    found: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)
    targets_hypothesis_id: str | None = None
    expected_if_true: str | None = None
    expected_if_false: str | None = None


class Evidence(BaseModel):
    items: dict[str, EvidenceItem] = Field(default_factory=dict)

    def add(self, item: EvidenceItem) -> None:
        self.items[item.id] = item

    def get(self, item_id: str) -> EvidenceItem | None:
        return self.items.get(item_id)

    def summary(self) -> str:
        if not self.items:
            return "No evidence collected"
        by_type: dict[str, list[EvidenceItem]] = {}
        for item in self.items.values():
            if item.evidence_type not in by_type:
                by_type[item.evidence_type] = []
            by_type[item.evidence_type].append(item)
        lines = []
        for etype, items in by_type.items():
            strong = sum((1 for i in items if i.strength == "STRONG"))
            moderate = sum((1 for i in items if i.strength == "MODERATE"))
            weak = sum((1 for i in items if i.strength == "WEAK"))
            lines.append(f"- {etype}: {len(items)} items (strong: {strong}, moderate: {moderate}, weak: {weak})")
        return "\n".join(lines)

    def get_by_type(self, evidence_type: str) -> list[EvidenceItem]:
        return [i for i in self.items.values() if i.evidence_type == evidence_type]

    def get_strong_evidence(self) -> list[EvidenceItem]:
        return [i for i in self.items.values() if i.strength == "STRONG"]


class CausalStep(BaseModel):
    id: str = Field(default_factory=generate_id)
    step_order: int
    claim: str
    mechanism: str | None = None
    code_reference: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_strength: str = "NONE"
    temporal_verified: bool = False
    is_assumption: bool = False
    assumption_note: str | None = None


class CausalChain(BaseModel):
    id: str = Field(default_factory=generate_id)
    hypothesis_id: str
    steps: list[CausalStep] = Field(default_factory=list)
    logical_validity: float = 0.0
    evidence_coverage: float = 0.0
    gaps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class Challenge(BaseModel):
    id: str = Field(default_factory=generate_id)
    challenge_type: str
    content: str
    severity: str = "MEDIUM"
    requires_response: bool = True
    resolved: bool = False
    resolution: str | None = None


class Investigation(BaseModel):
    id: str = Field(default_factory=generate_id)
    trigger_error: "Log"
    context_logs: list["Log"] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=Evidence)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    challenges: list[Challenge] = Field(default_factory=list)
    matched_pattern_id: str | None = None
    similar_investigation_ids: list[str] = Field(default_factory=list)
    outcome: InvestigationOutcome | None = None
    binder: Any = Field(default=None, exclude=True)


class QueryTypeStats(BaseModel):
    query_type: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    was_skipped: bool = False
    skip_reason: str = ""


class QueryEffectivenessReport(BaseModel):
    query_type_stats: dict[str, QueryTypeStats] = Field(default_factory=dict)
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    skipped_query_types: list[str] = Field(default_factory=list)
    strategy_pivots: list[str] = Field(default_factory=list)
    overall_success_rate: float = 0.0


class EvidenceGap(BaseModel):
    hypothesis_id: str
    hypothesis_description: str
    gap_type: str
    missing_evidence_types: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    severity: str = "medium"


class EvidenceGapAnalysis(BaseModel):
    gaps: list[EvidenceGap] = Field(default_factory=list)
    fully_covered_hypotheses: int = 0
    partially_covered_hypotheses: int = 0
    uncovered_hypotheses: int = 0
    most_critical_gap: EvidenceGap | None = None
    recommended_next_queries: list[str] = Field(default_factory=list)


class EvidenceQualityScore(BaseModel):
    overall_score: float = 0.0
    strength_score: float = 0.0
    diversity_score: float = 0.0
    coverage_score: float = 0.0
    discrimination_score: float = 0.0
    evidence_types_present: list[str] = Field(default_factory=list)
    evidence_types_missing: list[str] = Field(default_factory=list)
    hypotheses_with_evidence: int = 0
    hypotheses_without_evidence: int = 0
    has_strong_discriminating_evidence: bool = False
    has_code_and_log_evidence: bool = False
    top_hypothesis_supported: bool = False


class AlternativePath(BaseModel):
    path_type: str
    description: str
    expected_benefit: str
    difficulty: str = "medium"
    requires: list[str] = Field(default_factory=list)


class AlternativeInvestigationPaths(BaseModel):
    paths: list[AlternativePath] = Field(default_factory=list)
    reason_current_insufficient: str = ""
    most_promising_path: AlternativePath | None = None


def _rebuild_models() -> None:
    from .knowledge import PriorKnowledge
    from .logs import Log
    from .results import InvestigationResult
    from .source_location import SourceLocation

    Investigation.model_rebuild(_types_namespace={"Log": Log})
    InvestigationResult.model_rebuild(_types_namespace={"Hypothesis": Hypothesis})
    PriorKnowledge.model_rebuild(_types_namespace={"SourceLocation": SourceLocation})
