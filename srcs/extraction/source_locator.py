"""
File: source_locator.py
Purpose: Source code locator for error messages.
Category: Utility
Author: artdaq team
Depends: extraction, indexer, chroma_store, token_utils, source_location
Exports: SourceLocator
Complexity: Medium | Lines: 342
"""

from __future__ import annotations
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
from srcs.models.source_location import SourceLocation, SourceLocationResult
if TYPE_CHECKING:
    from srcs.extraction.indexer import CodeIndex
    from srcs.knowledge.chroma_store import ChromaStore
logger = logging.getLogger(__name__)

class SourceLocator:
    LOG_PATTERNS = ['TLOG\\s*\\([^)]*\\)\\s*<<', 'TLOG_\\w+\\s*\\([^)]*\\)\\s*<<', 'mf::Log\\w*\\s*\\([^)]*\\)', 'mf::LogDebug\\s*\\(', 'mf::LogInfo\\s*\\(', 'mf::LogWarning\\s*\\(', 'mf::LogError\\s*\\(', 'mf::LogAbsolute\\s*\\(', 'TRACE\\s*\\(', 'TRACE_\\w+\\s*\\(', 'TRACEN\\s*\\(', 'LOG_\\w+\\s*\\(', 'art::Exception\\s*\\(', 'cet::exception\\s*\\(', 'std::cerr\\s*<<', 'std::cout\\s*<<', 'fprintf\\s*\\(\\s*stderr', 'printf\\s*\\(', 'throw\\s+\\w+\\s*\\(']
    EXTENSIONS = ['.cc', '.cpp', '.cxx', '.c', '.h', '.hpp', '.hxx']
    FUNCTION_NAME_PATTERNS = ['\\b([a-z][a-zA-Z0-9]*(?:_[A-Za-z0-9]+)+)\\b', '\\b([A-Z][a-zA-Z0-9]*(?:_[A-Za-z0-9]+)+)\\b', '\\b([a-z][a-zA-Z0-9]*(?:::[a-zA-Z_][a-zA-Z0-9_]*)+)\\b', '\\b([A-Z][a-zA-Z0-9]+::[a-zA-Z_][a-zA-Z0-9_]+)\\b', '(?:in\\s+)?(?:function|method)\\s+[`\\\'"]*([a-zA-Z_][a-zA-Z0-9_:]+)[`\\\'"]*', '\\b([A-Z][a-z]+(?:[A-Z][a-z]+){2,})\\b']
    VARIABLE_PATTERNS = [('\\b\\d+\\b', '\\\\d+'), ('0x[0-9a-fA-F]+', '0x[0-9a-fA-F]+'), ('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '[0-9a-fA-F-]{36}'), ('\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}', '\\\\d+\\\\.\\\\d+\\\\.\\\\d+\\\\.\\\\d+'), ('\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}', '\\\\d{4}-\\\\d{2}-\\\\d{2}.\\\\d{2}:\\\\d{2}:\\\\d{2}')]

    def __init__(self, source_roots: list[Path], code_index: CodeIndex | None=None, chroma_store: ChromaStore | None=None) -> None:
        self._source_roots = source_roots
        self._index = code_index
        self._chroma = chroma_store
        self._log_macro_pattern = re.compile('|'.join(self.LOG_PATTERNS), re.IGNORECASE)

    def extract_function_names(self, message: str) -> list[str]:
        function_names: list[str] = []
        seen_lower: set[str] = set()
        for pattern in self.FUNCTION_NAME_PATTERNS:
            for match in re.finditer(pattern, message, re.IGNORECASE):
                func_name = match.group(1)
                if len(func_name) < 5:
                    continue
                func_lower = func_name.lower()
                if func_lower in seen_lower:
                    continue
                common_words = {'error', 'warning', 'debug', 'info', 'fatal', 'nullptr', 'null', 'true', 'false', 'void', 'timeout', 'occurred', 'waiting', 'request', 'window', 'buffer', 'failed', 'success', 'invalid', 'unknown', 'message', 'string', 'value', 'result', 'return', 'function', 'method', 'class', 'object', 'exception', 'thread', 'process', 'memory', 'pointer', 'reference', 'const', 'static', 'virtual', 'public', 'private', 'close', 'waiting', 'expected', 'actual', 'current'}
                if func_lower in common_words:
                    continue
                if '_' not in func_name and '::' not in func_name:
                    upper_count = sum((1 for c in func_name if c.isupper()))
                    if upper_count < 2:
                        continue
                seen_lower.add(func_lower)
                function_names.append(func_name)

        def specificity_score(name: str) -> tuple[int, int]:
            has_namespace = '::' in name or '_' in name
            return (1 if has_namespace else 0, len(name))
        function_names.sort(key=specificity_score, reverse=True)
        return function_names

    async def find_source(self, message: str, max_results: int=5, context_lines: int=3, component: str | None=None) -> SourceLocationResult:
        start_time = time.time()
        result = SourceLocationResult(original_message=message, locations=[], patterns_tried=[], files_searched=0)
        patterns = self._create_search_patterns(message)
        result.patterns_tried = [p.pattern for p in patterns]
        raw_matches = await self._search_files(patterns, max_results=max_results * 2, component=component)
        result.files_searched = raw_matches.get('files_searched', 0)
        ranked_matches = self._rank_matches(raw_matches.get('matches', []), message)
        top_matches = ranked_matches[:max_results]
        for match in top_matches:
            location = await self._enrich_with_index_data(match, context_lines)
            result.locations.append(location)
        result.search_time_ms = (time.time() - start_time) * 1000
        return result

    def _create_search_patterns(self, message: str) -> list[re.Pattern]:
        patterns = []
        static_segments = self._extract_static_segments(message)
        for segment in sorted(static_segments, key=len, reverse=True):
            if len(segment) >= 10:
                escaped = re.escape(segment)
                escaped = escaped.replace('\\ ', '\\s+')
                try:
                    patterns.append(re.compile(escaped, re.IGNORECASE))
                except re.error:
                    continue
        source_patterns = self._message_to_source_patterns(message)
        patterns.extend(source_patterns)
        key_phrases = self._extract_key_phrases(message)
        for phrase in key_phrases:
            if len(phrase) >= 6:
                try:
                    patterns.append(re.compile(re.escape(phrase), re.IGNORECASE))
                except re.error:
                    continue
        return patterns

    def _extract_static_segments(self, message: str) -> list[str]:
        static = message
        for pattern, _ in self.VARIABLE_PATTERNS:
            static = re.sub(pattern, ' ', static)
        words = [w.strip() for w in static.split() if len(w.strip()) >= 3]
        segments = []
        current_segment = []
        for word in words:
            current_segment.append(word)
            segment_text = ' '.join(current_segment)
            if segment_text in message:
                segments.append(segment_text)
        for word in words:
            if len(word) >= 5 and word not in segments:
                segments.append(word)
        return segments

    def _message_to_source_patterns(self, message: str) -> list[re.Pattern]:
        patterns = []
        number_matches = list(re.finditer('\\b\\d+\\b', message))
        if number_matches:
            for match in number_matches:
                before = message[:match.start()].strip()
                if len(before) >= 5:
                    escaped_before = re.escape(before[-30:])
                    pattern_str = escaped_before + '["\\\']?\\s*(?:<<|\\+)\\s*\\w+'
                    try:
                        patterns.append(re.compile(pattern_str, re.IGNORECASE))
                    except re.error:
                        continue
        hex_matches = list(re.finditer('0x[0-9a-fA-F]+', message))
        for match in hex_matches:
            before = message[:match.start()].strip()
            if len(before) >= 5:
                escaped_before = re.escape(before[-20:])
                pattern_str = escaped_before + '["\\\']?\\s*(?:<<|\\+)\\s*(?:0x)?[0-9a-fA-F]+'
                try:
                    patterns.append(re.compile(pattern_str, re.IGNORECASE))
                except re.error:
                    continue
        return patterns

    def _extract_key_phrases(self, message: str) -> list[str]:
        phrases = []
        error_patterns = ['(?:error|failed|exception|invalid|bad|corrupt|unable)[:\\s]+\\w+(?:\\s+\\w+)?', "(?:cannot|could not|couldn\\'t)\\s+\\w+(?:\\s+\\w+)?", '(?:unexpected|unknown|missing|null)\\s+\\w+']
        for pattern in error_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            phrases.extend(matches)
        identifiers = re.findall('\\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\\b', message)
        phrases.extend(identifiers)
        identifiers = re.findall('\\b\\w+_\\w+(?:_\\w+)*\\b', message)
        phrases.extend(identifiers)
        quoted = re.findall('"([^"]+)"', message)
        phrases.extend(quoted)
        quoted = re.findall("'([^']+)'", message)
        phrases.extend(quoted)
        return phrases

    async def _search_files(self, patterns: list[re.Pattern], max_results: int, component: str | None=None) -> dict:
        matches = []
        files_searched = 0
        max_files = 500
        for source_root in self._source_roots:
            if not source_root.exists():
                continue
            for ext in self.EXTENSIONS:
                for source_file in source_root.rglob(f'*{ext}'):
                    if files_searched >= max_files:
                        break
                    if component and component.lower() not in ('unknown', 'n/a', 'none', ''):
                        base = component
                        if '::' in base:
                            base = base.split('::')[0]
                        if '_' in base:
                            tail = base.rsplit('_', 1)[1]
                            if tail and tail[0].isupper():
                                base = tail
                        if base.lower() not in str(source_file).lower():
                            continue
                    files_searched += 1
                    try:
                        content = source_file.read_text(errors='ignore')
                        lines = content.split('\n')
                        for line_num, line in enumerate(lines, 1):
                            for pattern in patterns:
                                if pattern.search(line):
                                    context_start = max(0, line_num - 4)
                                    context_end = min(len(lines), line_num + 3)
                                    context_block = '\n'.join(lines[context_start:context_end])
                                    is_log = bool(self._log_macro_pattern.search(context_block))
                                    matches.append({'file': source_file, 'line_num': line_num, 'line': line, 'pattern': pattern.pattern, 'is_log': is_log, 'context_lines': lines[context_start:context_end], 'context_start': context_start})
                                    if len(matches) >= max_results:
                                        return {'matches': matches, 'files_searched': files_searched}
                                    break
                    except Exception as e:
                        logger.debug(f'Failed to search {source_file}: {e}')
                        continue
        return {'matches': matches, 'files_searched': files_searched}

    def _rank_matches(self, matches: list[dict], original_message: str) -> list[dict]:
        for match in matches:
            score = 0.0
            if match.get('is_log'):
                score += 0.3
            pattern_len = len(match.get('pattern', ''))
            score += min(0.3, pattern_len / 100)
            matched_line = match.get('line', '')
            msg_words = set(original_message.lower().split())
            line_words = set(matched_line.lower().split())
            common_words = msg_words & line_words
            if msg_words:
                score += 0.2 * len(common_words) / len(msg_words)
            for word in original_message.split():
                if len(word) >= 5 and word.lower() in matched_line.lower():
                    score += 0.05
            match['score'] = min(1.0, score)
        return sorted(matches, key=lambda m: m.get('score', 0), reverse=True)

    async def _enrich_with_index_data(self, match: dict, context_lines: int) -> SourceLocation:
        file_path = str(match['file'])
        line_num = match['line_num']
        all_context = match.get('context_lines', [])
        context_start = match.get('context_start', 0)
        line_idx_in_context = line_num - context_start - 1
        before = all_context[:line_idx_in_context][-context_lines:]
        after = all_context[line_idx_in_context + 1:][:context_lines]
        location = SourceLocation(file_path=file_path, line_number=line_num, matched_line=match['line'], context_before=before, context_after=after, match_score=match.get('score', 0.5), search_pattern=match['pattern'], is_log_statement=match.get('is_log', False))
        if self._index:
            func_info = self._find_enclosing_function(file_path, line_num)
            if func_info:
                location.function_name = func_info.get('name')
                location.function_signature = func_info.get('signature')
                location.function_start_line = func_info.get('start_line')
                location.function_end_line = func_info.get('end_line')
                location.class_name = func_info.get('class_name')
                if location.function_name:
                    raw_callers = self._index.get_callers(location.function_name)
                    raw_callees = self._index.get_callees(location.function_name)
                    location.callers = self._enrich_call_graph_entries(raw_callers, is_caller=True)
                    location.callees = self._enrich_call_graph_entries(raw_callees, is_caller=False)
        function_body = self._extract_function_body(Path(file_path), line_num, location.function_start_line, location.function_end_line)
        if function_body:
            location.function_body = function_body
        if self._chroma and location.function_name:
            summary = await self._get_function_summary(location.function_name, file_path)
            location.function_summary = summary
        return location

    def _extract_function_body(self, file_path: Path, line_num: int, func_start: int | None, func_end: int | None) -> str | None:
        if not file_path.exists():
            return None
        try:
            content = file_path.read_text(errors='ignore')
            lines = content.split('\n')
            if func_start is not None and func_end is not None:
                max_lines = 100
                if func_end - func_start > max_lines:
                    start = max(func_start - 1, line_num - 30)
                    end = min(func_end, line_num + 30)
                else:
                    start = func_start - 1
                    end = func_end
                return '\n'.join(lines[start:end])
            function_body = self._extract_with_tree_sitter(file_path, line_num)
            if function_body:
                return function_body
            start = max(0, line_num - 20)
            end = min(len(lines), line_num + 20)
            return '\n'.join(lines[start:end])
        except Exception as e:
            logger.debug(f'Failed to extract function body: {e}')
            return None

    def _extract_with_tree_sitter(self, file_path: Path, line_num: int) -> str | None:
        try:
            from srcs.extraction import CodeParser
            parser = CodeParser()
            parsed = parser.parse_file(file_path)
            if not parsed.root:
                return None
            for func_node in parsed.root.find_all('function_definition'):
                if func_node.start_line <= line_num <= func_node.end_line:
                    body = func_node.text
                    if len(body) > 5000:
                        lines = body.split('\n')
                        relative_line = line_num - func_node.start_line
                        start = max(0, relative_line - 30)
                        end = min(len(lines), relative_line + 30)
                        return '\n'.join(lines[start:end])
                    return body
        except Exception as e:
            logger.debug(f'Tree-sitter extraction failed: {e}')
        return None

    def _find_enclosing_function(self, file_path: str, line_num: int) -> dict | None:
        if not self._index:
            return None
        try:
            functions = self._index.find_function('%', file_filter=file_path)
            for func in functions:
                if func.start_line <= line_num <= func.end_line:
                    return {'name': func.name, 'signature': func.signature, 'start_line': func.start_line, 'end_line': func.end_line, 'class_name': func.class_name}
        except Exception as e:
            logger.debug(f'Failed to find enclosing function: {e}')
        return None

    def _extract_body_for_function(self, func_name: str, max_chars: int=0) -> str | None:
        if not self._index:
            return None
        body = self._index.get_function_source(func_name)
        if not body:
            return None
        from srcs.llm.token_utils import truncate_middle_if_needed
        return truncate_middle_if_needed(body, max_tokens=max_chars // 4 if max_chars > 0 else 0, label=f'call graph body:{func_name}')

    def _enrich_call_graph_entries(self, entries: list[dict], is_caller: bool, max_with_body: int=3) -> list[dict]:
        enriched = []
        for i, entry in enumerate(entries):
            enriched_entry = dict(entry)
            enriched_entry['role'] = 'CALLER' if is_caller else 'CALLEE'
            if is_caller:
                func_name = entry.get('caller_name')
                enriched_entry['relationship'] = 'passes data TO error location'
            else:
                func_name = entry.get('callee_name')
                enriched_entry['relationship'] = 'receives data FROM error location'
            if i < max_with_body and func_name:
                enriched_entry['body'] = self._extract_body_for_function(func_name)
                if not is_caller and self._index:
                    funcs = self._index.find_function(func_name)
                    if funcs:
                        enriched_entry['callee_file'] = str(funcs[0].file_path)
                        enriched_entry['callee_signature'] = funcs[0].signature
            else:
                enriched_entry['body'] = None
            enriched.append(enriched_entry)
        return enriched

    async def _get_function_summary(self, func_name: str, file_path: str) -> str | None:
        if not self._chroma:
            return None
        try:
            file_name = Path(file_path).name
            results = await self._chroma.find_similar_functions(f'function {func_name}', n=5, file_filter=file_name)
            for result in results:
                if result.get('function_name') == func_name:
                    summary = result.get('summary')
                    return str(summary) if summary else None
            if results:
                summary = results[0].get('summary')
                return str(summary) if summary else None
        except Exception as e:
            logger.debug(f'Failed to get function summary: {e}')
        return None