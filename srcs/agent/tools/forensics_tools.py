"""
File: forensics_tools.py
Purpose: Deep code forensics and dataflow analysis tools.
Category: Utility
Author: artdaq team
Depends: dataflow, extraction, models, source_location, source
Exports: CodeForensicsTools
Complexity: Medium | Lines: 210
"""

import re
from pathlib import Path
from srcs.extraction import CodeIndex, CodeIndexConfig
from srcs.models import EvidenceItem
from srcs.source import RepositoryManager, SourceConfig
from .base import logger, make_evidence, strength_from_confidence


class CodeForensicsTools:

    def __init__(
        self,
        code_index: CodeIndex | None = None,
        source_roots: list[Path] | None = None,
        source_config: SourceConfig | None = None,
    ):
        self._code_index = code_index
        self._source_roots = source_roots or []
        self._source_config = source_config
        if source_config and source_config.has_repositories():
            manager = RepositoryManager(source_config)
            repo_paths = manager.get_existing_repo_paths()
            for path in repo_paths:
                if path not in self._source_roots:
                    self._source_roots.append(path)
        from srcs.agent.dataflow import DataflowTracer

        self._dataflow_tracer = DataflowTracer(code_index, self._source_roots)

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

    async def trace_variable(
        self, variable_name: str, file_path: str, line_number: int, max_depth: int = 5
    ) -> list[EvidenceItem]:
        from srcs.models.source_location import SourceLocation

        results = []
        index = self._ensure_index()
        source_location = SourceLocation(file_path=file_path, line_number=line_number, matched_line="")
        if index:
            func_info = self._find_enclosing_function(file_path, line_number, index)
            if func_info:
                source_location.function_name = func_info.get("name")
                source_location.function_body = index.get_function_source(func_info.get("name", ""))
        try:
            chain = await self._dataflow_tracer.trace_variable(variable_name, source_location, max_depth)
            for i, node in enumerate(chain.nodes):
                content = f"Dataflow Step {i + 1}:\nFunction: {node.function_name}\nFile: {node.file_path}:{node.line_number}\nVariable: {node.variable_name}\nSource: {node.data_source}"
                if node.data_type:
                    content += f"\nType: {node.data_type}"
                strength = "STRONG" if node.is_error_point else "MODERATE"
                results.append(
                    make_evidence(
                        evidence_type="dataflow",
                        content=content,
                        source=f"dataflow:{node.function_name}:{node.variable_name}",
                        strength=strength,
                    )
                )
            if chain.root_source:
                results.append(
                    make_evidence(
                        evidence_type="dataflow",
                        content=f"Root data source identified: {chain.root_source}\nConfidence: {chain.confidence:.0%}",
                        source=f"dataflow:root:{chain.root_source}",
                        strength=strength_from_confidence(chain.confidence),
                    )
                )
        except Exception as e:
            logger.warning("Failed to trace variable %s: %s", variable_name, e)
        return results

    async def find_error_path(self, function_name: str, max_depth: int = 10) -> list[EvidenceItem]:
        results = []
        index = self._ensure_index()
        if not index:
            return []
        try:
            functions = index.find_function(function_name)
            if not functions:
                return []
            func = functions[0]
            source = index.get_function_source(function_name)
            if not source:
                return []
            error_patterns = [
                ("throw\\s+\\w+", "exception_throw"),
                ("return\\s+(?:nullptr|NULL|false|0)\\s*;", "error_return"),
                ("if\\s*\\([^)]*==\\s*nullptr", "null_check"),
                ("if\\s*\\(\\s*!\\s*\\w+\\s*\\)", "falsy_check"),
                ("(?:TLOG|LOG|mf::Log)(?:Error|Warning)", "error_log"),
                ("assert\\s*\\(", "assertion"),
            ]
            error_paths: list[dict[str, str | int]] = []
            lines = source.split("\n")
            for i, line in enumerate(lines, 1):
                for pattern, path_type in error_patterns:
                    if re.search(pattern, line):
                        error_paths.append({"line": i, "type": path_type, "code": line.strip()})
            if error_paths:
                content_parts = [f"Error paths in {function_name}:", f"File: {func.file_path}", ""]
                for path in error_paths[:10]:
                    path_line = path["line"]
                    path_type_str = str(path["type"])
                    path_code = str(path["code"])[:80]
                    content_parts.append(f"  Line {path_line} [{path_type_str}]: {path_code}")
                results.append(
                    make_evidence(
                        evidence_type="error_path",
                        content="\n".join(content_parts),
                        source=f"error_path:{function_name}",
                        strength="STRONG",
                    )
                )
        except Exception as e:
            logger.warning("Failed to find error paths in %s: %s", function_name, e)
        return results

    async def get_caller_chain(self, function_name: str, max_depth: int = 5) -> list[EvidenceItem]:
        results = []
        index = self._ensure_index()
        if not index:
            return []
        try:
            callers = index.get_callers(function_name)
            if not callers:
                results.append(
                    make_evidence(
                        evidence_type="caller_chain",
                        content=f"No callers found for {function_name} (may be entry point or external)",
                        source=f"caller_chain:{function_name}",
                        strength="WEAK",
                    )
                )
                return results
            chain: list[dict[str, str | int | list[dict]]] = [{"name": function_name, "depth": 0, "callers": callers}]
            visited = {function_name}
            current_depth = 1
            to_process: list[tuple[str, int]] = [
                (c.get("caller_name", c.get("name", "")), current_depth)
                for c in callers
                if c.get("caller_name") or c.get("name")
            ]
            while to_process and current_depth < max_depth:
                func_name, depth = to_process.pop(0)
                if func_name in visited or not func_name:
                    continue
                visited.add(func_name)
                upstream_callers = index.get_callers(func_name)
                chain.append({"name": func_name, "depth": depth, "callers": upstream_callers})
                for caller in upstream_callers:
                    caller_name = caller.get("caller_name", caller.get("name", ""))
                    if caller_name and caller_name not in visited:
                        to_process.append((caller_name, depth + 1))
                current_depth = max(current_depth, depth + 1)
            content_parts = [f"Caller chain for {function_name}:", ""]

            def get_depth(entry: dict[str, str | int | list[dict]]) -> int:
                d = entry.get("depth", 0)
                return int(d) if isinstance(d, (int, str)) else 0

            for entry in sorted(chain, key=get_depth):
                depth_val = get_depth(entry)
                indent = "  " * depth_val
                entry_callers = entry.get("callers")
                if isinstance(entry_callers, list):
                    caller_names = [c.get("caller_name", c.get("name", "?")) for c in entry_callers[:3]]
                else:
                    caller_names = []
                caller_str = ", ".join(caller_names) if caller_names else "(none)"
                content_parts.append(f"{indent}{entry['name']} <- called by: {caller_str}")
            results.append(
                make_evidence(
                    evidence_type="caller_chain",
                    content="\n".join(content_parts),
                    source=f"caller_chain:{function_name}",
                    strength="STRONG",
                )
            )
        except Exception as e:
            logger.warning("Failed to get caller chain for %s: %s", function_name, e)
        return results

    def _find_enclosing_function(self, file_path: str, line_num: int, index: CodeIndex) -> dict | None:
        try:
            functions = index.find_function("%", file_filter=file_path)
            for func in functions:
                if func.start_line <= line_num <= func.end_line:
                    return {
                        "name": func.name,
                        "signature": func.signature,
                        "start_line": func.start_line,
                        "end_line": func.end_line,
                        "class_name": func.class_name,
                    }
        except Exception as e:
            logger.debug("Failed to find enclosing function: %s", e)
        return None
