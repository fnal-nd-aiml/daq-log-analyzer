"""
File: store_interface.py
Purpose: Abstract interface for structured knowledge storage.
Category: Utility
Author: artdaq team
Depends: models
Exports: StructuredStore
Complexity: High | Lines: 152
"""

from abc import ABC, abstractmethod
from typing import Any
from srcs.models import CalibrationData, ErrorPattern, ErrorSignature, Investigation, PatternMatch, RootCausePattern


class StructuredStore(ABC):

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def store_investigation(self, investigation: Investigation) -> None: ...

    @abstractmethod
    async def get_investigation(self, investigation_id: str) -> Investigation | None: ...

    @abstractmethod
    async def get_recent_investigations(self, limit: int = 100, offset: int = 0) -> list[Investigation]: ...

    @abstractmethod
    async def count_investigations(self) -> int: ...

    @abstractmethod
    async def find_pattern(self, signature: ErrorSignature) -> PatternMatch | None: ...

    @abstractmethod
    async def get_pattern_by_id(self, pattern_id: str) -> ErrorPattern | None: ...

    @abstractmethod
    async def get_patterns_by_ids(self, pattern_ids: list[str]) -> list[ErrorPattern]: ...

    @abstractmethod
    async def get_pattern_root_causes(self, pattern_id: str) -> list[RootCausePattern]: ...

    @abstractmethod
    async def list_patterns(
        self, active_only: bool = True, limit: int = 50, offset: int = 0
    ) -> tuple[list[ErrorPattern], int]: ...

    @abstractmethod
    async def update_pattern_stats(self, pattern_id: str, correct: bool) -> None: ...

    @abstractmethod
    async def deactivate_pattern(self, pattern_id: str) -> bool: ...

    @abstractmethod
    async def get_pattern_statistics(self) -> dict[str, Any]: ...

    @abstractmethod
    async def create_pattern(
        self, pattern: ErrorPattern, root_cause_description: str, evidence_patterns: list[str]
    ) -> None: ...

    @abstractmethod
    async def update_pattern(
        self, pattern_id: str, times_seen: int, times_correct: int, times_incorrect: int, pattern_confidence: float
    ) -> None: ...

    @abstractmethod
    async def find_similar_patterns(self, signature: ErrorSignature, limit: int = 10) -> list[ErrorPattern]: ...

    @abstractmethod
    async def find_patterns_by_cause(self, cause: str, limit: int = 5) -> list[ErrorPattern]: ...

    @abstractmethod
    async def decay_old_patterns(self, threshold_date: str, decay_factor: float) -> int: ...

    @abstractmethod
    async def get_calibration(self, model: str, error_type: str | None = None) -> CalibrationData | None: ...

    @abstractmethod
    async def update_calibration(
        self, model: str, stated: float, actual: bool, error_type: str | None = None
    ) -> None: ...

    @abstractmethod
    async def get_all_calibrations(self) -> list[CalibrationData]: ...

    @abstractmethod
    async def record_feedback(
        self,
        investigation_id: str,
        was_correct: bool,
        actual_cause: str | None = None,
        feedback_notes: str | None = None,
        user_id: str | None = None,
        patterns_updated: list[str] | None = None,
        patterns_created: list[str] | None = None,
        feedback_source: str = "cli",
    ) -> str: ...

    @abstractmethod
    async def get_feedback_history(
        self, investigation_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def update_strategy_performance(
        self, strategy_name: str, was_correct: bool, confidence: float, rank: int, error_type: str | None = None
    ) -> None: ...

    @abstractmethod
    async def update_query_effectiveness(
        self,
        query_type: str,
        was_useful: bool,
        evidence_strength: float,
        result_count: int,
        error_type: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def get_strategy_performance(self, error_type: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_query_effectiveness(self, error_type: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_hypothesis_statistics(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_evidence_statistics(self) -> dict[str, Any]: ...

    @abstractmethod
    async def find_similar_investigations_by_signature(
        self, signature: ErrorSignature, limit: int = 100
    ) -> list[str]: ...

    @abstractmethod
    async def ensure_calibration_history_table(self) -> None: ...

    @abstractmethod
    async def record_calibration_snapshot(
        self,
        model: str,
        error_type: str | None,
        overall_bias: float,
        sample_size: int,
        overall_accuracy: float,
        buckets_json: str,
    ) -> None: ...

    @abstractmethod
    async def get_calibration_trend(
        self, model: str, error_type: str | None, limit: int = 30
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def clear_calibration_history(self, model: str | None = None) -> None: ...
