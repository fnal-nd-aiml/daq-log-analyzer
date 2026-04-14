> **Agentic REST API Design Document** | [← Code Analysis Tools](agentic-rest-service-design-ch3-code-analysis-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Pipeline & Admin Tools →](agentic-rest-service-design-ch5-pipeline-admin-tools.md)

---

# Chapter 4: Knowledge & Finding Tools

### Category: Knowledge Tools

These tools provide access to the knowledge base -- the system's accumulated learning
from past investigations. They query learned error patterns, retrieve similar historical
cases, and assemble bundled "warm start" packages that seed new investigations with
relevant prior knowledge. All three tools require `session_id` to access the session's
configured `KnowledgeBase` instance.

---

## Tool 10: `match_pattern`

### Purpose

Matches an error signature against the knowledge base's library of learned error
patterns. Use this tool when you encounter a specific error and want to know whether
the system has seen it before and what root causes are typically associated with it.
A strong pattern match (high confidence) may allow an investigation to take a fast
path, skipping expensive hypothesis generation and evidence seeking. A weak or absent
match tells the agent it is facing a novel error requiring full investigation.

Returns: `match` object with `pattern_id`, `confidence`, `message_pattern`, and
`typical_root_causes` array; or `match: null` when no pattern matches.

### Endpoint

```
POST /api/v1/agent/tools/match_pattern
```

### Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier. Required to access the session's KnowledgeBase."
    },
    "message_pattern": {
      "type": "string",
      "description": "Normalized error message with variable parts replaced by placeholders ({N}, {HEX}, {FLOAT}, {UUID}, {TIMESTAMP}). Example: 'Fragment timeout after {N}ms on link {HEX}'"
    },
    "level": {
      "type": "string",
      "enum": ["ERROR", "WARNING", "INFO", "DEBUG"],
      "default": "ERROR",
      "description": "Log level of the error."
    },
    "function": {
      "type": "string",
      "nullable": true,
      "description": "Function name where the error was emitted. Null if unknown."
    },
    "component": {
      "type": "string",
      "nullable": true,
      "description": "Component that emitted the error (e.g. 'BoardReader_01'). Null if unknown."
    }
  },
  "required": ["session_id", "message_pattern"]
}
```

### Response Schema

When a pattern is matched:

```json
{
  "match": {
    "pattern_id": "pat_a7c3e1f0",
    "confidence": 0.87,
    "message_pattern": "Fragment timeout after {N}ms on link {HEX}",
    "typical_root_causes": [
      {
        "description": "FE firmware crash on hardware link",
        "frequency": 0.7,
        "confidence": 0.85
      },
      {
        "description": "SHM buffer overflow under high rate",
        "frequency": 0.2,
        "confidence": 0.65
      }
    ]
  }
}
```

When no pattern matches:

```json
{
  "match": null
}
```

The `match.pattern_id` field is a navigation handle -- use it with `get_prior_knowledge`
or to reference this pattern in hypothesis recording.

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 400 | `VALIDATION_ERROR` | `message_pattern` is empty or missing |
| 400 | `invalid_enum_value` | `level` is not one of the valid enum values |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 503 | `VALIDATION_ERROR` | KnowledgeBase failed to initialize (SQLite/ChromaDB connection error) |
| 500 | `internal_error` | Unexpected error during pattern matching |

Example error:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "No active session with id 'b3f1a2c4-0000-0000-0000-000000000000'.",
    "details": {
      "session_id": "b3f1a2c4-0000-0000-0000-000000000000"
    }
  }
}
```

### Implementation

**Module:** `srcs/knowledge/base.py`
**Class:** `KnowledgeBase`
**Method:** `find_pattern(signature: ErrorSignature) -> PatternMatch | None`

Code path:

1. Router extracts `session_id`, looks up session to get `KnowledgeBase` instance.
2. Constructs `ErrorSignature(function=request.function, message_pattern=request.message_pattern, level=request.level, component=request.component)`.
3. Calls `kb.find_pattern(signature)`, which delegates to `self.sqlite.find_pattern(signature)`.
4. `SQLiteStore.find_pattern()` queries the `error_patterns` table, applies weighted scoring (function 40%, message 40%, level 10%, component 10%), and returns the best `PatternMatch` or `None`.
5. If `None`, returns `{"match": null}`. Otherwise, extracts `pattern_id`, `confidence`, `message_pattern`, and iterates over `match.root_causes` to build `typical_root_causes` array.
6. Returns flat response (no envelope).

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Resolves `session_id` to `KnowledgeBase` instance |
| SQLite (structured store) | Yes | Stores and queries learned error patterns |
| ChromaDB | No | Not used by this tool |
| LLM provider | No | Not used by this tool |

### Testing

1. **test_match_pattern_found** -- Insert a known `ErrorPattern` into the SQLite store. Call `match_pattern` with a matching signature. Assert response has `match.pattern_id`, `match.confidence > 0`, and `match.typical_root_causes` is a list. Mock: `SQLiteStore.find_pattern` returns a pre-built `PatternMatch`.

2. **test_match_pattern_not_found** -- Call with a signature that has no matching pattern. Assert `match` is `null`. Mock: `SQLiteStore.find_pattern` returns `None`.

3. **test_match_pattern_invalid_session** -- Call with a non-existent `session_id`. Assert 404 with `SESSION_NOT_FOUND` error code.

4. **test_match_pattern_root_causes** -- Insert a pattern with known root causes. Assert `match.typical_root_causes` contains objects with `description`, `frequency`, and `confidence` fields.

5. **test_match_pattern_empty_message** -- Call with `message_pattern: ""`. Assert 400 with `VALIDATION_ERROR`.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/match_pattern \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
    "message_pattern": "Fragment timeout after {N}ms on link {HEX}",
    "level": "ERROR",
    "function": "readFragment",
    "component": "BoardReader_01"
  }'
```

Response:

```json
{
  "match": {
    "pattern_id": "pat_a7c3e1f0",
    "confidence": 0.87,
    "message_pattern": "Fragment timeout after {N}ms on link {HEX}",
    "typical_root_causes": [
      {
        "description": "FE firmware crash on hardware link",
        "frequency": 0.7,
        "confidence": 0.85
      },
      {
        "description": "SHM buffer overflow under high rate",
        "frequency": 0.2,
        "confidence": 0.65
      }
    ]
  }
}
```

---

## Tool 11: `find_similar_investigations`

### Purpose

Finds similar past investigations using semantic vector search over ChromaDB embeddings.
Use this tool when you have an error and its surrounding context and want to find
historically similar cases -- even when the error messages differ in wording but
describe the same underlying problem. Unlike `match_pattern` which does exact signature
matching, this tool uses embedding similarity to find conceptually related
investigations. The returned cases include their root causes and outcome status,
letting the agent leverage prior diagnostic work.

Returns: `similar_investigations` array with `investigation_id`, `similarity`,
`error_message`, `root_cause`, and `outcome` per entry; plus `total` count.

### Endpoint

```
POST /api/v1/agent/tools/find_similar_investigations
```

### Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "error_message": {
      "type": "string",
      "description": "The error message text to search for. If omitted, the tool will attempt to use the first ERROR-level entry from parsed logs in the session."
    },
    "level": {
      "type": "string",
      "enum": ["ERROR", "WARNING", "INFO", "DEBUG"],
      "default": "ERROR",
      "description": "Log severity level."
    },
    "component": {
      "type": "string",
      "default": "Unknown",
      "description": "Component that emitted the error (e.g. 'BoardReader_01')."
    },
    "n": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20,
      "default": 5,
      "description": "Number of similar investigations to return."
    }
  },
  "required": ["session_id"]
}
```

### Response Schema

```json
{
  "similar_investigations": [
    {
      "investigation_id": "inv_8b2d4f6a",
      "similarity": 0.91,
      "error_message": "Fragment timeout after 5000ms on link 0x0100",
      "root_cause": "Fragment timeout caused by FE link 0x0100 firmware crash after power glitch",
      "outcome": "CONFIDENT"
    },
    {
      "investigation_id": "inv_c3e5a7b9",
      "similarity": 0.78,
      "error_message": "Hardware link timeout on register 0x0200",
      "root_cause": "Hardware link timeout due to misconfigured FE register",
      "outcome": "PROBABLE"
    }
  ],
  "total": 2
}
```

Each `investigation_id` is a navigation handle that can be used to reference this past
investigation. The `similarity` field ranges from 0 to 1, where higher values indicate
stronger semantic similarity.

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 400 | `VALIDATION_ERROR` | `error_message` is missing and no parsed logs with errors exist in session |
| 400 | `invalid_parameter` | `n` is outside the valid range [1, 20] |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 503 | `VALIDATION_ERROR` | ChromaDB connection failed or embedding generation failed |
| 500 | `internal_error` | Unexpected error during similarity search |

Example error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "ChromaDB is not available. Semantic search cannot be performed.",
    "details": {
      "service": "chromadb",
      "reason": "Connection refused on localhost:8100"
    }
  }
}
```

### Implementation

**Module:** `srcs/knowledge/base.py`
**Class:** `KnowledgeBase`
**Method:** `find_similar_investigations(error: Log, context: list[Log], n: int = 5) -> list[SimilarInvestigation]`

Code path:

1. Router extracts `session_id`, resolves session to get `KnowledgeBase` instance.
2. Reads `error_message` from params; if absent, falls back to first ERROR-level entry from `session.state.parsed_logs`.
3. Constructs `Log` object with `timestamp=datetime.now()`, `level`, `component`, and `message` from params.
4. Calls `kb.find_similar_investigations(error_log, context_logs=[], n=n)`.
5. For each `SimilarInvestigation` result, extracts `investigation_id`, `similarity`, `error_message`, `root_cause`, and `outcome` (using `hasattr` fallbacks for optional fields).
6. Returns flat response with `similar_investigations` array and `total` count.

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Resolves `session_id` to `KnowledgeBase` instance |
| ChromaDB | Yes | Stores investigation embeddings and performs vector similarity search |
| LLM provider | Yes | Generates embedding vectors for the query description |
| SQLite | No | Not directly queried (metadata is stored in ChromaDB) |

### Testing

1. **test_find_similar_with_results** -- Populate ChromaDB with 3 investigation embeddings. Call `find_similar_investigations` with a related error. Assert response contains `similar_investigations` sorted by `similarity` descending and `total` matches array length. Mock: `ChromaStore.find_similar_investigations` returns pre-built list.

2. **test_find_similar_empty_collection** -- Call against an empty ChromaDB collection. Assert `similar_investigations: []` and `total: 0`.

3. **test_find_similar_respects_n** -- Call with `n=2` when 5 similar investigations exist. Assert exactly 2 results returned.

4. **test_find_similar_missing_error_message** -- Call without `error_message` and with no parsed logs in session. Assert 400 with `VALIDATION_ERROR`.

5. **test_find_similar_embedding_failure** -- Simulate LLM embedding function raising an exception. Assert 503 with `VALIDATION_ERROR`.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/find_similar_investigations \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
    "error_message": "Fragment timeout after 5000ms on link 0x0100",
    "level": "ERROR",
    "component": "BoardReader_01",
    "n": 5
  }'
```

Response:

```json
{
  "similar_investigations": [
    {
      "investigation_id": "inv_8b2d4f6a",
      "similarity": 0.91,
      "error_message": "Fragment timeout after 5000ms on link 0x0100",
      "root_cause": "Fragment timeout caused by FE link 0x0100 firmware crash after power glitch",
      "outcome": "CONFIDENT"
    },
    {
      "investigation_id": "inv_c3e5a7b9",
      "similarity": 0.78,
      "error_message": "Hardware link timeout on register 0x0200",
      "root_cause": "Hardware link timeout due to misconfigured FE register 0x0200",
      "outcome": "PROBABLE"
    },
    {
      "investigation_id": "inv_d4f6a8c0",
      "similarity": 0.65,
      "error_message": "Fragment loss during high-rate acquisition",
      "root_cause": "BoardReader fragment loss from SHM backpressure during high-rate run",
      "outcome": "CONFIDENT"
    }
  ],
  "total": 3
}
```

---

## Tool 12: `get_prior_knowledge`

### Purpose

Assembles a combined prior knowledge bundle from all available historical sources:
pattern matches, similar investigations, recommended hypotheses derived from those
matches, and recommended evidence queries. This is the primary "warm start" tool --
call it early in an investigation to seed the agent with everything the system has
learned about this type of error. It combines the capabilities of `match_pattern` and
`find_similar_investigations` into a single call, and adds higher-level derived outputs
(hypotheses and queries) that pattern-only or similarity-only calls do not provide.

Returns: `matched_patterns` array (each with `pattern_id`, `confidence`,
`message_pattern`), `similar_investigations` array (each with `investigation_id`,
`similarity`), `recommended_hypotheses` array (each with `description`, `source`,
`prior_probability`), and `recommended_queries` array (each with `query_type`,
`parameters`).

### Endpoint

```
POST /api/v1/agent/tools/get_prior_knowledge
```

### Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "error_message": {
      "type": "string",
      "description": "The error message text. If omitted, the tool will attempt to use the first ERROR-level entry from parsed logs in the session."
    },
    "level": {
      "type": "string",
      "enum": ["ERROR", "WARNING", "INFO", "DEBUG"],
      "default": "ERROR",
      "description": "Log severity level."
    },
    "component": {
      "type": "string",
      "default": "Unknown",
      "description": "Component that emitted the error."
    }
  },
  "required": ["session_id"]
}
```

### Response Schema

```json
{
  "matched_patterns": [
    {
      "pattern_id": "pat_a7c3e1f0",
      "confidence": 0.87,
      "message_pattern": "Fragment timeout after {N}ms on link {HEX}"
    }
  ],
  "similar_investigations": [
    {
      "investigation_id": "inv_8b2d4f6a",
      "similarity": 0.91
    }
  ],
  "recommended_hypotheses": [
    {
      "description": "FE firmware crash on link causing fragment timeout",
      "source": "pattern",
      "prior_probability": 0.72
    },
    {
      "description": "Fragment timeout caused by FE link firmware crash",
      "source": "similar",
      "prior_probability": 0.85
    }
  ],
  "recommended_queries": [
    {
      "query_type": "code_search",
      "parameters": {"query": "getNext_"}
    },
    {
      "query_type": "log_search",
      "parameters": {"pattern": "FE link status change"}
    }
  ]
}
```

Navigation handles: `pattern_id` values reference specific patterns;
`investigation_id` values reference past investigations; hypothesis `source` fields
indicate the origin type (`"pattern"` or `"similar"`).

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 400 | `VALIDATION_ERROR` | `error_message` is missing and no parsed logs with errors exist in session |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 503 | `VALIDATION_ERROR` | SQLite or ChromaDB connection failure |
| 500 | `internal_error` | Unexpected error during prior knowledge assembly |

Example error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'error_message' is required (or parse_logs must have found errors).",
    "details": {
      "field": "error_message"
    }
  }
}
```

### Implementation

**Module:** `srcs/knowledge/base.py`
**Class:** `KnowledgeBase`
**Method:** `get_prior_knowledge(error: Log, context: list[Log]) -> PriorKnowledge`

Code path:

1. Router extracts `session_id`, resolves to `KnowledgeBase` instance.
2. Reads `error_message` from params; if absent, falls back to first ERROR-level entry from `session.state.parsed_logs`.
3. Constructs `Log` with `timestamp=datetime.now()`, `level`, `component`, and `message`.
4. Calls `kb.get_prior_knowledge(error_log, context_logs=[])`.
5. Extracts from `PriorKnowledge` result:
   a. `matched_patterns`: each with `pattern_id`, `confidence`, `message_pattern`.
   b. `similar_investigations`: each with `investigation_id`, `similarity`.
   c. `recommended_hypotheses`: each with `description`, `source`, `prior_probability`.
   d. `recommended_queries`: each with `query_type`, `parameters`.
6. Returns flat response (no envelope, no summary counts).

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Resolves `session_id` to `KnowledgeBase` instance |
| SQLite (structured store) | Yes | Pattern matching and root cause retrieval |
| ChromaDB | Yes | Semantic similarity search for investigations |
| LLM provider | Yes | Generates embeddings for similarity search |

### Testing

1. **test_prior_knowledge_full_bundle** -- Seed SQLite with a pattern and ChromaDB with a similar investigation. Call `get_prior_knowledge`. Assert all four lists are populated. Mock: `SQLiteStore.find_pattern` and `ChromaStore.find_similar_investigations` return pre-built results.

2. **test_prior_knowledge_no_history** -- Call against empty knowledge base. Assert all lists are empty.

3. **test_prior_knowledge_pattern_fields** -- Verify each entry in `matched_patterns` has `pattern_id`, `confidence`, and `message_pattern` fields only.

4. **test_prior_knowledge_hypothesis_fields** -- Verify each entry in `recommended_hypotheses` has `description`, `source`, and `prior_probability` fields.

5. **test_prior_knowledge_invalid_session** -- Call with non-existent `session_id`. Assert 404.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/get_prior_knowledge \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
    "error_message": "Fragment timeout after 5000ms on link 0x0100",
    "level": "ERROR",
    "component": "BoardReader_01"
  }'
```

Response:

```json
{
  "matched_patterns": [
    {
      "pattern_id": "pat_a7c3e1f0",
      "confidence": 0.87,
      "message_pattern": "Fragment timeout after {N}ms on link {HEX}"
    }
  ],
  "similar_investigations": [
    {
      "investigation_id": "inv_8b2d4f6a",
      "similarity": 0.91
    },
    {
      "investigation_id": "inv_c3e5a7b9",
      "similarity": 0.78
    }
  ],
  "recommended_hypotheses": [
    {
      "description": "FE firmware crash on link causing read timeout",
      "source": "pattern",
      "prior_probability": 0.72
    },
    {
      "description": "Fragment timeout caused by FE link 0x0100 firmware crash after power glitch",
      "source": "similar",
      "prior_probability": 0.85
    }
  ],
  "recommended_queries": [
    {
      "query_type": "code_search",
      "parameters": {"query": "getNext_"}
    },
    {
      "query_type": "log_search",
      "parameters": {"pattern": "FE link status change within 5s before timeout"}
    }
  ]
}
```

---

### Category: Finding/Hypothesis Tools

These tools manage the agent's in-progress reasoning state within a session. Findings
capture observed facts with evidence citations. Hypotheses capture candidate root
causes with confidence scores. These are session-scoped and held in memory only --
they are not persisted to the knowledge base. They structure the agent's investigation
and enable the orchestrator (or a human reviewer) to inspect the agent's reasoning
at any point during the investigation.

---

## Tool 13: `record_finding`

### Purpose

Records an intermediate investigation finding with a category, description, and optional
evidence references. Use this tool whenever the agent discovers something significant
during investigation: an error pattern, a temporal correlation between events, a
configuration anomaly, a component failure sequence. Each finding is tagged with a
severity level and category, and optionally linked to supporting evidence strings.
Findings accumulate in the session and form the evidentiary foundation for hypotheses
and the final synthesis.

This tool operates entirely on session state. It does not call any backend knowledge
base function or persist data to SQLite/ChromaDB. The finding exists only for the
duration of the session.

Returns: `finding_id` (auto-generated unique identifier) and `total_findings` count.

### Endpoint

```
POST /api/v1/agent/tools/record_finding
```

### Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "category": {
      "type": "string",
      "minLength": 1,
      "description": "Category of the finding (e.g. 'log_anomaly', 'code_issue', 'timing', 'config', 'resource')."
    },
    "description": {
      "type": "string",
      "minLength": 1,
      "maxLength": 2000,
      "description": "Clear description of what was discovered. Should be specific and cite relevant identifiers (timestamps, components, line numbers)."
    },
    "severity": {
      "type": "string",
      "enum": ["critical", "high", "medium", "low"],
      "default": "medium",
      "description": "Impact severity. 'critical' = root cause or data loss. 'high' = significant contributing factor. 'medium' = notable observation. 'low' = minor detail."
    },
    "evidence": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "Supporting evidence strings (e.g. log excerpts, code references)."
    },
    "source_tool": {
      "type": "string",
      "nullable": true,
      "description": "Name of the tool that produced this finding (e.g. 'search_logs', 'find_error_source')."
    }
  },
  "required": ["session_id", "category", "description"]
}
```

### Response Schema

```json
{
  "finding_id": "a1b2c3d4",
  "total_findings": 3
}
```

The `finding_id` is a navigation handle -- an auto-generated 8-character hex identifier
used to reference this finding in hypothesis evidence lists.

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 400 | `VALIDATION_ERROR` | `category` or `description` is empty or missing |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 500 | `internal_error` | Unexpected error writing to session state |

Example error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'category' and 'description' are required for record_finding.",
    "details": {}
  }
}
```

### Implementation

**Module:** None (session-state only)
**Class:** Session state manager (`SessionFinding` Pydantic model)
**Method:** N/A -- implemented directly in the tool router

Code path:

1. Router extracts `session_id`, resolves session state object.
2. Reads `category` and `description` from params. Validates both are non-empty.
3. Creates `SessionFinding(category=category, description=description, severity=severity, evidence=evidence, source_tool=source_tool)` which auto-generates an 8-character hex `id`.
4. Appends to `session.state.findings` list.
5. Returns `finding_id` and `total_findings` count.

No backend function is called. No data is written to SQLite or ChromaDB.

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Stores findings in session-scoped in-memory state |
| SQLite | No | Not used |
| ChromaDB | No | Not used |
| LLM provider | No | Not used |

### Testing

1. **test_record_finding_basic** -- Create a session, record a finding with category "timing" and severity "high". Assert response has `finding_id` (8-char hex string) and `total_findings` is 1.

2. **test_record_finding_increments_total** -- Record three findings in sequence. Assert `total_findings` increments to 1, 2, 3 respectively.

3. **test_record_finding_no_evidence** -- Record a finding without the `evidence` field. Assert it succeeds with `total_findings: 1`.

4. **test_record_finding_missing_category** -- Attempt to record a finding without `category`. Assert 400 with `VALIDATION_ERROR`.

5. **test_record_finding_invalid_session** -- Call with non-existent `session_id`. Assert 404.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/record_finding \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
    "category": "timing",
    "description": "BoardReader_01 experienced 487 fragment timeouts on link 0x0100 between 10:32:15 and 10:45:02 UTC. All timeouts had the same 5000ms duration, suggesting a hard link failure rather than intermittent latency.",
    "severity": "critical",
    "evidence": [
      "Fragment timeout after 5000ms on link 0x0100 (line 4523)",
      "Incomplete event: missing fragment from BoardReader_01 (line 8891)"
    ],
    "source_tool": "search_logs"
  }'
```

Response:

```json
{
  "finding_id": "a1b2c3d4",
  "total_findings": 1
}
```

---

## Tool 14: `record_hypothesis`

### Purpose

Records a root cause hypothesis for the investigation. Use this tool when the agent
has enough evidence (from findings, pattern matches, or similar cases) to propose a
candidate explanation for the observed failure. Each hypothesis has an initial
confidence score and can optionally reference supporting and contradicting evidence.
Hypotheses can be updated later via `update_hypothesis`.

This tool operates entirely on session state. It does not persist to the knowledge
base. Hypotheses are the central artifacts that drive the agent's subsequent evidence
seeking and adversarial review.

Returns: `hypothesis_id` (auto-generated unique identifier) and `total_hypotheses`
count.

### Endpoint

```
POST /api/v1/agent/tools/record_hypothesis
```

### Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "description": {
      "type": "string",
      "minLength": 1,
      "maxLength": 2000,
      "description": "Description of the proposed root cause. Should be specific enough to be testable -- i.e., the agent can seek evidence that would confirm or refute it."
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "default": 0.5,
      "description": "Initial confidence score (0.0 = impossible, 1.0 = certain). Pattern-derived hypotheses typically start at 0.6-0.8. Fresh hypotheses typically start at 0.3 or below."
    },
    "supporting_evidence": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "List of evidence strings supporting this hypothesis."
    },
    "contradicting_evidence": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "List of evidence strings contradicting this hypothesis."
    }
  },
  "required": ["session_id", "description"]
}
```

### Response Schema

```json
{
  "hypothesis_id": "e5f6a7b8",
  "total_hypotheses": 2
}
```

The `hypothesis_id` is a navigation handle -- an auto-generated 8-character hex
identifier used in `update_hypothesis` and referenced in the findings summary.

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 400 | `VALIDATION_ERROR` | `description` is empty or missing |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 500 | `internal_error` | Unexpected error writing to session state |

Example error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "'description' is required for record_hypothesis.",
    "details": {}
  }
}
```

### Implementation

**Module:** None (session-state only)
**Class:** Session state manager (`SessionHypothesis` Pydantic model)
**Method:** N/A -- implemented directly in the tool router

Code path:

1. Router extracts `session_id`, resolves session state object.
2. Reads `description` from params. Validates it is non-empty.
3. Creates `SessionHypothesis(description=description, confidence=confidence, supporting_evidence=supporting_evidence, contradicting_evidence=contradicting_evidence)` which auto-generates an 8-character hex `id` and defaults `status` to `"active"`.
4. Appends to `session.state.hypotheses` list.
5. Returns `hypothesis_id` and `total_hypotheses` count.

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Stores hypotheses in session-scoped in-memory state |
| SQLite | No | Not used |
| ChromaDB | No | Not used |
| LLM provider | No | Not used |

### Testing

1. **test_record_hypothesis_basic** -- Create a session, record a hypothesis with description and default confidence. Assert response has `hypothesis_id` (8-char hex string) and `total_hypotheses` is 1.

2. **test_record_hypothesis_with_evidence** -- Record a hypothesis with `supporting_evidence` and `contradicting_evidence` arrays. Assert it succeeds and `total_hypotheses` is 1.

3. **test_record_hypothesis_custom_confidence** -- Record with `confidence: 0.8`. Assert success and verify via `get_findings_summary` that the hypothesis has the correct confidence.

4. **test_record_hypothesis_increments_total** -- Record two hypotheses. Assert `total_hypotheses` increments to 1 then 2.

5. **test_record_hypothesis_missing_description** -- Attempt to record without `description`. Assert 400 with `VALIDATION_ERROR`.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/record_hypothesis \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
    "description": "Fragment timeout on BoardReader_01 link 0x0100 caused by FE firmware crash triggered by power supply voltage sag on crate 2. The consistent 5000ms timeout (hard limit) with no preceding latency increase points to a sudden link death rather than gradual degradation.",
    "confidence": 0.72,
    "supporting_evidence": ["Power supply voltage dip at line 3201 precedes timeout by 2.1s"]
  }'
```

Response:

```json
{
  "hypothesis_id": "e5f6a7b8",
  "total_hypotheses": 1
}
```

---

## Tool 15: `update_hypothesis`

### Purpose

Updates an existing hypothesis in the session. Use this tool after the agent discovers
new information that strengthens or weakens a hypothesis. Updates can change the
`confidence` score, the `status` (active, confirmed, refuted, merged), or add new
supporting/contradicting evidence. This allows the agent to evolve its reasoning as
evidence accumulates.

Returns: `hypothesis_id`, current `confidence`, and current `status`.

### Endpoint

```
POST /api/v1/agent/tools/update_hypothesis
```

### Request Schema

```json
{
  "type": "object",
  "properties": {
    "session_id": {
      "type": "string",
      "format": "uuid",
      "description": "Active session identifier."
    },
    "hypothesis_id": {
      "type": "string",
      "description": "ID of the hypothesis to update (8-char hex). Must reference an existing hypothesis in the session."
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "New absolute confidence value. Replaces the previous confidence score."
    },
    "status": {
      "type": "string",
      "enum": ["active", "confirmed", "refuted", "merged"],
      "description": "New status for the hypothesis."
    },
    "supporting_evidence": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "Additional supporting evidence strings to append to the hypothesis."
    },
    "contradicting_evidence": {
      "type": "array",
      "items": { "type": "string" },
      "default": [],
      "description": "Additional contradicting evidence strings to append to the hypothesis."
    }
  },
  "required": ["session_id", "hypothesis_id"]
}
```

### Response Schema

```json
{
  "hypothesis_id": "e5f6a7b8",
  "confidence": 0.85,
  "status": "active"
}
```

The response reflects the hypothesis state after the update has been applied. Only
the fields that were provided in the request are changed; all others retain their
previous values.

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 400 | `VALIDATION_ERROR` | `hypothesis_id` is missing, or `confidence` is outside [0.0, 1.0] |
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 400 | `VALIDATION_ERROR` | `hypothesis_id` does not match any hypothesis in the session |
| 500 | `internal_error` | Unexpected error updating session state |

Example error:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Hypothesis 'hyp_099' not found in session.",
    "details": {
      "hypothesis_id": "hyp_099"
    }
  }
}
```

### Implementation

**Module:** None (session-state only)
**Class:** Session state manager (`SessionHypothesis` Pydantic model)
**Method:** N/A -- implemented directly in the tool router

Code path:

1. Router extracts `session_id`, resolves session state object.
2. Reads `hypothesis_id` from params. Validates it is non-empty.
3. Iterates `session.state.hypotheses` to find the matching hypothesis by `id`. Raises validation error if not found.
4. If `confidence` is provided, sets `target.confidence` to the new value.
5. If `status` is provided, sets `target.status` to the new value.
6. If `supporting_evidence` is provided, extends `target.supporting_evidence`.
7. If `contradicting_evidence` is provided, extends `target.contradicting_evidence`.
8. Returns `hypothesis_id`, current `confidence`, and current `status`.

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Reads and writes hypothesis state in session |
| SQLite | No | Not used |
| ChromaDB | No | Not used |
| LLM provider | No | Not used |

### Testing

1. **test_update_hypothesis_confidence** -- Record a hypothesis with confidence 0.5, update with `confidence: 0.85`. Assert response has `confidence: 0.85` and `status: "active"` (unchanged).

2. **test_update_hypothesis_status** -- Record a hypothesis, update with `status: "confirmed"`. Assert response has `status: "confirmed"`.

3. **test_update_hypothesis_add_evidence** -- Record a hypothesis, update with `supporting_evidence: ["new evidence"]`. Assert the hypothesis now has the new evidence appended.

4. **test_update_hypothesis_not_found** -- Attempt to update a non-existent hypothesis ID. Assert 400 with `VALIDATION_ERROR`.

5. **test_update_hypothesis_partial_update** -- Update only `confidence` without providing `status`. Assert `status` remains at its previous value.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/update_hypothesis \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b",
    "hypothesis_id": "e5f6a7b8",
    "confidence": 0.85,
    "supporting_evidence": ["Crate 2 power supply voltage dip at line 3201 matches FE crash threshold"]
  }'
```

Response:

```json
{
  "hypothesis_id": "e5f6a7b8",
  "confidence": 0.85,
  "status": "active"
}
```

---

## Tool 16: `get_findings_summary`

### Purpose

Retrieves a read-only summary of all findings and hypotheses recorded in the current
session. Use this tool to review the state of the investigation before synthesizing a
final report, or at any checkpoint to assess coverage and completeness. The summary
presents findings aggregated by category and severity, and hypotheses ranked by
confidence, giving the agent (and any human observer) a clear picture of what has been
discovered and what the leading explanations are.

This tool performs no mutations and calls no backend services. It reads directly from
session state.

Returns: `total_findings`, `total_hypotheses`, `findings_by_category`,
`findings_by_severity`, `ranked_hypotheses` (sorted by confidence descending), and
`active_hypotheses` count.

### Endpoint

```
POST /api/v1/agent/tools/get_findings_summary
```

### Request Schema

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

### Response Schema

```json
{
  "total_findings": 5,
  "total_hypotheses": 3,
  "findings_by_category": {
    "timing": 2,
    "resource": 3
  },
  "findings_by_severity": {
    "critical": 1,
    "high": 2,
    "medium": 2
  },
  "ranked_hypotheses": [
    {
      "id": "e5f6a7b8",
      "description": "Fragment timeout caused by FE firmware crash triggered by power supply voltage sag",
      "confidence": 0.85,
      "status": "active",
      "supporting_count": 3,
      "contradicting_count": 0
    },
    {
      "id": "c9d0e1f2",
      "description": "BoardReader link 0x0100 hardware failure unrelated to power supply",
      "confidence": 0.15,
      "status": "active",
      "supporting_count": 0,
      "contradicting_count": 1
    }
  ],
  "active_hypotheses": 2
}
```

The `ranked_hypotheses` array is sorted by `confidence` descending (highest confidence
first). Each entry includes `supporting_count` and `contradicting_count` derived from
the lengths of the hypothesis's evidence arrays. `active_hypotheses` counts hypotheses
with `status == "active"`.

### Error Responses

| Status | Error Code | Condition |
|--------|-----------|-----------|
| 404 | `SESSION_NOT_FOUND` | `session_id` does not match any active session |
| 500 | `internal_error` | Unexpected error reading session state |

Example error:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "No active session with id 'b3f1a2c4-0000-0000-0000-000000000000'.",
    "details": {
      "session_id": "b3f1a2c4-0000-0000-0000-000000000000"
    }
  }
}
```

### Implementation

**Module:** None (session-state only)
**Class:** Session state manager (in-memory dict per session)
**Method:** N/A -- implemented directly in the tool router

Code path:

1. Router extracts `session_id`, resolves session state object.
2. Reads `session.state.findings` list. Aggregates by `category` and `severity` into count dicts.
3. Reads `session.state.hypotheses` list. Sorts by `confidence` descending. For each hypothesis, computes `supporting_count` and `contradicting_count` from evidence array lengths.
4. Counts `active_hypotheses` as hypotheses with `status == "active"`.
5. Returns flat response with all aggregate fields.

No backend function is called. No data is written.

### Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Session store | Yes | Reads findings and hypotheses from session state |
| SQLite | No | Not used |
| ChromaDB | No | Not used |
| LLM provider | No | Not used |

### Testing

1. **test_summary_empty_session** -- Create a new session with no findings or hypotheses. Assert `total_findings: 0`, `total_hypotheses: 0`, empty dicts for `findings_by_category` and `findings_by_severity`, empty `ranked_hypotheses`, `active_hypotheses: 0`.

2. **test_summary_ranked_hypotheses** -- Record hypotheses with confidences 0.3, 0.8, 0.5. Assert `ranked_hypotheses` array is ordered by confidence [0.8, 0.5, 0.3].

3. **test_summary_findings_aggregation** -- Record findings with categories "timing" and "resource" and severities "high" and "medium". Assert `findings_by_category` and `findings_by_severity` have correct counts.

4. **test_summary_active_hypotheses** -- Record two hypotheses, update one to status "refuted". Assert `active_hypotheses: 1`.

5. **test_summary_invalid_session** -- Call with non-existent `session_id`. Assert 404.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/agent/tools/get_findings_summary \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "b3f1a2c4-5d6e-7f80-9a1b-2c3d4e5f6a7b"
  }'
```

Response:

```json
{
  "total_findings": 3,
  "total_hypotheses": 2,
  "findings_by_category": {
    "timing": 1,
    "resource": 1,
    "log_anomaly": 1
  },
  "findings_by_severity": {
    "critical": 1,
    "high": 2
  },
  "ranked_hypotheses": [
    {
      "id": "e5f6a7b8",
      "description": "Fragment timeout on BoardReader_01 link 0x0100 caused by FE firmware crash triggered by power supply voltage sag on crate 2",
      "confidence": 0.85,
      "status": "active",
      "supporting_count": 2,
      "contradicting_count": 0
    },
    {
      "id": "c9d0e1f2",
      "description": "BoardReader_01 link 0x0100 hardware failure unrelated to power supply",
      "confidence": 0.15,
      "status": "active",
      "supporting_count": 0,
      "contradicting_count": 1
    }
  ],
  "active_hypotheses": 2
}
```

---

> [← Code Analysis Tools](agentic-rest-service-design-ch3-code-analysis-tools.md) | [Table of Contents](agentic-rest-service-design.md) | [Next: Pipeline & Admin Tools →](agentic-rest-service-design-ch5-pipeline-admin-tools.md)
