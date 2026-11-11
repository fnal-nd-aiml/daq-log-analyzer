"""
File: hypothesis_report.py
Purpose: Hypothesis generation report models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: TierBreakdown, TierGenerationReport, MergedGroup, DeduplicationReport, CategoryCoverage, ...
Complexity: Medium | Lines: 64
"""

from __future__ import annotations
from pydantic import BaseModel, Field

class TierBreakdown(BaseModel):
    tier_name: str
    count: int = 0
    hypothesis_ids: list[str] = Field(default_factory=list)
    avg_prior: float = 0.0
    best_prior: float = 0.0

class TierGenerationReport(BaseModel):
    tiers: list[TierBreakdown] = Field(default_factory=list)
    total_before_dedup: int = 0
    total_after_dedup: int = 0
    fast_path_triggered: bool = False
    fast_path_reason: str = ''
    primary_tier: str = ''

class MergedGroup(BaseModel):
    kept_hypothesis_id: str
    merged_hypothesis_ids: list[str] = Field(default_factory=list)
    similarity_scores: list[float] = Field(default_factory=list)
    merge_reason: str
    combined_prior: float = 0.0

class DeduplicationReport(BaseModel):
    method_used: str = 'none'
    original_count: int = 0
    final_count: int = 0
    merged_groups: list[MergedGroup] = Field(default_factory=list)
    distinct_hypotheses: list[str] = Field(default_factory=list)
    merge_threshold: float = 0.8

class CategoryCoverage(BaseModel):
    category: str
    is_covered: bool = False
    hypothesis_count: int = 0
    best_prior: float = 0.0
    hypothesis_ids: list[str] = Field(default_factory=list)

class CategoryCoverageAnalysis(BaseModel):
    categories: list[CategoryCoverage] = Field(default_factory=list)
    covered_count: int = 0
    missing_categories: list[str] = Field(default_factory=list)
    coverage_score: float = 0.0
    suggestions: list[str] = Field(default_factory=list)

class PriorAdjustment(BaseModel):
    reason: str
    delta: float

class PriorJustification(BaseModel):
    hypothesis_id: str
    base_rate: float
    adjustments: list[PriorAdjustment] = Field(default_factory=list)
    final_prior: float = 0.0
    normalization_factor: float = 1.0
    normalized_prior: float = 0.0

class PriorJustificationReport(BaseModel):
    justifications: list[PriorJustification] = Field(default_factory=list)
    normalization_mode: str = 'single_tier'
    code_hint_share: float = 0.5
    total_raw_prior: float = 0.0