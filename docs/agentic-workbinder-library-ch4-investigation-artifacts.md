> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 3: Code Knowledge Artifacts](agentic-workbinder-library-ch3-code-artifacts.md) | [Ch. 5: Observation Artifacts](agentic-workbinder-library-ch5-observation-artifacts.md)

---

# Chapter 4: Investigation Artifacts

The five artifact types documented in this chapter represent the intellectual core of an
investigation. They are the reasoning artifacts -- the structured outputs that capture
what the system thinks happened, why it thinks so, how confident it is, and what
challenges remain. They form a directed chain of reasoning that progresses from
speculation to conclusion:

```
Phase 1               Phase 2              Phase 3             Phase 4              Phase 6
Theorist              Detective            Logician            Devil's Advocate              Synthesizer
   |                     |                    |                   |                    |
   v                     v                    v                   v                    v
+----------+       +-----------+       +-------------+      +------------+      +-------------+
| Hypothesis|----->| Evidence  |------>| CausalChain |----->| Challenge  |----->| Conclusion  |
| Artifact  |<-----| Artifact  |       | Artifact    |      | Artifact   |      | Artifact    |
+----------+       +-----------+       +-------------+      +------------+      +-------------+
     ^                   |                    |                   |                    |
     |                   |                    |                   |                    |
     +------- bidirectional linking ----------+--- references ---+--- synthesizes ----+
```

Hypotheses are generated, evidence is gathered to support or refute them, causal chains
explain the reasoning path from root cause to observed error, challenges stress-test the
conclusions, and a final conclusion synthesizes everything into an actionable report.

These are the most queried artifacts through both the REST API and MCP interface. An
agentic client building its own investigation workflow will spend the majority of its
time reading and writing these five types.

**Permissions summary.** Investigation artifacts follow a strict write-once, read-forward
model. Each artifact type is written by exactly one persona and read by all subsequent
personas. The single exception is `EvidenceArtifact`, which has RW permissions for the
Detective -- the Detective both reads existing evidence (to avoid duplicate queries) and
writes new evidence items.

| Artifact | Writer | Readers | Permission |
|----------|--------|---------|------------|
| HypothesisArtifact | Theorist (Phase 1) | Detective, Logician, Devil's Advocate, Synthesizer | W / R |
| EvidenceArtifact | Detective (Phase 2) | Detective, Logician, Devil's Advocate, Synthesizer | RW / R |
| CausalChainArtifact | Logician (Phase 3) | Devil's Advocate, Synthesizer | W / R |
| ChallengeArtifact | Devil's Advocate (Phase 4) | Synthesizer | W / R |
| ConclusionArtifact | Synthesizer (Phase 6) | -- (final output) | W / -- |

---

## 4.1 HypothesisArtifact

### 1. Purpose & Role

The `HypothesisArtifact` represents a root cause hypothesis -- a proposed explanation for
why the observed error occurred. It is the starting point of the entire reasoning chain.
Without hypotheses, the downstream phases (evidence seeking, causal chain construction,
adversarial review) have nothing to operate on.

In the agentic API context, hypotheses serve as the pivotal navigation objects. A client
can list hypotheses, filter by score or source, and then drill into evidence, causal
chains, and challenges that reference a specific hypothesis. The bidirectional linking
between hypotheses and evidence (via `supporting_evidence_ids` and
`contradicting_evidence_ids`) makes each hypothesis a hub that connects the upstream
generation logic to the downstream evidence gathering.

The artifact preserves fields from the LLM response that were previously discarded in
earlier versions of the pipeline: `category`, `confirming_evidence`, and
`refuting_evidence`. These fields give downstream phases explicit guidance on what
evidence to seek (the Detective uses `confirming_evidence` and `refuting_evidence` to
design discriminating queries).

### 2. Schema

**Base fields** (inherited from `Artifact`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique 16-character UUID prefix |
| `artifact_type` | `ArtifactType` | `HYPOTHESIS_ARTIFACT` | Fixed type discriminator |
| `created_by` | `str` | -- (required) | Persona name that created this artifact |
| `created_at` | `datetime` | `datetime.now()` | Creation timestamp |
| `updated_at` | `datetime` | `datetime.now()` | Last modification timestamp |
| `tags` | `list[str]` | `[]` | Categorization tags |
| `phase` | `int \| None` | `None` | Investigation phase when created (typically 1) |
| `function_name` | `str \| None` | `None` | Related function for index grouping |
| `priority` | `Priority` | `NORMAL` | Priority level (LOW, NORMAL, HIGH, CRITICAL) |
| `is_deleted` | `bool` | `False` | Soft-deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |

**HypothesisArtifact-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | `str` | -- (required) | Clear, specific description of the proposed root cause |
| `source` | `str` | `"fresh"` | How this hypothesis was generated: `pattern_match`, `similar_case`, `fresh`, `alternative`. When category is available, formatted as `source:category` (e.g., `fresh:timing`) |
| `prior_probability` | `float` | `0.5` | Prior probability before evidence (0.0-1.0) |
| `score` | `float` | `0.5` | Current score after evidence scoring (0.0-1.0) |
| `supporting_evidence_ids` | `list[str]` | `[]` | IDs of EvidenceArtifacts that support this hypothesis |
| `contradicting_evidence_ids` | `list[str]` | `[]` | IDs of EvidenceArtifacts that contradict this hypothesis |
| `rank` | `int` | `0` | Position in the ranked hypothesis list (0 = top) |
| `llm_request_id` | `str \| None` | `None` | Links to the LLMRequestArtifact that generated this hypothesis |
| `category` | `str \| None` | `None` | Category classification from LLM (hardware, software, configuration, timing, resource, unknown) |
| `confirming_evidence` | `str \| None` | `None` | Description of evidence that would confirm this hypothesis |
| `refuting_evidence` | `str \| None` | `None` | Description of evidence that would refute this hypothesis |

### 3. Producer

**Phase:** 1 (Hypothesis Generation)
**Persona:** Theorist
**WorkBinder method:** `binder.add_hypothesis()`
**Parser:** `HypothesisParser` in `srcs/workbinder/artifacts/parsers/hypothesis.py`

The Theorist generates hypotheses from five tiers of decreasing confidence:

1. **Code hints** (prior 0.7-0.85) -- Direct evidence from code comments or diagnostic messages
2. **Pattern matches** (prior 0.6-0.8) -- Known error patterns from the knowledge base
3. **Similar cases** (prior 0.3-0.5) -- Past investigations with similar signatures
4. **Fresh LLM hypotheses** (prior <= 0.3) -- Novel hypotheses generated by the LLM
5. **Alternative hypotheses** (prior 0.1) -- Fallback alternatives

The parser converts the LLM response through a two-stage pipeline:

```
LLM JSON  -->  HypothesisItem  -->  Hypothesis (domain model)  -->  HypothesisArtifact
                  (Pydantic)            (srcs.models)                  (WorkBinder)
```

The `category` field from the LLM is incorporated into the `source` field as
`source_prefix:category` (e.g., `fresh:timing`). The `confirming_evidence` and
`refuting_evidence` descriptions are preserved in the artifact for the Detective.

**Lifecycle:** Created once during Phase 1. The `score` and evidence link fields are
updated during Phase 2 as evidence is gathered and linked via
`binder.link_evidence_to_hypothesis()`.

### 4. Consumers

| Phase | Persona | What They Read | How It Influences Behavior |
|-------|---------|----------------|---------------------------|
| 2 | Detective | `description`, `confirming_evidence`, `refuting_evidence`, `id` | Designs discriminating evidence queries targeting specific hypotheses. Uses `confirming_evidence` and `refuting_evidence` to decide what to look for. |
| 3 | Logician | `description`, `score`, `supporting_evidence_ids`, `id` | Builds causal chains for the top-scoring hypotheses. Only hypotheses above a score threshold get chains. |
| 4 | Devil's Advocate | `description`, `score`, `supporting_evidence_ids`, `contradicting_evidence_ids` | Evaluates whether the evidence actually supports the claims. Challenges hypotheses with weak evidence or missing links. |
| 6 | Synthesizer | All fields | Reports ranked hypotheses in the final conclusion. Uses `score`, `rank`, and evidence counts to determine the primary root cause. |

### 5. REST API Exposure

**Endpoint:** `GET /api/v1/binders/{binder_id}/hypotheses`

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_score` | `float` | `None` | Minimum hypothesis score (0.0-1.0) |
| `source` | `str` | `None` | Filter by source (pattern, similar, fresh, alternative) |
| `limit` | `int` | `50` | Maximum results (1-500) |

**Response snippet:**

```json
{
  "artifacts": [
    {
      "id": "a1b2c3d4",
      "artifact_type": "hypothesis_artifact",
      "created_by": "Theorist",
      "created_at": "2026-02-14T10:15:30.123456",
      "updated_at": "2026-02-14T10:22:45.654321",
      "phase": 1,
      "function_name": null,
      "priority": "normal",
      "tags": [],
      "is_deleted": false,
      "content": {
        "description": "Fragment generator initialization timeout causes null pointer in BoardReader::processFragment()",
        "source": "fresh:timing",
        "prior_probability": 0.3,
        "score": 0.72,
        "supporting_evidence_ids": ["ev-001a", "ev-003b"],
        "contradicting_evidence_ids": [],
        "rank": 0,
        "llm_request_id": "req-7f8e",
        "category": "timing",
        "confirming_evidence": "Log showing fragment generator initialization failure or timeout before the crash",
        "refuting_evidence": "Log showing fragment generator successfully initialized before first processFragment call"
      }
    }
  ],
  "total": 4
}
```

**Also available via generic endpoints:**

- `GET /api/v1/binders/{binder_id}/artifacts?artifact_type=hypothesis_artifact` -- generic artifact query
- `GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}` -- single artifact by ID
- `POST /api/v1/binders/{binder_id}/artifacts/search` -- full-text search across content

### 6. MCP Tool Access

**Tool:** `get_hypotheses`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binder_id` | `str` | -- (required) | The binder ID to query |
| `min_score` | `float \| None` | `None` | Minimum hypothesis score filter |
| `source` | `str \| None` | `None` | Filter by source (pattern, similar, fresh, alternative) |
| `limit` | `int` | `50` | Maximum results |

Returns a JSON array of hypothesis artifacts with all fields serialized via
`model_dump(mode="json")`.

**Also queryable via:**

- `search_artifacts` with `artifact_type="hypothesis_artifact"` -- generic filtered search
- `get_artifact` with specific `artifact_id` -- single artifact retrieval
- `search_artifact_content` with query string -- full-text content search

### 7. Artifact Relationships

```
                      +------------------+
                      | LLMRequestArtifact|
                      |   (Phase 1)      |
                      +--------+---------+
                               |
                      llm_request_id
                               |
                               v
+----------------+    +------------------+    +------------------+
| EvidenceArtifact|--->| HypothesisArtifact|<---| CausalChainArtifact|
| supports_       |    |                  |    | hypothesis_id    |
| hypothesis_ids  |    | supporting_      |    +------------------+
|                 |<---| evidence_ids     |
| contradicts_    |    |                  |    +------------------+
| hypothesis_ids  |    | contradicting_   |--->| ChallengeArtifact|
|                 |<---| evidence_ids     |    | target_hypothesis|
+----------------+    +------------------+    | _id              |
                                              +------------------+
```

**Key relationships:**

- **HypothesisArtifact <-> EvidenceArtifact**: Bidirectional. Hypotheses track which
  evidence supports or contradicts them. Evidence tracks which hypotheses it supports or
  contradicts. The `link_evidence_to_hypothesis()` method updates both sides atomically.
- **HypothesisArtifact -> LLMRequestArtifact**: Unidirectional via `llm_request_id`.
  Traces which LLM call generated this hypothesis.
- **CausalChainArtifact -> HypothesisArtifact**: Unidirectional via `hypothesis_id`.
  Each causal chain explains one hypothesis.
- **ChallengeArtifact -> HypothesisArtifact**: Unidirectional via
  `target_hypothesis_id`. Each challenge targets one hypothesis.

### 8. Session State Mapping

In the agentic REST API, the client sees hypotheses as part of the binder's artifact
collection. The binder endpoint `GET /binders/{id}/hypotheses` provides a specialized
view with score and source filtering. The generic artifact endpoints also surface
hypotheses.

The client can observe hypothesis evolution through the investigation:

1. **Phase 1 (creation):** Hypotheses appear with initial `prior_probability` and
   `score` equal to the prior. `supporting_evidence_ids` and
   `contradicting_evidence_ids` are empty.
2. **Phase 2 (evidence linking):** As the Detective gathers evidence, the
   `supporting_evidence_ids` and `contradicting_evidence_ids` lists grow. The `score`
   is updated to reflect evidence.
3. **Phase 3+ (downstream use):** The hypothesis is read but not further modified.
   The `rank` and `score` remain as set during Phase 2.

The `updated_at` timestamp changes each time evidence is linked, providing a natural
indicator of hypothesis activity.

### 9. Example

```json
{
  "id": "hyp-3f8a",
  "artifact_type": "hypothesis_artifact",
  "created_by": "Theorist",
  "created_at": "2026-02-14T10:15:30.123456",
  "updated_at": "2026-02-14T10:22:45.654321",
  "tags": [],
  "phase": 1,
  "function_name": null,
  "priority": "normal",
  "is_deleted": false,
  "deleted_by": null,
  "deleted_reason": null,
  "description": "Fragment generator initialization timeout due to hardware readout delay causes null pointer dereference in BoardReader::processFragment() when generator_ is not yet ready",
  "source": "fresh:timing",
  "prior_probability": 0.3,
  "score": 0.72,
  "supporting_evidence_ids": ["ev-a1b2", "ev-c3d4"],
  "contradicting_evidence_ids": [],
  "rank": 0,
  "llm_request_id": "req-7f8e",
  "category": "timing",
  "confirming_evidence": "Log entries showing fragment generator initialization took longer than expected, or a startup timeout before first processFragment call",
  "refuting_evidence": "Log entries showing fragment generator initialized successfully and was ready before processFragment was first invoked"
}
```

---

## 4.2 EvidenceArtifact

### 1. Purpose & Role

The `EvidenceArtifact` captures a single piece of evidence gathered during the
investigation -- a log entry, a code observation, a pattern match, or a dataflow trace
that either supports or refutes one or more hypotheses. Evidence is the empirical
backbone of the investigation; without it, hypotheses remain speculation.

In the agentic API context, evidence artifacts are the most numerous investigation
artifacts in a typical binder. The Detective gathers up to 10 iterations of evidence
queries, each producing multiple evidence items. Clients filter evidence by type
(code, log, pattern, dataflow), strength (STRONG, MODERATE, WEAK), and hypothesis
linkage.

The `EvidenceArtifact` is unique among investigation artifacts in that it carries
**counterfactual scoring fields**: `expected_if_true` and `expected_if_false`. These
record what the Detective expected to find if the target hypothesis is correct versus
incorrect, enabling downstream phases to assess how discriminating each piece of evidence
actually is. The `found` field distinguishes positive evidence (something was observed)
from absence evidence (something expected was not found).

This is the only artifact type with **RW permissions** for its producer. The Detective
both reads existing evidence (to check what has already been gathered and avoid duplicate
queries) and writes new evidence items.

### 2. Schema

**Base fields** (inherited from `Artifact`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique 16-character UUID prefix |
| `artifact_type` | `ArtifactType` | `EVIDENCE_ARTIFACT` | Fixed type discriminator |
| `created_by` | `str` | -- (required) | Persona name that created this artifact |
| `created_at` | `datetime` | `datetime.now()` | Creation timestamp |
| `updated_at` | `datetime` | `datetime.now()` | Last modification timestamp |
| `tags` | `list[str]` | `[]` | Categorization tags |
| `phase` | `int \| None` | `None` | Investigation phase when created (typically 2) |
| `function_name` | `str \| None` | `None` | Related function for index grouping |
| `priority` | `Priority` | `NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft-deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |

**EvidenceArtifact-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `evidence_type` | `str` | -- (required) | Evidence category: `log`, `code`, `pattern`, `dataflow` |
| `content` | `str` | -- (required) | The evidence content or description |
| `source` | `str` | -- (required) | Where this evidence was found (query type, function name, etc.) |
| `strength` | `str` | `"MODERATE"` | Evidence strength: `STRONG`, `MODERATE`, `WEAK` |
| `supports_hypothesis_ids` | `list[str]` | `[]` | IDs of hypotheses this evidence supports |
| `contradicts_hypothesis_ids` | `list[str]` | `[]` | IDs of hypotheses this evidence contradicts |
| `llm_request_id` | `str \| None` | `None` | Links to the LLMRequestArtifact if evidence came from an LLM query |
| `found` | `bool` | `True` | Whether evidence was actually found. `False` for absence evidence (expected something but did not find it) |
| `timestamp` | `datetime` | `datetime.now()` | When this evidence was gathered |
| `targets_hypothesis_id` | `str \| None` | `None` | ID of the specific hypothesis this evidence was gathered to test |
| `expected_if_true` | `str \| None` | `None` | What we expected to find if the target hypothesis is correct |
| `expected_if_false` | `str \| None` | `None` | What we expected to find if the target hypothesis is incorrect |

### 3. Producer

**Phase:** 2 (Evidence Seeking)
**Persona:** Detective
**WorkBinder method:** `binder.add_evidence()`
**Parser:** `EvidenceQueryParser` in `srcs/workbinder/artifacts/parsers/evidence.py`

The Detective operates in an iterative loop (up to 10 iterations) with an adaptive
strategy -- code-centric when source locations are available, log-centric otherwise.
Each iteration:

1. The LLM generates evidence queries (parsed by `EvidenceQueryParser` into
   `QueryItem` objects)
2. Queries are executed against logs, code, patterns, and the knowledge base
3. Results are converted to `EvidenceItem` domain models
4. Each `EvidenceItem` is stored as an `EvidenceArtifact` via `binder.add_evidence()`
5. Evidence is linked to hypotheses via `binder.link_evidence_to_hypothesis()`

The parser conversion flow:

```
LLM JSON  -->  QueryItem     -->  (query execution)  -->  EvidenceItem  -->  EvidenceArtifact
                 (query spec)                               (result)          (WorkBinder)
```

**Lifecycle:** Evidence artifacts are created throughout Phase 2 (potentially dozens per
investigation). They are linked to hypotheses via `link_evidence_to_hypothesis()`, which
updates both the evidence's `supports_hypothesis_ids`/`contradicts_hypothesis_ids` and
the hypothesis's `supporting_evidence_ids`/`contradicting_evidence_ids`.

### 4. Consumers

| Phase | Persona | What They Read | How It Influences Behavior |
|-------|---------|----------------|---------------------------|
| 2 | Detective | All fields (self-read) | Checks existing evidence to avoid duplicate queries. Reviews gap analysis to determine next iteration queries. |
| 3 | Logician | `content`, `source`, `strength`, `id`, `supports_hypothesis_ids` | Cites evidence IDs in causal chain steps. Only uses evidence that supports the target hypothesis. Marks steps without evidence as assumptions. |
| 4 | Devil's Advocate | `content`, `strength`, `found`, `expected_if_true`, `expected_if_false` | Evaluates whether evidence actually discriminates between hypotheses. Challenges weak evidence, absence evidence, and unmet expectations. |
| 6 | Synthesizer | All fields | Reports key evidence in the final conclusion. Counts evidence strength to inform confidence calibration. |

### 5. REST API Exposure

**Endpoint:** `GET /api/v1/binders/{binder_id}/evidence`

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `evidence_type` | `str` | `None` | Filter by type (code, log, pattern, dataflow) |
| `strength` | `str` | `None` | Filter by strength (STRONG, MODERATE, WEAK) |
| `limit` | `int` | `100` | Maximum results (1-500) |

**Response snippet:**

```json
{
  "artifacts": [
    {
      "id": "ev-a1b2",
      "artifact_type": "evidence_artifact",
      "created_by": "Detective",
      "created_at": "2026-02-14T10:18:22.456789",
      "updated_at": "2026-02-14T10:18:22.456789",
      "phase": 2,
      "function_name": null,
      "priority": "normal",
      "tags": ["code-evidence", "null-check"],
      "is_deleted": false,
      "content": {
        "evidence_type": "code",
        "content": "BoardReader::processFragment() at line 142 dereferences generator_ without null check: generator_->getFragment(). No guard clause exists.",
        "source": "function_lookup:processFragment",
        "strength": "STRONG",
        "supports_hypothesis_ids": ["hyp-3f8a"],
        "contradicts_hypothesis_ids": [],
        "llm_request_id": "req-b2c3",
        "found": true,
        "timestamp": "2026-02-14T10:18:22.456789",
        "targets_hypothesis_id": "hyp-3f8a",
        "expected_if_true": "Function dereferences generator_ without null check",
        "expected_if_false": "Function has null check with proper error handling"
      }
    }
  ],
  "total": 12
}
```

### 6. MCP Tool Access

**Tool:** `get_evidence`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binder_id` | `str` | -- (required) | The binder ID to query |
| `evidence_type` | `str \| None` | `None` | Filter by type (code, log, pattern, etc.) |
| `strength` | `str \| None` | `None` | Filter by strength (STRONG, MODERATE, WEAK) |
| `limit` | `int` | `100` | Maximum results |

Returns a JSON array of evidence artifacts.

**Also queryable via:**

- `search_artifacts` with `artifact_type="evidence_artifact"` -- generic filtered search
- `get_artifact` with specific `artifact_id` -- single artifact retrieval
- `search_artifact_content` with query string -- full-text content search

### 7. Artifact Relationships

```
+------------------+       +------------------+       +------------------+
| LLMRequestArtifact|       | HypothesisArtifact|       | CausalChainArtifact|
| (Detective query) |       | (target)         |       | (cites evidence) |
+--------+---------+       +--------+---------+       +--------+---------+
         |                          ^    ^                      |
    llm_request_id        supports_ |    | contradicts_    evidence_ids
         |                hypothesis|    |_hypothesis       (in steps)
         v                   _ids   |    |  _ids                |
+------------------+                |    |                      |
| EvidenceArtifact |----------------+    +----------------------+
|                  |                                            |
| targets_         |-----> (specific hypothesis targeted)       |
|  hypothesis_id   |                                            |
+------------------+<-------------------------------------------+
```

**Key relationships:**

- **EvidenceArtifact <-> HypothesisArtifact**: Bidirectional via
  `supports_hypothesis_ids`/`contradicts_hypothesis_ids` on the evidence side and
  `supporting_evidence_ids`/`contradicting_evidence_ids` on the hypothesis side. Managed
  by `binder.link_evidence_to_hypothesis()`.
- **EvidenceArtifact -> HypothesisArtifact** (targeting): Unidirectional via
  `targets_hypothesis_id`. Records which hypothesis this evidence was specifically
  gathered to test (may differ from which hypotheses it actually supports).
- **EvidenceArtifact -> LLMRequestArtifact**: Unidirectional via `llm_request_id`.
  Traces which LLM query generated the query that found this evidence.
- **CausalChainArtifact -> EvidenceArtifact**: Unidirectional via `evidence_ids` in
  each chain step. Causal chain steps cite evidence by ID.

### 8. Session State Mapping

Evidence artifacts accumulate over multiple iterations during Phase 2. A client polling
the binder will see the evidence count grow as the Detective works. Key observations:

1. **Iterative growth:** Evidence appears in waves (one per Detective iteration, up to
   10 iterations). Each wave adds several evidence items.
2. **Linking lag:** Evidence is first created with empty
   `supports_hypothesis_ids`/`contradicts_hypothesis_ids`, then linked shortly after
   via `link_evidence_to_hypothesis()`. A client may briefly see unlinked evidence.
3. **Counterfactual fields:** The `expected_if_true` and `expected_if_false` fields
   are set at creation time and never change. They represent the Detective's prediction
   before executing the query.
4. **Absence evidence:** Items with `found=false` indicate the Detective looked for
   something and did not find it. These are still valuable -- absence of expected
   evidence can refute a hypothesis.
5. **Tags:** Evidence artifacts may carry tags like `"code-evidence"` or
   `"log-evidence"` for categorization.

### 9. Example

```json
{
  "id": "ev-c3d4",
  "artifact_type": "evidence_artifact",
  "created_by": "Detective",
  "created_at": "2026-02-14T10:19:05.789012",
  "updated_at": "2026-02-14T10:19:05.789012",
  "tags": ["log-evidence", "timing"],
  "phase": 2,
  "function_name": null,
  "priority": "normal",
  "is_deleted": false,
  "deleted_by": null,
  "deleted_reason": null,
  "evidence_type": "log",
  "content": "Log entry at 14:32:01.445: 'FragmentGenerator::initialize() completed in 3502ms (timeout threshold: 3000ms)' -- initialization exceeded timeout threshold by 502ms, indicating the generator was not ready when processFragment() was first called at 14:32:01.100",
  "source": "log_search:FragmentGenerator::initialize",
  "strength": "STRONG",
  "supports_hypothesis_ids": ["hyp-3f8a"],
  "contradicts_hypothesis_ids": ["hyp-9e1f"],
  "llm_request_id": "req-d4e5",
  "found": true,
  "timestamp": "2026-02-14T10:19:05.789012",
  "targets_hypothesis_id": "hyp-3f8a",
  "expected_if_true": "Log showing fragment generator initialization took longer than expected or timed out",
  "expected_if_false": "Log showing fragment generator initialized within normal time bounds"
}
```

---

## 4.3 CausalChainArtifact

### 1. Purpose & Role

The `CausalChainArtifact` captures a causal chain -- a sequence of cause-and-effect
steps that explains how a root cause (identified by a hypothesis) led to the observed
error. It transforms the abstract claim of a hypothesis into a concrete, step-by-step
narrative supported by evidence citations.

In the agentic API context, causal chains are the bridge between "what we think happened"
(hypotheses) and "how we think it happened" (mechanism). A client reviewing an
investigation reads the causal chain to understand the reasoning path. The quality
metrics (`completeness_score`, `logical_validity`, `evidence_coverage`) provide
machine-readable indicators of chain quality that can drive automated decisions about
whether to accept the conclusion or seek more evidence.

Each step in the chain records its evidence IDs, enabling full traceability from
conclusion back to raw evidence. Steps without evidence are explicitly marked as
assumptions (`is_assumption: true`), making the reasoning gaps visible.

### 2. Schema

**Base fields** (inherited from `Artifact`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique 16-character UUID prefix |
| `artifact_type` | `ArtifactType` | `CAUSAL_CHAIN` | Fixed type discriminator |
| `created_by` | `str` | -- (required) | Persona name that created this artifact |
| `created_at` | `datetime` | `datetime.now()` | Creation timestamp |
| `updated_at` | `datetime` | `datetime.now()` | Last modification timestamp |
| `tags` | `list[str]` | `[]` | Categorization tags |
| `phase` | `int \| None` | `None` | Investigation phase when created (typically 3) |
| `function_name` | `str \| None` | `None` | Related function for index grouping |
| `priority` | `Priority` | `NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft-deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |

**CausalChainArtifact-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hypothesis_id` | `str` | -- (required) | ID of the HypothesisArtifact this chain explains |
| `steps` | `list[CausalStep]` | `[]` | Ordered chain steps from root cause to observed error |
| `completeness_score` | `float` | `0.0` | Overall chain completeness (0.0-1.0) |
| `logical_validity` | `float` | `0.0` | Proportion of steps that have mechanisms explaining how cause produces effect |
| `evidence_coverage` | `float` | `0.0` | Proportion of steps that are not assumptions (have evidence citations) |
| `gaps` | `list[str]` | `[]` | Identified gaps in the causal reasoning |
| `assumptions` | `list[str]` | `[]` | Assumptions made in the chain |
| `llm_request_id` | `str \| None` | `None` | Links to the LLMRequestArtifact that generated this chain |

**Step structure** (each element of `steps`):

Each step is a `CausalStep` Pydantic model defined in `srcs/workbinder/artifacts/causal_chain.py`:

```python
class CausalStep(BaseModel):
    """A single step in a causal chain linking root cause to observed error."""

    step_order: int = 0
    claim: str = ""
    mechanism: str = ""
    evidence_ids: list[str] = []
    is_assumption: bool = False
    assumption_note: str = ""
    evidence_strength: str = ""
```

| Field | Type | Description |
|-------|------|-------------|
| `step_order` | `int` | Position in the chain (0-based) |
| `claim` | `str` | The causal claim (e.g., "A causes B") |
| `mechanism` | `str` | How the cause actually produces the effect |
| `evidence_ids` | `list[str]` | IDs of EvidenceArtifacts supporting this step |
| `is_assumption` | `bool` | `true` if no evidence supports this step |
| `assumption_note` | `str` | Explanation of why this is an assumption |
| `evidence_strength` | `str` | Aggregate strength of cited evidence |

With this change, the `steps` field on `CausalChainArtifact` becomes `list[CausalStep]` instead of `list[dict[str, Any]]`, enabling Pydantic validation on each step.

### 3. Producer

**Phase:** 3 (Causal Chain Construction)
**Persona:** Logician
**WorkBinder method:** `binder.add_causal_chain()`
**Parser:** `CausalChainParser` in `srcs/workbinder/artifacts/parsers/causal_chain.py`

The Logician builds one causal chain per top-scoring hypothesis. The parser handles a
field mapping from the LLM response format: the LLM returns `evidence` (a list of
evidence IDs per step) which maps to `evidence_ids` in the domain model.

The parser conversion flow:

```
LLM JSON  -->  ChainStepItem  -->  CausalStep (domain model)  -->  CausalChainArtifact
                  (per step)          (srcs.models)                   (WorkBinder)
```

Quality metrics are computed after parsing:
- `logical_validity` = proportion of steps where `mechanism` is non-empty
- `evidence_coverage` = proportion of steps where `is_assumption` is `false`

**Reference validation:** When `binder.add_causal_chain()` is called, the binder
validates that `hypothesis_id` references an existing `HypothesisArtifact`. If the
reference is invalid, a `ValueError` is raised.

### 4. Consumers

| Phase | Persona | What They Read | How It Influences Behavior |
|-------|---------|----------------|---------------------------|
| 4 | Devil's Advocate | `steps`, `evidence_coverage`, `hypothesis_id` | Identifies weak steps (assumptions without evidence), challenges logical gaps, questions whether mechanism explanations are plausible. Targets steps with `is_assumption: true`. |
| 6 | Synthesizer | All fields | Presents the causal narrative in the final report. Uses quality metrics to adjust confidence. Reports assumption steps as caveats. |

### 5. REST API Exposure

**Endpoint:** `GET /api/v1/binders/{binder_id}/chains`

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hypothesis_id` | `str` | `None` | Filter by linked hypothesis ID |
| `limit` | `int` | `20` | Maximum results (1-500) |

**Response snippet:**

```json
{
  "artifacts": [
    {
      "id": "cc-5e6f",
      "artifact_type": "causal_chain",
      "created_by": "Logician",
      "created_at": "2026-02-14T10:25:12.345678",
      "updated_at": "2026-02-14T10:25:12.345678",
      "phase": 3,
      "function_name": null,
      "priority": "normal",
      "tags": [],
      "is_deleted": false,
      "content": {
        "hypothesis_id": "hyp-3f8a",
        "steps": [
          {
            "step_order": 0,
            "claim": "Hardware readout delay causes FragmentGenerator initialization to exceed 3-second timeout",
            "mechanism": "The FPGA board requires a warm-up period after power-on; the FragmentGenerator::initialize() call blocks on a register read that takes 3.5s instead of the expected 2s",
            "evidence_ids": ["ev-c3d4"],
            "is_assumption": false,
            "assumption_note": "",
            "evidence_strength": "STRONG"
          },
          {
            "step_order": 1,
            "claim": "Timeout during initialization leaves generator_ in null state",
            "mechanism": "When initialize() exceeds the timeout threshold, the generator object is created but the internal state pointer remains nullptr because the hardware handshake never completed",
            "evidence_ids": [],
            "is_assumption": true,
            "assumption_note": "No log entry confirms the internal state pointer value; inferred from code path analysis",
            "evidence_strength": ""
          },
          {
            "step_order": 2,
            "claim": "processFragment() dereferences null generator_ pointer",
            "mechanism": "BoardReader::processFragment() calls generator_->getFragment() at line 142 without a null check, causing a segmentation fault",
            "evidence_ids": ["ev-a1b2"],
            "is_assumption": false,
            "assumption_note": "",
            "evidence_strength": "STRONG"
          }
        ],
        "completeness_score": 0.0,
        "logical_validity": 1.0,
        "evidence_coverage": 0.67,
        "llm_request_id": "req-e5f6"
      }
    }
  ],
  "total": 2
}
```

### 6. MCP Tool Access

**Tool:** `get_causal_chains`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binder_id` | `str` | -- (required) | The binder ID to query |
| `hypothesis_id` | `str \| None` | `None` | Filter by linked hypothesis ID |
| `limit` | `int` | `20` | Maximum results |

Returns a JSON array of causal chain artifacts.

**Also queryable via:**

- `search_artifacts` with `artifact_type="causal_chain"` -- generic filtered search
- `get_artifact` with specific `artifact_id` -- single artifact retrieval

### 7. Artifact Relationships

```
+------------------+
| HypothesisArtifact|
| (the claim)      |
+--------+---------+
         ^
         | hypothesis_id
         |
+------------------+         +------------------+
| CausalChainArtifact|------->| EvidenceArtifact |
| steps[].          |         | (cited in steps) |
| evidence_ids      |         +------------------+
+--------+---------+
         |
         | (challenged by)
         v
+------------------+         +------------------+
| ChallengeArtifact|         | LLMRequestArtifact|
| (targets chain   |         | (generated chain) |
| via hypothesis)  |         +------------------+
+------------------+                ^
                              llm_request_id
```

**Key relationships:**

- **CausalChainArtifact -> HypothesisArtifact**: Each chain explains exactly one
  hypothesis via `hypothesis_id`. The binder validates this reference at creation time.
- **CausalChainArtifact -> EvidenceArtifact**: Each step cites evidence via
  `evidence_ids`. These are not validated at creation time (the LLM may reference
  evidence by ID that exists in the binder).
- **CausalChainArtifact -> LLMRequestArtifact**: Traces which LLM call produced the
  chain via `llm_request_id`.

### 8. Session State Mapping

Causal chains appear in the binder after Phase 3 completes. Typically there is one chain
per top-scoring hypothesis (usually 1-3 chains total). Key observations for the client:

1. **Late arrival:** Causal chains do not appear until after evidence gathering is
   complete. A client monitoring the binder in real-time will see hypotheses and evidence
   accumulate during Phases 1-2, then chains appear during Phase 3.
2. **Quality indicators:** The `evidence_coverage` field tells the client what fraction
   of the chain is backed by evidence versus assumption. A value below 0.5 suggests the
   chain has significant gaps.
3. **Step inspection:** Clients should render the `steps` array in order, flagging
   `is_assumption: true` steps as areas of uncertainty.
4. **One chain per hypothesis:** The `hypothesis_id` filter on the REST endpoint and MCP
   tool allows the client to retrieve the chain for a specific hypothesis.

### 9. Example

```json
{
  "id": "cc-5e6f",
  "artifact_type": "causal_chain",
  "created_by": "Logician",
  "created_at": "2026-02-14T10:25:12.345678",
  "updated_at": "2026-02-14T10:25:12.345678",
  "tags": [],
  "phase": 3,
  "function_name": null,
  "priority": "normal",
  "is_deleted": false,
  "deleted_by": null,
  "deleted_reason": null,
  "hypothesis_id": "hyp-3f8a",
  "steps": [
    {
      "step_order": 0,
      "claim": "FPGA board warm-up delay exceeds FragmentGenerator initialization timeout",
      "mechanism": "The FPGA requires approximately 3.5 seconds of warm-up after power-on. FragmentGenerator::initialize() issues a blocking register read during this period. The 3-second timeout fires before the hardware responds.",
      "evidence_ids": ["ev-c3d4"],
      "is_assumption": false,
      "assumption_note": "",
      "evidence_strength": "STRONG"
    },
    {
      "step_order": 1,
      "claim": "Timeout leaves generator_ internal state pointer as nullptr",
      "mechanism": "When initialize() times out, the FragmentGenerator object exists but its internal readout_buffer_ pointer was never assigned because the hardware handshake did not complete. The constructor sets readout_buffer_ to nullptr, and initialize() is the only place that assigns it.",
      "evidence_ids": [],
      "is_assumption": true,
      "assumption_note": "Inferred from code analysis of FragmentGenerator constructor and initialize() -- no runtime log confirms the nullptr value",
      "evidence_strength": ""
    },
    {
      "step_order": 2,
      "claim": "BoardReader::processFragment() dereferences nullptr via generator_->getFragment()",
      "mechanism": "processFragment() at line 142 calls generator_->getFragment() which internally accesses readout_buffer_->data(). Since readout_buffer_ is nullptr, this triggers a segmentation fault.",
      "evidence_ids": ["ev-a1b2"],
      "is_assumption": false,
      "assumption_note": "",
      "evidence_strength": "STRONG"
    }
  ],
  "completeness_score": 0.0,
  "logical_validity": 1.0,
  "evidence_coverage": 0.67,
  "llm_request_id": "req-e5f6"
}
```

---

## 4.4 ChallengeArtifact

### 1. Purpose & Role

The `ChallengeArtifact` represents an adversarial challenge -- a structured objection
raised against the investigation's conclusions during the review phase. Challenges
force the investigation to confront its weaknesses before presenting a final answer.

In the agentic API context, challenges serve as quality indicators. A client can
inspect unresolved challenges to understand the confidence limitations of the
investigation. The `severity` field (HIGH, MEDIUM, LOW) and `requires_response` flag
help clients prioritize which challenges matter most. HIGH severity challenges that are
unresolved directly reduce the final confidence score.

Challenges target specific hypotheses (via `target_hypothesis_id`), creating a clear
link between the objection and the claim being questioned. The `resolved` flag and
`resolution` field track whether and how each challenge was addressed.

### 2. Schema

**Base fields** (inherited from `Artifact`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique 16-character UUID prefix |
| `artifact_type` | `ArtifactType` | `CHALLENGE` | Fixed type discriminator |
| `created_by` | `str` | -- (required) | Persona name that created this artifact |
| `created_at` | `datetime` | `datetime.now()` | Creation timestamp |
| `updated_at` | `datetime` | `datetime.now()` | Last modification timestamp |
| `tags` | `list[str]` | `[]` | Categorization tags |
| `phase` | `int \| None` | `None` | Investigation phase when created (typically 4) |
| `function_name` | `str \| None` | `None` | Related function for index grouping |
| `priority` | `Priority` | `NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft-deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |

**ChallengeArtifact-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_hypothesis_id` | `str` | -- (required) | ID of the HypothesisArtifact being challenged |
| `challenge_type` | `str` | `""` | Type of challenge (e.g., `"evidence_gap"`, `"alternative_explanation"`, `"logical_flaw"`) |
| `content` | `str` | -- (required) | Specific description of the challenge or objection |
| `severity` | `str` | `"MEDIUM"` | Challenge severity: `HIGH`, `MEDIUM`, `LOW` |
| `requires_response` | `bool` | `True` | Whether this challenge must be addressed before accepting the conclusion |
| `resolved` | `bool` | `False` | Whether the challenge has been resolved |
| `resolution` | `str \| None` | `None` | How the challenge was resolved (if resolved) |
| `llm_request_id` | `str \| None` | `None` | Links to the LLMRequestArtifact that generated this challenge |

### 3. Producer

**Phase:** 4 (Adversarial Review)
**Persona:** Devil's Advocate
**WorkBinder method:** `binder.add_challenge()`
**Parser:** `ChallengeParser` in `srcs/workbinder/artifacts/parsers/challenge.py`

The Devil's Advocate reviews all prior artifacts and generates challenges through structural
analysis. The parser handles field mapping from the LLM response:

- LLM field `type` maps to domain model `challenge_type`
- LLM value `"missing"` is normalized to `"missing_evidence"`
- The `requires_response` flag is automatically set to `true` for HIGH severity
  challenges

Challenge types from the LLM:

| Type | Description |
|------|-------------|
| `logical_flaw` | Problem with the causal reasoning chain |
| `weak_evidence` | Evidence does not actually support the claim |
| `alternative` | A different explanation fits the evidence better |
| `missing` / `missing_evidence` | Evidence gap that should have been filled |

The parser conversion flow:

```
LLM JSON  -->  ChallengeItem  -->  Challenge (domain model)  -->  ChallengeArtifact
                  (Pydantic)          (srcs.models)                  (WorkBinder)
```

**Reference validation:** When `binder.add_challenge()` is called, the binder validates
that `target_hypothesis_id` references an existing `HypothesisArtifact`. If the reference
is invalid, a `ValueError` is raised.

### 4. Consumers

| Phase | Persona | What They Read | How It Influences Behavior |
|-------|---------|----------------|---------------------------|
| 6 | Synthesizer | `content`, `severity`, `resolved`, `resolution`, `requires_response` | Reports unresolved challenges in the conclusion. HIGH severity unresolved challenges lower the confidence score and may change the outcome from CONFIDENT to PROBABLE or UNCERTAIN. Resolved challenges are noted but do not penalize confidence. |

### 5. REST API Exposure

**Endpoint:** `GET /api/v1/binders/{binder_id}/challenges`

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resolved` | `bool` | `None` | Filter by resolution status |
| `severity` | `str` | `None` | Filter by severity (LOW, MEDIUM, HIGH) |
| `limit` | `int` | `50` | Maximum results (1-500) |

**Response snippet:**

```json
{
  "artifacts": [
    {
      "id": "ch-7g8h",
      "artifact_type": "challenge",
      "created_by": "Devil's Advocate",
      "created_at": "2026-02-14T10:28:33.567890",
      "updated_at": "2026-02-14T10:28:33.567890",
      "phase": 4,
      "function_name": null,
      "priority": "normal",
      "tags": [],
      "is_deleted": false,
      "content": {
        "target_hypothesis_id": "hyp-3f8a",
        "content": "The causal chain assumes the generator_ internal state pointer is nullptr after timeout (step 1), but no runtime evidence confirms this. The timeout handler in FragmentGenerator::initialize() might set a partial state that does not cause a null dereference but instead produces corrupted data.",
        "severity": "MEDIUM",
        "requires_response": false,
        "resolved": false,
        "resolution": null,
        "llm_request_id": "req-f6g7"
      }
    }
  ],
  "total": 3
}
```

### 6. MCP Tool Access

**Tool:** `get_challenges`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `binder_id` | `str` | -- (required) | The binder ID to query |
| `resolved` | `bool \| None` | `None` | Filter by resolution status |
| `severity` | `str \| None` | `None` | Filter by severity (LOW, MEDIUM, HIGH) |
| `limit` | `int` | `50` | Maximum results |

Returns a JSON array of challenge artifacts.

**Also queryable via:**

- `search_artifacts` with `artifact_type="challenge"` -- generic filtered search
- `get_artifact` with specific `artifact_id` -- single artifact retrieval

### 7. Artifact Relationships

```
+------------------+
| HypothesisArtifact|
| (being challenged)|
+--------+---------+
         ^
         | target_hypothesis_id
         |
+------------------+         +------------------+
| ChallengeArtifact|         | LLMRequestArtifact|
| (the objection)  |         | (generated this) |
+--------+---------+         +------------------+
         |                          ^
         |                   llm_request_id
         |                          |
         +--------------------------+
         |
         | (read by)
         v
+------------------+
| ConclusionArtifact|
| unresolved_      |
|  challenges[]    |
+------------------+
```

**Key relationships:**

- **ChallengeArtifact -> HypothesisArtifact**: Each challenge targets exactly one
  hypothesis via `target_hypothesis_id`. The binder validates this reference at creation
  time.
- **ChallengeArtifact -> LLMRequestArtifact**: Traces which LLM call generated the
  challenge via `llm_request_id`.
- **ConclusionArtifact -> ChallengeArtifact**: The conclusion's
  `unresolved_challenges` field lists challenge descriptions (as strings, not IDs) for
  challenges that were not resolved.

### 8. Session State Mapping

Challenges appear in the binder after Phase 4 completes. Typically 2-6 challenges are
generated per investigation. Key observations for the client:

1. **Resolution tracking:** Challenges may be resolved during the investigation (the
   Synthesizer or a review loop may set `resolved=true` and `resolution` text). A client
   should check both `resolved` and `requires_response` to understand the impact.
2. **Severity as priority:** HIGH severity with `requires_response=true` means the
   investigation acknowledges a significant gap. MEDIUM and LOW severity challenges are
   noted but do not block conclusions.
3. **Filtering for unresolved:** The REST API and MCP tool support `resolved=false`
   filtering, which is the most common client query -- "show me what is still
   problematic."
4. **Impact on outcome:** The number and severity of unresolved challenges directly
   influence the final `ConclusionArtifact` outcome. An investigation with unresolved
   HIGH challenges is unlikely to reach CONFIDENT status.

### 9. Example

```json
{
  "id": "ch-7g8h",
  "artifact_type": "challenge",
  "created_by": "Devil's Advocate",
  "created_at": "2026-02-14T10:28:33.567890",
  "updated_at": "2026-02-14T10:28:33.567890",
  "tags": [],
  "phase": 4,
  "function_name": null,
  "priority": "normal",
  "is_deleted": false,
  "deleted_by": null,
  "deleted_reason": null,
  "target_hypothesis_id": "hyp-3f8a",
  "content": "The causal chain assumes the generator_ internal state pointer is nullptr after timeout (step 1 is marked as assumption), but no runtime evidence confirms this value. The timeout handler in FragmentGenerator::initialize() may set a partial state rather than leaving nullptr, which would cause data corruption rather than a segmentation fault. This alternative mechanism would change the debugging recommendation.",
  "severity": "MEDIUM",
  "requires_response": false,
  "resolved": false,
  "resolution": null,
  "llm_request_id": "req-f6g7"
}
```

---

## 4.5 ConclusionArtifact

### 1. Purpose & Role

The `ConclusionArtifact` is the terminal artifact of the investigation pipeline -- the
final answer. It synthesizes all prior reasoning into an actionable conclusion that
includes the determined root cause, calibrated confidence, investigation outcome,
debugging recommendations, and known limitations.

In the agentic API context, the conclusion is what the client ultimately wants. After
an investigation completes, the client reads the conclusion to understand what the system
found. The `outcome` field provides a quick classification (CONFIDENT, PROBABLE,
UNCERTAIN, CONTRADICTORY, INSUFFICIENT) that the client can use for automated decision
making. The `debugging_steps` field gives the human operator concrete actions to take.

The conclusion carries dual confidence values: `confidence_raw` (the LLM's stated
confidence) and `confidence_calibrated` (adjusted by the calibration system based on
historical accuracy). The gap between these two values indicates how well-calibrated
the system is -- a large gap means the system's confidence claims have historically
been inaccurate.

### 2. Schema

**Base fields** (inherited from `Artifact`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | `generate_id()` | Unique 16-character UUID prefix |
| `artifact_type` | `ArtifactType` | `CONCLUSION` | Fixed type discriminator |
| `created_by` | `str` | -- (required) | Persona name that created this artifact |
| `created_at` | `datetime` | `datetime.now()` | Creation timestamp |
| `updated_at` | `datetime` | `datetime.now()` | Last modification timestamp |
| `tags` | `list[str]` | `[]` | Categorization tags |
| `phase` | `int \| None` | `None` | Investigation phase when created (typically 6) |
| `function_name` | `str \| None` | `None` | Related function for index grouping |
| `priority` | `Priority` | `NORMAL` | Priority level |
| `is_deleted` | `bool` | `False` | Soft-deletion flag |
| `deleted_by` | `str \| None` | `None` | Persona that deleted this artifact |
| `deleted_reason` | `str \| None` | `None` | Reason for deletion |

**ConclusionArtifact-specific fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `root_cause` | `str` | -- (required) | Final root cause determination -- a concise statement of what went wrong |
| `confidence_raw` | `float` | `0.0` | Raw confidence score from the LLM (0.0-1.0) |
| `confidence_calibrated` | `float` | `0.0` | Calibrated confidence adjusted by historical accuracy (0.0-1.0) |
| `outcome` | `str` | `"UNCERTAIN"` | Investigation outcome: `CONFIDENT`, `PROBABLE`, `UNCERTAIN`, `CONTRADICTORY`, `INSUFFICIENT` |
| `code_location` | `str \| None` | `None` | File:line of the error location (e.g., `BoardReader.cpp:142`) |
| `code_snippet` | `str \| None` | `None` | Relevant source code at the error location |
| `data_flow` | `str \| None` | `None` | Data flow description or ASCII diagram showing the call chain |
| `caveats` | `list[str]` | `[]` | Limitations, assumptions, and known gaps in the conclusion |
| `debugging_steps` | `list[str]` | `[]` | Specific, actionable debugging steps for the operator |
| `unresolved_challenges` | `list[str]` | `[]` | Challenge descriptions that were not resolved during adversarial review |
| `llm_request_id` | `str \| None` | `None` | Links to the LLMRequestArtifact that generated this conclusion |

### 3. Producer

**Phase:** 6 (Synthesis)
**Persona:** Synthesizer
**WorkBinder method:** `binder.add_conclusion()`
**Parser:** `ConclusionParser` in `srcs/workbinder/artifacts/parsers/conclusion.py`

The Synthesizer reads all prior artifacts (hypotheses, evidence, causal chains,
challenges) and produces a unified conclusion. The parser converts the LLM's synthesis
response through a two-stage pipeline:

```
LLM JSON  -->  ConclusionItem  -->  InvestigationConclusion  -->  ConclusionArtifact
                  (Pydantic)           (domain model)               (WorkBinder)
```

The `ConclusionItem` from the LLM includes additional nested structures:
- `sub_causes`: Ranked breakdown of contributing causes (`SubCauseItem`)
- `key_files`: Important source files to examine (`KeyFileItem`)

These are flattened or incorporated into the domain model and artifact. The
`confidence` from the LLM becomes `confidence_raw`, and the calibration system
provides `confidence_calibrated`.

The `outcome` is determined by the Judge (Phase 5) based on a decision tree:

| Outcome | Criteria |
|---------|----------|
| `CONFIDENT` | Score > 0.7, 2+ strong evidence, all HIGH challenges resolved |
| `PROBABLE` | Score 0.5-0.7, 1 strong or 3 moderate evidence |
| `UNCERTAIN` | Score 0.3-0.5, multiple viable hypotheses |
| `CONTRADICTORY` | Contradicting evidence >= supporting evidence |
| `INSUFFICIENT` | Score < 0.3, inadequate evidence |

**Singleton behavior:** There is exactly one `ConclusionArtifact` per investigation.
The `binder.get_conclusion()` convenience method returns the single conclusion or `None`.

### 4. Consumers

The `ConclusionArtifact` is the final output of the investigation pipeline. It is not
consumed by any downstream investigation phase -- it is consumed by the client (CLI,
API, Slack, MCP) and, optionally, by the Learner (Phase 7) for pattern extraction.

| Consumer | What They Read | How They Use It |
|----------|----------------|-----------------|
| CLI | `root_cause`, `outcome`, `confidence_calibrated`, `debugging_steps`, `caveats` | Displays the investigation report to the terminal operator |
| REST API | All fields | Returns as part of the investigation response body |
| Slack Bot | `root_cause`, `outcome`, `debugging_steps` | Posts a formatted investigation summary to the Slack channel |
| MCP Client | All fields | Presents the conclusion to the LLM client for further reasoning |
| Learner (Phase 7) | `root_cause`, `outcome`, `confidence_raw`, `confidence_calibrated` | Extracts patterns for future investigations and updates calibration |

### 5. REST API Exposure

The conclusion is accessible through the generic binder artifact endpoints. There is no
dedicated `/conclusion` endpoint -- use the generic artifact query filtered by type.

**Primary endpoint:** `GET /api/v1/binders/{binder_id}/artifacts?artifact_type=conclusion`

**Single artifact:** `GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}`

**Response snippet:**

```json
{
  "artifacts": [
    {
      "id": "con-8h9i",
      "artifact_type": "conclusion",
      "created_by": "Synthesizer",
      "created_at": "2026-02-14T10:32:15.678901",
      "updated_at": "2026-02-14T10:32:15.678901",
      "phase": 6,
      "function_name": null,
      "priority": "normal",
      "tags": [],
      "is_deleted": false,
      "content": {
        "root_cause": "Fragment generator initialization timeout due to FPGA warm-up delay causes null pointer dereference in BoardReader::processFragment() at line 142",
        "confidence_raw": 0.78,
        "confidence_calibrated": 0.72,
        "outcome": "PROBABLE",
        "code_location": "BoardReader.cpp:142",
        "code_snippet": "void BoardReader::processFragment() {\n  auto fragment = generator_->getFragment(); // line 142\n  ...\n}",
        "data_flow": "FPGA -> FragmentGenerator::initialize() [TIMEOUT] -> generator_.readout_buffer_ = nullptr -> BoardReader::processFragment() -> generator_->getFragment() -> readout_buffer_->data() [SEGFAULT]",
        "caveats": [
          "No runtime log confirms the generator_ internal state pointer value after timeout",
          "Race condition alternative not fully ruled out",
          "Timeout threshold (3000ms) may vary by hardware revision"
        ],
        "debugging_steps": [
          "Add null check in BoardReader::processFragment() before calling generator_->getFragment()",
          "Add diagnostic logging in FragmentGenerator::initialize() to log final state after timeout",
          "Increase initialization timeout threshold from 3000ms to 5000ms for FPGA v2+ boards",
          "Verify FPGA warm-up timing with hardware team for this specific board revision"
        ],
        "unresolved_challenges": [
          "The causal chain assumes the generator_ internal state pointer is nullptr after timeout, but no runtime evidence confirms this"
        ],
        "llm_request_id": "req-g7h8"
      }
    }
  ],
  "total": 1
}
```

The conclusion is also returned as part of the `GET /api/v1/investigations/{id}`
response, where it is incorporated into the full investigation detail object.

### 6. MCP Tool Access

The conclusion is accessible through the generic MCP artifact tools. There is no
dedicated `get_conclusion` MCP tool -- use the generic search or artifact retrieval:

- `search_artifacts` with `artifact_type="conclusion"` and the relevant `binder_id`
- `get_artifact` with the specific `binder_id` and `artifact_id`

**Typical MCP usage pattern:**

```
1. get_binder_summary(investigation_id)  -->  get binder_id, check outcome
2. search_artifacts(binder_id, artifact_type="conclusion")  -->  get conclusion
3. get_hypotheses(binder_id)  -->  see ranked hypotheses
4. get_challenges(binder_id, resolved=false)  -->  see unresolved issues
```

### 7. Artifact Relationships

```
+------------------+    +------------------+    +------------------+
| HypothesisArtifact|    | EvidenceArtifact |    | CausalChainArtifact|
| (ranked causes)  |    | (key evidence)   |    | (reasoning path) |
+--------+---------+    +--------+---------+    +--------+---------+
         |                       |                       |
         +----------- synthesized from ---------+-------+
                                                |
                                                v
+------------------+              +------------------+
| ChallengeArtifact|  unresolved  | ConclusionArtifact|
| (quality checks) |  challenges  | (final answer)   |
+------------------+  ----------> +------------------+
                                          |
                                          | llm_request_id
                                          v
                                  +------------------+
                                  | LLMRequestArtifact|
                                  | (synthesis call) |
                                  +------------------+
```

**Key relationships:**

- **ConclusionArtifact <- HypothesisArtifact, EvidenceArtifact, CausalChainArtifact**:
  The conclusion synthesizes information from all prior investigation artifacts. These
  are not formal ID references -- the Synthesizer reads them from the binder and
  incorporates their content into the conclusion text.
- **ConclusionArtifact <- ChallengeArtifact**: Unresolved challenges are listed in
  `unresolved_challenges` as description strings (not IDs).
- **ConclusionArtifact -> LLMRequestArtifact**: Traces which LLM call generated the
  conclusion via `llm_request_id`.

### 8. Session State Mapping

The conclusion is the final artifact created during an investigation. It appears once
and is not modified. Key observations for the client:

1. **Terminal artifact:** The conclusion marks the end of the investigation's reasoning
   pipeline. If a conclusion exists, the investigation is functionally complete
   (Phase 7 learning may still run afterward).
2. **Outcome as signal:** The `outcome` field is the single most important signal for
   automated decision making:
   - `CONFIDENT` -- the system believes it found the root cause
   - `PROBABLE` -- likely correct but with gaps
   - `UNCERTAIN` -- multiple explanations remain
   - `CONTRADICTORY` -- evidence points in different directions
   - `INSUFFICIENT` -- not enough data to draw conclusions
3. **Calibration gap:** Compare `confidence_raw` and `confidence_calibrated`. A large
   difference (e.g., raw=0.85, calibrated=0.60) indicates the system has historically
   overstated its confidence. Trust the calibrated value.
4. **Debugging steps are actionable:** The `debugging_steps` list contains concrete
   actions the operator can take, not abstract suggestions. These are the primary
   value delivered to the end user.
5. **Caveats and unresolved challenges:** Together, these fields describe everything
   the investigation could not determine. They should be presented prominently alongside
   the root cause to avoid overconfidence.

### 9. Example

```json
{
  "id": "con-8h9i",
  "artifact_type": "conclusion",
  "created_by": "Synthesizer",
  "created_at": "2026-02-14T10:32:15.678901",
  "updated_at": "2026-02-14T10:32:15.678901",
  "tags": [],
  "phase": 6,
  "function_name": null,
  "priority": "normal",
  "is_deleted": false,
  "deleted_by": null,
  "deleted_reason": null,
  "root_cause": "Fragment generator initialization timeout due to FPGA warm-up delay causes null pointer dereference in BoardReader::processFragment() at line 142. The FPGA board requires ~3.5 seconds of warm-up, but the initialization timeout is set to 3 seconds. When the timeout fires, the generator object exists but its internal readout buffer pointer remains nullptr. The subsequent call to processFragment() dereferences this null pointer, causing a segmentation fault.",
  "confidence_raw": 0.78,
  "confidence_calibrated": 0.72,
  "outcome": "PROBABLE",
  "code_location": "BoardReader.cpp:142",
  "code_snippet": "void BoardReader::processFragment() {\n  auto fragment = generator_->getFragment();  // line 142 - no null check\n  if (fragment.size() > 0) {\n    processData(fragment);\n  }\n}",
  "data_flow": "FPGA hardware -> FragmentGenerator::initialize() [3.5s, TIMEOUT at 3.0s] -> generator_.readout_buffer_ = nullptr -> BoardReader::processFragment() -> generator_->getFragment() -> readout_buffer_->data() [SEGFAULT]",
  "caveats": [
    "No runtime log confirms the internal readout_buffer_ pointer value after initialization timeout",
    "Race condition between EventBuilder thread and BoardReader thread not fully ruled out as contributing factor",
    "The 3-second timeout threshold may be hardware-revision dependent -- this analysis assumes FPGA v2 timing"
  ],
  "debugging_steps": [
    "Add null check in BoardReader::processFragment() before generator_->getFragment() call: if (!generator_ || !generator_->isReady()) { LOG_ERROR(...); return; }",
    "Add diagnostic logging to FragmentGenerator::initialize() final state: LOG_INFO('initialize() completed: ready=%d, buffer=%p', is_ready_, readout_buffer_)",
    "Increase FPGA initialization timeout from 3000ms to 5000ms in BoardReader configuration for v2+ boards",
    "Contact hardware team to confirm FPGA warm-up timing for board revision used in this run",
    "Review EventBuilder thread synchronization with BoardReader to rule out race condition"
  ],
  "unresolved_challenges": [
    "The causal chain assumes generator_ internal state pointer is nullptr after timeout (step 1), but no runtime evidence confirms this value"
  ],
  "llm_request_id": "req-g7h8"
}
```

---

## Cross-Artifact Relationship Summary

The following diagram shows all five investigation artifacts and their relationships:

```
Phase 1                   Phase 2                    Phase 3
Theorist                  Detective                  Logician
    |                         |                          |
    v                         v                          v
+------------------+    +------------------+    +------------------+
| HypothesisArtifact|<-->| EvidenceArtifact |    | CausalChainArtifact|
|                  |    |                  |    |                  |
| description      |    | content          |    | steps[]          |
| score            |    | strength         |    |  .claim          |
| supporting_      |    | found            |    |  .mechanism      |
|  evidence_ids[]  |    | supports_        |    |  .evidence_ids[] |-----> EvidenceArtifact
| contradicting_   |    |  hypothesis_ids[]|    |  .is_assumption  |
|  evidence_ids[]  |    | contradicts_     |    |                  |
| category         |    |  hypothesis_ids[]|    | hypothesis_id ---+-----> HypothesisArtifact
| confirming_      |    | targets_         |    | evidence_coverage|
|  evidence        |    |  hypothesis_id --+--->| logical_validity |
| refuting_        |    | expected_if_true |    +------------------+
|  evidence        |    | expected_if_false|
+--------+---------+    +------------------+
         |
         |  target_hypothesis_id
         |
         v
Phase 4                                          Phase 6
Devil's Advocate                                          Synthesizer
    |                                                |
    v                                                v
+------------------+                          +------------------+
| ChallengeArtifact|    unresolved_challenges | ConclusionArtifact|
|                  | -----------------------> |                  |
| content          |                          | root_cause       |
| severity         |                          | confidence_raw   |
| requires_response|                          | confidence_cal.  |
| resolved         |                          | outcome          |
| resolution       |                          | debugging_steps[]|
| target_hypothesis|                          | caveats[]        |
|  _id ------------+----> HypothesisArtifact  | code_location    |
+------------------+                          | code_snippet     |
                                              | data_flow        |
                                              +------------------+
```

**Read order for a client reviewing an investigation:**

1. Read the `ConclusionArtifact` for the summary, outcome, and debugging steps
2. Read `HypothesisArtifact` list (sorted by rank) for the ranked causes
3. Read `EvidenceArtifact` items linked to the top hypothesis for supporting data
4. Read the `CausalChainArtifact` for the top hypothesis for the reasoning path
5. Read `ChallengeArtifact` items (unresolved) for known limitations

---

## Permissions Matrix (Investigation Artifacts)

| Artifact | Phase 0: Archivist | Phase 1: Theorist | Phase 2: Detective | Phase 3: Logician | Phase 4: Devil's Advocate | Phase 5: Judge | Phase 6: Synthesizer |
|----------|-------------------|-------------------|-------------------|-------------------|--------------------------|----------------|---------------------|
| HypothesisArtifact | -- | **W** | R | R | R | R | R |
| EvidenceArtifact | -- | -- | **RW** | R | R | R | R |
| CausalChainArtifact | -- | -- | -- | **W** | R | R | R |
| ChallengeArtifact | -- | -- | -- | -- | **W** | R | R |
| ConclusionArtifact | -- | -- | -- | -- | -- | -- | **W** |

**Legend:** W = Write, R = Read, RW = Read+Write, -- = No access

---

## WorkBinder Convenience Methods Reference

| Method | Artifact Type | Used By | Description |
|--------|---------------|---------|-------------|
| `add_hypothesis()` | HypothesisArtifact | Theorist | Create a new hypothesis |
| `get_hypotheses()` | HypothesisArtifact | Detective, Logician, Devil's Advocate, Synthesizer | Get all hypotheses sorted by rank |
| `add_evidence()` | EvidenceArtifact | Detective | Create a new evidence item |
| `get_evidence_items()` | EvidenceArtifact | Detective, Logician, Devil's Advocate, Synthesizer | Get all evidence items |
| `link_evidence_to_hypothesis()` | Both | Detective | Bidirectionally link evidence to hypothesis (supports or contradicts) |
| `add_causal_chain()` | CausalChainArtifact | Logician | Create a new causal chain (validates hypothesis reference) |
| `get_causal_chains()` | CausalChainArtifact | Devil's Advocate, Synthesizer | Get all causal chains |
| `add_challenge()` | ChallengeArtifact | Devil's Advocate | Create a new challenge (validates hypothesis reference) |
| `get_challenges()` | ChallengeArtifact | Synthesizer | Get all challenges |
| `add_conclusion()` | ConclusionArtifact | Synthesizer | Create the investigation conclusion |
| `get_conclusion()` | ConclusionArtifact | Client, Learner | Get the single conclusion (or None) |

---

> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 3: Code Knowledge Artifacts](agentic-workbinder-library-ch3-code-artifacts.md) | [Ch. 5: Observation Artifacts](agentic-workbinder-library-ch5-observation-artifacts.md)
