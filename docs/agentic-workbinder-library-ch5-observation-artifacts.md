> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 4: Investigation Artifacts](agentic-workbinder-library-ch4-investigation-artifacts.md) | [Next: Ch. 6: Infrastructure Artifacts](agentic-workbinder-library-ch6-infrastructure-artifacts.md)

---

# Chapter 5: Observation Artifacts

The artifact types covered in Chapters 3 and 4 follow the strict phase ordering of the investigation pipeline: ErrorContextArtifact is produced in Phase 0, HypothesisArtifact in Phase 1, EvidenceArtifact in Phase 2, and so on. Each artifact type has a single producer phase and one or more consumer phases. The pipeline is a directed acyclic graph with well-defined data flow.

Observation artifacts break that pattern. The three types documented in this chapter -- Finding, Annotation, and PersonaContributionArtifact -- are **cross-cutting**: any persona can create them at any time during the investigation lifecycle. They serve as the annotation layer on top of the structured pipeline, enabling personas to record informal observations, attach commentary to existing artifacts, and submit structured contributions that the expert panel orchestrator can aggregate.

Where pipeline artifacts carry the investigation's primary data (hypotheses, evidence, causal chains, challenges, conclusions), observation artifacts carry the investigation's *metadata about itself*: what did a persona notice while working? What question arose about an existing artifact? What structured contribution did a persona make during expert Q&A? These secondary artifacts are critical for investigation traceability and for the expert panel's multi-persona deliberation protocol.

The cross-cutting nature of observation artifacts means they do not participate in the phase-gated read/write permissions matrix that governs pipeline artifacts. The WorkBinder enforces no restrictions on which phase can create a Finding, Annotation, or PersonaContributionArtifact. The `created_by` and `phase` fields on the base `Artifact` class provide attribution, but any persona can write at any time.

```
Pipeline Artifacts (strict phase ordering)
  Phase 0: ErrorContext, SourceLocation, CallGraph, CodeSnippet
  Phase 1: HypothesisArtifact
  Phase 2: EvidenceArtifact
  Phase 3: CausalChainArtifact
  Phase 4: ChallengeArtifact
  Phase 6: ConclusionArtifact

Observation Artifacts (cross-cutting, any phase)
  Finding ──────────► Any persona, any phase
  Annotation ─────────► Any persona, any phase, targets another artifact
  PersonaContribution ► Any persona, any phase, structured content dict
```

All three observation artifact types inherit from the common `Artifact` base class defined in `srcs/workbinder/artifacts_types.py`. They share the same base fields (id, artifact_type, created_by, created_at, updated_at, tags, phase, function_name, priority, is_deleted, deleted_by, deleted_reason) and the same lifecycle operations (add, update, soft-delete, restore, history tracking).

---

## 5.1 Finding

### 1. Purpose & Role

A Finding is a typed observation that any persona records during investigation. It is the most versatile cross-cutting artifact in the WorkBinder -- a general-purpose note with a category, a confidence score, and optional links to related artifacts.

Findings serve multiple roles in the investigation:

- **Observation capture**: When a persona notices something noteworthy while performing its primary task (e.g., the Archivist notices a suspicious pattern in the call graph while building it), it records a Finding rather than embedding that observation in an unrelated artifact.
- **Question escalation**: A persona can record a `question` finding to signal that something needs further investigation, without disrupting the pipeline flow.
- **Conclusion fragments**: Intermediate conclusions that are not yet full ConclusionArtifacts can be recorded as `conclusion` findings, providing breadcrumbs for the Synthesizer.
- **Warnings**: Potential issues (data quality concerns, missing source files, ambiguous patterns) are recorded as `warning` findings so downstream phases can account for them.
- **Recommendations**: Actionable suggestions (debugging steps, configuration changes, code fixes) can be captured as `recommendation` findings independently of the final synthesis.

In the agentic API context, Findings provide the LLM agent with a structured way to take notes during an investigation. Rather than losing observations in the conversational context, the agent persists them as first-class artifacts that appear in artifact searches, audit trails, and investigation summaries.

### 2. Schema

**Class**: `Finding` in `srcs/workbinder/artifacts_types.py` (line 156)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier (16-char UUID prefix) |
| `artifact_type` | `ArtifactType` | `ArtifactType.FINDING` | Always `"finding"` |
| `created_by` | `str` | *(required)* | Persona name that created this finding |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization and filtering |
| `phase` | `int \| None` | `None` | Phase when created (0-7), or None |
| `function_name` | `str \| None` | `None` | Related function for grouping |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level (low, normal, high, critical) |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `persona` | `str` | *(required)* | Persona making the finding (duplicates created_by for clarity) |
| `finding_type` | `FindingType` | *(required)* | One of: `observation`, `question`, `conclusion`, `warning`, `recommendation` |
| `content` | `str` | *(required)* | The finding text content |
| `related_artifacts` | `list[str]` | `[]` | IDs of related artifacts |
| `confidence` | `float` | `0.5` | Confidence level, constrained to [0.0, 1.0] |

**FindingType enum**:

| Value | Description |
|-------|-------------|
| `OBSERVATION` | General observation noticed during investigation |
| `QUESTION` | Question that needs further investigation |
| `CONCLUSION` | Intermediate conclusion fragment |
| `WARNING` | Potential issue or data quality concern |
| `RECOMMENDATION` | Actionable suggestion or debugging step |

### 3. Producer

**Who creates it**: Any persona, any phase. The Finding is the only pipeline-aware artifact with no single designated producer.

**WorkBinder convenience method**: `binder.add_finding()`

```python
def add_finding(
    self,
    persona: str,
    finding_type: FindingType | str,
    content: str,
    confidence: float = 0.5,
    related_artifacts: list[str] | None = None,
    phase: int | None = None,
    tags: list[str] | None = None,
) -> str:
```

The method accepts `finding_type` as either a `FindingType` enum value or a raw string (which is auto-converted). The `persona` argument is used for both the `persona` field and the `created_by` field on the base Artifact.

**BinderTools method**: `tools.add_finding()` (async wrapper used by LLM tool calls)

```python
async def add_finding(
    self,
    finding_type: str,
    content: str,
    related_artifacts: list[str] | None = None,
    confidence: float = 0.5,
    tags: list[str] | None = None,
) -> str:
```

When invoked through BinderTools, the `persona_name` and `current_phase` are injected from the tool's constructor context.

**Typical creation points**:

| Phase | Persona | Typical Finding Types |
|-------|---------|----------------------|
| 0 | Archivist | `observation` (patterns found), `warning` (missing source) |
| 1 | Theorist | `observation` (reasoning notes), `question` (ambiguities) |
| 2 | Detective | `observation` (evidence gaps), `warning` (low-quality results) |
| 3 | Logician | `observation` (chain construction notes), `warning` (assumption-heavy) |
| 4 | Devil's Advocate | `question` (unresolved challenges), `warning` (evidence concerns) |
| 6 | Synthesizer | `conclusion` (intermediate conclusions), `recommendation` (debugging steps) |

### 4. Consumers

Findings are consumed broadly because they are cross-cutting:

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| Detective (Phase 2) | `warning` and `question` findings from Phase 0-1 | May adjust evidence-seeking strategy to address flagged concerns |
| Logician (Phase 3) | `observation` findings | Incorporates relevant observations into causal chain reasoning |
| Devil's Advocate (Phase 4) | All finding types | Uses warnings and questions as starting points for adversarial challenges |
| Synthesizer (Phase 6) | `conclusion`, `recommendation`, `warning` findings | Incorporates intermediate conclusions and caveats into final report |
| Expert Panel | All finding types | Findings inform the panel's multi-persona deliberation |

Findings are retrieved through `binder.query()` with `artifact_type=ArtifactType.FINDING`, through `binder.get_related_artifacts()` (which checks `related_artifacts` lists), and through generic `get_by_tag()` or `get_by_function()` queries.

### 5. REST API Exposure

Findings are accessed through the generic artifact endpoints in `srcs/api/routes/binders.py`:

**Search findings by type**:

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=finding
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `artifact_type` | `str` | Set to `"finding"` |
| `phase` | `int` | Filter by investigation phase (0-7) |
| `function_name` | `str` | Filter by related function |
| `tags` | `list[str]` | Filter by tags (AND logic) |
| `include_deleted` | `bool` | Include soft-deleted findings |
| `limit` | `int` | Maximum results (default 50) |
| `offset` | `int` | Pagination offset |

**Get a specific finding**:

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

**Full-text search across findings**:

```
POST /api/v1/binders/{binder_id}/artifacts/search
Content-Type: application/json

{
  "query": "null pointer",
  "artifact_types": ["finding"]
}
```

**Response JSON snippet** (from `_artifact_to_response()`):

```json
{
  "id": "f8a3c1e2",
  "artifact_type": "finding",
  "created_by": "Archivist",
  "created_at": "2026-02-14T10:32:15.003Z",
  "updated_at": "2026-02-14T10:32:15.003Z",
  "phase": 0,
  "function_name": "processFragment",
  "priority": "normal",
  "tags": ["error-path", "null-check"],
  "is_deleted": false,
  "content": {
    "persona": "Archivist",
    "finding_type": "observation",
    "content": "Function processFragment has no null check on generator_ before dereferencing at line 142. This is a potential crash site if initialization fails.",
    "related_artifacts": ["src-a1b2c3d4"],
    "confidence": 0.8
  }
}
```

Note that the `content` field in the response is the type-specific payload: the base Artifact fields are lifted to the top level by `_artifact_to_response()`, and the remaining fields (`persona`, `finding_type`, `content`, `related_artifacts`, `confidence`) appear in the nested `content` object.

### 6. MCP Tool Access

Findings are accessed through the generic MCP artifact tools. There are no dedicated Finding-specific MCP tools.

| MCP Tool | Parameters for Findings | Returns |
|----------|-------------------------|---------|
| `search_artifacts` | `binder_id`, `artifact_type="finding"`, optional `phase`, `tags`, `function_name` | JSON array of Finding artifacts |
| `get_artifact` | `binder_id`, `artifact_id` | JSON object with full Finding details |
| `search_artifact_content` | `binder_id`, `query`, `artifact_types="finding"` | JSON array of Findings matching text query |

Example MCP tool call:

```json
{
  "tool": "search_artifacts",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "artifact_type": "finding",
    "phase": 0
  }
}
```

### 7. Artifact Relationships

Findings are the most heavily cross-referenced observation artifact. They link outward to other artifacts via `related_artifacts` and are linked inward from Annotations.

```
                    ┌──────────────────────┐
                    │      Finding         │
                    │ related_artifacts: ──┼──► SourceLocationArtifact
                    │   ["src-...",        │──► CodeSnippet
                    │    "cg-...",         │──► CallGraphNode
                    │    "hyp-..."]        │──► HypothesisArtifact
                    └──────────┬───────────┘──► EvidenceArtifact
                               │
                    ┌──────────┴───────────┐
                    │     Annotation        │
                    │ target_artifact_id ───┼──► This Finding
                    └──────────────────────┘
```

The `binder.get_related_artifacts(artifact_id)` method discovers Findings that reference a given artifact, Annotations on Findings, and other artifacts sharing the same `function_name`.

### 8. Session State Mapping

In the agentic REST API session model, Findings map to the investigation's observation layer:

| Session State Concept | Finding Field | Client View |
|----------------------|---------------|-------------|
| Persona notes | `content` | Displayed as investigation annotations |
| Observation category | `finding_type` | Grouped by type in UI (observations, questions, warnings) |
| Cross-references | `related_artifacts` | Clickable links to related artifacts |
| Confidence | `confidence` | Visual confidence indicator (0.0-1.0) |
| Phase attribution | `phase` | Timeline position in investigation |
| Function grouping | `function_name` | Grouped with other artifacts for same function |

Clients can poll for new Findings during a streaming investigation to show live persona observations as they occur. The `phase` field indicates which investigation step produced the finding, enabling timeline-based display.

### 9. Example

Full realistic JSON as returned by `GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}`:

```json
{
  "id": "fnd-8b2e4a91",
  "artifact_type": "finding",
  "created_by": "Detective",
  "created_at": "2026-02-14T10:35:22.417Z",
  "updated_at": "2026-02-14T10:35:22.417Z",
  "phase": 2,
  "function_name": "getNext_",
  "priority": "high",
  "tags": ["timeout", "evidence-gap", "boardreader"],
  "is_deleted": false,
  "content": {
    "persona": "Detective",
    "finding_type": "warning",
    "content": "Evidence search for timeout configuration found no config files referencing the 5000ms timeout value in getNext_. The timeout may be hardcoded rather than configurable, which would narrow the root cause to a code-level issue rather than a configuration problem. This absence of configuration evidence weakens the 'misconfiguration' hypothesis but does not refute it -- the value could be set through an environment variable or command-line argument not visible in the source.",
    "related_artifacts": [
      "hyp-c3d4e5f6",
      "ev-9a8b7c6d"
    ],
    "confidence": 0.65
  }
}
```

---

## 5.2 Annotation

### 1. Purpose & Role

An Annotation is a note attached to another artifact. Where a Finding is a standalone observation, an Annotation is always tethered to a specific target artifact through the `target_artifact_id` field. This makes Annotations the mechanism for inline commentary on any artifact in the WorkBinder.

Annotations solve the problem of adding context or commentary to existing artifacts without modifying them. The WorkBinder's design principle of "no modification by other phases" means that when the Devil's Advocate wants to question a specific hypothesis, it cannot edit the HypothesisArtifact. Instead, it creates an Annotation of type `question` targeting that hypothesis. This preserves the original artifact while adding a traceable layer of commentary.

In the agentic API context, Annotations enable the LLM agent to build up a commentary layer on investigation artifacts. When reviewing a call graph and noticing a suspicious pattern, the agent can annotate the call graph node rather than creating a separate, disconnected finding. This preserves spatial context -- the annotation is logically "on" the artifact it references.

The four annotation types cover the most common commentary patterns:

| AnnotationType | Use Case |
|---------------|----------|
| `comment` | General commentary on an artifact |
| `highlight` | Marking an artifact as particularly important or noteworthy |
| `question` | Raising a question about an artifact's content or validity |
| `correction` | Noting an error or inaccuracy in an artifact |

### 2. Schema

**Class**: `Annotation` in `srcs/workbinder/artifacts_types.py` (line 171)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.ANNOTATION` | Always `"annotation"` |
| `created_by` | `str` | *(required)* | Persona name that created this annotation |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Phase when created (0-7) |
| `function_name` | `str \| None` | `None` | Related function for grouping |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `target_artifact_id` | `str` | *(required)* | ID of the artifact being annotated |
| `annotation_type` | `AnnotationType` | *(required)* | One of: `comment`, `highlight`, `question`, `correction` |
| `annotation_content` | `str` | *(required)* | The annotation text (named `annotation_content` to avoid confusion with any `content` field on target) |

**AnnotationType enum**:

| Value | Description |
|-------|-------------|
| `COMMENT` | General commentary on the target artifact |
| `HIGHLIGHT` | Marks the target artifact as particularly important |
| `QUESTION` | Raises a question about the target artifact |
| `CORRECTION` | Notes an error or inaccuracy in the target artifact |

### 3. Producer

**Who creates it**: Any persona, any phase. Annotations are most commonly created by downstream phases commenting on upstream artifacts.

**WorkBinder convenience method**: `binder.add_annotation()`

```python
def add_annotation(
    self,
    target_artifact_id: str,
    annotation_type: AnnotationType | str,
    content: str,
    created_by: str,
) -> str:
```

The method accepts `annotation_type` as either an `AnnotationType` enum value or a raw string (auto-converted). Note that the `content` parameter maps to the `annotation_content` field on the Annotation model.

**BinderTools method**: `tools.annotate_artifact()` (async wrapper)

```python
async def annotate_artifact(
    self,
    artifact_id: str,
    annotation_type: str,
    content: str,
) -> str:
```

When invoked through BinderTools, the `persona_name` is injected from the tool's constructor context as `created_by`.

**Typical creation patterns**:

| Phase | Persona | Typical Annotation Pattern |
|-------|---------|---------------------------|
| 1 | Theorist | `comment` on SourceLocationArtifact -- why this location matters for a hypothesis |
| 2 | Detective | `highlight` on EvidenceArtifact -- marking strong discriminating evidence |
| 3 | Logician | `question` on HypothesisArtifact -- noting unclear mechanisms |
| 4 | Devil's Advocate | `question` on CausalChainArtifact -- challenging weak chain steps |
| 4 | Devil's Advocate | `correction` on EvidenceArtifact -- noting misinterpreted evidence |
| 6 | Synthesizer | `comment` on ConclusionArtifact -- adding synthesis notes |

### 4. Consumers

Annotations are consumed through two primary mechanisms:

1. **Direct query**: `binder.get_annotations(artifact_id)` returns all Annotations targeting a specific artifact. This is used by any phase that wants to see commentary on an artifact it is reading.

2. **Related artifacts**: `binder.get_related_artifacts(artifact_id)` includes Annotations on the queried artifact in its results.

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| Any persona reading an artifact | `annotation_content`, `annotation_type` | Sees inline commentary added by other personas |
| Devil's Advocate (Phase 4) | `question` and `correction` annotations | Uses them as inputs for adversarial review |
| Synthesizer (Phase 6) | All annotations | Incorporates highlights and corrections into final report |
| REST API client | Annotations via `get_artifact_history` or `search_artifacts` | Displays inline comments on artifacts |

### 5. REST API Exposure

Annotations are accessed through the generic artifact endpoints:

**Search annotations by type**:

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=annotation
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `artifact_type` | `str` | Set to `"annotation"` |
| `phase` | `int` | Filter by phase that created the annotation |
| `limit` | `int` | Maximum results (default 50) |
| `offset` | `int` | Pagination offset |

**Get annotations for a specific artifact**: There is no dedicated REST endpoint for "get annotations for artifact X." Clients must use the generic artifact search and filter client-side, or use the `search_artifact_content` endpoint to find annotations mentioning a specific artifact ID.

**Response JSON snippet**:

```json
{
  "id": "ann-d4e5f6a7",
  "artifact_type": "annotation",
  "created_by": "Devil's Advocate",
  "created_at": "2026-02-14T10:38:45.201Z",
  "updated_at": "2026-02-14T10:38:45.201Z",
  "phase": 4,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "target_artifact_id": "hyp-c3d4e5f6",
    "annotation_type": "question",
    "annotation_content": "This hypothesis assumes the fragment generator is uninitialized, but no evidence directly shows the initialization sequence failing. The code path analysis only shows the null check is missing, not that the generator is actually null at runtime."
  }
}
```

### 6. MCP Tool Access

Annotations are accessed through the generic MCP artifact tools:

| MCP Tool | Parameters for Annotations | Returns |
|----------|----------------------------|---------|
| `search_artifacts` | `binder_id`, `artifact_type="annotation"` | JSON array of Annotation artifacts |
| `get_artifact` | `binder_id`, `artifact_id` | JSON object with full Annotation details |
| `search_artifact_content` | `binder_id`, `query`, `artifact_types="annotation"` | JSON array matching text query |

To find all annotations on a specific artifact, search for the target artifact ID in annotation content:

```json
{
  "tool": "search_artifact_content",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "query": "hyp-c3d4e5f6",
    "artifact_types": "annotation"
  }
}
```

### 7. Artifact Relationships

Annotations have a mandatory one-to-one reference to a target artifact. The target can be any artifact type, including other Annotations (enabling threaded commentary).

```
Any Artifact                          Annotation
┌───────────────────┐                ┌───────────────────────┐
│ id: "hyp-c3d4e5f6"│◄───────────── │ target_artifact_id:   │
│ (HypothesisArtif.)│                │   "hyp-c3d4e5f6"     │
└───────────────────┘                │ annotation_type:      │
                                     │   "question"          │
Any Artifact                         │ annotation_content:   │
┌───────────────────┐                │   "Why assume..."     │
│ id: "ev-9a8b7c6d" │◄─────┐        └───────────────────────┘
│ (EvidenceArtifact)│       │
└───────────────────┘       │        ┌───────────────────────┐
                            └─────── │ target_artifact_id:   │
                                     │   "ev-9a8b7c6d"      │
                                     │ annotation_type:      │
                                     │   "correction"        │
                                     └───────────────────────┘

Annotation ──► Annotation (threaded)
┌───────────────────────┐            ┌───────────────────────┐
│ id: "ann-d4e5f6a7"    │◄────────── │ target_artifact_id:   │
│ annotation_type:      │            │   "ann-d4e5f6a7"     │
│   "question"          │            │ annotation_type:      │
└───────────────────────┘            │   "comment"           │
                                     │ (reply to question)   │
                                     └───────────────────────┘
```

The `binder.get_annotations(artifact_id)` method iterates all artifacts, filtering for `Annotation` instances whose `target_artifact_id` matches. The `binder.get_related_artifacts(artifact_id)` method also discovers Annotations as part of its broader relationship scan.

### 8. Session State Mapping

| Session State Concept | Annotation Field | Client View |
|----------------------|-----------------|-------------|
| Inline commentary | `annotation_content` | Displayed alongside the target artifact |
| Commentary type | `annotation_type` | Visual differentiation (comment icon, highlight color, question badge, correction strikethrough) |
| Target artifact | `target_artifact_id` | Navigable link to the annotated artifact |
| Author | `created_by` | Persona attribution badge |
| Phase context | `phase` | Shows when in the investigation the annotation was made |

In a streaming investigation, Annotations appear as real-time commentary on artifacts the client has already received. The client can subscribe to new annotations and display them inline with their target artifacts.

### 9. Example

Full realistic JSON as returned by `GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}`:

```json
{
  "id": "ann-7f2a3b4c",
  "artifact_type": "annotation",
  "created_by": "Logician",
  "created_at": "2026-02-14T10:37:12.884Z",
  "updated_at": "2026-02-14T10:37:12.884Z",
  "phase": 3,
  "function_name": "getNext_",
  "priority": "normal",
  "tags": ["chain-construction"],
  "is_deleted": false,
  "content": {
    "target_artifact_id": "ev-4d5e6f7a",
    "annotation_type": "highlight",
    "annotation_content": "This evidence item is critical for the causal chain. The log entry shows the exact timeout value (5000ms) matching the hardcoded constant in getNext_ at line 287. This provides the strongest link between the configured timeout and the observed failure, serving as step 3 in the causal chain for hypothesis hyp-c3d4e5f6."
  }
}
```

---

## 5.3 PersonaContributionArtifact

### 1. Purpose & Role

A PersonaContributionArtifact is a structured record of a persona's contribution to an investigation or expert panel session. Unlike a Finding (which is a free-text observation) or an Annotation (which comments on another artifact), a PersonaContributionArtifact carries a typed `content` dictionary whose schema varies by phase and persona.

This artifact type exists to solve two problems:

1. **Pipeline traceability**: After each phase completes, the persona records a PersonaContributionArtifact summarizing what it did, what it produced, and how confident it is in its output. This creates a per-phase summary layer that makes it possible to understand the investigation's progression without reading every individual hypothesis, evidence item, or chain.

2. **Expert panel aggregation**: When the `PanelOrchestrator` coordinates a multi-persona Q&A session (via `ask_experts`), each persona submits its contribution as a PersonaContributionArtifact. The orchestrator then aggregates these contributions into a unified answer. The `content` dict carries the persona's structured response (e.g., the Logician's contribution contains `causal_analysis`, `logical_steps`, and `assumptions`; the Devil's Advocate's contains `challenges`, `concerns`, and `alternatives`).

In the agentic API context, PersonaContributionArtifacts provide the client with per-persona summaries at each phase. Rather than parsing raw artifact lists, the client can read the contribution artifact for each phase to get a high-level view of what happened.

### 2. Schema

**Class**: `PersonaContributionArtifact` in `srcs/workbinder/artifacts_types.py` (line 326)

**Inherits from**: `Artifact`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique artifact identifier |
| `artifact_type` | `ArtifactType` | `ArtifactType.PERSONA_CONTRIBUTION` | Always `"persona_contribution"` |
| `created_by` | `str` | *(required)* | Persona name (auto-set from `persona_id` if not provided) |
| `created_at` | `datetime` | `datetime.now()` | Timestamp of creation |
| `updated_at` | `datetime` | `datetime.now()` | Timestamp of last update |
| `tags` | `list[str]` | `[]` | Tags for categorization |
| `phase` | `int \| None` | `None` | Auto-set from `contribution_phase` |
| `function_name` | `str \| None` | `None` | Related function for grouping |
| `priority` | `Priority` | `Priority.NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |
| `persona_id` | `str` | *(required)* | Persona identifier (e.g., "Theorist", "Detective") |
| `contribution_phase` | `int` | *(required)* | Phase when the contribution was made |
| `content` | `dict[str, Any]` | `{}` | The actual contribution (schema varies by persona) |
| `confidence` | `float` | `0.5` | Persona's confidence in its contribution (0.0-1.0) |
| `reasoning` | `str` | `""` | Explanation of the contribution and confidence level |

### 3. Producer

**Who creates it**: All phases, all personas. Each persona creates a PersonaContributionArtifact at the end of its phase execution, and again during expert panel Q&A sessions.

**WorkBinder convenience method**: `binder.add_persona_contribution()`

```python
def add_persona_contribution(
    self,
    persona_id: str,
    contribution_phase: int,
    content: dict[str, Any],
    confidence: float = 0.5,
    reasoning: str = "",
    created_by: str | None = None,
) -> str:
```

If `created_by` is not provided, it defaults to `persona_id`. The `phase` field on the base Artifact is automatically set to `contribution_phase`.

**Content dict schemas by persona**:

The `content` dict is not rigidly typed -- its schema depends on the persona and context. Common patterns:

| Persona | Content Keys (Pipeline) | Content Keys (Expert Q&A) |
|---------|------------------------|---------------------------|
| Archivist | `source_locations_found`, `call_graphs_built`, `code_snippets_collected`, `patterns_matched` | `historical_context`, `similar_cases`, `code_references` |
| Theorist | `hypotheses_generated`, `top_hypothesis`, `prior_probabilities`, `source_distribution` | `possible_causes`, `mechanism_analysis`, `probability_assessment` |
| Detective | `evidence_collected`, `iterations`, `queries_executed`, `discrimination_achieved` | `evidence_analysis`, `key_findings`, `data_sources` |
| Logician | `chains_built`, `average_validity`, `average_coverage`, `total_steps`, `assumptions_made`, `gaps_identified`, `chain_details` | `causal_analysis`, `logical_steps`, `assumptions` |
| Devil's Advocate | `challenges_raised`, `high_severity_count`, `unresolved_count` | `challenges`, `concerns`, `alternatives` |
| Synthesizer | `root_cause`, `confidence`, `outcome`, `key_evidence_count` | `synthesis`, `recommendations`, `confidence_assessment` |

### 4. Consumers

| Consumer | What They Extract | How It Influences Behavior |
|----------|-------------------|---------------------------|
| Downstream phases | Previous phase's `content`, `confidence`, `reasoning` | Understand what happened in prior phases without reading all artifacts |
| PanelOrchestrator | All persona contributions for a Q&A session | Aggregates into unified expert panel answer |
| Synthesizer (Phase 6) | All prior contributions | Uses confidence scores and reasoning summaries to calibrate final confidence |
| REST API client | Per-phase summaries | Displays investigation progress as per-phase persona summaries |

Contributions are retrieved through `binder.get_persona_contributions(persona_id=..., phase=...)`, which supports filtering by persona and/or phase.

### 5. REST API Exposure

PersonaContributionArtifacts are accessed through the generic artifact endpoints:

**Search contributions by type**:

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=persona_contribution
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `artifact_type` | `str` | Set to `"persona_contribution"` |
| `phase` | `int` | Filter by contribution phase |
| `limit` | `int` | Maximum results (default 50) |

**Get contributions for a specific phase**:

```
GET /api/v1/binders/{binder_id}/artifacts?artifact_type=persona_contribution&phase=2
```

**Response JSON snippet**:

```json
{
  "id": "pc-b3c4d5e6",
  "artifact_type": "persona_contribution",
  "created_by": "Logician",
  "created_at": "2026-02-14T10:37:45.112Z",
  "updated_at": "2026-02-14T10:37:45.112Z",
  "phase": 3,
  "function_name": null,
  "priority": "normal",
  "tags": [],
  "is_deleted": false,
  "content": {
    "persona_id": "Logician",
    "contribution_phase": 3,
    "content": {
      "chains_built": 2,
      "average_validity": 0.83,
      "average_coverage": 0.75,
      "total_steps": 8,
      "assumptions_made": 2,
      "gaps_identified": 1,
      "chain_details": [
        {
          "hypothesis": "Fragment timeout due to hardware link failure",
          "steps": 5,
          "validity": 0.90,
          "coverage": 0.80
        },
        {
          "hypothesis": "Timeout configuration too aggressive",
          "steps": 3,
          "validity": 0.75,
          "coverage": 0.67
        }
      ]
    },
    "confidence": 0.72,
    "reasoning": "Built 2 causal chains with good validity (0.83 average) and adequate evidence coverage (0.75 average). The primary chain for the hardware link failure hypothesis has strong mechanistic support with 4 of 5 steps backed by evidence. The secondary chain for timeout configuration has one critical assumption step."
  }
}
```

### 6. MCP Tool Access

PersonaContributionArtifacts are accessed through the generic MCP artifact tools:

| MCP Tool | Parameters for Contributions | Returns |
|----------|------------------------------|---------|
| `search_artifacts` | `binder_id`, `artifact_type="persona_contribution"`, optional `phase` | JSON array of contribution artifacts |
| `get_artifact` | `binder_id`, `artifact_id` | JSON object with full contribution details |
| `search_artifact_content` | `binder_id`, `query="Logician"`, `artifact_types="persona_contribution"` | JSON array matching persona name |

Example MCP tool call to get all Phase 3 contributions:

```json
{
  "tool": "search_artifacts",
  "arguments": {
    "binder_id": "wb-a1b2c3d4",
    "artifact_type": "persona_contribution",
    "phase": 3
  }
}
```

### 7. Artifact Relationships

PersonaContributionArtifacts do not carry explicit artifact ID references in their schema (unlike Findings with `related_artifacts` or Annotations with `target_artifact_id`). Their relationships are implicit through the `content` dict, which may contain artifact IDs in its values, and through the `phase` field, which associates them with the artifacts produced during that phase.

```
Phase 0 Artifacts                PersonaContributionArtifact (Phase 0)
┌──────────────────┐             ┌──────────────────────────────┐
│ ErrorContext     │◄── phase ── │ persona_id: "Archivist"      │
│ SourceLocation   │             │ contribution_phase: 0        │
│ CallGraph        │             │ content: {                   │
│ CodeSnippet      │             │   source_locations_found: 3, │
└──────────────────┘             │   call_graphs_built: 1,     │
                                 │   patterns_matched: 2       │
Phase 1 Artifacts                │ }                            │
┌──────────────────┐             └──────────────────────────────┘
│ HypothesisArtif. │
│ HypothesisArtif. │             PersonaContributionArtifact (Phase 1)
│ HypothesisArtif. │             ┌──────────────────────────────┐
└──────────────────┘◄── phase ── │ persona_id: "Theorist"       │
                                 │ contribution_phase: 1        │
                                 │ content: {                   │
                                 │   hypotheses_generated: 3,  │
                                 │   top_hypothesis: "...",     │
                                 │   ...                        │
                                 │ }                            │
                                 └──────────────────────────────┘
```

In the expert panel context, PersonaContributionArtifacts from multiple personas at the same phase are siblings, each providing the persona's independent perspective on the same question.

### 8. Session State Mapping

| Session State Concept | Contribution Field | Client View |
|----------------------|-------------------|-------------|
| Phase summary | `content` dict | Per-phase accordion panel showing what happened |
| Persona confidence | `confidence` | Confidence bar/badge for each phase |
| Reasoning explanation | `reasoning` | Expandable explanation text |
| Persona identity | `persona_id` | Persona avatar and name |
| Phase number | `contribution_phase` | Position in investigation timeline |

For expert panel Q&A sessions, the client sees a list of PersonaContributionArtifacts -- one per panelist -- each with the panelist's structured answer. The orchestrator's final aggregated answer is a separate artifact or response, but the individual contributions are preserved for transparency.

### 9. Example

Full realistic JSON for an expert panel Q&A contribution:

```json
{
  "id": "pc-e6f7a8b9",
  "artifact_type": "persona_contribution",
  "created_by": "Devil's Advocate",
  "created_at": "2026-02-14T11:02:33.891Z",
  "updated_at": "2026-02-14T11:02:33.891Z",
  "phase": 4,
  "function_name": null,
  "priority": "normal",
  "tags": ["expert-panel", "qa-session"],
  "is_deleted": false,
  "content": {
    "persona_id": "Devil's Advocate",
    "contribution_phase": 4,
    "content": {
      "challenges": [
        "The claim that hardware link failure is the root cause relies on a single log entry showing 'link 0x0100 timeout'. This could also indicate a software-side buffer overflow preventing timely reads.",
        "No evidence was gathered about the hardware link status register values, which would definitively distinguish hardware failure from software-side read stalls."
      ],
      "concerns": [
        "The 5000ms timeout value appears hardcoded and may be too short for the data rates observed in this configuration.",
        "Similar timeout errors in past investigations were caused by DAQ configuration mismatches 40% of the time."
      ],
      "alternatives": [
        "Software buffer management: if the read buffer is full, getNext_ would block until timeout even with a healthy hardware link.",
        "Configuration mismatch: the link address 0x0100 may not match the actual hardware mapping for this board."
      ]
    },
    "confidence": 0.45,
    "reasoning": "Low confidence in the hardware failure hypothesis due to insufficient discriminating evidence. The single timeout log entry is consistent with at least three different root causes. Without hardware diagnostics or buffer state information, we cannot distinguish between them."
  }
}
```

---

> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 4: Investigation Artifacts](agentic-workbinder-library-ch4-investigation-artifacts.md) | [Next: Ch. 6: Infrastructure Artifacts](agentic-workbinder-library-ch6-infrastructure-artifacts.md)
