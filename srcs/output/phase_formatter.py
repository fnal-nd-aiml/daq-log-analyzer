"""
File: phase_formatter.py
Purpose: Phase event formatter for CLI and Slack.
Category: Utility
Author: artdaq team
Depends: callbacks, persona
Exports: PhaseMetricsData, StructuredPhaseOutput, PhaseFormatter, get_phase_references
Complexity: Medium | Lines: 252
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any
from srcs.models.callbacks import PhaseEvent
from srcs.persona import PERSONAS, Persona
PHASE_REFERENCES: dict[int, list[int]] = {1: [0], 2: [1], 3: [2], 4: [3, 1], 5: [4, 2], 6: [5, 1]}
PHASE_TO_PERSONA: dict[int, str] = {-1: 'Chronicler', 0: 'Archivist', 1: 'Theorist', 2: 'Detective', 3: 'Logician', 4: 'Skeptic', 5: 'Judge', 6: 'Synthesizer', 7: 'Learner'}

@dataclass
class PhaseMetricsData:
    count: int = 0
    strong: int = 0
    moderate: int = 0
    weak: int = 0
    top_score: float = 0.0
    rounds: int = 0
    current_round: int = 0
    duration_ms: int = 0
    challenges_high: int = 0
    challenges_medium: int = 0
    challenges_low: int = 0

@dataclass
class StructuredPhaseOutput:
    phase: int
    persona_name: str
    event_type: str
    status: str
    summary_text: str
    metrics: PhaseMetricsData = field(default_factory=PhaseMetricsData)
    references: list[str] = field(default_factory=list)
    item_data: dict[str, Any] = field(default_factory=dict)

class PhaseFormatter:

    def format_event(self, event: PhaseEvent) -> str | None:
        if event.phase not in PERSONAS:
            return None
        persona = PERSONAS[event.phase]
        if event.event_type == 'start':
            return self._format_start(persona)
        elif event.event_type == 'item':
            message = event.message or self._format_item_message(event.data)
            return f'> "{message}"'
        elif event.event_type == 'progress':
            return f"_{event.message or '...'}_"
        elif event.event_type == 'complete':
            summary = self._format_completion_summary(event.phase, event.data)
            if summary:
                return f'**"{summary}"**'
        elif event.event_type == 'error':
            message = event.message or event.data.get('error', 'Unknown error')
            return f'**Error:** {message}'
        return None

    def _format_start(self, persona: Persona) -> str:
        return f'**{persona.name}** - {persona.role}\n_{persona.thinking_phrase}_'

    def _format_item_message(self, data: dict[str, Any]) -> str:
        item_type = data.get('type', 'item')
        if item_type == 'pattern':
            name = data.get('name', 'unknown')
            times = data.get('times_seen', 0)
            return f"I found a pattern: '{name}' - seen {times} times"
        elif item_type == 'similar_case':
            similarity = data.get('similarity', 0)
            return f'Similar case found ({similarity:.0%} similar)'
        elif item_type == 'hypothesis':
            desc = data.get('description', 'unknown')[:60]
            conf = data.get('prior', 0)
            source = data.get('source', 'unknown')
            return f'What if... {desc}... (confidence: {conf:.0%}, from {source})'
        elif item_type == 'evidence':
            strength = data.get('strength', 'UNKNOWN')
            content = data.get('content', '')[:60] if 'content' in data else ''
            if content:
                return f'Found {strength} evidence: {content}...'
            return f'Found {strength} evidence'
        elif item_type == 'chain':
            hyp = data.get('hypothesis', '')[:50]
            steps = data.get('steps', 0)
            return f'Built chain ({steps} steps) for: {hyp}...'
        elif item_type == 'challenge':
            severity = data.get('severity', 'UNKNOWN')
            return f'[{severity}] Challenge raised'
        elif item_type == 'learned_pattern':
            name = data.get('name', 'unknown')
            return f'Learned pattern: {name}'
        elif item_type == 'source_location':
            return self._format_source_location_item(data)
        return str(data)

    def _format_source_location_item(self, data: dict[str, Any]) -> str:
        file_path = data.get('file_path', 'unknown')
        line = data.get('line_number', '?')
        func = data.get('function_name', '')
        score = data.get('match_score', 0)
        is_log = data.get('is_log_statement', False)
        filename = os.path.basename(file_path)
        loc_str = f'{filename}:{line}'
        if func:
            loc_str += f' in {func}()'
        if is_log:
            loc_str += ' [LOG]'
        result = f'Found source: {loc_str} (score: {score:.0%})'
        sig = data.get('function_signature')
        if sig:
            result += f'\n    Signature: {sig}'
        class_name = data.get('class_name')
        if class_name:
            result += f'\n    Class: {class_name}'
        callers = data.get('callers') or []
        callees = data.get('callees') or []
        if callers:
            caller_names = [c.get('name', '?') for c in callers[:3]]
            result += f"\n    Called by: {', '.join(caller_names)}"
            if len(callers) > 3:
                result += f' (+{len(callers) - 3} more)'
        if callees:
            callee_names = [c.get('name', '?') for c in callees[:3]]
            result += f"\n    Calls: {', '.join(callee_names)}"
            if len(callees) > 3:
                result += f' (+{len(callees) - 3} more)'
        summary = data.get('function_summary')
        if summary:
            summary_short = summary[:100] + '...' if len(summary) > 100 else summary
            result += f'\n    Summary: {summary_short}'
        return result

    def _format_completion_summary(self, phase: int, data: dict[str, Any]) -> str:
        if phase == 0:
            patterns = data.get('patterns_found', 0)
            cases = data.get('similar_cases', 0)
            sources = data.get('source_locations', 0)
            parts = []
            if patterns:
                parts.append(f'{patterns} patterns')
            if cases:
                parts.append(f'{cases} similar cases')
            if sources:
                parts.append(f'{sources} source locations')
            if not parts:
                return 'No prior knowledge found'
            return 'Found ' + ', '.join(parts)
        elif phase == 1:
            count = data.get('hypotheses_count', 0)
            return f'Generated {count} hypotheses'
        elif phase == 2:
            count = data.get('evidence_count', 0)
            return f'Collected {count} pieces of evidence'
        elif phase == 3:
            count = data.get('chains_count', data.get('causal_chains_count', 0))
            return f'Built {count} causal chains'
        elif phase == 4:
            count = data.get('challenges_count', 0)
            return f'Raised {count} challenges'
        elif phase == 5:
            outcome = data.get('outcome', 'unknown')
            return f'Assessment: {outcome}'
        elif phase == 6:
            outcome = data.get('outcome', 'unknown')
            confidence = data.get('confidence', 0)
            if confidence:
                return f'Conclusion: {outcome} (confidence: {confidence:.0%})'
            return f'Conclusion: {outcome}'
        elif phase == 7:
            count = data.get('patterns_learned', 0)
            if count > 0:
                return f'Learned {count} new patterns'
            return 'No new patterns learned'
        return ''

    def format_event_structured(self, event: PhaseEvent) -> StructuredPhaseOutput | None:
        if event.phase not in PERSONAS:
            return None
        persona = PERSONAS[event.phase]
        persona_name = PHASE_TO_PERSONA.get(event.phase, 'Unknown')
        ref_phases = PHASE_REFERENCES.get(event.phase, [])
        references = [PHASE_TO_PERSONA[p] for p in ref_phases if p in PHASE_TO_PERSONA]
        if event.event_type == 'start':
            status = 'in_progress'
            summary_text = persona.thinking_phrase
        elif event.event_type == 'item':
            status = 'in_progress'
            summary_text = event.message or self._format_item_message(event.data)
        elif event.event_type == 'progress':
            status = 'in_progress'
            summary_text = event.message or '...'
        elif event.event_type == 'complete':
            status = 'complete'
            summary_text = self._format_completion_summary(event.phase, event.data)
        elif event.event_type == 'error':
            status = 'error'
            summary_text = event.message or event.data.get('error', 'Unknown error')
        else:
            status = 'pending'
            summary_text = ''
        metrics = self._extract_metrics(event)
        return StructuredPhaseOutput(phase=event.phase, persona_name=persona_name, event_type=event.event_type, status=status, summary_text=summary_text, metrics=metrics, references=references, item_data=event.data)

    def _extract_metrics(self, event: PhaseEvent) -> PhaseMetricsData:
        metrics = PhaseMetricsData()
        data = event.data
        phase = event.phase
        if event.event_type == 'item':
            item_type = data.get('type', '')
            if item_type == 'hypothesis':
                metrics.count = 1
                metrics.top_score = data.get('prior', 0)
            elif item_type == 'evidence':
                metrics.count = 1
                strength = data.get('strength', 'WEAK')
                if strength == 'STRONG':
                    metrics.strong = 1
                elif strength == 'MODERATE':
                    metrics.moderate = 1
                else:
                    metrics.weak = 1
            elif item_type == 'challenge':
                metrics.count = 1
                severity = data.get('severity', 'MEDIUM')
                if severity == 'HIGH':
                    metrics.challenges_high = 1
                elif severity == 'MEDIUM':
                    metrics.challenges_medium = 1
                else:
                    metrics.challenges_low = 1
            elif item_type == 'round':
                metrics.current_round = data.get('round', 0)
                metrics.rounds = data.get('total', 0)
        elif event.event_type == 'complete':
            if phase == 0:
                metrics.count = data.get('similar_cases', 0)
                metrics.strong = data.get('source_locations', 0)
                metrics.moderate = data.get('patterns_found', 0)
            elif phase == 1:
                metrics.count = data.get('hypotheses_count', 0)
            elif phase == 2:
                metrics.count = data.get('evidence_count', 0)
            elif phase == 3:
                metrics.count = data.get('chains_count', data.get('causal_chains_count', 0))
                metrics.strong = data.get('evidence_cited', 0)
            elif phase == 4:
                metrics.count = data.get('challenges_count', 0)
            elif phase == 6:
                metrics.top_score = data.get('confidence', 0)
        return metrics

def get_phase_references(phase: int) -> list[str]:
    ref_phases = PHASE_REFERENCES.get(phase, [])
    return [PHASE_TO_PERSONA[p] for p in ref_phases if p in PHASE_TO_PERSONA]