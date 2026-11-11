"""
File: pattern_tools.py
Purpose: Pattern-based evidence gathering tools.
Category: Utility
Author: artdaq team
Depends: knowledge, patterns, models
Exports: PatternTools
Complexity: Medium | Lines: 77
"""

import re
from srcs.knowledge import KnowledgeBase
from srcs.models import EvidenceItem, Log
from .base import logger, make_evidence, strength_from_confidence

class PatternTools:

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    async def lookup_error_pattern(self, error_message: str, function: str | None=None, component: str | None=None) -> list[EvidenceItem]:
        from srcs.knowledge.patterns import extract_signature
        results = []
        try:
            signature = extract_signature(function=function, message=error_message, level='ERROR', component=component)
            match = await self.kb.find_matching_pattern(signature)
            if match:
                pattern = match.pattern
                root_causes = await self.kb.get_pattern_root_causes(pattern.id)
                content_parts = [f'Known Pattern: {pattern.name}', f'Description: {pattern.description}', f'Confidence: {pattern.pattern_confidence:.2f}', f'Times seen: {pattern.times_seen}', f'Accuracy: {pattern.times_correct}/{pattern.times_seen}']
                if root_causes:
                    content_parts.append('Common root causes:')
                    for rc in root_causes[:5]:
                        content_parts.append(f'  - {rc.description} (freq: {rc.frequency:.2f})')
                results.append(make_evidence(evidence_type='pattern', content='\n'.join(content_parts), source=f'pattern:{pattern.id}', strength=strength_from_confidence(pattern.pattern_confidence)))
        except Exception as e:
            logger.warning('Failed to lookup error pattern: %s', e)
        return results

    async def get_historical_accuracy(self, pattern_id: str | None=None, error_type: str | None=None) -> list[EvidenceItem]:
        results = []
        try:
            if pattern_id:
                patterns = await self.kb.get_patterns_by_ids([pattern_id])
                if patterns:
                    pattern = patterns[0]
                    accuracy = pattern.times_correct / pattern.times_seen if pattern.times_seen > 0 else 0.0
                    results.append(make_evidence(evidence_type='accuracy_stats', content=f"Pattern '{pattern.name}' accuracy:\n  Correct: {pattern.times_correct}\n  Incorrect: {pattern.times_incorrect}\n  Accuracy: {accuracy:.1%}\n  Confidence: {pattern.pattern_confidence:.2f}", source=f'accuracy:{pattern_id}', strength='STRONG' if pattern.times_seen >= 10 else 'MODERATE'))
            else:
                stats = await self.kb.get_pattern_statistics()
                results.append(make_evidence(evidence_type='accuracy_stats', content=f"Overall pattern statistics:\n  Total patterns: {stats.get('total_patterns', 0)}\n  Active patterns: {stats.get('active_patterns', 0)}\n  Avg confidence: {stats.get('average_confidence', 0):.2f}\n  High accuracy: {stats.get('high_accuracy_patterns', 0)}\n  Low accuracy: {stats.get('low_accuracy_patterns', 0)}", source='accuracy:overall', strength='MODERATE'))
        except Exception as e:
            logger.warning('Failed to get historical accuracy: %s', e)
        return results

    async def get_discriminating_evidence(self, hypothesis_a: str, hypothesis_b: str, context_logs: list[Log]) -> list[EvidenceItem]:
        results = []
        terms_a = set(re.findall('\\b\\w{4,}\\b', hypothesis_a.lower()))
        terms_b = set(re.findall('\\b\\w{4,}\\b', hypothesis_b.lower()))
        unique_a = terms_a - terms_b
        unique_b = terms_b - terms_a
        logs_supporting_a = []
        logs_supporting_b = []
        logs_ambiguous = []
        for log in context_logs:
            log_text = log.message.lower()
            matches_a = sum((1 for term in unique_a if term in log_text))
            matches_b = sum((1 for term in unique_b if term in log_text))
            if matches_a > matches_b and matches_a > 0:
                logs_supporting_a.append((log, matches_a))
            elif matches_b > matches_a and matches_b > 0:
                logs_supporting_b.append((log, matches_b))
            elif matches_a > 0 or matches_b > 0:
                logs_ambiguous.append(log)
        if logs_supporting_a:
            content_parts = [f"Evidence supporting hypothesis A ('{hypothesis_a[:50]}...'):"]
            for log, score in sorted(logs_supporting_a, key=lambda x: -x[1])[:5]:
                content_parts.append(f'  [{log.level}] {log.message}')
            results.append(make_evidence(evidence_type='discriminating', content='\n'.join(content_parts), source='discriminating:hypothesis_a', strength='MODERATE'))
        if logs_supporting_b:
            content_parts = [f"Evidence supporting hypothesis B ('{hypothesis_b[:50]}...'):"]
            for log, score in sorted(logs_supporting_b, key=lambda x: -x[1])[:5]:
                content_parts.append(f'  [{log.level}] {log.message}')
            results.append(make_evidence(evidence_type='discriminating', content='\n'.join(content_parts), source='discriminating:hypothesis_b', strength='MODERATE'))
        if not results:
            results.append(make_evidence(evidence_type='discriminating', content=f"No clearly discriminating evidence found between hypotheses.\nHypothesis A unique terms: {', '.join(list(unique_a)[:10])}\nHypothesis B unique terms: {', '.join(list(unique_b)[:10])}\nConsider looking for:\n- Timing relationships between events\n- Error codes or specific identifiers\n- Component interactions", source='discriminating:none', strength='WEAK'))
        return results