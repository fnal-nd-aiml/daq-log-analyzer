"""
File: investigation_tools.py
Purpose: Investigation tools for log search and similar case lookup.
Category: Utility
Author: artdaq team
Depends: knowledge, models
Exports: InvestigationTools
Complexity: Medium | Lines: 149
"""

from datetime import datetime, timedelta
from srcs.knowledge import KnowledgeBase
from srcs.models import EvidenceItem, Log
from .base import logger, make_evidence, make_log_evidence, strength_from_confidence, strength_from_log_level


class InvestigationTools:

    def __init__(self, kb: KnowledgeBase, context_logs: list[Log]):
        self.kb = kb
        self.context_logs = context_logs

    async def search_logs(
        self, pattern: str, component: str | None = None, level: str | None = None
    ) -> list[EvidenceItem]:
        results = []
        pattern_lower = pattern.lower()
        for log in self.context_logs:
            if pattern_lower not in log.message.lower():
                continue
            if component is not None and log.component != component:
                continue
            if level is not None and log.level != level:
                continue
            strength = strength_from_log_level(log.level)
            if pattern_lower in log.message.lower()[:50]:
                strength = "MODERATE"
            results.append(
                make_evidence(
                    evidence_type="log",
                    content=f"[{log.timestamp}] {log.level} {log.component}: {log.message}",
                    source=f"log_search:{pattern}",
                    strength=strength,
                )
            )
        return results

    async def get_logs_in_window(
        self, start_offset_seconds: float, end_offset_seconds: float, reference_log: Log
    ) -> list[EvidenceItem]:
        start = reference_log.timestamp - timedelta(seconds=start_offset_seconds)
        end = reference_log.timestamp + timedelta(seconds=end_offset_seconds)
        results = []
        for log in self.context_logs:
            if start <= log.timestamp <= end:
                item = make_log_evidence(log, source=f"time_window:{start_offset_seconds}-{end_offset_seconds}s")
                results.append(item)
        return results

    async def get_logs_by_component(self, component: str, limit: int = 20) -> list[EvidenceItem]:
        results = []
        for log in self.context_logs:
            if log.component == component:
                results.append(
                    make_evidence(
                        evidence_type="log",
                        content=f"[{log.timestamp}] {log.level}: {log.message}",
                        source=f"component:{component}",
                        strength=strength_from_log_level(log.level),
                    )
                )
                if len(results) >= limit:
                    break
        return results

    async def lookup_similar_cases(self, description: str, n: int = 5) -> list[EvidenceItem]:
        query_log = Log(timestamp=datetime.now(), level="ERROR", component="unknown", message=description)
        try:
            similar = await self.kb.find_similar_investigations(query_log, self.context_logs, n)
        except Exception as e:
            logger.warning("Failed to lookup similar cases: %s", e)
            return []
        results = []
        for case in similar:
            strength = strength_from_confidence(case.similarity_score)
            if case.was_correct and case.similarity_score > 0.7:
                strength = "STRONG"
            content_parts = [f"Similar case {case.investigation_id}"]
            if case.root_cause:
                content_parts.append(f"Root cause: {case.root_cause}")
            if case.outcome:
                content_parts.append(f"Outcome: {case.outcome}")
            if case.was_correct is not None:
                content_parts.append(f"Verified: {('Yes' if case.was_correct else 'No')}")
            results.append(
                make_evidence(
                    evidence_type="similar_case",
                    content=" | ".join(content_parts),
                    source=f"similar_case:{case.investigation_id}",
                    strength=strength,
                )
            )
        return results

    async def count_by_level(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for log in self.context_logs:
            counts[log.level] = counts.get(log.level, 0) + 1
        return counts

    async def count_by_component(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for log in self.context_logs:
            counts[log.component] = counts.get(log.component, 0) + 1
        return counts

    async def find_sequences(self, patterns: list[str], max_gap_seconds: float = 5.0) -> list[list[EvidenceItem]]:
        if not patterns:
            return []
        sequences = []
        current_sequence = []
        current_pattern_idx = 0
        last_match_time = None
        for log in sorted(self.context_logs, key=lambda x: x.timestamp):
            pattern = patterns[current_pattern_idx].lower()
            if pattern in log.message.lower():
                if last_match_time and current_pattern_idx > 0:
                    gap = (log.timestamp - last_match_time).total_seconds()
                    if gap > max_gap_seconds:
                        current_sequence = []
                        current_pattern_idx = 0
                        if pattern in log.message.lower():
                            current_sequence.append(
                                make_evidence(
                                    evidence_type="log",
                                    content=f"[{log.timestamp}] {log.message}",
                                    source=f"sequence:{current_pattern_idx}",
                                    strength="MODERATE",
                                )
                            )
                            current_pattern_idx = 1
                            last_match_time = log.timestamp
                        continue
                current_sequence.append(
                    make_evidence(
                        evidence_type="log",
                        content=f"[{log.timestamp}] {log.message}",
                        source=f"sequence:{current_pattern_idx}",
                        strength="MODERATE",
                    )
                )
                current_pattern_idx += 1
                last_match_time = log.timestamp
                if current_pattern_idx >= len(patterns):
                    sequences.append(current_sequence)
                    current_sequence = []
                    current_pattern_idx = 0
                    last_match_time = None
        return sequences
