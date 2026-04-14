"""
File: knowledge.py
Purpose: Knowledge-related data models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: ErrorPattern, RootCausePattern, PatternMatch, SimilarInvestigation, RecommendedHypothesis, ...
Complexity: Medium | Lines: 174
"""

from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field
from .base import generate_id

if TYPE_CHECKING:
    from .source_location import SourceLocation


class ErrorPattern(BaseModel):
    id: str = Field(default_factory=generate_id)
    name: str
    description: str | None = None
    signature_function: str | None = None
    signature_message_pattern: str | None = None
    signature_level: str = "ERROR"
    times_seen: int = 0
    times_correct: int = 0
    times_incorrect: int = 0
    pattern_confidence: float = 0.0
    is_active: bool = True
    user_verified: bool = False
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class RootCausePattern(BaseModel):
    id: str = Field(default_factory=generate_id)
    error_pattern_id: str
    description: str
    frequency: float = 0.0
    confirming_evidence_patterns: list[str] = Field(default_factory=list)
    refuting_evidence_patterns: list[str] = Field(default_factory=list)


class PatternMatch(BaseModel):
    pattern: ErrorPattern
    confidence: float
    matched_fields: list[str]


class SimilarInvestigation(BaseModel):
    investigation_id: str
    similarity_score: float
    root_cause: str | None = None
    was_correct: bool | None = None
    outcome: str | None = None


class RecommendedHypothesis(BaseModel):
    description: str
    source: str
    prior: float
    is_authoritative: bool = False


class EvidenceQueryTemplate(BaseModel):
    query_type: str
    query_template: str
    expected_result: str | None = None
    full_source: bool = False


class FeedbackSummary(BaseModel):
    investigation_id: str
    was_correct: bool
    actual_cause: str | None = None
    what_was_wrong: str | None = None
    suggestions: str | None = None
    additional_notes: str | None = None


class PriorKnowledge(BaseModel):
    matched_patterns: list[PatternMatch] = Field(default_factory=list)
    similar_investigations: list[SimilarInvestigation] = Field(default_factory=list)
    recommended_hypotheses: list[RecommendedHypothesis] = Field(default_factory=list)
    recommended_queries: list[EvidenceQueryTemplate] = Field(default_factory=list)
    source_locations: list[SourceLocation] = Field(default_factory=list)
    resolution_digest: list[ResolutionDigest] = Field(default_factory=list)
    configuration_context: ConfigurationContext | None = None
    diagnostic_history: DiagnosticHistory | None = None
    enriched_case_summaries: list[str] = Field(default_factory=list)
    feedback_from_similar: list[FeedbackSummary] = Field(default_factory=list)
    documentation_context: str = ""
    tier1_pattern_confidence: float = 0.9
    tier1_pattern_accuracy: float = 0.85
    tier1_min_samples: int = 20
    code_hint_prior_threshold: float = 0.9
    code_hint_match_threshold: float = 0.7

    def has_tier1_pattern(self) -> bool:
        if not self.matched_patterns:
            return False
        match = self.matched_patterns[0]
        pattern = match.pattern
        if pattern.pattern_confidence < self.tier1_pattern_confidence:
            return False
        if pattern.times_seen < self.tier1_min_samples:
            return False
        if pattern.times_seen > 0:
            accuracy = pattern.times_correct / pattern.times_seen
        else:
            accuracy = 0.0
        return accuracy >= self.tier1_pattern_accuracy

    def has_authoritative_code_hint(self) -> bool:
        for rh in self.recommended_hypotheses:
            if not rh.is_authoritative:
                continue
            if rh.prior < self.code_hint_prior_threshold:
                continue
            if not rh.source.startswith("code_hint:explicit_cause"):
                continue
            if self.source_locations:
                best_match_score = max((loc.match_score or 0.0 for loc in self.source_locations))
                if best_match_score < self.code_hint_match_threshold:
                    continue
            return True
        return False

    def has_high_confidence_pattern(self) -> bool:
        if not self.matched_patterns:
            return False
        return self.matched_patterns[0].confidence > 0.9


class CalibrationBucket(BaseModel):
    stated_confidence: float
    actual_accuracy: float
    sample_count: int


class CalibrationData(BaseModel):
    model_name: str
    error_type: str | None = None
    buckets: dict[str, CalibrationBucket] = Field(default_factory=dict)
    overall_bias: float = 0.0
    sample_size: int = 0


class ResolutionDigest(BaseModel):
    investigation_id: str
    root_cause: str | None = None
    resolution_action: str | None = None
    resolution_category: str = "unknown"
    resolution_success: bool | None = None
    confidence: float = 0.0
    applicability_notes: str = ""


class ConfigParam(BaseModel):
    name: str
    current_value: str | None = None
    source: str = ""
    typical_range: tuple[str, str] | None = None
    note: str = ""


class ConfigurationContext(BaseModel):
    component: str
    relevant_params: list[ConfigParam] = Field(default_factory=list)
    config_from_similar_successes: dict[str, str] = Field(default_factory=dict)
    deviation_flags: list[str] = Field(default_factory=list)


class DiagnosticHistory(BaseModel):
    error_signature: str
    total_occurrences: int = 0
    resolved_count: int = 0
    resolution_rate: float = 0.0
    avg_confidence: float = 0.0
    common_root_causes: list[tuple[str, float]] = Field(default_factory=list)
    avg_time_to_resolve: str | None = None
