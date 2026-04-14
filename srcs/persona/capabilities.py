"""
File: capabilities.py
Purpose: Capability registry for persona-to-tool mapping.
Category: Utility
Author: artdaq team
Depends: tools, workbinder
Exports: Capability, CapabilityRegistry, get_capability_registry, register_tools, BINDER_CAPABILITIES
Complexity: Medium | Lines: 230
"""

from typing import TYPE_CHECKING, Any, Callable, Coroutine, cast

if TYPE_CHECKING:
    from srcs.agent.tools import CodeForensicsTools, CodeTools, InvestigationTools, PatternTools
    from srcs.workbinder import BinderTools


class Capability:

    def __init__(self, name: str, description: str, tool_class: str, method_name: str):
        self.name = name
        self.description = description
        self.tool_class = tool_class
        self.method_name = method_name


BUILTIN_CAPABILITIES: dict[str, Capability] = {
    "log_search": Capability(
        name="log_search",
        description="Search log entries by pattern",
        tool_class="InvestigationTools",
        method_name="search_logs",
    ),
    "similar_investigation_lookup": Capability(
        name="similar_investigation_lookup",
        description="Look up similar past investigations",
        tool_class="InvestigationTools",
        method_name="lookup_similar_cases",
    ),
    "time_window_search": Capability(
        name="time_window_search",
        description="Get logs within a time window",
        tool_class="InvestigationTools",
        method_name="get_logs_in_window",
    ),
    "code_lookup": Capability(
        name="code_lookup",
        description="Look up function definitions",
        tool_class="CodeTools",
        method_name="lookup_function",
    ),
    "class_lookup": Capability(
        name="class_lookup", description="Look up class definitions", tool_class="CodeTools", method_name="lookup_class"
    ),
    "code_search": Capability(
        name="code_search",
        description="Search for symbols in code",
        tool_class="CodeTools",
        method_name="search_symbols",
    ),
    "function_trace": Capability(
        name="function_trace",
        description="Trace variable dataflow",
        tool_class="CodeForensicsTools",
        method_name="trace_variable",
    ),
    "dataflow_analysis": Capability(
        name="dataflow_analysis",
        description="Analyze data flow paths",
        tool_class="CodeForensicsTools",
        method_name="find_error_path",
    ),
    "caller_chain": Capability(
        name="caller_chain",
        description="Get chain of callers for a function",
        tool_class="CodeForensicsTools",
        method_name="get_caller_chain",
    ),
    "pattern_lookup": Capability(
        name="pattern_lookup",
        description="Look up known error patterns",
        tool_class="PatternTools",
        method_name="lookup_error_pattern",
    ),
    "accuracy_check": Capability(
        name="accuracy_check",
        description="Check historical accuracy of a pattern",
        tool_class="PatternTools",
        method_name="get_historical_accuracy",
    ),
    "binder_list": Capability(
        name="binder_list",
        description="List artifacts in the binder",
        tool_class="BinderTools",
        method_name="list_artifacts",
    ),
    "binder_get": Capability(
        name="binder_get", description="Get artifact by ID", tool_class="BinderTools", method_name="get_artifact"
    ),
    "binder_search": Capability(
        name="binder_search",
        description="Search artifacts by content",
        tool_class="BinderTools",
        method_name="search_binder",
    ),
    "binder_related": Capability(
        name="binder_related",
        description="Get related artifacts",
        tool_class="BinderTools",
        method_name="get_related_artifacts",
    ),
    "binder_history": Capability(
        name="binder_history",
        description="Get artifact history",
        tool_class="BinderTools",
        method_name="get_artifact_history",
    ),
    "binder_stats": Capability(
        name="binder_stats",
        description="Get binder statistics",
        tool_class="BinderTools",
        method_name="get_binder_stats",
    ),
    "binder_add_finding": Capability(
        name="binder_add_finding",
        description="Add a finding to the binder",
        tool_class="BinderTools",
        method_name="add_finding",
    ),
    "binder_annotate": Capability(
        name="binder_annotate",
        description="Annotate an artifact",
        tool_class="BinderTools",
        method_name="annotate_artifact",
    ),
    "binder_update": Capability(
        name="binder_update", description="Update an artifact", tool_class="BinderTools", method_name="update_artifact"
    ),
    "binder_expand_call_graph": Capability(
        name="binder_expand_call_graph",
        description="Expand call graph for a function",
        tool_class="BinderTools",
        method_name="expand_call_graph",
    ),
    "binder_get_function": Capability(
        name="binder_get_function",
        description="Get function source code",
        tool_class="BinderTools",
        method_name="get_function_source",
    ),
    "binder_get_class": Capability(
        name="binder_get_class",
        description="Get class definition",
        tool_class="BinderTools",
        method_name="get_class_definition",
    ),
}
BINDER_CAPABILITIES = [
    "binder_list",
    "binder_get",
    "binder_search",
    "binder_related",
    "binder_history",
    "binder_stats",
    "binder_add_finding",
    "binder_annotate",
    "binder_update",
    "binder_expand_call_graph",
    "binder_get_function",
    "binder_get_class",
]


class CapabilityRegistry:

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = dict(BUILTIN_CAPABILITIES)
        self._tool_instances: dict[str, Any] = {}

    def register_capability(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability

    def register_tool(self, tool_class_name: str, instance: Any) -> None:
        self._tool_instances[tool_class_name] = instance

    def get_capability(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def resolve_capability(self, name: str) -> Callable[..., Coroutine[Any, Any, Any]] | None:
        capability = self._capabilities.get(name)
        if capability is None:
            return None
        tool = self._tool_instances.get(capability.tool_class)
        if tool is None:
            return None
        method = getattr(tool, capability.method_name, None)
        if method is None or not callable(method):
            return None
        return cast(Callable[..., Coroutine[Any, Any, Any]], method)

    def list_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def get_capabilities_for_persona(self, capability_names: list[str]) -> dict[str, Any]:
        resolved = {}
        for name in capability_names:
            method = self.resolve_capability(name)
            if method is not None:
                resolved[name] = method
        return resolved


_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


def register_tools(
    investigation_tools: "InvestigationTools | None" = None,
    code_tools: "CodeTools | None" = None,
    forensics_tools: "CodeForensicsTools | None" = None,
    pattern_tools: "PatternTools | None" = None,
    binder_tools: "BinderTools | None" = None,
) -> None:
    registry = get_capability_registry()
    if investigation_tools is not None:
        registry.register_tool("InvestigationTools", investigation_tools)
    if code_tools is not None:
        registry.register_tool("CodeTools", code_tools)
    if forensics_tools is not None:
        registry.register_tool("CodeForensicsTools", forensics_tools)
    if pattern_tools is not None:
        registry.register_tool("PatternTools", pattern_tools)
    if binder_tools is not None:
        registry.register_tool("BinderTools", binder_tools)
