"""
File: learning_config.py
Purpose: Configuration and data classes for pattern learning.
Category: Utility
Author: artdaq team
Depends: models
Exports: LearningConfig, PatternCandidate
Complexity: Low | Lines: 22
"""

from dataclasses import dataclass, field
from srcs.models import ErrorSignature

@dataclass
class LearningConfig:
    min_investigations_for_pattern: int = 3
    min_confidence_for_pattern: float = 0.6
    pattern_similarity_threshold: float = 0.7
    max_patterns_per_signature: int = 10
    pattern_decay_factor: float = 0.95
    min_samples_for_confidence: int = 5
    min_accuracy_threshold: float = 0.5
    min_samples_for_deactivation: int = 10

@dataclass
class PatternCandidate:
    signature: ErrorSignature
    root_cause: str
    supporting_investigations: list[str] = field(default_factory=list)
    evidence_patterns: list[str] = field(default_factory=list)
    confidence: float = 0.0
    times_seen: int = 0