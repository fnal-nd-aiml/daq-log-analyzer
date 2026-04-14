> **Agentic WorkBinder Library** | [<- Ch. 1: Architecture](agentic-workbinder-library-ch1-architecture.md) | [Table of Contents](agentic-workbinder-library.md) | [Next: Ch. 3: Code Knowledge Artifacts ->](agentic-workbinder-library-ch3-code-artifacts.md)

---

# Chapter 2: Context Artifacts

Context artifacts capture the *what* of an investigation -- the triggering error, the surrounding log environment, and the exact location in source code where the error originated. They are the first artifacts written to the binder and serve as foundational inputs that every downstream phase reads. In the agentic API context, these artifacts map directly to the session's initial state: when a client calls `POST /investigations` or the `investigate_error` MCP tool, the system parses the request payload into these three artifact types and stores them in the binder before any LLM reasoning begins.

Context artifacts answer three questions:

1. **What happened?** -- `ErrorContextArtifact` records the error message, log level, component, and surrounding log entries.
2. **What else was happening?** -- `LogBundleArtifact` merges multiple log files into a chronological timeline with an LLM-generated narrative, providing cross-board context.
3. **Where in the code?** -- `SourceLocationArtifact` pinpoints the source file, line number, and enclosing function where the error message originates.

```
Client Request
    |
    |   POST /investigations { error_message, log_content, ... }
    |
    v
+-------------------+     +-----------------------+     +--------------------------+
| ErrorContext       |     | LogBundle             |     | SourceLocation           |
| Artifact           |     | Artifact              |     | Artifact                 |
|                    |     |                       |     |                          |
| error_message      |     | merged_timeline       |     | file_path                |
| error_level        |     | annotated_narrative   |     | line_number              |
| error_component    |     | primary_error         |     | match_score              |
| context_logs[]     |     | error_timeline[]      |     | function_body            |
+-------------------+     | clues[]               |     | context_before/after     |
        |                  +-----------------------+     +--------------------------+
        |                           |                              |
        +---------------------------+------------------------------+
                                    |
                                    v
                          Phase 1 (Theorist)
                          Phase 2 (Detective)
                          Phase 3 (Logician)
                                  ...
```

All three artifacts share the common `Artifact` base class fields (id, artifact_type, created_by, created_at, tags, phase, function_name, priority, is_deleted) documented in [Chapter 1](agentic-workbinder-library-ch1-architecture.md). The schema tables below list only the type-specific fields unless a base field is set to a non-default value by the producing convenience method.

---

## 2.1 ErrorContextArtifact

### 1. Purpose & Role

The `ErrorContextArtifact` is the anchor of every investigation. It records the exact error message that triggered the investigation together with surrounding log entries that provide immediate temporal context. In the agentic API, this artifact is the first thing the system creates after parsing the client's request. Every downstream persona reads it to understand *what* they are investigating.

Without this artifact, no hypothesis can be generated and no evidence can be sought. The error message text drives pattern matching in the knowledge base, source code location finding, and LLM prompt construction. The `context_logs` field provides a window of log entries around the error that the Detective uses for initial evidence and the Theorist uses for environmental clues.

### 2. Schema

**Inherited base fields** (set to non-default values by `add_error_context()`):

| Field | Type | Value Set | Description |
|-------|------|-----------|-------------|
| `artifact_type` | `ArtifactType` | `ArtifactType.ERROR_CONTEXT` | Fixed discriminator |
| `phase` | `int \| None` | `0` | Always created in Phase 0 |
| `priority` | `Priority` | `Priority.CRITICAL` | Highest priority -- never pruned by token budgeting |

**Type-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `error_message` | `str` | *(required)* | The triggering error message text extracted from the log |
| `error_level` | `str` | `"ERROR"` | Log level of the triggering entry (ERROR, WARNING, FATAL, etc.) |
| `error_component` | `str \| None` | `None` | DAQ component that generated the error (e.g., `BoardReader`, `EventBuilder`) |
| `error_function` | `str \| None` | `None` | Function name from the log entry if parseable |
| `error_timestamp` | `datetime \| None` | `None` | Timestamp of the triggering error entry |
| `context_logs` | `list[dict[str, Any]]` | `[]` | Surrounding log entries serialized as dictionaries via `Log.model_dump()` |

### 3. Producer

**Phase:** 0 (Archivist / Pipeline Engine)

**Persona:** The Pipeline Engine (`srcs/pipeline/engine.py`) or the Archivist phase creates this artifact at investigation start. The Pipeline Engine calls `binder.add_error_context(trigger_error, context_logs, "Pipeline")` before any persona runs. In the persona-based flow, the `RetrievalOrchestrator` creates it during Phase 0.

**Convenience method:** `WorkBinder.add_error_context(error, context_logs, created_by)`

```python
# From srcs/pipeline/engine.py
investigation.binder = WorkBinder(investigation_id=investigation.id)
investigation.binder.add_error_context(trigger_error, context_logs, "Pipeline")
```

The method receives a `Log` model instance and a list of `Log` context entries, serializes the context logs to dictionaries, and sets `priority=Priority.CRITICAL` and `phase=0` automatically.

**Lifecycle moment:** Created once, never updated. If the investigation is resumed, the existing artifact is reloaded from SQLite.

### 4. Consumers

| Phase | Persona | What It Reads | How It Influences Behavior |
|-------|---------|---------------|---------------------------|
| 0 | Archivist | `error_message`, `error_component`, `error_function` | Drives pattern matching and source code location search |
| 1 | Theorist | `error_message`, `error_component`, `error_function`, `context_logs` | Included in hypothesis generation prompt; message text seeds category classification |
| 2 | Detective | `error_message`, `context_logs` | Error text used in `log_search` and `log_source` queries; context logs provide initial evidence candidates |
| 3 | Logician | `error_message` | Terminal node of causal chain -- chain must end at the observed error |
| 4 | Devil's Advocate | `error_message` | Verifies that the conclusion matches the actual error |
| 5 | Judge | `error_message` | Included in outcome assessment prompt |
| 6 | Synthesizer | `error_message`, `error_component`, `context_logs` | Builds executive summary and root cause description; retrieves source locations for code context |

Additionally, the `BinderSerializer` reads this artifact to generate the `ERROR UNDER INVESTIGATION` section of LLM prompts via `serialize_for_investigation_start()`.

### 5. REST API Exposure

**Generic artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=error_context
```

Query parameters: `artifact_type=error_context`, `phase=0`, `limit`, `offset`, `include_deleted`.

**Single artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Response JSON snippet:**

```json
{
  "id": "a1b2c3d4",
  "artifact_type": "error_context",
  "created_by": "Pipeline",
  "created_at": "2026-02-14T10:30:00",
  "updated_at": "2026-02-14T10:30:00",
  "phase": 0,
  "function_name": null,
  "priority": "critical",
  "tags": [],
  "is_deleted": false,
  "content": {
    "error_message": "Fragment generator not initialized in processFragment()",
    "error_level": "ERROR",
    "error_component": "BoardReader",
    "error_function": "processFragment",
    "error_timestamp": "2026-02-14T10:29:55.123000",
    "context_logs": [
      {
        "timestamp": "2026-02-14T10:29:54.900000",
        "level": "INFO",
        "component": "BoardReader",
        "message": "Starting fragment processing loop"
      }
    ]
  }
}
```

Note: The `content` object contains all type-specific fields (base fields like `id`, `created_by`, etc. are promoted to the top level by the `_artifact_to_response()` helper).

### 6. MCP Tool Access

**Primary tool:** `search_artifacts`

```
search_artifacts(
    binder_id="<id>",
    artifact_type="error_context",
    phase=0
)
```

**Also accessible via:** `get_artifact(binder_id, artifact_id)` when the artifact ID is known.

**Full-text search:** `search_artifact_content(binder_id, query="processFragment")` will match against the JSON content of all artifacts including ErrorContextArtifacts.

### 7. Artifact Relationships

```
ErrorContextArtifact
    |
    |  trigger_error_artifact_id
    v
InvestigationStateArtifact -----> references this as the root trigger
    |
    |  Drives retrieval
    v
SourceLocationArtifact(s) ------> found by matching error_message in source code
    |
    |  error_message text
    v
HypothesisArtifact(s) ----------> generated from error context and prior knowledge
```

The `InvestigationStateArtifact` stores a `trigger_error_artifact_id` field that links back to this artifact. The link is established when `add_investigation_state()` is called with the error artifact's ID.

### 8. Session State Mapping

In the agentic REST API session model, the ErrorContextArtifact corresponds to the **investigation trigger**. When a client calls:

```
POST /api/v1/investigations
{
  "error_message": "Fragment generator not initialized",
  "log_content": "...",
  "error_line": 150
}
```

The server parses this payload, creates `Log` objects, and stores them as an `ErrorContextArtifact`. The client can later retrieve this artifact via `GET /binders/{id}/artifacts?artifact_type=error_context` to see exactly what the system recorded as the investigation starting point.

The `GET /binders/{id}/summary` endpoint includes the error context indirectly through the `investigation_id` linkage and artifact counts.

### 9. Example

```json
{
  "id": "ec-7f2a1b09",
  "artifact_type": "error_context",
  "created_by": "Pipeline",
  "created_at": "2026-02-14T10:30:00.123456",
  "updated_at": "2026-02-14T10:30:00.123456",
  "phase": 0,
  "function_name": null,
  "priority": "critical",
  "tags": [],
  "is_deleted": false,
  "content": {
    "error_message": "Data receive timeout: No data received within 5000000 us from sender artdaqbr01 (missing sequence IDs: 121-130) at input rank 0, Timeout: shmem_ds1_br1",
    "error_level": "ERROR",
    "error_component": "EventBuilder",
    "error_function": "getNext_",
    "error_timestamp": "2026-02-14T10:29:55.123000",
    "context_logs": [
      {
        "timestamp": "2026-02-14T10:29:50.001000",
        "level": "INFO",
        "component": "EventBuilder",
        "function": "getNext_",
        "message": "Waiting for data from sender artdaqbr01 at input rank 0"
      },
      {
        "timestamp": "2026-02-14T10:29:54.500000",
        "level": "WARNING",
        "component": "EventBuilder",
        "function": "getNext_",
        "message": "Approaching timeout threshold for sender artdaqbr01"
      },
      {
        "timestamp": "2026-02-14T10:29:55.123000",
        "level": "ERROR",
        "component": "EventBuilder",
        "function": "getNext_",
        "message": "Data receive timeout: No data received within 5000000 us from sender artdaqbr01 (missing sequence IDs: 121-130) at input rank 0, Timeout: shmem_ds1_br1"
      },
      {
        "timestamp": "2026-02-14T10:29:55.200000",
        "level": "ERROR",
        "component": "EventBuilder",
        "function": null,
        "message": "Shutting down EventBuilder due to unrecoverable timeout"
      }
    ]
  }
}
```

---

## 2.2 LogBundleArtifact

### 1. Purpose & Role

The `LogBundleArtifact` exists to solve a specific problem: when an investigation involves multiple log files from different DAQ boards, each file provides only a partial view of the system. The Chronicler persona (Phase -1) merges these files into a single chronological timeline, asks the LLM to interpret the unified narrative, identifies which error came first and caused others, and stores the result as a `LogBundleArtifact`.

This artifact is **conditional** -- it only exists when the investigation was initiated with the `--files` flag (CLI) or with multiple `source_files` (API). Single-file investigations skip Phase -1 entirely and produce no `LogBundleArtifact`.

In the agentic API context, the LogBundleArtifact represents the system's understanding of the cross-board error narrative before any deep code analysis begins. It contains two key data structures that downstream phases use: the `primary_error` (which board/error triggered the cascade) and the `clues` list (typed search suggestions for the Archivist).

### 2. Schema

**Inherited base fields** (set to non-default values by `add_log_bundle()`):

| Field | Type | Value Set | Description |
|-------|------|-----------|-------------|
| `artifact_type` | `ArtifactType` | `ArtifactType.LOG_BUNDLE` | Fixed discriminator |
| `created_by` | `str` | `"Chronicler"` | Default persona |
| `phase` | `int \| None` | `-1` | Default phase for Chronicler |

**Type-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_files` | `list[dict[str, Any]]` | `[]` | Metadata about each source file (filename, error count, size, etc.) |
| `merged_timeline` | `str` | `""` | All log entries from all files interleaved by timestamp into a single chronological text |
| `annotated_narrative` | `str` | `""` | LLM-generated 2-4 paragraph narrative interpreting the merged timeline |
| `primary_error` | `LogBundleErrorEntry \| None` | `None` | The first error in the timeline that the LLM identified as the root trigger |
| `error_timeline` | `list[LogBundleErrorEntry]` | `[]` | All errors across all files in chronological order |
| `cascade_description` | `str` | `""` | LLM-generated description of how the primary error cascaded to other boards |
| `clues` | `list[LogBundleClue]` | `[]` | Typed clues with search suggestions for the Archivist to investigate |
| `affected_boards` | `list[BoardAnalysis]` | `[]` | Per-board structured analysis from Chronicler multi-file triage |
| `cascade_chain` | `list[CascadeLink]` | `[]` | Structured causal links in the failure cascade between boards |
| `documentation_reference` | `str` | `""` | Compact doc reference for downstream phases |

**Sub-model: `BoardAnalysis`**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `board_name` | `str` | *(required)* | Name of the DAQ board |
| `filename` | `str` | `""` | Source log file for this board |
| `role` | `str` | `"unknown"` | Role in the failure (e.g., `"primary"`, `"cascade"`, `"observer"`) |
| `failure_mode` | `str` | `""` | Description of the board's failure mode |
| `key_error_message` | `str` | `""` | Most significant error message from this board |
| `source_location` | `str` | `""` | Source code location related to this board's error |
| `error_count` | `int` | `0` | Number of errors in this board's log |
| `warning_count` | `int` | `0` | Number of warnings in this board's log |

**Sub-model: `CascadeLink`**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `from_board` | `str` | *(required)* | Board where the failure originated |
| `to_board` | `str` | *(required)* | Board that was affected |
| `mechanism` | `str` | *(required)* | How the failure propagated (e.g., `"shared VME crate"`, `"optical link"`) |
| `evidence` | `str` | `""` | Evidence supporting this cascade link |

**Sub-model: `LogBundleErrorEntry`**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `filename` | `str` | *(required)* | Source file containing this error |
| `line_number` | `int \| None` | `None` | Line number in the source file |
| `timestamp` | `datetime \| None` | `None` | Timestamp of the error entry |
| `level` | `str` | `"ERROR"` | Log level |
| `component` | `str \| None` | `None` | DAQ component that generated the error |
| `message` | `str` | *(required)* | The error message text |
| `is_primary` | `bool` | `False` | Whether the Chronicler identified this as the primary trigger error |

**Sub-model: `LogBundleClue`**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `clue_type` | `str` | *(required)* | Category: `"error_pattern"`, `"component_interaction"`, `"timing"`, `"configuration"` |
| `description` | `str` | *(required)* | Human-readable description of the clue |
| `source_file` | `str` | *(required)* | File where the clue was observed |
| `relevance` | `str` | `"HIGH"` | Relevance level: `HIGH`, `MEDIUM`, `LOW` |
| `suggested_search` | `str \| None` | `None` | Suggested search query for the Archivist to run |

### 3. Producer

**Phase:** -1 (Chronicler)

**Persona:** `ChroniclerPersona` in `srcs/persona/chronicler.py`

**Convenience method:** `WorkBinder.add_log_bundle(source_files, merged_timeline, annotated_narrative, primary_error, error_timeline, cascade_description, clues, created_by, phase)`

```python
# From srcs/persona/chronicler.py
artifact_id = binder.add_log_bundle(
    source_files=source_file_meta,
    merged_timeline=merged_timeline,
    annotated_narrative=narrative_response.annotated_narrative,
    primary_error=primary_error_entry,
    error_timeline=error_entries,
    cascade_description=narrative_response.cascade_description,
    clues=clue_entries,
    created_by="Chronicler",
    phase=-1,
)
```

**Production lifecycle:**

1. The Chronicler parses each source file into `Log` entries using the log parser
2. Entries from all files are merged chronologically with board-identifier annotations
3. The merged timeline text is sent to the LLM with the `chronicler` system prompt
4. The LLM returns a `ChroniclerNarrativeResponse` with narrative, primary error identification, cascade description, and clues
5. The Chronicler converts the LLM response into `LogBundleErrorEntry` and `LogBundleClue` objects
6. All data is stored as a single `LogBundleArtifact` via `add_log_bundle()`

**When it is NOT created:** Single-file investigations (the Chronicler checks `len(source_files) <= 1` and returns a passthrough contribution).

### 4. Consumers

| Phase | Persona | What It Reads | How It Influences Behavior |
|-------|---------|---------------|---------------------------|
| 0 | Archivist | `primary_error`, `clues`, `annotated_narrative` | The Archivist calls `binder.get_log_bundle()` and uses clues to guide source code location search. If a clue has `suggested_search`, the Archivist runs that query. The `primary_error` message may override the investigation's trigger error for source location matching. |
| 1 | Theorist | `annotated_narrative`, `cascade_description` | Narrative provides cross-board context for hypothesis generation |
| 2 | Detective | `error_timeline`, `clues` | Timeline errors provide evidence candidates; clue types guide query strategy |
| 6 | Synthesizer | `cascade_description`, `source_files` | Multi-board cascade context included in executive summary |

The key consumer is the Archivist (Phase 0). In `srcs/persona/archivist.py`:

```python
binder = context.require_binder()
log_bundle = binder.get_log_bundle()
if log_bundle is not None:
    logger.info("Using LOG_BUNDLE from Chronicler for guided retrieval")
    # Enrich prior knowledge using clues and primary error
```

### 5. REST API Exposure

**Generic artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=log_bundle
```

Since there is at most one LogBundleArtifact per investigation, this returns either an empty list or a single-element list.

**Single artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Full-text content search:**

```
POST /api/v1/binders/{binder_id}/artifacts/search
{
  "query": "timeout",
  "artifact_types": ["log_bundle"]
}
```

This searches within the JSON content of LogBundleArtifacts for the query string, matching against the `merged_timeline`, `annotated_narrative`, and `cascade_description` fields.

**Response JSON snippet:**

```json
{
  "id": "lb-9c4d2e01",
  "artifact_type": "log_bundle",
  "created_by": "Chronicler",
  "created_at": "2026-02-14T10:29:58",
  "updated_at": "2026-02-14T10:29:58",
  "phase": -1,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "source_files": [ "..." ],
    "merged_timeline": "...",
    "annotated_narrative": "...",
    "primary_error": { "..." },
    "error_timeline": [ "..." ],
    "cascade_description": "...",
    "clues": [ "..." ]
  }
}
```

### 6. MCP Tool Access

**Primary tool:** `search_artifacts`

```
search_artifacts(
    binder_id="<id>",
    artifact_type="log_bundle"
)
```

Since there is at most one LogBundleArtifact per binder, this is equivalent to a direct lookup.

**Also accessible via:** `get_artifact(binder_id, artifact_id)` for direct retrieval, and `search_artifact_content(binder_id, query="cascade")` for full-text search.

### 7. Artifact Relationships

```
                      Source Files (input)
                            |
                            v
                   +------------------+
                   | LogBundleArtifact|
                   |                  |
                   | merged_timeline  |
                   | primary_error ---|-------+
                   | clues[]---------|---+   |
                   +------------------+  |   |
                                         |   |
        +--------------------------------+   |
        |                                    |
        v                                    v
+------------------+              +------------------+
| SourceLocation   |              | ErrorContext      |
| Artifact(s)      |              | Artifact          |
| (guided by       |              | (may adopt        |
|  clue searches)  |              |  primary_error    |
+------------------+              |  as trigger)      |
                                  +------------------+
```

The LogBundleArtifact has an indirect relationship with SourceLocationArtifacts: the Archivist uses clues from the bundle to drive source location searches. The `primary_error` may influence which error message the ErrorContextArtifact records if the multi-file triage identifies a different root cause than the initially specified error line.

### 8. Session State Mapping

In the agentic REST API, the LogBundleArtifact represents the **pre-processing result** for multi-file investigations. The client sees it as an artifact with `phase=-1` in the binder's artifact list. The `GET /binders/{id}/summary` endpoint's `artifact_counts` will include `"log_bundle": 1` when a multi-file investigation was performed.

For the MCP client (Claude Desktop or VS Code), the LogBundleArtifact is accessible through `search_artifacts` and provides the merged narrative context that helps the user understand the cross-board error flow without manually correlating multiple log files.

### 9. Example

```json
{
  "id": "lb-9c4d2e01",
  "artifact_type": "log_bundle",
  "created_by": "Chronicler",
  "created_at": "2026-02-14T10:29:58.456789",
  "updated_at": "2026-02-14T10:29:58.456789",
  "phase": -1,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "source_files": [
      {
        "filename": "board_reader_01.log",
        "error_count": 3,
        "line_count": 1250,
        "first_timestamp": "2026-02-14T10:29:00",
        "last_timestamp": "2026-02-14T10:30:05"
      },
      {
        "filename": "event_builder_01.log",
        "error_count": 5,
        "line_count": 890,
        "first_timestamp": "2026-02-14T10:29:01",
        "last_timestamp": "2026-02-14T10:30:10"
      }
    ],
    "merged_timeline": "[10:29:50.001] [board_reader_01] INFO BoardReader: Starting fragment processing loop\n[10:29:50.100] [event_builder_01] INFO EventBuilder: Waiting for data from sender artdaqbr01\n[10:29:54.500] [event_builder_01] WARNING EventBuilder: Approaching timeout threshold\n[10:29:54.800] [board_reader_01] ERROR BoardReader: Fragment generator not initialized in processFragment()\n[10:29:55.123] [event_builder_01] ERROR EventBuilder: Data receive timeout: No data received within 5000000 us from sender artdaqbr01\n...",
    "annotated_narrative": "The merged timeline reveals a clear cascade originating from BoardReader board_reader_01. At 10:29:54.800, the BoardReader reported a fragment generator initialization failure in processFragment(). This failure prevented data fragments from being sent to the EventBuilder, which subsequently timed out at 10:29:55.123 after waiting 5 seconds for data from artdaqbr01.\n\nThe 323ms gap between the BoardReader error and the EventBuilder timeout is consistent with the EventBuilder's polling interval. The cascade propagated from a single board failure to a system-wide data flow interruption.",
    "primary_error": {
      "filename": "board_reader_01.log",
      "line_number": 847,
      "timestamp": "2026-02-14T10:29:54.800000",
      "level": "ERROR",
      "component": "BoardReader",
      "message": "Fragment generator not initialized in processFragment()",
      "is_primary": true
    },
    "error_timeline": [
      {
        "filename": "board_reader_01.log",
        "line_number": 847,
        "timestamp": "2026-02-14T10:29:54.800000",
        "level": "ERROR",
        "component": "BoardReader",
        "message": "Fragment generator not initialized in processFragment()",
        "is_primary": true
      },
      {
        "filename": "event_builder_01.log",
        "line_number": 623,
        "timestamp": "2026-02-14T10:29:55.123000",
        "level": "ERROR",
        "component": "EventBuilder",
        "message": "Data receive timeout: No data received within 5000000 us from sender artdaqbr01",
        "is_primary": false
      },
      {
        "filename": "event_builder_01.log",
        "line_number": 625,
        "timestamp": "2026-02-14T10:29:55.200000",
        "level": "ERROR",
        "component": "EventBuilder",
        "message": "Shutting down EventBuilder due to unrecoverable timeout",
        "is_primary": false
      }
    ],
    "cascade_description": "The primary error in BoardReader::processFragment() caused data flow to stop from board_reader_01. The EventBuilder, which was waiting for data at input rank 0, reached its 5-second timeout threshold and reported missing sequence IDs 121-130. This triggered an unrecoverable shutdown of the EventBuilder.",
    "clues": [
      {
        "clue_type": "error_pattern",
        "description": "Fragment generator initialization failure suggests the generator was never created or was destroyed before use",
        "source_file": "board_reader_01.log",
        "relevance": "HIGH",
        "suggested_search": "processFragment fragment generator init"
      },
      {
        "clue_type": "timing",
        "description": "323ms between BoardReader error and EventBuilder timeout indicates immediate cascade, not gradual degradation",
        "source_file": "event_builder_01.log",
        "relevance": "MEDIUM",
        "suggested_search": null
      },
      {
        "clue_type": "component_interaction",
        "description": "BoardReader sends fragments to EventBuilder via shared memory (shmem_ds1_br1)",
        "source_file": "event_builder_01.log",
        "relevance": "HIGH",
        "suggested_search": "shmem_ds1_br1 shared memory"
      }
    ]
  }
}
```

---

## 2.3 SourceLocationArtifact

### 1. Purpose & Role

The `SourceLocationArtifact` bridges the gap between log output and source code. When the system finds the source file and line number where an error message string appears in the codebase, it stores that location along with the enclosing function's signature, body, and surrounding context lines. This gives downstream phases the ability to reason about *code structure* rather than just *log text*.

Multiple SourceLocationArtifacts may exist for a single investigation because the same error message string might appear in multiple source files or at multiple call sites. Each artifact receives a `match_score` (0.0-1.0) indicating how confident the system is that this location is the true origin. High-scoring locations (>0.8) receive `priority=Priority.HIGH` automatically.

In the agentic API context, these artifacts represent the code intelligence layer. An MCP client can query them to see exactly where the investigation engine believes the error originates and what the surrounding code looks like.

### 2. Schema

**Inherited base fields** (set to non-default values by `add_source_location()`):

| Field | Type | Value Set | Description |
|-------|------|-----------|-------------|
| `artifact_type` | `ArtifactType` | `ArtifactType.SOURCE_LOCATION` | Fixed discriminator |
| `phase` | `int \| None` | `0` | Always created in Phase 0 |
| `function_name` | `str \| None` | *(from parameter)* | Enclosing function name (used for the function index) |
| `priority` | `Priority` | `Priority.HIGH` if `match_score > 0.8`, else `Priority.NORMAL` | Auto-set based on match confidence |

**Type-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_path` | `str` | *(required)* | Path to the source file containing the match |
| `line_number` | `int` | *(required)* | Line number where the error message or related code appears |
| `matched_line` | `str \| None` | `None` | The actual text of the matched line |
| `match_score` | `float` | `0.0` | Confidence score (0.0-1.0) that this is the true error origin |
| `is_log_statement` | `bool` | `False` | Whether the matched line is a logging macro/function call (e.g., `TLOG_ERROR`, `LOG_ERROR`) |
| `function_signature` | `str \| None` | `None` | Full signature of the enclosing function |
| `function_body` | `str \| None` | `None` | Complete body of the enclosing function |
| `context_before` | `list[str]` | `[]` | Lines of source code immediately before the match |
| `context_after` | `list[str]` | `[]` | Lines of source code immediately after the match |

### 3. Producer

**Phase:** 0 (Archivist)

**Persona:** The `RetrievalOrchestrator` in `srcs/persona/orchestration/retrieval_orchestrator.py` creates these artifacts during Phase 0 prior knowledge retrieval.

**Convenience method:** `WorkBinder.add_source_location(file_path, line_number, created_by, matched_line, match_score, is_log_statement, function_name, function_signature, function_body, context_before, context_after, phase)`

```python
# From srcs/persona/orchestration/retrieval_orchestrator.py
for loc in source_locations[:5]:  # Top 5 locations
    binder.add_source_location(
        file_path=loc.file_path,
        line_number=loc.line_number,
        created_by="Archivist",
        phase=0,
        match_score=loc.match_score or 0.0,
        matched_line=loc.matched_line,
        function_name=loc.function_name,
        function_body=loc.function_body,
        function_signature=loc.function_signature,
        context_before=loc.context_before,
        context_after=loc.context_after,
    )
```

**Production lifecycle:**

1. The `SourceLocator` (from `srcs/extraction/`) searches the configured source repositories for lines matching the error message text
2. Each match is scored based on string similarity, log macro detection, and function context
3. The top 5 matches are stored as individual `SourceLocationArtifact` instances
4. For each location, the orchestrator also creates associated `CallGraphNode`, `FunctionSummaryArtifact`, and `CodeSnippet` artifacts (documented in [Chapter 3](agentic-workbinder-library-ch3-code-artifacts.md))

**Audit logging:** The `add_source_location()` method records an audit entry with `operation_type="store"`, `artifact_type="source_location"`, and `method_name="add_source_location"`.

### 4. Consumers

| Phase | Persona | What It Reads | How It Influences Behavior |
|-------|---------|---------------|---------------------------|
| 1 | Theorist | `file_path`, `function_name`, `function_body`, `match_score` | Uses function/class context for hypothesis generation; high-score locations guide category classification |
| 2 | Detective | `file_path`, `line_number`, `function_name` | Focuses evidence search on this location; uses function name for `function_lookup` queries |
| 3 | Logician | `file_path`, `line_number` | Central point in causal chain -- chain must pass through this location |
| 4 | Devil's Advocate | `file_path`, `line_number`, `function_body` | Verifies that the causal chain leads to this location; checks code against claims |
| 6 | Synthesizer | `file_path`, `line_number`, `match_score`, `function_body` | Reports exact error location in the executive summary; retrieves top 3 locations for code context |

The Synthesizer reads source locations in two places:

```python
# Build source location context for LLM prompt
source_locations = binder.get_source_locations()  # Sorted by match_score descending
for loc in source_locations[:3]:
    # Format as "file.cpp:123 (95% match)"
```

The `BinderSerializer` also reads these artifacts to generate the `SOURCE LOCATIONS FOUND` section of LLM prompts, displaying each location with its match percentage.

### 5. REST API Exposure

**Generic artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=source_location
```

Returns all source location artifacts for the binder, typically 1-5 results.

**Filter by function:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=source_location&function_name=processFragment
```

**Single artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Response JSON snippet:**

```json
{
  "id": "sl-3e7f9a02",
  "artifact_type": "source_location",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:02",
  "updated_at": "2026-02-14T10:30:02",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "high",
  "tags": [],
  "is_deleted": false,
  "content": {
    "file_path": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
    "line_number": 142,
    "matched_line": "TLOG_ERROR(\"BoardReader\") << \"Fragment generator not initialized in processFragment()\";",
    "match_score": 0.95,
    "is_log_statement": true,
    "function_signature": "bool BoardReader_generator::processFragment(artdaq::Fragment& frag)",
    "function_body": "bool BoardReader_generator::processFragment(...) { ... }",
    "context_before": [
      "  // Check generator state before processing",
      "  if (!generator_) {"
    ],
    "context_after": [
      "    return false;",
      "  }"
    ]
  }
}
```

### 6. MCP Tool Access

**Primary tool:** `search_artifacts`

```
search_artifacts(
    binder_id="<id>",
    artifact_type="source_location",
    phase=0
)
```

**Filter by function:**

```
search_artifacts(
    binder_id="<id>",
    artifact_type="source_location",
    function_name="processFragment"
)
```

**Also accessible via:** `get_artifact(binder_id, artifact_id)` for direct retrieval.

### 7. Artifact Relationships

```
ErrorContextArtifact
    |
    |  error_message matched in source
    v
SourceLocationArtifact  <----- match_score ranks candidates
    |
    |  function_name links
    +--------+--------+---------+
    |        |        |         |
    v        v        v         v
CallGraph  Code    Function   Additional
Node       Snippet Summary    SourceLocations
    |                Artifact   (lower score)
    |
    v
Callers / Callees
```

Each `SourceLocationArtifact` is created alongside a constellation of related code knowledge artifacts. The `function_name` field is used as the grouping key in the binder's function index, linking it to:

- `CallGraphNode` -- the call graph centered on the same function
- `CodeSnippet` -- the function body stored as a browsable snippet
- `FunctionSummaryArtifact` -- LLM-generated summaries for the function and its callers/callees

These relationships are implicit (through the shared `function_name`) rather than explicit ID references.

### 8. Session State Mapping

In the agentic REST API, SourceLocationArtifacts represent the **code intelligence results** of the investigation. The client sees them as artifacts with `phase=0` in the binder. They are the primary way the system communicates "where in the code the error comes from" to both downstream personas and external API consumers.

The `GET /binders/{id}/summary` endpoint's `artifact_counts` includes `"source_location": N` showing how many candidate locations were found. A count of 0 indicates the system could not locate the error in source code, which typically leads to lower investigation confidence.

The `BinderSerializer` uses source locations to generate the `SOURCE LOCATIONS FOUND` section visible in the `serialize_for_investigation_start()` output, displaying file paths and match percentages.

### 9. Example

```json
{
  "id": "sl-3e7f9a02",
  "artifact_type": "source_location",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:02.789012",
  "updated_at": "2026-02-14T10:30:02.789012",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "high",
  "tags": [],
  "is_deleted": false,
  "content": {
    "file_path": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
    "line_number": 142,
    "matched_line": "TLOG_ERROR(\"BoardReader\") << \"Fragment generator not initialized in processFragment()\";",
    "match_score": 0.95,
    "is_log_statement": true,
    "function_signature": "bool BoardReader_generator::processFragment(artdaq::Fragment& frag)",
    "function_body": "bool BoardReader_generator::processFragment(artdaq::Fragment& frag) {\n  // Check generator state before processing\n  if (!generator_) {\n    TLOG_ERROR(\"BoardReader\") << \"Fragment generator not initialized in processFragment()\";\n    return false;\n  }\n\n  // Get the next fragment from the generator\n  auto result = generator_->getNext(frag);\n  if (!result) {\n    TLOG_WARNING(\"BoardReader\") << \"getNext returned false, retrying\";\n    return false;\n  }\n\n  ++fragments_processed_;\n  return true;\n}",
    "context_before": [
      "",
      "bool BoardReader_generator::processFragment(artdaq::Fragment& frag) {",
      "  // Check generator state before processing",
      "  if (!generator_) {"
    ],
    "context_after": [
      "    return false;",
      "  }",
      "",
      "  // Get the next fragment from the generator"
    ]
  }
}
```

---

## Summary: Context Artifact Flow

The three context artifacts form a layered description of the investigation's starting point:

```
                           Investigation Request
                                    |
                                    v
                 +------------------------------------------+
                 |          Phase -1 (Chronicler)            |
                 |  (only for multi-file investigations)     |
                 |                                           |
                 |  Produces: LogBundleArtifact              |
                 |    - merged_timeline                      |
                 |    - primary_error                        |
                 |    - clues[] for guided retrieval         |
                 +------------------------------------------+
                                    |
                                    v
                 +------------------------------------------+
                 |          Phase 0 (Archivist)              |
                 |                                           |
                 |  Produces:                                |
                 |    ErrorContextArtifact                   |
                 |      - error_message, context_logs        |
                 |                                           |
                 |    SourceLocationArtifact(s)              |
                 |      - file_path, line_number             |
                 |      - function_body, match_score         |
                 +------------------------------------------+
                                    |
                                    v
                 +------------------------------------------+
                 |     Phases 1-6 (Theorist through         |
                 |                  Synthesizer)             |
                 |                                           |
                 |  All phases READ context artifacts        |
                 |  None WRITE to context artifacts          |
                 +------------------------------------------+
```

Context artifacts are **write-once, read-many**: they are created during the earliest phases and never modified. This immutability is a deliberate design choice that ensures all downstream phases work from the same factual foundation.

---

> **Agentic WorkBinder Library** | [<- Ch. 1: Architecture](agentic-workbinder-library-ch1-architecture.md) | [Table of Contents](agentic-workbinder-library.md) | [Next: Ch. 3: Code Knowledge Artifacts ->](agentic-workbinder-library-ch3-code-artifacts.md)
