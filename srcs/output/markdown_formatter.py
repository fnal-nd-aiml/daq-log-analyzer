"""
File: markdown_formatter.py
Purpose: Unified markdown formatter for all output targets.
Category: Utility
Author: artdaq team
Depends: models, callbacks, question, persona
Exports: MarkdownFormatter
Complexity: Medium | Lines: 575
"""

import json
import os
from typing import Any
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent, PhaseEvent
from srcs.models import InvestigationOutcome, InvestigationResult
from srcs.models.question import PanelResponse
from srcs.persona import PERSONAS, Persona

class MarkdownFormatter:

    def __init__(self, full_output: bool=False):
        self.full_output = full_output
        self._last_system_prompt: str | None = None

    def format_event(self, event: PhaseEvent | LLMEvent | DataRetrievalEvent) -> str | None:
        if isinstance(event, PhaseEvent):
            return self.format_phase_event(event)
        elif isinstance(event, LLMEvent):
            return self.format_llm_event(event)
        elif isinstance(event, DataRetrievalEvent):
            return self.format_data_event(event)
        return None

    def format_phase_event(self, event: PhaseEvent) -> str | None:
        if event.event_type == 'start':
            return self._format_phase_start(event)
        elif event.event_type == 'item':
            return self._format_phase_item(event)
        elif event.event_type == 'progress':
            return self._format_phase_progress(event)
        elif event.event_type == 'complete':
            return self._format_phase_complete(event)
        elif event.event_type == 'error':
            return self._format_phase_error(event)
        return None

    def _get_persona(self, phase: int) -> Persona:
        if phase in PERSONAS:
            return PERSONAS[phase]
        return Persona(phase=phase, name='Assistant', role=f'Phase {phase}', color='white', thinking_phrase='Processing...', prompt_key=None, uses_llm=False, description='Unknown phase')

    def _format_phase_start(self, event: PhaseEvent) -> str:
        persona = self._get_persona(event.phase)
        lines = ['', '---', f'## {persona.name} - {persona.role}', '', f'*{persona.thinking_phrase}*']
        return '\n'.join(lines)

    def _format_phase_item(self, event: PhaseEvent) -> str:
        message = event.message or self._format_item_message(event.data)
        return f'> "{message}"'

    def _format_phase_progress(self, event: PhaseEvent) -> str:
        message = event.message or '...'
        return f'*{message}*'

    def _format_phase_complete(self, event: PhaseEvent) -> str | None:
        summary = self._format_completion_summary(event.phase, event.data)
        if summary:
            return f'**"{summary}"**'
        return None

    def _format_phase_error(self, event: PhaseEvent) -> str:
        message = event.message or event.data.get('error', 'Unknown error')
        return f'**Error:** {message}'

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

    def format_llm_event(self, event: LLMEvent) -> str:
        if event.event_type == 'request':
            return self._format_llm_request(event)
        elif event.event_type == 'response':
            return self._format_llm_response(event)
        return ''

    def _get_phase_label(self, phase: int) -> str:
        if phase in PERSONAS:
            return f'Phase {phase}: {PERSONAS[phase].name}'
        return f'Phase {phase}: Agent'

    def _format_llm_request(self, event: LLMEvent) -> str:
        lines: list[str] = []
        if event.system_prompt and event.system_prompt != self._last_system_prompt:
            lines.extend(self._format_system_context(event.system_prompt))
            self._last_system_prompt = event.system_prompt
        phase_label = self._get_phase_label(event.phase)
        lines.extend(['', '---', f'### -> QUERY TO LLM | {phase_label}', ''])
        if event.response_model:
            lines.append(f'**Expected Response:** {event.response_model}')
            lines.append('')
        lines.extend(self._format_prompt_content(event.user_prompt))
        lines.append('')
        return '\n'.join(lines)

    def _format_system_context(self, system_prompt: str) -> list[str]:
        lines = ['', '===', '### SYSTEM CONTEXT', '']
        if self.full_output:
            lines.extend(system_prompt.split('\n'))
        else:
            prompt_lines = system_prompt.split('\n')
            for line in prompt_lines[:30]:
                line = line.strip()
                if not line:
                    continue
                if len(line) > 100:
                    line = line[:97] + '...'
                lines.append(line)
            if len(prompt_lines) > 30:
                lines.append(f'... ({len(prompt_lines) - 30} more lines)')
        lines.extend(['', '===', ''])
        return lines

    def _format_prompt_content(self, prompt: str | None) -> list[str]:
        if not prompt:
            return []
        lines: list[str] = []
        if self.full_output:
            lines.append('**Complete Query:**')
            lines.extend(prompt.split('\n'))
        else:
            prompt_lines = prompt.split('\n')
            for line in prompt_lines[:15]:
                display_line = line[:120] + '...' if len(line) > 120 else line
                lines.append(display_line)
            if len(prompt_lines) > 15:
                lines.append(f'... ({len(prompt_lines) - 15} more lines)')
        return lines

    def _format_llm_response(self, event: LLMEvent) -> str:
        phase_label = self._get_phase_label(event.phase)
        lines = ['', '---', f'### <- RESPONSE FROM LLM | {phase_label}', '']
        if not event.response:
            lines.append('*No response*')
            return '\n'.join(lines)
        if event.response_model:
            lines.extend(self._format_structured_response(event.response, event.response_model))
        else:
            lines.extend(self._format_text_response(event.response))
        lines.append('')
        return '\n'.join(lines)

    def _format_structured_response(self, response: str, model_name: str) -> list[str]:
        lines: list[str] = []
        if self.full_output:
            lines.append('**Complete Response:**')
            try:
                data = json.loads(response)
                formatted = json.dumps(data, indent=2)
                lines.append('```json')
                lines.extend(formatted.split('\n'))
                lines.append('```')
            except json.JSONDecodeError:
                lines.extend(response.split('\n'))
            return lines
        try:
            data = json.loads(response)
            lines.extend(self._format_model_data(data, model_name))
        except json.JSONDecodeError:
            lines.extend(self._format_text_response(response))
        return lines

    def _format_model_data(self, data: dict, model_name: str) -> list[str]:
        if 'hypotheses' in data:
            return self._format_hypotheses_response(data)
        elif 'queries' in data:
            return self._format_queries_response(data)
        elif 'chains' in data or 'causal_chains' in data:
            return self._format_chains_response(data)
        elif 'challenges' in data:
            return self._format_challenges_response(data)
        else:
            return self._format_generic_structured(data, model_name)

    def _format_hypotheses_response(self, data: dict) -> list[str]:
        hypotheses = data.get('hypotheses', [])
        lines = [f'Generated {len(hypotheses)} hypotheses:', '']
        if not hypotheses:
            lines.append('*No hypotheses generated*')
            return lines
        max_items = len(hypotheses) if self.full_output else 10
        for i, hyp in enumerate(hypotheses[:max_items], 1):
            desc = hyp.get('description', 'Unknown')
            if not self.full_output and len(desc) > 60:
                desc = desc[:60] + '...'
            category = hyp.get('category', 'Unknown')
            prior = hyp.get('prior', 0)
            prior_label = self._format_prior(prior)
            lines.append(f'{i}. {desc} | {category} | {prior_label}')
        if not self.full_output and len(hypotheses) > 10:
            lines.append(f'... and {len(hypotheses) - 10} more')
        return lines

    def _format_queries_response(self, data: dict) -> list[str]:
        queries = data.get('queries', [])
        lines = [f'Generated {len(queries)} evidence queries:', '']
        max_queries = len(queries) if self.full_output else 5
        for i, query in enumerate(queries[:max_queries], 1):
            query_type = query.get('query_type', 'Unknown')
            target = query.get('query', query.get('query_template', 'Unknown'))
            purpose = query.get('expected_if_true', query.get('expected_result', ''))
            if not self.full_output:
                target = target[:60] + '...' if len(target) > 60 else target
                purpose = purpose[:60] + '...' if len(purpose) > 60 else purpose
            lines.append(f'{i}. [{query_type}] {target}')
            if purpose:
                lines.append(f'   *Purpose: {purpose}*')
        return lines

    def _format_chains_response(self, data: dict) -> list[str]:
        chains = data.get('chains', data.get('causal_chains', []))
        lines = [f'Built {len(chains)} causal chains:', '']
        max_chains = len(chains) if self.full_output else 3
        for i, chain in enumerate(chains[:max_chains], 1):
            hyp = chain.get('hypothesis', chain.get('root_cause', 'Unknown'))
            if not self.full_output and len(hyp) > 50:
                hyp = hyp[:50] + '...'
            steps = chain.get('steps', [])
            confidence = chain.get('confidence', 0)
            lines.append(f'**Chain {i}:** {hyp}')
            lines.append(f'Steps: {len(steps)}, Confidence: {confidence:.0%}')
            max_steps = len(steps) if self.full_output else 3
            for j, step in enumerate(steps[:max_steps], 1):
                cause = step.get('cause', '?')
                effect = step.get('effect', '?')
                if not self.full_output:
                    cause = cause[:30] + '...' if len(cause) > 30 else cause
                    effect = effect[:30] + '...' if len(effect) > 30 else effect
                lines.append(f'   {j}. {cause} -> {effect}')
            lines.append('')
        return lines

    def _format_challenges_response(self, data: dict) -> list[str]:
        challenges = data.get('challenges', [])
        lines = [f'Raised {len(challenges)} challenges:', '']
        max_challenges = len(challenges) if self.full_output else 5
        for i, challenge in enumerate(challenges[:max_challenges], 1):
            severity = challenge.get('severity', 'UNKNOWN')
            desc = challenge.get('description', challenge.get('challenge', 'Unknown'))
            target = challenge.get('target_hypothesis', '')
            if not self.full_output:
                desc = desc[:70] + '...' if len(desc) > 70 else desc
                target = target[:30] + '...' if len(target) > 30 else target
            lines.append(f'{i}. **[{severity}]** {desc}')
            if target:
                lines.append(f'   *Challenges: {target}*')
        return lines

    def _format_generic_structured(self, data: dict, model_name: str) -> list[str]:
        lines = [f'Response ({model_name}):', '']
        items = list(data.items())
        max_items = len(items) if self.full_output else 10
        for key, value in items[:max_items]:
            if isinstance(value, list):
                if self.full_output:
                    lines.append(f'**{key}:**')
                    for item in value:
                        lines.append(f'  - {item}')
                else:
                    lines.append(f'**{key}:** [{len(value)} items]')
            elif isinstance(value, dict):
                if self.full_output:
                    lines.append(f'**{key}:**')
                    for k, v in value.items():
                        lines.append(f'  {k}: {v}')
                else:
                    lines.append(f'**{key}:** {{...}}')
            elif isinstance(value, str) and len(value) > 80 and (not self.full_output):
                lines.append(f'**{key}:** {value[:80]}...')
            else:
                lines.append(f'**{key}:** {value}')
        return lines

    def _format_text_response(self, response: str) -> list[str]:
        lines: list[str] = []
        response_lines = response.split('\n')
        max_lines = len(response_lines) if self.full_output else 20
        for line in response_lines[:max_lines]:
            if not self.full_output and len(line) > 120:
                line = line[:120] + '...'
            lines.append(line)
        if not self.full_output and len(response_lines) > 20:
            lines.append(f'... ({len(response_lines) - 20} more lines)')
        return lines

    def _format_prior(self, prior: float) -> str:
        if prior >= 0.7:
            return f'High ({prior:.2f})'
        elif prior >= 0.4:
            return f'Medium ({prior:.2f})'
        else:
            return f'Low ({prior:.2f})'

    def format_data_event(self, event: DataRetrievalEvent) -> str:
        if event.event_type == 'query':
            return self._format_data_query(event)
        elif event.event_type == 'result':
            return self._format_data_result(event)
        return ''

    def _format_data_query(self, event: DataRetrievalEvent) -> str:
        if event.source == 'sqlite':
            header_type = 'PATTERN DATABASE QUERY'
        elif event.source == 'chromadb':
            header_type = 'SEMANTIC SEARCH'
        else:
            header_type = 'DATA QUERY'
        phase_label = self._get_phase_label(event.phase)
        lines = ['', '---', f'### -> {header_type} | {phase_label}', '']
        operation_readable = event.operation.replace('_', ' ').title()
        lines.append(f'**Operation:** {operation_readable}')
        if event.query_params:
            lines.append('')
            for key, value in event.query_params.items():
                key_readable = key.replace('_', ' ').title()
                if isinstance(value, str) and len(value) > 80 and (not self.full_output):
                    value = value[:77] + '...'
                lines.append(f'**{key_readable}:** {value}')
        lines.append('')
        return '\n'.join(lines)

    def _format_data_result(self, event: DataRetrievalEvent) -> str:
        if event.source == 'sqlite':
            header_type = 'PATTERN DATABASE RESULT'
        elif event.source == 'chromadb':
            header_type = 'SEMANTIC SEARCH RESULTS'
        else:
            header_type = 'DATA RESULT'
        phase_label = self._get_phase_label(event.phase)
        lines = ['', '---', f'### <- {header_type} | {phase_label}', '']
        if event.result_count is not None:
            count_word = 'result' if event.result_count == 1 else 'results'
            if event.result_count == 0:
                lines.append(f'*No {count_word} found*')
            else:
                lines.append(f'**Found:** {event.result_count} {count_word}')
        if event.result_summary:
            lines.append('')
            lines.extend(event.result_summary.split('\n'))
        lines.append('')
        return '\n'.join(lines)

    def format_investigation_result(self, result: InvestigationResult, verbose: bool=False) -> str:
        lines: list[str] = []
        emoji = self._get_outcome_emoji(result.outcome)
        description = self._get_outcome_description(result.outcome)
        lines.extend([f'# {emoji} {result.outcome.value}', '', f'*{description}*', '', '---'])
        if result.outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
            lines.extend(self._format_confident_result(result, verbose))
        elif result.outcome == InvestigationOutcome.UNCERTAIN:
            lines.extend(self._format_uncertain_result(result))
        elif result.outcome == InvestigationOutcome.INSUFFICIENT:
            lines.extend(self._format_insufficient_result(result))
        elif result.outcome == InvestigationOutcome.CONTRADICTORY:
            lines.extend(self._format_contradictory_result(result))
        lines.extend(['', '---', f'*Completed in {result.duration_seconds:.1f}s | Investigation ID: `{result.investigation_id}`*'])
        return '\n'.join(lines)

    def _get_outcome_emoji(self, outcome: InvestigationOutcome) -> str:
        emoji_map = {InvestigationOutcome.CONFIDENT: 'OK', InvestigationOutcome.PROBABLE: '=', InvestigationOutcome.UNCERTAIN: '?', InvestigationOutcome.INSUFFICIENT: 'X', InvestigationOutcome.CONTRADICTORY: '!'}
        return emoji_map.get(outcome, '?')

    def _get_outcome_description(self, outcome: InvestigationOutcome) -> str:
        desc_map = {InvestigationOutcome.CONFIDENT: 'High confidence in root cause', InvestigationOutcome.PROBABLE: 'Likely root cause identified', InvestigationOutcome.UNCERTAIN: 'Multiple hypotheses remain viable', InvestigationOutcome.INSUFFICIENT: 'Insufficient evidence for conclusion', InvestigationOutcome.CONTRADICTORY: 'Evidence contradicts itself'}
        return desc_map.get(outcome, '')

    def _format_confident_result(self, result: InvestigationResult, verbose: bool) -> list[str]:
        lines: list[str] = []
        if result.root_cause:
            rc = result.root_cause
            confidence = rc.confidence
            lines.extend(['', '## Root Cause', '', rc.root_cause, '', f'**Confidence:** {confidence.calibrated:.0%} (raw: {confidence.raw:.0%})', ''])
            if rc.code_location:
                lines.append(f'**Error Location:** `{rc.code_location}`')
                lines.append('')
            if rc.code_snippet:
                lines.extend(['**Code Context:**', '```cpp', rc.code_snippet, '```', ''])
            if rc.sub_causes:
                lines.extend(['## Ranked Causes', ''])
                for i, sc in enumerate(rc.sub_causes[:6], 1):
                    lines.append(f'{i}. {sc.description[:60]}... ({sc.probability:.0%})')
                lines.append('')
            if rc.debugging_steps:
                lines.extend(['## Debugging Steps', ''])
                for i, step in enumerate(rc.debugging_steps[:7], 1):
                    lines.append(f'{i}. {step}')
                lines.append('')
            if verbose and rc.key_files:
                lines.extend(['## Key Files', ''])
                for kf in rc.key_files[:5]:
                    lines.append(f'- `{kf.file_path}` - {kf.purpose}')
                lines.append('')
        if result.recommendations:
            lines.extend(['## Recommendations', ''])
            for rec in result.recommendations:
                lines.append(f'- {rec}')
            lines.append('')
        if verbose and result.alternatives:
            lines.extend(['## Alternative Hypotheses', ''])
            for alt in result.alternatives[:3]:
                lines.append(f'- {alt.description[:80]}... ({alt.score:.0%})')
            lines.append('')
        return lines

    def _format_uncertain_result(self, result: InvestigationResult) -> list[str]:
        lines = ['', '*Multiple hypotheses remain viable. More evidence is needed.*', '']
        if result.viable_hypotheses:
            lines.extend(['## Viable Hypotheses', ''])
            for h in result.viable_hypotheses:
                desc = h.description[:70] + '...' if len(h.description) > 70 else h.description
                lines.append(f'- {desc} ({h.score:.0%})')
            lines.append('')
        if result.discrimination_needed:
            lines.extend(['## To Discriminate', ''])
            for d in result.discrimination_needed:
                lines.append(f'- {d}')
            lines.append('')
        return lines

    def _format_insufficient_result(self, result: InvestigationResult) -> list[str]:
        reason = result.insufficient_reason or 'Insufficient evidence to reach conclusion'
        lines = ['', f'*{reason}*', '']
        if result.missing_evidence:
            lines.extend(['## Missing Evidence', ''])
            for m in result.missing_evidence:
                lines.append(f'- {m}')
            lines.append('')
        if result.viable_hypotheses:
            lines.extend(['## Best Guesses (unconfirmed)', ''])
            for h in result.viable_hypotheses[:3]:
                lines.append(f'- {h.description[:70]}... ({h.score:.0%})')
            lines.append('')
        return lines

    def _format_contradictory_result(self, result: InvestigationResult) -> list[str]:
        lines = ['', '*Evidence contradicts itself - multiple incompatible explanations found.*', '']
        if result.insufficient_reason:
            lines.append(f'*{result.insufficient_reason}*')
            lines.append('')
        if result.viable_hypotheses:
            lines.extend(['## Conflicting Hypotheses', ''])
            for h in result.viable_hypotheses:
                lines.append(f'- {h.description[:70]}... ({h.score:.0%})')
            lines.append('')
        return lines

    def format_panel_response(self, response: PanelResponse) -> str:
        if response.confidence >= 0.7:
            conf_text = 'High confidence'
        elif response.confidence >= 0.5:
            conf_text = 'Moderate confidence'
        else:
            conf_text = 'Low confidence'
        lines = [f'# Answer ({conf_text}: {response.confidence:.0%})', '', response.answer, '']
        if response.key_points:
            lines.extend(['## Key Points', ''])
            for point in response.key_points:
                lines.append(f'- {point}')
            lines.append('')
        if response.caveats:
            lines.extend(['## Caveats', ''])
            for caveat in response.caveats:
                lines.append(f'- {caveat}')
            lines.append('')
        lines.append(f'*Question ID: `{response.question_id}`*')
        return '\n'.join(lines)