> **Agentic REST API Design Document** | [← Architecture](agentic-rest-service-design-ch1-architecture.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Code Analysis Tools →](agentic-rest-service-design-ch3-code-analysis-tools.md)

---

# Chapter 2: Log Analysis Tools

## Part III: Agentic Tool Chapters

### Category: Log Analysis

Tools in this category parse, search, summarize, and correlate log data within an
investigation session. The `parse_logs` tool is the entry point: it ingests raw log
content and stores structured entries in session state. All subsequent log tools
operate on that session state and will reject requests if logs have not been parsed.

Navigation handles flow between tools as follows:

```
parse_logs  ──►  session state ──────────────┐
                   │                          │
                   ▼                          ▼
            search_logs  ──►  line numbers ──► get_log_context
                   │                          │
                   ▼                          ▼
            get_log_summary            correlate_events
```

---

#### Tool 1: parse_logs

##### 1. Purpose

Parses raw log content into structured, typed log entries and stores them in session
state for use by all other log analysis tools. This is always the first tool the agent
calls when beginning a log investigation.

The tool accepts one or more blocks of raw log text (e.g., contents of artdaq log files),
parses each line using multi-format detection (artdaq Message Facility, artdaq timestamped,
simple timestamped, fallback keyword matching), and returns the trigger error with
surrounding context plus a summary. The full parsed log list is stored server-side
in session state, so subsequent tools can operate on it without retransmitting the data.

Use this tool when: the agent receives a log file to investigate and needs to convert
raw text into structured data before searching, summarizing, or correlating.

Returns: the identified trigger error entry, context log entries surrounding it, a total
parsed count, and a summary object with entry count, error/warning counts, component
list, and time range.

##### 2. Endpoint

```
POST /api/v1/agent/tools/parse_logs
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier. Required for all tool calls."
    },
    "params": {
      "type": "object",
      "description": "Tool-specific parameters. Keys may also appear at the top level as a fallback.",
      "properties": {
        "content": {
          "type": "string",
          "minLength": 1,
          "description": "Raw log text content to parse. Supports artdaq Message Facility (%MSG-x), artdaq timestamped (YYYY-MM-DD HH:MM:SS.mmm LEVEL [Component] Function: Message), simple timestamped ([YYYY-MM-DD HH:MM:SS] LEVEL: Message), and fallback keyword matching."
        },
        "error_line": {
          "type": "integer",
          "minimum": 1,
          "description": "Optional specific line number of the suspected trigger error. If provided, extract_error_and_context will use this line as the anchor. If omitted, the first ERROR-level entry is used."
        },
        "context_lines": {
          "type": "integer",
          "minimum": 0,
          "default": 60,
          "description": "Number of log entries before the trigger error to include as temporal context. Default 60."
        }
      },
      "required": ["content"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "trigger_error": {
    "line": 4,
    "timestamp": "2026-02-14T10:32:15.003",
    "level": "ERROR",
    "component": "BoardReader01",
    "function": "getNext_",
    "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
    "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
  },
  "context_logs": [
    {
      "line": 2,
      "timestamp": "2026-02-14T10:30:01.150",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "configure",
      "message": "Configured with 2 links",
      "raw_line": "2026-02-14 10:30:01.150 INFO [BoardReader01] configure: Configured with 2 links"
    },
    {
      "line": 3,
      "timestamp": "2026-02-14T10:30:02.005",
      "level": "INFO",
      "component": "EventBuilder01",
      "function": "initialize",
      "message": "Initializing EventBuilder",
      "raw_line": "2026-02-14 10:30:02.005 INFO [EventBuilder01] initialize: Initializing EventBuilder"
    }
  ],
  "total_parsed": 9,
  "summary": {
    "total_entries": 9,
    "error_count": 4,
    "warning_count": 1,
    "components": ["BoardReader01", "EventBuilder01"],
    "time_range_start": "2026-02-14T10:30:01.003",
    "time_range_end": "2026-02-14T10:45:32.118"
  }
}
```

**Navigation handles:**
- `trigger_error.line` -- pass to `get_log_context` as the `line` parameter
- `context_logs[].line` -- pass to `get_log_context` to examine surrounding entries
- `summary.components[]` -- pass to `search_logs` as the `component` filter

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|-------------|------------|-----------|
| 400 | `VALIDATION_ERROR` | `content` field is missing, empty, or no parseable log entries found |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match an active session |

All validation failures (missing content, empty content, no parseable entries) raise the
same `VALIDATION_ERROR` code via `validation_error()` from `srcs/api/errors.py`.

**Example error response:**

```json
{
  "error": true,
  "error_code": "VALIDATION_ERROR",
  "message": "No parseable log entries found in content."
}
```

##### 6. Implementation

**Module:** `srcs/api/tools/log_tools.py`

**Registration:** `@register_tool("parse_logs")` decorator from `srcs/api/tools/router.py`

**Code path:**

```
POST /api/v1/agent/tools/parse_logs
  → srcs/api/tools/log_tools.py::parse_logs(ctx: ToolContext)
    → Extract params from ctx.request_body.get("params", {}), with fallback to top-level keys
    → log_parser.parse_log_content(content)
        → Iterates lines, tries _parse_msg_facility() then _parse_line()
        → _parse_line() tries _ARTDAQ_PATTERN, _SIMPLE_PATTERN, _FALLBACK_LEVEL_PATTERN
        → Returns list[Log]
    → log_parser.extract_error_and_context(logs, error_line, context_lines)
        → Finds trigger error (specified line or first ERROR)
        → Returns (trigger_error: Log, context_logs: list[Log])
    → Store in session: ctx.session.state.parsed_logs = [_log_to_dict(log) for log in logs]
    → Build ParsedLogSummary and store in ctx.session.state.log_summary
    → Return response with trigger_error, context_logs, total_parsed, summary
```

**Key backend functions:**

| Function | Signature | Returns |
|----------|-----------|---------|
| `parse_log_content` | `(content: str) -> list[Log]` | All parsed log entries |
| `extract_error_and_context` | `(logs: list[Log], error_line: int \| None, context_lines: int) -> tuple[Log, list[Log]]` | Trigger error + context |
| `_parse_msg_facility` | `(line: str, line_num: int, lines: list[str], idx: int) -> tuple[Log, int] \| None` | Single entry from %MSG block |
| `_parse_line` | `(line: str, line_num: int) -> Log \| None` | Single entry or None |

##### 7. Dependencies

| Dependency | Required For | Initialization |
|------------|-------------|----------------|
| `SessionStore` | Validating `session_id`, storing parsed logs | Created at API startup; in-memory dict with TTL expiration |
| `srcs.models.log_parser` | `parse_log_content()`, `extract_error_and_context()` | Pure import, no initialization needed |
| `srcs.models.logs.Log` | Pydantic model for log entries | Pure import |

No external services (no database, no LLM, no network) are required. This tool is
entirely CPU-bound and operates on the provided content string.

##### 8. Testing

| # | Test Case | Mock Strategy | Key Assertions |
|---|-----------|---------------|----------------|
| 1 | Parse artdaq-format content | No mocks needed; provide raw artdaq log text as `content` | Response contains `trigger_error`; `total_parsed` matches expected; `summary.error_count` > 0; `summary.components` includes `"BoardReader01"` |
| 2 | Parse with explicit `error_line` | Provide content with known error at line 150; set `error_line=150` | `trigger_error.line == 150`; `context_logs` contains surrounding entries |
| 3 | Empty content returns 400 | Send `content: ""` | HTTP 400; `error_code == "VALIDATION_ERROR"` |
| 4 | Unparseable content returns 400 | Send `content: "just some random text\nwith no log format"` | HTTP 400; `error_code == "VALIDATION_ERROR"` |
| 5 | Parsed logs stored in session | Parse valid content, then call `search_logs` in same session | `search_logs` succeeds (proving session storage worked); session `parsed_logs` is populated |

```python
@pytest.mark.asyncio
async def test_parse_logs_artdaq_format(client, active_session):
    """Parse artdaq-format log content and verify structured output."""
    content = (
        "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: "
        "Fragment timeout after 5000ms waiting for data on link 0x0100\n"
        "2026-02-14 10:32:15.004 INFO [BoardReader01] getNext_: "
        "Retrying link 0x0100\n"
    )
    response = await client.post(
        "/api/v1/agent/tools/parse_logs",
        json={"session_id": active_session.id, "params": {"content": content}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_parsed"] == 2
    assert data["summary"]["error_count"] == 1
    assert "BoardReader01" in data["summary"]["components"]
    assert data["trigger_error"]["function"] == "getNext_"
```

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/parse_logs \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "content": "2026-02-14 10:30:01.003 INFO [BoardReader01] initialize: Initializing BoardReader\n2026-02-14 10:30:01.150 INFO [BoardReader01] configure: Configured with 2 links\n2026-02-14 10:30:02.005 INFO [EventBuilder01] initialize: Initializing EventBuilder\n2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100\n2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200\n2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2\n2026-02-14 10:32:16.010 WARNING [EventBuilder01] process_fragments: Dropping incomplete event for sequence 10042\n2026-02-14 10:32:17.450 ERROR [BoardReader01] getNext_: SHM write failed: buffer full\n2026-02-14 10:45:32.118 INFO [BoardReader01] stop: BoardReader shutting down",
      "error_line": null,
      "context_lines": 60
    }
  }'
```

**Response:**

```json
{
  "trigger_error": {
    "line": 4,
    "timestamp": "2026-02-14T10:32:15.003",
    "level": "ERROR",
    "component": "BoardReader01",
    "function": "getNext_",
    "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
    "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
  },
  "context_logs": [
    {
      "line": 1,
      "timestamp": "2026-02-14T10:30:01.003",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "initialize",
      "message": "Initializing BoardReader",
      "raw_line": "2026-02-14 10:30:01.003 INFO [BoardReader01] initialize: Initializing BoardReader"
    },
    {
      "line": 2,
      "timestamp": "2026-02-14T10:30:01.150",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "configure",
      "message": "Configured with 2 links",
      "raw_line": "2026-02-14 10:30:01.150 INFO [BoardReader01] configure: Configured with 2 links"
    },
    {
      "line": 3,
      "timestamp": "2026-02-14T10:30:02.005",
      "level": "INFO",
      "component": "EventBuilder01",
      "function": "initialize",
      "message": "Initializing EventBuilder",
      "raw_line": "2026-02-14 10:30:02.005 INFO [EventBuilder01] initialize: Initializing EventBuilder"
    }
  ],
  "total_parsed": 9,
  "summary": {
    "total_entries": 9,
    "error_count": 4,
    "warning_count": 1,
    "components": ["BoardReader01", "EventBuilder01"],
    "time_range_start": "2026-02-14T10:30:01.003",
    "time_range_end": "2026-02-14T10:45:32.118"
  }
}
```

---

#### Tool 2: search_logs

##### 1. Purpose

Searches within previously parsed log entries stored in session state. Supports
filtering by regex pattern on message text, severity level, component name, and
time range. Returns matching entries with line numbers that serve as navigation
handles for `get_log_context`.

Use this tool when: the agent needs to find specific log entries after parsing -- for
example, searching for all fragment timeout errors, finding warnings from a particular
component, or locating entries within a time window around a known event.

Returns: a list of matching log entries with full metadata (line number, timestamp,
severity, component, function, message), the total match count, and the total number
of entries searched. Results are capped at a configurable limit (default 100).

Requires: `parse_logs` must have been called first to populate the session with log data.

##### 2. Endpoint

```
POST /api/v1/agent/tools/search_logs
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "params": {
      "type": "object",
      "description": "Tool-specific parameters.",
      "properties": {
        "pattern": {
          "type": "string",
          "description": "Regex pattern to match against log entry messages and raw lines. Case-insensitive. Example: 'timeout|timed out' to find all timeout-related entries."
        },
        "severity": {
          "type": "string",
          "enum": ["ERROR", "WARNING", "INFO", "DEBUG"],
          "description": "Filter to entries of this exact severity level."
        },
        "component": {
          "type": "string",
          "description": "Filter to entries from this component. Case-insensitive match. Example: 'BoardReader01'."
        },
        "time_start": {
          "type": "string",
          "format": "date-time",
          "description": "Include only entries at or after this timestamp. ISO 8601 format."
        },
        "time_end": {
          "type": "string",
          "format": "date-time",
          "description": "Include only entries at or before this timestamp. ISO 8601 format."
        },
        "limit": {
          "type": "integer",
          "minimum": 1,
          "default": 100,
          "description": "Maximum number of matching entries to return. Default 100."
        }
      }
    }
  },
  "required": ["session_id"]
}
```

##### 4. Response Schema

```json
{
  "matches": [
    {
      "line": 4,
      "timestamp": "2026-02-14T10:32:15.003",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
      "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
    },
    {
      "line": 5,
      "timestamp": "2026-02-14T10:32:15.510",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "Fragment timeout after 5000ms waiting for data on link 0x0200",
      "raw_line": "2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200"
    }
  ],
  "total_matches": 2,
  "searched": 9
}
```

**Navigation handles:**
- `matches[].line` -- pass to `get_log_context` as the `line` parameter
- `matches[].component` -- use to filter further or pass to `correlate_events`
- `matches[].timestamp` -- use to define time windows for `correlate_events`

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|-------------|------------|-----------|
| 400 | `VALIDATION_ERROR` | No parsed logs in session (call `parse_logs` first) |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match an active session |

All validation failures raise the `VALIDATION_ERROR` code via `validation_error()`
from `srcs/api/errors.py`.

**Example error response:**

```json
{
  "error": true,
  "error_code": "VALIDATION_ERROR",
  "message": "No parsed logs in session. Call parse_logs first."
}
```

##### 6. Implementation

**Module:** `srcs/api/tools/log_tools.py`

**Registration:** `@register_tool("search_logs")` decorator from `srcs/api/tools/router.py`

**Code path:**

```
POST /api/v1/agent/tools/search_logs
  → srcs/api/tools/log_tools.py::search_logs(ctx: ToolContext)
    → Extract params from ctx.request_body.get("params", {})
    → Retrieve parsed = ctx.session.state.parsed_logs
        → If empty, raise validation_error("No parsed logs in session.")
    → Apply filters sequentially:
        1. severity: entry.level == severity (case-insensitive)
        2. component: entry.component == component (case-insensitive)
        3. pattern: re.search(pattern, message, re.IGNORECASE) or re.search(pattern, raw_line, re.IGNORECASE)
        4. time_start: entry.timestamp >= time_start
        5. time_end: entry.timestamp <= time_end
    → Stop collecting when len(results) >= limit
    → Return response with matches, total_matches, searched
```

**Key implementation detail:** All filtering is done in Python on the in-memory
`list[dict]` stored in `session.state.parsed_logs`. No database queries are involved.
The regex pattern filter uses `re.search()` with `re.IGNORECASE` on both the `message`
and `raw_line` fields. There is no pagination (no offset parameter); results are capped
at `limit` (default 100).

##### 7. Dependencies

| Dependency | Required For | Initialization |
|------------|-------------|----------------|
| `SessionStore` | Validating `session_id`, retrieving session state | Created at API startup |
| `re` (stdlib) | Regex pattern matching on `pattern` parameter | Standard library import |
| Session log data | The `list[dict]` stored in `session.state.parsed_logs` | Populated by prior `parse_logs` call |

No external services required. This tool is entirely in-memory.

##### 8. Testing

| # | Test Case | Mock Strategy | Key Assertions |
|---|-----------|---------------|----------------|
| 1 | Search by severity filter | Pre-populate session with parsed logs containing mixed severities | Only entries matching the requested severity are returned; `total_matches` is correct |
| 2 | Search by regex pattern | Pre-populate session; search with `pattern: "timeout\|SHM"` | Both "timeout" and "SHM" entries returned; entries not matching are excluded |
| 3 | Limit results | Pre-populate session with many entries; search with `limit=5` | Returns at most 5 matches; `total_matches <= 5` |
| 4 | No parsed logs returns error | Send request before calling `parse_logs` | HTTP 400; `error_code == "VALIDATION_ERROR"` |

```python
@pytest.mark.asyncio
async def test_search_logs_by_pattern(client, session_with_parsed_logs):
    """Search parsed logs by regex pattern."""
    session_id = session_with_parsed_logs
    response = await client.post(
        "/api/v1/agent/tools/search_logs",
        json={
            "session_id": session_id,
            "params": {
                "pattern": "timeout",
                "severity": "ERROR",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] > 0
    for entry in data["matches"]:
        assert "timeout" in entry["message"].lower()
        assert entry["level"] == "ERROR"
        assert "line" in entry  # Navigation handle present
```

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/search_logs \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "pattern": "Fragment timeout",
      "severity": "ERROR",
      "component": "BoardReader01",
      "limit": 100
    }
  }'
```

**Response:**

```json
{
  "matches": [
    {
      "line": 4,
      "timestamp": "2026-02-14T10:32:15.003",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
      "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
    },
    {
      "line": 5,
      "timestamp": "2026-02-14T10:32:15.510",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "Fragment timeout after 5000ms waiting for data on link 0x0200",
      "raw_line": "2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200"
    }
  ],
  "total_matches": 2,
  "searched": 9
}
```

---

#### Tool 3: get_log_context

##### 1. Purpose

Retrieves a window of log entries surrounding a specific line number in parsed logs.
Returns the target entry plus N entries before and N entries after, providing the
temporal context needed to understand what led to an event and what happened
immediately after.

Use this tool when: the agent has identified a specific error or event (via
`search_logs` or `parse_logs`) and needs to see surrounding log activity to
understand the sequence of events leading to and following that entry.

Returns: the target log entry, the entries before it, and the entries after it --
each with full metadata. If the target line is near the beginning or end of the log,
the before/after arrays are shorter accordingly.

Requires: `parse_logs` must have been called first.

##### 2. Endpoint

```
POST /api/v1/agent/tools/get_log_context
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "params": {
      "type": "object",
      "description": "Tool-specific parameters.",
      "properties": {
        "line": {
          "type": "integer",
          "minimum": 1,
          "description": "Line number of the target entry. Obtained from search_logs matches, parse_logs trigger_error, or correlate_events output."
        },
        "before": {
          "type": "integer",
          "minimum": 0,
          "default": 10,
          "description": "Number of log entries to include before the target. Default 10."
        },
        "after": {
          "type": "integer",
          "minimum": 0,
          "default": 10,
          "description": "Number of log entries to include after the target. Default 10."
        }
      },
      "required": ["line"]
    }
  },
  "required": ["session_id", "params"]
}
```

##### 4. Response Schema

```json
{
  "target": {
    "line": 4,
    "timestamp": "2026-02-14T10:32:15.003",
    "level": "ERROR",
    "component": "BoardReader01",
    "function": "getNext_",
    "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
    "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
  },
  "before": [
    {
      "line": 2,
      "timestamp": "2026-02-14T10:30:01.150",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "configure",
      "message": "Configured with 2 links",
      "raw_line": "2026-02-14 10:30:01.150 INFO [BoardReader01] configure: Configured with 2 links"
    },
    {
      "line": 3,
      "timestamp": "2026-02-14T10:30:02.005",
      "level": "INFO",
      "component": "EventBuilder01",
      "function": "initialize",
      "message": "Initializing EventBuilder",
      "raw_line": "2026-02-14 10:30:02.005 INFO [EventBuilder01] initialize: Initializing EventBuilder"
    }
  ],
  "after": [
    {
      "line": 5,
      "timestamp": "2026-02-14T10:32:15.510",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "Fragment timeout after 5000ms waiting for data on link 0x0200",
      "raw_line": "2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200"
    },
    {
      "line": 6,
      "timestamp": "2026-02-14T10:32:16.008",
      "level": "ERROR",
      "component": "EventBuilder01",
      "function": "process_fragments",
      "message": "Incomplete event: expected 4 fragments, received 2",
      "raw_line": "2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2"
    }
  ]
}
```

**Navigation handles:**
- `before[].line` and `after[].line` -- can be passed back to `get_log_context` to shift the window
- `before[].component` and `after[].component` -- use for `correlate_events` or `search_logs` filtering
- `target.timestamp` -- use as anchor for time-based queries in `correlate_events`

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|-------------|------------|-----------|
| 400 | `VALIDATION_ERROR` | No parsed logs in session, or `line` parameter missing |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match an active session |

**Fallback behavior:** If no parsed log entry has the specified `line` number, the
tool falls back to treating the line value as an index into the parsed entries list
(clamped to valid range). It does NOT raise an error for missing line numbers.

**Example error response:**

```json
{
  "error": true,
  "error_code": "VALIDATION_ERROR",
  "message": "'line' parameter is required for get_log_context."
}
```

##### 6. Implementation

**Module:** `srcs/api/tools/log_tools.py`

**Registration:** `@register_tool("get_log_context")` decorator from `srcs/api/tools/router.py`

**Code path:**

```
POST /api/v1/agent/tools/get_log_context
  → srcs/api/tools/log_tools.py::get_log_context(ctx: ToolContext)
    → Extract params from ctx.request_body.get("params", {})
    → Retrieve parsed = ctx.session.state.parsed_logs
        → If empty, raise validation_error("No parsed logs in session.")
    → Find target_idx: index where parsed[i]["line"] == target_line
    → If not found, fallback: treat target_line as an index into parsed entries
        → target_idx = min(target_line - 1, len(parsed) - 1), clamped to >= 0
    → Compute window:
        start = max(0, target_idx - before)
        end = min(len(parsed), target_idx + after + 1)
    → Return:
        target = parsed[target_idx]
        before = parsed[start:target_idx]
        after = parsed[target_idx + 1:end]
```

**Key implementation detail:** The `line` field on log entries corresponds to the
original line number in the raw log file, which may not be contiguous (blank lines
and unparseable lines are skipped). The lookup iterates through the stored `list[dict]`
to find the entry where `entry["line"] == target_line`. If no exact match is found,
the tool falls back to treating the line value as a 1-based index into the parsed
entries list (clamped to valid bounds), rather than raising an error.

##### 7. Dependencies

| Dependency | Required For | Initialization |
|------------|-------------|----------------|
| `SessionStore` | Validating `session_id`, retrieving session state | Created at API startup |
| Session log data | The `list[dict]` stored in `session.state.parsed_logs` | Populated by prior `parse_logs` call |

No external services required.

##### 8. Testing

| # | Test Case | Mock Strategy | Key Assertions |
|---|-----------|---------------|----------------|
| 1 | Context around middle entry | Pre-populate session with 100 log entries; request line in the middle with `before=5, after=5` | `target.line` matches requested line; `len(before) <= 5`; `len(after) <= 5`; entries are in chronological order |
| 2 | Context near start of log | Request context for the first parsed entry with `before=20` | `before` array has fewer than 20 entries |
| 3 | Context near end of log | Request context for the last parsed entry with `after=20` | `after` array has 0 entries |
| 4 | Non-existent line falls back to index | Request `line=99999` on a short log | Target falls back to last entry in parsed logs (index clamped to valid range) |
| 5 | Correct temporal ordering | Request context around a known entry | `before` entries all have timestamps <= `target.timestamp`; `after` entries all have timestamps >= `target.timestamp` |

```python
@pytest.mark.asyncio
async def test_get_log_context_middle(client, session_with_parsed_logs):
    """Get context around a middle entry."""
    session_id = session_with_parsed_logs
    response = await client.post(
        "/api/v1/agent/tools/get_log_context",
        json={
            "session_id": session_id,
            "params": {
                "line": 4,
                "before": 3,
                "after": 3,
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target"]["line"] == 4
    assert data["target"]["level"] == "ERROR"
    assert len(data["before"]) <= 3
    assert len(data["after"]) <= 3
    # Entries should be in chronological order
    all_entries = data["before"] + [data["target"]] + data["after"]
    timestamps = [e["timestamp"] for e in all_entries]
    assert timestamps == sorted(timestamps)
```

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/get_log_context \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "line": 4,
      "before": 3,
      "after": 5
    }
  }'
```

**Response:**

```json
{
  "target": {
    "line": 4,
    "timestamp": "2026-02-14T10:32:15.003",
    "level": "ERROR",
    "component": "BoardReader01",
    "function": "getNext_",
    "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
    "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
  },
  "before": [
    {
      "line": 1,
      "timestamp": "2026-02-14T10:30:01.003",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "initialize",
      "message": "Initializing BoardReader",
      "raw_line": "2026-02-14 10:30:01.003 INFO [BoardReader01] initialize: Initializing BoardReader"
    },
    {
      "line": 2,
      "timestamp": "2026-02-14T10:30:01.150",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "configure",
      "message": "Configured with 2 links",
      "raw_line": "2026-02-14 10:30:01.150 INFO [BoardReader01] configure: Configured with 2 links"
    },
    {
      "line": 3,
      "timestamp": "2026-02-14T10:30:02.005",
      "level": "INFO",
      "component": "EventBuilder01",
      "function": "initialize",
      "message": "Initializing EventBuilder",
      "raw_line": "2026-02-14 10:30:02.005 INFO [EventBuilder01] initialize: Initializing EventBuilder"
    }
  ],
  "after": [
    {
      "line": 5,
      "timestamp": "2026-02-14T10:32:15.510",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "Fragment timeout after 5000ms waiting for data on link 0x0200",
      "raw_line": "2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200"
    },
    {
      "line": 6,
      "timestamp": "2026-02-14T10:32:16.008",
      "level": "ERROR",
      "component": "EventBuilder01",
      "function": "process_fragments",
      "message": "Incomplete event: expected 4 fragments, received 2",
      "raw_line": "2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2"
    },
    {
      "line": 7,
      "timestamp": "2026-02-14T10:32:16.010",
      "level": "WARNING",
      "component": "EventBuilder01",
      "function": "process_fragments",
      "message": "Dropping incomplete event for sequence 10042",
      "raw_line": "2026-02-14 10:32:16.010 WARNING [EventBuilder01] process_fragments: Dropping incomplete event for sequence 10042"
    },
    {
      "line": 8,
      "timestamp": "2026-02-14T10:32:17.450",
      "level": "ERROR",
      "component": "BoardReader01",
      "function": "getNext_",
      "message": "SHM write failed: buffer full",
      "raw_line": "2026-02-14 10:32:17.450 ERROR [BoardReader01] getNext_: SHM write failed: buffer full"
    },
    {
      "line": 9,
      "timestamp": "2026-02-14T10:45:32.118",
      "level": "INFO",
      "component": "BoardReader01",
      "function": "stop",
      "message": "BoardReader shutting down",
      "raw_line": "2026-02-14 10:45:32.118 INFO [BoardReader01] stop: BoardReader shutting down"
    }
  ]
}
```

---

#### Tool 4: get_log_summary

##### 1. Purpose

Generates aggregated statistics from parsed logs. Provides a high-level overview
of what happened in a log file: total entries, counts broken down by severity
level and by component, plus the stored summary from `parse_logs` (which includes
error/warning counts, component list, and time range).

Use this tool when: the agent needs a big-picture understanding of a log before
drilling into specifics -- for example, to decide which component to investigate
first, or to understand the distribution of errors across components.

Returns: total entry count, a `level_counts` dict mapping severity levels to counts,
a `component_counts` dict mapping component names to counts, and a `summary` object
with error/warning counts, component list, and time range.

Requires: `parse_logs` must have been called first.

##### 2. Endpoint

```
POST /api/v1/agent/tools/get_log_summary
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    }
  },
  "required": ["session_id"]
}
```

This tool takes no additional parameters beyond `session_id`. It operates on
whatever logs were previously parsed in the session via `parse_logs`.

##### 4. Response Schema

```json
{
  "total_entries": 9,
  "level_counts": {
    "ERROR": 4,
    "WARNING": 1,
    "INFO": 4
  },
  "component_counts": {
    "BoardReader01": 6,
    "EventBuilder01": 3
  },
  "summary": {
    "total_entries": 9,
    "error_count": 4,
    "warning_count": 1,
    "components": ["BoardReader01", "EventBuilder01"],
    "time_range_start": "2026-02-14T10:30:01.003",
    "time_range_end": "2026-02-14T10:45:32.118"
  }
}
```

**Navigation handles:**
- `component_counts` keys -- pass to `search_logs` as the `component` filter
- `summary.components[]` -- pass to `search_logs` or `correlate_events`
- `summary.time_range_start` / `time_range_end` -- use as `time_start` / `time_end` in `search_logs`

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|-------------|------------|-----------|
| 400 | `VALIDATION_ERROR` | No parsed logs in session (call `parse_logs` first) |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match an active session |

**Example error response:**

```json
{
  "error": true,
  "error_code": "VALIDATION_ERROR",
  "message": "No parsed logs in session. Call parse_logs first."
}
```

##### 6. Implementation

**Module:** `srcs/api/tools/log_tools.py`

**Registration:** `@register_tool("get_log_summary")` decorator from `srcs/api/tools/router.py`

**Code path:**

```
POST /api/v1/agent/tools/get_log_summary
  → srcs/api/tools/log_tools.py::get_log_summary(ctx: ToolContext)
    → Retrieve parsed = ctx.session.state.parsed_logs
        → If empty, raise validation_error("No parsed logs in session.")
    → Aggregate level_counts:
        For each entry, count by entry["level"]
    → Aggregate component_counts:
        For each entry, count by entry["component"]
    → Return:
        total_entries = len(parsed)
        level_counts = {level: count, ...}
        component_counts = {component: count, ...}
        summary = ctx.session.state.log_summary.model_dump() or null
```

##### 7. Dependencies

| Dependency | Required For | Initialization |
|------------|-------------|----------------|
| `SessionStore` | Validating `session_id`, retrieving stored logs | Created at API startup |
| Session log data | The `list[dict]` stored by `parse_logs` in `session.state.parsed_logs` | Populated by prior `parse_logs` call |

No external services required.

##### 8. Testing

| # | Test Case | Mock Strategy | Key Assertions |
|---|-----------|---------------|----------------|
| 1 | Full summary of mixed-severity log | Pre-populate session with known entries across components and severities | `level_counts` match expected; `component_counts` keys match known components; `total_entries` is correct |
| 2 | Summary includes stored summary | Pre-populate session via `parse_logs` | `summary` object is present with `error_count`, `warning_count`, `components`, `time_range_start`, `time_range_end` |
| 3 | Component counts are flat | Pre-populate with entries from two components | `component_counts` maps component name to integer count (not nested object) |
| 4 | Level counts cover all levels | Pre-populate with mixed entries | `level_counts` has keys for each severity present; values sum to `total_entries` |
| 5 | No parsed logs returns error | Call without prior `parse_logs` | HTTP 400; `error_code == "VALIDATION_ERROR"` |

```python
@pytest.mark.asyncio
async def test_get_log_summary_counts(client, session_with_parsed_logs):
    """Verify level and component counts in summary."""
    session_id = session_with_parsed_logs
    response = await client.post(
        "/api/v1/agent/tools/get_log_summary",
        json={
            "session_id": session_id,
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Level counts should be flat integer mapping
    assert isinstance(data["level_counts"], dict)
    for level, count in data["level_counts"].items():
        assert isinstance(count, int)
    # Component counts should be flat integer mapping
    assert isinstance(data["component_counts"], dict)
    for comp, count in data["component_counts"].items():
        assert isinstance(count, int)
    # Total entries should match sum of level counts
    assert data["total_entries"] == sum(data["level_counts"].values())
    # Summary should contain error_count and components
    assert "error_count" in data["summary"]
    assert "components" in data["summary"]
```

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/get_log_summary \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }'
```

**Response:**

```json
{
  "total_entries": 9,
  "level_counts": {
    "ERROR": 4,
    "WARNING": 1,
    "INFO": 4
  },
  "component_counts": {
    "BoardReader01": 6,
    "EventBuilder01": 3
  },
  "summary": {
    "total_entries": 9,
    "error_count": 4,
    "warning_count": 1,
    "components": ["BoardReader01", "EventBuilder01"],
    "time_range_start": "2026-02-14T10:30:01.003",
    "time_range_end": "2026-02-14T10:45:32.118"
  }
}
```

---

#### Tool 5: correlate_events

##### 1. Purpose

Cross-correlates events across components within a time window. For each entry
matching the target severity level (default ERROR), this tool finds entries from
OTHER components that occurred within the specified time window. Results are
organized as trigger/related-events pairs.

Use this tool when: the agent has identified errors in one component and wants
to understand what was happening in other components at the same time -- for
example, to determine whether a BoardReader timeout caused downstream EventBuilder
failures, or whether multiple components failed simultaneously due to a shared
upstream cause.

Returns: a list of correlation objects (each with a trigger entry and its related
events from other components), the total number of correlations found, and a list
of all components present in the parsed logs.

Requires: `parse_logs` must have been called first.

##### 2. Endpoint

```
POST /api/v1/agent/tools/correlate_events
```

##### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "params": {
      "type": "object",
      "description": "Tool-specific parameters.",
      "properties": {
        "window_seconds": {
          "type": "number",
          "minimum": 0.001,
          "default": 5,
          "description": "Time window in seconds. For each trigger event, related events from other components within this many seconds are included. Default 5 seconds."
        },
        "level": {
          "type": "string",
          "enum": ["ERROR", "WARNING", "INFO", "DEBUG"],
          "default": "ERROR",
          "description": "Severity level of trigger events to correlate. Default 'ERROR'."
        }
      }
    }
  },
  "required": ["session_id"]
}
```

##### 4. Response Schema

```json
{
  "correlations": [
    {
      "trigger": {
        "line": 4,
        "timestamp": "2026-02-14T10:32:15.003",
        "level": "ERROR",
        "component": "BoardReader01",
        "function": "getNext_",
        "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
        "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
      },
      "related_events": [
        {
          "entry": {
            "line": 6,
            "timestamp": "2026-02-14T10:32:16.008",
            "level": "ERROR",
            "component": "EventBuilder01",
            "function": "process_fragments",
            "message": "Incomplete event: expected 4 fragments, received 2",
            "raw_line": "2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2"
          },
          "delta_seconds": 1.005
        },
        {
          "entry": {
            "line": 7,
            "timestamp": "2026-02-14T10:32:16.010",
            "level": "WARNING",
            "component": "EventBuilder01",
            "function": "process_fragments",
            "message": "Dropping incomplete event for sequence 10042",
            "raw_line": "2026-02-14 10:32:16.010 WARNING [EventBuilder01] process_fragments: Dropping incomplete event for sequence 10042"
          },
          "delta_seconds": 1.007
        }
      ]
    },
    {
      "trigger": {
        "line": 5,
        "timestamp": "2026-02-14T10:32:15.510",
        "level": "ERROR",
        "component": "BoardReader01",
        "function": "getNext_",
        "message": "Fragment timeout after 5000ms waiting for data on link 0x0200",
        "raw_line": "2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200"
      },
      "related_events": [
        {
          "entry": {
            "line": 6,
            "timestamp": "2026-02-14T10:32:16.008",
            "level": "ERROR",
            "component": "EventBuilder01",
            "function": "process_fragments",
            "message": "Incomplete event: expected 4 fragments, received 2",
            "raw_line": "2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2"
          },
          "delta_seconds": 0.498
        }
      ]
    }
  ],
  "total_correlations": 2,
  "components": ["BoardReader01", "EventBuilder01"]
}
```

**Navigation handles:**
- `correlations[].trigger.line` -- pass to `get_log_context` to examine the trigger event in detail
- `correlations[].related_events[].entry.line` -- pass to `get_log_context` for related event context
- `correlations[].related_events[].entry.component` -- use in `search_logs` for deeper investigation
- `components[]` -- all components present in parsed logs

##### 5. Error Responses

| HTTP Status | Error Code | Condition |
|-------------|------------|-----------|
| 400 | `VALIDATION_ERROR` | No parsed logs in session (call `parse_logs` first) |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match an active session |

**Capping behavior:** Results are capped at 50 total correlations and 20 related
events per trigger to prevent oversized responses. If a single component log is
provided, correlations will simply be empty (no error is raised).

**Example error response:**

```json
{
  "error": true,
  "error_code": "VALIDATION_ERROR",
  "message": "No parsed logs in session. Call parse_logs first."
}
```

##### 6. Implementation

**Module:** `srcs/api/tools/log_tools.py`

**Registration:** `@register_tool("correlate_events")` decorator from `srcs/api/tools/router.py`

**Code path:**

```
POST /api/v1/agent/tools/correlate_events
  → srcs/api/tools/log_tools.py::correlate_events(ctx: ToolContext)
    → Extract params from ctx.request_body.get("params", {})
    → Retrieve parsed = ctx.session.state.parsed_logs
        → If empty, raise validation_error("No parsed logs in session.")
    → Group entries by component: by_component dict
    → For each entry matching target_level (case-insensitive):
        → Parse timestamp via datetime.fromisoformat()
        → For each OTHER component's entries:
            → Parse other timestamp, compute delta
            → If abs(delta) <= window_seconds:
                → Add to related list: {"entry": other, "delta_seconds": round(delta, 3)}
        → Cap related_events to 20 per trigger
        → If related list non-empty, add correlation
    → Cap total correlations to 50
    → Return:
        correlations = [{trigger, related_events}, ...]
        total_correlations = len(correlations before cap)
        components = list of all component names
```

**Single parsed-logs list:** This tool operates on the single `session.state.parsed_logs`
list (not multiple log stores). All entries from all prior `parse_logs` calls are
merged into this single list. Cross-component correlation works because the list
contains entries from all components.

##### 7. Dependencies

| Dependency | Required For | Initialization |
|------------|-------------|----------------|
| `SessionStore` | Validating `session_id`, retrieving session state | Created at API startup |
| Session log data | The `list[dict]` stored in `session.state.parsed_logs` | Populated by prior `parse_logs` call |
| `datetime` (stdlib) | Parsing ISO timestamps and computing deltas | Standard library import |

No external services required.

##### 8. Testing

| # | Test Case | Mock Strategy | Key Assertions |
|---|-----------|---------------|----------------|
| 1 | Cross-component correlation | Pre-populate session with entries from BoardReader and EventBuilder with overlapping timestamps | `correlations` contains entries where trigger is from one component and related_events from another; `delta_seconds` values are correct |
| 2 | Time window filtering | Pre-populate with events at t=0, t=2s, t=10s; set `window_seconds=5` | Events at t=0 and t=2s included in related_events; event at t=10s excluded |
| 3 | Level parameter | Pre-populate with mixed-severity entries; set `level: "WARNING"` | Only WARNING entries appear as triggers in correlations |
| 4 | Single component yields no correlations | Pre-populate with entries from only one component | `correlations` is empty; `total_correlations == 0` |
| 5 | Components list is complete | Pre-populate with entries from two components | `components` contains both component names |

```python
@pytest.mark.asyncio
async def test_correlate_events_cross_component(client, session_with_multi_component_logs):
    """Correlate events across components within a time window."""
    session_id = session_with_multi_component_logs
    response = await client.post(
        "/api/v1/agent/tools/correlate_events",
        json={
            "session_id": session_id,
            "params": {
                "window_seconds": 5,
                "level": "ERROR",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    # Should have correlations
    assert data["total_correlations"] > 0
    # Each correlation has a trigger and related events
    for corr in data["correlations"]:
        assert "trigger" in corr
        assert "related_events" in corr
        trigger_comp = corr["trigger"]["component"]
        for rel in corr["related_events"]:
            # Related events should be from different components
            assert rel["entry"]["component"] != trigger_comp
            assert "delta_seconds" in rel
            assert rel["delta_seconds"] <= 5.0
    # Components list should include all components
    assert len(data["components"]) >= 2
```

##### 9. Example

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/correlate_events \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "params": {
      "window_seconds": 5,
      "level": "ERROR"
    }
  }'
```

**Response:**

```json
{
  "correlations": [
    {
      "trigger": {
        "line": 4,
        "timestamp": "2026-02-14T10:32:15.003",
        "level": "ERROR",
        "component": "BoardReader01",
        "function": "getNext_",
        "message": "Fragment timeout after 5000ms waiting for data on link 0x0100",
        "raw_line": "2026-02-14 10:32:15.003 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0100"
      },
      "related_events": [
        {
          "entry": {
            "line": 6,
            "timestamp": "2026-02-14T10:32:16.008",
            "level": "ERROR",
            "component": "EventBuilder01",
            "function": "process_fragments",
            "message": "Incomplete event: expected 4 fragments, received 2",
            "raw_line": "2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2"
          },
          "delta_seconds": 1.005
        },
        {
          "entry": {
            "line": 7,
            "timestamp": "2026-02-14T10:32:16.010",
            "level": "WARNING",
            "component": "EventBuilder01",
            "function": "process_fragments",
            "message": "Dropping incomplete event for sequence 10042",
            "raw_line": "2026-02-14 10:32:16.010 WARNING [EventBuilder01] process_fragments: Dropping incomplete event for sequence 10042"
          },
          "delta_seconds": 1.007
        }
      ]
    },
    {
      "trigger": {
        "line": 5,
        "timestamp": "2026-02-14T10:32:15.510",
        "level": "ERROR",
        "component": "BoardReader01",
        "function": "getNext_",
        "message": "Fragment timeout after 5000ms waiting for data on link 0x0200",
        "raw_line": "2026-02-14 10:32:15.510 ERROR [BoardReader01] getNext_: Fragment timeout after 5000ms waiting for data on link 0x0200"
      },
      "related_events": [
        {
          "entry": {
            "line": 6,
            "timestamp": "2026-02-14T10:32:16.008",
            "level": "ERROR",
            "component": "EventBuilder01",
            "function": "process_fragments",
            "message": "Incomplete event: expected 4 fragments, received 2",
            "raw_line": "2026-02-14 10:32:16.008 ERROR [EventBuilder01] process_fragments: Incomplete event: expected 4 fragments, received 2"
          },
          "delta_seconds": 0.498
        }
      ]
    }
  ],
  "total_correlations": 2,
  "components": ["BoardReader01", "EventBuilder01"]
}
```

---

> [← Architecture](agentic-rest-service-design-ch1-architecture.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Code Analysis Tools →](agentic-rest-service-design-ch3-code-analysis-tools.md)
