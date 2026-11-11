"""
File: strategy.py
Purpose: Evidence seeking strategy and query effectiveness tracking.
Category: Utility
Author: artdaq team
Depends: None
Exports: QueryEffectiveness, EvidenceStrategy
Complexity: Medium | Lines: 69
"""

import logging
from dataclasses import dataclass, field
logger = logging.getLogger(__name__)

@dataclass
class QueryEffectiveness:
    query_type: str
    attempts: int = 0
    successes: int = 0
    consecutive_failures: int = 0
    consecutive_failure_limit: int = 3
    min_success_rate: float = 0.1
    min_attempts_for_rate: int = 5

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts > 0 else 0.0

    @property
    def is_effective(self) -> bool:
        if self.consecutive_failures >= self.consecutive_failure_limit:
            return False
        if self.attempts >= self.min_attempts_for_rate and self.success_rate < self.min_success_rate:
            return False
        return True

@dataclass
class EvidenceStrategy:
    has_context_logs: bool = True
    context_log_count: int = 0
    query_stats: dict[str, QueryEffectiveness] = field(default_factory=dict)
    mode: str = 'balanced'
    consecutive_failure_limit: int = 3
    min_success_rate: float = 0.1
    min_attempts_for_rate: int = 5
    LOG_QUERY_TYPES = {'log_search', 'component_logs', 'time_window'}
    CODE_QUERY_TYPES = {'function_lookup', 'class_lookup', 'code_search', 'log_source'}

    def record_query_result(self, query_type: str, found: bool) -> None:
        if query_type not in self.query_stats:
            self.query_stats[query_type] = QueryEffectiveness(query_type=query_type, consecutive_failure_limit=self.consecutive_failure_limit, min_success_rate=self.min_success_rate, min_attempts_for_rate=self.min_attempts_for_rate)
        stats = self.query_stats[query_type]
        stats.attempts += 1
        if found:
            stats.successes += 1
            stats.consecutive_failures = 0
        else:
            stats.consecutive_failures += 1
        self._update_strategy()

    def _update_strategy(self) -> None:
        log_failures = sum((1 for qt in self.LOG_QUERY_TYPES if qt in self.query_stats and (not self.query_stats[qt].is_effective)))
        if log_failures >= 2 or not self.has_context_logs:
            self.mode = 'code_centric'
            logger.debug('Pivoting to code-centric evidence strategy')

    def should_skip_query(self, query_type: str) -> bool:
        if query_type in self.query_stats:
            return not self.query_stats[query_type].is_effective
        if self.mode == 'code_centric' and query_type in self.LOG_QUERY_TYPES:
            return True
        return False

    def prioritize_queries(self, queries: list[dict]) -> list[dict]:
        if self.mode == 'code_centric':
            code_queries = [q for q in queries if q.get('query_type') in self.CODE_QUERY_TYPES]
            other_queries = [q for q in queries if q.get('query_type') not in self.CODE_QUERY_TYPES]
            return code_queries + other_queries
        return queries