"""
File: llm_display.py
Purpose: Rich console display for LLM and data retrieval logging.
Category: Utility
Author: artdaq team
Depends: callbacks, persona, rich
Exports: LLMLoggingDisplay
Complexity: Medium | Lines: 352
"""

import json
import re
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from srcs.models.callbacks import DataRetrievalEvent, LLMEvent
from srcs.persona import PERSONAS

class LLMLoggingDisplay:

    def __init__(self, console: Console | None=None, show_all: bool=False):
        self.console = console or Console()
        self.show_all = show_all
        self._system_prompt_shown = False
        self._last_system_prompt: str | None = None

    def on_llm_event(self, event: LLMEvent) -> None:
        if event.event_type == 'request':
            self._render_llm_request(event)
        elif event.event_type == 'response':
            self._render_llm_response(event)

    def on_data_event(self, event: DataRetrievalEvent) -> None:
        if event.event_type == 'query':
            self._render_data_query(event)
        elif event.event_type == 'result':
            self._render_data_result(event)

    def _get_phase_label(self, phase: int) -> str:
        if phase in PERSONAS:
            return f'Phase {phase}: {PERSONAS[phase].name}'
        return f'Phase {phase}: Agent'

    def _render_llm_request(self, event: LLMEvent) -> None:
        if event.system_prompt and event.system_prompt != self._last_system_prompt:
            self._render_system_context(event.system_prompt)
            self._last_system_prompt = event.system_prompt
        self.console.print()
        phase_label = self._get_phase_label(event.phase)
        header = f' -> QUERY TO LLM                                 {phase_label}'
        self.console.print(Rule(style='magenta'))
        self.console.print(Text(header, style='bold magenta'))
        self.console.print(Rule(style='magenta'))
        self._render_prompt_content(event.user_prompt, event.response_model)
        self.console.print(Rule(style='dim magenta'))

    def _render_system_context(self, system_prompt: str) -> None:
        self.console.print()
        self.console.print(Rule('  SYSTEM CONTEXT  ', style='bold magenta', characters='='))
        if self.show_all:
            for line in system_prompt.split('\n'):
                self.console.print(f'  {line}', style='magenta')
        else:
            lines = system_prompt.split('\n')
            content_lines = []
            for line in lines[:30]:
                line = line.strip()
                if not line:
                    continue
                if len(line) > 100:
                    line = line[:97] + '...'
                content_lines.append(line)
            if len(lines) > 30:
                content_lines.append(f'... ({len(lines) - 30} more lines)')
            for line in content_lines:
                self.console.print(f'  {line}', style='magenta')
        self.console.print(Rule(style='magenta', characters='='))

    def _render_prompt_content(self, prompt: str | None, response_model: str | None) -> None:
        if not prompt:
            return
        if response_model:
            self.console.print(f' Expected Response: [bold]{response_model}[/bold]', style='magenta')
            self.console.print()
        if self.show_all:
            self.console.print(' [bold]Complete Query:[/bold]', style='magenta')
            for line in prompt.split('\n'):
                self.console.print(f'   {line}', style='magenta')
            return
        sections = self._parse_prompt_sections(prompt)
        if sections:
            for section_name, section_content in sections.items():
                self.console.print(f' [bold]{section_name}:[/bold]', style='magenta')
                section_lines = section_content.split('\n')
                for line in section_lines[:10]:
                    if line.strip():
                        display_line = line[:120] + '...' if len(line) > 120 else line
                        self.console.print(f'   {display_line}', style='magenta')
                if section_content.count('\n') > 10:
                    self.console.print('   ...', style='dim magenta')
                self.console.print()
        else:
            lines = prompt.split('\n')
            for line in lines[:15]:
                display_line = line[:120] + '...' if len(line) > 120 else line
                self.console.print(f'   {display_line}', style='magenta')
            if len(lines) > 15:
                self.console.print(f'   ... ({len(lines) - 15} more lines)', style='dim magenta')

    def _parse_prompt_sections(self, prompt: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        section_patterns = ['(?:^|\\n)(Error[^:]*):?\\s*\\n?(.*?)(?=\\n[A-Z]|\\Z)', '(?:^|\\n)(Context[^:]*):?\\s*\\n?(.*?)(?=\\n[A-Z]|\\Z)', '(?:^|\\n)(Hypothesis|Hypotheses)[^:]*:?\\s*\\n?(.*?)(?=\\n[A-Z]|\\Z)', '(?:^|\\n)(Evidence[^:]*):?\\s*\\n?(.*?)(?=\\n[A-Z]|\\Z)', '(?:^|\\n)(Task[^:]*):?\\s*\\n?(.*?)(?=\\n[A-Z]|\\Z)']
        for pattern in section_patterns:
            match = re.search(pattern, prompt, re.DOTALL | re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                content = match.group(2).strip()
                if content:
                    sections[name] = content if self.show_all else content[:500]
        return sections

    def _render_llm_response(self, event: LLMEvent) -> None:
        self.console.print()
        phase_label = self._get_phase_label(event.phase)
        header = f' <- RESPONSE FROM LLM                           {phase_label}'
        self.console.print(Rule(style='magenta'))
        self.console.print(Text(header, style='bold magenta'))
        self.console.print(Rule(style='magenta'))
        if not event.response:
            self.console.print(' [dim]No response[/dim]')
            self.console.print(Rule(style='dim magenta'))
            return
        if event.response_model:
            self._render_structured_response(event.response, event.response_model)
        else:
            self._render_text_response(event.response)
        self.console.print(Rule(style='dim magenta'))

    def _render_structured_response(self, response: str, model_name: str) -> None:
        if self.show_all:
            self.console.print(' [bold]Complete Response:[/bold]', style='magenta')
            try:
                data = json.loads(response)
                formatted = json.dumps(data, indent=2)
                for line in formatted.split('\n'):
                    self.console.print(f'   {line}', style='magenta')
            except json.JSONDecodeError:
                for line in response.split('\n'):
                    self.console.print(f'   {line}', style='magenta')
            return
        try:
            data = json.loads(response)
            self._render_model_data(data, model_name)
        except json.JSONDecodeError:
            self._render_text_response(response)

    def _render_model_data(self, data: dict, model_name: str) -> None:
        if 'hypotheses' in data:
            self._render_hypotheses_response(data)
        elif 'queries' in data:
            self._render_queries_response(data)
        elif 'chains' in data or 'causal_chains' in data:
            self._render_chains_response(data)
        elif 'challenges' in data:
            self._render_challenges_response(data)
        else:
            self._render_generic_structured(data, model_name)

    def _render_hypotheses_response(self, data: dict) -> None:
        hypotheses = data.get('hypotheses', [])
        self.console.print(f' Generated {len(hypotheses)} hypotheses:', style='magenta')
        self.console.print()
        if not hypotheses:
            self.console.print(' [dim]No hypotheses generated[/dim]')
            return
        table = Table(show_header=True, header_style='bold magenta', box=None)
        table.add_column('#', style='dim', width=3)
        table.add_column('Description', width=50 if not self.show_all else None)
        table.add_column('Category', width=12)
        table.add_column('Prior', width=10)
        max_items = len(hypotheses) if self.show_all else 10
        for i, hyp in enumerate(hypotheses[:max_items], 1):
            full_desc = hyp.get('description', 'Unknown')
            if self.show_all:
                desc = full_desc
            else:
                desc = full_desc[:60]
                if len(full_desc) > 60:
                    desc += '...'
            category = hyp.get('category', 'Unknown')
            prior = hyp.get('prior', 0)
            prior_label = self._format_prior(prior)
            table.add_row(str(i), desc, category, prior_label)
        self.console.print(table)
        if not self.show_all and len(hypotheses) > 10:
            self.console.print(f' ... and {len(hypotheses) - 10} more', style='dim magenta')

    def _render_queries_response(self, data: dict) -> None:
        queries = data.get('queries', [])
        self.console.print(f' Generated {len(queries)} evidence queries:', style='magenta')
        self.console.print()
        max_queries = len(queries) if self.show_all else 5
        for i, query in enumerate(queries[:max_queries], 1):
            query_type = query.get('query_type', 'Unknown')
            full_target = query.get('query', query.get('query_template', 'Unknown'))
            full_purpose = query.get('expected_if_true', query.get('expected_result', ''))
            if self.show_all:
                target = full_target
                purpose = full_purpose
            else:
                target = full_target[:60] + '...' if len(full_target) > 60 else full_target
                purpose = full_purpose[:60] + '...' if len(full_purpose) > 60 else full_purpose
            self.console.print(f' {i}. [{query_type}] {target}', style='magenta')
            if purpose:
                self.console.print(f'    Purpose: {purpose}', style='dim magenta')

    def _render_chains_response(self, data: dict) -> None:
        chains = data.get('chains', data.get('causal_chains', []))
        self.console.print(f' Built {len(chains)} causal chains:', style='magenta')
        self.console.print()
        max_chains = len(chains) if self.show_all else 3
        for i, chain in enumerate(chains[:max_chains], 1):
            full_hyp = chain.get('hypothesis', chain.get('root_cause', 'Unknown'))
            if self.show_all:
                hyp = full_hyp
            else:
                hyp = full_hyp[:50] + '...' if len(full_hyp) > 50 else full_hyp
            steps = chain.get('steps', [])
            confidence = chain.get('confidence', 0)
            self.console.print(f' Chain {i}: {hyp}', style='bold magenta')
            self.console.print(f'   Steps: {len(steps)}, Confidence: {confidence:.0%}', style='dim magenta')
            max_steps = len(steps) if self.show_all else 3
            for j, step in enumerate(steps[:max_steps], 1):
                full_cause = step.get('cause', '?')
                full_effect = step.get('effect', '?')
                if self.show_all:
                    cause = full_cause
                    effect = full_effect
                else:
                    cause = full_cause[:30] + '...' if len(full_cause) > 30 else full_cause
                    effect = full_effect[:30] + '...' if len(full_effect) > 30 else full_effect
                self.console.print(f'   {j}. {cause} -> {effect}', style='magenta')

    def _render_challenges_response(self, data: dict) -> None:
        challenges = data.get('challenges', [])
        self.console.print(f' Raised {len(challenges)} challenges:', style='magenta')
        self.console.print()
        max_challenges = len(challenges) if self.show_all else 5
        for i, challenge in enumerate(challenges[:max_challenges], 1):
            severity = challenge.get('severity', 'UNKNOWN')
            full_desc = challenge.get('description', challenge.get('challenge', 'Unknown'))
            full_target = challenge.get('target_hypothesis', '')
            if self.show_all:
                description = full_desc
                target = full_target
            else:
                description = full_desc[:70] + '...' if len(full_desc) > 70 else full_desc
                target = full_target[:30] + '...' if len(full_target) > 30 else full_target
            self.console.print(f' {i}. [{severity}] {description}', style='magenta')
            if target:
                self.console.print(f'    Challenges: {target}', style='dim magenta')

    def _render_generic_structured(self, data: dict, model_name: str) -> None:
        self.console.print(f' Response ({model_name}):', style='magenta')
        self.console.print()
        items = list(data.items())
        max_items = len(items) if self.show_all else 10
        for key, value in items[:max_items]:
            if isinstance(value, list):
                if self.show_all:
                    self.console.print(f' {key}:', style='magenta')
                    for item in value:
                        self.console.print(f'   - {item}', style='magenta')
                else:
                    self.console.print(f' {key}: [{len(value)} items]', style='magenta')
            elif isinstance(value, dict):
                if self.show_all:
                    self.console.print(f' {key}:', style='magenta')
                    for k, v in value.items():
                        self.console.print(f'   {k}: {v}', style='magenta')
                else:
                    self.console.print(f' {key}: {{...}}', style='magenta')
            elif isinstance(value, str) and len(value) > 80 and (not self.show_all):
                self.console.print(f' {key}: {value[:80]}...', style='magenta')
            else:
                self.console.print(f' {key}: {value}', style='magenta')

    def _render_text_response(self, response: str) -> None:
        lines = response.split('\n')
        max_lines = len(lines) if self.show_all else 20
        for line in lines[:max_lines]:
            if self.show_all:
                display_line = line
            else:
                display_line = line[:120] + '...' if len(line) > 120 else line
            self.console.print(f' {display_line}', style='magenta')
        if not self.show_all and len(lines) > 20:
            self.console.print(f' ... ({len(lines) - 20} more lines)', style='dim magenta')

    def _format_prior(self, prior: float) -> str:
        if prior >= 0.7:
            return f'High ({prior:.2f})'
        elif prior >= 0.4:
            return f'Medium ({prior:.2f})'
        else:
            return f'Low ({prior:.2f})'

    def _render_data_query(self, event: DataRetrievalEvent) -> None:
        self.console.print()
        if event.source == 'sqlite':
            style = 'blue'
            header_type = 'PATTERN DATABASE QUERY'
        elif event.source == 'chromadb':
            style = 'cyan'
            header_type = 'SEMANTIC SEARCH'
        else:
            style = 'green'
            header_type = 'DATA QUERY'
        phase_label = self._get_phase_label(event.phase)
        header = f' -> {header_type:<35} {phase_label}'
        self.console.print(Rule(style=style))
        self.console.print(Text(header, style=f'bold {style}'))
        self.console.print(Rule(style=style))
        operation_readable = event.operation.replace('_', ' ').title()
        self.console.print(f' Operation: {operation_readable}', style=f'bold {style}')
        if event.query_params:
            self.console.print()
            for key, value in event.query_params.items():
                key_readable = key.replace('_', ' ').title()
                if isinstance(value, str) and len(value) > 80 and (not self.show_all):
                    value = value[:77] + '...'
                self.console.print(f' {key_readable}: {value}', style=style)
        self.console.print(Rule(style=f'dim {style}'))

    def _render_data_result(self, event: DataRetrievalEvent) -> None:
        self.console.print()
        if event.source == 'sqlite':
            style = 'blue'
            header_type = 'PATTERN DATABASE RESULT'
        elif event.source == 'chromadb':
            style = 'cyan'
            header_type = 'SEMANTIC SEARCH RESULTS'
        else:
            style = 'green'
            header_type = 'DATA RESULT'
        phase_label = self._get_phase_label(event.phase)
        header = f' <- {header_type:<35} {phase_label}'
        self.console.print(Rule(style=style))
        self.console.print(Text(header, style=f'bold {style}'))
        self.console.print(Rule(style=style))
        if event.result_count is not None:
            count_word = 'result' if event.result_count == 1 else 'results'
            if event.result_count == 0:
                self.console.print(f' No {count_word} found', style=f'dim {style}')
            else:
                self.console.print(f' Found: {event.result_count} {count_word}', style=f'bold {style}')
        if event.result_summary:
            self.console.print()
            for line in event.result_summary.split('\n'):
                self.console.print(f' {line}', style=style)
        self.console.print(Rule(style=f'dim {style}'))