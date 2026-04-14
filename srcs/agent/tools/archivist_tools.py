"""
File: archivist_tools.py
Purpose: Archivist tools for call graph context gathering.
Category: Utility
Author: artdaq team
Depends: extraction, llm, token_utils, pydantic
Exports: FunctionDetailedSummary, FunctionSummaries, ArchivistTools
Complexity: Medium | Lines: 314
"""

from pathlib import Path
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field
from srcs.extraction import CodeIndex
from .base import logger

if TYPE_CHECKING:
    from srcs.llm import LLMProvider


class FunctionDetailedSummary(BaseModel):
    function_name: str = Field(description="Fully qualified function name")
    purpose: str = Field(description="What the function does and why it exists")
    mechanism: str = Field(description="How it works - key logic, data transformations, state changes")
    data_flow: str = Field(description="How data enters/exits, key variables, buffers, return values")
    error_paths: str = Field(description="Error handling, failure modes, exception paths")
    error_line_relevance: str = Field(
        description="How this function relates to the specific error emission line under investigation"
    )


class FunctionSummaries(BaseModel):
    summaries: list[FunctionDetailedSummary] = Field(
        default_factory=list, description="List of detailed per-function summaries"
    )


class ArchivistTools:

    def __init__(
        self,
        code_index: CodeIndex | None = None,
        llm_provider: "LLMProvider | None" = None,
        source_roots: list[Path] | None = None,
    ):
        self._index = code_index
        self._llm = llm_provider
        self._source_roots = source_roots or []

    def _truncate_body(self, body: str | None, max_chars: int) -> str | None:
        if not body:
            return None
        from srcs.llm.token_utils import truncate_middle_if_needed

        return truncate_middle_if_needed(
            body, max_tokens=max_chars // 4 if max_chars > 0 else 0, label="archivist function body"
        )

    EXCLUDED_FUNCTIONS = {
        "TLOG",
        "LOG",
        "TRACE",
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "FATAL",
        "printf",
        "fprintf",
        "sprintf",
        "snprintf",
        "vprintf",
        "vfprintf",
        "assert",
        "static_assert",
        "BOOST_ASSERT",
        "malloc",
        "free",
        "realloc",
        "calloc",
        "new",
        "delete",
        "memcpy",
        "memset",
        "memmove",
        "memcmp",
        "strlen",
        "strcpy",
        "strncpy",
        "strcmp",
        "strncmp",
        "strcat",
        "pthread_self",
        "pthread_create",
        "pthread_join",
        "pthread_mutex_lock",
        "pthread_mutex_unlock",
        "pthread_cond_wait",
        "pthread_cond_signal",
        "pthread_setschedparam",
        "pthread_getschedparam",
        "std::cout",
        "std::cerr",
        "std::endl",
        "operator<<",
        "operator>>",
    }

    def _extract_simple_name(self, full_name: str) -> str:
        if "::" in full_name:
            return full_name.split("::")[-1]
        return full_name

    def _is_excluded_function(self, name: str) -> bool:
        if not name:
            return True
        if name in self.EXCLUDED_FUNCTIONS:
            return True
        excluded_prefixes = ("pthread_", "std::", "boost::", "__")
        if any((name.startswith(p) for p in excluded_prefixes)):
            return True
        return False

    async def get_call_graph_with_bodies(
        self, function_name: str, max_callers: int = 4, max_callees: int = 4, max_body_chars: int = 0
    ) -> dict:
        if not self._index:
            return {"error": "No code index available", "center_function": function_name}
        callers_list: list[dict] = []
        callees_list: list[dict] = []
        simple_name = self._extract_simple_name(function_name)
        result: dict[str, str | list[dict]] = {
            "center_function": simple_name,
            "callers": callers_list,
            "callees": callees_list,
        }
        raw_callers = self._index.get_callers(function_name)
        if not raw_callers and simple_name != function_name:
            raw_callers = self._index.get_callers(simple_name)
        seen_callers: set[str] = set()
        for caller in raw_callers:
            caller_name = caller.get("caller_name")
            if not caller_name or caller_name in seen_callers:
                continue
            if self._is_excluded_function(caller_name):
                continue
            seen_callers.add(caller_name)
            enriched = dict(caller)
            enriched["role"] = "CALLER"
            enriched["relationship"] = f"passes data TO {simple_name}"
            if len(callers_list) < max_callers:
                body = self._index.get_function_source(caller_name)
                if max_body_chars > 0:
                    enriched["body"] = self._truncate_body(body, max_body_chars)
                else:
                    enriched["body"] = body
            else:
                enriched["body"] = None
            callers_list.append(enriched)
        raw_callees = self._index.get_callees(function_name)
        if not raw_callees and simple_name != function_name:
            raw_callees = self._index.get_callees(simple_name)
        seen_callees: set[str] = set()
        for callee in raw_callees:
            callee_name = callee.get("callee_name")
            if not callee_name or callee_name in seen_callees:
                continue
            if self._is_excluded_function(callee_name):
                continue
            seen_callees.add(callee_name)
            enriched = dict(callee)
            enriched["role"] = "CALLEE"
            enriched["relationship"] = f"receives data FROM {simple_name}"
            if len(callees_list) < max_callees:
                body = self._index.get_function_source(callee_name)
                if max_body_chars > 0:
                    enriched["body"] = self._truncate_body(body, max_body_chars)
                else:
                    enriched["body"] = body
                funcs = self._index.find_function(callee_name)
                if funcs:
                    enriched["callee_file"] = str(funcs[0].file_path)
                    enriched["callee_signature"] = funcs[0].signature
            else:
                enriched["body"] = None
            callees_list.append(enriched)
        return result

    async def summarize_call_graph(
        self,
        call_graph: dict,
        error_context: str | None = None,
        error_file: str | None = None,
        error_line: int | None = None,
    ) -> list[FunctionDetailedSummary]:
        if not self._llm:
            return []
        functions_to_summarize = []
        for caller in call_graph.get("callers", []):
            if caller.get("body"):
                functions_to_summarize.append(
                    {
                        "name": caller.get("caller_name"),
                        "body": caller["body"],
                        "role": "CALLER",
                        "file": caller.get("caller_file", ""),
                    }
                )
        for callee in call_graph.get("callees", []):
            if callee.get("body"):
                functions_to_summarize.append(
                    {
                        "name": callee.get("callee_name"),
                        "body": callee["body"],
                        "role": "CALLEE",
                        "file": callee.get("callee_file", ""),
                    }
                )
        if not functions_to_summarize:
            return []
        center = call_graph.get("center_function", "unknown")
        error_loc = ""
        if error_file and error_line:
            error_loc = f"\nError emission location: {error_file}:{error_line}"
        elif error_file:
            error_loc = f"\nError emission file: {error_file}"
        error_ctx = ""
        if error_context:
            error_ctx = f"\nError message: {error_context}"
        summaries: list[FunctionDetailedSummary] = []
        for func in functions_to_summarize:
            try:
                summary = await self._summarize_single_function(
                    func_name=func["name"],
                    func_body=func["body"],
                    role=func["role"],
                    center_function=center,
                    error_context=error_ctx,
                    error_location=error_loc,
                )
                if summary:
                    summaries.append(summary)
            except Exception as e:
                logger.warning(f"Failed to summarize {func['name']}: {e}")
        return summaries

    async def _summarize_single_function(
        self, func_name: str, func_body: str, role: str, center_function: str, error_context: str, error_location: str
    ) -> FunctionDetailedSummary | None:
        if not self._llm:
            return None
        prompt = f"Analyze this C++ function in detail. It is a {role} of `{center_function}()` which is the function that emits the error under investigation.\n{error_context}\n{error_location}\n\n```cpp\n{func_body}\n```\n\nProvide a detailed analysis of this function with the following sections. Each section should be a substantial paragraph (at least 50 words) so the total analysis reaches approximately 300 words or more.\n\n1. **Purpose**: What the function does and why it exists in the codebase\n2. **Mechanism**: How it works - key logic, algorithms, data transformations, state changes, and control flow\n3. **Data Flow**: How data enters and exits the function - parameters, return values, key variables, buffers, shared state, and side effects\n4. **Error Paths**: Error handling, failure modes, exception paths, edge cases, and what happens when things go wrong\n5. **Error Line Relevance**: How this function specifically relates to the error emission line under investigation - what path leads from this function to the error, or what data it provides/consumes that is relevant"
        system_prompt = "You are an expert C++ code analyst specializing in DAQ (Data Acquisition) systems. Provide thorough, detailed function analysis that helps debug error root causes. Be specific about code behavior, not generic."
        try:
            result = await self._llm.generate_structured(prompt, FunctionDetailedSummary, system_prompt=system_prompt)
            if result and result.function_name != func_name:
                result.function_name = func_name
            return result
        except Exception as e:
            logger.warning(f"Structured summarization failed for {func_name}: {e}")
            return None

    def summaries_to_purpose_dict(self, summaries: list[FunctionDetailedSummary]) -> dict[str, str]:
        return {s.function_name: s.purpose for s in summaries}

    def _format_file_location(self, file_path: str | None, line: int | None) -> str:
        if not file_path:
            return ""
        from pathlib import Path

        filename = Path(file_path).name if file_path else ""
        if line:
            return f"{filename}:{line}"
        return filename

    def generate_call_graph_diagram(
        self, call_graph: dict, summaries: dict[str, str] | list[FunctionDetailedSummary] | None = None
    ) -> str | None:
        center = call_graph.get("center_function", "")
        callers = call_graph.get("callers", [])
        callees = call_graph.get("callees", [])
        purpose_dict: dict[str, str] = {}
        if isinstance(summaries, list):
            purpose_dict = self.summaries_to_purpose_dict(summaries)
        elif isinstance(summaries, dict):
            purpose_dict = summaries
        useful_callees = [c for c in callees if not self._is_excluded_function(c.get("callee_name", ""))]
        if not center or (not callers and (not useful_callees)):
            return None
        lines = []
        if callers:
            lines.append("CALLERS (functions that call the error location):")
            for c in callers[:4]:
                name = c.get("caller_name", "?")
                file_loc = self._format_file_location(c.get("caller_file"), c.get("call_line"))
                purpose = purpose_dict.get(name, "")
                if file_loc:
                    lines.append(f"  • {name}()  [{file_loc}]")
                else:
                    lines.append(f"  • {name}()")
                if purpose and (not purpose.startswith("error")):
                    lines.append(f"      {purpose}")
            lines.append("")
            lines.append("        │")
            lines.append("        ▼")
        lines.append("")
        lines.append(f"  ══► {center}() ◄══  [ERROR LOCATION]")
        lines.append("")
        if useful_callees:
            lines.append("        │")
            lines.append("        ▼")
            lines.append("")
            lines.append("CALLEES (functions called from error location):")
            for c in useful_callees[:4]:
                name = c.get("callee_name", "?")
                file_loc = self._format_file_location(c.get("callee_file"), c.get("call_line"))
                purpose = purpose_dict.get(name, "")
                if file_loc:
                    lines.append(f"  • {name}()  [{file_loc}]")
                else:
                    lines.append(f"  • {name}()")
                if purpose and (not purpose.startswith("error")):
                    lines.append(f"      {purpose}")
        return "\n".join(lines) if lines else None
