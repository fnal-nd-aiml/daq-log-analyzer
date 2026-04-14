> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 6](agentic-workbinder-library-ch6-infrastructure-artifacts.md) | [Ch. 8 API Integration & Testing](agentic-workbinder-library-ch8-api-integration.md)

---

# Chapter 7: Tools, Serialization & Parsing

The WorkBinder provides three surface-area layers beyond the core container: **BinderTools** exposes LLM-invokable methods for persona interaction, **BinderSerializer** converts binder state into token-budgeted prompt text, and the **Parser Subsystem** converts raw LLM responses back into domain models and artifacts. Together these layers form the read-write contract between the investigation pipeline and the binder.

This chapter documents every public method in each layer, the JSON utility functions that underpin parser robustness, and the BinderStore persistence API that makes the entire artifact graph durable.

---

## 7.1 BinderTools API

**Source:** `srcs/workbinder/tools.py` (654 lines)

`BinderTools` is the primary interface that personas use to interact with the work binder during investigation. It wraps the raw `WorkBinder` container with persona-scoped context (who is calling, what phase they are in) and adds code-index-backed navigation.

### 7.1.1 Constructor

```python
class BinderTools:
    def __init__(
        self,
        binder: WorkBinder,
        code_index: "CodeIndex | None" = None,
        persona_name: str = "system",
        current_phase: int | None = None,
    )
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `binder` | `WorkBinder` | The work binder instance to operate on |
| `code_index` | `CodeIndex \| None` | Optional code index for source lookups. When `None`, code navigation methods return error dicts. |
| `persona_name` | `str` | Name of the persona using these tools. Automatically stamped on every artifact created. |
| `current_phase` | `int \| None` | Current investigation phase number (0-7). Attached to artifacts for phase-based queries. |

The constructor stores these values as private instance attributes (`_binder`, `_index`, `_persona`, `_phase`). All tool methods are `async` to maintain consistency with the async architecture, even when the underlying operation is synchronous.

### 7.1.2 Call Graph Tools

#### `expand_call_graph()`

```python
async def expand_call_graph(
    self,
    function_name: str,
    direction: str = "both",
    depth: int = 1,
    max_body_chars: int = 0,
) -> dict[str, Any]
```

Expands the call graph around a function and adds the result to the binder as a `CallGraphNode` artifact.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `function_name` | `str` | -- | The function to center the graph on |
| `direction` | `str` | `"both"` | `"callers"`, `"callees"`, or `"both"` |
| `depth` | `int` | `1` | Depth to explore (passed to artifact but not used for recursive expansion) |
| `max_body_chars` | `int` | `0` | Maximum characters for included function bodies (0 = no truncation) |

**Behavior:**

1. Queries the `CodeIndex` for callers and/or callees (limited to 5 each).
2. For the first 3 callers/callees, retrieves function bodies and truncates them to `max_body_chars` using `_truncate_body()` (keeps first and last half with a `... [truncated] ...` marker).
3. For callees, also retrieves function signatures via `find_function()`.
4. Generates an ASCII diagram via `_generate_diagram()` showing the call relationships.
5. Adds a `CallGraphNode` artifact to the binder via `binder.add_call_graph()`.

**Returns:**

```json
{
  "artifact_id": "cg-abc123",
  "center_function": "processData",
  "callers": [
    {
      "caller_name": "handleRequest",
      "caller_file": "handler.cpp",
      "call_line": 42,
      "relationship": "passes data TO processData",
      "body": "void handleRequest() { ... }"
    }
  ],
  "callees": [
    {
      "callee_name": "validateBuffer",
      "callee_file": "validate.cpp",
      "callee_signature": "bool validateBuffer(const void*, size_t)",
      "relationship": "receives data FROM processData",
      "body": "bool validateBuffer(...) { ... }"
    }
  ],
  "diagram": "... ASCII call graph diagram ..."
}
```

If no code index is available, returns `{"error": "No code index available"}`.

#### `get_caller_body()`

```python
async def get_caller_body(self, caller_name: str) -> dict[str, Any]
```

Convenience wrapper that delegates to `get_function_source(caller_name)`. Returns the same dictionary format as `get_function_source()`.

#### `get_callee_body()`

```python
async def get_callee_body(self, callee_name: str) -> dict[str, Any]
```

Convenience wrapper that delegates to `get_function_source(callee_name)`.

### 7.1.3 Code Navigation Tools

#### `get_function_source()`

```python
async def get_function_source(
    self, function_name: str, add_to_binder: bool = True
) -> dict[str, Any]
```

Retrieves the full source code for a function from the code index.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `function_name` | `str` | -- | Name of the function to look up |
| `add_to_binder` | `bool` | `True` | Whether to create a `CodeSnippet` artifact |

**Returns:**

```json
{
  "name": "processData",
  "file_path": "/src/core.cpp",
  "start_line": 100,
  "end_line": 150,
  "signature": "void processData(const Fragment& frag)",
  "source": "void processData(...) { ... }",
  "artifact_id": "cs-def456"
}
```

The `artifact_id` field is only present when `add_to_binder=True` and source code is found. Returns `{"error": "Function not found: ..."}` when the function is not in the index.

#### `get_class_definition()`

```python
async def get_class_definition(
    self, class_name: str, add_to_binder: bool = True
) -> dict[str, Any]
```

Retrieves a class definition with method listing.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `class_name` | `str` | -- | Name of the class to look up |
| `add_to_binder` | `bool` | `True` | Whether to create a `CodeSnippet` artifact |

**Returns:**

```json
{
  "name": "FragmentReceiver",
  "file_path": "/src/fragment_receiver.hh",
  "start_line": 10,
  "end_line": 85,
  "base_classes": ["CommandableFragmentGenerator"],
  "methods": ["start", "stop", "getNext_"],
  "source": "class FragmentReceiver : public ... { ... }",
  "artifact_id": "cs-ghi789"
}
```

#### `search_code()`

```python
async def search_code(
    self, pattern: str, file_filter: str | None = None, limit: int = 10
) -> list[dict[str, Any]]
```

Searches the code index for functions matching a pattern.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | `str` | -- | Search pattern (supports wildcards) |
| `file_filter` | `str \| None` | `None` | Optional file path filter |
| `limit` | `int` | `10` | Maximum results to return |

**Returns:** A list of match summaries (without source bodies):

```json
[
  {
    "name": "processData",
    "file_path": "/src/core.cpp",
    "start_line": 100,
    "end_line": 150,
    "signature": "void processData(const Fragment& frag)"
  }
]
```

Note: This method does **not** add artifacts to the binder. It is a read-only search.

### 7.1.4 Finding and Annotation Tools

#### `add_finding()`

```python
async def add_finding(
    self,
    finding_type: str,
    content: str,
    related_artifacts: list[str] | None = None,
    confidence: float = 0.5,
    tags: list[str] | None = None,
) -> str
```

Adds a `Finding` artifact to the binder. The persona name and phase are automatically populated from the tool's constructor arguments.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `finding_type` | `str` | -- | One of: `observation`, `question`, `conclusion`, `warning`, `recommendation` |
| `content` | `str` | -- | The finding text |
| `related_artifacts` | `list[str] \| None` | `None` | IDs of related artifacts |
| `confidence` | `float` | `0.5` | Confidence level (0.0-1.0) |
| `tags` | `list[str] \| None` | `None` | Tags for categorization |

**Returns:** The artifact ID string.

#### `annotate_artifact()`

```python
async def annotate_artifact(
    self,
    artifact_id: str,
    annotation_type: str,
    content: str,
) -> str
```

Adds an `Annotation` artifact linked to an existing artifact.

| Parameter | Type | Description |
|-----------|------|-------------|
| `artifact_id` | `str` | ID of the artifact to annotate |
| `annotation_type` | `str` | One of: `comment`, `highlight`, `question`, `correction` |
| `content` | `str` | The annotation text |

**Returns:** The annotation artifact ID string.

### 7.1.5 CRUD Tools

#### `add_artifact()`

```python
async def add_artifact(
    self,
    artifact_type: str,
    content: dict[str, Any],
    tags: list[str] | None = None,
    priority: str = "normal",
    function_name: str | None = None,
) -> str
```

Generic artifact creation. Currently supports `CODE_SNIPPET` and `FINDING` types. Other types raise `ValueError`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artifact_type` | `str` | -- | The `ArtifactType` value string |
| `content` | `dict` | -- | Artifact-specific content fields |
| `tags` | `list[str] \| None` | `None` | Tags |
| `priority` | `str` | `"normal"` | Priority level |
| `function_name` | `str \| None` | `None` | Related function name |

For `code_snippet`, content must include: `file_path`, `start_line`, `end_line`, `content`.
For `finding`, content must include: `content`, and optionally `finding_type` (defaults to `"observation"`) and `confidence` (defaults to `0.5`).

#### `update_artifact()`

```python
async def update_artifact(
    self, artifact_id: str, updates: dict[str, Any]
) -> bool
```

Updates fields on an existing artifact. Delegates to `binder.update_artifact()` with the current persona name.

**Returns:** `True` if the artifact was found and updated, `False` if not found.

#### `mark_deleted()`

```python
async def mark_deleted(
    self, artifact_id: str, reason: str | None = None
) -> bool
```

Soft-deletes an artifact. The artifact remains in the binder but is flagged as deleted with the current persona name and optional reason.

**Returns:** `True` if deleted, `False` if not found.

#### `restore_artifact()`

```python
async def restore_artifact(self, artifact_id: str) -> bool
```

Restores a soft-deleted artifact.

**Returns:** `True` if restored, `False` if not found.

### 7.1.6 Query Tools

#### `get_artifact()`

```python
async def get_artifact(self, artifact_id: str) -> dict[str, Any] | None
```

Retrieves the full content of an artifact by ID, returned as a Pydantic `model_dump()` dictionary. Returns `None` if not found.

#### `list_artifacts()`

```python
async def list_artifacts(
    self,
    artifact_type: str | None = None,
    created_by: str | None = None,
    tags: list[str] | None = None,
    phase: int | None = None,
    function_name: str | None = None,
    include_deleted: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]
```

Lists artifacts with optional filters. Constructs a `BinderQuery` and returns summary dictionaries containing: `id`, `artifact_type`, `created_by`, `created_at`, `phase`, `function_name`, `priority`, `tags`, `is_deleted`.

Tags filter uses AND logic -- all specified tags must match.

#### `search_binder()`

```python
async def search_binder(
    self,
    query: str,
    artifact_types: list[str] | None = None,
) -> list[dict[str, Any]]
```

Full-text search across artifact contents. Performs a case-insensitive substring match on the JSON-serialized content of each non-deleted artifact. Results are limited to 50.

**Returns:** List of matching artifact summaries with `id`, `artifact_type`, `created_by`, and `function_name`.

#### `get_related_artifacts()`

```python
async def get_related_artifacts(self, artifact_id: str) -> list[dict[str, Any]]
```

Returns artifacts related to the given one (via the binder's `get_related_artifacts()` method). Returns summary dictionaries.

#### `get_artifact_history()`

```python
async def get_artifact_history(self, artifact_id: str) -> list[dict[str, Any]]
```

Returns the modification history for an artifact. Each history record contains: `id`, `modified_by`, `modified_at`, `action`, `changes`.

### 7.1.7 Statistics

#### `get_binder_stats()`

```python
async def get_binder_stats(self) -> dict[str, Any]
```

Returns aggregate statistics about the binder:

```json
{
  "binder_id": "binder-abc123",
  "investigation_id": "inv-456",
  "status": "active",
  "artifact_counts": {"call_graph": 3, "finding": 12, "code_snippet": 5},
  "total_artifacts": 20,
  "unique_tags": ["error-path", "timing", "configuration"],
  "tag_count": 3
}
```

---

## 7.2 BinderSerializer

**Source:** `srcs/workbinder/serializer.py` (506 lines)

`BinderSerializer` converts work binder state into formatted text suitable for inclusion in LLM prompts. It implements token budgeting, persona-aware prioritization, and browsable artifact indices.

### 7.2.1 Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `CHARS_PER_TOKEN` | `4` | Conservative estimate for token-to-character conversion |

### 7.2.2 Primary Serialization: `serialize_for_prompt()`

```python
def serialize_for_prompt(
    self,
    binder: WorkBinder,
    persona: str | None = None,
    max_tokens: int = 4000,
    focus_artifacts: list[str] | None = None,
    include_tool_instructions: bool = True,
    include_index: bool = True,
    include_recent_findings: bool = True,
) -> str
```

Creates a smart summary of binder state for an LLM prompt. This is the primary serialization method used by the investigation pipeline.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binder` | `WorkBinder` | -- | The work binder to serialize |
| `persona` | `str \| None` | `None` | Current persona name (for prioritization and filtering) |
| `max_tokens` | `int` | `4000` | Maximum tokens for output (converted to chars via `CHARS_PER_TOKEN`) |
| `focus_artifacts` | `list[str] \| None` | `None` | Specific artifact IDs to include in full detail |
| `include_tool_instructions` | `bool` | `True` | Whether to include tool usage documentation |
| `include_index` | `bool` | `True` | Whether to include the browsable artifact index |
| `include_recent_findings` | `bool` | `True` | Whether to include recent findings from other personas |

**Prioritization Order:**

1. Focused artifacts (always included in full detail)
2. Artifact index (browsable directory)
3. Recent findings from other personas (excludes current persona)
4. Tool usage instructions

**Token Budget Strategy:**

The output is assembled from parts in priority order. If the concatenated result exceeds `max_tokens * CHARS_PER_TOKEN` characters, it is truncated with a `... (truncated for length)` marker. The budget is calculated as:

```
max_chars = max_tokens * 4  # e.g., 4000 tokens = 16000 chars
```

### 7.2.3 Investigation Start: `serialize_for_investigation_start()`

```python
def serialize_for_investigation_start(
    self, binder: WorkBinder, max_tokens: int = 2000
) -> str
```

Creates a minimal summary suitable for early investigation phases (Phase 0). Includes:

1. **Error Context Summary** -- error message, component, and function from the first `ErrorContextArtifact`
2. **Source Locations Summary** -- top 3 source locations with match percentages
3. **Binder Contents** -- artifact type counts

This produces output like:

```
ERROR UNDER INVESTIGATION:
  Message: Timeout waiting for fragment from BoardReader_01
  Component: EventBuilder
  Function: getNext_

SOURCE LOCATIONS FOUND (3):
  - /src/fragment_receiver.cc:482 (92% match)
  - /src/event_builder.cc:315 (67% match)
  - /src/board_reader.cc:201 (45% match)

BINDER CONTENTS:
  - call_graph: 2
  - code_snippet: 5
  - source_location: 3
```

### 7.2.4 Per-Artifact-Type Serializers

#### `serialize_call_graph_detail()`

```python
def serialize_call_graph_detail(self, call_graph: CallGraphNode) -> str
```

Serializes a `CallGraphNode` with full detail including:

- Callers with file paths, summaries, and source bodies (in cpp code blocks)
- Callees with file paths, signatures, summaries, and source bodies

Each caller/callee is numbered and indented for readability.

### 7.2.5 Internal Methods

#### `_generate_index()`

Generates the browsable artifact index. Groups artifacts by type and produces a formatted table with:

| Artifact Type | Index Entry Format |
|---------------|-------------------|
| `CALL_GRAPH` | `[id] function() - N callers, M callees` |
| `CODE_SNIPPET` | `[id] function() body - file:start-end` |
| `FINDING` | `[id] [persona] content_preview...` |
| `SOURCE_LOCATION` | `[id] file:line - primary/secondary match (N%)` |
| `FUNCTION_SUMMARY` | `[id] function() [role] purpose_preview...` |
| `ERROR_CONTEXT` | `[id] error_message_preview...` |

Each type section shows up to 5 items with a `... (N more)` indicator for overflow.

#### `_serialize_focused_artifacts()`

Renders specific artifacts in full detail. Each artifact type has its own rendering format:

- **CallGraphNode**: Center function, diagram (or caller/callee counts)
- **CodeSnippet**: File path, line range, function name, source in code block
- **Finding**: Type, persona, confidence percentage, content
- **SourceLocationArtifact**: File, line, match score percentage, matched line
- **FunctionSummaryArtifact**: Function name, role, file, purpose, mechanism, data flow, error paths, error line relevance

#### `_serialize_recent_findings()`

Serializes the most recent findings from other personas (excludes the current persona). Sorted by creation time (newest first), limited to 5 entries. Format:

```
- [finding-id] [Phase N] [Theorist] (observation): Content preview (80 chars)...
```

#### `_get_tool_instructions()`

Returns a static string documenting the available binder tools, organized by operation category: READ, WRITE, UPDATE, DELETE. This text is included at the end of the serialized prompt to give the LLM context about available operations.

---

## 7.3 Parser Subsystem

**Source:** `srcs/workbinder/artifacts/parsers/` (11 files)

The parser subsystem provides a unified library for parsing LLM responses into domain models and WorkBinder artifacts. It consolidates scattered parsing logic into a single, reusable location with a consistent two-stage conversion pattern.

### 7.3.1 BaseParser ABC

**Source:** `srcs/workbinder/artifacts/parsers/base.py`

```python
class BaseParser(ABC, Generic[LLMResponseT, DomainModelT, ArtifactT]):
```

The abstract base class defines three type parameters and three abstract methods:

| Type Parameter | Bound | Description |
|----------------|-------|-------------|
| `LLMResponseT` | `BaseModel` | Pydantic model for the raw LLM response |
| `DomainModelT` | (any) | Domain model used by the investigation pipeline |
| `ArtifactT` | `Artifact` | WorkBinder artifact for persistence |

| Abstract Method | Signature | Purpose |
|-----------------|-----------|---------|
| `parse_llm_response` | `(raw_json: str) -> LLMResponseT` | Parse raw JSON into response model |
| `to_domain_model` | `(item: Any, **context) -> DomainModelT` | Convert response item to domain model |
| `to_artifact` | `(domain_model: Any, created_by: str, phase: int, **kwargs) -> ArtifactT` | Convert domain model to artifact |

### 7.3.2 Two-Stage Conversion Pattern

All parsers implement the same data flow:

```
LLM Response JSON (raw string)
       |
       v  parse_llm_response()
LLM Response Model (HypothesisResponse, QueryResponse, etc.)
       |
       v  to_domain_model()
Domain Model (Hypothesis, dict, CausalChain, Challenge, InvestigationConclusion)
       |
       v  to_artifact()
WorkBinder Artifact (HypothesisArtifact, EvidenceArtifact, etc.)
```

This separation:
1. Maintains backward compatibility with existing agent code that uses domain models
2. Preserves LLM response fields that were previously discarded (category, evidence designs)
3. Handles field name mapping between LLM output format and domain conventions
4. Enables artifact storage without changing agent logic

### 7.3.3 HypothesisParser

**Source:** `srcs/workbinder/artifacts/parsers/hypothesis.py`

```python
class HypothesisParser(BaseParser[HypothesisResponse, Hypothesis, HypothesisArtifact])
```

Parses Phase 1 hypothesis generation output.

**LLM Response Model:**

```python
class HypothesisItem(BaseModel):
    description: str
    category: str
    prior: float
    confirming_evidence: str = ""
    refuting_evidence: str = ""

class HypothesisResponse(BaseModel):
    hypotheses: List[HypothesisItem]
```

**Key Method: `to_domain_model()`**

```python
def to_domain_model(
    self,
    item: HypothesisItem,
    source_prefix: str = "fresh",
    max_prior: float | None = None,
    **context: object,
) -> Hypothesis
```

- Incorporates category into source as `"source_prefix:category"` (e.g., `"fresh:timing"`)
- Caps prior probability at `max_prior` if provided
- Preserves `confirming_evidence` and `refuting_evidence` on the domain model for downstream use

**Key Method: `to_artifact()`**

```python
def to_artifact(
    self,
    domain_model: Hypothesis,
    created_by: str,
    phase: int,
    rank: int = 0,
    llm_request_id: str | None = None,
    **kwargs: object,
) -> HypothesisArtifact
```

Converts the domain model to a `HypothesisArtifact`, including the extended fields (`category`, `confirming_evidence`, `refuting_evidence`) that were previously lost during parsing.

**Convenience Method: `parse_and_convert()`**

```python
def parse_and_convert(
    self,
    raw_json: str,
    source_prefix: str = "fresh",
    max_prior: float | None = None,
    exclude_descriptions: set[str] | None = None,
) -> list[Hypothesis]
```

Combines parse and convert in one step, with optional deduplication via `exclude_descriptions`.

### 7.3.4 EvidenceQueryParser

**Source:** `srcs/workbinder/artifacts/parsers/evidence.py`

```python
class EvidenceQueryParser(BaseParser[QueryResponse, dict[str, Any], EvidenceArtifact])
```

Parses Phase 2 evidence seeking output. Unlike other parsers, the domain model is a plain dictionary (query specification) rather than a Pydantic model, because queries are executed as dicts rather than being stored directly.

**LLM Response Model:**

```python
class QueryItem(BaseModel):
    query_type: str           # log_search, function_lookup, etc.
    query: str                # Query string or pattern
    targets_hypothesis_id: str = ""
    expected_if_true: str = ""
    expected_if_false: str = ""
    full_source: bool = False

class QueryResponse(BaseModel):
    queries: List[QueryItem]
```

**Key Method: `to_domain_model()`**

Converts `QueryItem` to a dictionary via `item.model_dump()`, producing a query specification ready for execution by the evidence seeker.

**Key Method: `to_artifact()`**

Takes an `EvidenceItem` (the result of query execution, not the query itself) and converts it to an `EvidenceArtifact`. Preserves targeting fields (`targets_hypothesis_id`, `expected_if_true`, `expected_if_false`) for counterfactual scoring.

**Convenience Method: `parse_to_queries()`**

```python
def parse_to_queries(self, raw_json: str) -> list[dict[str, Any]]
```

Parses LLM response directly to a list of query dictionaries.

### 7.3.5 CausalChainParser

**Source:** `srcs/workbinder/artifacts/parsers/causal_chain.py`

```python
class CausalChainParser(BaseParser[ChainResponse, CausalChain, CausalChainArtifact])
```

Parses Phase 3 causal chain construction output with field mapping.

**LLM Response Model:**

```python
class ChainStepItem(BaseModel):
    claim: str
    mechanism: str = ""
    evidence: List[str] = []    # NOTE: maps to evidence_ids in domain model
    is_assumption: bool = False

class ChainResponse(BaseModel):
    steps: List[ChainStepItem]
```

**Field Mapping:**

| LLM Field | Domain Field | Notes |
|-----------|-------------|-------|
| `evidence` | `evidence_ids` | LLM uses "evidence", domain model uses "evidence_ids" |

**Key Method: `to_domain_model()`**

```python
def to_domain_model(
    self,
    item: ChainResponse,
    hypothesis_id: str = "",
    **context: object,
) -> CausalChain
```

Note that this method takes the entire `ChainResponse` (not individual items) because a causal chain is a single entity composed of multiple steps. Each step's `evidence` field is mapped to `evidence_ids`.

**Key Method: `to_artifact()`**

Converts steps to dict format for artifact storage, preserving `step_order`, `claim`, `mechanism`, `evidence_ids`, `is_assumption`, `assumption_note`, and `evidence_strength` per step. Transfers `logical_validity` and `evidence_coverage` metrics from the domain model.

**Utility Method: `step_item_to_causal_step()`**

Converts a single `ChainStepItem` to a `CausalStep` domain model, useful for incremental chain building.

### 7.3.6 ChallengeParser

**Source:** `srcs/workbinder/artifacts/parsers/challenge.py`

```python
class ChallengeParser(BaseParser[ChallengeResponse, Challenge, ChallengeArtifact])
```

Parses Phase 4 adversarial review output with field normalization.

**LLM Response Model:**

```python
class ChallengeItem(BaseModel):
    type: str           # NOTE: maps to challenge_type in domain model
    content: str
    severity: str = "MEDIUM"

class ChallengeResponse(BaseModel):
    challenges: List[ChallengeItem]
```

**Field Mapping:**

| LLM Field | Domain Field | Notes |
|-----------|-------------|-------|
| `type` | `challenge_type` | LLM uses "type", domain uses "challenge_type" |
| `"missing"` | `"missing_evidence"` | Value normalization for challenge type |

**Key Method: `to_domain_model()`**

Normalizes the `type` field (mapping `"missing"` to `"missing_evidence"`) and sets `requires_response = True` for `HIGH` severity challenges.

**Key Method: `to_artifact()`**

```python
def to_artifact(
    self,
    domain_model: Challenge,
    created_by: str,
    phase: int,
    target_hypothesis_id: str = "",
    llm_request_id: str | None = None,
    **kwargs: object,
) -> ChallengeArtifact
```

Requires `target_hypothesis_id` to link the challenge to the hypothesis being challenged. Preserves resolution state (`resolved`, `resolution`) from the domain model.

**Convenience Method: `parse_and_convert()`**

```python
def parse_and_convert(self, raw_json: str) -> list[Challenge]
```

### 7.3.7 ConclusionParser

**Source:** `srcs/workbinder/artifacts/parsers/conclusion.py`

```python
class ConclusionParser(
    BaseParser[ConclusionResponse, InvestigationConclusion, ConclusionArtifact]
)
```

Parses Phase 6 synthesis output with rich structured fields.

**LLM Response Model:**

```python
class SubCauseItem(BaseModel):
    description: str
    probability: float = 0.0
    evidence_summary: str = ""

class KeyFileItem(BaseModel):
    file_path: str
    purpose: str
    line_range: str | None = None

class ConclusionItem(BaseModel):
    root_cause: str
    confidence: float = 0.0
    caveats: List[str] = []
    code_snippet: str = ""
    code_location: str = ""
    sub_causes: List[SubCauseItem] = []
    data_flow: str = ""
    key_files: List[KeyFileItem] = []
    debugging_steps: List[str] = []

class ConclusionResponse(BaseModel):
    conclusion: ConclusionItem
```

**Key Method: `to_domain_model()`**

```python
def to_domain_model(
    self,
    item: ConclusionItem,
    calibrated_confidence: float | None = None,
    **context: Any,
) -> InvestigationConclusion
```

Converts the conclusion item to an `InvestigationConclusion`, constructing a `CalibratedConfidence` object with both raw and calibrated values. Sub-causes are converted to `SubCause` domain models, key files to `KeyFile` models.

**Key Method: `to_artifact()`**

```python
def to_artifact(
    self,
    domain_model: InvestigationConclusion,
    created_by: str,
    phase: int,
    outcome: str = "CONFIDENT",
    llm_request_id: str | None = None,
    **kwargs: Any,
) -> ConclusionArtifact
```

The `outcome` parameter accepts one of: `CONFIDENT`, `PROBABLE`, `UNCERTAIN`, `CONTRADICTORY`, `INSUFFICIENT`.

### 7.3.8 Parser Coverage Summary

| Parser | Phase | LLM Response Model | Domain Model | Artifact Type |
|--------|-------|-------------------|--------------|---------------|
| `HypothesisParser` | 1 | `HypothesisResponse` | `Hypothesis` | `HypothesisArtifact` |
| `EvidenceQueryParser` | 2 | `QueryResponse` | `dict[str, Any]` | `EvidenceArtifact` |
| `CausalChainParser` | 3 | `ChainResponse` | `CausalChain` | `CausalChainArtifact` |
| `ChallengeParser` | 4 | `ChallengeResponse` | `Challenge` | `ChallengeArtifact` |
| `ConclusionParser` | 6 | `ConclusionResponse` | `InvestigationConclusion` | `ConclusionArtifact` |
| `MergedTimelineParser` | -1 | -- | -- | `MergedTimelineArtifact` |
| `LogBundleParser` | -1 | -- | -- | `LogBundleArtifact` |
| `BoardReaderIdentificationParser` | -1 | -- | -- | `BoardReaderIdentificationArtifact` |

Infrastructure artifacts (`InvestigationStateArtifact`, `PhaseStateArtifact`, `FlowConfigArtifact`, `LLMRequestArtifact`, `LLMResponseArtifact`, `ErrorContextArtifact`, `SourceLocationArtifact`, `CallGraphNode`, `CodeSnippet`, `Finding`, `Annotation`, `PersonaContributionArtifact`) are created programmatically and do not need parsers.

---

## 7.4 JSON Utilities

**Source:** `srcs/workbinder/artifacts/parsers/json_utils.py` (305 lines)

The JSON utilities provide robust extraction and repair for LLM output, which is frequently malformed. These functions are used by all parsers and also imported directly by LLM providers.

### 7.4.1 `extract_json()`

```python
def extract_json(response: str) -> str
```

Extracts JSON from LLM response text. Tries extraction strategies in order:

1. **Markdown code blocks** -- looks for `` ```json ... ``` `` first, then generic `` ``` ... ``` ``
2. **Regex extraction** -- searches for JSON objects `{...}` or arrays `[...]`
3. **Raw passthrough** -- returns the input as-is if no JSON structure is found

**Example:**

```python
>>> response = '''Here's the analysis:
... ```json
... {"result": "success"}
... ```
... '''
>>> extract_json(response)
'{"result": "success"}'
```

### 7.4.2 `fix_json()`

```python
def fix_json(json_str: str) -> str
```

Applies a multi-pass repair pipeline to fix common JSON formatting issues:

| Pass | Operation | Example |
|------|-----------|---------|
| Pass 1 | Remove trailing commas before `}` and `]` | `[1, 2, 3,]` -> `[1, 2, 3]` |
| Pass 1 | Quote unquoted property names | `{name: "test"}` -> `{"name": "test"}` |
| Pass 2 | Convert single quotes to double quotes | `{'key': 'val'}` -> `{"key": "val"}` |
| Pass 3 | Repair truncation (balance braces/brackets) | `{"items": [1, 2` -> `{"items": [1, 2]}` |
| Pass 4 | Remove JavaScript-style comments | `{"a": 1 // comment}` -> `{"a": 1 }` |

**Internal Functions:**

| Function | Purpose |
|----------|---------|
| `_convert_single_quotes(json_str)` | State-machine-based single-to-double quote conversion that handles escape sequences |
| `_repair_truncation(json_str)` | Counts unbalanced braces/brackets (ignoring those inside strings) and appends missing closers |
| `_remove_comments(json_str)` | Removes `/* ... */` block comments and `// ...` line comments (respecting string context) |

### 7.4.3 `parse_json_response()`

```python
def parse_json_response(
    response: str,
    model: type[T],
    fix_on_error: bool = True,
) -> T
```

The primary entry point for parsing LLM output. Combines extraction, validation, and repair:

1. Calls `extract_json()` to extract JSON from the raw response
2. Attempts `model.model_validate_json(json_str)` for direct Pydantic parsing
3. On failure (if `fix_on_error=True`), calls `fix_json()` and retries
4. Raises `ValueError` if parsing fails even after fixing

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `response` | `str` | -- | Raw LLM response text |
| `model` | `type[T]` | -- | Pydantic model class to parse into |
| `fix_on_error` | `bool` | `True` | Whether to attempt JSON repair on parse failure |

**Example:**

```python
class Result(BaseModel):
    items: list[str]

result = parse_json_response(
    '```json\n{"items": ["a", "b"]}\n```',
    Result
)
# result.items == ["a", "b"]
```

### 7.4.4 Common LLM Output Issues Handled

| Issue | Frequency | Handling |
|-------|-----------|---------|
| JSON wrapped in markdown code blocks | Very common | `extract_json()` strips block markers |
| Trailing commas in arrays/objects | Common | `fix_json()` pass 1 removes them |
| Unquoted property names | Common | `fix_json()` pass 1 adds quotes |
| Single quotes instead of double quotes | Occasional | `fix_json()` pass 2 converts them |
| Truncated JSON (token limit hit) | Occasional | `fix_json()` pass 3 appends missing closers |
| JavaScript-style comments | Rare | `fix_json()` pass 4 removes them |
| JSON embedded in explanatory text | Common | `extract_json()` regex extraction |

---

## 7.5 BinderStore (Persistence)

**Source:** `srcs/workbinder/persistence.py` (2061 lines)

`BinderStore` provides durable SQLite storage for work binders and their artifacts, with support for querying, filtering, history tracking, and investigation resume.

### 7.5.1 SQLite Schema

The schema consists of 6 tables and 13 indexes:

#### Tables

**`work_binders`** -- Main binder records

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Binder ID |
| `investigation_id` | TEXT | NOT NULL | Associated investigation |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | Last update timestamp |
| `status` | TEXT | DEFAULT 'active' | Lifecycle status |

**`binder_artifacts`** -- Polymorphic artifact storage with soft delete

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Artifact ID |
| `binder_id` | TEXT | NOT NULL, FK | Parent binder |
| `artifact_type` | TEXT | NOT NULL | `ArtifactType` value |
| `created_by` | TEXT | NOT NULL | Persona name |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | Last update timestamp |
| `phase` | INTEGER | | Investigation phase |
| `function_name` | TEXT | | Related function |
| `priority` | TEXT | DEFAULT 'normal' | Priority level |
| `tags_json` | TEXT | | JSON array of tags |
| `content_json` | TEXT | NOT NULL | Polymorphic content blob |
| `is_deleted` | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| `deleted_by` | TEXT | | Who deleted |
| `deleted_reason` | TEXT | | Why deleted |

**`artifact_history`** -- Modification audit trail

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | History entry ID |
| `artifact_id` | TEXT | NOT NULL, FK | Target artifact |
| `modified_by` | TEXT | NOT NULL | Persona name |
| `modified_at` | TIMESTAMP | NOT NULL | Modification timestamp |
| `action` | TEXT | NOT NULL | create, update, delete, restore |
| `changes_json` | TEXT | NOT NULL | Before/after values |

**`artifact_tags`** -- Many-to-many tag associations

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `artifact_id` | TEXT | PK, FK | Artifact ID |
| `tag` | TEXT | PK | Tag string |

**`artifact_annotations`** -- Annotation cross-references

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Annotation ID |
| `artifact_id` | TEXT | NOT NULL, FK | Annotation artifact ID |
| `target_artifact_id` | TEXT | NOT NULL | Target being annotated |
| `created_by` | TEXT | NOT NULL | Persona name |
| `annotation_type` | TEXT | NOT NULL | comment, highlight, etc. |
| `content` | TEXT | NOT NULL | Annotation text |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |

**`binder_audit_log`** -- Complete access traceability

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Entry ID |
| `binder_id` | TEXT | NOT NULL, FK | Parent binder |
| `persona_name` | TEXT | NOT NULL | Actor |
| `phase_number` | INTEGER | | Phase context |
| `timestamp` | TIMESTAMP | NOT NULL | Access time |
| `access_sequence` | INTEGER | NOT NULL | Ordering within investigation |
| `operation_type` | TEXT | NOT NULL | "store" or "retrieve" |
| `artifact_type` | TEXT | NOT NULL | ArtifactType value |
| `artifact_id` | TEXT | | Specific artifact (null for bulk) |
| `method_name` | TEXT | NOT NULL | e.g., "add_hypothesis" |
| `result_count` | INTEGER | DEFAULT 1 | Artifacts affected |
| `success` | BOOLEAN | DEFAULT TRUE | Operation success |

#### Indexes

| Index | Table | Column(s) | Purpose |
|-------|-------|-----------|---------|
| `idx_binder_artifacts_binder` | `binder_artifacts` | `binder_id` | Fast artifact lookup by binder |
| `idx_binder_artifacts_type` | `binder_artifacts` | `artifact_type` | Filter by type |
| `idx_binder_artifacts_phase` | `binder_artifacts` | `phase` | Filter by phase |
| `idx_binder_artifacts_function` | `binder_artifacts` | `function_name` | Filter by function |
| `idx_artifact_tags_tag` | `artifact_tags` | `tag` | Tag-based queries |
| `idx_binders_investigation` | `work_binders` | `investigation_id` | Lookup by investigation |
| `idx_binders_status` | `work_binders` | `status` | Status-based listing |
| `idx_annotations_target` | `artifact_annotations` | `target_artifact_id` | Annotation lookup |
| `idx_audit_log_binder` | `binder_audit_log` | `binder_id` | Audit log by binder |
| `idx_audit_log_persona` | `binder_audit_log` | `persona_name` | Audit log by persona |
| `idx_audit_log_phase` | `binder_audit_log` | `phase_number` | Audit log by phase |
| `idx_audit_log_sequence` | `binder_audit_log` | `binder_id, access_sequence` | Ordered audit trail |

### 7.5.2 Binder Lifecycle: save / load / delete

#### `save_binder()`

```python
async def save_binder(self, binder: WorkBinder) -> None
```

Saves or updates a complete work binder. Performs:

1. Upserts the `work_binders` record
2. Saves all artifacts (via `_save_artifact()` for each), using `INSERT OR REPLACE`
3. Saves all history entries (using `INSERT OR IGNORE` to avoid duplicates)
4. Saves all audit log entries (using `INSERT OR IGNORE`)
5. Updates tag associations (deletes and re-inserts)
6. Updates annotation cross-references for `Annotation` artifacts

#### `load_binder()`

```python
async def load_binder(self, binder_id: str) -> WorkBinder | None
```

Loads a complete binder by ID, including all artifacts, history, and audit log. Uses `_row_to_artifact()` for polymorphic deserialization based on the `artifact_type` discriminator. The `ARTIFACT_CLASSES` mapping covers all 19 persistable artifact types:

```python
ARTIFACT_CLASSES: dict[ArtifactType, type[Artifact]] = {
    ArtifactType.CALL_GRAPH: CallGraphNode,
    ArtifactType.CODE_SNIPPET: CodeSnippet,
    ArtifactType.FINDING: Finding,
    ArtifactType.ANNOTATION: Annotation,
    ArtifactType.SOURCE_LOCATION: SourceLocationArtifact,
    ArtifactType.ERROR_CONTEXT: ErrorContextArtifact,
    ArtifactType.FUNCTION_SUMMARY: FunctionSummaryArtifact,
    ArtifactType.LOG_BUNDLE: LogBundleArtifact,
    ArtifactType.LLM_REQUEST: LLMRequestArtifact,
    ArtifactType.LLM_RESPONSE: LLMResponseArtifact,
    ArtifactType.FLOW_CONFIG: FlowConfigArtifact,
    ArtifactType.PHASE_STATE: PhaseStateArtifact,
    ArtifactType.INVESTIGATION_STATE: InvestigationStateArtifact,
    ArtifactType.PERSONA_CONTRIBUTION: PersonaContributionArtifact,
    ArtifactType.HYPOTHESIS_ARTIFACT: HypothesisArtifact,
    ArtifactType.EVIDENCE_ARTIFACT: EvidenceArtifact,
    ArtifactType.CAUSAL_CHAIN: CausalChainArtifact,
    ArtifactType.CHALLENGE: ChallengeArtifact,
    ArtifactType.CONCLUSION: ConclusionArtifact,
}
```

Note: The legacy `ArtifactType.HYPOTHESIS` and `ArtifactType.EVIDENCE` enum values are intentionally excluded from this mapping. They exist for backward compatibility with older binder snapshots. New artifacts always use `HYPOTHESIS_ARTIFACT` and `EVIDENCE_ARTIFACT`. The two meta-types (`ArtifactHistory`, `AuditLogEntry`) are stored in separate tables rather than as binder artifacts.

#### `load_binder_for_investigation()`

```python
async def load_binder_for_investigation(
    self, investigation_id: str
) -> WorkBinder | None
```

Looks up the binder ID by investigation ID, then delegates to `load_binder()`.

#### `delete_binder()`

```python
async def delete_binder(
    self, binder_id: str, hard: bool = False
) -> tuple[int, int]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binder_id` | `str` | -- | Binder to delete |
| `hard` | `bool` | `False` | If True: permanent removal. If False: soft delete. |

**Soft delete** (`hard=False`): Marks all active artifacts as deleted, updates binder status to `'archived'`. Returns `(artifacts_deleted, 0)`.

**Hard delete** (`hard=True`): Permanently removes tags, annotations, history, artifacts, and the binder record itself. Returns `(artifacts_count, history_count)`.

### 7.5.3 Resume Support

#### `load_for_resume()`

```python
async def load_for_resume(
    self, investigation_id: str
) -> tuple[WorkBinder, int, dict[str, Any]]
```

Loads a paused binder and determines the resume point. Raises `ValueError` if the investigation is not found or not in paused state.

**Returns:** Tuple of `(binder, resume_phase, resume_context)`.

#### `list_resumable_investigations()`

```python
async def list_resumable_investigations(self) -> list[dict[str, Any]]
```

Returns all binders with `status = 'paused'`, ordered by most recently updated. Each entry contains: `binder_id`, `investigation_id`, `created_at`, `updated_at`, `status`.

#### `get_investigation_summary()`

```python
async def get_investigation_summary(
    self, investigation_id: str
) -> dict[str, Any] | None
```

Returns a summary combining binder metadata with investigation state and artifact counts.

### 7.5.4 Direct Artifact Operations (CRUD)

These methods operate directly on the database without loading the full binder into memory.

#### `add_artifact()`

```python
async def add_artifact(self, binder_id: str, artifact: Artifact) -> str
```

Adds an artifact to a stored binder. Records a "create" history entry and updates the binder's `updated_at` timestamp.

#### `update_artifact()`

```python
async def update_artifact(
    self, artifact_id: str, updates: dict[str, Any], modified_by: str
) -> bool
```

Updates artifact fields in the database. Parses the current `content_json`, applies updates, records a "update" history entry with before/after values. Also updates the `artifact_tags` table if `"tags"` is in the updates.

#### `delete_artifact()`

```python
async def delete_artifact(
    self, artifact_id: str, deleted_by: str, reason: str | None = None
) -> bool
```

Soft-deletes an artifact (sets `is_deleted = TRUE`). Records a "delete" history entry.

#### `restore_artifact()`

```python
async def restore_artifact(self, artifact_id: str, restored_by: str) -> bool
```

Restores a soft-deleted artifact (sets `is_deleted = FALSE`, clears `deleted_by` and `deleted_reason`). Records a "restore" history entry.

#### `get_artifact_by_id()`

```python
async def get_artifact_by_id(
    self, binder_id: str, artifact_id: str
) -> Artifact | None
```

Retrieves a single artifact by its primary key, scoped to a specific binder.

### 7.5.5 Query Methods

#### `query_artifacts()`

```python
async def query_artifacts(
    self,
    binder_id: str,
    artifact_type: str | None = None,
    phase: int | None = None,
    function_name: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Artifact]
```

The primary query method. Builds a dynamic SQL query with optional filters. Tags use a subquery with `GROUP BY ... HAVING COUNT(DISTINCT tag)` to implement AND logic. Results are ordered by `created_at DESC` with limit/offset pagination.

#### `search_artifacts()`

```python
async def search_artifacts(
    self, binder_id: str, query: str, artifact_types: list[str] | None = None
) -> list[Artifact]
```

Full-text search via `content_json LIKE ?` with optional artifact type filtering. Results are limited to 50 and ordered by `created_at DESC`.

#### `list_binders()`

```python
async def list_binders(
    self, status: str | None = None, limit: int = 100
) -> list[dict[str, Any]]
```

Lists binder summaries with optional status filter.

#### `get_artifact_count()`

```python
async def get_artifact_count(self, binder_id: str) -> dict[str, int]
```

Returns artifact counts grouped by type (excluding deleted artifacts).

### 7.5.6 Specialized Artifact Queries

These methods combine `query_artifacts()` with post-query filtering on content fields.

| Method | Artifact Type | Additional Filters |
|--------|---------------|-------------------|
| `get_hypotheses(binder_id, min_score, source, limit)` | `hypothesis_artifact` | `score >= min_score`, `source == source` |
| `get_evidence_items(binder_id, evidence_type, strength, limit)` | `evidence_artifact` | `evidence_type`, `strength` |
| `get_causal_chains(binder_id, hypothesis_id, limit)` | `causal_chain` | `hypothesis_id` |
| `get_challenges(binder_id, resolved, severity, limit)` | `challenge` | `resolved`, `severity` |

### 7.5.7 LLM Traceability Queries

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_llm_requests()` | `(binder_id, persona, phase, prompt_key, limit)` | Get LLM request artifacts with content-level filtering |
| `get_llm_responses()` | `(binder_id, request_id, phase, parse_success, limit)` | Get LLM response artifacts with content-level filtering |
| `get_llm_exchanges()` | `(binder_id, phase)` | Pair requests with responses by ID. Returns `list[tuple[Artifact, Artifact \| None]]` |
| `get_llm_statistics()` | `(binder_id)` | Aggregate: total requests/responses, token counts, latency, breakdown by persona/phase, parse success/failure counts |

### 7.5.8 Investigation State Queries

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_investigation_state_artifact()` | `(binder_id)` | Returns the single `InvestigationStateArtifact` or `None` |
| `get_phase_states()` | `(binder_id, status)` | Returns `PhaseStateArtifact` list with optional status filter |
| `list_investigations_with_state()` | `(outcome, status, limit)` | Lists all investigations with state info. Filters by outcome and/or binder status |
| `get_similar_investigations()` | `(error_function, error_message_pattern, limit)` | Finds similar investigations by matching error context. Returns ranked by match score (0.0-1.0) |

### 7.5.9 Audit Log Queries

#### `get_audit_log()`

```python
async def get_audit_log(
    self,
    binder_id: str,
    persona_name: str | None = None,
    phase_number: int | None = None,
    operation_type: str | None = None,
    limit: int = 100,
) -> list[AuditLogEntry]
```

Queries audit log entries with optional filters. Results are ordered by `access_sequence`.

#### `get_audit_log_count()`

```python
async def get_audit_log_count(self, binder_id: str) -> int
```

Returns the total count of audit log entries for a binder.

### 7.5.10 Reference Validation

#### `validate_references()`

```python
async def validate_references(self, binder_id: str) -> list[str]
```

Validates all inter-artifact references within a binder. Checks:

| Artifact Type | Reference Fields Checked |
|---------------|------------------------|
| `hypothesis_artifact` | `supporting_evidence_ids`, `contradicting_evidence_ids` |
| `evidence_artifact` | `targets_hypothesis_id` |
| `causal_chain` | `hypothesis_id`, step-level `evidence_ids` |
| `challenge` | `target_hypothesis_id` |
| `annotation` | `target_artifact_id` |

Raises `ValueError` with a formatted error list if any invalid references are found. Returns an empty list if all references are valid.

### 7.5.11 Pattern and Calibration Queries

BinderStore also provides read access to knowledge base tables (shared database):

| Method | Description |
|--------|-------------|
| `list_patterns(active_only, min_confidence, min_times_seen, limit, offset)` | Paginated pattern listing with filtering |
| `get_pattern(pattern_id)` | Pattern detail with associated root causes |
| `get_pattern_statistics()` | Aggregate stats: total, active, average confidence, accuracy breakdown |
| `list_calibrations(limit)` | List model calibration records |
| `get_calibration(model, error_type)` | Get calibration buckets for a specific model |

### 7.5.12 Polymorphic Deserialization

The `_row_to_artifact()` method handles deserialization of the polymorphic `content_json` column:

1. Reads the `artifact_type` discriminator from the row
2. Looks up the corresponding Pydantic model class in `ARTIFACT_CLASSES`
3. Parses `content_json` into a dict and merges with common fields (`id`, `created_by`, `created_at`, etc.)
4. Calls `artifact_class.model_validate(content)` for Pydantic validation

The `_json_serializer()` module-level function handles custom serialization for `datetime`, Pydantic models (via `model_dump`), and enums (via `.value`).

---

## Summary

The three layers documented in this chapter form the complete I/O boundary of the WorkBinder:

- **BinderTools** provides the write path for personas -- adding artifacts, expanding call graphs, recording findings
- **BinderSerializer** provides the read path for prompts -- converting binder state into token-budgeted context
- **Parsers** provide the return path from LLM -- converting raw text responses back into typed domain models and durable artifacts
- **JSON Utilities** ensure robustness against the messy reality of LLM output formats
- **BinderStore** makes the entire graph durable and queryable across investigation sessions

These layers are used by every phase of the investigation pipeline and by both the REST API and MCP server for external access.
