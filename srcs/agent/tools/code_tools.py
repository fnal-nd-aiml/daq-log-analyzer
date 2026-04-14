"""
File: code_tools.py
Purpose: Code-based evidence gathering tools.
Category: Utility
Author: artdaq team
Depends: extraction, source_locator, chroma_store, token_utils, models, ...
Exports: CodeTools
Complexity: Medium | Lines: 515
"""

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING
from srcs.extraction import CodeExtractor, CodeIndex, CodeIndexConfig, CodeParser
from srcs.extraction.source_locator import SourceLocator
from srcs.models import EvidenceItem
from srcs.source import RepositoryManager, SourceConfig
from .base import logger, validate_path

if TYPE_CHECKING:
    from srcs.knowledge.chroma_store import ChromaStore


class CodeTools:

    def __init__(
        self,
        code_index: CodeIndex | None = None,
        source_roots: list[Path] | None = None,
        source_config: SourceConfig | None = None,
    ):
        self._code_index = code_index
        self._source_roots = source_roots or []
        self._source_config = source_config
        self._parser = CodeParser()
        self._extractor = CodeExtractor(self._parser)
        if source_config and source_config.has_repositories():
            manager = RepositoryManager(source_config)
            repo_paths = manager.get_existing_repo_paths()
            for path in repo_paths:
                if path not in self._source_roots:
                    self._source_roots.append(path)

    def _ensure_index(self) -> CodeIndex | None:
        if self._code_index is not None:
            return self._code_index
        if not self._source_roots:
            return None
        try:
            config = CodeIndexConfig(source_roots=self._source_roots)
            self._code_index = CodeIndex(config)
            self._code_index.build_index()
            return self._code_index
        except Exception as e:
            logger.warning("Failed to build code index: %s", e)
            return None

    async def lookup_function(
        self, function_name: str, include_source: bool = True, max_source_length: int = 0
    ) -> list[EvidenceItem]:
        index = self._ensure_index()
        if index is None:
            return []
        functions = []
        try:
            functions = index.find_function(function_name)
            if not functions and "_" in function_name:
                parts = function_name.split("_")
                for i in range(len(parts)):
                    partial = "_".join(parts[i:])
                    if len(partial) >= 5:
                        functions = index.find_function(f"%{partial}%")
                        if functions:
                            logger.debug("Partial match '%s' found %s functions", partial, len(functions))
                            break
            if not functions and "%" not in function_name:
                functions = index.find_function(f"%{function_name}%")
                if functions:
                    logger.debug("Wildcard search for '%s' found %s functions", function_name, len(functions))
        except Exception as e:
            logger.warning("Failed to lookup function %s: %s", function_name, e)
            return []
        results = []
        for func in functions:
            content_parts = [
                f"Function: {func.name}",
                f"File: {func.file_path}:{func.start_line}-{func.end_line}",
                f"Signature: {func.signature}",
            ]
            if func.return_type:
                content_parts.append(f"Returns: {func.return_type}")
            if func.class_name:
                content_parts.append(f"Class: {func.class_name}")
            if func.docstring:
                content_parts.append(f"Doc: {func.docstring[:100]}...")
            if include_source:
                source = index.get_function_source(func.name)
                if source:
                    if max_source_length > 0:
                        from srcs.llm.token_utils import truncate_if_needed

                        source = truncate_if_needed(
                            source, max_tokens=max_source_length // 4, label=f"function source:{func.name}"
                        )
                    content_parts.append(f"Source:\n{source}")
            results.append(
                EvidenceItem(
                    evidence_type="code",
                    content="\n".join(content_parts),
                    source=f"function:{func.name}@{func.file_path}:{func.start_line}",
                    strength="STRONG",
                )
            )
        return results

    async def lookup_class(self, class_name: str, include_source: bool = True) -> list[EvidenceItem]:
        index = self._ensure_index()
        if index is None:
            return []
        try:
            classes = index.find_class(class_name)
        except Exception as e:
            logger.warning("Failed to lookup class %s: %s", class_name, e)
            return []
        results = []
        for cls in classes:
            content_parts = [
                f"Class: {cls.name}",
                f"File: {cls.file_path}:{cls.start_line}-{cls.end_line}",
                f"Signature: {cls.signature}",
            ]
            if cls.base_classes:
                content_parts.append(f"Base classes: {', '.join(cls.base_classes)}")
            if cls.methods:
                content_parts.append(f"Methods: {', '.join(cls.methods[:10])}")
                if len(cls.methods) > 10:
                    content_parts.append(f"  ... and {len(cls.methods) - 10} more")
            if include_source:
                source = index.get_class_source(cls.name)
                if source:
                    content_parts.append(f"Source:\n{source}")
            results.append(
                EvidenceItem(
                    evidence_type="code",
                    content="\n".join(content_parts),
                    source=f"class:{cls.name}@{cls.file_path}:{cls.start_line}",
                    strength="STRONG",
                )
            )
        return results

    async def search_symbols(self, query: str, symbol_type: str | None = None, limit: int = 20) -> list[EvidenceItem]:
        index = self._ensure_index()
        if index is None:
            return []
        try:
            symbols = index.search_symbols(query, symbol_type)
        except Exception as e:
            logger.warning("Failed to search symbols for %s: %s", query, e)
            return []
        results = []
        for symbol in symbols[:limit]:
            results.append(
                EvidenceItem(
                    evidence_type="code",
                    content=f"Symbol: {symbol['name']} ({symbol['type']})\nFile: {symbol['file']}:{symbol['line']}\nContext: {symbol.get('context', 'N/A')}",
                    source=f"symbol:{symbol['name']}@{symbol['file']}:{symbol['line']}",
                    strength="MODERATE",
                )
            )
        return results

    async def get_code_context(
        self, file_path: str | Path, line_number: int, context_lines: int = 10
    ) -> EvidenceItem | None:
        file_path = Path(file_path)
        if not file_path.exists():
            return None
        try:
            if self._source_roots:
                file_path = validate_path(file_path, self._source_roots)
        except ValueError:
            logger.warning("Path validation failed for %s", file_path)
            return None
        try:
            parsed = self._parser.parse_file(file_path)
            lines, enclosing_func = self._extractor.get_context_around_line(parsed, line_number, context_lines)
        except Exception as e:
            logger.warning("Failed to get code context for %s:%s: %s", file_path, line_number, e)
            return None
        content_parts = [f"File: {file_path}:{line_number}"]
        if enclosing_func:
            content_parts.append(f"Enclosing function: {enclosing_func.name}")
            content_parts.append(f"Function signature: {enclosing_func.signature}")
        start_line = max(1, line_number - context_lines)
        numbered_lines = []
        for i, line in enumerate(lines):
            ln = start_line + i
            marker = ">>>" if ln == line_number else "   "
            numbered_lines.append(f"{marker} {ln:4d}: {line}")
        content_parts.append("Code:\n" + "\n".join(numbered_lines))
        return EvidenceItem(
            evidence_type="code",
            content="\n".join(content_parts),
            source=f"code_context:{file_path}:{line_number}",
            strength="STRONG" if enclosing_func else "MODERATE",
        )

    async def find_function_calls(self, function_name: str, file_path: str | Path | None = None) -> list[EvidenceItem]:
        results = []
        if file_path:
            file_path = Path(file_path)
            if not file_path.exists():
                return []
            try:
                if self._source_roots:
                    file_path = validate_path(file_path, self._source_roots)
            except ValueError:
                logger.warning("Path validation failed for %s", file_path)
                return []
            try:
                parsed = self._parser.parse_file(file_path)
                call_lines = self._extractor.find_function_calls(parsed, function_name)
                for line in call_lines:
                    code_line = parsed.get_line(line)
                    results.append(
                        EvidenceItem(
                            evidence_type="code",
                            content=f"Call to {function_name} at {file_path}:{line}\n  {code_line}",
                            source=f"function_call:{function_name}@{file_path}:{line}",
                            strength="MODERATE",
                        )
                    )
            except Exception as e:
                logger.warning("Failed to find calls to %s in %s: %s", function_name, file_path, e)
        else:
            index = self._ensure_index()
            if index is None:
                return []
            try:
                stats = index.get_stats()
                if stats["files"] == 0:
                    return []
                symbols = index.search_symbols(f"%{function_name}%", symbol_type="function")
                for symbol in symbols[:5]:
                    results.append(
                        EvidenceItem(
                            evidence_type="code",
                            content=f"Function definition: {symbol['name']}\nFile: {symbol['file']}:{symbol['line']}\nContext: {symbol.get('context', 'N/A')}",
                            source=f"function_def:{symbol['name']}@{symbol['file']}:{symbol['line']}",
                            strength="STRONG",
                        )
                    )
                call_pattern = re.compile(f"(?:^|[^\\w:])(?:\\w+::)*{re.escape(function_name)}\\s*\\(", re.MULTILINE)
                files_searched = 0
                max_files = 50
                for source_root in self._source_roots:
                    if files_searched >= max_files:
                        break
                    extensions = [".cpp", ".cxx", ".cc", ".c", ".h", ".hpp", ".py"]
                    for ext in extensions:
                        for source_file in source_root.rglob(f"*{ext}"):
                            if files_searched >= max_files:
                                break
                            try:
                                validate_path(source_file, self._source_roots)
                                file_content = await asyncio.to_thread(source_file.read_text, errors="ignore")
                                file_lines = file_content.split("\n")
                                for line_num, line_text in enumerate(file_lines, 1):
                                    if call_pattern.search(line_text):
                                        is_definition = any(
                                            (
                                                s["file"] == str(source_file) and abs(s["line"] - line_num) < 3
                                                for s in symbols
                                            )
                                        )
                                        if not is_definition:
                                            results.append(
                                                EvidenceItem(
                                                    evidence_type="code",
                                                    content=f"Call site: {function_name}\nFile: {source_file}:{line_num}\nLine: {line_text.strip()}",
                                                    source=f"call_site:{function_name}@{source_file}:{line_num}",
                                                    strength="MODERATE",
                                                )
                                            )
                                files_searched += 1
                            except ValueError:
                                logger.debug("Path validation failed for %s", source_file)
                            except Exception as e:
                                logger.debug("Failed to search %s: %s", source_file, e)
            except Exception as e:
                logger.warning("Failed to find calls to %s: %s", function_name, e)
        return results[:20]

    async def get_index_stats(self) -> dict:
        index = self._ensure_index()
        if index is None:
            return {"files": 0, "functions": 0, "classes": 0, "symbols": 0}
        return index.get_stats()

    async def get_log_source(self, log_message: str, component: str | None = None) -> list[EvidenceItem]:
        index = self._ensure_index()
        results = []
        quoted_strings = re.findall('"([^"]+)"', log_message)
        quoted_strings.extend(re.findall("'([^']+)'", log_message))
        static_segments = re.split(
            "\\b(?:\\d+|0x[0-9a-fA-F]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\\b",
            log_message,
        )
        static_segments = [s.strip() for s in static_segments if len(s.strip()) >= 10]
        static_segments.sort(key=len, reverse=True)
        quoted_strings.extend(static_segments[:2])
        cpp_func_pattern = "\\b([A-Za-z_]\\w*(?:::[A-Za-z_]\\w*)+)\\s*\\("
        cpp_functions = re.findall(cpp_func_pattern, log_message)
        for cpp_func in cpp_functions:
            parts = cpp_func.split("::")
            if len(parts) >= 2:
                quoted_strings.append(parts[-1])
                quoted_strings.append(parts[-2])
        artdaq_log_patterns = [
            "TLOG\\s*\\(",
            "TLOG_\\w+\\s*\\(",
            "TLOG_DEBUG\\s*\\(",
            "TLOG_INFO\\s*\\(",
            "TLOG_WARNING\\s*\\(",
            "TLOG_ERROR\\s*\\(",
            "mf::Log\\w*\\s*\\(",
            "mf::LogDebug\\s*\\(",
            "mf::LogInfo\\s*\\(",
            "mf::LogWarning\\s*\\(",
            "mf::LogError\\s*\\(",
            "mf::LogAbsolute\\s*\\(",
            "mf::LogProblem\\s*\\(",
            "mf::LogPrint\\s*\\(",
            "mf::LogSystem\\s*\\(",
            "mf::LogVerbatim\\s*\\(",
            "TRACE\\s*\\(",
            "TRACE_\\w+\\s*\\(",
            "TRACEN\\s*\\(",
            "LOG_\\w+\\s*\\(",
            "LOG_DEBUG\\s*\\(",
            "LOG_INFO\\s*\\(",
            "LOG_WARNING\\s*\\(",
            "LOG_ERROR\\s*\\(",
            "art::Exception\\s*\\(",
            "cet::exception\\s*\\(",
        ]
        search_terms = quoted_strings[:5]
        identifiers = re.findall("\\b([A-Z][a-zA-Z0-9_]+)\\b", log_message)
        search_terms.extend(identifiers[:2])
        for cpp_func in cpp_functions:
            func_results = await self.lookup_function(cpp_func.split("::")[-1])
            for fr in func_results[:3]:
                results.append(
                    EvidenceItem(
                        evidence_type="log_source",
                        content=f"Function from error message: {fr.content}",
                        source=fr.source.replace("function:", "log_source_func:"),
                        strength="STRONG",
                    )
                )
        if index is not None:
            for term in search_terms:
                if len(term) < 4:
                    continue
                try:
                    symbols = index.search_symbols(f"%{term}%", symbol_type=None)
                    for symbol in symbols[:5]:
                        context_item = await self.get_code_context(symbol["file"], symbol["line"], context_lines=5)
                        if context_item:
                            results.append(
                                EvidenceItem(
                                    evidence_type="log_source",
                                    content=f"Log source for '{term}':\nFile: {symbol['file']}:{symbol['line']}\nContext: {symbol.get('context', 'N/A')}",
                                    source=f"log_source:{symbol['file']}:{symbol['line']}",
                                    strength="STRONG",
                                )
                            )
                except Exception as e:
                    logger.debug("Failed to search for log source '%s': %s", term, e)
        files_searched = 0
        max_files = 30
        log_macro_pattern = re.compile("|".join(artdaq_log_patterns), re.IGNORECASE)
        for source_root in self._source_roots:
            if files_searched >= max_files:
                break
            extensions = [".cpp", ".cxx", ".cc", ".c", ".h", ".hpp"]
            for ext in extensions:
                for source_file in source_root.rglob(f"*{ext}"):
                    if files_searched >= max_files:
                        break
                    if component and component.lower() not in str(source_file).lower():
                        continue
                    try:
                        validate_path(source_file, self._source_roots)
                        content = await asyncio.to_thread(source_file.read_text, errors="ignore")
                        lines = content.split("\n")
                        for line_num, line in enumerate(lines, 1):
                            if log_macro_pattern.search(line):
                                term_found = None
                                for term in search_terms:
                                    if len(term) >= 4 and term.lower() in line.lower():
                                        term_found = term
                                        break
                                if term_found:
                                    start_idx = max(0, line_num - 3)
                                    end_idx = min(len(lines), line_num + 3)
                                    context_lines_list = lines[start_idx:end_idx]
                                    results.append(
                                        EvidenceItem(
                                            evidence_type="log_source",
                                            content=f"artdaq log statement for '{term_found}':\nFile: {source_file}:{line_num}\nContext:\n"
                                            + "\n".join(
                                                (
                                                    f"  {start_idx + idx + 1}: {ctx_line}"
                                                    for idx, ctx_line in enumerate(context_lines_list)
                                                )
                                            ),
                                            source=f"log_source:{source_file}:{line_num}",
                                            strength="STRONG",
                                        )
                                    )
                        files_searched += 1
                    except ValueError:
                        logger.debug("Path validation failed for %s", source_file)
                    except Exception as e:
                        logger.debug("Failed to search %s: %s", source_file, e)
        return results[:15]

    async def find_related_functions(
        self, description: str, n: int = 10, chroma_store: "ChromaStore | None" = None
    ) -> list[EvidenceItem]:
        results: list[EvidenceItem] = []
        if chroma_store is None:
            logger.debug("No ChromaStore available for semantic function search")
            return results
        try:
            similar_funcs = await chroma_store.find_similar_functions(description, n)
            for func_info in similar_funcs:
                file_path = func_info.get("file_path")
                start_line = func_info.get("start_line")
                content_parts = [
                    f"Function: {func_info.get('function_name', 'Unknown')}",
                    f"Summary: {func_info.get('summary', 'No summary')}",
                    f"Similarity: {func_info.get('similarity', 0):.2%}",
                ]
                if file_path:
                    content_parts.append(f"File: {file_path}")
                if start_line:
                    content_parts.append(f"Line: {start_line}")
                if func_info.get("signature"):
                    content_parts.append(f"Signature: {func_info['signature']}")
                if func_info.get("class_name"):
                    content_parts.append(f"Class: {func_info['class_name']}")
                if file_path and start_line:
                    context_item = await self.get_code_context(file_path, start_line, context_lines=5)
                    if context_item:
                        content_parts.append(f"\nSource:\n{context_item.content}")
                similarity = func_info.get("similarity", 0)
                if similarity > 0.7:
                    strength = "STRONG"
                elif similarity > 0.4:
                    strength = "MODERATE"
                else:
                    strength = "WEAK"
                results.append(
                    EvidenceItem(
                        evidence_type="code",
                        content="\n".join(content_parts),
                        source=f"semantic_function:{func_info.get('function_id', 'unknown')}",
                        strength=strength,
                    )
                )
        except Exception as e:
            logger.warning("Failed to find related functions for '%s': %s", description, e)
        return results

    async def find_error_source(
        self,
        error_message: str,
        component: str | None = None,
        max_results: int = 5,
        chroma_store: "ChromaStore | None" = None,
    ) -> list[EvidenceItem]:
        index = self._ensure_index()
        locator = SourceLocator(source_roots=self._source_roots, code_index=index, chroma_store=chroma_store)
        try:
            result = await locator.find_source(error_message, max_results=max_results, component=component)
        except Exception as e:
            logger.warning("Failed to find error source for '%s': %s", error_message, e)
            return []
        evidence = []
        for loc in result.locations:
            context_str = "\n".join(
                (f"  {line}" for line in loc.context_before + [f">>> {loc.matched_line}"] + loc.context_after)
            )
            caller_count = len(loc.callers) if loc.callers else 0
            callee_count = len(loc.callees) if loc.callees else 0
            content = f"Source: {loc.file_path}:{loc.line_number}\nFunction: {loc.function_name or 'Unknown'}\nSignature: {loc.function_signature or 'Unknown'}\nClass: {loc.class_name or 'N/A'}\nIs log statement: {loc.is_log_statement}\n\nMatched Line:\n  {loc.matched_line}\n\nContext:\n{context_str}\n\nSummary: {loc.function_summary or 'No summary available'}\n\nCall Graph:\n  Callers: {caller_count} functions call this\n  Callees: {callee_count} functions called by this"
            if loc.callers:
                caller_details = "\n".join(
                    (
                        f"    - {c.get('caller_name', 'unknown')} ({c.get('caller_file', 'unknown')}:{c.get('call_line', '?')})"
                        for c in loc.callers[:5]
                    )
                )
                content += f"\n  Top callers:\n{caller_details}"
            if loc.function_body:
                content += f"\n\nFunction Body:\n```cpp\n{loc.function_body}\n```"
            if loc.match_score > 0.7 and loc.is_log_statement:
                strength = "STRONG"
            elif loc.match_score > 0.4 or loc.is_log_statement:
                strength = "MODERATE"
            else:
                strength = "WEAK"
            evidence.append(
                EvidenceItem(
                    evidence_type="source_location",
                    content=content,
                    source=f"source_locator:{loc.file_path}:{loc.line_number}",
                    strength=strength,
                )
            )
        return evidence
