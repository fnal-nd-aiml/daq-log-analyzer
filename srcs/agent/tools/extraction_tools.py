"""
File: extraction_tools.py
Purpose: Unified tools for code extraction, parsing, and analysis.
Category: Utility
Author: artdaq team
Depends: extraction, source_locator, summarizer, chroma_store, llm, ...
Exports: ExtractionTools
Complexity: High | Lines: 307
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from srcs.extraction import CodeExtractor, CodeIndex, CodeParser
from srcs.extraction.source_locator import SourceLocator
from srcs.extraction.summarizer import FunctionSummarizer
from .base import logger, validate_path

if TYPE_CHECKING:
    from srcs.knowledge.chroma_store import ChromaStore
    from srcs.llm import LLMProvider


class ExtractionTools:

    def __init__(
        self,
        source_roots: list[Path] | None = None,
        code_index: CodeIndex | None = None,
        llm_provider: "LLMProvider | None" = None,
        chroma_store: "ChromaStore | None" = None,
    ):
        self._source_roots = source_roots or []
        self._index = code_index
        self._llm = llm_provider
        self._chroma = chroma_store
        self._parser = CodeParser()
        self._extractor = CodeExtractor(self._parser)
        self._locator: SourceLocator | None = None
        self._summarizer: FunctionSummarizer | None = None

    def _ensure_locator(self) -> SourceLocator | None:
        if self._locator is None and self._source_roots:
            self._locator = SourceLocator(
                source_roots=self._source_roots, code_index=self._index, chroma_store=self._chroma
            )
        return self._locator

    def _ensure_summarizer(self) -> FunctionSummarizer | None:
        if self._summarizer is None and self._llm:
            self._summarizer = FunctionSummarizer(self._llm)
        return self._summarizer

    async def find_error_source(
        self, error_message: str, component: str | None = None, max_results: int = 5
    ) -> list[dict]:
        locator = self._ensure_locator()
        if not locator:
            return [{"error": "No source roots configured"}]
        result = await locator.find_source(error_message, max_results=max_results, component=component)
        return [
            {
                "file_path": loc.file_path,
                "line_number": loc.line_number,
                "matched_line": loc.matched_line,
                "function_name": loc.function_name,
                "function_signature": loc.function_signature,
                "function_body": loc.function_body,
                "match_score": loc.match_score,
                "is_log_statement": loc.is_log_statement,
                "context_before": loc.context_before,
                "context_after": loc.context_after,
                "callers": loc.callers,
                "callees": loc.callees,
            }
            for loc in result.locations
        ]

    async def get_source_context(self, file_path: str, line_number: int, context_lines: int = 10) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        try:
            if self._source_roots:
                path = validate_path(path, self._source_roots)
        except ValueError:
            return {"error": f"Path {file_path} is outside allowed source roots"}
        try:
            content = await asyncio.to_thread(path.read_text, errors="ignore")
        except Exception as e:
            return {"error": f"Failed to read file: {e}"}
        lines = content.split("\n")
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        result = {
            "file_path": file_path,
            "line_number": line_number,
            "line": lines[line_number - 1] if line_number <= len(lines) else "",
            "context_before": lines[start : line_number - 1],
            "context_after": lines[line_number:end],
        }
        if self._index:
            funcs = self._index.find_function("%", file_filter=file_path)
            for func in funcs:
                if func.start_line <= line_number <= func.end_line:
                    result["function_name"] = func.name
                    result["function_signature"] = func.signature
                    break
        return result

    async def summarize_function(self, source: str, name: str, file_path: str = "", language: str = "cpp") -> str:
        summarizer = self._ensure_summarizer()
        if not summarizer:
            return f"Function {name} (no LLM available for summary)"
        return await summarizer.summarize_function(source=source, name=name, file_path=file_path, language=language)

    async def batch_summarize(self, functions: list[dict], language: str = "cpp") -> dict[str, str]:
        summarizer = self._ensure_summarizer()
        if not summarizer:
            return {f["name"]: f"Function {f['name']}" for f in functions}
        results = {}
        for func in functions:
            try:
                summary = await summarizer.summarize_function(
                    source=func.get("source", ""),
                    name=func["name"],
                    file_path=func.get("file_path", ""),
                    language=language,
                )
                results[func["name"]] = summary
            except Exception as e:
                logger.debug(f"Failed to summarize {func['name']}: {e}")
                results[func["name"]] = f"Function {func['name']}"
        return results

    async def lookup_function(self, name: str, include_source: bool = True, max_source_length: int = 0) -> list[dict]:
        if not self._index:
            return [{"error": "No code index available"}]
        functions = self._index.find_function(name)
        results = []
        for func in functions:
            result = {
                "name": func.name,
                "file_path": str(func.file_path),
                "start_line": func.start_line,
                "end_line": func.end_line,
                "signature": func.signature,
                "return_type": func.return_type,
                "parameters": func.parameters,
                "class_name": func.class_name,
                "docstring": func.docstring,
            }
            if include_source:
                source = self._index.get_function_source(func.name)
                if source and max_source_length > 0:
                    from srcs.llm.token_utils import truncate_if_needed

                    source = truncate_if_needed(
                        source, max_tokens=max_source_length // 4, label=f"extraction source:{func.name}"
                    )
                result["source"] = source
            results.append(result)
        return results

    async def lookup_class(self, name: str, include_source: bool = True) -> list[dict]:
        if not self._index:
            return [{"error": "No code index available"}]
        classes = self._index.find_class(name)
        results = []
        for cls in classes:
            result = {
                "name": cls.name,
                "file_path": str(cls.file_path),
                "start_line": cls.start_line,
                "end_line": cls.end_line,
                "signature": cls.signature,
                "base_classes": cls.base_classes,
                "methods": cls.methods,
            }
            if include_source:
                result["source"] = self._index.get_class_source(cls.name)
            results.append(result)
        return results

    async def get_function_source(self, name: str) -> str | None:
        if not self._index:
            return None
        return self._index.get_function_source(name)

    async def get_callers(self, function_name: str) -> list[dict]:
        if not self._index:
            return []
        return self._index.get_callers(function_name)

    async def get_callees(self, function_name: str) -> list[dict]:
        if not self._index:
            return []
        return self._index.get_callees(function_name)

    async def get_call_chain(self, function_name: str, direction: str = "callers", depth: int = 3) -> dict:
        if not self._index:
            return {"name": function_name, "children": [], "error": "No index"}
        return self._index.get_call_chain(function_name, direction, depth)

    async def search_symbols(self, query: str, symbol_type: str | None = None) -> list[dict]:
        if not self._index:
            return []
        return self._index.search_symbols(query, symbol_type)

    async def get_file_dependencies(self, file_path: str) -> list[dict]:
        if not self._index:
            return []
        return self._index.get_file_dependencies(file_path)

    async def parse_file(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        try:
            if self._source_roots:
                path = validate_path(path, self._source_roots)
        except ValueError:
            return {"error": f"Path {file_path} is outside allowed source roots"}
        try:
            parsed = self._parser.parse_file(path)
        except Exception as e:
            return {"error": f"Failed to parse file: {e}"}
        func_count = 0
        class_count = 0
        if parsed.root:
            func_count = len(parsed.root.find_all("function_definition"))
            class_count = len(parsed.root.find_all("class_specifier"))
            class_count += len(parsed.root.find_all("class_definition"))
        return {
            "file_path": file_path,
            "language": parsed.language,
            "has_errors": parsed.has_errors,
            "errors": parsed.errors,
            "function_count": func_count,
            "class_count": class_count,
        }

    async def extract_functions(self, file_path: str) -> list[dict]:
        path = Path(file_path)
        if not path.exists():
            return [{"error": f"File not found: {file_path}"}]
        try:
            if self._source_roots:
                path = validate_path(path, self._source_roots)
        except ValueError:
            return [{"error": f"Path {file_path} is outside allowed source roots"}]
        try:
            result = self._extractor.extract_from_file(path)
        except Exception as e:
            return [{"error": f"Failed to extract functions: {e}"}]
        return [
            {
                "name": f.name,
                "signature": f.signature,
                "start_line": f.start_line,
                "end_line": f.end_line,
                "return_type": f.return_type,
                "parameters": f.parameters,
                "class_name": f.class_name,
            }
            for f in result.get("functions", [])
        ]

    async def extract_classes(self, file_path: str) -> list[dict]:
        path = Path(file_path)
        if not path.exists():
            return [{"error": f"File not found: {file_path}"}]
        try:
            if self._source_roots:
                path = validate_path(path, self._source_roots)
        except ValueError:
            return [{"error": f"Path {file_path} is outside allowed source roots"}]
        try:
            result = self._extractor.extract_from_file(path)
        except Exception as e:
            return [{"error": f"Failed to extract classes: {e}"}]
        return [
            {
                "name": c.name,
                "signature": c.signature,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "base_classes": c.base_classes,
                "methods": c.methods,
            }
            for c in result.get("classes", [])
        ]

    async def find_node_at_line(
        self, file_path: str, line_number: int, node_type: str = "function_definition"
    ) -> dict | None:
        path = Path(file_path)
        if not path.exists():
            return None
        try:
            if self._source_roots:
                path = validate_path(path, self._source_roots)
        except ValueError:
            logger.warning(f"Path validation failed for {file_path}")
            return None
        try:
            parsed = self._parser.parse_file(path)
        except Exception as e:
            logger.debug(f"Failed to parse {file_path}: {e}")
            return None
        if not parsed.root:
            return None
        for node in parsed.root.find_all(node_type):
            if node.start_line <= line_number <= node.end_line:
                text = node.text
                return {"type": node.type, "start_line": node.start_line, "end_line": node.end_line, "text": text}
        return None
