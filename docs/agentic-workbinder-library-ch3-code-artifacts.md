> **Agentic WorkBinder Library** | [<- Ch. 2: Context Artifacts](agentic-workbinder-library-ch2-context-artifacts.md) | [Table of Contents](agentic-workbinder-library.md) | [Next: Ch. 4 ->](agentic-workbinder-library-ch4-investigation-artifacts.md)

---

# Chapter 3: Code Knowledge Artifacts

Code knowledge artifacts capture *derived intelligence about source code* that enables personas to reason about function behavior, data flow, and call relationships. Unlike context artifacts (Chapter 2) that record *what happened*, code knowledge artifacts record *how the code works*. They are the investigation engine's memory of the codebase -- extracted once during Phase 0 and referenced by every downstream phase.

Three artifact types make up this category:

1. **CallGraphNode** -- the call graph centered on a function, showing who calls it and what it calls, with optional source bodies and LLM summaries.
2. **CodeSnippet** -- a fragment of source code with file location, language, and optional summary.
3. **FunctionSummaryArtifact** -- a structured, LLM-generated paragraph-level summary of a single function's purpose, mechanism, data flow, error handling, and relevance to the error under investigation.

These three artifacts are always produced together during Phase 0 by the `RetrievalOrchestrator`. For each source location found (see [Chapter 2, Section 2.3](agentic-workbinder-library-ch2-context-artifacts.md#23-sourcelocationartifact)), the orchestrator creates:

- One `CallGraphNode` centered on the function at that location
- One or more `CodeSnippet` artifacts for the function body and related code
- One `FunctionSummaryArtifact` per function in the call graph (center, callers, callees)

```
SourceLocationArtifact
    |
    +--- function_name = "processFragment"
    |
    v
+------------------+     +------------------+     +------------------+
| CallGraphNode    |     | CodeSnippet      |     | FunctionSummary  |
|                  |     |                  |     | Artifact         |
| center_function  |     | file_path        |     |                  |
| callers[]        |     | start_line       |     | purpose          |
| callees[]        |     | end_line         |     | mechanism        |
| diagram          |     | content          |     | data_flow        |
+------------------+     | language         |     | error_paths      |
       |                  | summary          |     | error_line_      |
       |                  +------------------+     |   relevance      |
       |                                           | role             |
       |                                           +------------------+
       v
  CallerInfo[]              CalleeInfo[]
  - caller_name             - callee_name
  - caller_file             - callee_file
  - summary                 - summary
  - body                    - body
```

All three artifact types inherit the common `Artifact` base class. Schema tables below list only type-specific fields; base fields (id, artifact_type, created_by, created_at, updated_at, tags, phase, function_name, priority, is_deleted, deleted_by, deleted_reason) are documented in [Chapter 1](agentic-workbinder-library-ch1-architecture.md).

---

## 3.1 CallGraphNode

### 1. Purpose & Role

The `CallGraphNode` provides structural understanding of the code around an error location. It answers two questions that are central to root cause analysis:

- **Who calls this function?** (callers) -- these are upstream candidates for the root cause. If the error is in `processFragment()`, the caller `start()` might be passing bad data.
- **What does this function call?** (callees) -- these are downstream effects. If `processFragment()` calls `getNext()`, a failure in `getNext()` might propagate back as the observed error.

In the agentic API context, CallGraphNodes give the Theorist structural evidence for hypothesis generation and give the Logician the skeleton of the causal chain. The optional `diagram` field provides an ASCII visualization that can be displayed to users or included in LLM prompts.

Each `CallGraphNode` is associated with a single center function. For an investigation with 3 source locations, there may be 3 separate CallGraphNode artifacts, each centered on a different function.

### 2. Schema

**Inherited base fields** (set to non-default values by `add_call_graph()`):

| Field | Type | Value Set | Description |
|-------|------|-----------|-------------|
| `artifact_type` | `ArtifactType` | `ArtifactType.CALL_GRAPH` | Fixed discriminator |
| `function_name` | `str \| None` | *(same as `center_function`)* | Set to `center_function` for function index grouping |
| `phase` | `int \| None` | `0` | Always created in Phase 0 |

**Type-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `center_function` | `str` | *(required)* | Name of the function at the center of the call graph |
| `callers` | `list[CallerInfo]` | `[]` | Functions that call the center function (upstream) |
| `callees` | `list[CalleeInfo]` | `[]` | Functions that the center function calls (downstream) |
| `depth_explored` | `int` | `1` | How many levels of callers/callees were explored |
| `diagram` | `str \| None` | `None` | ASCII diagram of call relationships |

**Sub-model: `CallerInfo`**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `caller_name` | `str` | *(required)* | Name of the calling function |
| `caller_file` | `str \| None` | `None` | Source file containing the caller |
| `caller_line` | `int \| None` | `None` | Line number where the caller is defined |
| `call_line` | `int \| None` | `None` | Line number where the call to the center function occurs |
| `summary` | `str \| None` | `None` | LLM-generated summary of the caller function |
| `body` | `str \| None` | `None` | Full source code body of the caller function |
| `relationship` | `str \| None` | `None` | Description of how the caller relates to the center function |

**Sub-model: `CalleeInfo`**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `callee_name` | `str` | *(required)* | Name of the called function |
| `callee_file` | `str \| None` | `None` | Source file containing the callee |
| `callee_line` | `int \| None` | `None` | Line number where the callee is defined |
| `callee_signature` | `str \| None` | `None` | Full function signature of the callee |
| `summary` | `str \| None` | `None` | LLM-generated summary of the callee function |
| `body` | `str \| None` | `None` | Full source code body of the callee function |
| `relationship` | `str \| None` | `None` | Description of how the callee relates to the center function |

### 3. Producer

**Phase:** 0 (Archivist)

**Persona:** The `RetrievalOrchestrator` creates CallGraphNode artifacts during Phase 0 prior knowledge retrieval. The `BinderTools.expand_call_graph()` method can also create them dynamically during later phases when a persona uses the tool interface.

**Convenience method:** `WorkBinder.add_call_graph(center_function, callers, callees, created_by, phase, diagram, depth)`

```python
# From srcs/persona/orchestration/retrieval_orchestrator.py
if loc.function_name and (loc.callers or loc.callees):
    binder.add_call_graph(
        center_function=loc.function_name,
        callers=loc.callers or [],
        callees=loc.callees or [],
        created_by="Archivist",
        phase=0,
        diagram=loc.call_graph_diagram,
    )
```

The convenience method converts raw dictionaries into `CallerInfo` and `CalleeInfo` Pydantic models, sets `function_name=center_function` for index grouping, and records an audit log entry.

**BinderTools production path:**

```python
# From srcs/workbinder/tools.py
result = await tools.expand_call_graph("processData", direction="both")
# Internally calls binder.add_call_graph() with extracted callers/callees
```

The `BinderTools.expand_call_graph()` method uses the `CodeIndex` to look up callers and callees, then stores them as a new CallGraphNode. This path is available during any phase when a persona uses the tool interface.

### 4. Consumers

| Phase | Persona | What It Reads | How It Influences Behavior |
|-------|---------|---------------|---------------------------|
| 1 | Theorist | `callers`, `callees`, `center_function` | Identifies upstream causes by examining caller functions; callee failures suggest propagation paths |
| 2 | Detective | `callers`, `callees`, `center_function` | Uses caller/callee function names for `function_lookup` queries; searches callers for evidence of bad input |
| 3 | Logician | `callers`, `callees`, `diagram` | Traces data flow through the call chain to construct causal chain steps; diagram provides visual reference |
| 4 | Devil's Advocate | `callers`, `callees` | Verifies that the causal chain follows actual call graph relationships; challenges chains that skip call levels |
| 6 | Synthesizer | `diagram`, `callers`, `callees` | Includes data flow description in the final report |

The `BinderSerializer` reads CallGraphNodes to generate the `CALL GRAPHS` section of the binder index, showing each graph's center function and caller/callee counts:

```
| CALL GRAPHS (2)
|   [cg-001] processFragment() - 3 callers, 2 callees
|   [cg-002] getNext_() - 1 callers, 4 callees
```

The `serialize_call_graph_detail()` method produces a full text rendering with callers and callees listed individually, including file paths, summaries, and code bodies when available.

### 5. REST API Exposure

**Generic artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=call_graph
```

**Filter by function:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=call_graph&function_name=processFragment
```

**Single artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Response JSON snippet:**

```json
{
  "id": "cg-a1b2c3d4",
  "artifact_type": "call_graph",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:03",
  "updated_at": "2026-02-14T10:30:03",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "center_function": "processFragment",
    "callers": [
      {
        "caller_name": "start",
        "caller_file": "BoardReader_generator.cc",
        "caller_line": 85,
        "call_line": 112,
        "summary": "Entry point that begins fragment processing loop",
        "body": null,
        "relationship": "Direct caller in main processing loop"
      }
    ],
    "callees": [
      {
        "callee_name": "getNext",
        "callee_file": "FragmentGenerator.cc",
        "callee_line": 45,
        "callee_signature": "bool FragmentGenerator::getNext(Fragment& frag)",
        "summary": "Returns next fragment from hardware buffer",
        "body": null,
        "relationship": "Fragment retrieval from hardware interface"
      }
    ],
    "depth_explored": 1,
    "diagram": "        start()\n          |\n          v\n    processFragment()\n          |\n          v\n       getNext()"
  }
}
```

### 6. MCP Tool Access

**Primary tool:** `search_artifacts`

```
search_artifacts(
    binder_id="<id>",
    artifact_type="call_graph",
    function_name="processFragment"
)
```

**Also accessible via:**
- `get_artifact(binder_id, artifact_id)` for direct retrieval by ID
- `search_artifact_content(binder_id, query="processFragment")` for full-text search across all artifact contents

### 7. Artifact Relationships

```
                   SourceLocationArtifact
                   (file_path, line_number,
                    function_name="processFragment")
                            |
                            | function_name link
                            v
                     CallGraphNode
                     center_function="processFragment"
                            |
           +----------------+----------------+
           |                                 |
           v                                 v
     CallerInfo[]                       CalleeInfo[]
     caller_name="start"                callee_name="getNext"
           |                                 |
           v                                 v
  FunctionSummaryArtifact            FunctionSummaryArtifact
  function_name="start"              function_name="getNext"
  role="CALLER"                      role="CALLEE"
  center_function=                   center_function=
    "processFragment"                  "processFragment"
           |                                 |
           v                                 v
     CodeSnippet                        CodeSnippet
     (function body)                    (function body)
```

The CallGraphNode is the hub artifact connecting source locations to function summaries. The relationships are implicit through shared `function_name` values rather than explicit ID references. The `center_function` field on the CallGraphNode matches the `function_name` field on the associated SourceLocationArtifact, and each function in the callers/callees lists may have a corresponding FunctionSummaryArtifact and CodeSnippet.

### 8. Session State Mapping

In the agentic REST API, CallGraphNodes represent the **code structure intelligence** gathered during Phase 0. The `GET /binders/{id}/summary` endpoint's `artifact_counts` includes `"call_graph": N` showing how many function-centered graphs were built.

For MCP clients, the `search_artifacts` tool with `artifact_type="call_graph"` provides the structural context needed to understand function relationships. The `diagram` field, when present, gives a quick visual overview without needing to parse the callers/callees lists.

The `BinderSerializer` includes CallGraphNodes in the binder index shown to personas, making the call structure browsable within LLM prompts.

### 9. Example

```json
{
  "id": "cg-a1b2c3d4",
  "artifact_type": "call_graph",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:03.234567",
  "updated_at": "2026-02-14T10:30:03.234567",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "center_function": "processFragment",
    "callers": [
      {
        "caller_name": "start",
        "caller_file": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
        "caller_line": 85,
        "call_line": 112,
        "summary": "Main entry point for the BoardReader fragment generation loop. Calls processFragment() in a tight loop until stop is requested. Does not check the return value of processFragment() -- assumes success.",
        "body": "void BoardReader_generator::start() {\n  while (!should_stop()) {\n    artdaq::Fragment frag;\n    processFragment(frag);\n    if (frag.dataSize() > 0) {\n      send_fragment(std::move(frag));\n    }\n  }\n}",
        "relationship": "Direct caller in main processing loop"
      },
      {
        "caller_name": "resume",
        "caller_file": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
        "caller_line": 130,
        "call_line": 145,
        "summary": "Resumes fragment generation after a pause. Calls processFragment() to restart data flow.",
        "body": null,
        "relationship": "Resume path caller"
      }
    ],
    "callees": [
      {
        "callee_name": "getNext",
        "callee_file": "artdaq/DAQdata/Globals/FragmentGenerator.cc",
        "callee_line": 45,
        "callee_signature": "bool FragmentGenerator::getNext(artdaq::Fragment& frag)",
        "summary": "Returns the next data fragment from the hardware buffer. Returns false if buffer is empty or generator is in error state. Does not throw exceptions.",
        "body": "bool FragmentGenerator::getNext(artdaq::Fragment& frag) {\n  if (!initialized_) {\n    return false;\n  }\n  // Read from hardware buffer\n  auto data = hw_interface_->read();\n  if (data.empty()) {\n    return false;\n  }\n  frag.setData(data);\n  return true;\n}",
        "relationship": "Fragment retrieval from hardware interface"
      },
      {
        "callee_name": "send_fragment",
        "callee_file": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
        "callee_line": 160,
        "callee_signature": "void BoardReader_generator::send_fragment(artdaq::Fragment&& frag)",
        "summary": "Sends a completed fragment to the downstream EventBuilder via shared memory transport.",
        "body": null,
        "relationship": "Downstream data delivery"
      }
    ],
    "depth_explored": 1,
    "diagram": "    start()          resume()\n      \\                /\n       \\              /\n        v            v\n     processFragment()\n        /           \\\n       /             \\\n      v               v\n  getNext()     send_fragment()"
  }
}
```

---

## 3.2 CodeSnippet

### 1. Purpose & Role

The `CodeSnippet` artifact stores a fragment of source code with precise file location information. It serves as the raw evidence layer for code-based reasoning: when a persona needs to examine actual source code, it reads CodeSnippet artifacts rather than making live filesystem calls.

CodeSnippets differ from the `function_body` field on `SourceLocationArtifact` in scope and purpose. A SourceLocationArtifact stores the function body as context for the *location match*. A CodeSnippet is a standalone, browsable artifact that can represent any code fragment -- a function body, a class definition, or a region of interest -- and carries its own summary and match score.

In the agentic API context, CodeSnippets are the artifacts that get included in LLM prompts when personas need to reason about code. The `BinderSerializer` renders them with syntax-highlighted fenced code blocks for optimal LLM comprehension.

### 2. Schema

**Inherited base fields** (set to non-default values by `add_code_snippet()`):

| Field | Type | Value Set | Description |
|-------|------|-----------|-------------|
| `artifact_type` | `ArtifactType` | `ArtifactType.CODE_SNIPPET` | Fixed discriminator |
| `function_name` | `str \| None` | *(from parameter)* | Set to `snippet_function_name` for function index grouping |
| `phase` | `int \| None` | `0` | Typically created in Phase 0, but can be created in any phase via BinderTools |

**Type-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_path` | `str` | *(required)* | Path to the source file containing the snippet |
| `start_line` | `int` | *(required)* | First line number of the snippet |
| `end_line` | `int` | *(required)* | Last line number of the snippet |
| `content` | `str` | *(required)* | The actual source code text |
| `language` | `str` | `"cpp"` | Programming language (used for syntax highlighting in LLM prompts) |
| `snippet_function_name` | `str \| None` | `None` | Function this snippet belongs to (independent of base `function_name`) |
| `summary` | `str \| None` | `None` | LLM-generated summary of what the code does |
| `match_score` | `float \| None` | `None` | Match score when the snippet came from a source location search |

### 3. Producer

**Phase:** 0 (Archivist) and any phase via BinderTools

**Persona:** The `RetrievalOrchestrator` creates CodeSnippet artifacts during Phase 0 for each source location's function body. The `BinderTools.get_function_source()` and `BinderTools.get_class_definition()` methods can create them dynamically during any phase.

**Convenience method:** `WorkBinder.add_code_snippet(file_path, start_line, end_line, content, created_by, language, function_name, summary, phase, match_score)`

```python
# From srcs/persona/orchestration/retrieval_orchestrator.py
if loc.function_body and loc.function_name:
    binder.add_code_snippet(
        file_path=loc.file_path,
        start_line=loc.line_number,
        end_line=loc.line_number + loc.function_body.count("\n"),
        content=loc.function_body,
        created_by="Archivist",
        phase=0,
        language="cpp",
        function_name=loc.function_name,
    )
```

**BinderTools production path:**

```python
# From srcs/workbinder/tools.py -- get_function_source()
artifact_id = self._binder.add_code_snippet(
    file_path=str(func.file_path),
    start_line=func.start_line,
    end_line=func.end_line,
    content=source,
    created_by=self._persona_name,
    phase=self._current_phase,
    language="cpp",
    function_name=func.name,
)
```

```python
# From srcs/workbinder/tools.py -- get_class_definition()
artifact_id = self._binder.add_code_snippet(
    file_path=str(cls.file_path),
    start_line=cls.start_line,
    end_line=cls.end_line,
    content=source,
    created_by=self._persona_name,
    phase=self._current_phase,
    language="cpp",
    function_name=cls.name,
)
```

**Audit logging:** The `add_code_snippet()` method records an audit entry with `operation_type="store"`, `artifact_type="code_snippet"`, and `method_name="add_code_snippet"`.

### 4. Consumers

| Phase | Persona | What It Reads | How It Influences Behavior |
|-------|---------|---------------|---------------------------|
| 1 | Theorist | `content`, `snippet_function_name` | Analyzes code logic for potential causes; null check presence/absence informs hypothesis generation |
| 2 | Detective | `content`, `file_path`, `start_line` | Examines code for evidence patterns; uses code to validate or refute hypotheses; `get_code_snippets()` called for initial evidence |
| 3 | Logician | `content`, `snippet_function_name` | References specific code in causal chain steps; mechanism descriptions cite line numbers |
| 4 | Devil's Advocate | `content` | Verifies that claims about code behavior match what the actual code does |
| 6 | Synthesizer | `content`, `file_path`, `start_line`, `end_line` | Includes relevant code in the final report; retrieves top 3 snippets for cross-referencing with numeric analysis |

The Synthesizer reads code snippets explicitly:

```python
# From srcs/persona/synthesizer.py
code_snippets = binder.get_code_snippets()
code_context_lines = []
for s in code_snippets[:3]:  # Top 3 snippets
    truncated = s.content[:2000]
    code_context_lines.append(
        f"  {s.file_path}:{s.start_line}-{s.end_line}"
    )
    code_context_lines.append(f"  ```{s.language}\n{truncated}\n  ```")
```

The `BinderSerializer` renders CodeSnippets in the binder index with file location and function name:

```
| CODE SNIPPETS (3)
|   [cs-001] processFragment() body - BoardReader_generator.cc:130-155
|   [cs-002] getNext() body - FragmentGenerator.cc:45-78
|   [cs-003] start() body - BoardReader_generator.cc:85-120
```

And in full detail with fenced code blocks:

```
File: BoardReader_generator.cc
Lines: 130-155
Function: processFragment
```cpp
bool BoardReader_generator::processFragment(...) { ... }
```

### 5. REST API Exposure

**Generic artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=code_snippet
```

**Filter by function:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=code_snippet&function_name=processFragment
```

**Filter by phase** (to distinguish Phase 0 initial snippets from later-phase tool-added snippets):

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=code_snippet&phase=0
```

**Single artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Response JSON snippet:**

```json
{
  "id": "cs-5f8e2a01",
  "artifact_type": "code_snippet",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:04",
  "updated_at": "2026-02-14T10:30:04",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "file_path": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
    "start_line": 130,
    "end_line": 155,
    "content": "bool BoardReader_generator::processFragment(...) { ... }",
    "language": "cpp",
    "snippet_function_name": "processFragment",
    "summary": null,
    "match_score": null
  }
}
```

### 6. MCP Tool Access

**Primary tool:** `search_artifacts`

```
search_artifacts(
    binder_id="<id>",
    artifact_type="code_snippet",
    function_name="processFragment"
)
```

**Full-text search** (useful for finding snippets containing specific code patterns):

```
search_artifact_content(
    binder_id="<id>",
    query="nullptr",
    artifact_types="code_snippet"
)
```

**Also accessible via:** `get_artifact(binder_id, artifact_id)` for direct retrieval.

### 7. Artifact Relationships

```
SourceLocationArtifact
    |
    | function_body extracted as CodeSnippet
    v
CodeSnippet (Phase 0, from RetrievalOrchestrator)
    |
    | function_name grouping
    +---> CallGraphNode (same function_name)
    +---> FunctionSummaryArtifact (same function_name)

BinderTools.get_function_source()
    |
    v
CodeSnippet (Phase N, from persona tool call)
    |
    | references same code as
    v
CallGraphNode.callers[].body / callees[].body
```

CodeSnippets have two relationship patterns:

1. **Phase 0 constellation:** Created alongside SourceLocationArtifact, CallGraphNode, and FunctionSummaryArtifact for the same function. Linked through shared `function_name`.

2. **Tool-driven expansion:** Created by `BinderTools.get_function_source()` or `get_class_definition()` during any phase when a persona needs to examine additional code. These snippets are linked to the requesting persona via `created_by`.

### 8. Session State Mapping

In the agentic REST API, CodeSnippets represent the **code evidence corpus** available to the investigation. The `GET /binders/{id}/summary` endpoint's `artifact_counts` includes `"code_snippet": N` showing how many code fragments have been collected.

A growing count of CodeSnippets across phases indicates active code exploration by personas using the BinderTools interface. Phase 0 snippets represent initial retrieval; later-phase snippets represent tool-driven evidence gathering.

For MCP clients, the `search_artifacts` and `search_artifact_content` tools provide access to code snippets. The `search_artifact_content` tool is particularly useful for finding snippets containing specific code patterns (e.g., searching for `"nullptr"` or `"mutex"` across all code snippets).

### 9. Example

```json
{
  "id": "cs-5f8e2a01",
  "artifact_type": "code_snippet",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:04.567890",
  "updated_at": "2026-02-14T10:30:04.567890",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "file_path": "artdaq/DAQdata/Globals/BoardReader_generator.cc",
    "start_line": 130,
    "end_line": 155,
    "content": "bool BoardReader_generator::processFragment(artdaq::Fragment& frag) {\n  // Check generator state before processing\n  if (!generator_) {\n    TLOG_ERROR(\"BoardReader\") << \"Fragment generator not initialized in processFragment()\";\n    return false;\n  }\n\n  // Get the next fragment from the generator\n  auto result = generator_->getNext(frag);\n  if (!result) {\n    TLOG_WARNING(\"BoardReader\") << \"getNext returned false, retrying\";\n    return false;\n  }\n\n  // Update statistics\n  ++fragments_processed_;\n  last_fragment_time_ = std::chrono::steady_clock::now();\n\n  // Check for fragment size anomalies\n  if (frag.dataSize() == 0) {\n    TLOG_WARNING(\"BoardReader\") << \"Empty fragment received\";\n    ++empty_fragment_count_;\n  }\n\n  return true;\n}",
    "language": "cpp",
    "snippet_function_name": "processFragment",
    "summary": null,
    "match_score": null
  }
}
```

---

## 3.3 FunctionSummaryArtifact

### 1. Purpose & Role

The `FunctionSummaryArtifact` provides LLM-generated, structured intelligence about a single function's behavior. Unlike a `CodeSnippet` that stores raw code, a `FunctionSummaryArtifact` stores *interpreted knowledge* -- what the function does, how it works, how data flows through it, how it handles errors, and how it relates to the error under investigation.

Each summary is organized into five paragraph-level fields designed to give downstream personas enough context to reason about the function without re-reading the raw code:

- **purpose** -- what the function does and why it exists
- **mechanism** -- how it works, key logic and transformations
- **data_flow** -- how data enters and exits the function
- **error_paths** -- error handling and failure modes
- **error_line_relevance** -- how this function relates to the specific error being investigated

The `role` field distinguishes whether the function is a CALLER (upstream of the error function) or CALLEE (downstream), which influences how downstream personas interpret the summary. A CALLER's error paths might explain bad input; a CALLEE's error paths might explain propagated failures.

### 2. Schema

**Inherited base fields** (set to non-default values by `add_function_summary()`):

| Field | Type | Value Set | Description |
|-------|------|-----------|-------------|
| `artifact_type` | `ArtifactType` | `ArtifactType.FUNCTION_SUMMARY` | Fixed discriminator |
| `function_name` | `str \| None` | *(from parameter)* | Name of the summarized function (used for function index grouping) |
| `phase` | `int \| None` | `0` | Always created in Phase 0 |

**Type-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_path` | `str \| None` | `None` | Source file containing the function |
| `purpose` | `str` | *(required)* | What the function does and why it exists |
| `mechanism` | `str` | *(required)* | How it works -- key logic, algorithms, and transformations |
| `data_flow` | `str` | *(required)* | How data enters and exits the function, parameter usage, return values |
| `error_paths` | `str` | *(required)* | Error handling behavior, failure modes, exception paths |
| `error_line_relevance` | `str` | *(required)* | How this function relates to the error line under investigation |
| `center_function` | `str` | *(required)* | The error function this summary relates to (the center of the call graph) |
| `role` | `str` | *(required)* | `"CALLER"` or `"CALLEE"` -- relationship to the center function |

### 3. Producer

**Phase:** 0 (Archivist)

**Persona:** The `RetrievalOrchestrator` creates FunctionSummaryArtifact instances during Phase 0, after building the call graph for each source location. For each function in the call graph (center function, callers, and callees), the orchestrator generates an LLM summary and stores it as a separate artifact.

**Convenience method:** `WorkBinder.add_function_summary(function_name, purpose, mechanism, data_flow, error_paths, error_line_relevance, center_function, role, created_by, phase, file_path)`

```python
# From srcs/persona/orchestration/retrieval_orchestrator.py
for summary_dict in loc.function_summaries:
    # Determine role from the summary
    func_name = summary_dict.get("function_name", "unknown")
    role = "CALLEE"
    if loc.callers:
        for c in loc.callers:
            if c.get("caller_name") == func_name:
                role = "CALLER"
                break

    binder.add_function_summary(
        function_name=func_name,
        purpose=summary_dict.get("purpose", ""),
        mechanism=summary_dict.get("mechanism", ""),
        data_flow=summary_dict.get("data_flow", ""),
        error_paths=summary_dict.get("error_paths", ""),
        error_line_relevance=summary_dict.get(
            "error_line_relevance", ""
        ),
        center_function=loc.function_name or "",
        role=role,
        created_by="Archivist",
        phase=0,
        file_path=loc.file_path,
    )
```

**Audit logging:** The `add_function_summary()` method records an audit entry with `operation_type="store"`, `artifact_type="function_summary"`, and `method_name="add_function_summary"`.

**Production lifecycle:**

1. The `RetrievalOrchestrator` retrieves the call graph for a source location
2. For each function in the graph, it collects the function body (if available)
3. The ArchivistTools / LLM generates a structured summary with the five required fields
4. The orchestrator determines the role (CALLER or CALLEE) by checking against the callers list
5. Each summary is stored as a separate `FunctionSummaryArtifact`

For a typical investigation with one source location and a call graph with 2 callers and 3 callees, this produces 5-6 FunctionSummaryArtifacts (one per function in the graph, possibly including the center function itself).

### 4. Consumers

| Phase | Persona | What It Reads | How It Influences Behavior |
|-------|---------|---------------|---------------------------|
| 1 | Theorist | `purpose`, `error_paths`, `error_line_relevance`, `role` | Uses summaries to understand code behavior without reading raw code; CALLER summaries suggest upstream causes; error paths inform hypothesis categories |
| 2 | Detective | `mechanism`, `data_flow`, `error_paths` | Guides evidence-seeking queries; identifies which functions to look up for additional evidence |
| 3 | Logician | `data_flow`, `mechanism`, `role` | Constructs causal chain steps using data flow descriptions; mechanism descriptions provide the "how X causes Y" |
| 4 | Devil's Advocate | `error_paths`, `error_line_relevance` | Challenges whether the causal chain accounts for all error paths; questions whether the error line relevance assessment is accurate |
| 6 | Synthesizer | `purpose`, `data_flow`, `error_line_relevance` | Builds the root cause narrative and data flow section of the final report |

The `BinderSerializer` renders FunctionSummaryArtifacts in both the binder index and full detail:

**Index rendering:**
```
| FUNCTION SUMMARIES (5)
|   [fs-001] processFragment() [CALLEE] Processes incoming data...
|   [fs-002] start() [CALLER] Entry point that begins...
|   [fs-003] getNext() [CALLEE] Returns next fragment...
```

**Full detail rendering:**
```
Function: processFragment()
Role: CALLEE of start
File: BoardReader_generator.cc
Purpose: Processes incoming data fragments from the hardware buffer...
Mechanism: Checks generator state, calls getNext() to retrieve...
Data Flow: Receives Fragment reference, passes to generator...
Error Paths: Returns false if generator is null...
Error Line Relevance: Contains the exact log statement that...
```

### 5. REST API Exposure

**Generic artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=function_summary
```

**Filter by function:**

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=function_summary&function_name=processFragment
```

This returns the summary for the `processFragment` function itself (if it exists), not summaries *related to* processFragment. To get summaries for callers/callees of processFragment, clients need to read the CallGraphNode first, then query by each caller/callee function name.

**Single artifact endpoint:**

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Response JSON snippet:**

```json
{
  "id": "fs-7c3d9e02",
  "artifact_type": "function_summary",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:05",
  "updated_at": "2026-02-14T10:30:05",
  "phase": 0,
  "function_name": "getNext",
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "file_path": "artdaq/DAQdata/Globals/FragmentGenerator.cc",
    "purpose": "Returns the next data fragment from the hardware buffer...",
    "mechanism": "Checks initialization state, reads from hardware interface...",
    "data_flow": "Receives Fragment reference parameter, populates it with...",
    "error_paths": "Returns false without modifying the fragment if...",
    "error_line_relevance": "Called by processFragment() -- if getNext() returns...",
    "center_function": "processFragment",
    "role": "CALLEE"
  }
}
```

### 6. MCP Tool Access

**Primary tool:** `search_artifacts`

```
search_artifacts(
    binder_id="<id>",
    artifact_type="function_summary",
    function_name="processFragment"
)
```

**Full-text search** (useful for finding summaries mentioning specific concepts):

```
search_artifact_content(
    binder_id="<id>",
    query="null pointer",
    artifact_types="function_summary"
)
```

This searches across the `purpose`, `mechanism`, `data_flow`, `error_paths`, and `error_line_relevance` fields of all FunctionSummaryArtifacts.

**Also accessible via:** `get_artifact(binder_id, artifact_id)` for direct retrieval.

### 7. Artifact Relationships

```
                     CallGraphNode
                     center_function="processFragment"
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
  FunctionSummary   FunctionSummary   FunctionSummary
  Artifact          Artifact          Artifact
  func="start"      func="process     func="getNext"
  role="CALLER"      Fragment"        role="CALLEE"
  center="process    (center func     center="process
   Fragment"          itself, if        Fragment"
                      summarized)
           |                |                |
           v                v                v
     CodeSnippet      CodeSnippet      CodeSnippet
     (function body)  (function body)  (function body)
```

Each `FunctionSummaryArtifact` is semantically linked to:

- **CallGraphNode** -- through the `center_function` field. The summary's `center_function` matches the CallGraphNode's `center_function`, and the summary's `function_name` matches one of the callers/callees listed in the CallGraphNode.
- **CodeSnippet** -- through the shared `function_name`. The summary describes the same function whose body is stored in a CodeSnippet.
- **SourceLocationArtifact** -- indirectly. The center function in the summary relates to a source location found during error message matching.

The `role` field creates a directional relationship: CALLER summaries describe functions upstream of the error, while CALLEE summaries describe functions downstream.

### 8. Session State Mapping

In the agentic REST API, FunctionSummaryArtifacts represent the **LLM-interpreted code intelligence** layer. They sit between raw CodeSnippets (what the code says) and investigation artifacts like HypothesisArtifacts (what the code means for the error).

The `GET /binders/{id}/summary` endpoint's `artifact_counts` includes `"function_summary": N`. A typical investigation produces 3-10 function summaries depending on the call graph size. A count of 0 indicates no call graph was built, usually because the error could not be located in source code.

For MCP clients, FunctionSummaryArtifacts provide a way to understand code behavior without reading raw source. The structured fields (purpose, mechanism, data_flow, error_paths, error_line_relevance) are designed to answer the specific questions that arise during root cause analysis.

### 9. Example

```json
{
  "id": "fs-7c3d9e02",
  "artifact_type": "function_summary",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:30:05.678901",
  "updated_at": "2026-02-14T10:30:05.678901",
  "phase": 0,
  "function_name": "getNext",
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "file_path": "artdaq/DAQdata/Globals/FragmentGenerator.cc",
    "purpose": "Returns the next data fragment from the hardware buffer. This is the primary data retrieval interface used by BoardReader to obtain raw detector data for event building. It serves as the bridge between hardware I/O and the artdaq fragment processing pipeline.",
    "mechanism": "First checks whether the generator has been properly initialized by testing the initialized_ flag. If not initialized, returns false immediately without attempting any hardware access. When initialized, delegates to the hardware interface's read() method to pull raw bytes from the DMA buffer. If the read returns empty data (buffer exhaustion or hardware error), returns false. Otherwise, copies the data into the provided Fragment reference using setData() and returns true.",
    "data_flow": "Input: receives an artdaq::Fragment reference parameter that will be populated with hardware data. The function does not allocate the Fragment -- the caller provides it. Output: returns bool indicating success. On success, the Fragment reference contains valid data with correct header fields. On failure, the Fragment is unmodified. Internal state: reads from hw_interface_ (hardware abstraction layer) and checks initialized_ (set during init() call).",
    "error_paths": "Two failure modes: (1) Generator not initialized -- returns false immediately. This is the likely path when processFragment() encounters the 'Fragment generator not initialized' error, as it means init() was never called or failed silently. (2) Empty hardware read -- returns false when the DMA buffer has no data available. This is a normal transient condition during low-rate periods. Neither failure mode throws exceptions or logs errors -- the caller is expected to handle false returns.",
    "error_line_relevance": "This function is called by processFragment() immediately after the null generator check. If the generator_ pointer is valid but the underlying initialization state (initialized_ flag) is false, getNext() will return false without logging. However, the error in processFragment() occurs BEFORE getNext() is called -- at the null pointer check on generator_ itself. This suggests the issue is not in getNext() but in the generator creation/assignment path.",
    "center_function": "processFragment",
    "role": "CALLEE"
  }
}
```

---

## Summary: Code Knowledge Artifact Constellation

The three code knowledge artifacts form a constellation around each source location found during Phase 0. Together, they provide structural, textual, and interpretive views of the same code:

```
+-------------------------------------------------------------------+
|                    Code Knowledge Constellation                    |
|                    (per source location)                           |
+-------------------------------------------------------------------+
|                                                                   |
|   CallGraphNode                                                   |
|   +-----------+                                                   |
|   | Structure |  WHO calls WHOM?                                  |
|   | View      |  callers[] + callees[] + diagram                  |
|   +-----------+                                                   |
|        |                                                          |
|        +--- per function in graph:                                |
|        |                                                          |
|        |    CodeSnippet                 FunctionSummaryArtifact    |
|        |    +-----------+              +-------------------+      |
|        |    | Raw Code  |              | Interpreted       |      |
|        +--->| View      |              | Knowledge View    |      |
|             |           |              |                   |      |
|             | content   |              | purpose           |      |
|             | language  |              | mechanism         |      |
|             | lines     |              | data_flow         |      |
|             +-----------+              | error_paths       |      |
|                                        | error_line_       |      |
|                                        |   relevance       |      |
|                                        | role (CALLER/     |      |
|                                        |       CALLEE)     |      |
|                                        +-------------------+      |
+-------------------------------------------------------------------+
```

**Data flow through the investigation pipeline:**

```
Phase 0 (Archivist)
    |
    | Produces: CallGraphNode, CodeSnippet, FunctionSummaryArtifact
    |
    v
Phase 1 (Theorist)
    |  READS: CallGraphNode structure for upstream/downstream analysis
    |  READS: FunctionSummaryArtifact for error path reasoning
    |  READS: CodeSnippet for direct code examination
    |
    v
Phase 2 (Detective)
    |  READS: CallGraphNode for function names to look up
    |  READS: CodeSnippet for code pattern evidence
    |  READS: FunctionSummaryArtifact for mechanism understanding
    |  MAY WRITE: additional CodeSnippets via BinderTools
    |
    v
Phase 3 (Logician)
    |  READS: CallGraphNode for data flow tracing
    |  READS: FunctionSummaryArtifact.data_flow for chain step mechanisms
    |
    v
Phase 4 (Devil's Advocate)
    |  READS: CodeSnippet to verify claims match actual code
    |  READS: FunctionSummaryArtifact.error_paths to challenge gaps
    |
    v
Phase 6 (Synthesizer)
    |  READS: CodeSnippet for report code excerpts
    |  READS: FunctionSummaryArtifact for narrative construction
    |  READS: CallGraphNode.diagram for data flow description
    v
```

Code knowledge artifacts are **write-once at Phase 0, read-many throughout the pipeline** (with the exception of CodeSnippets, which can also be created during later phases via BinderTools). Their immutability after creation ensures that all personas work from the same code understanding, and their structured format enables both LLM reasoning and API/MCP access.

---

> **Agentic WorkBinder Library** | [<- Ch. 2: Context Artifacts](agentic-workbinder-library-ch2-context-artifacts.md) | [Table of Contents](agentic-workbinder-library.md) | [Next: Ch. 4 ->](agentic-workbinder-library-ch4-investigation-artifacts.md)
