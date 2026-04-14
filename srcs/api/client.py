"""
File: client.py
Purpose: AgentClient -- typed async HTTP client for the agentic API.
Category: Utility
Author: artdaq team
Depends: None
Exports: AgentClient
Complexity: High | Lines: 470
"""

from __future__ import annotations
import json
import logging
from typing import Any, AsyncIterator
import httpx
from .errors import AgentAPIError
from .sse import SSEEvent

logger = logging.getLogger(__name__)


def _build_query_params(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


class AgentClient:

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        *,
        timeout: float = 300.0,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout
        self._transport = _transport
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def _from_transport(cls, transport: httpx.AsyncBaseTransport) -> "AgentClient":
        return cls(api_url="http://in-process", _transport=transport)

    async def __aenter__(self) -> "AgentClient":
        self._client = httpx.AsyncClient(base_url=self._api_url, timeout=self._timeout, transport=self._transport)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("AgentClient must be used as an async context manager.")
        return self._client

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        resp = await self._http.request(method, path, json=json_body, params=params)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                err = body.get("error", {})
                raise AgentAPIError(
                    code=err.get("code", "HTTP_ERROR"),
                    message=err.get("message", resp.text),
                    status_code=resp.status_code,
                    details=err.get("details", {}),
                    recovery_hint=err.get("recovery_hint"),
                )
            except (json.JSONDecodeError, KeyError):
                raise AgentAPIError(code="HTTP_ERROR", message=resp.text, status_code=resp.status_code)
        return resp.json()

    async def _request_list(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> list[Any]:
        resp = await self._http.request(method, path, json=json_body, params=params)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                err = body.get("error", {})
                raise AgentAPIError(
                    code=err.get("code", "HTTP_ERROR"),
                    message=err.get("message", resp.text),
                    status_code=resp.status_code,
                    details=err.get("details", {}),
                    recovery_hint=err.get("recovery_hint"),
                )
            except (json.JSONDecodeError, KeyError):
                raise AgentAPIError(code="HTTP_ERROR", message=resp.text, status_code=resp.status_code)
        return resp.json()

    async def _stream_sse(self, path: str, json_body: dict[str, Any]) -> AsyncIterator[SSEEvent]:
        async with self._http.stream("POST", path, json=json_body) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                try:
                    err = json.loads(body).get("error", {})
                    raise AgentAPIError(
                        code=err.get("code", "HTTP_ERROR"),
                        message=err.get("message", body.decode()),
                        status_code=resp.status_code,
                    )
                except (json.JSONDecodeError, KeyError):
                    raise AgentAPIError(code="HTTP_ERROR", message=body.decode(), status_code=resp.status_code)
            event_type = ""
            data_buf = ""
            event_id = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("id: "):
                    event_id = line[4:]
                elif line.startswith("data: "):
                    data_buf = line[6:]
                elif line == "":
                    if event_type and data_buf:
                        try:
                            data = json.loads(data_buf)
                        except json.JSONDecodeError:
                            data = {"raw": data_buf}
                        yield SSEEvent(event=event_type, data=data, id=event_id)
                    event_type = ""
                    data_buf = ""
                    event_id = None

    async def get_health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def create_session(self) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/agent/sessions")

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/agent/sessions/{session_id}")

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/api/v1/agent/sessions/{session_id}")

    async def _invoke_tool(self, tool_name: str, session_id: str | None = None, **params: Any) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if session_id:
            body["session_id"] = session_id
        if params:
            body["params"] = params
        return await self._request("POST", f"/api/v1/agent/tools/{tool_name}", json_body=body)

    async def parse_logs(
        self, session_id: str, content: str, error_line: int | None = None, context_lines: int = 60
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session_id": session_id,
            "content": content,
            "params": {"context_lines": context_lines},
        }
        if error_line is not None:
            body["params"]["error_line"] = error_line
        return await self._request("POST", "/api/v1/agent/tools/parse_logs", json_body=body)

    async def search_logs(
        self,
        session_id: str,
        *,
        pattern: str | None = None,
        severity: str | None = None,
        component: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if pattern:
            params["pattern"] = pattern
        if severity:
            params["severity"] = severity
        if component:
            params["component"] = component
        return await self._invoke_tool("search_logs", session_id, **params)

    async def get_log_context(self, session_id: str, line: int, before: int = 10, after: int = 10) -> dict[str, Any]:
        return await self._invoke_tool("get_log_context", session_id, line=line, before=before, after=after)

    async def get_log_summary(self, session_id: str) -> dict[str, Any]:
        return await self._invoke_tool("get_log_summary", session_id)

    async def correlate_events(self, session_id: str, window_seconds: int = 5, level: str = "ERROR") -> dict[str, Any]:
        return await self._invoke_tool("correlate_events", session_id, window_seconds=window_seconds, level=level)

    async def find_error_source(self, session_id: str, error_message: str) -> dict[str, Any]:
        return await self._invoke_tool("find_error_source", session_id, error_message=error_message)

    async def lookup_function(self, session_id: str, name: str, file_filter: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": name}
        if file_filter:
            params["file_filter"] = file_filter
        return await self._invoke_tool("lookup_function", session_id, **params)

    async def get_call_graph(
        self, session_id: str, name: str, depth: int = 1, direction: str = "both"
    ) -> dict[str, Any]:
        return await self._invoke_tool("get_call_graph", session_id, name=name, depth=depth, direction=direction)

    async def summarize_function(self, session_id: str, name: str, file_filter: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": name}
        if file_filter:
            params["file_filter"] = file_filter
        return await self._invoke_tool("summarize_function", session_id, **params)

    async def search_code(
        self, session_id: str, query: str, symbol_type: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"query": query, "limit": limit}
        if symbol_type:
            params["type"] = symbol_type
        return await self._invoke_tool("search_code", session_id, **params)

    async def match_pattern(self, session_id: str, message_pattern: str, **kwargs: Any) -> dict[str, Any]:
        return await self._invoke_tool("match_pattern", session_id, message_pattern=message_pattern, **kwargs)

    async def find_similar_investigations(self, session_id: str, error_message: str, n: int = 5) -> dict[str, Any]:
        return await self._invoke_tool("find_similar_investigations", session_id, error_message=error_message, n=n)

    async def get_prior_knowledge(self, session_id: str, error_message: str, **kwargs: Any) -> dict[str, Any]:
        return await self._invoke_tool("get_prior_knowledge", session_id, error_message=error_message, **kwargs)

    async def record_finding(
        self, session_id: str, category: str, description: str, severity: str = "medium", **kwargs: Any
    ) -> dict[str, Any]:
        return await self._invoke_tool(
            "record_finding", session_id, category=category, description=description, severity=severity, **kwargs
        )

    async def record_hypothesis(
        self, session_id: str, description: str, confidence: float = 0.5, **kwargs: Any
    ) -> dict[str, Any]:
        return await self._invoke_tool(
            "record_hypothesis", session_id, description=description, confidence=confidence, **kwargs
        )

    async def update_hypothesis(self, session_id: str, hypothesis_id: str, **kwargs: Any) -> dict[str, Any]:
        return await self._invoke_tool("update_hypothesis", session_id, hypothesis_id=hypothesis_id, **kwargs)

    async def get_findings_summary(self, session_id: str) -> dict[str, Any]:
        return await self._invoke_tool("get_findings_summary", session_id)

    async def investigate(self, session_id: str, error_message: str | None = None, **kwargs: Any) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if error_message:
            params["error_message"] = error_message
        params.update(kwargs)
        return await self._invoke_tool("investigate", session_id, **params)

    async def investigate_stream(
        self,
        session_id: str,
        error_message: str | None = None,
        *,
        verbose: bool = False,
        source_files: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[SSEEvent]:
        body: dict[str, Any] = {"session_id": session_id, "params": {}}
        if error_message:
            body["params"]["error_message"] = error_message
        if verbose:
            body["params"]["verbose"] = True
        if source_files is not None:
            body["params"]["source_files"] = source_files
        body["params"].update(kwargs)
        async for event in self._stream_sse("/api/v1/agent/tools/investigate_stream", body):
            yield event

    async def ask_experts(self, session_id: str, question: str) -> dict[str, Any]:
        return await self._invoke_tool("ask_experts", session_id, question=question)

    async def init_knowledge_base(self, skip_source: bool = False, skip_ollama_check: bool = False) -> dict[str, Any]:
        return await self._invoke_tool(
            "init_knowledge_base", skip_source=skip_source, skip_ollama_check=skip_ollama_check
        )

    async def sync_sources(self) -> dict[str, Any]:
        return await self._invoke_tool("sync_sources")

    async def submit_feedback(
        self,
        investigation_id: str,
        correct: bool,
        actual_cause: str | None = None,
        feedback_source: str = "cli",
        user_id: str | None = None,
        what_was_helpful: str | None = None,
        what_was_wrong: str | None = None,
        suggestions: str | None = None,
        additional_notes: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"correct": correct, "feedback_source": feedback_source}
        if actual_cause is not None:
            body["actual_cause"] = actual_cause
        if user_id is not None:
            body["user_id"] = user_id
        if what_was_helpful is not None:
            body["what_was_helpful"] = what_was_helpful
        if what_was_wrong is not None:
            body["what_was_wrong"] = what_was_wrong
        if suggestions is not None:
            body["suggestions"] = suggestions
        if additional_notes is not None:
            body["additional_notes"] = additional_notes
        return await self._request("POST", f"/api/v1/investigations/{investigation_id}/feedback", json_body=body)

    async def list_investigations(self, limit: int = 20, offset: int = 0, outcome: str | None = None) -> dict[str, Any]:
        qp = _build_query_params(limit=limit, offset=offset, outcome=outcome)
        return await self._request("GET", "/api/v1/investigations", params=qp)

    async def get_investigation(self, investigation_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/investigations/{investigation_id}")

    async def investigate_from_content(
        self, content: str, error_line: int | None = None, context_lines: int = 60
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"content": content, "context_lines": context_lines}
        if error_line is not None:
            body["error_line"] = error_line
        return await self._request("POST", "/api/v1/investigations/from-content", json_body=body)

    async def investigate_from_files(self, files: list[dict[str, Any]], context_lines: int = 60) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/v1/investigations/from-files", json_body={"files": files, "context_lines": context_lines}
        )

    async def get_source_status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/admin/source/status")

    async def sync_source_repos(self) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/admin/source/sync")

    async def init_system(self, skip_source: bool = False, skip_ollama_check: bool = False) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/v1/admin/init", json_body={"skip_source": skip_source, "skip_ollama_check": skip_ollama_check}
        )

    async def list_binders(self, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        qp = _build_query_params(status=status, limit=limit)
        return await self._request("GET", "/api/v1/binders", params=qp)

    async def get_binder(self, binder_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/binders/{binder_id}")

    async def get_binder_summary(self, binder_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/binders/{binder_id}/summary")

    async def get_binder_by_investigation(self, investigation_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/binders/by-investigation/{investigation_id}")

    async def get_binder_hypotheses(
        self, binder_id: str, *, min_score: float | None = None, source: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        qp = _build_query_params(min_score=min_score, source=source, limit=limit)
        return await self._request("GET", f"/api/v1/binders/{binder_id}/hypotheses", params=qp)

    async def get_binder_evidence(
        self, binder_id: str, *, evidence_type: str | None = None, strength: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        qp = _build_query_params(evidence_type=evidence_type, strength=strength, limit=limit)
        return await self._request("GET", f"/api/v1/binders/{binder_id}/evidence", params=qp)

    async def get_binder_chains(
        self, binder_id: str, *, hypothesis_id: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        qp = _build_query_params(hypothesis_id=hypothesis_id, limit=limit)
        return await self._request("GET", f"/api/v1/binders/{binder_id}/chains", params=qp)

    async def get_binder_challenges(
        self, binder_id: str, *, resolved: bool | None = None, severity: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        qp = _build_query_params(resolved=resolved, severity=severity, limit=limit)
        return await self._request("GET", f"/api/v1/binders/{binder_id}/challenges", params=qp)

    async def get_binder_feedback(self, binder_id: str, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        qp = _build_query_params(limit=limit, offset=offset)
        return await self._request("GET", f"/api/v1/binders/{binder_id}/feedback", params=qp)

    async def get_binder_llm_exchanges(self, binder_id: str, *, phase: int | None = None) -> list[Any]:
        qp = _build_query_params(phase=phase)
        return await self._request_list("GET", f"/api/v1/binders/{binder_id}/llm/exchanges", params=qp)

    async def get_binder_llm_statistics(self, binder_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/binders/{binder_id}/llm/statistics")

    async def query_binder_artifacts(
        self,
        binder_id: str,
        *,
        artifact_type: str | None = None,
        phase: int | None = None,
        function_name: str | None = None,
        tags: list[str] | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        qp = _build_query_params(
            artifact_type=artifact_type,
            phase=phase,
            function_name=function_name,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        if tags:
            qp["tags"] = tags
        return await self._request("GET", f"/api/v1/binders/{binder_id}/artifacts", params=qp)

    async def get_binder_artifact(self, binder_id: str, artifact_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/binders/{binder_id}/artifacts/{artifact_id}")

    async def search_binder_artifacts(
        self, binder_id: str, query: str, artifact_types: list[str] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if artifact_types:
            body["artifact_types"] = artifact_types
        return await self._request("POST", f"/api/v1/binders/{binder_id}/artifacts/search", json_body=body)

    async def get_artifact_history(self, binder_id: str, artifact_id: str) -> list[Any]:
        return await self._request_list("GET", f"/api/v1/binders/{binder_id}/artifacts/{artifact_id}/history")

    async def get_binder_audit_log(
        self,
        binder_id: str,
        *,
        persona_name: str | None = None,
        phase_number: int | None = None,
        operation_type: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        qp = _build_query_params(
            persona_name=persona_name, phase_number=phase_number, operation_type=operation_type, limit=limit
        )
        return await self._request_list("GET", f"/api/v1/binders/{binder_id}/audit", params=qp)

    async def get_binder_audit_summary(self, binder_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/binders/{binder_id}/audit/summary")

    async def list_investigations_with_state(
        self, *, outcome: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[Any]:
        qp = _build_query_params(outcome=outcome, status=status, limit=limit)
        return await self._request_list("GET", "/api/v1/binders/investigations", params=qp)

    async def resume_investigation(self, investigation_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/binders/{investigation_id}/resume")

    async def get_strategy_weights(self, error_type: str | None = None) -> dict[str, Any]:
        qp = _build_query_params(error_type=error_type)
        return await self._request("GET", "/api/v1/strategies/weights", params=qp)

    async def get_query_priority(self, error_type: str | None = None) -> dict[str, Any]:
        qp = _build_query_params(error_type=error_type)
        return await self._request("GET", "/api/v1/strategies/query-priority", params=qp)

    async def get_strategy_recommendations(self, error_type: str | None = None) -> dict[str, Any]:
        qp = _build_query_params(error_type=error_type)
        return await self._request("GET", "/api/v1/strategies/recommendations", params=qp)

    async def investigate_one_shot(
        self, content: str, error_line: int | None = None, context_lines: int = 60
    ) -> dict[str, Any]:
        session = await self.create_session()
        sid = session["session_id"]
        try:
            await self.parse_logs(sid, content, error_line=error_line, context_lines=context_lines)
            result = await self.investigate(sid)
            return result
        finally:
            try:
                await self.delete_session(sid)
            except Exception:
                pass
