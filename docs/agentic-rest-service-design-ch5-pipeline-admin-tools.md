> **Agentic REST API Design Document** | [← Knowledge & Finding Tools](agentic-rest-service-design-ch4-knowledge-finding-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Client Refactoring →](agentic-rest-service-design-ch6-client-refactoring.md)

---

# Chapter 5: Pipeline, Expert & Admin Tools

### Category: Pipeline

---

## Tool 17: `investigate`

### 1. Purpose

Runs the full 7-phase investigation pipeline on an error within the context of an active session. This is the primary analytical tool -- it accepts error input from three sources (in priority order): (1) inline `source_files` with raw log content, (2) an `error_message` parameter, or (3) previously parsed logs in the session state (from a prior `parse_logs` call). It produces a root cause analysis with a calibrated confidence score.

Returns: `outcome` (investigation verdict), `confidence` (calibrated score), `root_cause` (full `InvestigationConclusion` model dump, or stringified if not a model, or null), `executive_summary`, `explanation`, and `recommendations`.

Use this tool when the agent has identified a specific error to investigate. The error can be provided directly via `source_files` or `error_message`, or it can come from session state populated by a prior `parse_logs` call. The investigation result is stored in `session.state.investigation_result` for follow-up queries.

This is a synchronous endpoint. It blocks until the investigation completes, which may take 30-120 seconds depending on pipeline depth and LLM latency.

### 2. Endpoint

```
POST /api/v1/agent/tools/investigate
```

### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier. Investigation state is stored here."
    },
    "params": {
      "type": "object",
      "description": "Investigation parameters. All fields are optional -- if omitted, the error is extracted from session parsed_logs.",
      "properties": {
        "error_message": {
          "type": "string",
          "description": "Error message text. Used as the trigger error when source_files are not provided."
        },
        "level": {
          "type": "string",
          "description": "Log severity level for error_message. Defaults to 'ERROR'.",
          "default": "ERROR"
        },
        "component": {
          "type": "string",
          "description": "artdaq component name (e.g., BoardReader_01, EventBuilder_00). Defaults to 'Unknown'.",
          "default": "Unknown"
        },
        "verbose": {
          "type": "boolean",
          "description": "Enable verbose output (used by investigate_stream for LLM/data events).",
          "default": false
        },
        "source_files": {
          "type": "array",
          "description": "Raw log files to parse inline. When provided, the trigger error is extracted from the first file. Each file contains a filename, raw content, and optional error_line pointer.",
          "items": {
            "type": "object",
            "properties": {
              "filename": {
                "type": "string",
                "description": "Name of the log file"
              },
              "content": {
                "type": "string",
                "description": "Raw log file content"
              },
              "error_line": {
                "type": ["integer", "null"],
                "description": "Line number of the error to investigate. If null, the first ERROR entry is used.",
                "default": null
              }
            },
            "required": ["filename", "content"]
          }
        }
      }
    }
  },
  "required": ["session_id"]
}
```

**Error resolution priority:** The tool resolves the trigger error from three sources in this order:

1. **`source_files`** -- If provided, the first file's content is parsed via `parse_log_content()` and the error is extracted using `extract_error_and_context()` with the optional `error_line` pointer. Up to 60 context log entries surrounding the error are included.
2. **`error_message`** -- If no source_files (or parsing yields no entries), a `Log` is constructed from `error_message`, `level`, and `component` with an empty context list.
3. **Session `parsed_logs`** -- If neither of the above is provided, the tool falls back to `session.state.parsed_logs` (populated by a prior `parse_logs` call). The first ERROR entry becomes the trigger, and preceding entries become context (capped at 60).

### 4. Response Schema

```json
{
  "outcome": "CONFIDENT",
  "confidence": 0.82,
  "root_cause": {
    "root_cause": "Fragment timeout in BoardReader_01 due to upstream hardware link failure on link 0x0100",
    "confidence": {
      "raw": 0.82,
      "calibrated": 0.78
    },
    "caveats": [
      "Hardware link status could not be verified directly from logs"
    ],
    "code_snippet": "if (timeout_ms > fragment_timeout_) {\n  TLOG(TLERROR) << \"Fragment timeout after \" << timeout_ms << \"ms\";\n}",
    "code_location": "artdaq/DAQdata/Globals.cc:482 in check_fragment_timeout()",
    "sub_causes": [],
    "data_flow": "FE Hardware -> BoardReader_01::getNext_() -> FragmentBuffer -> EventBuilder",
    "key_files": [],
    "debugging_steps": [
      "Check FE hardware link status register for link 0x0100",
      "Verify FE firmware version matches expected configuration",
      "Compare run configuration with last successful run"
    ]
  },
  "executive_summary": "Fragment timeout on BoardReader_01 link 0x0100 caused by upstream hardware link failure.",
  "explanation": "The investigation identified a consistent pattern of fragment timeouts...",
  "recommendations": [
    "Check physical link status on FE module for link 0x0100",
    "Review FE configuration for timeout parameters",
    "Compare with last known-good run configuration"
  ]
}
```

The response contains only these six top-level fields. The `root_cause` field is the full `InvestigationConclusion` model dump (via `model_dump(mode="json")`), or a stringified representation if not a Pydantic model, or `null` if no root cause was identified. Fields from the full `InvestigationResult` that are **not** returned: `investigation_id`, `timestamp`, `causal_chain`, `evidence_summary`, `processing_tier`, `pattern_match_used`, `duration_seconds`, `alternatives`, `viable_hypotheses`, `discrimination_needed`, `insufficient_reason`, `missing_evidence`, `primary_hypothesis`.

### 5. Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not exist or has expired |
| 422 | `VALIDATION_ERROR` | No error source available (no `source_files`, no `error_message`, and no session `parsed_logs`) |
| 500 | `TOOL_EXECUTION_ERROR` | Unrecoverable error during pipeline execution |

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Either provide 'error_message' or call parse_logs first.",
    "details": {}
  }
}
```

### 6. Implementation

```
POST request
  -> FastAPI tool dispatch (srcs/api/tools/pipeline_tools.py:investigate)
  -> _build_error_log(ctx) resolves trigger error and context:
     Priority 1: source_files -> parse_log_content() + extract_error_and_context()
     Priority 2: error_message -> construct Log(level, component, message)
     Priority 3: session.state.parsed_logs -> find first ERROR entry + preceding context
  -> _parse_source_files(params) extracts SourceFile objects if present
  -> _get_coordinator() builds InvestigationCoordinator from dependency injection
     (Settings -> LLMConfig -> LLMProvider, StorageConfig -> KnowledgeBase, SourceConfig,
      InvestigationConfig, PipelineConfig)
  -> await coordinator.investigate(error, context, source_files=source_files)
     (srcs/agent/coordinator.py:InvestigationCoordinator.investigate)
     -> PipelineEngine.execute() runs phases 0-7
  -> Store result.model_dump(mode="json") in session.state.investigation_result
  -> Extract and return six response fields from InvestigationResult
```

Key code path: `srcs/api/tools/pipeline_tools.py:investigate()` calls `_build_error_log()` to resolve the trigger error, then delegates to `InvestigationCoordinator.investigate(error, context, source_files)` which returns `InvestigationResult`. The coordinator delegates to `PipelineEngine` which executes configured phases in order: prior retrieval (0), hypothesis generation (1), evidence seeking (2), causal chains (3), adversarial review (4), insufficiency check (5), synthesis (6), and optional learning (7).

### 7. Dependencies

| Service | Purpose |
|---------|---------|
| `SessionStore` | Retrieve and update session state |
| `InvestigationCoordinator` | Pipeline orchestration (built via `_get_coordinator()`) |
| `KnowledgeBase` | Pattern retrieval, similar case lookup, result persistence |
| `LLMProvider` | Hypothesis generation, evidence analysis, synthesis |
| `SourceConfig` | Source repository paths for code-centric evidence |

### 8. Testing

```
test_investigate_returns_confident_result
  - POST with valid session_id and params containing error_message
  - Mock InvestigationCoordinator.investigate to return CONFIDENT result
  - Assert 200, outcome == "CONFIDENT", root_cause present

test_investigate_with_source_files
  - POST with valid session_id and params containing source_files
  - Assert error is extracted from first file's content
  - Assert 200 with investigation result

test_investigate_stores_result_in_session
  - POST with valid session and error_message
  - Verify session.state.investigation_result contains the result after completion

test_investigate_falls_back_to_session_parsed_logs
  - POST with valid session_id but no error_message and no source_files
  - Pre-populate session.state.parsed_logs with ERROR entries
  - Assert error is extracted from parsed_logs

test_investigate_invalid_session_returns_404
  - POST with non-existent session_id
  - Assert 404 with error code "SESSION_NOT_FOUND"

test_investigate_no_error_source_returns_422
  - POST with session_id but no error_message, no source_files, and empty parsed_logs
  - Assert 422 with error code "VALIDATION_ERROR"
```

### 9. Example

Using `error_message` parameter:

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "params": {
      "error_message": "Fragment timeout after 5000ms on link 0x0100",
      "component": "BoardReader_01",
      "level": "ERROR"
    }
  }'
```

Using `source_files` parameter (highest priority):

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "params": {
      "source_files": [
        {
          "filename": "BoardReader_01.log",
          "content": "14-Feb-2026 10:32:10.001 DEBUG BoardReader_01 getNext_: Requesting fragment from link 0x0100\n14-Feb-2026 10:32:15.003 ERROR BoardReader_01 getNext_: Fragment timeout after 5000ms on link 0x0100\n14-Feb-2026 10:32:17.450 WARNING BoardReader_01 putFragmentOnSHM_: SHM write failed: buffer full",
          "error_line": 2
        }
      ]
    }
  }'
```

Response:

```json
{
  "outcome": "CONFIDENT",
  "confidence": 0.82,
  "root_cause": {
    "root_cause": "Fragment timeout in BoardReader_01 due to upstream hardware link failure on link 0x0100",
    "confidence": {
      "raw": 0.82,
      "calibrated": 0.78
    },
    "caveats": ["Hardware link status could not be verified directly from logs"],
    "code_snippet": "if (timeout_ms > fragment_timeout_) { ... }",
    "code_location": "artdaq/DAQdata/Globals.cc:482",
    "sub_causes": [],
    "data_flow": "FE Hardware -> BoardReader_01::getNext_() -> FragmentBuffer -> EventBuilder",
    "key_files": [],
    "debugging_steps": [
      "Check FE hardware link status register for link 0x0100",
      "Verify FE firmware version matches expected configuration"
    ]
  },
  "executive_summary": "Fragment timeout on BoardReader_01 link 0x0100 caused by upstream hardware link failure.",
  "explanation": "The investigation identified a consistent pattern of fragment timeouts on a single link...",
  "recommendations": [
    "Check physical link status on FE module for link 0x0100",
    "Review FE configuration for timeout parameters"
  ]
}
```

---

## Tool 18: `investigate_stream`

### 1. Purpose

Streaming version of the investigation pipeline that delivers real-time progress events via Server-Sent Events (SSE) while the 7-phase pipeline executes. Returns a `StreamingResponse` (not a JSON dict). This is the preferred tool for interactive clients that want to display phase-by-phase progress as the investigation unfolds.

Use this when the calling agent or UI needs visibility into the investigation as it happens, rather than waiting for the full result. The final `investigation_complete` event carries the full investigation result as a model dump.

The callback mechanism uses `phase_event_to_sse()` to map `PhaseEvent` callbacks to SSE events with event types of the form `phase_{evt.event_type}`. When `verbose=true` is set in params, the tool additionally wires `llm_event_to_sse` and `data_retrieval_event_to_sse` mappers via `LoggingLLMProvider` and `LoggingKnowledgeBase` wrappers, emitting `llm_request`, `llm_response`, `data_query`, and `data_result` events alongside the phase events.

### 2. Endpoint

```
POST /api/v1/agent/tools/investigate_stream
Accept: text/event-stream
```

### 3. Request Schema

The request body uses the same schema as `investigate` (same `session_id` + `params` structure with `error_message`, `level`, `component`, `source_files`). The `verbose` parameter in `params` controls whether LLM and data retrieval events are also streamed:

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
      "description": "Same params as investigate, plus verbose controls SSE detail level.",
      "properties": {
        "error_message": { "type": "string" },
        "level": { "type": "string", "default": "ERROR" },
        "component": { "type": "string", "default": "Unknown" },
        "verbose": {
          "type": "boolean",
          "description": "When true, also emit llm_request, llm_response, data_query, and data_result SSE events via LoggingLLMProvider and LoggingKnowledgeBase wrappers.",
          "default": false
        },
        "source_files": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "filename": { "type": "string" },
              "content": { "type": "string" },
              "error_line": { "type": ["integer", "null"], "default": null }
            },
            "required": ["filename", "content"]
          }
        }
      }
    }
  },
  "required": ["session_id"]
}
```

### 4. Response Schema

The response is an SSE stream (`Content-Type: text/event-stream`). Each event has a `type` field and a `data` payload.

**SSE Event Types (always emitted):**

| Event Type | Source | Description |
|-----------|--------|-------------|
| `phase_start` | `phase_event_to_sse(PhaseEvent(event_type="start"))` | Phase is beginning execution |
| `phase_progress` | `phase_event_to_sse(PhaseEvent(event_type="progress"))` | Incremental progress within a phase |
| `phase_complete` | `phase_event_to_sse(PhaseEvent(event_type="complete"))` | Phase finished successfully |
| `investigation_complete` | Pipeline finished | Full investigation result (model dump) |
| `error` | Pipeline exception | Error details (`{"message": "..."}`) |

**SSE Event Types (verbose=true only):**

| Event Type | Source | Description |
|-----------|--------|-------------|
| `llm_request` | `llm_event_to_sse(LLMEvent(event_type="request"))` | LLM prompt being sent (system_prompt, user_prompt, model_name) |
| `llm_response` | `llm_event_to_sse(LLMEvent(event_type="response"))` | LLM response received (response text, parse status) |
| `data_query` | `data_retrieval_event_to_sse(DataRetrievalEvent(event_type="query"))` | Knowledge base query (source, operation, query_params) |
| `data_result` | `data_retrieval_event_to_sse(DataRetrievalEvent(event_type="result"))` | Knowledge base result (result_summary, result_count) |

When `verbose=true`, the tool wraps the coordinator's `LLMProvider` with `LoggingLLMProvider` (from `srcs/llm/logging_wrapper.py`) and the `KnowledgeBase` with `LoggingKnowledgeBase` (from `srcs/knowledge/logging_wrapper.py`). These wrappers intercept all LLM calls and data queries, emitting SSE events for each one. The wrappers also update the coordinator's internal `_pipeline_engine` references if the engine has already been created.

**Event structures:**

```
event: phase_start
data: {"phase": 0, "phase_name": "Prior Knowledge Retrieval", "message": "Searching for similar cases and known patterns..."}

event: phase_progress
data: {"phase": 1, "phase_name": "Hypothesis Generation", "message": "Generated 4 hypotheses from 3 sources", "hypothesis_count": 4, "sources": ["pattern", "similar", "fresh"]}

event: phase_complete
data: {"phase": 1, "phase_name": "Hypothesis Generation", "hypotheses_generated": 4, "top_hypothesis": "Fragment timeout due to hardware link failure", "top_prior": 0.75}

event: investigation_complete
data: {"outcome": "CONFIDENT", "confidence": 0.82, "root_cause": "Fragment timeout in BoardReader_01...", "executive_summary": "Fragment timeout on BoardReader_01 link 0x0100 caused by upstream hardware link failure."}

event: error
data: {"message": "Connection refused to Ollama"}
```

The `investigation_complete` event data contains the full `InvestigationResult` model dump (via `result.model_dump(mode="json")`), which is also stored in `session.state.investigation_result`. The `error` event data contains only a `message` field.

### 5. Error Responses

Errors during streaming are delivered as SSE `error` events rather than HTTP error codes, since the stream has already started with a 200 status. Pre-stream validation errors use standard HTTP codes.

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not exist (pre-stream validation) |
| 422 | `VALIDATION_ERROR` | Invalid request body (pre-stream validation) |
| 200 + SSE `error` | n/a | Any exception during pipeline execution (message in SSE event data) |

Pre-stream error:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 550e8400-... not found or expired.",
    "details": {}
  }
}
```

Mid-stream error (SSE):

```
event: error
data: {"message": "Connection to Ollama lost during evidence seeking phase"}
```

### 6. Implementation

```
POST request
  -> FastAPI tool dispatch (srcs/api/tools/pipeline_tools.py:investigate_stream)
  -> _build_error_log(ctx) resolves trigger error and context (same as investigate)
  -> Parse verbose flag from params (default false)
  -> _parse_source_files(params) extracts SourceFile objects if present
  -> _get_coordinator() builds InvestigationCoordinator
  -> Create asyncio.Queue[SSEEvent | None] for event bridging
  -> Define three callbacks: on_phase_event, on_llm_event, on_data_event
     - Each calls the corresponding mapper (*_to_sse) and puts result onto queue
  -> If verbose=true:
     - Wrap coordinator.llm with LoggingLLMProvider(llm, on_llm_event)
     - Wrap coordinator.kb with LoggingKnowledgeBase(kb, on_data_event)
     - Also update coordinator._pipeline_engine references if engine exists
  -> Return StreamingResponse(media_type="text/event-stream")
     -> Spawn asyncio task: run_investigation()
        - await coordinator.investigate(error, context, callback=on_phase_event,
                                         source_files=source_files)
        - On completion: store result.model_dump() in session.state.investigation_result
          - Put SSEEvent(event="investigation_complete", data=result_dict) onto queue
        - On exception: put SSEEvent(event="error", data={"message": str(e)}) onto queue
        - Finally: put None sentinel to signal stream end
     -> event_generator() reads from queue, yields format_sse(event) until sentinel
```

The callback parameter in `InvestigationCoordinator.investigate(error, context, callback)` accepts `Callable[[PhaseEvent], None]`. Phase events are always streamed. When `verbose=true`, the `LoggingLLMProvider` and `LoggingKnowledgeBase` wrappers intercept LLM and data operations, emitting additional SSE events through the same queue.

### 7. Dependencies

| Service | Purpose |
|---------|---------|
| `SessionStore` | Validate session, store final result |
| `InvestigationCoordinator` | Pipeline execution with callback support |
| `KnowledgeBase` | Pattern retrieval, similar cases |
| `LLMProvider` | All LLM-dependent phases |
| `LoggingLLMProvider` | LLM call interception for verbose SSE events |
| `LoggingKnowledgeBase` | Data query interception for verbose SSE events |
| `asyncio.Queue` | Bridge between sync callbacks and async SSE generator |

### 8. Testing

```
test_investigate_stream_returns_sse_content_type
  - POST with valid session and trigger_error
  - Assert Content-Type is "text/event-stream"
  - Collect events, verify at least phase_start and investigation_complete events

test_investigate_stream_emits_phase_events_in_order
  - POST with valid inputs, mock coordinator with callback invocations
  - Collect all phase_start events
  - Assert phases appear in order: 0, 1, 2, 3, 4, 5, 6

test_investigate_stream_complete_event_contains_result_summary
  - POST with valid inputs
  - Parse the investigation_complete event data
  - Assert it contains outcome, confidence, root_cause, and executive_summary fields

test_investigate_stream_invalid_session_returns_404_not_sse
  - POST with non-existent session_id
  - Assert HTTP 404 (not a stream), error code "SESSION_NOT_FOUND"

test_investigate_stream_mid_pipeline_error_emits_error_event
  - Mock LLMProvider to raise during phase 2
  - POST with valid inputs
  - Collect events, assert an "error" event is emitted with a message field
```

### 9. Example

```bash
curl -N -X POST http://localhost:8000/api/v1/agent/tools/investigate_stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "params": {
      "error_message": "Fragment timeout after 5000ms on link 0x0100",
      "component": "BoardReader_01",
      "level": "ERROR",
      "verbose": true
    }
  }'
```

Response (SSE stream):

```
event: phase_start
data: {"phase": 0, "phase_name": "Prior Knowledge Retrieval", "message": "Searching for similar cases and known patterns..."}

event: data_query
data: {"phase": 0, "source": "knowledge_base", "operation": "find_similar", "query_params": {"error_message": "Fragment timeout after 5000ms on link 0x0100"}}

event: data_result
data: {"phase": 0, "source": "knowledge_base", "operation": "find_similar", "result_summary": "Found 2 similar cases", "result_count": 2}

event: phase_complete
data: {"phase": 0, "phase_name": "Prior Knowledge Retrieval", "patterns_found": 1, "similar_cases": 2}

event: phase_start
data: {"phase": 1, "phase_name": "Hypothesis Generation", "message": "Generating root cause hypotheses..."}

event: llm_request
data: {"phase": 1, "model_name": "gpt-oss:120b", "system_prompt": "You are a DAQ systems expert...", "user_prompt": "Generate hypotheses for: Fragment timeout after 5000ms..."}

event: llm_response
data: {"phase": 1, "model_name": "gpt-oss:120b", "response": "Based on the error pattern..."}

event: phase_complete
data: {"phase": 1, "phase_name": "Hypothesis Generation", "hypotheses_generated": 4, "top_hypothesis": "Fragment timeout due to hardware link failure"}

event: phase_start
data: {"phase": 2, "phase_name": "Evidence Seeking", "message": "Gathering discriminating evidence..."}

event: phase_progress
data: {"phase": 2, "phase_name": "Evidence Seeking", "message": "Evidence iteration 3/10: 7 items collected", "iteration": 3, "evidence_count": 7}

event: phase_complete
data: {"phase": 2, "phase_name": "Evidence Seeking", "total_evidence": 12, "iterations_used": 5}

event: phase_start
data: {"phase": 3, "phase_name": "Causal Chain Construction", "message": "Building reasoning chains..."}

event: phase_complete
data: {"phase": 3, "phase_name": "Causal Chain Construction", "chains_built": 2}

event: phase_start
data: {"phase": 4, "phase_name": "Adversarial Review", "message": "Challenging conclusions..."}

event: phase_complete
data: {"phase": 4, "phase_name": "Adversarial Review", "challenges_raised": 3, "challenges_resolved": 2}

event: phase_complete
data: {"phase": 6, "phase_name": "Final Synthesis", "outcome": "CONFIDENT"}

event: investigation_complete
data: {"outcome": "CONFIDENT", "confidence": 0.82, "root_cause": {...}, "executive_summary": "Fragment timeout on BoardReader_01 link 0x0100 caused by upstream hardware link failure.", ...}

```

Note: The `data_query`, `data_result`, `llm_request`, and `llm_response` events shown above are only emitted when `verbose=true` in params. Without verbose mode, only `phase_*` events, `investigation_complete`, and `error` events are emitted.

---

### Category: Expert Panel

---

## Tool 19: `ask_experts`

### 1. Purpose

Asks the expert panel a DAQ-related question and returns a synthesized answer. The panel consists of specialized personas that are dynamically selected based on question type. Each persona contributes its domain expertise, then the panel produces a unified answer with confidence scoring.

Returns: `answer` (synthesized text response), `confidence` (panel consensus score), `question_type` (classification such as TROUBLESHOOT, CONCEPTUAL, etc.), `key_points` (list of key takeaways), and `caveats` (list of limitations or assumptions).

Use this tool when the agent needs domain knowledge about artdaq systems, configuration guidance, troubleshooting advice, or conceptual explanations -- situations where a structured investigation pipeline is not needed, but expert reasoning is valuable.

This is a synchronous-only endpoint. SSE streaming for `ask_experts` is not currently implemented.

### 2. Endpoint

```
POST /api/v1/agent/tools/ask_experts
```

The response is JSON (`Content-Type: application/json`). SSE streaming is not currently implemented for this tool.

### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier. Parsed logs from session state are used as related_logs."
    },
    "params": {
      "type": "object",
      "properties": {
        "question": {
          "type": "string",
          "minLength": 1,
          "description": "The DAQ-related question to ask the expert panel."
        }
      },
      "required": ["question"]
    }
  },
  "required": ["session_id", "params"]
}
```

Log context is automatically drawn from the session's `parsed_logs` state (up to 20 entries), if available from a prior `parse_logs` call. There is no explicit `log_content` or `stream` parameter.

### 4. Response Schema

```json
{
  "answer": "Fragment timeouts in artdaq typically indicate that the BoardReader is not receiving data from the front-end hardware within the configured timeout window. The most common causes are:\n\n1. Hardware link failure: The physical connection between the FE module and the BoardReader host has dropped...\n\n2. FE firmware hang: The front-end firmware has entered a stuck state...\n\n3. Configuration mismatch: The timeout parameter in the FCL configuration is set too low for the data rate...",
  "confidence": 0.85,
  "question_type": "TROUBLESHOOT",
  "key_points": [
    "Fragment timeouts originate in BoardReader getNext_() when no fragment arrives within the configured window",
    "Three primary causes: hardware link failure, firmware hang, configuration mismatch",
    "Check FE status registers and link diagnostics before adjusting timeout parameters"
  ],
  "caveats": [
    "Exact diagnostic steps depend on the specific FE hardware module in use"
  ]
}
```

The response contains only these five top-level fields. Fields from the full `PanelResponse` that are **not** returned: `question_id`, `sources`, `dissenting_views`, `contributions_summary`, `citations`. The `question_type` is the string value of the classification enum (e.g., `"TROUBLESHOOT"`, `"CONCEPTUAL"`).

### 5. Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not exist or has expired |
| 422 | `VALIDATION_ERROR` | `question` is missing from params |
| 500 | `TOOL_EXECUTION_ERROR` | Unrecoverable error during panel orchestration |

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'question' is required for ask_experts.",
    "details": {}
  }
}
```

### 6. Implementation

```
POST request
  -> FastAPI tool dispatch (srcs/api/tools/pipeline_tools.py:ask_experts)
  -> Extract question from params (raise VALIDATION_ERROR if missing)
  -> Create LLMProvider from dependencies (get_settings -> get_llm_config -> create_llm_provider)
  -> Instantiate PanelOrchestrator(llm_provider=llm)
     (srcs/persona/orchestrator.py:PanelOrchestrator)
  -> Build related_logs from session.state.parsed_logs (up to 20 entries)
     - Each entry converted to Log model (timestamp, level, component, message)
     - Entries that fail conversion are silently skipped
  -> result = await orchestrator.answer(question, related_logs=related_logs or None)
     (srcs/persona/orchestrator.py:PanelOrchestrator.answer)
  -> Extract subset of fields from PanelResponse:
     - answer, confidence, question_type (as .value string), key_points, caveats
  -> Return JSON response
```

This is a synchronous-only tool. No SSE streaming callback is wired for `ask_experts` in the current implementation.

### 7. Dependencies

| Service | Purpose |
|---------|---------|
| `SessionStore` | Validate session, provide parsed logs from session state |
| `PanelOrchestrator` | Expert panel coordination |
| `LLMProvider` | Question classification, persona contributions, synthesis |
| `BasePersona` subclasses | Individual persona reasoning (Archivist, Theorist, etc.) |

### 8. Testing

```
test_ask_experts_returns_panel_response
  - POST with valid session_id and question
  - Mock PanelOrchestrator.answer to return PanelResponse
  - Assert 200, answer field is non-empty, confidence is between 0 and 1

test_ask_experts_includes_question_type
  - POST with valid session_id and question
  - Assert response contains question_type as a string (e.g., "TROUBLESHOOT")

test_ask_experts_with_session_logs
  - POST with question after parse_logs has populated session state
  - Verify PanelOrchestrator.answer receives related_logs list from session

test_ask_experts_invalid_session_returns_404
  - POST with non-existent session_id
  - Assert 404 with error code "SESSION_NOT_FOUND"

test_ask_experts_missing_question_returns_422
  - POST with params but no question field
  - Assert 422 with error code "VALIDATION_ERROR"
```

### 9. Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/ask_experts \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "params": {
      "question": "What causes fragment timeouts in BoardReaders and how do I diagnose them?"
    }
  }'
```

Response:

```json
{
  "answer": "Fragment timeouts in artdaq BoardReaders occur when the getNext_() method does not receive a data fragment from the front-end hardware within the configured timeout window (typically set via the fragment_timeout parameter in FCL).\n\nThe three most common causes are:\n\n1. Hardware link failure -- The physical or optical link between the front-end module and the host has dropped. Check FE status registers and link diagnostics.\n\n2. Front-end firmware hang -- The FE FPGA firmware has entered a stuck state and is no longer producing data. A power cycle or firmware reset is typically required.\n\n3. Configuration mismatch -- The fragment_timeout value is set too low relative to the expected data rate, causing spurious timeouts during normal operation. Review the FCL configuration against the expected trigger rate.\n\nDiagnostic steps: (1) Check if the timeout is on a single link or all links, (2) examine FE status registers, (3) compare the current FCL with the last known-good configuration, (4) check for upstream errors preceding the timeout in the logs.",
  "confidence": 0.85,
  "question_type": "TROUBLESHOOT",
  "key_points": [
    "Fragment timeouts originate in BoardReader getNext_() when no fragment arrives within the configured window",
    "Three primary causes: hardware link failure, firmware hang, configuration mismatch",
    "Check FE status registers and link diagnostics before adjusting timeout parameters"
  ],
  "caveats": [
    "Exact diagnostic steps depend on the specific FE hardware module in use"
  ]
}
```

---

### Category: Admin

---

## Tool 20: `init_knowledge_base`

### 1. Purpose

Initializes the knowledge base infrastructure required for the investigation system. This creates data directories, initializes the SQLite database schema, optionally checks Ollama model availability, and optionally syncs source repositories from GitHub.

Use this tool on first deployment or when resetting the knowledge base. It is an administrative operation that does NOT require a session -- it operates on server-wide state.

This tool is idempotent: calling it multiple times will not corrupt existing data. Directories are created with `exist_ok=True`, and database schema initialization uses `CREATE TABLE IF NOT EXISTS`.

### 2. Endpoint

```
POST /api/v1/agent/tools/init_knowledge_base
```

### 3. Request Schema

```json
{
  "type": "object",
  "properties": {
    "params": {
      "type": "object",
      "properties": {
        "skip_source": {
          "type": "boolean",
          "description": "Skip syncing source repositories from GitHub. Use when repositories are already cloned or not needed.",
          "default": false
        },
        "skip_ollama_check": {
          "type": "boolean",
          "description": "Accepted but reserved for future use. The tool version does not implement Ollama model checking.",
          "default": false
        }
      }
    }
  },
  "required": []
}
```

Note: This is a session-less tool (`session_less=True`). No `session_id` is required. The `skip_ollama_check` parameter is accepted in the schema but is not currently acted upon -- it is reserved for future implementation of Ollama model availability checking in the tool version.

### 4. Response Schema

```json
{
  "success": true,
  "steps": [
    {
      "step": "create_directories",
      "success": true,
      "message": "Created ./data"
    },
    {
      "step": "init_database",
      "success": true,
      "message": "SQLite initialized at ./data/knowledge.db"
    },
    {
      "step": "sync_source",
      "success": true,
      "message": "3 repos synced"
    }
  ]
}
```

The `steps` array is ordered by execution sequence: `create_directories`, `init_database`, `sync_source`. Each step runs regardless of whether previous steps failed (best-effort initialization). The top-level `success` is `true` only if all steps succeeded. When `skip_source=true`, the `sync_source` step is still present but with message `"Skipped"`.

### 5. Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 422 | `VALIDATION_ERROR` | `config.yaml` does not exist on the server |
| 500 | `TOOL_EXECUTION_ERROR` | Unrecoverable error during initialization |

Note: Individual step failures do NOT produce HTTP errors. They are reported as `success: false` entries in the `steps` array with descriptive messages, and the top-level `success` is set to `false`.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "config.yaml not found.",
    "details": {}
  }
}
```

### 6. Implementation

```
POST request
  -> FastAPI tool dispatch (srcs/api/tools/admin_tools.py:init_knowledge_base)
  -> Extract params: skip_source (default false), skip_ollama_check (reserved, unused)
  -> Verify config.yaml exists (raise VALIDATION_ERROR if missing)
  -> Parse config.yaml with PyYAML
  -> Step 1: Create data directories
     - data_dir from storage.sqlite_path parent
     - data_dir/chroma/ for ChromaDB
  -> Step 2: Initialize SQLite database
     - SQLiteStore(db_path)._ensure_initialized()
     - Creates tables: investigations, patterns, calibration, etc.
  -> Step 3: Sync source repos (unless skip_source)
     - load_source_config() from srcs.config
     - If source_config exists and has_repositories():
       RepositoryManager(source_config).sync_all() via asyncio.to_thread
     - Clones new repos, pulls updates for existing ones
     - If skip_source: step recorded with message "Skipped"
  -> Return {"success": all_success, "steps": steps}
```

Implementation file: `srcs/api/tools/admin_tools.py:init_knowledge_base()`. This is a standalone tool implementation that reads config.yaml directly (not via the admin route handler). The `skip_ollama_check` parameter is accepted but assigned to `_` (unused).

### 7. Dependencies

| Service | Purpose |
|---------|---------|
| `config.yaml` | Server configuration (storage paths, source repos) |
| `SQLiteStore` | Database schema initialization (`srcs/knowledge/sqlite_store.py`) |
| `RepositoryManager` | GitHub repository cloning and updating (`srcs/source`) |
| `load_source_config` | Source config loader (`srcs/config.py`) |

### 8. Testing

```
test_init_creates_directories_and_database
  - POST with default parameters
  - Mock config.yaml with valid content
  - Assert 200, success=true
  - Assert steps include create_directories, init_database, sync_source with success=true

test_init_skip_source_skips_sync
  - POST with params: {"skip_source": true}
  - Assert sync_source step has message "Skipped"
  - Assert no RepositoryManager calls were made

test_init_skip_ollama_check_accepted
  - POST with params: {"skip_ollama_check": true}
  - Assert parameter is accepted without error (reserved for future use)

test_init_missing_config_returns_422
  - Remove config.yaml (or mock it absent)
  - POST with default parameters
  - Assert 422 with error code "VALIDATION_ERROR"

test_init_partial_failure_reports_all_steps
  - Mock RepositoryManager.sync_all to partially fail
  - POST with default parameters
  - Assert 200, success=false
  - Assert sync_source step has success=false
  - Assert other steps still executed and reported
```

### 9. Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/init_knowledge_base \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "skip_source": false
    }
  }'
```

Response:

```json
{
  "success": true,
  "steps": [
    {
      "step": "create_directories",
      "success": true,
      "message": "Created ./data"
    },
    {
      "step": "init_database",
      "success": true,
      "message": "SQLite initialized at ./data/knowledge.db"
    },
    {
      "step": "sync_source",
      "success": true,
      "message": "3 repos synced"
    }
  ]
}
```

Initialization with source sync skipped:

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/init_knowledge_base \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "skip_source": true
    }
  }'
```

Response:

```json
{
  "success": true,
  "steps": [
    {
      "step": "create_directories",
      "success": true,
      "message": "Created ./data"
    },
    {
      "step": "init_database",
      "success": true,
      "message": "SQLite initialized at ./data/knowledge.db"
    },
    {
      "step": "sync_source",
      "success": true,
      "message": "Skipped"
    }
  ]
}
```

---

## Tool 21: `sync_sources`

### 1. Purpose

Syncs configured source repositories from GitHub. For repositories not yet cloned, it performs a fresh clone. For repositories already present, it pulls the latest changes from the configured branch. This keeps the local code index up to date with upstream changes so that investigation tools can reference current source code.

Use this tool when source repositories need refreshing -- after configuration changes, before an investigation that requires current code, or as a periodic maintenance operation.

This is an administrative operation that does NOT require a session. It operates on server-wide state using the `source` section of `config.yaml`.

### 2. Endpoint

```
POST /api/v1/agent/tools/sync_sources
```

### 3. Request Schema

```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

No parameters are required. The tool reads repository configuration from `config.yaml` on the server.

### 4. Response Schema

```json
{
  "results": [
    {
      "repo_name": "art-daq/artdaq",
      "success": true,
      "action": "updated",
      "message": "Pulled latest from branch develop",
      "path": "/opt/daq-analyzer/data/repos/artdaq"
    },
    {
      "repo_name": "art-daq/artdaq_core",
      "success": true,
      "action": "cloned",
      "message": "Cloned branch develop",
      "path": "/opt/daq-analyzer/data/repos/artdaq_core"
    },
    {
      "repo_name": "art-daq/artdaq_utilities",
      "success": false,
      "action": "failed",
      "message": "Authentication failed: ARTDAQ_GITHUB_TOKEN not set or expired",
      "path": null
    }
  ],
  "success_count": 2,
  "failure_count": 1
}
```

Each entry in `results` corresponds to one configured repository. The `action` field indicates what was done: `"cloned"` for new repositories, `"updated"` for existing ones, or `"failed"` for errors. The top-level `success_count` and `failure_count` provide a quick summary.

### 5. Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 422 | `VALIDATION_ERROR` | No source configuration found in `config.yaml` |
| 500 | `TOOL_EXECUTION_ERROR` | Unrecoverable error before sync could start |

Note: Individual repository sync failures do NOT produce HTTP errors. They are reported as `success: false` entries in the `results` array.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "No source configuration found in config.yaml.",
    "details": {}
  }
}
```

### 6. Implementation

```
POST request
  -> FastAPI tool dispatch (srcs/api/tools/admin_tools.py:sync_sources)
  -> load_source_config() from config.yaml
     (srcs/config.py:load_source_config)
  -> If no source config: raise VALIDATION_ERROR
  -> If no repositories configured: return empty results (success_count=0, failure_count=0)
  -> RepositoryManager(source_config)
     (srcs/source:RepositoryManager)
  -> await asyncio.to_thread(manager.sync_all)
     -> For each configured repository:
        - If not cloned: git clone {url} --branch {branch}
        - If cloned: git pull origin {branch}
     -> Returns list of SyncResult(repo_name, success, action, message, path)
  -> Map SyncResult objects to dicts with: repo_name, success, action, message, path (str or null)
  -> Count successes and failures
  -> Return {"results": [...], "success_count": N, "failure_count": N}
```

Implementation file: `srcs/api/tools/admin_tools.py:sync_sources()`. This is a session-less tool (`session_less=True`). The `RepositoryManager.sync_all()` method handles both cloning and updating, running Git operations in a thread pool via `asyncio.to_thread` to avoid blocking the event loop.

### 7. Dependencies

| Service | Purpose |
|---------|---------|
| `config.yaml` | Source repository configuration (URLs, branches) |
| `RepositoryManager` | Git clone/pull operations |
| `ARTDAQ_GITHUB_TOKEN` (env) | Authentication for private repositories |
| Git CLI | Underlying clone/pull operations |

### 8. Testing

```
test_sync_sources_returns_results_for_all_repos
  - POST with no body
  - Mock RepositoryManager.sync_all to return 3 results
  - Assert 200, results has 3 entries, success_count + failure_count == 3

test_sync_sources_no_config_returns_422
  - Mock load_source_config to return None
  - POST with no body
  - Assert 422 with error code "VALIDATION_ERROR"

test_sync_sources_empty_repo_list_returns_empty
  - Mock source config with no repositories
  - POST with no body
  - Assert 200, results is empty, success_count == 0, failure_count == 0

test_sync_sources_partial_failure_reports_both
  - Mock sync_all to return 2 successes and 1 failure
  - POST with no body
  - Assert success_count == 2, failure_count == 1
  - Assert failed entry has action == "failed" and path is null

test_sync_sources_clone_and_update_actions
  - Mock sync_all with one "cloned" and one "updated" result
  - POST with no body
  - Assert one result has action "cloned", other has action "updated"
  - Assert both have non-null path values
```

### 9. Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/sync_sources \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:

```json
{
  "results": [
    {
      "repo_name": "art-daq/artdaq",
      "success": true,
      "action": "updated",
      "message": "Pulled latest from branch develop",
      "path": "/opt/daq-analyzer/data/repos/artdaq"
    },
    {
      "repo_name": "art-daq/artdaq_core",
      "success": true,
      "action": "updated",
      "message": "Pulled latest from branch develop",
      "path": "/opt/daq-analyzer/data/repos/artdaq_core"
    },
    {
      "repo_name": "art-daq/artdaq_utilities",
      "success": true,
      "action": "cloned",
      "message": "Cloned branch develop",
      "path": "/opt/daq-analyzer/data/repos/artdaq_utilities"
    }
  ],
  "success_count": 3,
  "failure_count": 0
}
```

When a repository sync fails:

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/sync_sources \
  -H "Content-Type: application/json"
```

Response:

```json
{
  "results": [
    {
      "repo_name": "art-daq/artdaq",
      "success": true,
      "action": "updated",
      "message": "Pulled latest from branch develop",
      "path": "/opt/daq-analyzer/data/repos/artdaq"
    },
    {
      "repo_name": "private-org/custom-fe-driver",
      "success": false,
      "action": "failed",
      "message": "Authentication failed: ARTDAQ_GITHUB_TOKEN not set or expired",
      "path": null
    }
  ],
  "success_count": 1,
  "failure_count": 1
}
```

---

> [← Knowledge & Finding Tools](agentic-rest-service-design-ch4-knowledge-finding-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Client Refactoring →](agentic-rest-service-design-ch6-client-refactoring.md)
