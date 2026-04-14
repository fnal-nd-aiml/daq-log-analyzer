"""
File: tools.py
Purpose: Binder Tools - LLM-invokable tools for Work Binder interaction.
Category: Utility
Author: artdaq team
Depends: indexer, token_utils
Exports: BinderTools
Complexity: Medium | Lines: 368
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
from .artifacts import ArtifactType
from .binder import BinderQuery, WorkBinder

if TYPE_CHECKING:
    from srcs.extraction.indexer import CodeIndex
logger = logging.getLogger(__name__)


class BinderTools:

    def __init__(
        self,
        binder: WorkBinder,
        code_index: "CodeIndex | None" = None,
        persona_name: str = "system",
        current_phase: int | None = None,
    ):
        self._binder = binder
        self._index = code_index
        self._persona = persona_name
        self._phase = current_phase

    async def expand_call_graph(
        self, function_name: str, direction: str = "both", depth: int = 1, max_body_chars: int = 0
    ) -> dict[str, Any]:
        if not self._index:
            return {"error": "No code index available"}
        callers = []
        callees = []
        if direction in ("callers", "both"):
            raw_callers = self._index.get_callers(function_name)
            for i, caller in enumerate(raw_callers[:5]):
                caller_info = {
                    "caller_name": caller.get("caller_name", "unknown"),
                    "caller_file": caller.get("caller_file"),
                    "call_line": caller.get("call_line"),
                    "relationship": f"passes data TO {function_name}",
                }
                if i < 3:
                    body = self._index.get_function_source(caller["caller_name"])
                    caller_info["body"] = self._truncate_body(body, max_body_chars)
                callers.append(caller_info)
        if direction in ("callees", "both"):
            raw_callees = self._index.get_callees(function_name)
            for i, callee in enumerate(raw_callees[:5]):
                callee_name = callee.get("callee_name", "unknown")
                callee_info = {
                    "callee_name": callee_name,
                    "callee_file": callee.get("callee_file"),
                    "relationship": f"receives data FROM {function_name}",
                }
                if i < 3:
                    funcs = self._index.find_function(callee_name)
                    if funcs:
                        callee_info["callee_signature"] = funcs[0].signature
                    body = self._index.get_function_source(callee_name)
                    callee_info["body"] = self._truncate_body(body, max_body_chars)
                callees.append(callee_info)
        diagram = self._generate_diagram(function_name, callers, callees)
        artifact_id = self._binder.add_call_graph(
            center_function=function_name,
            callers=callers,
            callees=callees,
            created_by=self._persona,
            phase=self._phase,
            diagram=diagram,
            depth=depth,
        )
        return {
            "artifact_id": artifact_id,
            "center_function": function_name,
            "callers": callers,
            "callees": callees,
            "diagram": diagram,
        }

    def _truncate_body(self, body: str | None, max_chars: int) -> str | None:
        if not body:
            return None
        from srcs.llm.token_utils import truncate_middle_if_needed

        return truncate_middle_if_needed(
            body, max_tokens=max_chars // 4 if max_chars > 0 else 0, label="binder function body"
        )

    def _generate_diagram(self, center: str, callers: list[dict], callees: list[dict]) -> str:
        lines = [
            "",
            "=" * 60,
            "CALL GRAPH CONTEXT",
            "(These show data flow - NOT necessarily error sources)",
            "=" * 60,
            "",
        ]
        if callers:
            lines.append("CALLERS (pass data TO error location):")
            lines.append("-" * 40)
            for c in callers[:3]:
                name = c.get("caller_name", "?")
                lines.append(f"  [{name}]")
                if c.get("body"):
                    lines.append(f"    ^ (has body: {len(c['body'])} chars)")
            lines.append("        |")
            lines.append("        v")
        lines.append("")
        lines.append(f"  >>> [{center}] <<<  <-- ERROR SOURCE")
        lines.append("")
        if callees:
            lines.append("        |")
            lines.append("        v")
            lines.append("CALLEES (called BY error location):")
            lines.append("-" * 40)
            for c in callees[:3]:
                name = c.get("callee_name", "?")
                lines.append(f"  [{name}]")
                if c.get("body"):
                    lines.append(f"    ^ (has body: {len(c['body'])} chars)")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    async def get_caller_body(self, caller_name: str) -> dict[str, Any]:
        return await self.get_function_source(caller_name)

    async def get_callee_body(self, callee_name: str) -> dict[str, Any]:
        return await self.get_function_source(callee_name)

    async def get_function_source(self, function_name: str, add_to_binder: bool = True) -> dict[str, Any]:
        if not self._index:
            return {"error": "No code index available"}
        funcs = self._index.find_function(function_name)
        if not funcs:
            return {"error": f"Function not found: {function_name}"}
        func = funcs[0]
        source = self._index.get_function_source(function_name)
        result = {
            "name": func.name,
            "file_path": str(func.file_path),
            "start_line": func.start_line,
            "end_line": func.end_line,
            "signature": func.signature,
            "source": source,
        }
        if add_to_binder and source:
            artifact_id = self._binder.add_code_snippet(
                file_path=str(func.file_path),
                start_line=func.start_line,
                end_line=func.end_line,
                content=source,
                created_by=self._persona,
                function_name=func.name,
                phase=self._phase,
            )
            result["artifact_id"] = artifact_id
        return result

    async def get_class_definition(self, class_name: str, add_to_binder: bool = True) -> dict[str, Any]:
        if not self._index:
            return {"error": "No code index available"}
        classes = self._index.find_class(class_name)
        if not classes:
            return {"error": f"Class not found: {class_name}"}
        cls = classes[0]
        source = self._index.get_class_source(class_name)
        result = {
            "name": cls.name,
            "file_path": str(cls.file_path),
            "start_line": cls.start_line,
            "end_line": cls.end_line,
            "base_classes": cls.base_classes,
            "methods": cls.methods,
            "source": source,
        }
        if add_to_binder and source:
            artifact_id = self._binder.add_code_snippet(
                file_path=str(cls.file_path),
                start_line=cls.start_line,
                end_line=cls.end_line,
                content=source,
                created_by=self._persona,
                function_name=cls.name,
                phase=self._phase,
            )
            result["artifact_id"] = artifact_id
        return result

    async def search_code(self, pattern: str, file_filter: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if not self._index:
            return [{"error": "No code index available"}]
        funcs = self._index.find_function(pattern, file_filter=file_filter)
        results = []
        for func in funcs[:limit]:
            results.append(
                {
                    "name": func.name,
                    "file_path": str(func.file_path),
                    "start_line": func.start_line,
                    "end_line": func.end_line,
                    "signature": func.signature,
                }
            )
        return results

    async def add_finding(
        self,
        finding_type: str,
        content: str,
        related_artifacts: list[str] | None = None,
        confidence: float = 0.5,
        tags: list[str] | None = None,
    ) -> str:
        return self._binder.add_finding(
            persona=self._persona,
            finding_type=finding_type,
            content=content,
            confidence=confidence,
            related_artifacts=related_artifacts,
            phase=self._phase,
            tags=tags,
        )

    async def annotate_artifact(self, artifact_id: str, annotation_type: str, content: str) -> str:
        return self._binder.add_annotation(
            target_artifact_id=artifact_id, annotation_type=annotation_type, content=content, created_by=self._persona
        )

    async def add_artifact(
        self,
        artifact_type: str,
        content: dict[str, Any],
        tags: list[str] | None = None,
        priority: str = "normal",
        function_name: str | None = None,
    ) -> str:
        atype = ArtifactType(artifact_type)
        if atype == ArtifactType.CODE_SNIPPET:
            return self._binder.add_code_snippet(
                file_path=content["file_path"],
                start_line=content["start_line"],
                end_line=content["end_line"],
                content=content["content"],
                created_by=self._persona,
                function_name=function_name,
                phase=self._phase,
            )
        elif atype == ArtifactType.FINDING:
            return self._binder.add_finding(
                persona=self._persona,
                finding_type=content.get("finding_type", "observation"),
                content=content["content"],
                confidence=content.get("confidence", 0.5),
                phase=self._phase,
                tags=tags,
            )
        else:
            raise ValueError(f"Unsupported artifact type for add: {artifact_type}")

    async def update_artifact(self, artifact_id: str, updates: dict[str, Any]) -> bool:
        return self._binder.update_artifact(artifact_id, updates, self._persona)

    async def mark_deleted(self, artifact_id: str, reason: str | None = None) -> bool:
        return self._binder.mark_deleted(artifact_id, self._persona, reason)

    async def restore_artifact(self, artifact_id: str) -> bool:
        return self._binder.restore_artifact(artifact_id, self._persona)

    async def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        artifact = self._binder.get_artifact(artifact_id)
        if artifact:
            return artifact.model_dump()
        return None

    async def list_artifacts(
        self,
        artifact_type: str | None = None,
        created_by: str | None = None,
        tags: list[str] | None = None,
        phase: int | None = None,
        function_name: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = BinderQuery(
            artifact_type=ArtifactType(artifact_type) if artifact_type else None,
            created_by=created_by,
            tags=tags,
            phase=phase,
            function_name=function_name,
            include_deleted=include_deleted,
            limit=limit,
        )
        artifacts = self._binder.query(query)
        return [
            {
                "id": a.id,
                "artifact_type": a.artifact_type.value,
                "created_by": a.created_by,
                "created_at": a.created_at.isoformat(),
                "phase": a.phase,
                "function_name": a.function_name,
                "priority": a.priority.value,
                "tags": a.tags,
                "is_deleted": a.is_deleted,
            }
            for a in artifacts
        ]

    async def search_binder(self, query: str, artifact_types: list[str] | None = None) -> list[dict[str, Any]]:
        results = []
        query_lower = query.lower()
        for artifact in self._binder._artifacts.values():
            if artifact.is_deleted:
                continue
            if artifact_types:
                if artifact.artifact_type.value not in artifact_types:
                    continue
            artifact_str = artifact.model_dump_json().lower()
            if query_lower in artifact_str:
                results.append(
                    {
                        "id": artifact.id,
                        "artifact_type": artifact.artifact_type.value,
                        "created_by": artifact.created_by,
                        "function_name": artifact.function_name,
                    }
                )
        return results[:50]

    async def get_related_artifacts(self, artifact_id: str) -> list[dict[str, Any]]:
        related = self._binder.get_related_artifacts(artifact_id)
        return [
            {
                "id": a.id,
                "artifact_type": a.artifact_type.value,
                "created_by": a.created_by,
                "function_name": a.function_name,
            }
            for a in related
        ]

    async def get_artifact_history(self, artifact_id: str) -> list[dict[str, Any]]:
        history = self._binder.get_history(artifact_id)
        return [
            {
                "id": h.id,
                "modified_by": h.modified_by,
                "modified_at": h.modified_at.isoformat(),
                "action": h.action,
                "changes": h.changes,
            }
            for h in history
        ]

    async def get_binder_stats(self) -> dict[str, Any]:
        counts = self._binder.count_by_type()
        tags = self._binder.get_all_tags()
        return {
            "binder_id": self._binder.id,
            "investigation_id": self._binder.investigation_id,
            "status": self._binder.status,
            "artifact_counts": counts,
            "total_artifacts": sum(counts.values()),
            "unique_tags": tags,
            "tag_count": len(tags),
        }
