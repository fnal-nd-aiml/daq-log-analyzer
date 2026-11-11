"""
File: investigation_config.py
Purpose: Investigation configuration models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: HypothesisConfig, EvidenceConfig, OutcomeConfig, CausalChainConfig, InvestigationConfig
Complexity: Medium | Lines: 84
"""

from pydantic import BaseModel

class HypothesisConfig(BaseModel):
    code_hint_prior_min: float = 0.7
    code_hint_prior_max: float = 0.85
    explicit_cause_prior_min: float = 0.9
    explicit_cause_prior_max: float = 0.95
    pattern_prior_min: float = 0.6
    pattern_prior_max: float = 0.8
    similar_prior_min: float = 0.3
    similar_prior_max: float = 0.5
    fresh_prior_max: float = 0.3
    alternative_prior: float = 0.1
    merge_similarity_threshold: float = 0.8
    merge_prior_cap: float = 0.95
    merge_other_prior_factor: float = 0.3
    enable_llm_deduplication: bool = True
    llm_dedup_similarity_threshold: float = 0.8
    llm_dedup_min_hypotheses: int = 4
    authoritative_hint_threshold: float = 0.85
    max_fresh_if_code_hints: int = 2
    code_hint_probability_share: float = 0.7
    max_alternatives: int = 3
    max_code_hint_hypotheses: int = 5
    max_parsed_hypotheses: int = 5

class EvidenceConfig(BaseModel):
    strength_strong: float = 0.25
    strength_moderate: float = 0.15
    strength_weak: float = 0.05
    targeted_boost_factor: float = 1.5
    targeted_contradict_factor: float = 1.0
    absence_contradict_factor: float = 0.5
    non_targeted_code_factor: float = 0.75
    non_targeted_log_factor: float = 0.5
    code_hint_match_factor: float = 1.0
    term_match_threshold: float = 0.4
    category_relevance_score: float = 0.15
    weak_term_relevance_score: float = 0.05
    consecutive_failure_limit: int = 3
    min_success_rate: float = 0.1
    min_attempts_for_rate: int = 5
    clear_winner_score: float = 0.7
    clear_winner_margin: float = 0.3
    code_hint_early_stop_score: float = 0.5
    code_hint_early_stop_margin: float = 0.2
    min_iterations_before_stop: int = 3
    max_queries_per_iteration: int = 5
    max_log_queries_code_centric: int = 1

class OutcomeConfig(BaseModel):
    confident_score_threshold: float = 0.7
    probable_score_threshold: float = 0.5
    code_hint_probable_threshold: float = 0.6
    viable_threshold: float = 0.4
    high_challenge_penalty: float = 0.15
    medium_challenge_penalty: float = 0.05
    min_confidence_floor: float = 0.3

class CausalChainConfig(BaseModel):
    max_chains: int = 3
    min_hypothesis_score: float = 0.2
    min_evidence_coverage: float = 0.5
    min_logical_validity: float = 0.5

class InvestigationConfig(BaseModel):
    max_hypotheses: int = 10
    max_evidence_iterations: int = 10
    max_chain_depth: int = 8
    confidence_floor: float = 0.1
    confidence_ceiling: float = 0.95
    tier1_pattern_confidence: float = 0.9
    tier1_pattern_accuracy: float = 0.85
    tier1_min_samples: int = 20
    code_hint_fast_path_prior_threshold: float = 0.9
    code_hint_fast_path_match_threshold: float = 0.7
    enable_auto_learning: bool = True
    default_function_source_length: int = 2000
    docs_max_chars: int = 12000
    subcomponent_map_path: str = 'data/docs/sub-component-map.yaml'
    hypothesis: HypothesisConfig = HypothesisConfig()
    evidence: EvidenceConfig = EvidenceConfig()
    outcome: OutcomeConfig = OutcomeConfig()
    causal_chain: CausalChainConfig = CausalChainConfig()