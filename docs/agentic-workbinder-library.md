> **Agentic WorkBinder Library** | [Agentic REST API Design](agentic-rest-service-design.md) | [Agentic Persona Library](agentic-persona-library.md)

---

# Agentic WorkBinder Library

## Table of Contents

---

### Document Purpose

This is the third companion document in the artdaq Deep Investigation Agent agentic design series. The [Agentic REST API Design](agentic-rest-service-design.md) specifies 21 composable session-based tools exposed by the REST API. The [Agentic Persona Library](agentic-persona-library.md) details the 10 personas that power the investigation pipeline. This document fills the gap between them by documenting the **WorkBinder** -- the central artifact store through which all personas communicate.

The WorkBinder is the single source of truth for every investigation. Personas do not exchange data directly; instead, each phase writes typed artifacts into the binder and later phases read them forward. The binder captures not only investigation artifacts (hypotheses, evidence, causal chains) but also every LLM request/response pair, phase lifecycle state, flow configuration, and a complete audit trail. This design enables full traceability, reproducibility, and pause/resume of any investigation.

This document covers all 24 artifact types, the core WorkBinder API, the permissions model, the audit system, state management, LLM communication tracking, evidence-hypothesis linking, and the complete artifact data flow through the 7-phase investigation pipeline.

---

### Artifact Quick Reference

| Artifact Type | Category | Producer Phase | Key Fields | Chapter |
|---------------|----------|----------------|------------|---------|
| `LOG_BUNDLE` | Multi-File Log | -1 Chronicler | `source_files`, `merged_timeline`, `primary_error`, `clues`, `affected_boards`, `cascade_chain` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `MERGED_TIMELINE` | Multi-File Log | -1 Chronicler | `entries`, `total_entries`, `total_errors`, `file_count` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `BOARDREADER_IDENTIFICATION` | Multi-File Log | -1 Chronicler | `boardreader_types`, `components`, `error_messages` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `ERROR_CONTEXT` | Original | 0 Archivist | `error_message`, `error_level`, `error_component`, `context_logs` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `SOURCE_LOCATION` | Original | 0 Archivist | `file_path`, `line_number`, `match_score`, `function_signature` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `CALL_GRAPH` | Original | 0 Archivist | `center_function`, `callers`, `callees`, `diagram` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `CODE_SNIPPET` | Original | 0 Archivist | `file_path`, `start_line`, `end_line`, `content`, `summary` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `FUNCTION_SUMMARY` | Original | 0 Archivist | `purpose`, `mechanism`, `data_flow`, `error_paths`, `role` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `FINDING` | Original | Any | `persona`, `finding_type`, `content`, `confidence` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `ANNOTATION` | Original | Any | `target_artifact_id`, `annotation_type`, `annotation_content` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `HYPOTHESIS_ARTIFACT` | Investigation | 1 Theorist | `description`, `source`, `score`, `supporting_evidence_ids` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `EVIDENCE_ARTIFACT` | Investigation | 2 Detective | `evidence_type`, `content`, `strength`, `supports_hypothesis_ids` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `CAUSAL_CHAIN` | Investigation | 3 Logician | `hypothesis_id`, `steps`, `completeness_score`, `evidence_coverage`, `gaps`, `assumptions` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `CHALLENGE` | Investigation | 4 Devil's Advocate | `target_hypothesis_id`, `challenge_type`, `content`, `severity`, `resolved` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `CONCLUSION` | Investigation | 6 Synthesizer | `root_cause`, `confidence_raw`, `confidence_calibrated`, `outcome` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `PERSONA_CONTRIBUTION` | Investigation | Any | `persona_id`, `contribution_phase`, `content`, `confidence` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `LLM_REQUEST` | LLM Tracking | Any | `persona`, `prompt_key`, `system_prompt`, `user_prompt`, `model` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `LLM_RESPONSE` | LLM Tracking | Any | `linked_request_id`, `raw_response`, `tokens_used`, `latency_ms` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `FLOW_CONFIG` | State Mgmt | 0 System | `investigation_config`, `llm_config`, `enabled_phases` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `PHASE_STATE` | State Mgmt | Per-phase | `phase_number`, `persona_name`, `status`, `started_at` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `INVESTIGATION_STATE` | State Mgmt | 0 System | `investigation_id`, `current_phase`, `status`, `outcome` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |
| `FEEDBACK` | Feedback | Any | `investigation_id`, `was_correct`, `actual_cause`, `feedback_source` | [Ch. 1](agentic-workbinder-library-ch1-architecture.md) |

---

### Artifact Flow Diagram

```
Time ──────────────────────────────────────────────────────────────────────────>

Phase -1         Phase 0          Phase 1          Phase 2          Phase 3
Chronicler       Archivist        Theorist         Detective        Logician
    |                |                |                |                |
    | Write:         | Write:         | Read:          | Read:          | Read:
    | LOG_BUNDLE     | FLOW_CONFIG    | ERROR_CONTEXT  | Phase 0+1      | Phase 0+1+2
    | MERGED_TIMELINE| INV_STATE      | SOURCE_LOC     | artifacts      | artifacts
    | BOARDREADER_ID | ERROR_CONTEXT  | CALL_GRAPH     |                |
    |                | SOURCE_LOC     | CODE_SNIPPET   | Write:         | Write:
    |                | CALL_GRAPH     | FUNC_SUMMARY   | EVIDENCE       | CAUSAL_CHAIN
    |                | CODE_SNIPPET   | LOG_BUNDLE     |                |
    |                | FUNC_SUMMARY   |                |                |
    |                | PHASE_STATE    | Write:         |                |
    |                |                | HYPOTHESIS     |                |
    v                v                v                v                v
─────────────────────────────────────────────────────────────────────────────

Phase 4          Phase 5          Phase 6          Phase 7
Devil's Advocate Judge            Synthesizer      Learner
    |                |                |                |
    | Read:          | Read:          | Read:          | Read:
    | All prior      | All prior      | ALL artifacts  | ALL artifacts
    | artifacts      | artifacts      |                |
    |                |                | Write:         | Write:
    | Write:         | Write:         | CONCLUSION     | (patterns to
    | CHALLENGE      | (outcome       |                |  knowledge base)
    |                |  determination)|                |
    v                v                v                v
─────────────────────────────────────────────────────────────────────────────

Cross-cutting artifacts written at any phase:
  LLM_REQUEST / LLM_RESPONSE    (every LLM call)
  PHASE_STATE                   (phase lifecycle)
  FINDING / ANNOTATION          (any persona observation)
  PERSONA_CONTRIBUTION          (any persona contribution)
```

---

### Permissions Matrix

| Artifact | -1: Chronicler | 0: Archivist | 1: Theorist | 2: Detective | 3: Logician | 4: Devil's Advocate | 5: Judge | 6: Synthesizer |
|----------|----------------|--------------|-------------|--------------|-------------|---------------------|----------|----------------|
| LOG_BUNDLE | W | R | R | R | R | R | R | R |
| MERGED_TIMELINE | W | R | R | R | R | R | R | R |
| BOARDREADER_ID | W | R | R | R | R | R | R | R |
| ERROR_CONTEXT | - | W | R | R | R | R | R | R |
| SOURCE_LOCATION | - | W | R | R | R | R | R | R |
| CALL_GRAPH | - | W | R | R | R | R | R | R |
| CODE_SNIPPET | - | W | R | R | R | R | R | R |
| FUNCTION_SUMMARY | - | W | R | R | R | R | R | R |
| HYPOTHESIS | - | - | W | R | R | R | R | R |
| EVIDENCE | - | - | - | RW | R | R | R | R |
| CAUSAL_CHAIN | - | - | - | - | W | R | R | R |
| CHALLENGE | - | - | - | - | - | W | R | R |
| CONCLUSION | - | - | - | - | - | - | - | W |

**Legend:** R = Read, W = Write, RW = Read+Write, - = No access

**Design Principles:**
1. **Write Once** -- Each investigation artifact type is written by exactly one phase
2. **Read Forward** -- Later phases can read artifacts from earlier phases
3. **No Cross-Phase Modification** -- Phases do not modify artifacts written by other phases
4. **Binder is the Single Source of Truth** -- All inter-phase data exchange happens through the binder

---

### Supporting Types Quick Reference

These models are not stored as standalone artifacts but are used as embedded fields within artifact types.

| Type | Used In | Key Fields |
|------|---------|------------|
| `CallerInfo` | `CallGraphNode.callers` | `caller_name`, `caller_file`, `caller_line`, `call_line`, `summary`, `body`, `relationship` |
| `CalleeInfo` | `CallGraphNode.callees` | `callee_name`, `callee_file`, `callee_line`, `callee_signature`, `summary`, `body`, `relationship` |
| `LogBundleErrorEntry` | `LogBundleArtifact.error_timeline` | `filename`, `line_number`, `timestamp`, `level`, `component`, `message`, `is_primary` |
| `LogBundleClue` | `LogBundleArtifact.clues` | `clue_type`, `description`, `source_file`, `relevance`, `suggested_search` |
| `BoardAnalysis` | `LogBundleArtifact.affected_boards` | `board_name`, `filename`, `role`, `failure_mode`, `key_error_message`, `source_location`, `error_count`, `warning_count` |
| `CascadeLink` | `LogBundleArtifact.cascade_chain` | `from_board`, `to_board`, `mechanism`, `evidence` |
| `MergedTimelineEntry` | `MergedTimelineArtifact.entries` | `timestamp`, `source_file`, `board_name`, `level`, `component`, `message`, `source_location` |
| `AuditLogEntry` | `WorkBinder._audit_log` | `persona_name`, `phase_number`, `timestamp`, `access_sequence`, `operation_type`, `artifact_type`, `method_name`, `result_count` |
| `ArtifactHistory` | `WorkBinder._history` | `artifact_id`, `modified_by`, `modified_at`, `action`, `changes` |

---

### Document Structure

| Chapter | Title | Content Summary |
|---------|-------|-----------------|
| [Ch. 1](agentic-workbinder-library-ch1-architecture.md) | Architecture & Core API | Design philosophy, Artifact base class, ArtifactType enum, WorkBinder core API, permissions model, history & audit system, state management, LLM tracking, evidence-hypothesis linking, artifact data flow |
| [Ch. 2](agentic-workbinder-library-ch2-context-artifacts.md) | Context Artifacts | ErrorContextArtifact, LogBundleArtifact, SourceLocationArtifact -- the foundational "what happened" inputs |
| [Ch. 3](agentic-workbinder-library-ch3-code-artifacts.md) | Code Knowledge Artifacts | CallGraphNode, CodeSnippet, FunctionSummaryArtifact -- derived intelligence about source code |
| [Ch. 4](agentic-workbinder-library-ch4-investigation-artifacts.md) | Investigation Artifacts | HypothesisArtifact, EvidenceArtifact, CausalChainArtifact, ChallengeArtifact, ConclusionArtifact -- the reasoning chain |
| [Ch. 5](agentic-workbinder-library-ch5-observation-artifacts.md) | Observation Artifacts | Finding, Annotation, PersonaContributionArtifact -- cross-cutting artifacts any persona can create |
| [Ch. 6](agentic-workbinder-library-ch6-infrastructure-artifacts.md) | Infrastructure Artifacts | InvestigationStateArtifact, PhaseStateArtifact, FlowConfigArtifact, LLMRequestArtifact, LLMResponseArtifact -- operational state |
| [Ch. 7](agentic-workbinder-library-ch7-tools-serialization.md) | Tools, Serialization & Parsing | BinderTools API, BinderSerializer, parser subsystem, BinderStore persistence |
| [Ch. 8](agentic-workbinder-library-ch8-api-integration.md) | API Integration & Testing | REST API endpoints, MCP server tools, session-to-binder state mapping, testing strategy |

---

> **Agentic WorkBinder Library** | [Agentic REST API Design](agentic-rest-service-design.md) | [Agentic Persona Library](agentic-persona-library.md)
