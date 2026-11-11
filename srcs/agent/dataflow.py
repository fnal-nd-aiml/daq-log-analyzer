"""
File: dataflow.py
Purpose: Phase 2.5: Dataflow Tracing.
Category: Utility
Author: artdaq team
Depends: indexer, source_location
Exports: VariableTrace, DataflowNode, DataflowChain, CodeHintExtractor, DataflowTracer, ...
Complexity: High | Lines: 463
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from srcs.extraction.indexer import CodeIndex
    from srcs.models.source_location import SourceLocation
logger = logging.getLogger(__name__)

@dataclass
class VariableTrace:
    variable_name: str
    source_function: str
    source_file: str
    source_line: int
    assignment_type: str
    source_expression: str = ''
    upstream_calls: list[str] = field(default_factory=list)

@dataclass
class DataflowNode:
    function_name: str
    file_path: str | Path
    line_number: int
    variable_name: str
    data_source: str
    data_type: str = ''
    is_error_point: bool = False

@dataclass
class DataflowChain:
    nodes: list[DataflowNode] = field(default_factory=list)
    root_source: str = ''
    confidence: float = 0.0
    gaps: list[str] = field(default_factory=list)

class CodeHintExtractor:
    HINT_PATTERNS = [('//\\s*(.+)$', 'comment'), ('/\\*\\s*(.+?)\\s*\\*/', 'block_comment'), ('(?:TLOG|LOG|mf::Log)\\w*\\s*\\([^)]*\\)\\s*<<\\s*"([^"]+)"', 'log_message'), ('throw\\s+\\w+\\s*\\(\\s*"([^"]+)"', 'exception_message'), ('assert\\s*\\([^,]+,\\s*"([^"]+)"', 'assert_message'), ('<<\\s*"([^"]*(?:caused by|due to|because|indicates|means)[^"]*)"', 'causal_message')]
    EXPLICIT_CAUSE_PATTERNS = ['["\\\']?[Tt]his\\s+is\\s+(?:most\\s+)?likely\\s+caused\\s+by\\s+([^"\\\'!.]+)["\\\']?', '["\\\']?[Tt]his\\s+is\\s+caused\\s+by\\s+([^"\\\'!.]+)["\\\']?', '["\\\']?[Tt]his\\s+(?:error\\s+)?happens\\s+when\\s+([^"\\\'!.]+)["\\\']?', '["\\\']?[Tt]his\\s+(?:error\\s+)?occurs\\s+when\\s+([^"\\\'!.]+)["\\\']?', '["\\\']?[Tt]his\\s+(?:error\\s+)?means\\s+([^"\\\'!.]+)["\\\']?', '["\\\']?(?:Check|Look\\s+at)\\s+([^"\\\'!.]+)\\s+first["\\\']?', '["\\\']?[Tt]he\\s+(?:problem|issue)\\s+is\\s+(?:likely\\s+)?([^"\\\'!.]+)["\\\']?', '["\\\']?(?:The\\s+)?[Mm]ost\\s+common\\s+cause\\s+is\\s+([^"\\\'!.]+)["\\\']?']
    FRAGMENT_START_WORDS = frozenset({'and', 'or', 'the', 'a', 'an', 'that', 'which', 'but', 'so', 'then', 'if', 'when', 'while', 'is', 'are', 'was', 'were'})
    FRAGMENT_END_WORDS = frozenset({'and', 'or', 'the', 'a', 'an', 'that', 'which', 'to', 'for', 'with', 'by', 'from', 'at', 'of', 'in', 'on'})
    FRAGMENT_END_CHARS = frozenset({')', ',', ':', ';', '-', '/'})

    def __init__(self) -> None:
        self._compiled_patterns = [(re.compile(pattern, re.IGNORECASE | re.MULTILINE), hint_type) for pattern, hint_type in self.HINT_PATTERNS]
        self._explicit_cause_patterns = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in self.EXPLICIT_CAUSE_PATTERNS]

    def _is_valid_hypothesis(self, text: str) -> bool:
        if not text:
            return False
        text = text.strip()
        words = text.split()
        if len(words) < 4:
            return False
        first_word = words[0].lower().rstrip('.,!?')
        if first_word in self.FRAGMENT_START_WORDS:
            return False
        last_word = words[-1].lower().rstrip('.,!?')
        if last_word in self.FRAGMENT_END_WORDS:
            return False
        last_char = text[-1]
        if last_char in self.FRAGMENT_END_CHARS:
            return False
        if text.endswith('!') and len(words) < 5:
            return False
        alpha_count = sum((1 for c in text if c.isalpha()))
        if alpha_count < len(text) * 0.5:
            return False
        underscore_count = text.count('_')
        if underscore_count > 2:
            return False
        if text.count('(') != text.count(')'):
            return False
        if text.count('[') != text.count(']'):
            return False
        lower = text.lower()
        op_prefixes = ('do a ', 'do more ', 'do some ', 'do the ', 'checking ', 'iterate ', 'iterating ', 'likely that', 'make sure ', 'set the ', 'look up ', 'looking up ', 'loop ')
        if any((lower.startswith(p) for p in op_prefixes)):
            return False
        state_phrases = ('is false', 'is true', 'should be set', 'is not set', 'is set to')
        failure_words = ('error', 'timeout', 'fail', 'fault', 'crash', 'abort', 'exceed', 'overflow', 'underflow', 'stall', 'miss', 'lost', 'corrupt', 'invalid', 'expired', 'violat', 'latency', 'delay')
        if any((sp in lower for sp in state_phrases)):
            if not any((fw in lower for fw in failure_words)):
                return False
        return True

    def extract_hints(self, function_body: str) -> list[dict]:
        hints = []
        for pattern, hint_type in self._compiled_patterns:
            for match in pattern.finditer(function_body):
                hint_text = match.group(1).strip()
                if len(hint_text) >= 10 and (not self._is_trivial(hint_text)) and self._is_valid_hypothesis(hint_text):
                    hints.append({'type': hint_type, 'content': hint_text, 'position': match.start()})
        hints.sort(key=lambda h: h['position'])
        return self._deduplicate(hints)

    def find_explicit_cause_hints(self, function_body: str) -> list[dict]:
        hints = []
        seen_lower = set()
        for pattern in self._explicit_cause_patterns:
            for match in pattern.finditer(function_body):
                hint = match.group(1).strip()
                hint = hint.rstrip('!"\'')
                if len(hint) < 5:
                    continue
                hint_lower = hint.lower()
                if hint_lower in seen_lower:
                    continue
                seen_lower.add(hint_lower)
                hints.append({'content': hint, 'is_authoritative': True, 'full_match': match.group(0).strip()})
        return hints

    def find_causal_hints(self, function_body: str) -> list[str]:
        causal_patterns = ['"([^"]*(?:caused by|due to|because of?)[^"]*)"', '"([^"]*(?:indicates?|means?|suggests?)[^"]*)"', '"([^"]*(?:problem with|issue with|error (?:in|from))[^"]*)"', '(?:caused by|due to|because of?)\\s+([^".\\n;]+[^".\\n;,\\s])', '(?:indicates?|means?|suggests?)\\s+(?:that\\s+)?([^".\\n;]+[^".\\n;,\\s])', '(?:problem with|issue with)\\s+([^".\\n;]+[^".\\n;,\\s])']
        hints = []
        seen_lower = set()
        for pattern in causal_patterns:
            for match in re.finditer(pattern, function_body, re.IGNORECASE):
                hint = match.group(1).strip()
                if len(hint) < 10:
                    continue
                hint_lower = hint.lower()
                if hint_lower in seen_lower:
                    continue
                if self._is_valid_hypothesis(hint):
                    seen_lower.add(hint_lower)
                    hints.append(hint)
        return hints

    def _is_trivial(self, text: str) -> bool:
        trivial = {'todo', 'fixme', 'hack', 'xxx', 'bug', 'note', 'debug', 'test', 'temp', 'temporary'}
        text_lower = text.lower()
        return any((t in text_lower for t in trivial)) or len(text.split()) < 3

    def _deduplicate(self, hints: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for hint in hints:
            content = hint['content'].lower()
            if content not in seen:
                seen.add(content)
                unique.append(hint)
        return unique

class DataflowTracer:

    def __init__(self, code_index: CodeIndex | None=None, source_roots: list[Path] | None=None) -> None:
        self._index = code_index
        self._source_roots = source_roots or []
        self._hint_extractor = CodeHintExtractor()

    async def trace_variable(self, variable_name: str, source_location: SourceLocation, max_depth: int=5) -> DataflowChain:
        chain = DataflowChain()
        error_node = DataflowNode(function_name=source_location.function_name or 'unknown', file_path=source_location.file_path, line_number=source_location.line_number, variable_name=variable_name, data_source='error_point', is_error_point=True)
        chain.nodes.append(error_node)
        if source_location.function_body:
            traces = self._trace_in_function(variable_name, source_location.function_body, source_location.function_name or '')
            for trace in traces:
                node = DataflowNode(function_name=trace.source_function, file_path=source_location.file_path, line_number=trace.source_line, variable_name=trace.variable_name, data_source=trace.assignment_type)
                chain.nodes.append(node)
                for upstream_call in trace.upstream_calls[:max_depth]:
                    upstream_node = await self._trace_upstream_call(upstream_call, source_location.file_path)
                    if upstream_node:
                        chain.nodes.append(upstream_node)
        chain.confidence = self._calculate_confidence(chain)
        chain.root_source = self._identify_root_source(chain)
        return chain

    def _trace_in_function(self, variable_name: str, function_body: str, function_name: str) -> list[VariableTrace]:
        traces = []
        call_pattern = re.compile(f'\\b{re.escape(variable_name)}\\s*=\\s*([^;]+);', re.MULTILINE)
        for match in call_pattern.finditer(function_body):
            expr = match.group(1).strip()
            calls = re.findall('(\\w+(?:::\\w+)*)\\s*\\(', expr)
            traces.append(VariableTrace(variable_name=variable_name, source_function=function_name, source_file='', source_line=function_body[:match.start()].count('\n') + 1, assignment_type='return_value' if calls else 'expression', source_expression=expr, upstream_calls=calls))
        param_pattern = re.compile(f'[\\w&*<>]+\\s+{re.escape(variable_name)}\\s*[,)]')
        if param_pattern.search(function_body[:200]):
            traces.append(VariableTrace(variable_name=variable_name, source_function=function_name, source_file='', source_line=1, assignment_type='parameter', source_expression=f'parameter: {variable_name}'))
        member_pattern = re.compile(f'{re.escape(variable_name)}\\s*=\\s*(?:this->)?(\\w+_?)\\s*[;.]', re.MULTILINE)
        for match in member_pattern.finditer(function_body):
            member_name = match.group(1)
            traces.append(VariableTrace(variable_name=variable_name, source_function=function_name, source_file='', source_line=function_body[:match.start()].count('\n') + 1, assignment_type='member_access', source_expression=f'member: {member_name}'))
        for_pattern = re.compile(f'for\\s*\\([^:]+:\\s*{re.escape(variable_name)}\\s*\\)', re.MULTILINE)
        if for_pattern.search(function_body):
            traces.append(VariableTrace(variable_name=variable_name, source_function=function_name, source_file='', source_line=1, assignment_type='iteration_source', source_expression=f'iterating over: {variable_name}'))
        return traces

    async def _trace_upstream_call(self, function_name: str, current_file: str) -> DataflowNode | None:
        if not self._index:
            return None
        try:
            simple_name = function_name.split('::')[-1]
            functions = self._index.find_function(simple_name)
            for func in functions:
                return DataflowNode(function_name=func.name, file_path=func.file_path, line_number=func.start_line, variable_name='return_value', data_source='function_return', data_type=func.return_type or '')
        except Exception as e:
            logger.debug('Failed to trace upstream call %s: %s', function_name, e)
        return None

    def _calculate_confidence(self, chain: DataflowChain) -> float:
        if not chain.nodes:
            return 0.0
        node_score = min(0.4, len(chain.nodes) * 0.1)
        type_bonus = 0.0
        for node in chain.nodes:
            if node.data_source in ('return_value', 'function_return'):
                type_bonus += 0.15
            elif node.data_source == 'parameter':
                type_bonus += 0.1
            elif node.data_source == 'member_access':
                type_bonus += 0.1
        gap_penalty = len(chain.gaps) * 0.1
        return min(1.0, max(0.0, node_score + type_bonus - gap_penalty))

    def _identify_root_source(self, chain: DataflowChain) -> str:
        if not chain.nodes:
            return 'unknown'
        for node in reversed(chain.nodes):
            func_lower = node.function_name.lower()
            source_lower = node.data_source.lower()
            if 'generator' in func_lower or 'generator' in source_lower:
                return 'FragmentGenerator'
            if 'hardware' in func_lower:
                return 'Hardware'
            if 'config' in func_lower:
                return 'Configuration'
            if 'buffer' in func_lower:
                return 'FragmentBuffer'
            if 'request' in func_lower:
                return 'Request'
        return chain.nodes[-1].data_source if chain.nodes else 'unknown'

    def extract_error_variable(self, source_location: SourceLocation) -> str | None:
        error_line = source_location.matched_line
        null_check = re.search('if\\s*\\(\\s*!?\\s*(\\w+)\\s*(?:==\\s*nullptr|!=\\s*nullptr|\\))', error_line)
        if null_check:
            return null_check.group(1)
        deref = re.search('(\\w+)\\s*->|(?<!\\w)\\*\\s*(\\w+)', error_line)
        if deref:
            return deref.group(1) or deref.group(2)
        bad_var = re.search('(?:bad|invalid|null|nullptr|empty)\\s+(\\w+)', error_line, re.IGNORECASE)
        if bad_var:
            return bad_var.group(1)
        log_var = re.search('<<\\s*(\\w+)\\s*(?:<<|;)', error_line)
        if log_var:
            return log_var.group(1)
        return None

    async def trace_from_error(self, source_location: SourceLocation, max_depth: int=5) -> tuple[DataflowChain, list[str]]:
        hints = []
        if source_location.function_body:
            hints = self._hint_extractor.find_causal_hints(source_location.function_body)
        error_var = self.extract_error_variable(source_location)
        if error_var:
            chain = await self.trace_variable(error_var, source_location, max_depth)
        else:
            chain = DataflowChain(nodes=[DataflowNode(function_name=source_location.function_name or 'unknown', file_path=source_location.file_path, line_number=source_location.line_number, variable_name='unknown', data_source='error_point', is_error_point=True)], gaps=['Could not identify error variable'])
        return (chain, hints)

    def generate_evidence_queries(self, chain: DataflowChain) -> list[dict]:
        queries = []
        seen_functions = set()
        for node in chain.nodes:
            if node.function_name and node.function_name not in seen_functions:
                seen_functions.add(node.function_name)
                queries.append({'query_type': 'function_lookup', 'query': node.function_name, 'from_dataflow': True, 'full_source': True, 'expected_result': f'Dataflow trace: {node.data_source}'})
        if chain.root_source and chain.root_source not in seen_functions:
            queries.append({'query_type': 'code_search', 'query': chain.root_source, 'from_dataflow': True, 'expected_result': f'Root data source: {chain.root_source}'})
        return queries

@dataclass
class NumericValue:
    value: int | float
    unit: str
    value_type: str
    raw_match: str
    position: int = 0

@dataclass
class LabeledRange:
    label: str
    start: int
    end: int
    span_us: int
    raw_match: str
    position: int = 0

@dataclass
class NumericAnalysis:
    values: list[NumericValue]
    labeled_ranges: list[LabeledRange] = field(default_factory=list)
    buffer_behind_window_us: int | None = None
    buffer_behind_window_human: str = ''
    timestamp_gap_us: int | None = None
    timestamp_gap_human: str = ''
    timeout_exceeded_by_us: int | None = None
    timeout_exceeded_percent: float | None = None
    interpretation: str = ''

class NumericExtractor:
    PATTERNS = {'timeout_us': re.compile('(\\d+)\\s*(?:us|microseconds?)\\b', re.IGNORECASE), 'timeout_ms': re.compile('(\\d+)\\s*(?:ms|milliseconds?)\\b', re.IGNORECASE), 'timeout_s': re.compile('(\\d+(?:\\.\\d+)?)\\s*(?:s|seconds?)\\b', re.IGNORECASE), 'timestamp': re.compile('\\{?(\\d{10,19})\\}?'), 'range': re.compile('\\{(\\d+)-(\\d+)\\}'), 'comparison': re.compile('(\\d+)\\s*(>|<|>=|<=)\\s*(\\d+)'), 'memory_bytes': re.compile('(\\d+)\\s*(?:bytes?|B)\\b', re.IGNORECASE), 'memory_kb': re.compile('(\\d+)\\s*(?:KB|kb|kilobytes?)\\b', re.IGNORECASE), 'memory_mb': re.compile('(\\d+)\\s*(?:MB|mb|megabytes?)\\b', re.IGNORECASE), 'memory_gb': re.compile('(\\d+)\\s*(?:GB|gb|gigabytes?)\\b', re.IGNORECASE), 'count': re.compile('(?:count|size|length|num)\\s*[:=]\\s*(\\d+)', re.IGNORECASE)}
    LABELED_RANGE_RE = re.compile('(\\w+(?:_\\w+)*)\\s*[=(]\\s*\\{(\\d{10,19})-(\\d{10,19})\\}')

    def extract(self, message: str) -> list[NumericValue]:
        values: list[NumericValue] = []
        range_positions: set[int] = set()
        self._last_labeled_ranges: list[LabeledRange] = []
        for match in self.LABELED_RANGE_RE.finditer(message):
            label = match.group(1).strip()
            start_val = int(match.group(2))
            end_val = int(match.group(3))
            span = end_val - start_val
            self._last_labeled_ranges.append(LabeledRange(label=label, start=start_val, end=end_val, span_us=span, raw_match=match.group(0), position=match.start()))
        for match in self.PATTERNS['range'].finditer(message):
            start_val = int(match.group(1))
            end_val = int(match.group(2))
            range_positions.add(match.start())
            if len(match.group(1)) >= 16 and len(match.group(2)) >= 16:
                gap = end_val - start_val
                values.append(NumericValue(value=gap, unit='us', value_type='timestamp_gap', raw_match=match.group(0), position=match.start()))
            else:
                values.append(NumericValue(value=end_val - start_val, unit='range', value_type='range', raw_match=match.group(0), position=match.start()))
        for match in self.PATTERNS['timestamp'].finditer(message):
            raw_value = match.group(1)
            if len(raw_value) >= 16:
                is_in_range = False
                for rp in range_positions:
                    if rp <= match.start() <= rp + 50:
                        is_in_range = True
                        break
                if not is_in_range:
                    values.append(NumericValue(value=int(raw_value), unit='us', value_type='timestamp', raw_match=match.group(0), position=match.start()))
        for unit_suffix, pattern in [('us', self.PATTERNS['timeout_us']), ('ms', self.PATTERNS['timeout_ms']), ('s', self.PATTERNS['timeout_s'])]:
            for match in pattern.finditer(message):
                value = float(match.group(1))
                if unit_suffix == 'ms':
                    value_us = int(value * 1000)
                elif unit_suffix == 's':
                    value_us = int(value * 1000000)
                else:
                    value_us = int(value)
                values.append(NumericValue(value=value_us, unit='us', value_type='timeout', raw_match=match.group(0), position=match.start()))
        for unit, mult in [('memory_bytes', 1), ('memory_kb', 1024), ('memory_mb', 1024 * 1024), ('memory_gb', 1024 * 1024 * 1024)]:
            for match in self.PATTERNS[unit].finditer(message):
                value = int(match.group(1)) * mult
                values.append(NumericValue(value=value, unit='bytes', value_type='memory', raw_match=match.group(0), position=match.start()))
        for match in self.PATTERNS['count'].finditer(message):
            values.append(NumericValue(value=int(match.group(1)), unit='count', value_type='count', raw_match=match.group(0), position=match.start()))
        values.sort(key=lambda v: v.position)
        return values

    def analyze(self, message: str) -> NumericAnalysis:
        values = self.extract(message)
        analysis = NumericAnalysis(values=values)
        if hasattr(self, '_last_labeled_ranges'):
            analysis.labeled_ranges = self._last_labeled_ranges
        if len(analysis.labeled_ranges) >= 2:
            window_range = None
            buffer_range = None
            for lr in analysis.labeled_ranges:
                label_lower = lr.label.lower()
                if 'window' in label_lower or 'request' in label_lower:
                    window_range = lr
                elif 'buffer' in label_lower:
                    buffer_range = lr
            if window_range and buffer_range:
                gap = window_range.end - buffer_range.end
                if gap > 0:
                    analysis.buffer_behind_window_us = gap
                    analysis.buffer_behind_window_human = self._format_duration(gap)
        timestamp_gaps = [v for v in values if v.value_type == 'timestamp_gap']
        if timestamp_gaps:
            gaps = sorted((int(v.value) for v in timestamp_gaps if v.value > 0))
            if gaps:
                smallest_gap = gaps[0]
                analysis.timestamp_gap_us = smallest_gap
                analysis.timestamp_gap_human = self._format_duration(smallest_gap)
        else:
            timestamps = [v for v in values if v.value_type == 'timestamp']
            if len(timestamps) >= 2:
                ts_values = sorted((int(v.value) for v in timestamps))
                gap_us = ts_values[-1] - ts_values[0]
                analysis.timestamp_gap_us = gap_us
                analysis.timestamp_gap_human = self._format_duration(gap_us)
        timeouts = [v for v in values if v.value_type == 'timeout']
        if len(timeouts) >= 2:
            timeout_values = sorted((int(t.value) for t in timeouts))
            configured_timeout = timeout_values[0]
            actual_wait = timeout_values[-1]
            if actual_wait > configured_timeout:
                exceeded_by = actual_wait - configured_timeout
                exceeded_percent = exceeded_by / configured_timeout * 100 if configured_timeout > 0 else 0
                analysis.timeout_exceeded_by_us = exceeded_by
                analysis.timeout_exceeded_percent = exceeded_percent
        elif len(timeouts) == 1 and analysis.timestamp_gap_us:
            timeout_us = int(timeouts[0].value)
            if analysis.timestamp_gap_us > timeout_us:
                exceeded_by = analysis.timestamp_gap_us - timeout_us
                exceeded_percent = exceeded_by / timeout_us * 100 if timeout_us > 0 else 0
                analysis.timeout_exceeded_by_us = exceeded_by
                analysis.timeout_exceeded_percent = exceeded_percent
        analysis.interpretation = self._generate_interpretation(analysis)
        return analysis

    def _format_duration(self, microseconds: int) -> str:
        if microseconds >= 1000000:
            seconds = microseconds / 1000000
            return f'{seconds:.1f} seconds'
        elif microseconds >= 1000:
            ms = microseconds / 1000
            return f'{ms:.1f} ms'
        else:
            return f'{microseconds} us'

    def _generate_interpretation(self, analysis: NumericAnalysis) -> str:
        parts: list[str] = []
        if analysis.timestamp_gap_us:
            parts.append(f'Timestamp gap of {analysis.timestamp_gap_human} detected')
        if analysis.timeout_exceeded_by_us:
            parts.append(f'Timeout exceeded by {self._format_duration(analysis.timeout_exceeded_by_us)} ({analysis.timeout_exceeded_percent:.0f}% over limit)')
        if analysis.buffer_behind_window_us:
            parts.append(f'Buffer latest data is {analysis.buffer_behind_window_human} behind the request window maximum (data IS arriving but too slowly)')
        for v in analysis.values:
            if v.value_type == 'memory' and v.value > 1000000000:
                parts.append(f'Large memory value: {v.value / (1024 * 1024 * 1024):.1f} GB')
        if not parts:
            return 'No significant numeric patterns identified'
        return '; '.join(parts)

    def format_for_hypothesis(self, analysis: NumericAnalysis) -> str:
        if not analysis.values:
            return ''
        lines = ['## Numeric Analysis from Error Message']
        if analysis.timestamp_gap_us:
            gap_us = analysis.timestamp_gap_us
            lines.append(f'- **Timestamp Gap**: {gap_us:,} us (= {self._format_duration(gap_us)}). {analysis.timestamp_gap_human}')
        if analysis.buffer_behind_window_us:
            gap_us = analysis.buffer_behind_window_us
            lines.append(f"- **Buffer Behind Window**: Buffer's latest data is {gap_us:,} us (= {self._format_duration(gap_us)}) behind the request window maximum. Data IS flowing but not fast enough.")
            if analysis.labeled_ranges:
                for lr in analysis.labeled_ranges:
                    lines.append(f'  - {lr.label}: {lr.start} to {lr.end} (span: {self._format_duration(lr.span_us)})')
        if analysis.timeout_exceeded_by_us:
            exceeded_us = analysis.timeout_exceeded_by_us
            lines.append(f'- **Timeout Violation**: Exceeded by {exceeded_us:,} us (= {self._format_duration(exceeded_us)}), {analysis.timeout_exceeded_percent:.0f}% over configured limit')
        if analysis.interpretation:
            lines.append(f'- **Interpretation**: {analysis.interpretation}')
        if analysis.values:
            lines.append('- **Key Values**:')
            for v in analysis.values[:5]:
                suffix = ''
                if v.unit == 'us' and v.value >= 1000:
                    suffix = f' (= {self._format_duration(int(v.value))})'
                lines.append(f'  - {v.value_type}: {v.raw_match}{suffix}')
        return '\n'.join(lines)

    def recommend_hypotheses(self, analysis: NumericAnalysis) -> list[dict]:
        hypotheses: list[dict] = []
        if analysis.buffer_behind_window_us:
            hypotheses.append({'description': f"Data pipeline latency: buffer's latest data is {analysis.buffer_behind_window_human} behind the request window maximum. Upstream data production is not keeping pace with data requests.", 'source': 'numeric_analysis:buffer_latency', 'prior': 0.85})
        return hypotheses