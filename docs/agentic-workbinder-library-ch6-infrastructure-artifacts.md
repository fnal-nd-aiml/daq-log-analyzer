> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 5: Observation Artifacts](agentic-workbinder-library-ch5-observation-artifacts.md) | [Next: Ch. 7: Tools, Serialization & Parsing](agentic-workbinder-library-ch7-tools-serialization.md)

---

# Chapter 6: Infrastructure Artifacts

Chapters 3 and 4 documented the pipeline artifacts that carry the investigation's primary data. Chapter 5 covered the cross-cutting observation artifacts that any persona can create for commentary and contribution tracking. This chapter documents the final artifact category: **infrastructure artifacts** -- the operational machinery that makes investigations reproducible, resumable, and debuggable.

Infrastructure artifacts are not part of the investigation's intellectual content. They do not contain hypotheses, evidence, causal reasoning, or conclusions. Instead, they record:

- **Where the investigation is** (InvestigationStateArtifact, PhaseStateArtifact)
- **How the investigation was configured** (FlowConfigArtifact)
- **What the LLM was asked and what it answered** (LLMRequestArtifact, LLMResponseArtifact)

These five artifact types are critical for three operational concerns:

1. **Pause/resume workflows**: The InvestigationStateArtifact and PhaseStateArtifacts enable an investigation to be paused at any point, persisted to SQLite, and resumed later from the exact phase where it stopped. The agentic REST API exposes this through the `GET /binders/resumable` and investigation lifecycle endpoints.

2. **Investigation reproducibility**: The FlowConfigArtifact captures the complete configuration snapshot at investigation start -- LLM provider, model, temperature, enabled phases, source repository configuration, and pipeline parameters. Given a FlowConfigArtifact and the same input log, the investigation should produce similar results.

3. **LLM traceability and debugging**: The LLMRequestArtifact and LLMResponseArtifact pair captures every LLM interaction during the investigation. When a phase produces unexpected results, developers can inspect the exact prompts sent and responses received, measure token consumption and latency, and identify parse failures. This complete audit trail is essential for debugging the agent itself.

```
Infrastructure Artifact Relationships
======================================

FlowConfigArtifact (1 per investigation)
  |
  |  captures configuration at start
  v
InvestigationStateArtifact (1 per investigation)
  |
  |  tracks overall progress, pause/resume
  |
  ├──► PhaseStateArtifact (1 per phase, up to 8)
  |      |
  |      |  tracks per-phase execution
  |      |
  |      └──► input_artifact_ids ──► artifacts from prior phases
  |      └──► output_artifact_ids ──► artifacts produced by this phase
  |
  └──► trigger_error_artifact_id ──► ErrorContextArtifact

LLMRequestArtifact ◄──► LLMResponseArtifact
  |                         |
  |  linked_response_id ──► |  linked_request_id
  |                         |
  |  per-call record        |  per-call record
  v                         v
  (many per investigation, paired 1:1)
```

All five infrastructure artifact types inherit from the common `Artifact` base class and share the standard lifecycle operations (add, update, soft-delete, restore, history tracking). Unlike pipeline artifacts, several infrastructure artifacts are **mutable** -- InvestigationStateArtifact and PhaseStateArtifact are updated as the investigation progresses, and LLMRequestArtifact is updated to link its response after the LLM call completes.

---

## 6.1 InvestigationStateArtifact

### 1. Purpose & Role

The InvestigationStateArtifact is the central state tracker for an investigation. There is exactly one instance per WorkBinder, created at the start of the investigation and updated as each phase completes or the investigation pauses/resumes.

This artifact answers the fundamental question: "What is the current state of this investigation?" It tracks:

- **Current phase**: Which phase the investigation is currently in or about to enter
- **Status**: Whether the investigation is active, completed, failed, or paused
- **Outcome**: The investigation's final determination (CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT), set when the investigation completes
- **Pause/resume state**: When the investigation was paused, why, and how many times it has been resumed

In the agentic REST API context, the InvestigationStateArtifact is the primary artifact that the session management layer reads to determine investigation lifecycle state. The `GET /binders/{id}/state` endpoint returns this artifact directly, and the `GET /binders/{id}/summary` endpoint derives its response from it. The `GET /binders/resumable` endpoint scans for InvestigationStateArtifacts with `status == "paused"`.

### 2. Schema

**Class**: `InvestigationStateArtifact` in `srcs/workbinder/artifacts_types.py` (line 306)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.INVESTIGATION_STATE` | Always `"investigation_state"` |
| `created_by` | `str` | *(required)* | Typically `"system"` |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Set to `0` at creation |
| `function_name` | `str \| None` | `None` | Not typically used |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `investigation_id` | `str` | *(required)* | Links to the Investigation model ID |
| `trigger_error_artifact_id` | `str \| None` | `None` | Links to the ErrorContextArtifact that triggered this investigation |
| `current_phase` | `int` | `0` | Phase the investigation is currently in or about to enter (0-7) |
| `outcome` | `str \| None` | `None` | Investigation outcome: CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT |
| `status` | `str` | `"active"` | Lifecycle status: `active`, `completed`, `failed`, `paused` |
| `started_at` | `datetime` | `datetime.now()` | When the investigation started |
| `completed_at` | `datetime \| None` | `None` | When the investigation completed (or failed) |
| `paused_at` | `datetime \| None` | `None` | When the investigation was paused |
| `pause_reason` | `str \| None` | `None` | Human-readable reason for pausing |
| `resume_count` | `int` | `0` | How many times this investigation has been resumed |

**Status lifecycle**:

```
                          ┌──────────┐
                          │  active  │◄────── resume_investigation()
                          └────┬─────┘            ▲
                               │                  │
                    ┌──────────┼──────────┐       │
                    │          │          │       │
                    ▼          ▼          ▼       │
              ┌──────────┐ ┌────────┐ ┌────────┐ │
              │completed │ │ failed │ │ paused ├─┘
              └──────────┘ └────────┘ └────────┘
```

### 3. Producer

**Who creates it**: The `InvestigationCoordinator` at the start of the investigation (Phase 0 initialization).

**WorkBinder convenience method**: `binder.add_investigation_state()`

```python
def add_investigation_state(
    self,
    investigation_id: str,
    trigger_error_artifact_id: str | None = None,
    created_by: str = "system",
) -> str:
```

The method creates an InvestigationStateArtifact with `current_phase=0`, `status="active"`, and `started_at=datetime.now()`. The `phase` field on the base Artifact is set to `0`.

**Update methods** (mutate the existing artifact):

| Method | Effect |
|--------|--------|
| `binder.complete_phase(phase, output_ids)` | Increments `current_phase` to `phase + 1` |
| `binder.pause_investigation(reason)` | Sets `status="paused"`, records `paused_at` and `pause_reason` |
| `binder.resume_investigation()` | Sets `status="active"`, clears pause fields, increments `resume_count` |
| `binder.update_investigation_state(**updates)` | Generic update for `outcome`, `completed_at`, `status`, etc. |

### 4. Consumers

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| InvestigationCoordinator | `current_phase`, `status` | Determines which phase to execute next; skips if investigation is completed/failed |
| Resume logic | `status`, `current_phase`, `resume_count` | `binder.can_resume()` checks `status == "paused"`; `binder.get_resume_point()` reads `current_phase` |
| REST API `/binders/{id}/state` | Full artifact | Returns investigation lifecycle state to client |
| REST API `/binders/{id}/summary` | `current_phase`, `outcome`, `status`, `resume_count` | Builds investigation summary response |
| REST API `/binders/resumable` | `status == "paused"` | Lists paused investigations available for resume |
| MCP `get_investigation_state` | Full artifact | Returns state for MCP client inspection |
| MCP `list_investigations_with_state` | `status`, `outcome`, `current_phase` | Filtered listing across all investigations |

### 5. REST API Exposure

**Dedicated endpoint** -- `GET /binders/{binder_id}/state`:

```
GET /api/v1/binders/{binder_id}/state
```

Returns an `InvestigationStateResponse` wrapping the full artifact:

```json
{
  "artifact": {
    "id": "is-a1b2c3d4",
    "artifact_type": "investigation_state",
    "created_by": "system",
    "created_at": "2026-02-14T10:30:01.003Z",
    "updated_at": "2026-02-14T10:42:15.891Z",
    "phase": 0,
    "function_name": null,
    "priority": "normal",
    "tags": [],
    "is_deleted": false,
    "content": {
      "investigation_id": "inv-e5f6a7b8",
      "trigger_error_artifact_id": "ec-c3d4e5f6",
      "current_phase": 6,
      "outcome": null,
      "status": "active",
      "started_at": "2026-02-14T10:30:01.003Z",
      "completed_at": null,
      "paused_at": null,
      "pause_reason": null,
      "resume_count": 0
    }
  }
}
```

**Summary endpoint** -- `GET /binders/{binder_id}/summary`:

```
GET /api/v1/binders/{binder_id}/summary
```

Returns a `BinderInvestigationSummaryResponse` derived from the InvestigationStateArtifact:

| Response Field | Source |
|---------------|--------|
| `current_phase` | `InvestigationStateArtifact.current_phase` |
| `outcome` | `InvestigationStateArtifact.outcome` |
| `status` | Binder status (synced with investigation status) |
| `resume_count` | `InvestigationStateArtifact.resume_count` |
| `artifact_counts` | Aggregated from all artifacts in binder |

**Resumable endpoint** -- `GET /binders/resumable`:

```
GET /api/v1/binders/resumable
```

Returns a list of `ResumableInvestigationResponse` objects for all investigations with `status == "paused"`.

**Cross-binder listing** -- `GET /binders/investigations`:

```
GET /api/v1/binders/investigations?outcome=CONFIDENT&status=active&limit=50
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `outcome` | `str` | Filter by outcome (CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT) |
| `status` | `str` | Filter by binder status (active, paused, archived) |
| `limit` | `int` | Maximum results (default 50) |

### 6. MCP Tool Access

| MCP Tool | Parameters | Returns |
|----------|------------|---------|
| `get_investigation_state` | `binder_id` | JSON object with full InvestigationStateArtifact |
| `list_investigations_with_state` | `outcome`, `status`, `limit` | JSON array of investigation summaries with state |
| `list_resumable_investigations` | *(none)* | JSON array of paused investigations |
| `find_similar_investigations` | `error_function`, `error_message_pattern`, `limit` | JSON array of similar investigations |

Example MCP tool call:

```json
{
  "tool": "get_investigation_state",
  "arguments": {
    "binder_id": "wb-a1b2c3d4"
  }
}
```

### 7. Artifact Relationships

The InvestigationStateArtifact sits at the center of the infrastructure artifact graph. It links downward to the ErrorContextArtifact that triggered the investigation, and it is implicitly linked to all PhaseStateArtifacts through the shared `investigation_id`.

```
                    ┌────────────────────────────────┐
                    │   InvestigationStateArtifact   │
                    │   investigation_id: "inv-..."  │
                    │   current_phase: 6             │
                    │   status: "active"             │
                    │   trigger_error_artifact_id ───┼──► ErrorContextArtifact
                    └────────────┬───────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ PhaseState (0)  │ │ PhaseState (1)  │ │ PhaseState (6)  │
    │ status:complete │ │ status:complete │ │ status:in_prog  │
    │ output_ids:[...│ │ output_ids:[...│ │ output_ids:[]   │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
              │                  │
              ▼                  ▼
    FlowConfigArtifact   LLMRequest/Response pairs
    (captured at start)   (per-phase LLM interactions)
```

### 8. Session State Mapping

| Session State Concept | Artifact Field | Client View |
|----------------------|---------------|-------------|
| Investigation progress | `current_phase` | Progress bar / phase indicator (0-7) |
| Investigation status | `status` | Status badge (active, completed, failed, paused) |
| Final outcome | `outcome` | Outcome determination with confidence |
| Pause state | `paused_at`, `pause_reason` | Pause notification with reason |
| Resume history | `resume_count` | Count of investigation resumes |
| Investigation timing | `started_at`, `completed_at` | Duration display |
| Trigger error link | `trigger_error_artifact_id` | Clickable link to the triggering error |

The InvestigationStateArtifact is the single artifact that the client polls to determine whether the investigation is still running, has completed, or has been paused. In a streaming investigation, the client watches for updates to this artifact to update its progress display.

### 9. Example

Full realistic JSON as returned by `GET /api/v1/binders/{binder_id}/state`:

```json
{
  "artifact": {
    "id": "is-7a8b9c0d",
    "artifact_type": "investigation_state",
    "created_by": "system",
    "created_at": "2026-02-14T10:30:01.003Z",
    "updated_at": "2026-02-14T10:45:32.118Z",
    "phase": 0,
    "function_name": null,
    "priority": "normal",
    "tags": [],
    "is_deleted": false,
    "content": {
      "investigation_id": "inv-e5f6a7b8",
      "trigger_error_artifact_id": "ec-c3d4e5f6",
      "current_phase": 7,
      "outcome": "PROBABLE",
      "status": "completed",
      "started_at": "2026-02-14T10:30:01.003Z",
      "completed_at": "2026-02-14T10:45:32.118Z",
      "paused_at": null,
      "pause_reason": null,
      "resume_count": 0
    }
  }
}
```

---

## 6.2 PhaseStateArtifact

### 1. Purpose & Role

A PhaseStateArtifact tracks the execution state of a single investigation phase. There is one PhaseStateArtifact per phase that has been started (up to 8 for phases 0-7). Each artifact records when the phase started, when it completed (or failed), which artifacts it consumed as input, and which artifacts it produced as output.

PhaseStateArtifacts provide the per-phase granularity that InvestigationStateArtifact lacks. While InvestigationStateArtifact tells you "the investigation is at phase 4," the PhaseStateArtifacts tell you "Phase 0 completed in 3.2 seconds with 7 output artifacts, Phase 1 completed in 1.8 seconds with 3 output artifacts, Phase 2 completed in 12.4 seconds with 15 output artifacts, Phase 3 is currently in progress."

In the agentic REST API context, PhaseStateArtifacts enable detailed progress tracking. The `GET /binders/{id}/phases` endpoint returns all phase states, and the client can use them to display per-phase timing, status, and artifact counts. During a streaming investigation, the client watches PhaseStateArtifact updates to know when each phase starts and finishes.

### 2. Schema

**Class**: `PhaseStateArtifact` in `srcs/workbinder/artifacts_types.py` (line 288)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.PHASE_STATE` | Always `"phase_state"` |
| `created_by` | `str` | *(required)* | Persona name for this phase |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Set to `phase_number` at creation |
| `function_name` | `str \| None` | `None` | Not typically used |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `phase_number` | `int` | *(required)* | Phase number (0-7) |
| `persona_name` | `str` | *(required)* | Persona handling this phase |
| `status` | `str` | `"pending"` | Phase status: `pending`, `in_progress`, `completed`, `failed` |
| `started_at` | `datetime \| None` | `None` | When phase execution started |
| `completed_at` | `datetime \| None` | `None` | When phase execution completed (or failed) |
| `input_artifact_ids` | `list[str]` | `[]` | IDs of artifacts consumed as input to this phase |
| `output_artifact_ids` | `list[str]` | `[]` | IDs of artifacts produced by this phase |
| `error_message` | `str \| None` | `None` | Error message if phase failed |

**Status lifecycle**:

```
┌─────────┐  start_phase()  ┌─────────────┐  complete_phase()  ┌───────────┐
│ pending ├────────────────►│ in_progress ├───────────────────►│ completed │
└─────────┘                 └──────┬──────┘                    └───────────┘
                                   │
                                   │ fail_phase()
                                   ▼
                            ┌──────────┐
                            │  failed  │
                            └──────────┘
```

### 3. Producer

**Who creates it**: The `InvestigationCoordinator` via `binder.start_phase()` at the beginning of each phase.

**WorkBinder convenience methods**:

```python
def start_phase(self, phase: int, persona_name: str) -> str:
```

Creates a new PhaseStateArtifact with `status="in_progress"` and `started_at=datetime.now()`, or updates an existing one if the phase was previously started (e.g., on resume).

```python
def complete_phase(
    self, phase: int, output_ids: list[str], modified_by: str = "system"
) -> None:
```

Updates the PhaseStateArtifact to `status="completed"`, sets `completed_at=datetime.now()`, and records `output_artifact_ids`. Also increments `current_phase` on the InvestigationStateArtifact.

```python
def fail_phase(
    self, phase: int, error_message: str, modified_by: str = "system"
) -> None:
```

Updates the PhaseStateArtifact to `status="failed"`, sets `completed_at=datetime.now()`, and records `error_message`.

**Retrieval method**:

```python
def get_phase_state(self, phase: int) -> PhaseStateArtifact | None:
```

Returns the PhaseStateArtifact for a specific phase number, or None if that phase has not been started.

### 4. Consumers

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| InvestigationCoordinator | `status` for each phase | Determines which phases need execution; skips completed phases on resume |
| Resume logic (`get_resume_point`) | `status` of current and previous phases | Determines exact resume point: resumes from in_progress phase, or previous phase if current is not started |
| REST API `/binders/{id}/phases` | All PhaseStateArtifacts | Returns per-phase progress to client |
| MCP `get_phase_states` | All PhaseStateArtifacts with optional status filter | Per-phase status for MCP clients |
| Quality analysis | `output_artifact_ids` per phase | Counts artifacts produced per phase for quality metrics |

### 5. REST API Exposure

**Dedicated endpoint** -- `GET /binders/{binder_id}/phases`:

```
GET /api/v1/binders/{binder_id}/phases
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | `str` | Filter by status: `pending`, `in_progress`, `completed`, `failed` |

Returns an `ArtifactListResponse` containing all PhaseStateArtifacts for the binder:

```json
{
  "artifacts": [
    {
      "id": "ps-1a2b3c4d",
      "artifact_type": "phase_state",
      "created_by": "Archivist",
      "created_at": "2026-02-14T10:30:02.115Z",
      "updated_at": "2026-02-14T10:33:15.442Z",
      "phase": 0,
      "function_name": null,
      "priority": "normal",
      "tags": [],
      "is_deleted": false,
      "content": {
        "phase_number": 0,
        "persona_name": "Archivist",
        "status": "completed",
        "started_at": "2026-02-14T10:30:02.115Z",
        "completed_at": "2026-02-14T10:33:15.442Z",
        "input_artifact_ids": [],
        "output_artifact_ids": [
          "ec-c3d4e5f6",
          "src-a1b2c3d4",
          "src-e5f6a7b8",
          "cg-1a2b3c4d",
          "cs-5e6f7a8b",
          "cs-9c0d1e2f",
          "fs-3a4b5c6d",
          "fs-7e8f9a0b"
        ],
        "error_message": null
      }
    },
    {
      "id": "ps-5e6f7a8b",
      "artifact_type": "phase_state",
      "created_by": "Theorist",
      "created_at": "2026-02-14T10:33:15.443Z",
      "updated_at": "2026-02-14T10:34:58.201Z",
      "phase": 1,
      "function_name": null,
      "priority": "normal",
      "tags": [],
      "is_deleted": false,
      "content": {
        "phase_number": 1,
        "persona_name": "Theorist",
        "status": "completed",
        "started_at": "2026-02-14T10:33:15.443Z",
        "completed_at": "2026-02-14T10:34:58.201Z",
        "input_artifact_ids": [],
        "output_artifact_ids": [
          "hyp-c3d4e5f6",
          "hyp-d4e5f6a7",
          "hyp-e5f6a7b8"
        ],
        "error_message": null
      }
    }
  ],
  "total": 2
}
```

Also accessible through the generic artifact endpoint:

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=phase_state
```

### 6. MCP Tool Access

| MCP Tool | Parameters | Returns |
|----------|------------|---------|
| `get_phase_states` | `binder_id`, optional `status` | JSON array of PhaseStateArtifacts |
| `search_artifacts` | `binder_id`, `artifact_type="phase_state"` | JSON array via generic search |
| `get_artifact` | `binder_id`, `artifact_id` | JSON object with full PhaseStateArtifact |

Example MCP tool call to get only completed phases:

```json
{
  "tool": "get_phase_states",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "status": "completed"
  }
}
```

### 7. Artifact Relationships

PhaseStateArtifacts have explicit links to the artifacts they consumed and produced:

```
                    PhaseStateArtifact (Phase 2)
                    ┌───────────────────────────────┐
                    │ phase_number: 2               │
                    │ persona_name: "Detective"     │
                    │ input_artifact_ids: ──────────┼──► HypothesisArtifact(s) from Phase 1
                    │   ["hyp-c3d4e5f6",           │──► SourceLocationArtifact(s) from Phase 0
                    │    "hyp-d4e5f6a7",           │──► CallGraphNode(s) from Phase 0
                    │    "src-a1b2c3d4"]           │
                    │                               │
                    │ output_artifact_ids: ─────────┼──► EvidenceArtifact(s) produced
                    │   ["ev-1a2b3c4d",            │──► Finding(s) produced
                    │    "ev-5e6f7a8b",            │
                    │    "ev-9c0d1e2f",            │
                    │    "fnd-3a4b5c6d"]           │
                    └───────────────────────────────┘
                                 ▲
                                 │ implicit link via phase_number
                                 │
                    ┌───────────────────────────────┐
                    │ InvestigationStateArtifact    │
                    │ current_phase: 3              │
                    │ (Phase 2 just completed)      │
                    └───────────────────────────────┘
```

The `input_artifact_ids` and `output_artifact_ids` fields are populated by the coordinator. Currently, `input_artifact_ids` is often left empty (the coordinator does not explicitly track inputs for each phase), while `output_artifact_ids` is populated by `complete_phase()`.

### 8. Session State Mapping

| Session State Concept | Artifact Field | Client View |
|----------------------|---------------|-------------|
| Phase name | `persona_name` | "Archivist", "Theorist", etc. |
| Phase progress | `status` | Status indicator per phase |
| Phase timing | `started_at`, `completed_at` | Duration display per phase |
| Phase outputs | `output_artifact_ids` | Artifact count badge per phase |
| Phase errors | `error_message` | Error display for failed phases |
| Phase number | `phase_number` | Position in progress bar (0-7) |

Clients can use PhaseStateArtifacts to build a detailed phase timeline showing which phase ran when, how long each took, and how many artifacts each produced. For failed investigations, the `error_message` on the failed phase indicates what went wrong.

### 9. Example

Full realistic JSON for a failed phase:

```json
{
  "id": "ps-c0d1e2f3",
  "artifact_type": "phase_state",
  "created_by": "Detective",
  "created_at": "2026-02-14T10:35:01.224Z",
  "updated_at": "2026-02-14T10:35:48.903Z",
  "phase": 2,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "phase_number": 2,
    "persona_name": "Detective",
    "status": "failed",
    "started_at": "2026-02-14T10:35:01.224Z",
    "completed_at": "2026-02-14T10:35:48.903Z",
    "input_artifact_ids": [],
    "output_artifact_ids": [
      "ev-1a2b3c4d",
      "ev-5e6f7a8b"
    ],
    "error_message": "LLM response parse failure: evidence query JSON contained trailing comma at position 847. 2 evidence items collected before failure."
  }
}
```

---

## 6.3 FlowConfigArtifact

### 1. Purpose & Role

The FlowConfigArtifact captures the complete investigation configuration at the moment the investigation starts. It is a snapshot -- not a live reference -- meaning that if the configuration changes after the investigation starts, the FlowConfigArtifact still reflects the original settings.

This artifact enables two critical capabilities:

1. **Reproducibility**: Given a FlowConfigArtifact and the same input log, a developer can reconstruct the exact configuration used for an investigation. This is essential for debugging unexpected results, since the LLM model, temperature, enabled phases, and pipeline parameters all affect the investigation outcome.

2. **Resume with original config**: When an investigation is paused and later resumed, the resume logic can read the FlowConfigArtifact to ensure the same configuration is used, even if the system's default configuration has changed since the investigation was started.

In the agentic REST API context, the FlowConfigArtifact is readable through the generic artifact endpoints. It provides clients with transparency about how an investigation was configured, which is important for comparing results across investigations with different settings.

### 2. Schema

**Class**: `FlowConfigArtifact` in `srcs/workbinder/artifacts_types.py` (line 272)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.FLOW_CONFIG` | Always `"flow_config"` |
| `created_by` | `str` | *(required)* | Typically `"system"` |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Always set to `0` (created at investigation start) |
| `function_name` | `str \| None` | `None` | Not used |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `investigation_config` | `dict[str, Any]` | `{}` | InvestigationConfig as dict: max_hypotheses, evidence_iterations, min_chain_score, etc. |
| `llm_config` | `dict[str, Any]` | `{}` | LLM provider config: provider name, model, temperature, max_tokens, endpoint |
| `source_config` | `dict[str, Any] \| None` | `None` | Source repository config: repo URLs, branches, local paths |
| `pipeline_config` | `dict[str, Any] \| None` | `None` | PipelineConfig if using the pipeline engine |
| `enabled_phases` | `list[int]` | `[0, 1, 2, 3, 4, 5, 6, 7]` | Which investigation phases are enabled |
| `phase_parameters` | `dict[str, dict[str, Any]]` | `{}` | Per-phase parameter overrides |

**Typical `investigation_config` keys**:

| Key | Type | Description |
|-----|------|-------------|
| `max_hypotheses` | `int` | Maximum hypotheses to generate |
| `evidence_iterations` | `int` | Maximum evidence-seeking iterations |
| `min_chain_score` | `float` | Minimum hypothesis score for chain building |
| `max_chains` | `int` | Maximum causal chains to build |
| `enable_auto_learning` | `bool` | Whether to extract patterns after investigation |
| `fast_path_threshold` | `float` | Confidence threshold for fast-path bypass |

**Typical `llm_config` keys**:

| Key | Type | Description |
|-----|------|-------------|
| `provider` | `str` | LLM provider name (`"ollama"`, `"anthropic"`) |
| `model` | `str` | Model identifier (e.g., `"qwen2.5:14b"`, `"claude-3-sonnet"`) |
| `temperature` | `float` | Default temperature |
| `max_tokens` | `int` | Default max tokens per request |
| `host` | `str` | Provider endpoint URL |

### 3. Producer

**Who creates it**: The `InvestigationCoordinator` at the start of Phase 0 initialization.

**WorkBinder convenience method**: `binder.add_flow_config()`

```python
def add_flow_config(
    self,
    investigation_config: dict[str, Any],
    llm_config: dict[str, Any],
    source_config: dict[str, Any] | None = None,
    pipeline_config: dict[str, Any] | None = None,
    enabled_phases: list[int] | None = None,
    phase_parameters: dict[str, dict[str, Any]] | None = None,
    created_by: str = "system",
) -> str:
```

The method sets the base Artifact `phase` field to `0`. If `enabled_phases` is not provided, it defaults to `list(range(8))` -- all phases enabled.

**Retrieval method**:

```python
def get_flow_config(self) -> FlowConfigArtifact | None:
```

Returns the single FlowConfigArtifact in the binder, or None if not yet created. There should be exactly one per investigation.

### 4. Consumers

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| Resume logic | `enabled_phases`, `investigation_config`, `llm_config` | Ensures resumed investigation uses original configuration |
| Debugging/inspection | All fields | Developers inspect to understand investigation settings |
| REST API client | All fields | Displays investigation configuration for transparency |
| Quality analysis | `llm_config.model`, `investigation_config` parameters | Compares results across different model/config combinations |

The FlowConfigArtifact is typically read-only after creation. It is not updated during the investigation.

### 5. REST API Exposure

FlowConfigArtifacts are accessed through the generic artifact endpoints:

**Search for the flow config**:

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=flow_config
```

Since there is exactly one FlowConfigArtifact per binder, this returns a single-element list.

**Get by artifact ID**:

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Response JSON snippet**:

```json
{
  "id": "fc-2b3c4d5e",
  "artifact_type": "flow_config",
  "created_by": "system",
  "created_at": "2026-02-14T10:30:01.005Z",
  "updated_at": "2026-02-14T10:30:01.005Z",
  "phase": 0,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "investigation_config": {
      "max_hypotheses": 5,
      "evidence_iterations": 10,
      "min_chain_score": 0.2,
      "max_chains": 3,
      "enable_auto_learning": true,
      "fast_path_threshold": 0.9
    },
    "llm_config": {
      "provider": "ollama",
      "model": "qwen2.5:14b",
      "temperature": 0.1,
      "max_tokens": 4096,
      "host": "http://localhost:11434"
    },
    "source_config": {
      "repositories": [
        {
          "name": "artdaq",
          "url": "https://github.com/art-daq/artdaq.git",
          "branch": "develop"
        }
      ],
      "local_path": "/data/repos"
    },
    "pipeline_config": null,
    "enabled_phases": [0, 1, 2, 3, 4, 5, 6, 7],
    "phase_parameters": {}
  }
}
```

### 6. MCP Tool Access

FlowConfigArtifacts are accessed through the generic MCP artifact tools:

| MCP Tool | Parameters | Returns |
|----------|------------|---------|
| `search_artifacts` | `binder_id`, `artifact_type="flow_config"` | JSON array (single element) |
| `get_artifact` | `binder_id`, `artifact_id` | Full FlowConfigArtifact JSON |

Example MCP tool call:

```json
{
  "tool": "search_artifacts",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "artifact_type": "flow_config"
  }
}
```

### 7. Artifact Relationships

The FlowConfigArtifact has no explicit artifact ID references. Its relationship to other artifacts is temporal -- it is created first and describes the configuration under which all subsequent artifacts were produced.

```
FlowConfigArtifact
┌───────────────────────────────────────┐
│ investigation_config: {...}           │
│ llm_config: {...}                     │      Governs all subsequent
│ source_config: {...}                  │──────artifacts and phases
│ enabled_phases: [0,1,2,3,4,5,6,7]    │
│ phase_parameters: {}                  │
└───────────────────────────────────────┘
         │
         │  created at investigation start (phase 0)
         │  read on resume to restore configuration
         ▼
┌───────────────────────────────────────┐
│ InvestigationStateArtifact            │
│ (created immediately after config)    │
└───────────────────────────────────────┘
```

### 8. Session State Mapping

| Session State Concept | Artifact Field | Client View |
|----------------------|---------------|-------------|
| LLM model used | `llm_config.model` | Model name badge |
| LLM provider | `llm_config.provider` | Provider indicator |
| Temperature setting | `llm_config.temperature` | Configuration detail |
| Investigation parameters | `investigation_config` | Settings panel |
| Enabled phases | `enabled_phases` | Phase toggle indicators |
| Source repositories | `source_config` | Repository links |

Clients display FlowConfigArtifact data in an "Investigation Settings" panel, providing transparency about the exact configuration used. This is particularly useful when comparing investigations that used different models or parameter settings.

### 9. Example

Full realistic JSON as returned by `GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}`:

```json
{
  "id": "fc-9d0e1f2a",
  "artifact_type": "flow_config",
  "created_by": "system",
  "created_at": "2026-02-14T10:30:01.005Z",
  "updated_at": "2026-02-14T10:30:01.005Z",
  "phase": 0,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "investigation_config": {
      "max_hypotheses": 5,
      "evidence_iterations": 10,
      "min_chain_score": 0.2,
      "max_chains": 3,
      "enable_auto_learning": true,
      "fast_path_threshold": 0.9,
      "min_evidence_for_confident": 2,
      "max_adversarial_challenges": 10
    },
    "llm_config": {
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20241022",
      "temperature": 0.1,
      "max_tokens": 4096,
      "api_key": "***REDACTED***"
    },
    "source_config": {
      "repositories": [
        {
          "name": "artdaq",
          "url": "https://github.com/art-daq/artdaq.git",
          "branch": "develop",
          "local_path": "/data/repos/artdaq"
        },
        {
          "name": "artdaq_core",
          "url": "https://github.com/art-daq/artdaq-core.git",
          "branch": "develop",
          "local_path": "/data/repos/artdaq_core"
        }
      ]
    },
    "pipeline_config": null,
    "enabled_phases": [0, 1, 2, 3, 4, 5, 6, 7],
    "phase_parameters": {
      "2": {
        "max_iterations": 15,
        "strategy": "code_centric"
      }
    }
  }
}
```

---

## 6.4 LLMRequestArtifact

### 1. Purpose & Role

An LLMRequestArtifact records a single LLM request made during an investigation. Every time a persona calls the LLM -- for hypothesis generation, evidence planning, chain construction, adversarial review, or synthesis -- the full request is captured as an artifact before the LLM is invoked.

This artifact solves the traceability problem: after an investigation completes, developers and users need to understand *why* the LLM produced certain results. Was the system prompt missing key context? Was the user prompt too vague? Was the temperature too high? The LLMRequestArtifact preserves the exact inputs so these questions can be answered.

In the agentic REST API context, LLMRequestArtifacts enable:

- **Prompt debugging**: Inspecting the exact prompts sent to the LLM to diagnose unexpected results
- **Cost tracking**: Counting requests and estimating token usage across phases and personas
- **Reprocessing**: Replaying the same request with a different model or temperature to compare results
- **Audit compliance**: Maintaining a complete record of all LLM interactions for regulatory or organizational requirements

Each LLMRequestArtifact is paired with an LLMResponseArtifact through bidirectional linking: the request's `linked_response_id` points to the response, and the response's `linked_request_id` points back to the request. This link is established after the LLM call completes, so a request may exist without a response if the LLM call failed catastrophically.

### 2. Schema

**Class**: `LLMRequestArtifact` in `srcs/workbinder/artifacts_types.py` (line 236)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.LLM_REQUEST` | Always `"llm_request"` |
| `created_by` | `str` | *(required)* | Persona name (same as `persona` field) |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Investigation phase (0-7) |
| `function_name` | `str \| None` | `None` | Not typically used |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `persona` | `str` | *(required)* | Which persona made the request (e.g., "Theorist", "Detective") |
| `prompt_key` | `str` | *(required)* | Prompt identifier (e.g., `"hypothesis_generation"`, `"evidence_planning"`, `"causal_chain"`) |
| `system_prompt` | `str` | *(required)* | Full system prompt sent to the LLM |
| `user_prompt` | `str` | *(required)* | Full user prompt sent to the LLM |
| `model` | `str` | *(required)* | Model identifier used (e.g., `"qwen2.5:14b"`, `"claude-3-sonnet"`) |
| `temperature` | `float` | `0.1` | Temperature setting for this request |
| `max_tokens` | `int` | `4096` | Maximum tokens requested |
| `request_timestamp` | `datetime` | `datetime.now()` | When the request was sent |
| `linked_response_id` | `str \| None` | `None` | Links to the corresponding LLMResponseArtifact (set after response is received) |

### 3. Producer

**Who creates it**: All LLM-using phases, via the `binder.record_llm_request()` method called from `_call_llm` in each persona.

**WorkBinder convenience method**: `binder.record_llm_request()`

```python
def record_llm_request(
    self,
    persona: str,
    prompt_key: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    phase: int | None = None,
) -> str:
```

Returns the artifact ID, which is then passed to `record_llm_response()` to establish the bidirectional link.

**Post-creation update**: After the LLM response is received and recorded, `record_llm_response()` updates this artifact's `linked_response_id`:

```python
# Inside record_llm_response():
if request:
    self.update_artifact(request_id, {"linked_response_id": response_id}, persona)
```

**Typical prompt_key values by phase**:

| Phase | Persona | Common prompt_key Values |
|-------|---------|--------------------------|
| 0 | Archivist | `"prior_knowledge_summary"`, `"call_graph_summarization"` |
| 1 | Theorist | `"hypothesis_generation"` |
| 2 | Detective | `"evidence_planning"`, `"evidence_evaluation"` |
| 3 | Logician | `"causal_chain_construction"` |
| 4 | Devil's Advocate | `"adversarial_review"` |
| 6 | Synthesizer | `"investigation_synthesis"` |

### 4. Consumers

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| `record_llm_response()` | Request artifact for persona name lookup | Sets `created_by` on response from request's `persona` |
| REST API `/binders/{id}/llm/requests` | Full request artifacts | Displays prompt history for debugging |
| REST API `/binders/{id}/llm/exchanges` | Paired with responses | Shows complete LLM conversations |
| REST API `/binders/{id}/llm/statistics` | `persona`, `phase`, `model` | Aggregates usage statistics |
| MCP `get_llm_requests` | Full request artifacts | Prompt inspection |
| MCP `get_llm_exchanges` | Paired request/response | Complete conversation view |
| MCP `get_llm_statistics` | Aggregated counts | Usage dashboards |

### 5. REST API Exposure

**Dedicated endpoint** -- `GET /binders/{binder_id}/llm/requests`:

```
GET /api/v1/binders/{binder_id}/llm/requests
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `persona` | `str` | Filter by persona name |
| `phase` | `int` | Filter by phase number (0-7) |
| `prompt_key` | `str` | Filter by prompt key |
| `limit` | `int` | Maximum results (default 100) |

**Exchanges endpoint** -- `GET /binders/{binder_id}/llm/exchanges`:

```
GET /api/v1/binders/{binder_id}/llm/exchanges
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `phase` | `int` | Filter by phase number (0-7) |

Returns `list[LLMExchangeResponse]`:

```json
[
  {
    "request": {
      "id": "lr-1a2b3c4d",
      "artifact_type": "llm_request",
      "created_by": "Theorist",
      "phase": 1,
      "content": {
        "persona": "Theorist",
        "prompt_key": "hypothesis_generation",
        "system_prompt": "You are an expert artdaq developer...",
        "user_prompt": "Given the following error context and prior knowledge...",
        "model": "qwen2.5:14b",
        "temperature": 0.1,
        "max_tokens": 4096,
        "request_timestamp": "2026-02-14T10:33:15.500Z",
        "linked_response_id": "lrsp-5e6f7a8b"
      }
    },
    "response": {
      "id": "lrsp-5e6f7a8b",
      "artifact_type": "llm_response",
      "created_by": "Theorist",
      "phase": 1,
      "content": {
        "linked_request_id": "lr-1a2b3c4d",
        "raw_response": "[{\"description\": \"Fragment timeout...\", ...}]",
        "parsed_content": {"hypotheses": [...]},
        "tokens_used": 1847,
        "latency_ms": 2340.5,
        "response_timestamp": "2026-02-14T10:33:17.840Z",
        "parse_success": true,
        "parse_errors": []
      }
    }
  }
]
```

**Statistics endpoint** -- `GET /binders/{binder_id}/llm/statistics`:

```
GET /api/v1/binders/{binder_id}/llm/statistics
```

Returns `LLMStatisticsResponse`:

```json
{
  "total_requests": 8,
  "total_responses": 8,
  "total_tokens_used": 14562,
  "total_latency_ms": 18450.3,
  "average_latency_ms": 2306.3,
  "by_persona": {
    "Archivist": 2,
    "Theorist": 1,
    "Detective": 3,
    "Logician": 1,
    "Synthesizer": 1
  },
  "by_phase": {
    "0": 2,
    "1": 1,
    "2": 3,
    "3": 1,
    "6": 1
  },
  "parse_successes": 7,
  "parse_failures": 1
}
```

### 6. MCP Tool Access

| MCP Tool | Parameters | Returns |
|----------|------------|---------|
| `get_llm_requests` | `binder_id`, `persona`, `phase`, `prompt_key`, `limit` | JSON array of LLMRequestArtifacts |
| `get_llm_exchanges` | `binder_id`, `phase` | JSON array of `{request, response}` pairs |
| `get_llm_statistics` | `binder_id` | JSON object with aggregated statistics |

Example MCP tool call to get all Detective LLM requests:

```json
{
  "tool": "get_llm_requests",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "persona": "Detective",
    "phase": 2
  }
}
```

### 7. Artifact Relationships

LLMRequestArtifacts have a 1:1 relationship with LLMResponseArtifacts through bidirectional linking:

```
LLMRequestArtifact                    LLMResponseArtifact
┌──────────────────────────┐          ┌──────────────────────────┐
│ id: "lr-1a2b3c4d"        │          │ id: "lrsp-5e6f7a8b"     │
│ persona: "Theorist"      │          │ linked_request_id: ─────┼──► "lr-1a2b3c4d"
│ prompt_key: "hyp_gen"    │          │ raw_response: "..."     │
│ system_prompt: "..."     │          │ parsed_content: {...}   │
│ user_prompt: "..."       │          │ tokens_used: 1847       │
│ model: "qwen2.5:14b"    │          │ latency_ms: 2340.5      │
│ linked_response_id: ─────┼──►      │ parse_success: true     │
│   "lrsp-5e6f7a8b"       │          └──────────────────────────┘
└──────────────────────────┘

Pipeline artifacts may reference LLM request IDs:
┌──────────────────────────┐
│ HypothesisArtifact       │
│ llm_request_id: ─────────┼──► "lr-1a2b3c4d"
│ (links to generating     │    (traces which LLM call
│  LLM request)            │     produced this hypothesis)
└──────────────────────────┘

┌──────────────────────────┐
│ CausalChainArtifact      │
│ llm_request_id: ─────────┼──► "lr-9c0d1e2f"
└──────────────────────────┘

┌──────────────────────────┐
│ ChallengeArtifact        │
│ llm_request_id: ─────────┼──► "lr-3a4b5c6d"
└──────────────────────────┘
```

Multiple pipeline artifact types carry an `llm_request_id` field that links back to the LLMRequestArtifact that generated them. This provides full provenance: for any hypothesis, chain, or challenge, you can trace back to the exact prompt and response that produced it.

### 8. Session State Mapping

| Session State Concept | Artifact Field | Client View |
|----------------------|---------------|-------------|
| Prompt content | `system_prompt`, `user_prompt` | Expandable prompt viewer |
| Prompt identifier | `prompt_key` | Prompt name label |
| Model used | `model` | Model badge |
| Temperature | `temperature` | Configuration detail |
| Request timing | `request_timestamp` | Timeline position |
| Response link | `linked_response_id` | Navigable link to response |
| Persona attribution | `persona` | Persona badge showing who made the call |

Clients can display LLM requests in a "Prompt Inspector" panel that shows the full system and user prompts, enabling prompt debugging. The `linked_response_id` provides one-click navigation to the corresponding response.

### 9. Example

Full realistic JSON as returned by `GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}`:

```json
{
  "id": "lr-4b5c6d7e",
  "artifact_type": "llm_request",
  "created_by": "Detective",
  "created_at": "2026-02-14T10:35:05.112Z",
  "updated_at": "2026-02-14T10:35:08.445Z",
  "phase": 2,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "persona": "Detective",
    "prompt_key": "evidence_planning",
    "system_prompt": "You are an expert DAQ systems investigator. Your role is to plan evidence-gathering queries that will discriminate between competing hypotheses about the root cause of an error.\n\nYou have access to these query types:\n- log_search: Search log entries by text pattern\n- function_lookup: Look up function definition by name\n- code_search: Search code for symbols/patterns\n- time_window: Get logs within a time range\n\nGenerate queries that maximize discrimination between hypotheses.",
    "user_prompt": "## Current Hypotheses\n\n1. Fragment timeout due to hardware link failure (score: 0.65)\n   - Confirming: Log showing link status error before timeout\n   - Refuting: Log showing successful link communication close to timeout\n\n2. Timeout configuration too aggressive (score: 0.45)\n   - Confirming: Config file showing timeout < recommended minimum\n   - Refuting: Config showing standard timeout value\n\n## Evidence Gathered So Far\n\n- [ev-1a2b3c4d] Code: getNext_ has hardcoded 5000ms timeout (STRONG, supports H1)\n- [ev-5e6f7a8b] Log: No link error messages before timeout (MODERATE, weakly contradicts H1)\n\n## Analyzed Functions\n\n- getNext_ (full source reviewed)\n\n## Generate 3-5 discriminating evidence queries.",
    "model": "qwen2.5:14b",
    "temperature": 0.1,
    "max_tokens": 4096,
    "request_timestamp": "2026-02-14T10:35:05.112Z",
    "linked_response_id": "lrsp-8f9a0b1c"
  }
}
```

---

## 6.5 LLMResponseArtifact

### 1. Purpose & Role

An LLMResponseArtifact records the complete response from a single LLM call. It is always paired with an LLMRequestArtifact through the `linked_request_id` field. Together, the request/response pair provides a complete record of every LLM interaction during the investigation.

This artifact captures not just the raw LLM output, but also the result of parsing that output into structured data. The `parse_success` and `parse_errors` fields are critical for debugging: when a phase produces unexpected results, the first diagnostic step is checking whether the LLM response parsed correctly. A `parse_success: false` with `parse_errors` entries immediately explains why a phase failed or produced degraded output.

In the agentic REST API context, LLMResponseArtifacts enable:

- **Response inspection**: Viewing the raw LLM output alongside the parsed structured data
- **Parse failure diagnosis**: Identifying which LLM calls failed to parse and why
- **Performance monitoring**: Tracking token usage and latency across phases and personas
- **Token budgeting**: Analyzing total token consumption to optimize cost
- **Latency profiling**: Identifying which LLM calls are slow and which phases dominate investigation time

### 2. Schema

**Class**: `LLMResponseArtifact` in `srcs/workbinder/artifacts_types.py` (line 255)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.LLM_RESPONSE` | Always `"llm_response"` |
| `created_by` | `str` | *(required)* | Persona name (inherited from corresponding request) |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Investigation phase (0-7) |
| `function_name` | `str \| None` | `None` | Not typically used |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `linked_request_id` | `str` | *(required)* | Links to the corresponding LLMRequestArtifact |
| `raw_response` | `str` | *(required)* | Full raw LLM output text |
| `parsed_content` | `dict[str, Any] \| None` | `None` | Parsed JSON/structured content (None if parse failed) |
| `tokens_used` | `int` | `0` | Token count for this response |
| `latency_ms` | `float` | `0.0` | Response time in milliseconds |
| `response_timestamp` | `datetime` | `datetime.now()` | When the response was received |
| `parse_success` | `bool` | `True` | Whether parsing the response into structured data succeeded |
| `parse_errors` | `list[str]` | `[]` | Parse error messages (empty if parse succeeded) |

### 3. Producer

**Who creates it**: All LLM-using phases, via the `binder.record_llm_response()` method called after each LLM call completes.

**WorkBinder convenience method**: `binder.record_llm_response()`

```python
def record_llm_response(
    self,
    request_id: str,
    raw_response: str,
    parsed_content: dict[str, Any] | None,
    tokens_used: int,
    latency_ms: float,
    parse_success: bool,
    parse_errors: list[str] | None = None,
    phase: int | None = None,
) -> str:
```

The method:
1. Retrieves the corresponding LLMRequestArtifact to extract the persona name for `created_by`
2. Creates the LLMResponseArtifact
3. Updates the LLMRequestArtifact's `linked_response_id` to point to the new response

This bidirectional linking ensures that requests and responses can be navigated in either direction.

**Typical response patterns**:

| Outcome | `parse_success` | `parsed_content` | `parse_errors` |
|---------|-----------------|-------------------|----------------|
| Successful parse | `true` | `{...}` structured data | `[]` |
| JSON parse error | `false` | `None` | `["JSON decode error at position 847: trailing comma"]` |
| Schema validation error | `false` | partial dict | `["Missing required field: 'description'"]` |
| Empty response | `false` | `None` | `["Empty response from LLM"]` |
| Timeout | `false` | `None` | `["Request timed out after 60s"]` |

### 4. Consumers

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| Phase logic | `parsed_content` | The structured output used to create pipeline artifacts (hypotheses, evidence queries, chains, etc.) |
| REST API `/binders/{id}/llm/responses` | Full response artifacts | Response inspection |
| REST API `/binders/{id}/llm/exchanges` | Paired with requests | Complete conversation view |
| REST API `/binders/{id}/llm/statistics` | `tokens_used`, `latency_ms`, `parse_success` | Aggregated performance metrics |
| MCP `get_llm_responses` | Full response artifacts | Response inspection |
| MCP `get_llm_statistics` | Aggregated metrics | Usage dashboards |
| Debugging | `raw_response`, `parse_errors` | Diagnosing why a phase produced unexpected results |

### 5. REST API Exposure

**Dedicated endpoint** -- `GET /binders/{binder_id}/llm/responses`:

```
GET /api/v1/binders/{binder_id}/llm/responses
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `request_id` | `str` | Filter by specific request ID (get the response for a known request) |
| `phase` | `int` | Filter by phase number (0-7) |
| `parse_success` | `bool` | Filter by parse success status (useful for finding failures) |
| `limit` | `int` | Maximum results (default 100) |

**Finding parse failures**:

```
GET /api/v1/binders/{binder_id}/llm/responses?parse_success=false
```

This is a common debugging query -- filtering for `parse_success=false` immediately shows which LLM calls failed to produce usable structured output.

**Response JSON snippet**:

```json
{
  "id": "lrsp-8f9a0b1c",
  "artifact_type": "llm_response",
  "created_by": "Detective",
  "created_at": "2026-02-14T10:35:08.445Z",
  "updated_at": "2026-02-14T10:35:08.445Z",
  "phase": 2,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "linked_request_id": "lr-4b5c6d7e",
    "raw_response": "[{\"query_type\": \"log_search\", \"query\": \"link.*status\", ...}]",
    "parsed_content": {
      "queries": [
        {
          "query_type": "log_search",
          "query": "link.*status",
          "targets_hypothesis": "H1",
          "expected_if_true": "Link status error message before timeout",
          "expected_if_false": "No link status errors"
        }
      ]
    },
    "tokens_used": 892,
    "latency_ms": 1205.3,
    "response_timestamp": "2026-02-14T10:35:08.445Z",
    "parse_success": true,
    "parse_errors": []
  }
}
```

### 6. MCP Tool Access

| MCP Tool | Parameters | Returns |
|----------|------------|---------|
| `get_llm_responses` | `binder_id`, `request_id`, `phase`, `parse_success`, `limit` | JSON array of LLMResponseArtifacts |
| `get_llm_exchanges` | `binder_id`, `phase` | JSON array of paired request/response objects |
| `get_llm_statistics` | `binder_id` | Aggregated token, latency, and parse success statistics |

Example MCP tool call to find parse failures:

```json
{
  "tool": "get_llm_responses",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "parse_success": false
  }
}
```

### 7. Artifact Relationships

The LLMResponseArtifact has a mandatory link back to its request and is linked from pipeline artifacts that were produced from this response:

```
LLMRequestArtifact              LLMResponseArtifact
┌────────────────────┐          ┌─────────────────────────┐
│ id: "lr-4b5c6d7e"  │◄─────── │ linked_request_id:      │
│ linked_response_id:│          │   "lr-4b5c6d7e"         │
│   "lrsp-8f9a0b1c" ├────────►│ id: "lrsp-8f9a0b1c"     │
└────────────────────┘          │ raw_response: "..."     │
                                │ parsed_content: {...}   │
                                │ tokens_used: 892        │
                                │ latency_ms: 1205.3      │
                                │ parse_success: true     │
                                │ parse_errors: []        │
                                └─────────────────────────┘
                                         │
                                         │ parsed_content used to create:
                                         ▼
                                ┌─────────────────────────┐
                                │ EvidenceArtifact(s)     │
                                │ llm_request_id: ────────┼──► "lr-4b5c6d7e"
                                │ (derived from parsed    │
                                │  evidence queries)      │
                                └─────────────────────────┘
```

The relationship between LLMResponseArtifact and the pipeline artifacts it generates is indirect: the response's `parsed_content` is consumed by phase logic to create pipeline artifacts, and those pipeline artifacts carry `llm_request_id` pointing to the request (not the response). To trace from a pipeline artifact back to the raw LLM output, follow: `pipeline_artifact.llm_request_id` -> `LLMRequestArtifact.linked_response_id` -> `LLMResponseArtifact.raw_response`.

### 8. Session State Mapping

| Session State Concept | Artifact Field | Client View |
|----------------------|---------------|-------------|
| Raw LLM output | `raw_response` | Expandable raw text viewer |
| Parsed result | `parsed_content` | Formatted JSON tree view |
| Token usage | `tokens_used` | Token count badge |
| Response latency | `latency_ms` | Latency indicator |
| Parse status | `parse_success` | Success/failure badge |
| Parse errors | `parse_errors` | Error message list (for failures) |
| Response timing | `response_timestamp` | Timeline position |
| Request link | `linked_request_id` | Navigable link to corresponding request |

Clients display LLM responses in a "Response Inspector" panel showing the raw output, parsed content, and parse status. Parse failures are highlighted with error details. Token usage and latency are shown for cost and performance monitoring.

### 9. Example

Full realistic JSON for a response with parse failure:

```json
{
  "id": "lrsp-2c3d4e5f",
  "artifact_type": "llm_response",
  "created_by": "Logician",
  "created_at": "2026-02-14T10:37:14.992Z",
  "updated_at": "2026-02-14T10:37:14.992Z",
  "phase": 3,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "linked_request_id": "lr-f6a7b8c9",
    "raw_response": "Based on the evidence gathered, here is the causal chain:\n\n```json\n{\"steps\": [{\"claim\": \"Hardware link 0x0100 becomes unresponsive\", \"mechanism\": \"Physical connection degradation or firmware issue causes link to stop responding to read requests\", \"evidence\": [\"ev-1a2b3c4d\"], \"is_assumption\": false}, {\"claim\": \"getNext_ blocks waiting for data on unresponsive link\", \"mechanism\": \"The polling loop in getNext_ continuously checks link status without exponential backoff\", \"evidence\": [\"ev-5e6f7a8b\", \"ev-9c0d1e2f\"], \"is_assumption\": false}, {\"claim\": \"5000ms timeout triggers after polling exhaustion\", \"mechanism\": \"Hardcoded timeout constant FRAGMENT_TIMEOUT_MS = 5000 reached\", \"evidence\": [\"ev-1a2b3c4d\"], \"is_assumption\": false}, {\"claim\": \"Timeout triggers error logging and fragment request failure\", \"mechanism\": \"getNext_ logs ERROR and returns nullptr to calling EventBuilder\", \"evidence\": [], \"is_assumption\": true,}]}\n```\n\nThis chain has good mechanistic support...",
    "parsed_content": null,
    "tokens_used": 1523,
    "latency_ms": 3891.7,
    "response_timestamp": "2026-02-14T10:37:14.992Z",
    "parse_success": false,
    "parse_errors": [
      "JSON decode error: trailing comma at position 847 in steps array",
      "Fallback regex extraction failed: could not find valid JSON object in response",
      "Using fallback chain construction with 0 steps recovered"
    ]
  }
}
```

---

> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 5: Observation Artifacts](agentic-workbinder-library-ch5-observation-artifacts.md) | [Next: Ch. 7: Tools, Serialization & Parsing](agentic-workbinder-library-ch7-tools-serialization.md)
