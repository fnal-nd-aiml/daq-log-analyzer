> **Agentic WorkBinder Library** | [Table of Contents](agentic-workbinder-library.md) | [Ch. 7 Tools, Serialization & Parsing](agentic-workbinder-library-ch7-tools-serialization.md)

---

# Chapter 8: API Integration & Testing

The WorkBinder is the authoritative store for all investigation artifacts. Two external interfaces expose it: the **FastAPI REST API** (for web clients and the agentic REST service) and the **MCP Server** (for Claude Desktop, VS Code, and other MCP-compatible clients). This chapter documents every endpoint and tool, maps session state to binder state, provides cross-references to companion design documents, and defines the testing strategy.

---

## 8.1 REST API Endpoints

**Source:** `srcs/api/routes/binders.py` (1619 lines)

All binder endpoints are registered under the `/api/v1/` prefix via a FastAPI `APIRouter`. The router is mounted at the application level in `srcs/api/app.py`. Every endpoint is read-only -- there are no mutation endpoints in the REST API for binders.

### 8.1.1 Dependency Injection

```python
def get_binder_store(
    settings: Annotated[Settings, Depends(get_settings)]
) -> BinderStore:
    """Get binder store instance."""
    data_dir = Path(settings.data_dir)
    return BinderStore(data_dir / "knowledge.db")
```

The `BinderStore` is instantiated per-request from the application settings. The database path is `{ARTDAQ_DATA_DIR}/knowledge.db`.

### 8.1.2 Response Models

The API defines Pydantic response models for type-safe serialization:

| Model | Fields | Used By |
|-------|--------|---------|
| `BinderSummaryResponse` | `binder_id`, `investigation_id`, `status`, `created_at`, `updated_at`, `artifact_count` | List binders |
| `BinderDetailResponse` | `id`, `investigation_id`, `status`, `created_at`, `updated_at`, `artifact_counts` | Get binder detail |
| `BinderInvestigationSummaryResponse` | All detail fields plus `current_phase`, `outcome`, `resume_count` | Get binder summary |
| `ArtifactResponse` | `id`, `artifact_type`, `created_by`, `created_at`, `updated_at`, `phase`, `function_name`, `priority`, `tags`, `is_deleted`, `content` | All artifact endpoints |
| `ArtifactHistoryEntryResponse` | `id`, `artifact_id`, `modified_by`, `modified_at`, `action`, `changes` | Artifact history |
| `AuditLogEntryResponse` | `id`, `persona_name`, `phase_number`, `timestamp`, `access_sequence`, `operation_type`, `artifact_type`, `artifact_id`, `method_name`, `result_count`, `success` | Audit log |
| `AuditSummaryResponse` | `total_entries`, `by_persona`, `by_phase`, `by_operation` | Audit summary |
| `LLMExchangeResponse` | `request: ArtifactResponse`, `response: ArtifactResponse \| None` | LLM exchanges |
| `LLMStatisticsResponse` | `total_requests`, `total_responses`, `total_tokens_used`, `total_latency_ms`, `average_latency_ms`, `by_persona`, `by_phase`, `parse_successes`, `parse_failures` | LLM statistics |
| `InvestigationStateResponse` | `artifact: ArtifactResponse` | Investigation state |
| `ValidationResponse` | `binder_id`, `valid`, `errors` | Reference validation |
| `InvestigationWithStateResponse` | `binder_id`, `investigation_id`, `binder_status`, `created_at`, `updated_at`, `current_phase`, `investigation_status`, `outcome` | Investigation listing |
| `ResumableInvestigationResponse` | `binder_id`, `investigation_id`, `created_at`, `updated_at`, `status` | Resumable investigations |

### 8.1.3 Cross-Binder Discovery Endpoints

These endpoints are declared before the `/{binder_id}` routes to prevent FastAPI from matching literal strings like "resumable" as binder IDs.

---

#### List Resumable Investigations

```
GET /api/v1/binders/resumable
```

Returns paused investigations that support continuation.

| Parameter | In | Type | Description |
|-----------|----|------|-------------|
| (none) | | | |

**Response:** `list[ResumableInvestigationResponse]`

```json
[
  {
    "binder_id": "bdr-abc123",
    "investigation_id": "inv-456",
    "created_at": "2026-02-14T10:00:00",
    "updated_at": "2026-02-14T10:30:00",
    "status": "paused"
  }
]
```

---

#### List Investigations with State

```
GET /api/v1/binders/investigations
```

Returns investigation summaries including current phase, status, and outcome.

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `outcome` | query | `str \| None` | `None` | Filter: CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT |
| `status` | query | `str \| None` | `None` | Filter: active, paused, archived |
| `limit` | query | `int` | `50` | Max results (1-500) |

**Response:** `list[InvestigationWithStateResponse]`

---

#### Find Similar Investigations

```
POST /api/v1/binders/similar
```

Searches across all binders for matching error signatures.

**Request Body:** `SimilarInvestigationRequest`

```json
{
  "error_function": "processData",
  "error_message_pattern": "timeout waiting",
  "limit": 10
}
```

**Response:** `list[dict]` with `binder_id`, `investigation_id`, `match_score`, `created_at`.

The match scoring algorithm awards 0.5 for exact function match (0.25 for substring match) and 0.5 for message pattern substring match, producing a 0.0-1.0 composite score.

### 8.1.4 Binder CRUD Endpoints

---

#### List Binders

```
GET /api/v1/binders
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `status` | query | `str \| None` | `None` | Filter by status |
| `limit` | query | `int` | `50` | Max results (1-500) |

**Response:** `BinderListResponse`

```json
{
  "binders": [
    {
      "binder_id": "bdr-abc123",
      "investigation_id": "inv-456",
      "status": "active",
      "created_at": "2026-02-14T10:00:00",
      "updated_at": "2026-02-14T10:30:00",
      "artifact_count": null
    }
  ],
  "total": 1
}
```

---

#### Get Binder Detail

```
GET /api/v1/binders/{binder_id}
```

Returns binder metadata with artifact counts by type.

**Response:** `BinderDetailResponse`

```json
{
  "id": "bdr-abc123",
  "investigation_id": "inv-456",
  "status": "active",
  "created_at": "2026-02-14T10:00:00",
  "updated_at": "2026-02-14T10:30:00",
  "artifact_counts": {
    "call_graph": 3,
    "finding": 12,
    "hypothesis_artifact": 5,
    "evidence_artifact": 8,
    "llm_request": 7,
    "llm_response": 7
  }
}
```

**Error:** 404 if binder not found.

---

#### Get Binder Summary

```
GET /api/v1/binders/{binder_id}/summary
```

Returns comprehensive investigation summary including state.

**Response:** `BinderInvestigationSummaryResponse`

```json
{
  "binder_id": "bdr-abc123",
  "investigation_id": "inv-456",
  "status": "completed",
  "current_phase": 7,
  "outcome": "CONFIDENT",
  "resume_count": 0,
  "artifact_counts": { "...": "..." },
  "created_at": "2026-02-14T10:00:00",
  "updated_at": "2026-02-14T10:35:00"
}
```

### 8.1.5 Specialized Artifact Query Endpoints

---

#### Get Hypotheses

```
GET /api/v1/binders/{binder_id}/hypotheses
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `min_score` | query | `float \| None` | `None` | Min score (0.0-1.0) |
| `source` | query | `str \| None` | `None` | pattern, similar, fresh, alternative |
| `limit` | query | `int` | `50` | Max results (1-500) |

**Response:** `ArtifactListResponse` with `artifacts` and `total`.

---

#### Get Evidence

```
GET /api/v1/binders/{binder_id}/evidence
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `evidence_type` | query | `str \| None` | `None` | code, log, pattern, etc. |
| `strength` | query | `str \| None` | `None` | STRONG, MODERATE, WEAK |
| `limit` | query | `int` | `100` | Max results (1-500) |

**Response:** `ArtifactListResponse`

---

#### Get Causal Chains

```
GET /api/v1/binders/{binder_id}/chains
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `hypothesis_id` | query | `str \| None` | `None` | Filter by linked hypothesis |
| `limit` | query | `int` | `20` | Max results (1-500) |

**Response:** `ArtifactListResponse`

---

#### Get Challenges

```
GET /api/v1/binders/{binder_id}/challenges
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `resolved` | query | `bool \| None` | `None` | Filter by resolution |
| `severity` | query | `str \| None` | `None` | LOW, MEDIUM, HIGH |
| `limit` | query | `int` | `50` | Max results (1-500) |

**Response:** `ArtifactListResponse`

### 8.1.6 LLM Traceability Endpoints

---

#### Get LLM Requests

```
GET /api/v1/binders/{binder_id}/llm/requests
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `persona` | query | `str \| None` | `None` | Filter by persona name |
| `phase` | query | `int \| None` | `None` | Phase 0-7 |
| `prompt_key` | query | `str \| None` | `None` | e.g., hypothesis_generation |
| `limit` | query | `int` | `100` | Max results (1-500) |

**Response:** `ArtifactListResponse`

---

#### Get LLM Responses

```
GET /api/v1/binders/{binder_id}/llm/responses
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `request_id` | query | `str \| None` | `None` | Filter by request ID |
| `phase` | query | `int \| None` | `None` | Phase 0-7 |
| `parse_success` | query | `bool \| None` | `None` | Filter by parse success |
| `limit` | query | `int` | `100` | Max results (1-500) |

**Response:** `ArtifactListResponse`

---

#### Get LLM Exchanges

```
GET /api/v1/binders/{binder_id}/llm/exchanges
```

Returns paired request/response exchanges. Response may be null if no matching response was recorded.

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `phase` | query | `int \| None` | `None` | Phase 0-7 |

**Response:** `list[LLMExchangeResponse]`

```json
[
  {
    "request": {
      "id": "req-001",
      "artifact_type": "llm_request",
      "content": {
        "persona": "Theorist",
        "prompt_key": "hypothesis_generation",
        "system_prompt": "...",
        "user_prompt": "...",
        "model": "claude-3"
      }
    },
    "response": {
      "id": "resp-001",
      "artifact_type": "llm_response",
      "content": {
        "raw_response": "...",
        "tokens_used": 1500,
        "latency_ms": 2300.5,
        "parse_success": true
      }
    }
  }
]
```

---

#### Get LLM Statistics

```
GET /api/v1/binders/{binder_id}/llm/statistics
```

Returns aggregate LLM usage metrics.

**Response:** `LLMStatisticsResponse`

```json
{
  "total_requests": 7,
  "total_responses": 7,
  "total_tokens_used": 12500,
  "total_latency_ms": 18450.3,
  "average_latency_ms": 2635.8,
  "by_persona": {"Theorist": 1, "Detective": 3, "Logician": 1, "Devil's Advocate": 1, "Synthesizer": 1},
  "by_phase": {"1": 1, "2": 3, "3": 1, "4": 1, "6": 1},
  "parse_successes": 7,
  "parse_failures": 0
}
```

### 8.1.7 Investigation State Endpoints

---

#### Get Investigation State

```
GET /api/v1/binders/{binder_id}/state
```

Returns the `InvestigationStateArtifact` for a binder.

**Response:** `InvestigationStateResponse` (wraps `ArtifactResponse`)

**Error:** 404 if no investigation state artifact exists.

---

#### Get Phase States

```
GET /api/v1/binders/{binder_id}/phases
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `status` | query | `str \| None` | `None` | pending, running, completed, failed |

**Response:** `ArtifactListResponse`

---

#### Validate References

```
GET /api/v1/binders/{binder_id}/validate
```

Validates all inter-artifact references in a binder.

**Response:** `ValidationResponse`

```json
{
  "binder_id": "bdr-abc123",
  "valid": false,
  "errors": [
    "Hypothesis hyp-001: supporting_evidence_ids references non-existent artifact 'ev-999'",
    "CausalChain cc-001: hypothesis_id references non-existent artifact 'hyp-999'"
  ]
}
```

### 8.1.8 Generic Artifact Endpoints

---

#### Search Artifacts (with filters)

```
GET /api/v1/binders/{binder_id}/artifacts
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `artifact_type` | query | `str \| None` | `None` | Filter by type |
| `phase` | query | `int \| None` | `None` | Phase 0-7 |
| `function_name` | query | `str \| None` | `None` | Filter by function |
| `tags` | query | `list[str]` | `[]` | Tags (AND logic) |
| `include_deleted` | query | `bool` | `False` | Include deleted |
| `limit` | query | `int` | `50` | Max results (1-500) |
| `offset` | query | `int` | `0` | Pagination offset |

**Response:** `ArtifactListResponse`

---

#### Get Artifact by ID

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}
```

Returns the full artifact with all content fields.

**Response:** `ArtifactResponse`

**Error:** 404 if artifact not found.

---

#### Get Artifact History

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}/history
```

Returns the chronological modification history.

**Response:** `list[ArtifactHistoryEntryResponse]`

---

#### Full-Text Search

```
POST /api/v1/binders/{binder_id}/artifacts/search
```

**Request Body:** `ArtifactSearchRequest`

```json
{
  "query": "timeout waiting",
  "artifact_types": ["finding", "hypothesis_artifact"]
}
```

**Response:** `ArtifactListResponse` (max 50 results)

---

#### Get Artifact Audit Trail

```
GET /api/v1/binders/{binder_id}/artifacts/{artifact_id}/audit
```

Returns all audit log entries for a specific artifact.

**Response:** `list[AuditLogEntryResponse]`

### 8.1.9 Audit Log Endpoints

---

#### Search Audit Log

```
GET /api/v1/binders/{binder_id}/audit
```

| Parameter | In | Type | Default | Description |
|-----------|----|------|---------|-------------|
| `persona_name` | query | `str \| None` | `None` | Filter by persona |
| `phase_number` | query | `int \| None` | `None` | Phase 0-7 |
| `operation_type` | query | `str \| None` | `None` | "store" or "retrieve" |
| `limit` | query | `int` | `100` | Max entries (1-1000) |

**Response:** `list[AuditLogEntryResponse]`

---

#### Get Audit Summary

```
GET /api/v1/binders/{binder_id}/audit/summary
```

Returns aggregated audit statistics.

**Response:** `AuditSummaryResponse`

```json
{
  "total_entries": 142,
  "by_persona": {"Archivist": 35, "Theorist": 22, "Detective": 45, "Logician": 18, "Devil's Advocate": 12, "Synthesizer": 10},
  "by_phase": {"0": 35, "1": 22, "2": 45, "3": 18, "4": 12, "6": 10},
  "by_operation": {"store": 87, "retrieve": 55}
}
```

### 8.1.10 Helper: `_artifact_to_response()`

All endpoints use a shared helper to convert Pydantic artifact models to `ArtifactResponse`:

```python
def _artifact_to_response(artifact: Any) -> ArtifactResponse:
```

This function separates common fields (`id`, `artifact_type`, `created_by`, etc.) from type-specific content. The content is produced by `model_dump(exclude=common_fields, mode="json")`, ensuring all nested datetime and enum values are serializable.

### 8.1.11 Endpoint Summary Table

| Method | Path | Description |
|--------|------|-------------|
| GET | `/binders` | List binders |
| GET | `/binders/resumable` | List resumable investigations |
| GET | `/binders/investigations` | List investigations with state |
| POST | `/binders/similar` | Find similar investigations |
| GET | `/binders/{id}` | Get binder detail |
| GET | `/binders/{id}/summary` | Get investigation summary |
| GET | `/binders/{id}/state` | Get investigation state |
| GET | `/binders/{id}/phases` | Get phase states |
| GET | `/binders/{id}/validate` | Validate references |
| GET | `/binders/{id}/hypotheses` | Get hypotheses |
| GET | `/binders/{id}/evidence` | Get evidence |
| GET | `/binders/{id}/chains` | Get causal chains |
| GET | `/binders/{id}/challenges` | Get challenges |
| GET | `/binders/{id}/llm/requests` | Get LLM requests |
| GET | `/binders/{id}/llm/responses` | Get LLM responses |
| GET | `/binders/{id}/llm/exchanges` | Get LLM exchanges |
| GET | `/binders/{id}/llm/statistics` | Get LLM statistics |
| GET | `/binders/{id}/artifacts` | Search artifacts |
| GET | `/binders/{id}/artifacts/{art_id}` | Get artifact |
| GET | `/binders/{id}/artifacts/{art_id}/history` | Get history |
| GET | `/binders/{id}/artifacts/{art_id}/audit` | Get artifact audit trail |
| POST | `/binders/{id}/artifacts/search` | Full-text search |
| GET | `/binders/{id}/audit` | Search audit log |
| GET | `/binders/{id}/audit/summary` | Get audit summary |

---

## 8.2 MCP Server Tools

**Source:** `srcs/mcp/server.py` (3360 lines)

The MCP server exposes 53 tools via the FastMCP framework. Tools related to binder/artifact access are organized below by category. All binder data tools are read-only; command tools (investigate, feedback, ask) may write to the database.

### 8.2.1 Binder Management Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `list_binders` | `status?: str`, `limit?: int=50` | JSON array of binder summaries | List available workbinders |
| `get_binder` | `binder_id: str` | JSON object with metadata + artifact_counts | Get binder detail |
| `get_binder_summary` | `investigation_id: str` | JSON summary with status, phase, outcome, counts | Get investigation summary |
| `list_resumable_investigations` | (none) | JSON array of paused investigations | List resumable investigations |
| `validate_binder` | `binder_id: str` | JSON with valid boolean and errors | Validate artifact references |

### 8.2.2 Artifact Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `search_artifacts` | `binder_id: str`, `artifact_type?: str`, `phase?: int`, `function_name?: str`, `tags?: str` (comma-sep), `include_deleted?: bool=False`, `limit?: int=100`, `offset?: int=0` | JSON array of full artifacts | Filter and search artifacts |
| `get_artifact` | `binder_id: str`, `artifact_id: str` | JSON artifact object | Get single artifact |
| `get_artifact_history` | `binder_id: str`, `artifact_id: str` | JSON array of history entries | Get modification history |
| `search_artifact_content` | `binder_id: str`, `query: str`, `artifact_types?: str` (comma-sep) | JSON array of matching artifacts | Full-text content search |

**Note on tag format:** MCP tools accept tags as a comma-separated string (e.g., `"error-path,timing"`) rather than a JSON array, since MCP tool parameters are simpler types.

### 8.2.3 Specialized Artifact Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `get_hypotheses` | `binder_id: str`, `min_score?: float`, `source?: str`, `limit?: int=50` | JSON array of hypothesis artifacts | Hypothesis query |
| `get_evidence` | `binder_id: str`, `evidence_type?: str`, `strength?: str`, `limit?: int=100` | JSON array of evidence artifacts | Evidence query |
| `get_causal_chains` | `binder_id: str`, `hypothesis_id?: str`, `limit?: int=20` | JSON array of chain artifacts | Causal chain query |
| `get_challenges` | `binder_id: str`, `resolved?: bool`, `severity?: str`, `limit?: int=50` | JSON array of challenge artifacts | Challenge query |

### 8.2.4 LLM Traceability Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `get_llm_requests` | `binder_id: str`, `persona?: str`, `phase?: int`, `prompt_key?: str`, `limit?: int=100` | JSON array of request artifacts | LLM request query |
| `get_llm_responses` | `binder_id: str`, `request_id?: str`, `phase?: int`, `parse_success?: bool`, `limit?: int=100` | JSON array of response artifacts | LLM response query |
| `get_llm_exchanges` | `binder_id: str`, `phase?: int` | JSON array of {request, response} pairs | Paired exchanges |
| `get_llm_statistics` | `binder_id: str` | JSON statistics object | Aggregate LLM metrics |

### 8.2.5 Investigation State Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `get_investigation_state` | `binder_id: str` | JSON state artifact | Investigation state |
| `get_phase_states` | `binder_id: str`, `status?: str` | JSON array of phase states | Phase lifecycle |
| `list_investigations_with_state` | `outcome?: str`, `status?: str`, `limit?: int=50` | JSON array of summaries | Investigation listing |
| `find_similar_investigations` | `error_function?: str`, `error_message_pattern?: str`, `limit?: int=10` | JSON array with match scores | Similarity search |

### 8.2.6 Audit Log Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `search_audit_log` | `binder_id: str`, `persona_name?: str`, `phase_number?: int`, `operation_type?: str`, `limit?: int=100` | JSON array of audit entries | Audit search |
| `get_artifact_audit_trail` | `binder_id: str`, `artifact_id: str` | JSON array of audit entries | Per-artifact audit |
| `get_audit_summary` | `binder_id: str` | JSON with by_persona, by_phase, by_operation | Audit statistics |

### 8.2.7 Command Tools

These tools invoke the investigation pipeline or knowledge base and may create or modify data.

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `investigate_error` | `error_message: str`, `log_content?: str`, `error_line?: int`, `context_lines?: int=60`, `additional_files?: str` (JSON) | JSON investigation result | Run 7-phase investigation |
| `analyze_message` | `message: str` | JSON investigation result | Lightweight investigation |
| `submit_feedback` | `investigation_id: str`, `correct: bool`, `actual_cause?: str`, `corrected_summary?: str`, `feedback_source?: str="mcp"` | JSON with success, patterns_updated | Submit feedback |
| `ask_experts` | `question: str`, `log_content?: str` | JSON with answer, confidence, key_points | Expert panel Q&A |

**Progress Reporting:** Command tools use `ctx.report_progress(progress, total)` and `ctx.info()` for phase-by-phase progress updates via MCP Context.

### 8.2.8 Pattern and Calibration Tools

| Tool | Parameters | Return | Description |
|------|-----------|--------|-------------|
| `list_patterns` | `active_only?: bool=True`, `min_confidence?: float`, `min_times_seen?: int`, `limit?: int=50`, `offset?: int=0` | JSON with patterns and total | List error patterns |
| `get_pattern` | `pattern_id: str` | JSON pattern with root causes | Pattern detail |
| `get_pattern_statistics` | (none) | JSON aggregate stats | Pattern statistics |
| `get_pattern_root_causes` | `pattern_id: str` | JSON array of root causes | Pattern root causes |
| `match_pattern` | `message_pattern: str`, `function?: str`, `level?: str="ERROR"`, `component?: str` | JSON matching pattern | Find matching pattern |
| `get_pattern_accuracy_trend` | `pattern_id: str`, `limit?: int=30` | JSON trend data | Accuracy over time |
| `list_calibrations` | `limit?: int=50` | JSON array of calibrations | List calibrations |
| `get_calibration` | `model: str`, `error_type?: str` | JSON calibration data | Model calibration |
| `get_calibration_trend` | `model?: str="default"`, `error_type?: str`, `limit?: int=30` | JSON trend with chart | Calibration trend |
| `record_calibration_snapshot` | `model?: str="default"`, `error_type?: str` | JSON confirmation | Record snapshot |
| `get_calibration_summary` | (none) | JSON cross-model summary | Summary |
| `export_calibration` | `model?: str="default"`, `error_type?: str` | JSON export data | Export calibration |

### 8.2.9 REST API vs MCP Tool Mapping

| Operation | REST Endpoint | MCP Tool |
|-----------|--------------|----------|
| List binders | `GET /binders` | `list_binders` |
| Get binder | `GET /binders/{id}` | `get_binder` |
| Get summary | `GET /binders/{id}/summary` | `get_binder_summary` |
| Search artifacts | `GET /binders/{id}/artifacts` | `search_artifacts` |
| Get artifact | `GET /binders/{id}/artifacts/{art_id}` | `get_artifact` |
| Artifact history | `GET /binders/{id}/artifacts/{art_id}/history` | `get_artifact_history` |
| Full-text search | `POST /binders/{id}/artifacts/search` | `search_artifact_content` |
| Get hypotheses | `GET /binders/{id}/hypotheses` | `get_hypotheses` |
| Get evidence | `GET /binders/{id}/evidence` | `get_evidence` |
| Get chains | `GET /binders/{id}/chains` | `get_causal_chains` |
| Get challenges | `GET /binders/{id}/challenges` | `get_challenges` |
| LLM requests | `GET /binders/{id}/llm/requests` | `get_llm_requests` |
| LLM responses | `GET /binders/{id}/llm/responses` | `get_llm_responses` |
| LLM exchanges | `GET /binders/{id}/llm/exchanges` | `get_llm_exchanges` |
| LLM statistics | `GET /binders/{id}/llm/statistics` | `get_llm_statistics` |
| Investigation state | `GET /binders/{id}/state` | `get_investigation_state` |
| Phase states | `GET /binders/{id}/phases` | `get_phase_states` |
| Validate references | `GET /binders/{id}/validate` | `validate_binder` |
| Resumable | `GET /binders/resumable` | `list_resumable_investigations` |
| Investigations list | `GET /binders/investigations` | `list_investigations_with_state` |
| Similar | `POST /binders/similar` | `find_similar_investigations` |
| Audit log | `GET /binders/{id}/audit` | `search_audit_log` |
| Audit summary | `GET /binders/{id}/audit/summary` | `get_audit_summary` |
| Artifact audit | `GET /binders/{id}/artifacts/{art_id}/audit` | `get_artifact_audit_trail` |

Both interfaces access the same `BinderStore` and `knowledge.db` database, ensuring data consistency.

---

## 8.3 Session State Mapping

### 8.3.1 WorkBinder as Session State

The WorkBinder serves as the persistent session state for each investigation. The relationship is:

```
1 Investigation : 1 WorkBinder : 1 binder_id
```

The `investigation_id` is the primary lookup key. The binder's `status` field maps to the investigation lifecycle:

| Binder Status | Meaning | Phase Range |
|---------------|---------|-------------|
| `active` | Investigation in progress | Any phase |
| `paused` | Investigation suspended | Resumes at last completed + 1 |
| `completed` | Investigation finished | Phase 7 completed |
| `archived` | Soft-deleted | N/A |

### 8.3.2 Client View at Each Pipeline Phase

| Phase | Artifacts Created | Client-Visible State |
|-------|-------------------|---------------------|
| -1 (Multi-File Triage) | `LogBundleArtifact` | Merged timeline, primary error identified |
| 0 (Prior Retrieval) | `ErrorContextArtifact`, `SourceLocationArtifact`, `CallGraphNode`, `CodeSnippet`, `FunctionSummaryArtifact`, `FlowConfigArtifact`, `InvestigationStateArtifact`, `PhaseStateArtifact` | Error context, source locations, call graphs |
| 1 (Hypothesis Generation) | `HypothesisArtifact`, `LLMRequestArtifact`, `LLMResponseArtifact`, `PhaseStateArtifact` | Ranked hypothesis list |
| 2 (Evidence Seeking) | `EvidenceArtifact`, `LLMRequestArtifact`, `LLMResponseArtifact`, `PhaseStateArtifact` | Evidence items linked to hypotheses |
| 3 (Causal Chain) | `CausalChainArtifact`, `LLMRequestArtifact`, `LLMResponseArtifact`, `PhaseStateArtifact` | Causal chains for top hypotheses |
| 4 (Adversarial Review) | `ChallengeArtifact`, `LLMRequestArtifact`, `LLMResponseArtifact`, `PhaseStateArtifact` | Challenges to conclusions |
| 5-6 (Insufficiency + Synthesis) | `ConclusionArtifact`, `LLMRequestArtifact`, `LLMResponseArtifact`, `PhaseStateArtifact` | Final conclusion with outcome |
| 7 (Learning) | `PersonaContributionArtifact`, `PhaseStateArtifact` | Patterns extracted |

### 8.3.3 SSE Event Correlation

When the REST API streams investigation progress via Server-Sent Events, each event corresponds to a phase transition in the WorkBinder:

| SSE Event | WorkBinder Operation |
|-----------|---------------------|
| `phase_start` | `binder.start_phase(N, persona_name)` -- creates PhaseStateArtifact with status "in_progress" |
| `phase_progress` | Artifacts being added during phase execution |
| `phase_complete` | `binder.complete_phase(N, output_ids)` -- updates PhaseStateArtifact status to "completed" |
| `phase_error` | `binder.fail_phase(N, error_message)` -- updates PhaseStateArtifact status to "failed" |
| `investigation_complete` | `InvestigationStateArtifact` updated with outcome and `completed_at` |

### 8.3.4 Phase Transition Events

The `InvestigationStateArtifact.current_phase` field is updated as phases progress:

```
Phase 0 started  -> current_phase = 0
Phase 0 complete -> current_phase = 0, phase_state[0].status = "completed"
Phase 1 started  -> current_phase = 1
...
Phase 7 complete -> current_phase = 7, investigation status = "completed"
```

On pause:
```
binder.pause_investigation("reason")
-> investigation_state.status = "paused"
-> investigation_state.paused_at = now
-> investigation_state.pause_reason = "reason"
```

On resume:
```
binder.resume_investigation()
-> investigation_state.status = "active"
-> investigation_state.resume_count += 1
```

---

## 8.4 Cross-References

### 8.4.1 Agentic REST Service Design

| Chapter | Relevance |
|---------|-----------|
| [Ch. 1: Architecture](agentic-rest-service-design-ch1-architecture.md) | Session model and tool dispatch |
| [Ch. 2: Log Analysis Tools](agentic-rest-service-design-ch2-log-analysis-tools.md) | Tools that create log/error artifacts |
| [Ch. 3: Code Analysis Tools](agentic-rest-service-design-ch3-code-analysis-tools.md) | Tools that create call graph and code snippet artifacts |
| [Ch. 4: Knowledge & Finding Tools](agentic-rest-service-design-ch4-knowledge-finding-tools.md) | Pattern and calibration queries |
| [Ch. 5: Pipeline, Expert & Admin Tools](agentic-rest-service-design-ch5-pipeline-admin-tools.md) | Investigation tool that populates the binder |
| [Ch. 6: Client Refactoring](agentic-rest-service-design-ch6-client-refactoring.md) | How clients consume binder state |

### 8.4.2 Agentic Persona Library

| Chapter | Relevance |
|---------|-----------|
| [Ch. 1: Architecture](agentic-persona-library-ch1-architecture.md) | Persona lifecycle and binder interaction model |
| [Ch. 2: Pipeline Personas](agentic-persona-library-ch2-pipeline-personas.md) | Which personas produce which artifact types |
| [Ch. 3: Analysis Personas](agentic-persona-library-ch3-analysis-personas.md) | Detective, Logician, Devil's Advocate artifact production |
| [Ch. 4: Learning Personas](agentic-persona-library-ch4-learning-personas.md) | Pattern extraction from binder contents |
| [Ch. 6: Prompt Architecture](agentic-persona-library-ch6-prompt-architecture.md) | How BinderSerializer output is used in prompts |

### 8.4.3 WorkBinder Library (Earlier Chapters)

| Chapter | Relevance |
|---------|-----------|
| Ch. 1-4 (Architecture, Artifacts, Binder, State) | Core container and artifact types referenced throughout |
| Ch. 5-6 (LLM Tracking, State Management) | State artifacts that drive the session mapping |
| [Ch. 7: Tools, Serialization & Parsing](agentic-workbinder-library-ch7-tools-serialization.md) | BinderTools, Serializer, Parser implementations |

---

## 8.5 Testing Strategy

### 8.5.1 Unit Tests for WorkBinder Core

**Source:** `tests/unit/test_workbinder.py`

Tests for the `WorkBinder` container class follow a straightforward create-and-verify pattern:

```python
class TestWorkBinder:
    def test_create_binder(self):
        binder = WorkBinder(investigation_id="test-123")
        assert binder.id is not None
        assert binder.investigation_id == "test-123"
        assert binder.status == "active"
        assert len(binder._artifacts) == 0

    def test_add_call_graph(self):
        binder = WorkBinder(investigation_id="test")
        artifact_id = binder.add_call_graph(
            center_function="processData",
            callers=[{"caller_name": "handleRequest"}],
            callees=[{"callee_name": "validateBuffer"}],
            created_by="Archivist",
            phase=0,
        )
        artifact = binder.get_artifact(artifact_id)
        assert isinstance(artifact, CallGraphNode)
        assert artifact.center_function == "processData"
```

**Coverage targets:**

| Test Area | Test Pattern |
|-----------|-------------|
| Artifact creation | Create each artifact type, verify fields |
| Soft delete / restore | `mark_deleted()` -> verify `is_deleted`, `restore_artifact()` -> verify restored |
| Update with history | `update_artifact()` -> verify changed fields and history record |
| Query by type | Add mixed artifacts, `query(BinderQuery(artifact_type=...))` |
| Query by phase | Add artifacts at different phases, filter |
| Query by function | Add artifacts with function names, filter |
| Query by tags | Add tagged artifacts, verify AND logic |
| Count by type | `count_by_type()` returns correct dict |
| Tag operations | `get_all_tags()`, `get_by_tag()` |

### 8.5.2 Persistence Round-Trip Tests

**Source:** `tests/unit/test_binder_persistence.py`

Tests for `BinderStore` use a temporary SQLite database fixture:

```python
class TestBinderStore:
    @pytest.fixture
    def temp_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)

    @pytest.fixture
    def store(self, temp_db):
        return BinderStore(temp_db)

    @pytest.mark.asyncio
    async def test_save_and_load_binder(self, store):
        binder = WorkBinder(investigation_id="test-123")
        binder.add_finding(
            persona="Theorist",
            finding_type=FindingType.OBSERVATION,
            content="Test finding",
            confidence=0.8,
            phase=1,
        )
        await store.save_binder(binder)
        loaded = await store.load_binder(binder.id)
        assert loaded is not None
        assert loaded.investigation_id == "test-123"
        assert len(loaded._artifacts) == 1
```

**Coverage targets:**

| Test Area | Test Pattern |
|-----------|-------------|
| Save and load | Save binder with artifacts, load by ID, verify all fields |
| Load by investigation | `load_binder_for_investigation()` |
| Nonexistent binder | `load_binder("nonexistent")` returns `None` |
| Direct artifact CRUD | `add_artifact()`, `update_artifact()`, `delete_artifact()`, `restore_artifact()` |
| Query artifacts | `query_artifacts()` with various filter combinations |
| Full-text search | `search_artifacts()` with query strings |
| History tracking | Verify history entries after create, update, delete, restore |
| Audit log persistence | Verify audit log entries survive save/load cycle |
| Resume support | Pause, save, `load_for_resume()`, verify phase and context |
| Reference validation | Add artifacts with valid/invalid references, verify `validate_references()` |
| Binder deletion | Soft delete (archive), hard delete (permanent removal) |
| Artifact count | `get_artifact_count()` by type |

### 8.5.3 API Endpoint Tests

**Source:** `tests/unit/test_api_binders.py`

API tests validate response models and parameter validation:

```python
class TestBinderListEndpoint:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_list_binders_response_model(self):
        summary = BinderSummaryResponse(
            binder_id="binder-123",
            investigation_id="inv-456",
            status="active",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            artifact_count=10,
        )
        assert summary.binder_id == "binder-123"

    def test_list_binders_validation(self, client):
        response = client.get("/api/v1/binders?limit=-1")
        assert response.status_code == 422
```

**Coverage targets:**

| Test Area | Test Pattern |
|-----------|-------------|
| Response model validation | Construct each response model, verify field types |
| Parameter validation | Send invalid parameters (negative limits, out-of-range phases), expect 422 |
| 404 handling | Request nonexistent binder/artifact, expect 404 |
| Endpoint routing | Verify each endpoint returns correct status code with mocked store |
| Pagination | Verify limit/offset behavior |
| Filter combinations | Test each filter parameter individually and in combination |

### 8.5.4 Parser Tests

Parser tests verify the two-stage conversion pattern for each parser:

```python
class TestHypothesisParser:
    def test_parse_llm_response(self):
        raw_json = '{"hypotheses": [{"description": "Test", "category": "timing", "prior": 0.3}]}'
        parser = HypothesisParser()
        response = parser.parse_llm_response(raw_json)
        assert len(response.hypotheses) == 1
        assert response.hypotheses[0].category == "timing"

    def test_to_domain_model(self):
        item = HypothesisItem(description="Test", category="timing", prior=0.5)
        parser = HypothesisParser()
        hypothesis = parser.to_domain_model(item, source_prefix="fresh", max_prior=0.3)
        assert hypothesis.prior == 0.3  # capped
        assert hypothesis.source == "fresh:timing"

    def test_to_artifact(self):
        hypothesis = Hypothesis(description="Test", source="fresh:timing", prior=0.3, score=0.3)
        parser = HypothesisParser()
        artifact = parser.to_artifact(hypothesis, "Theorist", phase=1, rank=0)
        assert isinstance(artifact, HypothesisArtifact)
        assert artifact.created_by == "Theorist"
```

**Coverage targets per parser:**

| Parser | Key Test Cases |
|--------|---------------|
| `HypothesisParser` | Parse valid response, prior capping, category incorporation, deduplication, malformed JSON |
| `EvidenceQueryParser` | Parse query list, to_domain_model produces dict, to_artifact from EvidenceItem |
| `CausalChainParser` | Parse chain steps, evidence->evidence_ids mapping, logical validity/coverage metrics |
| `ChallengeParser` | Parse challenges, type->challenge_type mapping, "missing"->"missing_evidence", severity-based requires_response |
| `ConclusionParser` | Parse conclusion with sub_causes and key_files, calibrated confidence, outcome mapping |

### 8.5.5 JSON Utility Tests

```python
class TestJsonUtils:
    def test_extract_json_from_markdown(self):
        response = '```json\n{"result": "ok"}\n```'
        assert extract_json(response) == '{"result": "ok"}'

    def test_fix_json_trailing_commas(self):
        assert '"items": [1, 2, 3]' in fix_json('{"items": [1, 2, 3,]}')

    def test_fix_json_unquoted_keys(self):
        assert '"name"' in fix_json('{name: "test"}')

    def test_fix_json_single_quotes(self):
        result = fix_json("{'key': 'value'}")
        assert '"key"' in result

    def test_fix_json_truncation_repair(self):
        result = fix_json('{"items": [1, 2')
        assert result.endswith(']}')

    def test_parse_json_response_with_repair(self):
        # Malformed JSON gets extracted and repaired
        class Result(BaseModel):
            items: list[str]
        result = parse_json_response(
            "Here: ```json\n{'items': ['a', 'b',]}\n```",
            Result
        )
        assert result.items == ["a", "b"]
```

**Coverage targets:**

| Function | Test Cases |
|----------|-----------|
| `extract_json()` | Markdown json block, generic code block, raw JSON, embedded JSON, no JSON |
| `fix_json()` | Trailing commas, unquoted keys, single quotes, truncation, comments, combined issues |
| `_convert_single_quotes()` | Simple conversion, escaped characters, mixed quotes |
| `_repair_truncation()` | Missing braces, missing brackets, nested structures, already balanced |
| `_remove_comments()` | Line comments, block comments, comments in strings (preserved) |
| `parse_json_response()` | Clean JSON, fixable JSON, unfixable JSON (raises ValueError), fix_on_error=False |

### 8.5.6 Serialization Tests

```python
class TestBinderSerializer:
    def test_serialize_for_prompt(self):
        binder = WorkBinder(investigation_id="test")
        binder.add_finding(persona="Theorist", finding_type="observation",
                          content="Test", confidence=0.5)
        serializer = BinderSerializer()
        result = serializer.serialize_for_prompt(binder, persona="Detective")
        assert "WORK BINDER" in result
        assert "BINDER INDEX" in result

    def test_serialize_for_investigation_start(self):
        binder = WorkBinder(investigation_id="test")
        serializer = BinderSerializer()
        result = serializer.serialize_for_investigation_start(binder)
        assert "BINDER CONTENTS" in result or result == ""

    def test_token_budget_truncation(self):
        binder = WorkBinder(investigation_id="test")
        for i in range(100):
            binder.add_finding(persona="Theorist", finding_type="observation",
                              content=f"Finding {i} " * 50, confidence=0.5)
        serializer = BinderSerializer()
        result = serializer.serialize_for_prompt(binder, max_tokens=500)
        assert len(result) <= 500 * 4 + 100  # Allow for truncation message
```

**Coverage targets:**

| Test Area | Test Cases |
|-----------|-----------|
| Empty binder | Serialize produces valid output |
| Persona exclusion | Current persona's findings excluded from recent findings |
| Focus artifacts | Specified artifacts rendered in full detail |
| Token budget | Large binder truncated to budget |
| Artifact index | All types correctly indexed |
| Call graph detail | `serialize_call_graph_detail()` includes callers, callees, code blocks |
| Tool instructions | Included when `include_tool_instructions=True` |

### 8.5.7 Permission Enforcement

The WorkBinder follows a "universal access" model -- all personas have equal access to all capabilities. There are no permission restrictions to test. The relevant test is:

```python
def test_any_persona_can_access_all_operations(self):
    """All personas have unrestricted access."""
    binder = WorkBinder(investigation_id="test")
    tools = BinderTools(binder=binder, persona_name="AnyPersona")
    # Should not raise
    await tools.add_finding(finding_type="observation", content="Test", confidence=0.5)
    await tools.list_artifacts()
    await tools.get_binder_stats()
```

### 8.5.8 Test Fixtures and Factories

Common fixtures used across workbinder tests:

```python
# Temporary database for persistence tests
@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)

@pytest.fixture
def store(temp_db):
    return BinderStore(temp_db)

# Pre-populated binder for query tests
@pytest.fixture
def populated_binder():
    binder = WorkBinder(investigation_id="test")
    binder.add_error_context(
        error=mock_log_entry(),
        context_logs=[],
        created_by="Archivist",
    )
    binder.add_finding(
        persona="Theorist",
        finding_type="observation",
        content="Test finding",
        confidence=0.8,
        phase=1,
    )
    binder.add_call_graph(
        center_function="processData",
        callers=[{"caller_name": "handleRequest"}],
        callees=[],
        created_by="Archivist",
        phase=0,
    )
    return binder

# Mock code index for BinderTools tests
@pytest.fixture
def mock_code_index():
    index = MagicMock()
    index.get_callers.return_value = [
        {"caller_name": "handleRequest", "caller_file": "handler.cpp"}
    ]
    index.get_callees.return_value = []
    index.find_function.return_value = [
        MagicMock(name="processData", file_path=Path("/src/core.cpp"),
                  start_line=100, end_line=150,
                  signature="void processData()")
    ]
    index.get_function_source.return_value = "void processData() { ... }"
    return index

# FastAPI test client
@pytest.fixture
def client():
    return TestClient(app)
```

### 8.5.9 Test File Inventory

| Test File | Module Under Test | Test Count Pattern |
|-----------|-------------------|-------------------|
| `tests/unit/test_workbinder.py` | `WorkBinder`, `BinderTools`, `BinderSerializer` | Core container, tools, serializer |
| `tests/unit/test_binder_persistence.py` | `BinderStore` | Persistence round-trips, queries |
| `tests/unit/test_api_binders.py` | `srcs/api/routes/binders.py` | Response models, endpoint validation |
| `tests/unit/test_slack_binder_commands.py` | Slack binder command handlers | Slack-specific binder access |
| `tests/unit/test_slack_binder_formatter.py` | Slack binder output formatting | Slack block formatting |

### 8.5.10 Running Tests

```bash
# All workbinder tests
./run_tests.sh tests/unit/test_workbinder.py tests/unit/test_binder_persistence.py

# API endpoint tests
./run_tests.sh tests/unit/test_api_binders.py

# Parser-related tests
./run_tests.sh tests/unit/test_parser.py

# All tests with coverage
./run_tests.sh --cov

# Specific test pattern
./run_tests.sh -k 'test_save_and_load'
```

---

## Summary

The WorkBinder is exposed through two parallel interfaces -- REST API and MCP -- that provide complete read access to the investigation artifact graph. Both interfaces access the same SQLite database via `BinderStore`, ensuring consistency.

The REST API provides 31 endpoints with Pydantic response models, parameter validation, and pagination. The MCP server provides 41 tools (of which approximately 25 are binder-related) with JSON string responses and progress reporting for long-running commands.

Session state maps one-to-one from investigation to binder. Each pipeline phase creates a deterministic set of artifact types, and phase transitions are tracked by `PhaseStateArtifact` and `InvestigationStateArtifact` records that enable pause, resume, and post-hoc analysis.

Testing spans five layers: core container unit tests, persistence round-trip tests, API endpoint tests, parser two-stage conversion tests, and JSON utility robustness tests. The universal access model means there are no permission boundaries to test -- all personas and all API consumers have equal read access to all artifacts.
