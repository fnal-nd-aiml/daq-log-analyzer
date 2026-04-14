> **Agentic WorkBinder Library -- Ch. 1: Architecture & Core API** | [Table of Contents](agentic-workbinder-library.md) | [Next: Ch. 2: Context Artifacts ->](agentic-workbinder-library-ch2-context-artifacts.md)

---

# Chapter 1: Architecture & Core API

This chapter documents the WorkBinder's design philosophy, all artifact type definitions, the core CRUD API, the permissions model, the audit system, state management, LLM communication tracking, evidence-hypothesis linking, and the complete artifact data flow through the investigation pipeline.

**Source files:**
- `srcs/workbinder/artifacts_types.py` -- All artifact type definitions (24 types + supporting models)
- `srcs/workbinder/binder.py` -- WorkBinder core class (~2,422 lines)
- `srcs/workbinder/ARTIFACT_PERMISSIONS.md` -- Permissions matrix reference

---

## 1.1 Design Philosophy

The WorkBinder exists because the investigation pipeline is a multi-phase, multi-persona system where each phase must communicate its outputs to downstream phases without direct coupling. Rather than pass data structures between function calls, all inter-phase communication flows through a single shared container -- the WorkBinder. This design is governed by five core principles.

### Binder-Centric Data Exchange

**All** inter-phase communication happens through the binder. Each phase (persona) receives only the binder as input and writes its outputs back to the binder. No phase passes data directly to another phase. The `InvestigationCoordinator` orchestrates phase execution order, but it is the binder that carries state.

```python
async def seek(self, binder: WorkBinder) -> None:
    # 1. Read what this phase needs from the binder
    hypotheses = binder.get_hypotheses()
    source_locations = binder.get_source_locations()

    # 2. Do work using retrieved artifacts...

    # 3. Write outputs back to the binder
    for item in gathered_evidence:
        binder.add_evidence(
            evidence_type=item.evidence_type,
            content=item.content,
            source=item.source,
            strength=item.strength,
            created_by="Detective",
            phase=2,
        )
```

### Write-Once / Read-Forward

Each investigation artifact type is written by exactly one phase. Later phases can read artifacts from earlier phases but cannot modify them. This ensures that the Theorist's hypotheses remain stable while the Detective seeks evidence against them, and that the Logician's causal chains are not altered by the Devil's Advocate who reviews them.

The only exception is `EVIDENCE`, which has `RW` permission for the Detective (Phase 2) -- the Detective both reads prior evidence to avoid duplicate queries and writes new evidence items within the same phase.

### Complete Capture

Everything goes into the binder: investigation artifacts, LLM requests and responses (with full prompt text), phase lifecycle state, flow configuration snapshots, and audit log entries. This makes every investigation fully inspectable after the fact.

### Resumability

Because the binder captures complete state, a persisted binder can be deserialized to resume an interrupted investigation. The `InvestigationStateArtifact` tracks which phase was in progress; `PhaseStateArtifact` records per-phase status (pending, in_progress, completed, failed); and `FlowConfigArtifact` preserves the exact configuration used at investigation start.

### Traceability

Every artifact creation, modification, and deletion is recorded in `ArtifactHistory`. Every artifact access (both stores and retrieves) is recorded in `AuditLogEntry` with a monotonically increasing `access_sequence` number. The `audit_context()` context manager attributes retrieval operations to the persona and phase performing them.

---

## 1.2 Artifact Base Class

All 24 artifact types inherit from the `Artifact` base model defined in `srcs/workbinder/artifacts_types.py`. The base class uses Pydantic v2 `BaseModel` and provides common metadata fields.

### Base Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique identifier (16-char UUID prefix) |
| `artifact_type` | `ArtifactType` | (set by subclass) | Discriminator for polymorphic storage |
| `created_by` | `str` | (required) | Persona name that created this artifact |
| `created_at` | `datetime` | `datetime.now()` | Creation timestamp |
| `updated_at` | `datetime` | `datetime.now()` | Last modification timestamp |
| `tags` | `list[str]` | `[]` | User-defined tags for categorization |
| `phase` | `int \| None` | `None` | Investigation phase when created (-1 through 7) |
| `function_name` | `str \| None` | `None` | Related function name for grouping |
| `priority` | `Priority` | `Priority.NORMAL` | Artifact priority level |
| `is_deleted` | `bool` | `False` | Soft delete flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |

### ID Generation Scheme

All artifact IDs are generated by `generate_id()` from `srcs/models/base.py`. This function produces a 16-character UUID prefix (e.g., `a1b2c3d4e5f6g7h8`). The same generator is used across all models in the system, ensuring consistent ID format in the database (`TEXT PRIMARY KEY`).

### Inheritance Pattern

Each concrete artifact type inherits from `Artifact` and overrides `artifact_type` with its enum value as a class-level default:

```python
class CallGraphNode(Artifact):
    artifact_type: ArtifactType = ArtifactType.CALL_GRAPH
    center_function: str
    callers: list[CallerInfo] = Field(default_factory=list)
    callees: list[CalleeInfo] = Field(default_factory=list)
    depth_explored: int = 1
    diagram: str | None = None
```

This pattern means each subclass carries its type discriminator automatically. The `WorkBinder._get_artifact_classes()` static method returns a mapping of `ArtifactType` to concrete class, used for deserialization.

### Soft Deletion

Artifacts are never hard-deleted from the binder. Instead, `mark_deleted()` sets the `is_deleted`, `deleted_by`, and `deleted_reason` fields. Soft-deleted artifacts are excluded from queries by default (unless `include_deleted=True` is set on `BinderQuery`). The `restore_artifact()` method reverses soft deletion.

---

## 1.3 ArtifactType Enum

The `ArtifactType` enum (`str, Enum`) defines all 23 artifact types stored in the binder. Each value is a lowercase string used as the discriminator in polymorphic storage.

### All 24 ArtifactType Values

| Enum Value | String | Artifact Class | Description |
|-----------|--------|----------------|-------------|
| `CALL_GRAPH` | `"call_graph"` | `CallGraphNode` | Call graph centered on a function with callers and callees |
| `CODE_SNIPPET` | `"code_snippet"` | `CodeSnippet` | Source code fragment with location and optional summary |
| `FINDING` | `"finding"` | `Finding` | Persona observation, question, conclusion, or recommendation |
| `ANNOTATION` | `"annotation"` | `Annotation` | Comment, highlight, question, or correction on another artifact |
| `SOURCE_LOCATION` | `"source_location"` | `SourceLocationArtifact` | Error source location in code with match score |
| `HYPOTHESIS` | `"hypothesis"` | (legacy, not mapped) | Legacy value -- see `HYPOTHESIS_ARTIFACT` |
| `EVIDENCE` | `"evidence"` | (legacy, not mapped) | Legacy value -- see `EVIDENCE_ARTIFACT` |
| `ERROR_CONTEXT` | `"error_context"` | `ErrorContextArtifact` | Triggering error message and surrounding log context |
| `LLM_REQUEST` | `"llm_request"` | `LLMRequestArtifact` | Full LLM request with prompts, model, and parameters |
| `LLM_RESPONSE` | `"llm_response"` | `LLMResponseArtifact` | Full LLM response with parsed content and metrics |
| `FLOW_CONFIG` | `"flow_config"` | `FlowConfigArtifact` | Complete configuration snapshot at investigation start |
| `PHASE_STATE` | `"phase_state"` | `PhaseStateArtifact` | Per-phase lifecycle state |
| `INVESTIGATION_STATE` | `"investigation_state"` | `InvestigationStateArtifact` | Central investigation state tracker |
| `PERSONA_CONTRIBUTION` | `"persona_contribution"` | `PersonaContributionArtifact` | Record of a persona's contribution |
| `HYPOTHESIS_ARTIFACT` | `"hypothesis_artifact"` | `HypothesisArtifact` | Hypothesis with evidence links and scoring |
| `EVIDENCE_ARTIFACT` | `"evidence_artifact"` | `EvidenceArtifact` | Evidence item with hypothesis relationships |
| `CAUSAL_CHAIN` | `"causal_chain"` | `CausalChainArtifact` | Causal chain linking root cause to observed error |
| `CHALLENGE` | `"challenge"` | `ChallengeArtifact` | Adversarial challenge during review |
| `CONCLUSION` | `"conclusion"` | `ConclusionArtifact` | Final investigation conclusion with root cause |
| `FUNCTION_SUMMARY` | `"function_summary"` | `FunctionSummaryArtifact` | Detailed per-function LLM summary |
| `LOG_BUNDLE` | `"log_bundle"` | `LogBundleArtifact` | Chronologically merged multi-file log bundle |
| `MERGED_TIMELINE` | `"merged_timeline"` | `MergedTimelineArtifact` | Chronologically merged timeline of parsed log entries from all files |
| `BOARDREADER_IDENTIFICATION` | `"boardreader_identification"` | `BoardReaderIdentificationArtifact` | Boardreader types, components, and key error messages from Phase -1 |
| `FEEDBACK` | `"feedback"` | `FeedbackArtifact` | User feedback on investigation correctness |

**Note:** `HYPOTHESIS` and `EVIDENCE` exist in the enum for backward compatibility but are not mapped to artifact classes in `_get_artifact_classes()`. The active types are `HYPOTHESIS_ARTIFACT` and `EVIDENCE_ARTIFACT`.

### Supporting Enums

#### Priority

Controls artifact prioritization in serialization and display.

| Value | String |
|-------|--------|
| `LOW` | `"low"` |
| `NORMAL` | `"normal"` |
| `HIGH` | `"high"` |
| `CRITICAL` | `"critical"` |

#### FindingType

Categorizes findings made by any persona.

| Value | String | Usage |
|-------|--------|-------|
| `OBSERVATION` | `"observation"` | Factual observation from logs or code |
| `QUESTION` | `"question"` | Open question requiring investigation |
| `CONCLUSION` | `"conclusion"` | Conclusion drawn from evidence |
| `WARNING` | `"warning"` | Warning about a potential issue |
| `RECOMMENDATION` | `"recommendation"` | Suggested action or investigation direction |

#### AnnotationType

Categorizes annotations placed on other artifacts.

| Value | String | Usage |
|-------|--------|-------|
| `COMMENT` | `"comment"` | General comment on an artifact |
| `HIGHLIGHT` | `"highlight"` | Highlight important content |
| `QUESTION` | `"question"` | Question about an artifact |
| `CORRECTION` | `"correction"` | Correction to artifact content |

---

## 1.4 WorkBinder Core API

The `WorkBinder` class is defined as a Python `dataclass` in `srcs/workbinder/binder.py`. It is the central container for all investigation artifacts, providing CRUD operations, querying, indexing, serialization, and state management.

### Constructor

```python
@dataclass
class WorkBinder:
    id: str = field(default_factory=generate_id)
    investigation_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: str = "active"  # active, completed, archived, paused
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique binder ID |
| `investigation_id` | `str` | `""` | Links to the Investigation this binder belongs to |
| `created_at` | `datetime` | `datetime.now()` | Binder creation time |
| `updated_at` | `datetime` | `datetime.now()` | Last modification time |
| `status` | `str` | `"active"` | Binder lifecycle status |

### Internal Storage

| Field | Type | Description |
|-------|------|-------------|
| `_artifacts` | `dict[str, Artifact]` | Primary artifact store, keyed by artifact ID |
| `_history` | `list[ArtifactHistory]` | Modification history for all artifacts |
| `_tags_index` | `dict[str, set[str]]` | Tag-to-artifact-IDs index for fast tag lookups |
| `_function_index` | `dict[str, set[str]]` | Function-name-to-artifact-IDs index |
| `_audit_log` | `list[AuditLogEntry]` | Complete audit trail |
| `_access_sequence` | `int` | Monotonically increasing access counter |
| `_audit_persona` | `str \| None` | Current audit context persona |
| `_audit_phase` | `int \| None` | Current audit context phase |

### Core CRUD Methods

#### `add_artifact(artifact, record_history=True) -> str`

Adds an artifact to the binder. Updates tag and function indexes. Records an `ArtifactHistory` entry with action `"create"`. Returns the artifact ID.

#### `get_artifact(artifact_id) -> Artifact | None`

Retrieves an artifact by ID. Returns `None` if not found. Returns the artifact even if it is soft-deleted (unlike `query()` which excludes deleted artifacts by default). This is needed by internal methods like `restore_artifact()` and admin/debugging tools.

#### `update_artifact(artifact_id, updates, modified_by) -> bool`

Updates artifact fields by name. Records before/after values in `ArtifactHistory` with action `"update"`. Updates tag and function indexes if those fields change. Sets `updated_at` on both the artifact and the binder. Returns `True` if the artifact was found and updated, `False` otherwise.

#### `mark_deleted(artifact_id, deleted_by, reason=None) -> bool`

Soft-deletes an artifact by setting `is_deleted=True`, `deleted_by`, and `deleted_reason`. Records `ArtifactHistory` with action `"delete"`. Returns `True` if found, `False` otherwise.

#### `restore_artifact(artifact_id, restored_by) -> bool`

Reverses soft deletion by clearing `is_deleted`, `deleted_by`, and `deleted_reason`. Records `ArtifactHistory` with action `"restore"`. Returns `True` if found, `False` otherwise.

### Query Methods

#### `query(query: BinderQuery) -> list[Artifact]`

The primary query method. `BinderQuery` is a dataclass with the following filter parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artifact_type` | `ArtifactType \| None` | `None` | Filter by artifact type |
| `created_by` | `str \| None` | `None` | Filter by creator persona |
| `tags` | `list[str] \| None` | `None` | Filter by tags (all must match) |
| `phase` | `int \| None` | `None` | Filter by creation phase |
| `function_name` | `str \| None` | `None` | Filter by related function |
| `priority` | `Priority \| None` | `None` | Filter by priority |
| `include_deleted` | `bool` | `False` | Include soft-deleted artifacts |
| `limit` | `int` | `100` | Maximum results |
| `offset` | `int` | `0` | Pagination offset |

All filters are AND-combined. Deleted artifacts are excluded by default.

#### `get_by_type(artifact_type) -> list[Artifact]`

Shortcut for `query(BinderQuery(artifact_type=...))`.

#### `get_by_tag(tag) -> list[Artifact]`

Uses the `_tags_index` for fast tag-based lookup. Returns non-deleted artifacts matching the tag.

#### `get_by_function(function_name) -> list[Artifact]`

Uses the `_function_index` for fast function-based lookup. Returns non-deleted artifacts related to the named function.

#### `get_related_artifacts(artifact_id) -> list[Artifact]`

Finds artifacts related to the given artifact by:
- Findings that reference this artifact in their `related_artifacts` list
- Annotations targeting this artifact via `target_artifact_id`
- Artifacts sharing the same `function_name`

#### `get_annotations(artifact_id) -> list[Annotation]`

Returns all `Annotation` artifacts whose `target_artifact_id` matches the given ID.

#### `get_history(artifact_id=None) -> list[ArtifactHistory]`

Returns modification history. If `artifact_id` is provided, filters to that artifact only.

#### `count_by_type() -> dict[str, int]`

Returns a dictionary mapping artifact type string values to counts of non-deleted artifacts.

#### `get_all_tags() -> list[str]`

Returns all unique tag names used across artifacts in the binder.

### Reference Validation

#### `artifact_exists(artifact_id) -> bool`

Returns `True` if the artifact exists and is not soft-deleted.

#### `validate_artifact_reference(artifact_id, expected_type=None, context="") -> Artifact`

Validates that an artifact reference is valid. Raises `ValueError` if:
- The artifact ID does not exist in the binder
- The artifact has been soft-deleted
- The artifact is not an instance of `expected_type` (if provided)

The `context` parameter is included in error messages for debugging. This method is called internally by `link_evidence_to_hypothesis()`, `add_causal_chain()`, and `add_challenge()` to enforce referential integrity.

### Serialization

#### `to_dict() -> dict[str, Any]`

Serializes the binder to a dictionary containing `id`, `investigation_id`, `created_at`, `updated_at`, `status`, `artifacts` (keyed by ID, each as `model_dump()`), and `history`.

#### `from_dict(data) -> WorkBinder` (classmethod)

Deserializes a binder from a dictionary. Uses `_get_artifact_classes()` to reconstruct each artifact into its correct concrete type via `model_validate()`. History entries are reconstructed without re-recording.

### Convenience Methods Table

These methods wrap `add_artifact()` with type-specific constructors. Each creates the appropriate artifact instance, adds it to the binder, and records an audit log entry.

| Method | Artifact Type | Producer | Returns |
|--------|---------------|----------|---------|
| `add_call_graph(center_function, callers, callees, created_by, ...)` | `CallGraphNode` | Archivist | artifact ID |
| `add_function_summary(function_name, purpose, mechanism, data_flow, error_paths, error_line_relevance, center_function, role, created_by, ...)` | `FunctionSummaryArtifact` | Archivist | artifact ID |
| `add_code_snippet(file_path, start_line, end_line, content, created_by, ...)` | `CodeSnippet` | Archivist | artifact ID |
| `add_finding(persona, finding_type, content, ...)` | `Finding` | Any persona | artifact ID |
| `add_annotation(target_artifact_id, annotation_type, content, created_by)` | `Annotation` | Any persona | artifact ID |
| `add_source_location(file_path, line_number, created_by, ...)` | `SourceLocationArtifact` | Archivist | artifact ID |
| `add_error_context(error, context_logs, created_by)` | `ErrorContextArtifact` | Archivist | artifact ID |
| `add_hypothesis(description, source, prior_probability, ...)` | `HypothesisArtifact` | Theorist | artifact ID |
| `add_evidence(evidence_type, content, source, strength, ...)` | `EvidenceArtifact` | Detective | artifact ID |
| `add_causal_chain(hypothesis_id, steps, ...)` | `CausalChainArtifact` | Logician | artifact ID |
| `add_challenge(target_hypothesis_id, content, severity, ...)` | `ChallengeArtifact` | Devil's Advocate | artifact ID |
| `add_conclusion(root_cause, confidence_raw, confidence_calibrated, outcome, ...)` | `ConclusionArtifact` | Synthesizer | artifact ID |
| `add_log_bundle(source_files, merged_timeline, ...)` | `LogBundleArtifact` | Chronicler | artifact ID |
| `add_merged_timeline(entries, total_entries, ...)` | `MergedTimelineArtifact` | Chronicler | artifact ID |
| `add_boardreader_identification(boardreader_types, components, error_messages, ...)` | `BoardReaderIdentificationArtifact` | Chronicler | artifact ID |
| `add_flow_config(investigation_config, llm_config, ...)` | `FlowConfigArtifact` | System | artifact ID |
| `add_investigation_state(investigation_id, ...)` | `InvestigationStateArtifact` | System | artifact ID |
| `add_persona_contribution(persona_id, contribution_phase, content, ...)` | `PersonaContributionArtifact` | Any persona | artifact ID |
| `add_feedback(investigation_id, was_correct, ...)` | `FeedbackArtifact` | System/API | artifact ID |

### Convenience Getter Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_hypotheses()` | `list[HypothesisArtifact]` | All hypotheses, sorted by `rank` |
| `get_evidence_items()` | `list[EvidenceArtifact]` | All evidence items |
| `get_causal_chains()` | `list[CausalChainArtifact]` | All causal chains |
| `get_challenges()` | `list[ChallengeArtifact]` | All challenges |
| `get_error_context()` | `ErrorContextArtifact \| None` | The triggering error artifact |
| `get_source_locations()` | `list[SourceLocationArtifact]` | All source locations, sorted by `match_score` (descending) |
| `get_call_graphs()` | `list[CallGraphNode]` | All call graph artifacts |
| `get_code_snippets()` | `list[CodeSnippet]` | All code snippets |
| `get_conclusion()` | `ConclusionArtifact \| None` | The investigation conclusion |
| `get_log_bundle()` | `LogBundleArtifact \| None` | The log bundle (if multi-file) |
| `get_merged_timeline()` | `MergedTimelineArtifact \| None` | The merged timeline (if multi-file) |
| `get_boardreader_identification()` | `BoardReaderIdentificationArtifact \| None` | The boardreader identification (if multi-file) |
| `get_flow_config()` | `FlowConfigArtifact \| None` | The flow configuration |
| `get_investigation_state()` | `InvestigationStateArtifact \| None` | The investigation state tracker |
| `get_phase_state(phase)` | `PhaseStateArtifact \| None` | State for a specific phase |
| `get_persona_contributions(persona_id, phase)` | `list[PersonaContributionArtifact]` | Contributions, optionally filtered |
| `get_feedback()` | `list[FeedbackArtifact]` | All feedback artifacts |

The getter methods for `get_hypotheses()`, `get_evidence_items()`, `get_causal_chains()`, `get_challenges()`, `get_source_locations()`, and `get_call_graphs()` emit audit log entries via `_log_access()` using the current `audit_context()` values.

---

## 1.5 Permissions Model

The WorkBinder enforces a conceptual permissions model based on two rules: **write-once** (each investigation artifact type is produced by exactly one phase) and **read-forward** (later phases read artifacts from earlier phases). The enforcement is primarily structural -- each phase's code calls only the convenience methods appropriate for its role.

### Per-Phase Permissions Matrix

| Artifact | -1: Chronicler | 0: Archivist | 1: Theorist | 2: Detective | 3: Logician | 4: Devil's Advocate | 5: Judge | 6: Synthesizer |
|----------|----------------|--------------|-------------|--------------|-------------|---------------------|----------|----------------|
| LOG_BUNDLE | **W** | R | R | R | R | R | R | R |
| MERGED_TIMELINE | **W** | R | R | R | R | R | R | R |
| BOARDREADER_ID | **W** | R | R | R | R | R | R | R |
| ERROR_CONTEXT | - | **W** | R | R | R | R | R | R |
| SOURCE_LOCATION | - | **W** | R | R | R | R | R | R |
| CALL_GRAPH | - | **W** | R | R | R | R | R | R |
| CODE_SNIPPET | - | **W** | R | R | R | R | R | R |
| FUNCTION_SUMMARY | - | **W** | R | R | R | R | R | R |
| HYPOTHESIS | - | - | **W** | R | R | R | R | R |
| EVIDENCE | - | - | - | **RW** | R | R | R | R |
| CAUSAL_CHAIN | - | - | - | - | **W** | R | R | R |
| CHALLENGE | - | - | - | - | - | **W** | R | R |
| CONCLUSION | - | - | - | - | - | - | - | **W** |

### Enforcement Mechanism

The WorkBinder does not enforce permissions at the API level with a `_check_permission()` method. Instead, permissions are enforced structurally:

1. **Phase code** -- Each phase's implementation (e.g., `hypotheses.py` for Phase 1) calls only the convenience write methods appropriate for its role and only the convenience read methods for its allowed artifact types.

2. **`audit_context()`** -- The context manager sets the current persona and phase. All getter methods that emit audit log entries use this context to attribute access. This creates a complete audit trail that can be inspected to verify permission compliance after the fact.

3. **Reference validation** -- Methods like `add_causal_chain()` and `add_challenge()` call `validate_artifact_reference()` to ensure the referenced hypothesis artifact actually exists, enforcing relational integrity.

### Implementation Pattern

Each phase receives **only the binder** as input and returns `None` (writing results to the binder instead):

```python
# In Phase 2 (Detective)
async def seek(self, binder: WorkBinder) -> None:
    # Use audit_context to attribute reads
    with binder.audit_context("Detective", phase=2):
        # Read from earlier phases
        hypotheses = binder.get_hypotheses()
        source_locations = binder.get_source_locations()
        code_snippets = binder.get_code_snippets()

    # Write this phase's outputs
    for item in gathered_evidence:
        binder.add_evidence(
            evidence_type=item.evidence_type,
            content=item.content,
            source=item.source,
            strength=item.strength,
            created_by="Detective",
            phase=2,
        )
```

---

## 1.6 History & Audit System

The WorkBinder maintains two parallel tracking systems: **modification history** (what changed) and **access audit log** (who accessed what).

### ArtifactHistory Model

Records every modification to an artifact. Defined in `srcs/workbinder/artifacts_types.py`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique history entry ID |
| `artifact_id` | `str` | (required) | ID of the modified artifact |
| `modified_by` | `str` | (required) | Persona name that performed the modification |
| `modified_at` | `datetime` | `datetime.now()` | When the modification occurred |
| `action` | `str` | (required) | One of: `"create"`, `"update"`, `"delete"`, `"restore"` |
| `changes` | `dict[str, Any]` | `{}` | Before/after values for updates; full artifact dump for creates |

History entries are recorded automatically by:
- `add_artifact()` -- records `"create"` action with full artifact dump in `changes.artifact`
- `update_artifact()` -- records `"update"` action with `changes.before` and `changes.after` dicts
- `mark_deleted()` -- records `"delete"` action with `changes.reason`
- `restore_artifact()` -- records `"restore"` action with empty changes

### AuditLogEntry Model

Records every artifact access (both stores and retrieves). Defined in `srcs/workbinder/artifacts_types.py`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique audit entry ID |
| `persona_name` | `str` | (required) | Who performed the operation |
| `phase_number` | `int \| None` | (required) | Investigation phase number |
| `timestamp` | `datetime` | `datetime.now()` | When the access occurred |
| `access_sequence` | `int` | (required) | 1-based monotonically increasing sequence number |
| `operation_type` | `str` | (required) | `"store"` or `"retrieve"` |
| `artifact_type` | `str` | (required) | ArtifactType string value |
| `artifact_id` | `str \| None` | `None` | Specific artifact ID (`None` for bulk retrieves) |
| `method_name` | `str` | (required) | Name of the method called (e.g., `"add_hypothesis"`, `"get_hypotheses"`) |
| `result_count` | `int` | `1` | Number of artifacts affected or returned |
| `success` | `bool` | `True` | Whether the operation succeeded |

### `audit_context()` Context Manager

Sets the persona name and phase number for operations within the block. All getter methods that emit audit log entries use these values to attribute reads:

```python
with binder.audit_context("Theorist", phase=1):
    # All reads within this block are attributed to Theorist/Phase 1
    source_locations = binder.get_source_locations()
    call_graphs = binder.get_call_graphs()
    code_snippets = binder.get_code_snippets()
```

The context manager is nestable. When the block exits, the previous audit context is restored. If no audit context is active, getter methods attribute reads to `"Unknown"` persona with `None` phase.

### Access Sequence Tracking

The `_access_sequence` counter starts at 0 and increments by 1 for every `_log_access()` call. This creates a total ordering of all artifact accesses within an investigation, enabling reconstruction of the exact sequence of reads and writes.

### `_log_access()` Internal Method

```python
def _log_access(
    self,
    persona_name: str,
    phase_number: int | None,
    operation_type: str,    # "store" or "retrieve"
    artifact_type: str,
    method_name: str,
    artifact_id: str | None = None,
    result_count: int = 1,
    success: bool = True,
) -> None
```

Creates an `AuditLogEntry` with the current `_access_sequence` (incremented first) and appends it to `_audit_log`.

### `get_audit_log()` Query Method

```python
def get_audit_log(
    self,
    persona_name: str | None = None,
    phase_number: int | None = None,
    operation_type: str | None = None,
) -> list[AuditLogEntry]
```

Returns audit log entries with optional filtering by persona, phase, or operation type. All filters are AND-combined.

---

## 1.7 State Management API

The WorkBinder provides a complete state management layer for tracking investigation lifecycle and per-phase progress. This enables monitoring, error recovery, and investigation pause/resume.

### Investigation State

#### `add_investigation_state(investigation_id, trigger_error_artifact_id=None, created_by="system") -> str`

Creates an `InvestigationStateArtifact` with `current_phase=0`, `status="active"`, and `started_at=datetime.now()`. Called once at investigation start by the coordinator.

#### `get_investigation_state() -> InvestigationStateArtifact | None`

Returns the (single) investigation state artifact, or `None` if not yet created.

#### `update_investigation_state(modified_by="system", **updates) -> bool`

Updates the investigation state artifact with arbitrary field values. Returns `True` if the state was found and updated.

### Phase Lifecycle

#### `start_phase(phase, persona_name) -> str`

Marks a phase as started. If a `PhaseStateArtifact` already exists for this phase, updates it to `status="in_progress"` with a new `started_at` timestamp. Otherwise, creates a new `PhaseStateArtifact`. Returns the artifact ID.

#### `complete_phase(phase, output_ids, modified_by="system") -> None`

Marks a phase as completed by setting `status="completed"`, `completed_at=datetime.now()`, and `output_artifact_ids` to the list of artifact IDs produced by the phase. Also advances `current_phase` on the investigation state artifact to `phase + 1`.

#### `fail_phase(phase, error_message, modified_by="system") -> None`

Marks a phase as failed by setting `status="failed"`, `completed_at=datetime.now()`, and `error_message`.

#### `get_phase_state(phase) -> PhaseStateArtifact | None`

Returns the `PhaseStateArtifact` for the given phase number, or `None` if the phase has not been started.

### Pause / Resume Lifecycle

#### `pause_investigation(reason, modified_by="system") -> None`

Sets the investigation state to `status="paused"` with `paused_at=datetime.now()` and `pause_reason`. Also sets `self.status = "paused"` on the binder itself.

#### `can_resume() -> bool`

Returns `True` if the investigation state exists and has `status == "paused"`.

#### `get_resume_point() -> tuple[int, dict[str, Any]]`

Determines the phase to resume from and builds a resume context. The resume phase is determined by:
1. Starting from `current_phase` on the investigation state
2. If the current phase was `"in_progress"`, resume there
3. If the previous phase was not `"completed"`, resume from the previous phase

The resume context is a dictionary containing `phase`, `hypotheses`, `evidence`, and `findings` collected from all non-deleted artifacts. Raises `ValueError` if the investigation is not in paused state.

#### `resume_investigation(modified_by="system") -> int`

Resumes a paused investigation by setting `status="active"`, clearing `paused_at` and `pause_reason`, and incrementing `resume_count`. Also sets `self.status = "active"`. Returns the phase to resume from. Raises `ValueError` if the investigation cannot be resumed.

### Phase Timing

Phase timing is captured through the `PhaseStateArtifact` fields:
- `started_at` -- set by `start_phase()`
- `completed_at` -- set by `complete_phase()` or `fail_phase()`

The elapsed time for a phase can be computed as `completed_at - started_at`.

### Investigation State Lifecycle

```
                    +------------------+
                    |     Created      |
                    +--------+---------+
                             |
                    +--------v---------+
          +---------+     Active       +---------+
          |         +--------+---------+         |
          |                  |                   |
   +------v------+  +-------v--------+  +-------v------+
   |   Paused    |  |   Completed    |  |    Failed    |
   +------+------+  +----------------+  +--------------+
          |
   +------v------+
   |   Resumed   +-------> Active
   +-------------+
```

---

## 1.8 LLM Communication Tracking

Every LLM call during an investigation is captured as a paired request/response in the binder. This enables full reproducibility, cost tracking, and debugging of LLM interactions.

### `record_llm_request()` Method

```python
def record_llm_request(
    self,
    persona: str,          # Which persona made the request
    prompt_key: str,       # e.g., "hypothesis_generation"
    system_prompt: str,    # Full system prompt text
    user_prompt: str,      # Full user prompt text
    model: str,            # Model name (e.g., "gpt-4")
    temperature: float = 0.1,
    max_tokens: int = 4096,
    phase: int | None = None,
) -> str  # Returns artifact ID
```

Creates an `LLMRequestArtifact` and adds it to the binder. The `created_by` field is set to the `persona` value. The `linked_response_id` is initially `None` and will be populated when the response is recorded.

### `record_llm_response()` Method

```python
def record_llm_response(
    self,
    request_id: str,                           # ID of the corresponding request
    raw_response: str,                         # Full raw LLM output text
    parsed_content: dict[str, Any] | None,     # Parsed JSON/structured content
    tokens_used: int,                          # Token count
    latency_ms: float,                         # Response time in milliseconds
    parse_success: bool,                       # Whether parsing succeeded
    parse_errors: list[str] | None = None,     # Any parse errors encountered
    phase: int | None = None,
) -> str  # Returns artifact ID
```

Creates an `LLMResponseArtifact` linked to the request via `linked_request_id`. After creating the response artifact, it also updates the request artifact's `linked_response_id` to point back to the response, creating a bidirectional link. The `created_by` field is extracted from the request artifact's `persona` field.

### Exchange Pairing

The bidirectional linking between request and response artifacts works as follows:

1. `record_llm_request()` creates an `LLMRequestArtifact` with `linked_response_id=None`
2. The LLM call is made externally
3. `record_llm_response()` creates an `LLMResponseArtifact` with `linked_request_id=request_id`
4. `record_llm_response()` then updates the request artifact: `linked_response_id = response_id`

After both calls, either artifact can be used to find its partner:
- Request -> Response: via `request.linked_response_id`
- Response -> Request: via `response.linked_request_id`

### `get_llm_exchanges()` Method

```python
def get_llm_exchanges(
    self, phase: int | None = None
) -> list[tuple[LLMRequestArtifact, LLMResponseArtifact | None]]
```

Returns all LLM request/response pairs, sorted by `request_timestamp`. If `phase` is provided, filters to only that phase's exchanges. The response element is `None` if no linked response exists (e.g., if the LLM call failed before a response was recorded).

### `get_llm_statistics()` (BinderStore Only)

The `BinderStore` persistence layer provides a `get_llm_statistics(binder_id)` method that computes aggregate token usage and latency statistics by persona and phase. This method queries the persisted artifacts in SQLite and is not available on the in-memory `WorkBinder` class.

### LLM Artifact Fields Reference

**LLMRequestArtifact** (extends Artifact):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `persona` | `str` | (required) | Which persona made the request |
| `prompt_key` | `str` | (required) | Identifier for the prompt type (e.g., `"hypothesis_generation"`) |
| `system_prompt` | `str` | (required) | Full system prompt text |
| `user_prompt` | `str` | (required) | Full user prompt text |
| `model` | `str` | (required) | Model name used |
| `temperature` | `float` | `0.1` | Temperature parameter |
| `max_tokens` | `int` | `4096` | Maximum tokens requested |
| `request_timestamp` | `datetime` | `datetime.now()` | When the request was made |
| `linked_response_id` | `str \| None` | `None` | ID of the paired response artifact |

**LLMResponseArtifact** (extends Artifact):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `linked_request_id` | `str` | (required) | ID of the paired request artifact |
| `raw_response` | `str` | (required) | Full raw LLM output text |
| `parsed_content` | `dict[str, Any] \| None` | `None` | Parsed structured content |
| `tokens_used` | `int` | `0` | Token count for this response |
| `latency_ms` | `float` | `0.0` | Response time in milliseconds |
| `response_timestamp` | `datetime` | `datetime.now()` | When the response was received |
| `parse_success` | `bool` | `True` | Whether JSON parsing succeeded |
| `parse_errors` | `list[str]` | `[]` | Parse error messages (if any) |

---

## 1.9 Evidence-Hypothesis Linking

The WorkBinder provides bidirectional linking between evidence and hypotheses, enabling the investigation pipeline to track which evidence supports or contradicts which hypotheses.

### `link_evidence_to_hypothesis()` Method

```python
def link_evidence_to_hypothesis(
    self,
    evidence_id: str,
    hypothesis_id: str,
    relationship: str,        # "supports" or "contradicts"
    modified_by: str = "system",
) -> None
```

This method performs the following steps:

1. **Validates both references** -- calls `validate_artifact_reference()` on both IDs, ensuring each exists, is not deleted, and is the correct type (`EvidenceArtifact` or `HypothesisArtifact`)

2. **Updates the evidence artifact** -- appends `hypothesis_id` to either `supports_hypothesis_ids` (if `relationship == "supports"`) or `contradicts_hypothesis_ids` (if `relationship == "contradicts"`)

3. **Updates the hypothesis artifact** -- appends `evidence_id` to either `supporting_evidence_ids` (if `relationship == "supports"`) or `contradicting_evidence_ids` (if `relationship == "contradicts"`)

4. **Deduplicates** -- checks whether the ID is already in the list before appending, preventing duplicate links

5. **Records history** -- each `update_artifact()` call records an `ArtifactHistory` entry

**Atomicity note:** This method performs two `update_artifact()` calls (one for the evidence, one for the hypothesis). These are not wrapped in a database transaction at the in-memory binder level. If the second update fails (e.g., due to a validation error), the first update will have already been applied. In practice this is unlikely since both references are validated upfront in step 1, but callers should be aware that partial linking is theoretically possible. The `BinderStore` persistence layer handles this atomically by wrapping `save_binder()` in a SQLite transaction.

### Bidirectional ID Lists

**HypothesisArtifact** linking fields:

| Field | Type | Description |
|-------|------|-------------|
| `supporting_evidence_ids` | `list[str]` | IDs of `EvidenceArtifact`s that support this hypothesis |
| `contradicting_evidence_ids` | `list[str]` | IDs of `EvidenceArtifact`s that contradict this hypothesis |

**EvidenceArtifact** linking fields:

| Field | Type | Description |
|-------|------|-------------|
| `supports_hypothesis_ids` | `list[str]` | IDs of `HypothesisArtifact`s this evidence supports |
| `contradicts_hypothesis_ids` | `list[str]` | IDs of `HypothesisArtifact`s this evidence contradicts |

### Targeting Fields on EvidenceArtifact

In addition to the linking fields that are populated by `link_evidence_to_hypothesis()`, the `EvidenceArtifact` has targeting fields set at creation time via `add_evidence()`:

| Field | Type | Description |
|-------|------|-------------|
| `targets_hypothesis_id` | `str \| None` | The hypothesis this evidence was specifically gathered to test |
| `expected_if_true` | `str \| None` | What we would expect to find if the target hypothesis is correct |
| `expected_if_false` | `str \| None` | What we would expect to find if the target hypothesis is incorrect |
| `found` | `bool` | `True` if the evidence was found; `False` for absence evidence |

These fields support counterfactual reasoning in the evidence-seeking phase. The Detective generates queries that target specific hypotheses and records what was expected vs. what was found, enabling discriminating evidence analysis.

### Reference Validation in Linking Operations

The following convenience methods validate their artifact references before creating artifacts:

| Method | Validates | Expected Type |
|--------|-----------|---------------|
| `link_evidence_to_hypothesis()` | `evidence_id`, `hypothesis_id` | `EvidenceArtifact`, `HypothesisArtifact` |
| `add_causal_chain()` | `hypothesis_id` | `HypothesisArtifact` |
| `add_challenge()` | `target_hypothesis_id` | `HypothesisArtifact` |

All validation uses `validate_artifact_reference()` which raises `ValueError` immediately on invalid references. There is no backward-compatibility mode that silently accepts bad references.

### Example Linking Flow

```python
# Phase 1: Theorist creates hypotheses
hyp_id = binder.add_hypothesis(
    description="Buffer overflow in processData",
    source="fresh",
    prior_probability=0.3,
    created_by="Theorist",
    phase=1,
)

# Phase 2: Detective creates evidence
ev_id = binder.add_evidence(
    evidence_type="code",
    content="No bounds check found in processData()",
    source="code_analysis",
    strength="STRONG",
    created_by="Detective",
    phase=2,
    targets_hypothesis_id=hyp_id,
    expected_if_true="No bounds check before buffer access",
    expected_if_false="Bounds check present with proper error handling",
)

# Phase 2: Detective links evidence to hypothesis
binder.link_evidence_to_hypothesis(ev_id, hyp_id, "supports")

# After linking:
# - hypothesis.supporting_evidence_ids == [ev_id]
# - evidence.supports_hypothesis_ids == [hyp_id]
```

---

## 1.10 Artifact Data Flow Diagram

The following diagram shows the complete flow of artifacts through the investigation pipeline, from Phase -1 (multi-file triage) through Phase 7 (learning). Cross-cutting artifacts (LLM tracking, phase state, findings, annotations) are produced at every phase but are omitted from the per-phase columns for clarity.

### Full Pipeline Artifact Flow

```
+===========================================================================+
|                              WORKBINDER                                    |
|                     (Central Artifact Store)                               |
|                                                                            |
|  Internal Storage:                                                         |
|    _artifacts    : dict[str, Artifact]     (all artifacts by ID)          |
|    _history      : list[ArtifactHistory]   (modification audit trail)     |
|    _tags_index   : dict[str, set[str]]     (tag -> artifact IDs)          |
|    _function_index: dict[str, set[str]]    (function -> artifact IDs)     |
|    _audit_log    : list[AuditLogEntry]     (access audit trail)           |
+===========================================================================+
         |              |              |              |              |
         v              v              v              v              v
+-------------+  +-------------+  +-------------+  +-------------+  +--------+
| Phase -1    |  | Phase 0     |  | Phase 1     |  | Phase 2     |  | Phase 3|
| Chronicler  |  | Archivist   |  | Theorist    |  | Detective   |  |Logician|
+------+------+  +------+------+  +------+------+  +------+------+  +---+----+
       |                |                |                |              |
  WRITES:          WRITES:          READS:           READS:         READS:
  LOG_BUNDLE       FLOW_CONFIG      LOG_BUNDLE       LOG_BUNDLE    LOG_BUNDLE
  MERGED_TIMELINE
                   INV_STATE        ERROR_CONTEXT    ERROR_CONTEXT ERROR_CTX
                   ERROR_CONTEXT    SOURCE_LOC       SOURCE_LOC    SOURCE_LOC
                   SOURCE_LOC       CALL_GRAPH       CALL_GRAPH    CALL_GRAPH
                   CALL_GRAPH       CODE_SNIPPET     CODE_SNIPPET  CODE_SNIP
                   CODE_SNIPPET     FUNC_SUMMARY     FUNC_SUMMARY  FUNC_SUM
                   FUNC_SUMMARY                      HYPOTHESIS    HYPOTHESIS
                   PHASE_STATE      WRITES:                        EVIDENCE
                                    HYPOTHESIS       WRITES:
                                                     EVIDENCE      WRITES:
                                                                   CAUSAL_CHAIN
       |                |                |                |              |
       v                v                v                v              v
+===========================================================================+
|                              WORKBINDER                                    |
+===========================================================================+
         |              |              |              |
         v              v              v              v
+-------------+  +-------------+  +-------------+  +-------------+
| Phase 4     |  | Phase 5     |  | Phase 6     |  | Phase 7     |
| Devil's Advocate     |  | Judge       |  | Synthesizer |  | Learner     |
+------+------+  +------+------+  +------+------+  +------+------+
       |                |                |                |
  READS:           READS:           READS:           READS:
  All prior        All prior        ALL artifacts    ALL artifacts
  artifacts        artifacts
                                    WRITES:          WRITES:
  WRITES:          WRITES:          CONCLUSION       (patterns to
  CHALLENGE        (outcome                          knowledge base,
                   determination                     not binder
                   updates                           artifacts)
                   INV_STATE)
       |                |                |                |
       v                v                v                v
+===========================================================================+
|                              WORKBINDER                                    |
|                                                                            |
|  Cross-cutting artifacts written at every phase:                           |
|    LLM_REQUEST / LLM_RESPONSE  (every LLM call, bidirectionally linked)   |
|    PHASE_STATE                 (start_phase / complete_phase / fail_phase) |
|    FINDING                     (any persona observation)                   |
|    ANNOTATION                  (any persona note on an artifact)           |
|    PERSONA_CONTRIBUTION        (any persona's structured contribution)     |
|                                                                            |
|  State artifacts (written once, updated throughout):                       |
|    INVESTIGATION_STATE         (current_phase, status, outcome)            |
|    FLOW_CONFIG                 (frozen at investigation start)             |
+===========================================================================+
```

### Sequential Data Flow Summary

| Phase | Persona | Reads From Binder | Writes To Binder |
|-------|---------|-------------------|------------------|
| -1 | Chronicler | (external log files) | `LOG_BUNDLE`, `MERGED_TIMELINE`, `BOARDREADER_IDENTIFICATION` |
| 0 | Archivist | `LOG_BUNDLE` (if present) | `FLOW_CONFIG`, `INVESTIGATION_STATE`, `ERROR_CONTEXT`, `SOURCE_LOCATION`, `CALL_GRAPH`, `CODE_SNIPPET`, `FUNCTION_SUMMARY`, `PHASE_STATE` |
| 1 | Theorist | `ERROR_CONTEXT`, `SOURCE_LOCATION`, `CALL_GRAPH`, `CODE_SNIPPET`, `FUNCTION_SUMMARY`, `LOG_BUNDLE` | `HYPOTHESIS_ARTIFACT` |
| 2 | Detective | Phase 0 artifacts + `HYPOTHESIS_ARTIFACT` | `EVIDENCE_ARTIFACT` |
| 3 | Logician | Phase 0 artifacts + `HYPOTHESIS_ARTIFACT` + `EVIDENCE_ARTIFACT` | `CAUSAL_CHAIN` |
| 4 | Devil's Advocate | All prior artifacts | `CHALLENGE` |
| 5 | Judge | All prior artifacts | (updates `INVESTIGATION_STATE` with outcome) |
| 6 | Synthesizer | All artifacts | `CONCLUSION` |
| 7 | Learner | All artifacts | (patterns stored in knowledge base, not as binder artifacts) |

### Artifact Type Detailed Reference

The following sections provide the complete field listing for each artifact type, grouped by category.

#### Original Artifacts

**CallGraphNode** -- Call graph centered on a function:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `center_function` | `str` | (required) | Function at the center of the graph |
| `callers` | `list[CallerInfo]` | `[]` | Functions that call the center function |
| `callees` | `list[CalleeInfo]` | `[]` | Functions called by the center function |
| `depth_explored` | `int` | `1` | Call graph traversal depth |
| `diagram` | `str \| None` | `None` | ASCII diagram representation |

**CodeSnippet** -- Source code fragment:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_path` | `str` | (required) | Path to source file |
| `start_line` | `int` | (required) | First line number |
| `end_line` | `int` | (required) | Last line number |
| `content` | `str` | (required) | Actual source code text |
| `language` | `str` | `"cpp"` | Programming language |
| `snippet_function_name` | `str \| None` | `None` | Function this snippet is from |
| `summary` | `str \| None` | `None` | LLM-generated summary |
| `match_score` | `float \| None` | `None` | Match score for source location matches |

**Finding** -- Persona observation or conclusion:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `persona` | `str` | (required) | Persona making the finding |
| `finding_type` | `FindingType` | (required) | Category of finding |
| `content` | `str` | (required) | Finding text |
| `related_artifacts` | `list[str]` | `[]` | IDs of related artifacts |
| `confidence` | `float` | `0.5` | Confidence level (0.0-1.0) |

**Annotation** -- Note on another artifact:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_artifact_id` | `str` | (required) | ID of the artifact being annotated |
| `annotation_type` | `AnnotationType` | (required) | Category of annotation |
| `annotation_content` | `str` | (required) | Annotation text |

**SourceLocationArtifact** -- Error source location:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_path` | `str` | (required) | Path to source file |
| `line_number` | `int` | (required) | Line where error originates |
| `matched_line` | `str \| None` | `None` | Content of the matched line |
| `match_score` | `float` | `0.0` | Match confidence (0.0-1.0) |
| `is_log_statement` | `bool` | `False` | Whether this is a log macro |
| `function_signature` | `str \| None` | `None` | Enclosing function signature |
| `function_body` | `str \| None` | `None` | Enclosing function body |
| `context_before` | `list[str]` | `[]` | Source lines before the match |
| `context_after` | `list[str]` | `[]` | Source lines after the match |

**ErrorContextArtifact** -- Triggering error and context:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `error_message` | `str` | (required) | The triggering error message |
| `error_level` | `str` | `"ERROR"` | Log level |
| `error_component` | `str \| None` | `None` | Component that generated the error |
| `error_function` | `str \| None` | `None` | Function that generated the error |
| `error_timestamp` | `datetime \| None` | `None` | When the error occurred |
| `context_logs` | `list[dict[str, Any]]` | `[]` | Surrounding log entries |

**FunctionSummaryArtifact** -- Per-function LLM summary:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_path` | `str \| None` | `None` | Source file path |
| `purpose` | `str` | (required) | What the function does and why |
| `mechanism` | `str` | (required) | How it works -- key logic and transformations |
| `data_flow` | `str` | (required) | How data enters and exits |
| `error_paths` | `str` | (required) | Error handling and failure modes |
| `error_line_relevance` | `str` | (required) | How this relates to the error emission line |
| `center_function` | `str` | (required) | The error function this summary relates to |
| `role` | `str` | (required) | `"CALLER"` or `"CALLEE"` |

#### Multi-File Log Artifact

**LogBundleArtifact** -- Chronologically merged multi-file log bundle:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_files` | `list[dict[str, Any]]` | `[]` | Metadata about each source log file |
| `merged_timeline` | `str` | `""` | All files interleaved by timestamp |
| `annotated_narrative` | `str` | `""` | LLM-generated narrative interpreting the merged log |
| `primary_error` | `LogBundleErrorEntry \| None` | `None` | LLM-identified primary trigger error |
| `error_timeline` | `list[LogBundleErrorEntry]` | `[]` | All errors across all files in chronological order |
| `cascade_description` | `str` | `""` | How the primary error cascaded through the system |
| `clues` | `list[LogBundleClue]` | `[]` | Clues extracted for the Archivist |
| `affected_boards` | `list[BoardAnalysis]` | `[]` | Per-board structured analysis from Chronicler multi-file triage |
| `cascade_chain` | `list[CascadeLink]` | `[]` | Structured causal links in the failure cascade |
| `documentation_reference` | `str` | `""` | Compact doc reference for downstream phases |

**MergedTimelineArtifact** -- Chronologically merged timeline of parsed log entries:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `entries` | `list[MergedTimelineEntry]` | `[]` | Parsed log entries from all files |
| `total_entries` | `int` | `0` | Total number of entries |
| `total_errors` | `int` | `0` | Total error entries |
| `total_warnings` | `int` | `0` | Total warning entries |
| `total_info` | `int` | `0` | Total info entries |
| `file_count` | `int` | `0` | Number of source files |
| `earliest_timestamp` | `str` | `""` | Earliest timestamp in the timeline |
| `latest_timestamp` | `str` | `""` | Latest timestamp in the timeline |

**BoardReaderIdentificationArtifact** -- Boardreader identification from Phase -1:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `boardreader_types` | `list[str]` | `[]` | Identified boardreader types |
| `components` | `list[str]` | `[]` | Identified components |
| `error_messages` | `list[str]` | `[]` | Key error messages |
| `llm_request_id` | `str \| None` | `None` | LLM request that generated this identification |

#### Investigation Artifacts

**HypothesisArtifact** -- Hypothesis with evidence links:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | `str` | (required) | Root cause description |
| `source` | `str` | `"fresh"` | Origin: `"pattern_match"`, `"similar_case"`, `"fresh"`, `"alternative"` |
| `prior_probability` | `float` | `0.5` | Initial confidence (0.0-1.0) |
| `score` | `float` | `0.5` | Current score after evidence |
| `supporting_evidence_ids` | `list[str]` | `[]` | IDs of supporting evidence |
| `contradicting_evidence_ids` | `list[str]` | `[]` | IDs of contradicting evidence |
| `rank` | `int` | `0` | Position in ranked hypothesis list |
| `llm_request_id` | `str \| None` | `None` | ID of the LLM request that generated this hypothesis |
| `category` | `str \| None` | `None` | Category classification from LLM (e.g., timing, configuration) |
| `confirming_evidence` | `str \| None` | `None` | Description of evidence that would confirm |
| `refuting_evidence` | `str \| None` | `None` | Description of evidence that would refute |

**EvidenceArtifact** -- Evidence item:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `evidence_type` | `str` | (required) | `"log"`, `"code"`, `"pattern"`, `"dataflow"`, `"numeric"` |
| `content` | `str` | (required) | Evidence content/description |
| `source` | `str` | (required) | Where the evidence was found |
| `strength` | `str` | `"MODERATE"` | `"STRONG"`, `"MODERATE"`, `"WEAK"` |
| `supports_hypothesis_ids` | `list[str]` | `[]` | IDs of hypotheses this supports |
| `contradicts_hypothesis_ids` | `list[str]` | `[]` | IDs of hypotheses this contradicts |
| `llm_request_id` | `str \| None` | `None` | If evidence came from LLM query |
| `found` | `bool` | `True` | `False` for absence evidence |
| `timestamp` | `datetime` | `datetime.now()` | When evidence was gathered |
| `targets_hypothesis_id` | `str \| None` | `None` | Hypothesis this was gathered to test |
| `expected_if_true` | `str \| None` | `None` | Expected content if target hypothesis correct |
| `expected_if_false` | `str \| None` | `None` | Expected content if target hypothesis incorrect |

**CausalChainArtifact** -- Causal chain:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hypothesis_id` | `str` | (required) | ID of the hypothesis this chain supports |
| `steps` | `list[dict[str, Any]]` | `[]` | Chain steps (claim, mechanism, evidence, is_assumption) |
| `completeness_score` | `float` | `0.0` | Overall completeness score |
| `logical_validity` | `float` | `0.0` | Proportion of steps with mechanisms |
| `evidence_coverage` | `float` | `0.0` | Proportion of non-assumption steps |
| `gaps` | `list[str]` | `[]` | Identified gaps in the causal reasoning |
| `assumptions` | `list[str]` | `[]` | Assumptions made in the chain |
| `llm_request_id` | `str \| None` | `None` | LLM request that generated this chain |

**ChallengeArtifact** -- Adversarial challenge:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_hypothesis_id` | `str` | (required) | ID of the hypothesis being challenged |
| `challenge_type` | `str` | `""` | Type of challenge (e.g., `"evidence_gap"`, `"alternative_explanation"`, `"logical_flaw"`) |
| `content` | `str` | (required) | The challenge/objection text |
| `severity` | `str` | `"MEDIUM"` | `"HIGH"`, `"MEDIUM"`, `"LOW"` |
| `requires_response` | `bool` | `True` | Whether the challenge must be addressed |
| `resolved` | `bool` | `False` | Whether the challenge has been resolved |
| `resolution` | `str \| None` | `None` | Resolution text if resolved |
| `llm_request_id` | `str \| None` | `None` | LLM request that generated this challenge |

**ConclusionArtifact** -- Investigation conclusion:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `root_cause` | `str` | (required) | Final root cause determination |
| `confidence_raw` | `float` | `0.0` | Raw confidence (0.0-1.0) |
| `confidence_calibrated` | `float` | `0.0` | Calibrated confidence (0.0-1.0) |
| `outcome` | `str` | `"UNCERTAIN"` | `"CONFIDENT"`, `"PROBABLE"`, `"UNCERTAIN"`, `"CONTRADICTORY"`, `"INSUFFICIENT"` |
| `code_location` | `str \| None` | `None` | File:line of error |
| `code_snippet` | `str \| None` | `None` | Relevant code snippet |
| `data_flow` | `str \| None` | `None` | Call chain / data flow description |
| `caveats` | `list[str]` | `[]` | Caveats and limitations |
| `debugging_steps` | `list[str]` | `[]` | Recommended debugging steps |
| `unresolved_challenges` | `list[str]` | `[]` | Challenges not addressed |
| `llm_request_id` | `str \| None` | `None` | If conclusion came from LLM |

**PersonaContributionArtifact** -- Persona contribution:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `persona_id` | `str` | (required) | Persona identifier |
| `contribution_phase` | `int` | (required) | Phase when contribution was made |
| `content` | `dict[str, Any]` | `{}` | The actual contribution data |
| `confidence` | `float` | `0.5` | Persona's confidence (0.0-1.0) |
| `reasoning` | `str` | `""` | Explanation of the contribution |

#### State Management Artifacts

**FlowConfigArtifact** -- Configuration snapshot:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `investigation_config` | `dict[str, Any]` | `{}` | Investigation configuration |
| `llm_config` | `dict[str, Any]` | `{}` | LLM provider configuration |
| `source_config` | `dict[str, Any] \| None` | `None` | Source repository configuration |
| `pipeline_config` | `dict[str, Any] \| None` | `None` | Pipeline engine configuration |
| `enabled_phases` | `list[int]` | `[0, 1, 2, 3, 4, 5, 6, 7]` | Which phases are enabled |
| `phase_parameters` | `dict[str, dict[str, Any]]` | `{}` | Per-phase parameter overrides |

**PhaseStateArtifact** -- Per-phase lifecycle:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `phase_number` | `int` | (required) | Phase number (-1 through 7) |
| `persona_name` | `str` | (required) | Persona handling this phase |
| `status` | `str` | `"pending"` | `"pending"`, `"in_progress"`, `"completed"`, `"failed"` |
| `started_at` | `datetime \| None` | `None` | When the phase started |
| `completed_at` | `datetime \| None` | `None` | When the phase completed or failed |
| `input_artifact_ids` | `list[str]` | `[]` | IDs of artifacts consumed by this phase |
| `output_artifact_ids` | `list[str]` | `[]` | IDs of artifacts produced by this phase |
| `error_message` | `str \| None` | `None` | Error message if phase failed |

**InvestigationStateArtifact** -- Central state tracker:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `investigation_id` | `str` | (required) | Links to the Investigation model |
| `trigger_error_artifact_id` | `str \| None` | `None` | ID of the ErrorContextArtifact |
| `current_phase` | `int` | `0` | Current/next phase to execute |
| `outcome` | `str \| None` | `None` | InvestigationOutcome value |
| `status` | `str` | `"active"` | `"active"`, `"completed"`, `"failed"`, `"paused"` |
| `started_at` | `datetime` | `datetime.now()` | When the investigation started |
| `completed_at` | `datetime \| None` | `None` | When the investigation completed |
| `paused_at` | `datetime \| None` | `None` | When the investigation was paused |
| `pause_reason` | `str \| None` | `None` | Reason for pausing |
| `resume_count` | `int` | `0` | How many times the investigation has been resumed |

---

> **Agentic WorkBinder Library -- Ch. 1: Architecture & Core API** | [Table of Contents](agentic-workbinder-library.md) | [Next: Ch. 2: Context Artifacts ->](agentic-workbinder-library-ch2-context-artifacts.md)
