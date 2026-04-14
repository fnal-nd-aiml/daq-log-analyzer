"""
File: code_tools.py
Purpose: Code analysis tools for the agentic API.
Category: Utility
Author: artdaq team
Depends: source_locator, summarizer, llm
Exports: find_error_source, lookup_function, get_call_graph, summarize_function, search_code
Complexity: Medium | Lines: 217
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
from ..dependencies import get_code_index, get_settings, get_source_config
from ..errors import validation_error
from .router import ToolContext, register_tool

logger = logging.getLogger(__name__)


def _get_code_index_or_error() -> Any:
    settings = get_settings()
    index = get_code_index(settings)
    if index is None:
        raise validation_error(
            "Code index not available. Run init_knowledge_base with source sync first.",
            {"recovery_hint": "POST /api/v1/agent/tools/init_knowledge_base"},
        )
    return index


@register_tool("find_error_source")
async def find_error_source(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    error_message = params.get("error_message")
    if not error_message:
        raise validation_error("'error_message' is required for find_error_source.")
    settings = get_settings()
    index = get_code_index(settings)
    source_config = get_source_config(settings)
    from srcs.extraction.source_locator import SourceLocator

    source_roots: list[Path] = []
    if source_config:
        repos_path = Path(source_config.repos_path)
        if repos_path.exists():
            source_roots = [p for p in repos_path.iterdir() if p.is_dir()]
    locator = SourceLocator(source_roots=source_roots, code_index=index)
    result = await locator.find_source(error_message)
    locations = []
    for loc in result.locations:
        locations.append(
            {
                "file": str(loc.file_path),
                "line": loc.line_number,
                "score": loc.score,
                "context": loc.context,
                "function": loc.function_name,
            }
        )
    return {
        "locations": locations,
        "search_patterns": result.search_patterns,
        "best_match": (
            {
                "file": str(result.best_match.file_path),
                "line": result.best_match.line_number,
                "score": result.best_match.score,
                "function": result.best_match.function_name,
            }
            if result.best_match
            else None
        ),
    }


@register_tool("lookup_function")
async def lookup_function(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    name = params.get("name")
    if not name:
        raise validation_error("'name' is required for lookup_function.")
    index = _get_code_index_or_error()
    file_filter = params.get("file_filter")
    functions = index.find_function(name, file_filter=file_filter)
    return {
        "functions": [
            {
                "name": f.name,
                "file_path": str(f.file_path),
                "start_line": f.start_line,
                "end_line": f.end_line,
                "signature": f.signature,
                "return_type": f.return_type,
                "parameters": f.parameters,
                "class_name": f.class_name,
            }
            for f in functions
        ],
        "total": len(functions),
    }


@register_tool("get_call_graph")
async def get_call_graph(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    name = params.get("name")
    if not name:
        raise validation_error("'name' is required for get_call_graph.")
    index = _get_code_index_or_error()
    depth = params.get("depth", 1)
    direction = params.get("direction", "both")
    result: dict[str, Any] = {"function": name}
    if direction in ("callers", "both"):
        callers = index.get_callers(name, max_depth=depth)
        result["callers"] = [
            {
                "name": c.name,
                "file_path": str(c.file_path) if hasattr(c, "file_path") else None,
                "depth": c.depth if hasattr(c, "depth") else 1,
            }
            for c in callers
        ]
    if direction in ("callees", "both"):
        callees = index.get_callees(name, max_depth=depth)
        result["callees"] = [
            {
                "name": c.name,
                "file_path": str(c.file_path) if hasattr(c, "file_path") else None,
                "depth": c.depth if hasattr(c, "depth") else 1,
            }
            for c in callees
        ]
    return result


@register_tool("summarize_function")
async def summarize_function(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    name = params.get("name")
    if not name:
        raise validation_error("'name' is required for summarize_function.")
    index = _get_code_index_or_error()
    file_filter = params.get("file_filter")
    functions = index.find_function(name, file_filter=file_filter)
    if not functions:
        return {"error": f"Function '{name}' not found", "functions": [], "total": 0}
    func = functions[0]
    source = ""
    try:
        func_path = Path(func.file_path)
        if func_path.exists() and func.start_line and func.end_line:
            lines = func_path.read_text().splitlines()
            source = "\n".join(lines[func.start_line - 1 : func.end_line])
    except Exception as e:
        logger.warning("Failed to read source for %s: %s", name, e)
    if not source:
        return {
            "name": func.name,
            "file_path": str(func.file_path),
            "start_line": func.start_line,
            "end_line": func.end_line,
            "signature": func.signature,
            "summary": f"Function {name} (source unavailable)",
        }
    ext = Path(func.file_path).suffix.lower()
    lang_map = {
        ".py": "python",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".h": "cpp",
        ".hpp": "cpp",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
    }
    language = lang_map.get(ext, "cpp")
    from srcs.extraction.summarizer import FunctionSummarizer

    settings = get_settings()
    from srcs.llm import create_llm_provider
    from ..dependencies import get_llm_config

    llm_config = get_llm_config(settings)
    llm = create_llm_provider(llm_config)
    summarizer = FunctionSummarizer(llm)
    summary = await summarizer.summarize_function(source, name, str(func.file_path), language)
    return {
        "name": func.name,
        "file_path": str(func.file_path),
        "start_line": func.start_line,
        "end_line": func.end_line,
        "signature": func.signature,
        "class_name": func.class_name,
        "return_type": func.return_type,
        "summary": summary,
    }


@register_tool("search_code")
async def search_code(ctx: ToolContext) -> dict[str, Any]:
    params = ctx.request_body.get("params", {})
    query = params.get("query")
    if not query:
        raise validation_error("'query' is required for search_code.")
    index = _get_code_index_or_error()
    symbol_type = params.get("type")
    limit = params.get("limit", 20)
    results = index.search_symbols(query, symbol_type=symbol_type, limit=limit)
    return {
        "symbols": [
            {
                "name": s.name,
                "type": s.symbol_type,
                "file_path": str(s.file_path) if hasattr(s, "file_path") else None,
                "line": s.line if hasattr(s, "line") else None,
                "context": s.context if hasattr(s, "context") else None,
            }
            for s in results
        ],
        "total": len(results),
    }
