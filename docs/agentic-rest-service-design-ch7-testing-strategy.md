> **Agentic REST API Design Document** | [← Client Refactoring](agentic-rest-service-design-ch6-client-refactoring.md) | [Table of Contents](agentic-rest-service-design.md)

---

# Chapter 7: Testing Strategy

# Part V: Testing Strategy

## 5.1 Per-Tool Unit Test Patterns

### Standard Fixtures

Every tool endpoint test needs an async client fixture and helper to create sessions. In the actual implementation, these are defined **inline in each test file** (not in a shared conftest):

> **Note:** The design originally called for a centralized `tests/unit/api/conftest.py`, but the actual implementation uses **per-file inline fixtures** with `pytest_asyncio.fixture`. Tests are organized by tool category (e.g., `test_api_log_tools.py`, `test_api_code_tools.py`) rather than one file per tool. Test classes use class-based organization (e.g., `class TestParseLogsTool`).

```python
# Actual pattern used in each test file (e.g., tests/unit/test_api_log_tools.py)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client():
    """Async test client (defined inline per test file)."""
    from srcs.api import dependencies
    from srcs.api.app import create_app
    dependencies._session_store = None
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    dependencies._session_store = None


async def _create_session(client: AsyncClient) -> str:
    """Helper to create a session and return its ID."""
    resp = await client.post("/api/v1/agent/sessions")
    return resp.json()["session_id"]
```

### Test File Organization

| Category | Test File | Tool Coverage |
|----------|-----------|---------------|
| Log Analysis | `tests/unit/test_api_log_tools.py` | `parse_logs`, `search_logs`, `get_log_context`, `get_log_summary`, `correlate_events` |
| Code Analysis | `tests/unit/test_api_code_tools.py` | `lookup_function`, `get_call_graph`, `search_code` (note: `find_error_source` lacks tests) |
| Knowledge | `tests/unit/test_api_knowledge_tools.py` | `match_pattern`, `find_similar_investigations`, `get_prior_knowledge` |
| Findings | `tests/unit/test_api_finding_tools.py` | `record_finding`, `record_hypothesis`, `update_hypothesis`, `get_findings_summary` |
| Pipeline | `tests/unit/test_api_pipeline_tools.py` | `investigate`, `investigate_stream`, `ask_experts` |
| Admin | `tests/unit/test_api_admin_tools.py` | `init_knowledge_base`, `sync_sources` |

> **Gap:** `find_error_source` currently has **no test coverage**. This is a known gap.

### Mock Patterns

Backend services are mocked inline via `patch()` rather than centralized fixtures:

```python
# Actual mock pattern (inline per test)
with patch("srcs.api.tools.knowledge_tools._get_kb") as mock_kb:
    mock_kb.return_value = AsyncMock()
    # ... test code

with patch("srcs.api.tools.code_tools.get_code_index") as mock_index:
    mock_index.return_value = MagicMock()
    # ... test code

with patch("srcs.api.tools.pipeline_tools._get_coordinator") as mock_coord:
    mock_coord.return_value = AsyncMock()
    coordinator = AsyncMock()
    coordinator.investigate.return_value = MagicMock(
        investigation_id="inv-001",
        outcome="CONFIDENT",
        root_cause="Fragment timeout due to hardware link failure",
        confidence=0.85,
        duration_seconds=12.5,
        model_dump=MagicMock(return_value={
            "investigation_id": "inv-001",
            "outcome": "CONFIDENT",
            "root_cause": "Fragment timeout due to hardware link failure",
            "confidence": 0.85,
            "duration_seconds": 12.5,
        }),
    )
    return coordinator
```

### Test Template

Every tool test follows the same pattern: **arrange session state, invoke tool, assert response structure and side effects**.

```python
# Template pattern:

async def test_tool_name(async_client, mock_session_store, mock_backend):
    """Test description."""
    store, session = mock_session_store

    # ARRANGE: Set up session state that the tool expects
    session["trigger_error"] = {
        "timestamp": "2024-01-15T10:30:45",
        "level": "ERROR",
        "component": "BoardReader_01",
        "function": "readData",
        "message": "Fragment timeout after 5000ms",
    }

    # Patch dependencies
    with patch("srcs.api.routes.agent_tools.get_session_store", return_value=store):
        with patch("srcs.api.routes.agent_tools.get_backend", return_value=mock_backend):
            # ACT: Invoke tool endpoint
            response = await async_client.post(
                "/api/v1/agent/tools/tool_name",
                json={"session_id": "test-session-001", "param": "value"},
            )

    # ASSERT: Check response
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
    assert data["expected_field"] == "expected_value"

    # ASSERT: Check side effects on session state
    assert session["some_state_field"] is not None
```

### Complete Example: `parse_logs` Tool

```python
# tests/unit/api/test_tool_parse_logs.py

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_parse_logs_extracts_trigger_and_context(
    async_client, mock_session_store
):
    """parse_logs should parse raw log content, identify the trigger error,
    and store parsed entries in the session."""
    store, session = mock_session_store

    log_content = """2024-01-15 10:30:40.000 INFO  [BoardReader_01] initialize: Starting up
2024-01-15 10:30:42.000 INFO  [BoardReader_01] readData: Reading fragments
2024-01-15 10:30:44.000 WARNING [BoardReader_01] readData: Slow response from link 0x0100
2024-01-15 10:30:45.000 ERROR [BoardReader_01] readData: Fragment timeout after 5000ms on link 0x0100
2024-01-15 10:30:45.500 ERROR [EventBuilder_00] processFragments: Incomplete event - missing BoardReader_01"""

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/parse_logs",
            json={
                "session_id": "test-session-001",
                "content": log_content,
                "context_lines": 60,
            },
        )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "total_entries" in data
    assert data["total_entries"] == 5
    assert "trigger_error" in data
    assert "context_count" in data
    assert data["context_count"] >= 1

    # Verify trigger error is the Fragment timeout
    trigger = data["trigger_error"]
    assert trigger["level"] == "ERROR"
    assert "Fragment timeout" in trigger["message"]
    assert trigger["component"] == "BoardReader_01"
    assert trigger["function"] == "readData"

    # Verify session state was updated
    assert session["trigger_error"] is not None
    assert session["parsed_logs"] is not None
    assert len(session["context_logs"]) >= 1


@pytest.mark.asyncio
async def test_parse_logs_with_error_line(async_client, mock_session_store):
    """parse_logs with explicit error_line should use that line as trigger."""
    store, session = mock_session_store

    log_content = """2024-01-15 10:30:40.000 INFO  [BR] start: ok
2024-01-15 10:30:41.000 ERROR [BR] readData: timeout
2024-01-15 10:30:42.000 ERROR [EB] build: incomplete"""

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/parse_logs",
            json={
                "session_id": "test-session-001",
                "content": log_content,
                "error_line": 3,  # The EB error, not the first error
                "context_lines": 10,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "incomplete" in data["trigger_error"]["message"].lower()


@pytest.mark.asyncio
async def test_parse_logs_empty_content(async_client, mock_session_store):
    """parse_logs with empty content should return 422."""
    store, _ = mock_session_store

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/parse_logs",
            json={
                "session_id": "test-session-001",
                "content": "",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_parse_logs_invalid_session(async_client):
    """parse_logs with unknown session_id should return 404."""
    store = MagicMock()
    store.get.return_value = None

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/parse_logs",
            json={
                "session_id": "nonexistent",
                "content": "some log content",
            },
        )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "SESSION_NOT_FOUND"
```

### Complete Example: `search_logs` Tool

```python
# tests/unit/api/test_tool_search_logs.py

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def session_with_parsed_logs(mock_session_store):
    """Session that already has parsed log entries."""
    store, session = mock_session_store
    session["parsed_logs"] = [
        {
            "line": 1,
            "timestamp": "2024-01-15T10:30:40.000",
            "level": "INFO",
            "component": "BoardReader_01",
            "function": "initialize",
            "message": "Starting up",
        },
        {
            "line": 2,
            "timestamp": "2024-01-15T10:30:42.000",
            "level": "INFO",
            "component": "BoardReader_01",
            "function": "readData",
            "message": "Reading fragments from link 0x0100",
        },
        {
            "line": 3,
            "timestamp": "2024-01-15T10:30:44.000",
            "level": "WARNING",
            "component": "BoardReader_01",
            "function": "readData",
            "message": "Slow response from link 0x0100",
        },
        {
            "line": 4,
            "timestamp": "2024-01-15T10:30:45.000",
            "level": "ERROR",
            "component": "BoardReader_01",
            "function": "readData",
            "message": "Fragment timeout after 5000ms on link 0x0100",
        },
        {
            "line": 5,
            "timestamp": "2024-01-15T10:30:45.500",
            "level": "ERROR",
            "component": "EventBuilder_00",
            "function": "processFragments",
            "message": "Incomplete event - missing BoardReader_01 data",
        },
    ]
    return store, session


@pytest.mark.asyncio
async def test_search_logs_grep(async_client, session_with_parsed_logs):
    """search_logs with grep should filter by message pattern."""
    store, session = session_with_parsed_logs

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/search_logs",
            json={
                "session_id": "test-session-001",
                "grep": "timeout",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] == 1
    assert len(data["entries"]) == 1
    assert "timeout" in data["entries"][0]["message"].lower()


@pytest.mark.asyncio
async def test_search_logs_severity_filter(async_client, session_with_parsed_logs):
    """search_logs with severity filter should return matching or higher entries."""
    store, _ = session_with_parsed_logs

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/search_logs",
            json={
                "session_id": "test-session-001",
                "severity": "ERROR",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] == 2
    assert all(e["level"] == "ERROR" for e in data["entries"])


@pytest.mark.asyncio
async def test_search_logs_component_filter(async_client, session_with_parsed_logs):
    """search_logs filtered by component returns only that component."""
    store, _ = session_with_parsed_logs

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/search_logs",
            json={
                "session_id": "test-session-001",
                "component": "EventBuilder_00",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] == 1
    assert data["entries"][0]["component"] == "EventBuilder_00"


@pytest.mark.asyncio
async def test_search_logs_pagination(async_client, session_with_parsed_logs):
    """search_logs respects limit and offset."""
    store, _ = session_with_parsed_logs

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/search_logs",
            json={
                "session_id": "test-session-001",
                "limit": 2,
                "offset": 0,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 2
    assert data["total_matches"] == 5
    assert data["truncated"] is True


@pytest.mark.asyncio
async def test_search_logs_no_parsed_logs(async_client, mock_session_store):
    """search_logs before parsing should return 409 (no logs parsed yet)."""
    store, session = mock_session_store
    session["parsed_logs"] = None

    with patch(
        "srcs.api.routes.agent_tools.get_session_store",
        return_value=store,
    ):
        response = await async_client.post(
            "/api/v1/agent/tools/search_logs",
            json={"session_id": "test-session-001"},
        )

    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "no_parsed_logs"
    assert data["error"]["recovery_hint"] == "Call parse_logs first"
```

---

## 5.2 Integration Test Approach

Integration tests verify complete workflows through the API layer, using real (in-memory) storage but mocked LLM providers to avoid external dependencies.

### Database Fixtures

```python
# tests/integration/conftest.py

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from srcs.api.app import create_app


@pytest.fixture
def temp_data_dir():
    """Temporary data directory for SQLite and ChromaDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        (data_dir / "chroma").mkdir()
        yield data_dir


@pytest.fixture
def mock_llm_provider():
    """Mock LLM that returns deterministic responses.

    Returns structured JSON matching the expected Pydantic schemas
    for each investigation phase.
    """
    llm = AsyncMock()

    # Phase 1: Hypothesis generation
    llm.generate_structured.return_value = {
        "hypotheses": [
            {
                "description": "Fragment timeout due to hardware link failure",
                "category": "hardware",
                "prior": 0.7,
                "confirming_evidence_design": "Check link status registers",
                "refuting_evidence_design": "If software timeout value is wrong",
            },
        ]
    }

    # Phase 2: Evidence seeking (generic tool call response)
    llm.generate.return_value = "Based on the evidence, the timeout is consistent with link failure."

    return llm


@pytest.fixture
def mock_chroma():
    """Mock ChromaDB client that returns empty results."""
    chroma = MagicMock()
    collection = MagicMock()
    collection.query.return_value = {"ids": [[]], "documents": [[]], "distances": [[]]}
    chroma.get_or_create_collection.return_value = collection
    return chroma


@pytest.fixture
async def integration_client(temp_data_dir, mock_llm_provider, mock_chroma):
    """Fully wired async test client with in-memory storage.

    Uses real SQLite (in temp dir), mock ChromaDB, and mock LLM.
    """
    import os
    os.environ["ARTDAQ_DATA_DIR"] = str(temp_data_dir)

    app = create_app()

    # Override dependency injection
    from srcs.api.dependencies import get_llm_provider, get_chroma_client
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_chroma_client] = lambda: mock_chroma

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

### Full Workflow Test

```python
# tests/integration/test_investigation_workflow.py

import pytest


LOG_CONTENT = """2024-01-15 10:30:40.000 INFO  [BoardReader_01] initialize: Starting data acquisition
2024-01-15 10:30:42.000 INFO  [BoardReader_01] readData: Reading fragments from link 0x0100
2024-01-15 10:30:44.000 WARNING [BoardReader_01] readData: Slow response from link 0x0100 (3200ms)
2024-01-15 10:30:45.000 ERROR [BoardReader_01] readData: Fragment timeout after 5000ms on link 0x0100
2024-01-15 10:30:45.500 ERROR [EventBuilder_00] processFragments: Incomplete event - missing BoardReader_01"""


@pytest.mark.asyncio
async def test_full_investigation_workflow(integration_client):
    """Test the complete workflow: create session -> parse -> search ->
    find source -> record finding -> investigate."""
    client = integration_client

    # Step 1: Create session
    resp = await client.post("/api/v1/agent/sessions")
    assert resp.status_code == 201
    session = resp.json()
    session_id = session["session_id"]
    assert session["status"] == "active"

    # Step 2: Parse logs
    resp = await client.post(
        "/api/v1/agent/tools/parse_logs",
        json={
            "session_id": session_id,
            "content": LOG_CONTENT,
            "context_lines": 60,
        },
    )
    assert resp.status_code == 200
    parsed = resp.json()
    assert parsed["total_entries"] == 5
    assert "Fragment timeout" in parsed["trigger_error"]["message"]

    # Step 3: Search logs for errors
    resp = await client.post(
        "/api/v1/agent/tools/search_logs",
        json={
            "session_id": session_id,
            "severity": "ERROR",
        },
    )
    assert resp.status_code == 200
    search = resp.json()
    assert search["total_matches"] == 2

    # Step 4: Find error source in code
    resp = await client.post(
        "/api/v1/agent/tools/find_error_source",
        json={
            "session_id": session_id,
            "error_message": "Fragment timeout",
            "component": "BoardReader_01",
            "function": "readData",
        },
    )
    assert resp.status_code == 200
    # May return empty if no code indexed, which is fine

    # Step 5: Record a finding
    resp = await client.post(
        "/api/v1/agent/tools/record_finding",
        json={
            "session_id": session_id,
            "finding": "Fragment timeout on link 0x0100 preceded EventBuilder incomplete event",
            "severity": "critical",
            "evidence": [
                {"line": 4, "excerpt": "Fragment timeout after 5000ms on link 0x0100"},
                {"line": 5, "excerpt": "Incomplete event - missing BoardReader_01"},
            ],
        },
    )
    assert resp.status_code == 200
    finding = resp.json()
    assert finding["finding_id"] is not None
    assert finding["total_findings"] == 1

    # Step 6: Verify findings
    resp = await client.post(
        "/api/v1/agent/tools/get_findings",
        json={"session_id": session_id},
    )
    assert resp.status_code == 200
    findings = resp.json()
    assert len(findings["findings"]) == 1
    assert findings["by_severity"]["critical"] == 1

    # Step 7: Run full investigation
    resp = await client.post(
        "/api/v1/agent/tools/investigate",
        json={"session_id": session_id},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["investigation_id"] is not None
    assert result["outcome"] in [
        "CONFIDENT", "PROBABLE", "UNCERTAIN", "INSUFFICIENT", "CONTRADICTORY"
    ]
    assert result["duration_seconds"] > 0

    # Step 8: Clean up session
    resp = await client.delete(f"/api/v1/agent/sessions/{session_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_session_lifecycle(integration_client):
    """Test session creation, retrieval, and deletion."""
    client = integration_client

    # Create
    resp = await client.post("/api/v1/agent/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    # Get
    resp = await client.get(f"/api/v1/agent/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id

    # Delete
    resp = await client.delete(f"/api/v1/agent/sessions/{session_id}")
    assert resp.status_code == 200

    # Verify gone
    resp = await client.get(f"/api/v1/agent/sessions/{session_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_feedback_after_investigation(integration_client):
    """Test feedback submission after a completed investigation."""
    client = integration_client

    # Run a quick investigation
    resp = await client.post("/api/v1/agent/sessions")
    session_id = resp.json()["session_id"]

    await client.post(
        "/api/v1/agent/tools/parse_logs",
        json={
            "session_id": session_id,
            "content": LOG_CONTENT,
            "context_lines": 60,
        },
    )

    resp = await client.post(
        "/api/v1/agent/tools/investigate",
        json={"session_id": session_id},
    )
    investigation_id = resp.json()["investigation_id"]

    # Submit positive feedback
    resp = await client.post(
        f"/api/v1/investigations/{investigation_id}/feedback",
        json={
            "correct": True,
            "feedback_source": "integration_test",
        },
    )
    assert resp.status_code == 200
    feedback = resp.json()
    assert "patterns_updated" in feedback

    # Submit negative feedback with cause
    resp = await client.post(
        f"/api/v1/investigations/{investigation_id}/feedback",
        json={
            "correct": False,
            "actual_cause": "Actually a software configuration issue",
            "feedback_source": "integration_test",
        },
    )
    assert resp.status_code == 200
```

---

## 5.3 SSE Stream Testing

SSE endpoints require special testing patterns because they return a stream of events rather than a single JSON response.

### How to Test SSE Endpoints

```python
# tests/integration/test_sse_streaming.py

import json
import pytest
from collections import defaultdict

from httpx import ASGITransport, AsyncClient


def parse_sse_events(raw_text: str) -> list[dict]:
    """Parse raw SSE text into a list of event dicts.

    Each event has "event" (type) and "data" (parsed JSON) keys.
    """
    events = []
    current_event = ""
    current_data_lines = []

    for line in raw_text.split("\n"):
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            current_data_lines.append(line[5:].strip())
        elif line == "" and current_event:
            raw_data = "\n".join(current_data_lines)
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                data = {"raw": raw_data}
            events.append({"event": current_event, "data": data})
            current_event = ""
            current_data_lines = []

    return events
```

### Verify Event Ordering

```python
@pytest.mark.asyncio
async def test_investigate_stream_event_ordering(integration_client):
    """Verify that phase_start always comes before phase_complete for each phase."""
    client = integration_client

    # Set up session with parsed logs
    resp = await client.post("/api/v1/agent/sessions")
    session_id = resp.json()["session_id"]

    await client.post(
        "/api/v1/agent/tools/parse_logs",
        json={
            "session_id": session_id,
            "content": LOG_CONTENT,
            "context_lines": 60,
        },
    )

    # Stream investigation
    events = []
    async with client.stream(
        "POST",
        "/api/v1/agent/tools/investigate/stream",
        json={"session_id": session_id},
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            # Parse complete events from buffer
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                parsed = parse_sse_events(event_text + "\n\n")
                events.extend(parsed)

    # Verify ordering: phase_start must precede phase_complete for each phase
    phase_started = set()
    phase_completed = set()

    for evt in events:
        if evt["event"] == "phase_start":
            phase = evt["data"]["phase"]
            assert phase not in phase_started, f"Phase {phase} started twice"
            phase_started.add(phase)

        elif evt["event"] == "phase_complete":
            phase = evt["data"]["phase"]
            assert phase in phase_started, (
                f"Phase {phase} completed without starting"
            )
            assert phase not in phase_completed, (
                f"Phase {phase} completed twice"
            )
            phase_completed.add(phase)

    # All started phases must be completed
    assert phase_started == phase_completed, (
        f"Started but not completed: {phase_started - phase_completed}"
    )

    # Must end with "result" then "done"
    event_types = [e["event"] for e in events]
    assert "result" in event_types, "Missing result event"
    assert "done" in event_types, "Missing done event"
    assert event_types[-1] == "done", "Last event must be 'done'"
    assert event_types[-2] == "result", "Second-to-last event must be 'result'"
```

### Verify Event Schema

```python
@pytest.mark.asyncio
async def test_sse_event_schemas(integration_client):
    """Verify that each SSE event type conforms to its expected schema."""
    client = integration_client

    # Set up and stream
    resp = await client.post("/api/v1/agent/sessions")
    session_id = resp.json()["session_id"]
    await client.post(
        "/api/v1/agent/tools/parse_logs",
        json={
            "session_id": session_id,
            "content": LOG_CONTENT,
            "context_lines": 60,
        },
    )

    events = []
    async with client.stream(
        "POST",
        "/api/v1/agent/tools/investigate/stream",
        json={"session_id": session_id},
        headers={"Accept": "text/event-stream"},
    ) as response:
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                events.extend(parse_sse_events(event_text + "\n\n"))

    # Schema validators per event type
    schema_checks = {
        "phase_start": lambda d: (
            "phase" in d and isinstance(d["phase"], int) and
            "phase_name" in d and isinstance(d["phase_name"], str)
        ),
        "phase_progress": lambda d: (
            "phase" in d and isinstance(d["phase"], int)
        ),
        "phase_item": lambda d: (
            "phase" in d and isinstance(d["phase"], int) and
            "type" in d and isinstance(d["type"], str)
        ),
        "phase_complete": lambda d: (
            "phase" in d and isinstance(d["phase"], int)
        ),
        "phase_error": lambda d: (
            "phase" in d and "error" in d
        ),
        "llm_request": lambda d: (
            "phase" in d and "model" in d
        ),
        "llm_response": lambda d: (
            "phase" in d and "model" in d
        ),
        "result": lambda d: (
            "investigation_id" in d and "outcome" in d
        ),
        "done": lambda d: (
            "session_id" in d
        ),
    }

    for evt in events:
        event_type = evt["event"]
        if event_type in schema_checks:
            assert schema_checks[event_type](evt["data"]), (
                f"Event {event_type} failed schema check: {evt['data']}"
            )


@pytest.mark.asyncio
async def test_sse_error_event_on_failure(integration_client):
    """Verify that an error event is emitted when investigation fails."""
    client = integration_client

    # Create session but do NOT parse logs (investigation should fail)
    resp = await client.post("/api/v1/agent/sessions")
    session_id = resp.json()["session_id"]

    events = []
    async with client.stream(
        "POST",
        "/api/v1/agent/tools/investigate/stream",
        json={"session_id": session_id},
        headers={"Accept": "text/event-stream"},
    ) as response:
        # Might get 409 directly, or might get an error event in the stream
        if response.status_code == 409:
            return  # Acceptable: server rejected the request upfront

        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                events.extend(parse_sse_events(event_text + "\n\n"))

    # Should contain an error event
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) >= 1, "Expected at least one error event"
    assert "message" in error_events[0]["data"]
```

### Test Stream Termination

```python
@pytest.mark.asyncio
async def test_sse_stream_terminates_cleanly(integration_client):
    """Verify the SSE stream closes after the done event."""
    client = integration_client

    resp = await client.post("/api/v1/agent/sessions")
    session_id = resp.json()["session_id"]
    await client.post(
        "/api/v1/agent/tools/parse_logs",
        json={
            "session_id": session_id,
            "content": LOG_CONTENT,
            "context_lines": 60,
        },
    )

    event_count = 0
    saw_done = False

    async with client.stream(
        "POST",
        "/api/v1/agent/tools/investigate/stream",
        json={"session_id": session_id},
        headers={"Accept": "text/event-stream"},
    ) as response:
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                parsed = parse_sse_events(event_text + "\n\n")
                for evt in parsed:
                    event_count += 1
                    if evt["event"] == "done":
                        saw_done = True

    assert saw_done, "Stream must end with a 'done' event"
    assert event_count >= 3, "Expected at least phase_start, result, done"
```

---

## 5.4 Client Library Testing

### Unit Tests with httpx Mock Transport

The `AgentClient` is tested in isolation using httpx's mock transport, which lets you define exact request/response pairs without starting a server.

```python
# tests/unit/api/test_client.py

import json
import pytest
from unittest.mock import AsyncMock

import httpx

from srcs.api.client import AgentClient
from srcs.api.errors import AgentAPIError
from srcs.api.sse import SSEEvent


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport that returns predefined responses.

    Routes are registered as (method, path) -> response_factory.
    """

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], httpx.Response] = {}
        self.requests: list[httpx.Request] = []

    def add_route(
        self,
        method: str,
        path: str,
        status_code: int = 200,
        json_body: dict | None = None,
        content: bytes | None = None,
        headers: dict | None = None,
    ) -> None:
        response_headers = headers or {}
        if json_body is not None:
            body = json.dumps(json_body).encode()
            response_headers.setdefault("content-type", "application/json")
        else:
            body = content or b""
        self.routes[(method.upper(), path)] = httpx.Response(
            status_code=status_code,
            content=body,
            headers=response_headers,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key in self.routes:
            return self.routes[key]
        return httpx.Response(404, content=b'{"error": {"code": "not_found"}}')


@pytest.fixture
def mock_transport():
    return MockTransport()


@pytest.fixture
async def agent_client(mock_transport):
    """AgentClient backed by mock transport."""
    client = AgentClient("http://test")
    client._http = httpx.AsyncClient(
        transport=mock_transport,
        base_url="http://test",
    )
    yield client
    await client._http.aclose()


# ── Health ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(agent_client, mock_transport):
    mock_transport.add_route(
        "GET", "/health",
        json_body={"status": "healthy", "timestamp": "2024-01-15T10:00:00Z"},
    )
    result = await agent_client.health()
    assert result["status"] == "healthy"


# ── Session Management ────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session(agent_client, mock_transport):
    mock_transport.add_route(
        "POST", "/api/v1/agent/sessions",
        status_code=201,
        json_body={
            "session_id": "sess-123",
            "created_at": "2024-01-15T10:00:00Z",
            "status": "active",
            "tools": ["parse_logs", "search_logs", "investigate"],
        },
    )
    result = await agent_client.create_session()
    assert result["session_id"] == "sess-123"
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_delete_session(agent_client, mock_transport):
    mock_transport.add_route(
        "DELETE", "/api/v1/agent/sessions/sess-123",
        json_body={"deleted": True},
    )
    result = await agent_client.delete_session("sess-123")
    assert result["deleted"] is True


# ── Error Propagation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_error_propagation(agent_client, mock_transport):
    """AgentAPIError should be raised with structured error details."""
    mock_transport.add_route(
        "GET", "/api/v1/agent/sessions/nonexistent",
        status_code=404,
        json_body={
            "error": {
                "code": "SESSION_NOT_FOUND",
                "message": "Session nonexistent does not exist",
                "recovery_hint": "Create a new session with POST /api/v1/agent/sessions",
            },
        },
    )

    with pytest.raises(AgentAPIError) as exc_info:
        await agent_client.get_session("nonexistent")

    err = exc_info.value
    assert err.status_code == 404
    assert err.code == "SESSION_NOT_FOUND"
    assert "nonexistent" in err.message
    assert err.recovery_hint is not None


@pytest.mark.asyncio
async def test_server_error_propagation(agent_client, mock_transport):
    """500-level errors should also raise AgentAPIError."""
    mock_transport.add_route(
        "POST", "/api/v1/agent/tools/investigate",
        status_code=500,
        json_body={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "LLM service unavailable",
            },
        },
    )

    with pytest.raises(AgentAPIError) as exc_info:
        await agent_client.investigate("sess-123")

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "INTERNAL_ERROR"


# ── Tool Calls ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_logs_sends_correct_body(agent_client, mock_transport):
    """Verify parse_logs sends the right JSON body."""
    mock_transport.add_route(
        "POST", "/api/v1/agent/tools/parse_logs",
        json_body={
            "total_entries": 5,
            "trigger_error": {"message": "timeout"},
            "context_count": 3,
        },
    )

    result = await agent_client.parse_logs(
        "sess-123",
        content="some log content",
        error_line=42,
        context_lines=30,
    )

    assert result["total_entries"] == 5

    # Verify request body
    request = mock_transport.requests[-1]
    body = json.loads(request.content)
    assert body["session_id"] == "sess-123"
    assert body["content"] == "some log content"
    assert body["error_line"] == 42
    assert body["context_lines"] == 30


@pytest.mark.asyncio
async def test_record_finding(agent_client, mock_transport):
    mock_transport.add_route(
        "POST", "/api/v1/agent/tools/record_finding",
        json_body={"finding_id": "f-001", "total_findings": 1},
    )

    result = await agent_client.record_finding(
        "sess-123",
        finding="Fragment timeout precedes incomplete event",
        severity="critical",
        evidence=[{"line": 4, "excerpt": "Fragment timeout"}],
    )

    assert result["finding_id"] == "f-001"


@pytest.mark.asyncio
async def test_submit_feedback(agent_client, mock_transport):
    mock_transport.add_route(
        "POST", "/api/v1/investigations/inv-001/feedback",
        json_body={
            "message": "Feedback recorded",
            "patterns_updated": 1,
            "patterns_created": 0,
        },
    )

    result = await agent_client.submit_feedback(
        "inv-001",
        correct=True,
        feedback_source="test",
    )

    assert result["patterns_updated"] == 1
```

### SSE Consumption Tests

Testing SSE requires a mock that returns streaming content:

```python
# tests/unit/api/test_client_sse.py

import json
import pytest

import httpx

from srcs.api.client import AgentClient
from srcs.api.sse import SSEEvent


class SSEMockTransport(httpx.AsyncBaseTransport):
    """Mock transport that returns SSE event streams."""

    def __init__(self, events: list[dict]) -> None:
        self.events = events

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        lines = []
        for evt in self.events:
            lines.append(f"event: {evt['event']}")
            lines.append(f"data: {json.dumps(evt['data'])}")
            lines.append("")  # Empty line terminates event

        body = "\n".join(lines).encode()
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream"},
        )


@pytest.mark.asyncio
async def test_investigate_stream_yields_events():
    """Client should yield SSEEvent objects from the SSE stream."""
    transport = SSEMockTransport([
        {"event": "phase_start", "data": {"phase": 0, "phase_name": "Prior Knowledge"}},
        {"event": "phase_complete", "data": {"phase": 0, "summary": "Found 3 patterns"}},
        {"event": "phase_start", "data": {"phase": 1, "phase_name": "Hypothesis Generation"}},
        {"event": "phase_complete", "data": {"phase": 1, "summary": "Generated 4 hypotheses"}},
        {"event": "result", "data": {"investigation_id": "inv-001", "outcome": "CONFIDENT"}},
        {"event": "done", "data": {"session_id": "sess-123"}},
    ])

    client = AgentClient("http://test")
    client._http = httpx.AsyncClient(transport=transport, base_url="http://test")

    events = []
    async for event in client.investigate_stream("sess-123"):
        events.append(event)

    await client._http.aclose()

    assert len(events) == 6
    assert events[0].event == "phase_start"
    assert events[0].data["phase"] == 0
    assert events[-2].event == "result"
    assert events[-2].data["outcome"] == "CONFIDENT"
    assert events[-1].event == "done"


@pytest.mark.asyncio
async def test_investigate_stream_stops_at_done():
    """Client should stop consuming after the 'done' event."""
    transport = SSEMockTransport([
        {"event": "phase_start", "data": {"phase": 0, "phase_name": "Prior Knowledge"}},
        {"event": "done", "data": {"session_id": "sess-123"}},
        # This event should never be yielded
        {"event": "phase_start", "data": {"phase": 1, "phase_name": "Should Not Appear"}},
    ])

    client = AgentClient("http://test")
    client._http = httpx.AsyncClient(transport=transport, base_url="http://test")

    events = []
    async for event in client.investigate_stream("sess-123"):
        events.append(event)

    await client._http.aclose()

    assert len(events) == 2
    assert events[-1].event == "done"


@pytest.mark.asyncio
async def test_ask_experts_stream():
    """ask_experts_stream should yield expert events."""
    transport = SSEMockTransport([
        {"event": "expert_start", "data": {"expert": "DAQ Specialist"}},
        {"event": "expert_chunk", "data": {"text": "Fragment timeouts typically..."}},
        {"event": "expert_done", "data": {"expert": "DAQ Specialist"}},
        {"event": "result", "data": {"answer": "Full compiled answer here", "question_id": "q-001"}},
        {"event": "done", "data": {}},
    ])

    client = AgentClient("http://test")
    client._http = httpx.AsyncClient(transport=transport, base_url="http://test")

    events = []
    async for event in client.ask_experts_stream("What causes fragment timeouts?"):
        events.append(event)

    await client._http.aclose()

    assert events[0].event == "expert_start"
    assert events[0].data["expert"] == "DAQ Specialist"
    result_events = [e for e in events if e.event == "result"]
    assert len(result_events) == 1
    assert "answer" in result_events[0].data
```

### Integration Test with Real Server (TestClient)

```python
# tests/integration/test_client_integration.py

import pytest
from httpx import ASGITransport, AsyncClient

from srcs.api.app import create_app
from srcs.api.client import AgentClient


LOG_CONTENT = """2024-01-15 10:30:45.000 ERROR [BoardReader_01] readData: Fragment timeout after 5000ms"""


@pytest.fixture
async def live_agent_client(temp_data_dir, mock_llm_provider, mock_chroma):
    """AgentClient wired to a real in-process FastAPI server."""
    import os
    os.environ["ARTDAQ_DATA_DIR"] = str(temp_data_dir)

    app = create_app()
    from srcs.api.dependencies import get_llm_provider, get_chroma_client
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_chroma_client] = lambda: mock_chroma

    transport = ASGITransport(app=app)
    client = AgentClient("http://test")
    client._http = AsyncClient(transport=transport, base_url="http://test")
    yield client
    await client._http.aclose()


@pytest.mark.asyncio
async def test_client_full_workflow(live_agent_client):
    """End-to-end test: AgentClient -> FastAPI -> Coordinator -> Response."""
    client = live_agent_client

    # Health check
    health = await client.health()
    assert health["status"] == "healthy"

    # Create session
    session = await client.create_session()
    session_id = session["session_id"]

    # Parse logs
    parsed = await client.parse_logs(
        session_id, content=LOG_CONTENT, context_lines=60
    )
    assert parsed["total_entries"] >= 1
    assert "Fragment timeout" in parsed["trigger_error"]["message"]

    # Run investigation (sync)
    result = await client.investigate(session_id)
    assert result["investigation_id"] is not None
    assert result["outcome"] in [
        "CONFIDENT", "PROBABLE", "UNCERTAIN", "INSUFFICIENT", "CONTRADICTORY"
    ]

    # Submit feedback
    feedback = await client.submit_feedback(
        result["investigation_id"],
        correct=True,
        feedback_source="integration_test",
    )
    assert "patterns_updated" in feedback

    # Clean up
    await client.delete_session(session_id)


@pytest.mark.asyncio
async def test_client_streaming_workflow(live_agent_client):
    """End-to-end test: AgentClient SSE streaming."""
    client = live_agent_client

    session = await client.create_session()
    session_id = session["session_id"]

    await client.parse_logs(session_id, content=LOG_CONTENT, context_lines=60)

    events = []
    async for event in client.investigate_stream(session_id):
        events.append(event)

    # Verify we got meaningful events
    event_types = [e.event for e in events]
    assert "phase_start" in event_types
    assert "result" in event_types
    assert "done" in event_types

    # Verify result event has investigation data
    result_event = next(e for e in events if e.event == "result")
    assert result_event.data["investigation_id"] is not None

    await client.delete_session(session_id)
```

---

> [← Client Refactoring](agentic-rest-service-design-ch6-client-refactoring.md) | [Table of Contents](agentic-rest-service-design.md)
