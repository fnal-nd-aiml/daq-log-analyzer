> **Agentic REST API Design Document** | [Table of Contents](agentic-rest-service-design.md) | [Next: Log Analysis Tools →](agentic-rest-service-design-ch2-log-analysis-tools.md)

---

# Agentic REST API Design Document

## Part I: Architecture Overview

---

### 1. Problem Statement

The artdaq Deep Investigation Agent currently has four client interfaces that all directly instantiate `InvestigationCoordinator` to run investigations:

| Client | File | Instantiation Pattern |
|--------|------|-----------------------|
| CLI | `srcs/cli/investigate.py` | `CoordinatorFactory.create(app_config)` or manual construction with logging wrappers |
| Slack | `srcs/slack/app.py` | `CoordinatorFactory.create_with_logging(...)` |
| MCP | `srcs/mcp/server.py` | `CoordinatorFactory.create(config)` via lazy global singleton |
| REST API | `srcs/api/dependencies.py` | FastAPI DI chain building `InvestigationCoordinator` per-request |

This creates three categories of problems:

**Duplicated initialization logic.** Each client independently loads configuration, creates LLM providers, initializes `KnowledgeBase`, configures pipelines, and wires up logging wrappers. The CLI does this in ~60 lines of branching code; Slack does it differently with its own logging callback setup; MCP caches a global coordinator; and the API uses FastAPI dependency injection. Changes to initialization (e.g., adding a new required dependency) must be replicated across all four.

**Inconsistent error handling.** The CLI catches `ValueError` and generic `Exception` with Rich console output. The API uses registered exception handlers returning JSON. Slack formats errors as Slack blocks. MCP returns JSON strings. There is no shared contract for what errors look like or how they propagate.

**No session state sharing.** Each investigation is a one-shot call to `coordinator.investigate()`. There is no way to pause an investigation, inspect intermediate findings, invoke individual tools (code lookup, log search, pattern matching) outside the fixed 7-phase pipeline, or compose a custom investigation workflow. Every client gets the same monolithic pipeline or nothing.

**The agentic approach** solves these problems by making the REST API the single authoritative interface for all investigation capabilities. Instead of exposing one endpoint that runs the entire 7-phase pipeline, the API exposes individual capabilities (log parsing, code search, hypothesis generation, evidence seeking) as composable tools within a session. The LLM (or a human operator) decides which tools to invoke and in what order. All clients -- CLI, Slack, MCP, and external integrations -- call the API rather than directly constructing coordinators.

---

### 2. Target Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Clients                                     │
│                                                                          │
│   ┌───────┐    ┌─────────┐    ┌───────┐    ┌──────────────┐             │
│   │  CLI  │    │  Slack  │    │  MCP  │    │  External /  │             │
│   │       │    │   Bot   │    │Server │    │  Web UI      │             │
│   └───┬───┘    └────┬────┘    └───┬───┘    └──────┬───────┘             │
│       │             │             │               │                      │
│       └─────────────┴──────┬──────┴───────────────┘                      │
│                            │                                             │
│                   ┌────────▼────────┐                                    │
│                   │  AgentClient    │  srcs/api/client.py                │
│                   │  (httpx async)  │  Python client library             │
│                   └────────┬────────┘                                    │
└────────────────────────────┼─────────────────────────────────────────────┘
                             │ HTTP/SSE
┌────────────────────────────┼─────────────────────────────────────────────┐
│                    REST API │  /api/v1/agent/                            │
│                            │                                             │
│                   ┌────────▼────────┐                                    │
│                   │ Session Manager │  In-memory session store            │
│                   │                 │  with optional persistence          │
│                   └────────┬────────┘                                    │
│                            │                                             │
│                   ┌────────▼────────┐                                    │
│                   │  Tool Router    │  Routes tool invocations to         │
│                   │                 │  backend implementations            │
│                   └────────┬────────┘                                    │
│                            │                                             │
│          ┌─────────────────┼─────────────────────┐                       │
│          │                 │                     │                       │
│   ┌──────▼──────┐  ┌──────▼──────┐  ┌───────────▼──────────┐            │
│   │ Log Tools   │  │ Code Tools  │  │ Investigation Tools  │            │
│   │ parse_logs  │  │ search_code │  │ generate_hypotheses  │            │
│   │ search_logs │  │ get_function│  │ seek_evidence        │            │
│   │ get_context │  │ call_graph  │  │ build_chains         │            │
│   └──────┬──────┘  └──────┬──────┘  └───────────┬──────────┘            │
│          │                 │                     │                       │
│   ┌──────▼─────────────────▼─────────────────────▼──────────┐            │
│   │                 Backend Services                         │            │
│   │                                                          │            │
│   │  ┌──────────────┐ ┌───────────┐ ┌───────────────────┐   │            │
│   │  │ KnowledgeBase│ │ CodeIndex │ │  SourceLocator    │   │            │
│   │  │ (SQLite +    │ │ (tree-    │ │  (GitHub repos)   │   │            │
│   │  │  ChromaDB)   │ │  sitter)  │ │                   │   │            │
│   │  └──────────────┘ └───────────┘ └───────────────────┘   │            │
│   │                                                          │            │
│   │  ┌──────────────┐ ┌───────────┐ ┌───────────────────┐   │            │
│   │  │ LLMProvider  │ │ Pattern   │ │  Calibration      │   │            │
│   │  │ (Ollama /    │ │ Learner   │ │  Reporter         │   │            │
│   │  │  Anthropic)  │ │           │ │                   │   │            │
│   │  └──────────────┘ └───────────┘ └───────────────────┘   │            │
│   └──────────────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────────────┘
```

All clients interact through `AgentClient`, a thin async Python wrapper around `httpx`. The REST API manages sessions, routes tool invocations, and owns all backend service lifecycles. Backend services are wired together using FastAPI `Depends()` functions (see `srcs/api/dependencies.py`), not `app.state` singletons. No client directly imports or instantiates `InvestigationCoordinator`, `KnowledgeBase`, or `LLMProvider`.

> **NOTE (implementation status):** The CLI and MCP server support dual-path operation. The CLI uses a direct `InvestigationCoordinator` by default, switching to `AgentClient` only when the `--api-url` flag is provided. The MCP server uses a direct coordinator by default, switching to `AgentClient` only when the `ARTDAQ_API_URL` environment variable is set. The Slack bot uses a direct coordinator by default, switching to `AgentClient` when its `api_url` setting is configured. This dual-path design is intentional, allowing each client to operate standalone or against a remote API server.

---

### 3. Current vs Target Comparison

| Aspect | Current | Target |
|--------|---------|--------|
| **Client integration** | Each client imports `CoordinatorFactory`, loads config, builds coordinator directly | All clients use `AgentClient` to call REST API |
| **Initialization** | Duplicated across CLI (manual + factory), Slack (factory with logging), MCP (lazy global), API (DI chain) | Single initialization in API server; clients need only a base URL |
| **Session state** | None -- each `investigate()` call is stateless and one-shot | Sessions track parsed logs, findings, hypotheses, and tool history |
| **Composability** | All-or-nothing 7-phase pipeline; no way to invoke individual phases or tools | Individual tools exposed as endpoints; LLM or human chooses sequence |
| **Error handling** | Four different error formats (Rich console, Slack blocks, JSON strings, FastAPI JSON) | Single structured JSON error contract; clients adapt for display |
| **Streaming** | CLI uses `PhaseEvent` callbacks; Slack posts progressive updates; MCP uses `Context.report_progress` | SSE streaming with standardized event types mapped from `PhaseEvent`, `LLMEvent`, `DataRetrievalEvent` |
| **Configuration** | Each client loads `config.yaml` independently | API server owns config; clients are config-free |
| **Testing** | Must test each client's coordinator wiring separately | Test tool endpoints once; client tests are HTTP-level |
| **Extensibility** | Adding a tool requires changes in coordinator, all clients | Adding a tool requires one endpoint + tool registration; clients discover via session |

---

### 4. Session Lifecycle

Sessions are the central coordination primitive. A session groups related tool invocations into a coherent investigation context, accumulating state as tools are called.

**Lifecycle stages:**

```
   CREATE              INVOKE TOOLS              CLOSE
     │                      │                      │
     ▼                      ▼                      ▼
┌─────────┐   ┌───────────────────────────┐   ┌─────────┐
│  active  │──►│  tools mutate session     │──►│ closed  │
│          │   │  state (logs, findings,   │   │         │
│  empty   │   │  hypotheses, history)     │   │ archived│
│  state   │   └───────────────────────────┘   └─────────┘
└─────────┘              │    ▲
                         │    │
                         └────┘
                       (iterative)
```

**What sessions track:**

- **Parsed logs** -- Log entries parsed from uploaded files or content, available to all subsequent tools without re-parsing.
- **Findings** -- Intermediate conclusions recorded by the agent or user during investigation. Each finding has severity, evidence references, and a timestamp.
- **Hypotheses** -- Root cause hypotheses generated or manually added. Each has a score, source tier, and linked evidence.
- **Tool history** -- Complete record of every tool invocation within the session: tool name, arguments, result summary, timestamp, and duration.

**Session state model:**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-02-14T10:00:00Z",
  "updated_at": "2026-02-14T10:05:32Z",
  "status": "active",
  "metadata": {
    "source": "cli",
    "user_id": "operator-1"
  },
  "state": {
    "parsed_logs": [
      {
        "log_id": "log-001",
        "filename": "BoardReader_01.log",
        "entry_count": 1247,
        "error_count": 23,
        "time_range": {
          "start": "2026-02-14T10:30:00Z",
          "end": "2026-02-14T10:45:00Z"
        }
      }
    ],
    "findings": [
      {
        "finding_id": "f-001",
        "finding": "Fragment timeout on link 0x0100 preceded all downstream errors",
        "severity": "critical",
        "evidence": [
          {
            "log_id": "log-001",
            "lines": [4523, 4524],
            "excerpt": "Fragment timeout after 5000ms on link 0x0100"
          }
        ],
        "recorded_at": "2026-02-14T10:03:15Z"
      }
    ],
    "hypotheses": [
      {
        "hypothesis_id": "h-001",
        "description": "Frontend hardware link failure on BoardReader_01",
        "score": 0.72,
        "source": "pattern",
        "evidence_ids": ["f-001"],
        "created_at": "2026-02-14T10:04:00Z"
      }
    ],
    "tool_history": [
      {
        "invocation_id": "inv-001",
        "tool": "parse_logs",
        "arguments": {"content": "...", "error_line": 150},
        "result_summary": "Parsed 1247 entries, 23 errors found",
        "started_at": "2026-02-14T10:01:00Z",
        "duration_ms": 340,
        "status": "success"
      }
    ]
  }
}
```

**Persistence:** Sessions are stored in-memory by default for fast access. Optional persistence to SQLite allows sessions to survive server restarts and enables the `GET /api/v1/agent/sessions/{id}` endpoint to return historical sessions. Session data that exceeds a configurable TTL (default: 24 hours) is automatically archived.

---

### 5. SSE Streaming Design

Long-running operations (`investigate_stream` and `ask_experts`) stream progress events to clients using Server-Sent Events (SSE). This replaces the current per-client callback mechanisms with a single transport.

**Mapping from existing callback types to SSE events:**

| Callback Type | Event Fields | SSE Event Name | When Emitted |
|---------------|-------------|----------------|--------------|
| `PhaseEvent` (start) | `phase`, `phase_name`, `message` | `phase_start` | Phase begins execution |
| `PhaseEvent` (progress) | `phase`, `phase_name`, `data`, `message` | `phase_progress` | Intermediate progress within a phase |
| `PhaseEvent` (item) | `phase`, `phase_name`, `data` | `phase_item` | Individual item produced (hypothesis, evidence) |
| `PhaseEvent` (complete) | `phase`, `phase_name`, `data`, `message` | `phase_complete` | Phase finishes execution |
| `LLMEvent` (request) | `phase`, `model_name`, `system_prompt`, `user_prompt` | `llm_request` | LLM call initiated |
| `LLMEvent` (response) | `phase`, `model_name`, `response`, `parse_failed` | `llm_response` | LLM response received |
| `DataRetrievalEvent` (query) | `phase`, `source`, `operation`, `query_params` | `data_query` | Knowledge base query issued |
| `DataRetrievalEvent` (result) | `phase`, `source`, `operation`, `result_count` | `data_result` | Knowledge base results returned |
| -- | `investigation_id`, `outcome`, `result` | `complete` | Investigation finished |
| -- | `code`, `message`, `details` | `error` | Unrecoverable error |

**Expert panel events** (`ask_experts` with `stream=true`):

| Source | Event Fields | SSE Event Name | When Emitted |
|--------|-------------|----------------|--------------|
| PanelOrchestrator | `question_type`, `question_id` | `classification` | Question classified |
| PanelOrchestrator | `personas`, `count` | `panel_selected` | Personas selected for panel |
| PanelOrchestrator | `persona`, `phase` | `contribution_start` | Persona begins answering |
| PanelOrchestrator | `persona`, `content`, `confidence` | `contribution_complete` | Persona finished answering |
| PanelOrchestrator | `persona`, `error` | `contribution_error` | Persona failed (exception) |
| PanelOrchestrator | `consensus_score`, `endorsements`, `critiques` | `voting_complete` | Voting round finished |
| PanelOrchestrator | `round`, `disagreements` | `deliberation_start` | Consensus below threshold (0.7) |
| PanelOrchestrator | `round`, `resolved` | `deliberation_complete` | Deliberation round finished |
| PanelOrchestrator | `answer`, `confidence`, `key_points` | `synthesis_complete` | Final panel response synthesized |

**SSE event format:**

Each event follows the standard SSE wire format. The `event:` field identifies the type, and `data:` contains a JSON payload.

```
event: phase_start
data: {"phase": 0, "phase_name": "Prior Knowledge Retrieval", "message": "Retrieving patterns and similar cases"}

event: llm_request
data: {"phase": 1, "model_name": "claude-3-5-sonnet", "prompt_summary": "Generate hypotheses for fragment timeout error"}

event: llm_response
data: {"phase": 1, "model_name": "claude-3-5-sonnet", "tokens_used": 1247, "parse_success": true}

event: phase_item
data: {"phase": 1, "phase_name": "Hypothesis Generation", "data": {"hypothesis_id": "h-001", "description": "Frontend link failure", "score": 0.72}}

event: phase_complete
data: {"phase": 1, "phase_name": "Hypothesis Generation", "data": {"hypothesis_count": 5, "top_score": 0.72}}

event: data_query
data: {"phase": 2, "source": "chromadb", "operation": "find_similar_investigations", "query_params": {"error_pattern": "Fragment timeout"}}

event: complete
data: {"session_id": "a1b2c3d4-...", "investigation_id": "inv-20260214-001", "outcome": "CONFIDENT", "result_url": "/api/v1/investigations/inv-20260214-001"}
```

**Client consumption pattern:**

```python
import httpx

async with httpx.AsyncClient() as client:
    async with client.stream(
        "POST",
        "http://localhost:8000/api/v1/agent/sessions/{session_id}/investigate_stream",
        json={"trigger_error": {...}, "context_logs": [...]},
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
                handle_event(event_type, data)
```

**Backpressure and reconnection:** The SSE endpoint sets `Cache-Control: no-cache` and `Connection: keep-alive`. Each event includes an `id:` field (monotonic counter) to support `Last-Event-ID` based reconnection. If a client disconnects mid-stream, the investigation continues; the client can reconnect and receive events from where it left off (buffered for up to 60 seconds).

---

### 6. Error Handling Conventions

All API errors follow a single structured format. This replaces the current mix of `{"detail": "..."}` responses scattered across exception handlers in `app.py`.

**Error response schema:**

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session a1b2c3d4-... does not exist or has been archived.",
    "details": {
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "suggestion": "Create a new session with POST /api/v1/agent/sessions"
    },
    "recovery_hint": "Create a new session and re-upload your log data."
  }
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error.code` | `string` | Yes | Machine-readable error code (snake_case) |
| `error.message` | `string` | Yes | Human-readable description of what went wrong |
| `error.details` | `object` | No | Additional context specific to the error |
| `error.recovery_hint` | `string` | No | Actionable suggestion for the caller (or the LLM) |

**Standard HTTP status codes and error codes:**

| HTTP Status | Error Code | When Used | Example |
|-------------|------------|-----------|---------|
| 400 | `bad_request` | Malformed request body | Missing required field |
| 400 | `invalid_tool` | Unknown tool name in invocation | `tool: "nonexistent_tool"` |
| 404 | `SESSION_NOT_FOUND` | Session ID does not exist | Expired or never created |
| 404 | `investigation_not_found` | Investigation ID does not exist | Typo in ID |
| 409 | `SESSION_CLOSED` | Operation conflicts with session state | Invoking tool on closed session |
| 409 | `session_already_closed` | Attempting to close an already-closed session | Double-close |
| 404 | `TOOL_NOT_FOUND` | Requested tool name not registered | Typo in tool name |
| 422 | `VALIDATION_ERROR` | Request parses but fails semantic validation | `error_line` exceeds log length |
| 500 | `internal_error` | Unexpected server-side failure | Unhandled exception |
| 500 | `TOOL_EXECUTION_ERROR` | Tool raised an exception during execution | Code index unavailable |
| 500 | `INTERNAL_ERROR` | Server-side error | Unexpected exception |

**Examples:**

400 -- Invalid tool arguments:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Parameter 'severity' must be one of: ERROR, WARNING, INFO, DEBUG.",
    "details": {
      "tool": "search_logs",
      "parameter": "severity",
      "provided_value": "FATAL",
      "allowed_values": ["ERROR", "WARNING", "INFO", "DEBUG"]
    },
    "recovery_hint": "Use one of the allowed severity values and retry."
  }
}
```

404 -- Session not found:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session a1b2c3d4-e5f6-7890-abcd-ef1234567890 does not exist or has been archived.",
    "details": {
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    },
    "recovery_hint": "Create a new session with POST /api/v1/agent/sessions."
  }
}
```

409 -- Session conflict:

```json
{
  "error": {
    "code": "SESSION_CLOSED",
    "message": "Cannot invoke tools on a closed session.",
    "details": {
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "session_status": "closed",
      "closed_at": "2026-02-14T11:00:00Z"
    },
    "recovery_hint": "Create a new session to continue investigating."
  }
}
```

500 -- Tool execution error:

```json
{
  "error": {
    "code": "TOOL_EXECUTION_ERROR",
    "message": "Tool 'search_code' failed: Code index not initialized.",
    "details": {
      "tool": "search_code",
      "exception_type": "ExtractionError",
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    },
    "recovery_hint": "Ensure source repositories are synced via POST /api/v1/admin/source/sync, then retry."
  }
}
```

503 -- LLM unavailable:

```json
{
  "error": {
    "code": "TOOL_EXECUTION_ERROR",
    "message": "Cannot reach LLM provider: Connection refused to http://localhost:11434.",
    "details": {
      "provider": "ollama",
      "host": "http://localhost:11434"
    },
    "recovery_hint": "Start the Ollama server or configure an alternative LLM provider."
  }
}
```

---

### 7. API Client Library Design

`srcs/api/client.py` provides an async Python client that wraps all agent API endpoints. Clients (CLI, MCP) use this library when configured to connect to a remote API server.

**Tool response format:** Tool responses are returned as flat JSON objects. Each tool defines its own response schema. There is no standardized envelope wrapping tool results. Tools return their result dicts directly via `JSONResponse` (see `srcs/api/tools/router.py`).

**Dependency injection:** Backend services are wired together using FastAPI `Depends()` functions in `srcs/api/dependencies.py`. The dependency chain flows from `Settings` through `LLMConfig`, `StorageConfig`, `LLMProvider`, `KnowledgeBase`, and up to `InvestigationCoordinator`. Sessions use a module-level singleton `SessionStore`. There is no use of `app.state` for dependency injection.

**Class: `AgentClient`**

```python
class AgentClient:
    """Typed async HTTP client for the agentic REST API.

    Wraps httpx.AsyncClient to provide typed methods for every
    agent endpoint. Handles session management, SSE streaming,
    and structured error propagation. All methods return plain
    dicts (no Pydantic response models in the client interface).

    Usage:
        async with AgentClient("http://localhost:8000") as client:
            session = await client.create_session()
            result = await client.parse_logs(session["session_id"], content="...")
            await client.delete_session(session["session_id"])
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        *,
        timeout: float = 300.0,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None: ...

    async def __aenter__(self) -> "AgentClient": ...
    async def __aexit__(self, *args) -> None: ...

    # ── Session Management ──────────────────────────────────────

    async def create_session(self) -> dict[str, Any]: ...

    async def get_session(self, session_id: str) -> dict[str, Any]: ...

    async def delete_session(self, session_id: str) -> dict[str, Any]: ...

    # ── Tool Invocations (via generic _invoke_tool) ─────────────
    # All tool methods send {session_id, params} and return flat dicts.

    async def parse_logs(
        self,
        session_id: str,
        content: str,
        error_line: int | None = None,
        context_lines: int = 60,
    ) -> dict[str, Any]: ...

    async def search_logs(
        self,
        session_id: str,
        *,
        pattern: str | None = None,
        severity: str | None = None,
        component: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]: ...

    async def get_log_context(
        self,
        session_id: str,
        line: int,
        before: int = 10,
        after: int = 10,
    ) -> dict[str, Any]: ...

    async def get_log_summary(self, session_id: str) -> dict[str, Any]: ...

    async def correlate_events(
        self,
        session_id: str,
        window_seconds: int = 5,
        level: str = "ERROR",
    ) -> dict[str, Any]: ...

    async def find_error_source(
        self,
        session_id: str,
        error_message: str,
    ) -> dict[str, Any]: ...

    async def lookup_function(
        self,
        session_id: str,
        name: str,
        file_filter: str | None = None,
    ) -> dict[str, Any]: ...

    async def get_call_graph(
        self,
        session_id: str,
        name: str,
        depth: int = 1,
        direction: str = "both",
    ) -> dict[str, Any]: ...

    async def search_code(
        self,
        session_id: str,
        query: str,
        symbol_type: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]: ...

    async def match_pattern(
        self,
        session_id: str,
        message_pattern: str,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def find_similar_investigations(
        self,
        session_id: str,
        error_message: str,
        n: int = 5,
    ) -> dict[str, Any]: ...

    async def get_prior_knowledge(
        self,
        session_id: str,
        error_message: str,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def record_finding(
        self,
        session_id: str,
        category: str,
        description: str,
        severity: str = "medium",
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def record_hypothesis(
        self,
        session_id: str,
        description: str,
        confidence: float = 0.5,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def update_hypothesis(
        self,
        session_id: str,
        hypothesis_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def get_findings_summary(self, session_id: str) -> dict[str, Any]: ...

    # ── Pipeline Tools ──────────────────────────────────────────

    async def investigate(
        self,
        session_id: str,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run investigation (non-streaming)."""
        ...

    async def investigate_stream(
        self,
        session_id: str,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[SSEEvent]:
        """Run investigation with SSE streaming."""
        ...

    async def ask_experts(
        self,
        session_id: str,
        question: str,
    ) -> dict[str, Any]: ...

    # ── Admin Tools (session-less) ──────────────────────────────

    async def init_knowledge_base(
        self,
        skip_source: bool = False,
        skip_ollama_check: bool = False,
    ) -> dict[str, Any]: ...

    async def sync_sources(self) -> dict[str, Any]: ...

    # ── Convenience Methods ─────────────────────────────────────

    async def investigate_one_shot(
        self,
        content: str,
        error_line: int | None = None,
        context_lines: int = 60,
    ) -> dict[str, Any]:
        """One-shot convenience: create session -> parse -> investigate -> close.

        Returns the investigation result dict.
        """
        ...
```

**Error propagation:** When the API returns a non-2xx response with the structured error format, `AgentClient` raises an `AgentAPIError` exception (defined in `srcs/api/errors.py`) that preserves the `code`, `message`, `details`, and `recovery_hint` fields:

```python
@dataclass
class AgentAPIError(Exception):
    """Structured error from the Agent REST API."""

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

**Client migration example (CLI dual-path design):**

The CLI supports both direct coordinator usage (default) and AgentClient-based operation (via `--api-url` flag). This is an intentional dual-path design:

```python
# srcs/cli/investigate.py -- direct path (default)
from srcs.config import CoordinatorFactory, load_config

app_config = load_config(config_file)
coordinator = CoordinatorFactory.create(app_config)
result = await coordinator.investigate(error, context, callback=callback)

# srcs/cli/investigate.py -- API path (when --api-url is provided)
from srcs.api.client import AgentClient

async with AgentClient(api_url) as client:
    session = await client.create_session()
    sid = session["session_id"]
    await client.parse_logs(sid, log_content, error_line=error_line)
    result = await client.investigate(sid, error_message=message)
    await client.delete_session(sid)
```

---

## Part II: Session Management

---

Session management endpoints create, inspect, and close investigation sessions. Sessions are the prerequisite for all tool invocations -- every tool call references a `session_id`.

---

### `POST /api/v1/agent/sessions`

**Purpose:** Create a new investigation session. Returns a session handle that the client uses for all subsequent tool invocations. The session starts with empty state and accumulates data as tools are called.

**Endpoint:** `POST /api/v1/agent/sessions`

**Request Schema:**

No request body is required. Sessions are created with default metadata.

**Response Schema (201 Created):**

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "Unique session identifier (hex string, 16 chars). Use this in all subsequent tool invocation and session management calls."
    },
    "status": {
      "type": "string",
      "enum": ["active", "closed"],
      "description": "Current session status. Newly created sessions are always 'active'."
    }
  },
  "required": ["session_id", "status"]
}
```

**Response example:**

```json
{
  "session_id": "a1b2c3d4e5f67890",
  "status": "active"
}
```

**Error Responses:**

| Status | Code | Condition |
|--------|------|-----------|
| 500 | `INTERNAL_ERROR` | Server failed to create session |

**Implementation notes:**

- Generates a hex-encoded UUID prefix (16 chars) for the `session_id`.
- Stores the session in an in-memory `dict[str, Session]` protected by an `asyncio.Lock`.
- Sessions have a 24-hour TTL. Expired sessions are lazily reaped on access.
- No authentication is enforced.

**Example (curl):**

```bash
curl -X POST http://localhost:8000/api/v1/agent/sessions
```

---

### `GET /api/v1/agent/sessions/{session_id}`

**Purpose:** Retrieve the current state of an existing session. Returns aggregated counts for findings, hypotheses, parsed logs, and tool invocations, plus metadata. Use this to check session progress or verify session liveness.

**Endpoint:** `GET /api/v1/agent/sessions/{session_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | `string` | Yes | The session identifier returned from `POST /api/v1/agent/sessions`. |

**Response Schema (200 OK):**

```json
{
  "type": "object",
  "properties": {
    "metadata": {
      "type": "object",
      "properties": {
        "session_id": { "type": "string" },
        "created_at": { "type": "number", "description": "Unix timestamp of session creation." },
        "last_accessed_at": { "type": "number", "description": "Unix timestamp of last access." },
        "status": { "type": "string", "enum": ["active", "closed"] },
        "tool_invocation_count": { "type": "integer" }
      }
    },
    "findings_count": {
      "type": "integer",
      "description": "Number of findings recorded in this session."
    },
    "hypotheses_count": {
      "type": "integer",
      "description": "Number of hypotheses generated in this session."
    },
    "parsed_logs_count": {
      "type": "integer",
      "description": "Number of log entries parsed in this session."
    },
    "tool_invocation_count": {
      "type": "integer",
      "description": "Total number of tools invoked during the session."
    },
    "has_investigation_result": {
      "type": "boolean",
      "description": "Whether the investigate tool has been called and produced a result."
    }
  },
  "required": ["metadata", "findings_count", "hypotheses_count", "parsed_logs_count", "tool_invocation_count", "has_investigation_result"]
}
```

**Response example:**

```json
{
  "metadata": {
    "session_id": "a1b2c3d4e5f67890",
    "created_at": 1707904800.0,
    "last_accessed_at": 1707905132.0,
    "status": "active",
    "tool_invocation_count": 3
  },
  "findings_count": 1,
  "hypotheses_count": 2,
  "parsed_logs_count": 1247,
  "tool_invocation_count": 3,
  "has_investigation_result": false
}
```

**Error Responses:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `SESSION_NOT_FOUND` | No session exists with the given ID |
| 409 | `SESSION_CLOSED` | Session has been closed |
| 500 | `INTERNAL_ERROR` | Server failed to retrieve session state |

**Error example (404):**

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'ffffffffffffffff' does not exist or has expired.",
    "recovery_hint": "Create a new session with POST /api/v1/agent/sessions."
  }
}
```

**Implementation notes:**

- Touches the session (updates `last_accessed_at`).
- Returns aggregated counts rather than full state arrays to keep response sizes small.
- Full state data (parsed logs, findings, hypotheses) is accessed via individual tools (`get_findings_summary`, `get_log_summary`, etc.).

**Example (curl):**

```bash
curl http://localhost:8000/api/v1/agent/sessions/a1b2c3d4e5f67890
```

---

### `DELETE /api/v1/agent/sessions/{session_id}`

**Purpose:** Close and archive a session. After closure, no further tool invocations are accepted for this session. The session state remains readable via `GET` for the duration of the TTL, but the status changes to `"closed"`. Use this to signal that an investigation is complete and release server-side resources.

**Endpoint:** `DELETE /api/v1/agent/sessions/{session_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | `string` (UUID) | Yes | The session identifier to close. |

**Response Schema (200 OK):**

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "description": "The closed session identifier."
    },
    "status": {
      "type": "string",
      "enum": ["closed"],
      "description": "Session status after closure. Always 'closed'."
    }
  },
  "required": ["session_id", "status"]
}
```

**Response example:**

```json
{
  "session_id": "a1b2c3d4e5f67890",
  "status": "closed"
}
```

**Error Responses:**

| Status | Code | Condition |
|--------|------|-----------|
| 404 | `SESSION_NOT_FOUND` | No session exists with the given ID |
| 500 | `INTERNAL_ERROR` | Server failed to close session |

**Error example (404):**

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'ffffffffffffffff' does not exist or has expired.",
    "recovery_hint": "Create a new session with POST /api/v1/agent/sessions."
  }
}
```

**Implementation notes:**

- Sets the session `status` to `"closed"` and records `closed_at`.
- Closed sessions remain in the session store (in-memory and/or SQLite) until the TTL expires, so `GET` requests continue to work.
- Any in-flight SSE streams for this session are terminated with an `error` event containing `code: "SESSION_CLOSED"`.
- If the session has an associated investigation result (from `investigate_stream`), it is persisted to the knowledge base before the session is closed so that patterns can be learned from it.
- Closing a session is idempotent from the server's perspective (the session stays closed), but returns 409 to alert the caller that the operation was a no-op.

**Example (curl):**

```bash
curl -X DELETE http://localhost:8000/api/v1/agent/sessions/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

> [Table of Contents](agentic-rest-service-design.md) | [Next: Log Analysis Tools →](agentic-rest-service-design-ch2-log-analysis-tools.md)
