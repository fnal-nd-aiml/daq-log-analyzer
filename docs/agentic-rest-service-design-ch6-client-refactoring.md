> **Agentic REST API Design Document** | [← Pipeline & Admin Tools](agentic-rest-service-design-ch5-pipeline-admin-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Testing Strategy →](agentic-rest-service-design-ch7-testing-strategy.md)

---

# Chapter 6: Client Refactoring Guide

# Part IV: Client Refactoring Guide

The original architecture had all three clients (CLI, Slack, MCP) instantiate `InvestigationCoordinator` directly via `CoordinatorFactory`, creating tight coupling to internal modules.

The refactored architecture varies by client: CLI and Slack are now **API-only** (all operations flow through `AgentClient` and the REST API), while MCP retains a **dual-path** design (direct coordinator by default, API client when `ARTDAQ_API_URL` is set).

```
Before:                              After:

CLI ──► CoordinatorFactory           CLI ──► AgentClient ──► REST API (API-only)

Slack ──► CoordinatorFactory         Slack ──► AgentClient ──► REST API (API-only)

MCP ──► CoordinatorFactory           MCP ──► CoordinatorFactory (default)
                                         └──► AgentClient ──► REST API (via ARTDAQ_API_URL env var)
```

> **Note:** The CLI and Slack dual-path design described in earlier planning has been simplified. Both now exclusively use `AgentClient`, which can connect to a remote API server or use an in-process ASGI transport (via `AgentClient._from_transport()`) for zero-network-hop operation.

---

## 4.1 API Client Library (`srcs/api/client.py`)

### Design Principles

- Single async class (`AgentClient`) wrapping `httpx.AsyncClient`
- Async context manager for connection lifecycle
- Typed method for every tool and session operation
- SSE stream consumption via `async for` generators
- Structured error propagation through `AgentAPIError`
- No dependency on any `srcs` module other than Pydantic response models

### Error Hierarchy

```python
# srcs/api/errors.py

from dataclasses import dataclass


@dataclass
class AgentAPIError(Exception):
    """Structured error from the Agent REST API.

    Attributes:
        code: Machine-readable error code in SCREAMING_SNAKE_CASE
              (e.g., "SESSION_NOT_FOUND", "VALIDATION_ERROR",
              "TOOL_EXECUTION_ERROR").
        message: Human-readable error description.
        status_code: HTTP status code from the API response.
        details: Optional dict with additional context.
        recovery_hint: Optional suggestion for the caller on how to
                       recover (e.g., "Create a new session first").
    """

    code: str
    message: str
    status_code: int
    details: dict | None = None
    recovery_hint: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.status_code}] {self.code}: {self.message}"]
        if self.recovery_hint:
            parts.append(f"  Hint: {self.recovery_hint}")
        return "\n".join(parts)
```

### SSE Event Model

```python
# srcs/api/sse.py

from dataclasses import dataclass
from typing import Any


@dataclass
class SSEEvent:
    """A single Server-Sent Event parsed from the stream.

    Attributes:
        event: Event type string (e.g., "phase_start", "phase_complete",
               "evidence_item", "error", "done").
        data: Parsed JSON payload.
        id: Optional event ID for resumption.
    """

    event: str
    data: dict[str, Any]
    id: str | None = None
```

### Full Class Interface

```python
# srcs/api/client.py

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from .errors import AgentAPIError
from .sse import SSEEvent


class AgentClient:
    """Async client for the Agent REST API.

    Wraps httpx.AsyncClient and provides typed methods for every
    session operation and tool invocation. Intended to be used as
    an async context manager.

    Usage:
        async with AgentClient("http://localhost:8000") as client:
            session = await client.create_session()
            parsed = await client.parse_logs(
                session["session_id"], content=log_text
            )
            async for event in client.investigate_stream(
                session["session_id"]
            ):
                print(event.event, event.data)
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 300.0,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: Root URL of the API server (e.g., "http://localhost:8000").
            timeout: Default request timeout in seconds. The investigate
                     endpoint may take several minutes, so the default is
                     generous.
            headers: Optional extra HTTP headers (e.g., auth tokens).
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = headers or {}
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AgentClient:
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
            headers=self._headers,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError(
                "AgentClient must be used as an async context manager"
            )
        return self._http

    # ── Internal helpers ──────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a request and return the parsed JSON response.

        Raises AgentAPIError on non-2xx responses.
        """
        response = await self._client.request(
            method,
            path,
            json=json_body,
            params=params,
            timeout=timeout,
        )
        if response.status_code >= 400:
            body = response.json() if response.content else {}
            raise AgentAPIError(
                code=body.get("error", {}).get("code", "unknown"),
                message=body.get("error", {}).get("message", response.text),
                status_code=response.status_code,
                details=body.get("error", {}).get("details"),
                recovery_hint=body.get("error", {}).get("recovery_hint"),
            )
        return response.json()

    async def _stream_sse(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """Open an SSE stream and yield parsed events.

        Yields SSEEvent objects until the stream closes or a "done"
        event is received. Raises AgentAPIError if the initial response
        is an error.
        """
        async with self._client.stream(
            method,
            path,
            json=json_body,
            params=params,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                try:
                    err = json.loads(body)
                except json.JSONDecodeError:
                    err = {}
                raise AgentAPIError(
                    code=err.get("error", {}).get("code", "stream_error"),
                    message=err.get("error", {}).get("message", body.decode()),
                    status_code=response.status_code,
                    details=err.get("error", {}).get("details"),
                    recovery_hint=err.get("error", {}).get("recovery_hint"),
                )

            event_type = ""
            data_lines: list[str] = []
            event_id: str | None = None

            async for raw_line in response.aiter_lines():
                line = raw_line.rstrip("\n")

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
                elif line.startswith("id:"):
                    event_id = line[3:].strip()
                elif line == "":
                    # Empty line = end of event
                    if event_type and data_lines:
                        raw_data = "\n".join(data_lines)
                        try:
                            parsed = json.loads(raw_data)
                        except json.JSONDecodeError:
                            parsed = {"raw": raw_data}

                        yield SSEEvent(
                            event=event_type,
                            data=parsed,
                            id=event_id,
                        )

                        if event_type == "done":
                            return

                    event_type = ""
                    data_lines = []
                    event_id = None

    # ── Health ────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """GET /health -- check API server health."""
        return await self._request("GET", "/health")

    # ── Session Management ────────────────────────────────────────

    async def create_session(
        self,
        *,
        config_overrides: dict | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/sessions -- create a new investigation session.

        Args:
            config_overrides: Optional dict of config overrides for this
                              session (e.g., {"verbose": True}).

        Returns:
            Dict with "session_id", "created_at", "status", "tools".
        """
        body: dict[str, Any] = {}
        if config_overrides:
            body["config"] = config_overrides
        return await self._request("POST", "/api/v1/agent/sessions", json_body=body)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """GET /api/v1/agent/sessions/{session_id} -- get session state."""
        return await self._request("GET", f"/api/v1/agent/sessions/{session_id}")

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """DELETE /api/v1/agent/sessions/{session_id} -- destroy a session."""
        return await self._request("DELETE", f"/api/v1/agent/sessions/{session_id}")

    # ── Log Parsing Tools ─────────────────────────────────────────
    #
    # NOTE (implementation status): The actual client in
    # srcs/api/client.py maps 1:1 to the 22 registered tools via a
    # generic _invoke_tool() helper, with typed wrappers for each
    # tool. It also provides:
    #  - investigate_one_shot() convenience method
    #  - REST investigation endpoints (submit_feedback, list_investigations, etc.)
    #  - REST admin endpoints (get_source_status, sync_source_repos, init_system)
    #  - Extensive binder endpoints (60+ methods for artifact access, audit logs, etc.)
    #  - Strategy endpoints (get_strategy_weights, get_query_priority, etc.)

    async def parse_logs(
        self,
        session_id: str,
        *,
        content: str,
        error_line: int | None = None,
        context_lines: int = 60,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/parse_logs

        Parse raw log content and store parsed entries in the session.

        Args:
            session_id: Active session ID.
            content: Raw log text.
            error_line: Optional specific error line number.
            context_lines: Lines of context to extract around error.

        Returns:
            Dict with "total_entries", "trigger_error", "context_count",
            "log_levels" summary.
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/parse_logs",
            json_body={
                "session_id": session_id,
                "content": content,
                "error_line": error_line,
                "context_lines": context_lines,
            },
        )

    async def parse_logs_multi(
        self,
        session_id: str,
        *,
        files: list[dict[str, Any]],
        error_line: int | None = None,
        context_lines: int = 60,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/parse_logs_multi

        Parse multiple log files for multi-file investigation.

        Args:
            session_id: Active session ID.
            files: List of {"filename": str, "content": str} dicts.
            error_line: Optional specific error line number.
            context_lines: Lines of context to extract around error.

        Returns:
            Dict with "files_parsed", "trigger_error", "source_files".
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/parse_logs_multi",
            json_body={
                "session_id": session_id,
                "files": files,
                "error_line": error_line,
                "context_lines": context_lines,
            },
        )

    async def create_log_from_message(
        self,
        session_id: str,
        *,
        message: str,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/create_log_from_message

        Create a structured log entry from a plain error message.

        Args:
            session_id: Active session ID.
            message: Plain error message text.

        Returns:
            Dict with "trigger_error" (the synthesized Log entry).
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/create_log_from_message",
            json_body={
                "session_id": session_id,
                "message": message,
            },
        )

    # ── Investigation Tools ───────────────────────────────────────

    async def search_logs(
        self,
        session_id: str,
        *,
        grep: str | None = None,
        severity: str | None = None,
        component: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/search_logs

        Search parsed logs within the session.

        Returns:
            Dict with "entries", "total_matches", "truncated".
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/search_logs",
            json_body={
                "session_id": session_id,
                "grep": grep,
                "severity": severity,
                "component": component,
                "time_start": time_start,
                "time_end": time_end,
                "limit": limit,
                "offset": offset,
            },
        )

    async def get_log_context(
        self,
        session_id: str,
        *,
        line: int,
        before: int = 20,
        after: int = 20,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/get_log_context

        Get surrounding log lines around a specific line number.

        Returns:
            Dict with "center_line", "entries", "range".
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/get_log_context",
            json_body={
                "session_id": session_id,
                "line": line,
                "before": before,
                "after": after,
            },
        )

    # ── Code Analysis Tools ───────────────────────────────────────

    async def find_function(
        self,
        session_id: str,
        *,
        name: str,
        file_hint: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/find_function

        Look up a function by name in the indexed source code.

        Returns:
            Dict with "functions" list (file, line, signature, body_preview).
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/find_function",
            json_body={
                "session_id": session_id,
                "name": name,
                "file_hint": file_hint,
            },
        )

    async def find_class(
        self,
        session_id: str,
        *,
        name: str,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/find_class

        Look up a class by name in the indexed source code.

        Returns:
            Dict with "classes" list (file, line, methods, bases).
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/find_class",
            json_body={
                "session_id": session_id,
                "name": name,
            },
        )

    async def get_call_graph(
        self,
        session_id: str,
        *,
        function_name: str,
        depth: int = 2,
        direction: str = "both",
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/get_call_graph

        Get call graph for a function (callers and/or callees).

        Args:
            direction: "callers", "callees", or "both".

        Returns:
            Dict with "function", "callers", "callees" trees.
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/get_call_graph",
            json_body={
                "session_id": session_id,
                "function_name": function_name,
                "depth": depth,
                "direction": direction,
            },
        )

    async def find_error_source(
        self,
        session_id: str,
        *,
        error_message: str,
        component: str | None = None,
        function: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/find_error_source

        Locate where an error message originates in source code.

        Returns:
            Dict with "locations" list and "best_match".
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/find_error_source",
            json_body={
                "session_id": session_id,
                "error_message": error_message,
                "component": component,
                "function": function,
            },
        )

    async def trace_dataflow(
        self,
        session_id: str,
        *,
        function_name: str,
        variable: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/trace_dataflow

        Trace data flow through a function.

        Returns:
            Dict with "function", "dataflow" (inputs, outputs, transforms).
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/trace_dataflow",
            json_body={
                "session_id": session_id,
                "function_name": function_name,
                "variable": variable,
            },
        )

    # ── Knowledge Tools ───────────────────────────────────────────

    async def find_similar_cases(
        self,
        session_id: str,
        *,
        limit: int = 5,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/find_similar_cases

        Search knowledge base for similar past investigations.

        Returns:
            Dict with "cases" list (investigation_id, similarity, outcome, root_cause).
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/find_similar_cases",
            json_body={
                "session_id": session_id,
                "limit": limit,
            },
        )

    async def match_patterns(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/match_patterns

        Match the trigger error against known error patterns.

        Returns:
            Dict with "matches" list (pattern_id, confidence, root_causes).
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/match_patterns",
            json_body={"session_id": session_id},
        )

    # ── Findings ──────────────────────────────────────────────────

    async def record_finding(
        self,
        session_id: str,
        *,
        finding: str,
        severity: str,
        evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/record_finding

        Record an analysis finding with supporting evidence.

        Returns:
            Dict with "finding_id", "total_findings".
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/record_finding",
            json_body={
                "session_id": session_id,
                "finding": finding,
                "severity": severity,
                "evidence": evidence or [],
            },
        )

    async def get_findings(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/get_findings

        Retrieve all findings recorded in the session.

        Returns:
            Dict with "findings" list and "by_severity" counts.
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/get_findings",
            json_body={"session_id": session_id},
        )

    # ── Investigation Execution ───────────────────────────────────

    async def investigate(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/investigate

        Run the full 7-phase investigation pipeline synchronously.
        Blocks until the investigation completes.

        Returns:
            Full InvestigationResult as a dict.
        """
        return await self._request(
            "POST",
            "/api/v1/agent/tools/investigate",
            json_body={"session_id": session_id},
            timeout=self._timeout,
        )

    async def investigate_stream(
        self,
        session_id: str,
    ) -> AsyncIterator[SSEEvent]:
        """POST /api/v1/agent/tools/investigate/stream

        Run the full 7-phase investigation pipeline with SSE streaming.
        Yields events as the investigation progresses.

        SSE event types:
            phase_start    - Phase beginning (data: {phase, phase_name})
            phase_progress - Progress update (data: {phase, message})
            phase_item     - Individual item (data: {phase, type, ...})
            phase_complete - Phase finished (data: {phase, summary, metrics})
            phase_error    - Phase error (data: {phase, error})
            llm_request    - LLM prompt sent (data: {phase, model, prompt_key})
            llm_response   - LLM response received (data: {phase, model, tokens})
            data_query     - Data retrieval (data: {phase, source, operation})
            data_result    - Data result (data: {phase, source, count})
            result         - Final result (data: {full InvestigationResult})
            error          - Fatal error (data: {code, message, details})
            done           - Stream complete (data: {session_id})

        Yields:
            SSEEvent objects.
        """
        async for event in self._stream_sse(
            "POST",
            "/api/v1/agent/tools/investigate/stream",
            json_body={"session_id": session_id},
        ):
            yield event

    # ── Expert Panel ──────────────────────────────────────────────

    async def ask_experts(
        self,
        question: str,
        *,
        log_content: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/agent/tools/ask_experts

        Ask the expert panel a question (synchronous).

        Returns:
            Dict with "answer", "experts_consulted", "question_id".
        """
        body: dict[str, Any] = {"question": question}
        if log_content:
            body["log_content"] = log_content
        return await self._request(
            "POST",
            "/api/v1/agent/tools/ask_experts",
            json_body=body,
        )

    async def ask_experts_stream(
        self,
        question: str,
        *,
        log_content: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """POST /api/v1/agent/tools/ask_experts/stream

        Ask the expert panel with SSE streaming for real-time updates.

        SSE event types:
            expert_start   - Expert begins answering
            expert_chunk   - Partial answer text
            expert_done    - Expert finished
            result         - Final compiled answer
            done           - Stream complete

        Yields:
            SSEEvent objects.
        """
        body: dict[str, Any] = {"question": question}
        if log_content:
            body["log_content"] = log_content
        async for event in self._stream_sse(
            "POST",
            "/api/v1/agent/tools/ask_experts/stream",
            json_body=body,
        ):
            yield event

    # ── Feedback ──────────────────────────────────────────────────

    async def submit_feedback(
        self,
        investigation_id: str,
        *,
        correct: bool,
        actual_cause: str | None = None,
        corrected_summary: str | None = None,
        feedback_source: str = "api_client",
    ) -> dict[str, Any]:
        """POST /api/v1/investigations/{id}/feedback

        Submit feedback on an investigation result.

        Returns:
            Dict with "message", "patterns_updated", "patterns_created".
        """
        return await self._request(
            "POST",
            f"/api/v1/investigations/{investigation_id}/feedback",
            json_body={
                "correct": correct,
                "actual_cause": actual_cause,
                "corrected_summary": corrected_summary,
                "feedback_source": feedback_source,
            },
        )

    # ── Read-Only Queries (non-session) ───────────────────────────

    async def list_investigations(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/investigations -- list recent investigations."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if outcome:
            params["outcome"] = outcome
        return await self._request("GET", "/api/v1/investigations", params=params)

    async def get_investigation(
        self,
        investigation_id: str,
    ) -> dict[str, Any]:
        """GET /api/v1/investigations/{id} -- get full investigation details."""
        return await self._request(
            "GET", f"/api/v1/investigations/{investigation_id}"
        )

    async def get_investigation_quality(
        self,
        investigation_id: str,
    ) -> dict[str, Any]:
        """GET /api/v1/investigations/{id}/quality -- get quality analysis."""
        return await self._request(
            "GET", f"/api/v1/investigations/{investigation_id}/quality"
        )
```

### Key Design Decisions

1. **All tool calls are POST**: Even read-like tools (search_logs, find_function) use POST because they require a `session_id` in the body and operate on session state. This follows the RPC-over-HTTP pattern used by session-scoped tools.

2. **SSE streams return `AsyncIterator[SSEEvent]`**: Callers consume with `async for`, which naturally handles backpressure and cleanup.

3. **Timeout defaults to 300s**: Investigation can take several minutes with LLM calls. The connect timeout is always 10s to fail fast on unreachable servers.

4. **No Pydantic models in the client interface**: Methods accept and return plain dicts. This keeps the client library lightweight and avoids version coupling between client and server models. Callers that want typed access can wrap with their own models.

5. **Thread safety**: Each `AgentClient` instance owns one `httpx.AsyncClient`. For concurrent use, create multiple instances or use httpx's built-in connection pooling.

---

## 4.2 CLI Design (`srcs/cli/investigate.py`)

### Previous Direct Path (Removed)

The CLI previously created an `InvestigationCoordinator` through `CoordinatorFactory`, wired up logging wrappers manually, and drove the investigation loop directly. This path has been **removed** in favor of the API-only approach below:

```python
# BEFORE (current srcs/cli/investigate.py, abbreviated)

from srcs.config import CoordinatorFactory, load_config
from srcs.knowledge import KnowledgeBase, PatternLearner
from srcs.llm import create_llm_provider
from srcs.models.log_parser import parse_log_file, extract_error_and_context

async def run_investigation(log_file, error_line, context_lines, config_file,
                            verbose, message, llm_log, llm_all, content,
                            additional_files):
    app_config = load_config(config_file)

    # Parse logs locally
    logs = parse_log_file(log_file)
    error, context = extract_error_and_context(logs, error_line, context_lines)

    # Build multi-file source_files locally
    if additional_files:
        source_files = [SourceFile(...) for af in additional_files]

    # Create coordinator with optional logging wrappers
    if effective_verbose and effective_llm_log:
        llm = create_llm_provider(app_config.llm)
        kb = KnowledgeBase(app_config.storage, llm)
        logging_llm = LoggingLLMProvider(llm, on_llm_event)
        logging_kb = LoggingKnowledgeBase(kb, on_data_event)
        coordinator = InvestigationCoordinator(
            logging_kb, logging_llm, app_config.investigation, ...
        )
        coordinator.configure_pipeline(app_config.pipeline)
    else:
        coordinator = CoordinatorFactory.create(app_config)

    # Run investigation
    result = await coordinator.investigate(error, context, callback=...,
                                           source_files=source_files)
    display_result(console, result, effective_verbose)
```

**Problems with this approach:**

- CLI imports 8+ internal modules (`srcs.agent`, `srcs.config`, `srcs.knowledge`, `srcs.llm`, `srcs.models`, `srcs.output`, `srcs.extraction`, logging wrappers)
- Manual wiring of `LoggingLLMProvider` and `LoggingKnowledgeBase`
- Log parsing duplicated between CLI and Slack
- No way to run CLI against a remote API server

### Current Architecture: API-Only Path

The CLI now exclusively uses `AgentClient` for all operations. The API URL is resolved from the `--api-url` flag, `ARTDAQ_API_URL` env var, or defaults to `http://localhost:8000`. The CLI can also use an in-process ASGI transport for zero-overhead local operation:

```python
# srcs/cli/investigate.py -- AgentClient path (abbreviated)

from srcs.api.client import AgentClient

async def _run_via_agent_client(
    api_url: str,
    log_file: Path | None,
    error_line: int | None,
    context_lines: int,
    message: str | None,
    content: str | None,
    verbose: bool | None,
) -> None:
    # Prepare log content from file, message, or content arg
    if message is not None:
        log_content = message
    elif content is not None:
        log_content = content
    elif log_file is not None:
        log_content = log_file.read_text(encoding="utf-8", errors="replace")
    else:
        console.print("[red]No input provided[/red]")
        return

    async with AgentClient(api_url) as client:
        session = await client.create_session()
        sid = session["session_id"]

        try:
            # Parse logs (skip for message-based investigation)
            if message is None:
                await client.parse_logs(
                    sid, log_content,
                    error_line=error_line,
                    context_lines=context_lines,
                )

            # Run investigation (streaming or sync based on verbose flag)
            if verbose:
                async for event in client.investigate_stream(
                    sid, error_message=message
                ):
                    # Handle SSE events for display
                    ...
            else:
                result = await client.investigate(sid, error_message=message)
                # Display result summary
                ...
        finally:
            try:
                await client.delete_session(sid)
            except Exception:
                pass
```

### Dual-Path Summary

| Aspect | Direct Path (default) | AgentClient Path (`--api-url`) |
|--------|----------------------|-------------------------------|
| Imports | 8+ internal modules (`srcs.agent`, `srcs.config`, `srcs.knowledge`, `srcs.llm`, etc.) | `srcs.api.client.AgentClient` only |
| Log parsing | Local (`parse_log_file`, `extract_error_and_context`) | `client.parse_logs()` (server-side) |
| Coordinator | `CoordinatorFactory.create()` with manual logging wrappers | `client.create_session()` |
| Investigation | `coordinator.investigate(error, context, ...)` | `client.investigate(session_id)` or `client.investigate_stream()` |
| Verbose mode | `PhaseEvent` callback wired to `VerboseDisplay` | SSE events with simplified console output |
| Feedback | Direct `KnowledgeBase` + `PatternLearner` calls | Not implemented in API path (direct path only) |
| Multi-file | Manual `SourceFile` construction + read | Not implemented in API path (direct path only) |
| Configuration | `load_config()` for everything | API URL from `--api-url` flag; server handles the rest |

Both paths coexist in the same `run_investigation()` function. The `--api-url` flag triggers the API path; its absence uses the direct coordinator path. This is an intentional design that allows the CLI to work standalone or against a remote API server.

### CLI Flag

```python
# In srcs/cli/main.py, the investigate command includes:
@app.command()
def investigate(
    log_file: Path = typer.Argument(...),
    # ... existing flags ...
    api_url: str = typer.Option(
        None, "--api-url",
        help="Agent API server URL (default: http://localhost:8000)"
    ),
):
    ...
```

---

## 4.3 Slack Bot Design (`srcs/slack/app.py`)

### Previous Direct Path (Removed)

The Slack bot previously created a coordinator via `CoordinatorFactory.create_with_logging()`, manually wired `ProgressReporter` callbacks, and ran the investigation in-process. This path has been **removed** — the Slack bot now exclusively uses `AgentClient`. All investigation and knowledge operations flow through the REST API:

```python
# BEFORE (current srcs/slack/app.py, abbreviated)

from srcs.config import CoordinatorFactory, load_config
from srcs.knowledge import KnowledgeBase, PatternLearner
from srcs.llm import create_llm_provider

async def _run_and_report_investigation(app_config, event, client, say,
                                         error, context, channel_config, ...):
    reporter = ProgressReporter(say=say, verbose=channel_config.verbose, ...)

    # Create coordinator with logging wrappers
    coordinator, md_formatter, collected_events, _, logging_llm = (
        CoordinatorFactory.create_with_logging(
            app_config,
            enable_logging=channel_config.llm_logging,
            full_output=channel_config.full_output,
            llm_callback=reporter.on_llm_event,
            data_callback=reporter.on_data_event,
        )
    )

    reporter.start()
    investigation_result = await coordinator.investigate(
        error, context,
        callback=phase_callback,
        source_files=source_files,
    )
    await reporter.stop()

    # Format and send result
    blocks = format_investigation_result(investigation_result)
    await say(text=..., blocks=blocks)
```

### Current Architecture: API-Only Path

The Slack bot now exclusively uses `AgentClient` for all operations. The API URL is resolved from `SlackSettings.api_url` or the `LOGANALYZER_SLACK_BOT_API_URL` env var:

```python
# srcs/slack/app.py -- AgentClient path (abbreviated)

from srcs.api.client import AgentClient

async def _run_investigation_via_api(
    api_url: str,
    say: Callable[..., Any],
    error: Any,
    channel_config: ChannelConfig,
    active_investigations: _ActiveInvestigations | None,
    content_hash: str,
) -> None:
    error_message = getattr(error, "message", str(error))

    async with AgentClient(api_url) as agent:
        session = await agent.create_session()
        sid = session["session_id"]
        try:
            result = await agent.investigate(sid, error_message=error_message)

            # Format API result for Slack (simplified blocks)
            outcome = result.get("outcome", "UNKNOWN")
            blocks = [...]  # Header + section with confidence, root cause, summary
            await say(text=f"Investigation complete: {outcome}", blocks=blocks)
        finally:
            if active_investigations and content_hash:
                active_investigations.finish(content_hash)
            try:
                await agent.delete_session(sid)
            except Exception:
                pass
```

> **NOTE:** The Slack bot's AgentClient path uses non-streaming `investigate()` only and formats results with simplified Slack blocks. It does not use SSE streaming or the full verbose `ProgressReporter` display. Feedback still uses the direct `KnowledgeBase` + `PatternLearner` path regardless of the `api_url` setting.

### Dual-Path Summary

| Aspect | Direct Path (default) | AgentClient Path (`api_url`) |
|--------|----------------------|------------------------------|
| Imports | `CoordinatorFactory`, `KnowledgeBase`, `PatternLearner`, `create_llm_provider`, `MarkdownFormatter` | `srcs.api.client.AgentClient` only |
| Config | `load_config()` for full app config | `api_url` from `SlackSettings` |
| Log parsing | Local `parse_log_content()`, local file download + parse | Skipped (sends error message directly to `investigate()`) |
| Investigation | In-process `coordinator.investigate()` with `ProgressReporter` | `agent.investigate(session_id)` non-streaming |
| Progress | `PhaseEvent` callback + `ProgressReporter.on_phase_event()` | Not used in API path |
| LLM logging | `LoggingLLMProvider` wrapping + `on_llm_event` callback | Not available in API path |
| Feedback | Direct `KnowledgeBase.update_calibration()` + `PatternLearner.apply_feedback()` | Same (always uses direct path) |
| File handling | Downloads from Slack, parses locally | Same download, but sends error message to API |

Both paths coexist in `_run_and_report_investigation()`. The `api_url` parameter (from `SlackSettings.api_url`) triggers the API path; its absence uses the direct coordinator path. This is an intentional design.

### Configuration

```yaml
# config.yaml -- slack section
slack:
  bot_token: "xoxb-..."
  app_token: "xapp-..."
  api_url: "http://localhost:8000"  # Optional: enables AgentClient path
```

Or via environment variable:
```bash
LOGANALYZER_SLACK_BOT_API_URL=http://localhost:8000
```

### ProgressReporter Note

> **NOTE (implementation status):** The `ProgressReporter` SSE adapter methods (`on_sse_phase_start`, `on_sse_phase_progress`, etc.) described in the original design are not used in the current implementation. The Slack bot's AgentClient path uses non-streaming `investigate()` and formats the result directly without progress reporting. The `ProgressReporter` class is only used in the direct coordinator path where it receives `PhaseEvent` callbacks natively.

---

## 4.4 MCP Server Dual-Path Design (`srcs/mcp/server.py`)

### Direct Path (Default)

The MCP server maintains a global `_coordinator` that it creates via `CoordinatorFactory.create()` on first use. This is the default behavior when `ARTDAQ_API_URL` is not set:

```python
# BEFORE (current srcs/mcp/server.py, abbreviated)

_coordinator: "InvestigationCoordinator | None" = None

async def get_coordinator() -> "InvestigationCoordinator":
    global _coordinator
    if _coordinator is None:
        from srcs.config import CoordinatorFactory, load_config
        config = load_config()
        _coordinator = CoordinatorFactory.create(config)
    return _coordinator

@mcp.tool()
async def investigate_error(error_message: str, log_content: str | None = None,
                            error_line: int | None = None,
                            context_lines: int = 60) -> str:
    coordinator = await get_coordinator()
    # Parse logs locally
    if log_content:
        logs = parse_log_content(log_content)
        error, context = extract_error_and_context(logs, error_line, context_lines)
    else:
        error = create_log_from_message(error_message)
        context = []
    # Run investigation in-process
    result = await coordinator.investigate(error, context, callback=progress_callback)
    return json.dumps(result.model_dump(mode="json"), ...)
```

### AgentClient Path (via `ARTDAQ_API_URL` env var)

When `ARTDAQ_API_URL` is set, the MCP server's command tools (`investigate_error`, etc.) delegate to the REST API via `AgentClient`. A global `AgentClient` instance with a persistent session is created on first use:

```python
# srcs/mcp/server.py -- AgentClient path (abbreviated)

_client: "AgentClient | None" = None
_client_session_id: str | None = None

async def _get_agent_client() -> "AgentClient | None":
    """Get or create AgentClient if API URL is configured."""
    global _client, _client_session_id
    api_url = os.environ.get("ARTDAQ_API_URL")
    if not api_url:
        return None

    if _client is None:
        from srcs.api.client import AgentClient
        _client = AgentClient(api_url)
        await _client.__aenter__()
        session = await _client.create_session()
        _client_session_id = session["session_id"]

    return _client

# Inside investigate_error tool:
async def investigate_error(...) -> str:
    # AgentClient path: use REST API when configured
    agent = await _get_agent_client()
    if agent is not None and _client_session_id is not None:
        result_data = await agent.investigate(
            _client_session_id, error_message=error_message
        )
        return json.dumps(result_data, default=_json_default, indent=2)

    # Direct path: use coordinator (falls through if no API URL)
    coordinator = await get_coordinator()
    ...
```

> **NOTE:** The MCP server's read-only data tools (binder access, pattern queries, calibration, etc.) always use direct `BinderStore` and `aiosqlite` access regardless of the `ARTDAQ_API_URL` setting. Only the command tools (`investigate_error`, `analyze_message`, `submit_feedback`, `ask_experts`) check for the AgentClient path.

### Dual-Path Summary

| Aspect | Direct Path (default) | AgentClient Path (`ARTDAQ_API_URL`) |
|--------|----------------------|-------------------------------------|
| Coordinator | Global `_coordinator` via `CoordinatorFactory.create()` | Not used -- delegates via `AgentClient` |
| Imports | `srcs.config`, `srcs.agent`, `srcs.knowledge`, `srcs.models`, `srcs.persona`, `srcs.workbinder` | Additional: `srcs.api.client` |
| Log parsing | Local `parse_log_content()`, `create_log_from_message()` | Skipped (sends error message to `investigate()`) |
| Investigation | In-process `coordinator.investigate()` | `agent.investigate(session_id)` non-streaming |
| Progress | MCP Context directly from coordinator callback | Not available in API path |
| Data access | Direct `BinderStore`, direct `aiosqlite` | Same (always direct for read-only tools) |
| Feedback | Direct `KnowledgeBase` + `PatternLearner` | `agent.investigate()` includes pattern learning server-side |
| Configuration | `load_config()` for full app config | `ARTDAQ_API_URL` env var triggers API path |

Both paths coexist in the same tool functions. The `_get_agent_client()` helper returns `None` when `ARTDAQ_API_URL` is not set, causing the tool to fall through to the direct coordinator path. This is an intentional design that allows the MCP server to work standalone or against a remote API server.

### MCP Tool Interface Compatibility

The MCP tool signatures (parameter names, types, return format) remain identical from the MCP client's perspective. A Claude Desktop user or VS Code extension calling `investigate_error` sees exactly the same interface regardless of which backend path is active.

---


---

> [← Pipeline & Admin Tools](agentic-rest-service-design-ch5-pipeline-admin-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Testing Strategy →](agentic-rest-service-design-ch7-testing-strategy.md)
