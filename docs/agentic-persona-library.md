> **Agentic Persona Library** | [Agentic REST API Design](agentic-rest-service-design.md)

---

# Agentic Persona Library

## Table of Contents

---

### Document Purpose

This is a companion document to the [Agentic REST API Design Document](agentic-rest-service-design.md). While that document specifies 21 composable session-based tools exposed by the REST API, this document details the **persona system** that powers the LLM-backed tools (`investigate`, `investigate_stream`, `ask_experts`). It documents how each persona maps to API tools, interacts with session state, emits SSE events, and participates in expert panel Q&A.

The persona system is the intelligence layer of the artdaq Deep Investigation Agent. Personas are not merely prompt templates -- they are structured abstractions with defined lifecycles (`prepare`/`contribute`/`reflect`), collaboration protocols (`critique`/`endorse`/`respond_to`), and orchestration mechanics (EvidenceOrchestrator, RetrievalOrchestrator). Each persona owns a specific phase of the investigation pipeline, contributes artifacts to the shared WorkBinder, and can participate in expert panel discussions via the PanelOrchestrator.

This document covers the `BasePersona` ABC, the `InvestigationContext` shared state, all collaboration models, the orchestration layer, the capability registry, and the prompt architecture -- everything needed to understand, extend, or test the persona system.

---

### Persona Quick Reference

| Phase | Name | Role | Uses LLM | Primary API Tools | Chapter |
|-------|------|------|----------|-------------------|---------|
| -1 | Chronicler | Multi-File Log Triage | Yes | `investigate`, `investigate_stream` | [Ch. 2](agentic-persona-library-ch2-pipeline-personas.md) |
| 0 | Archivist | Prior Knowledge Retrieval | Yes | `investigate`, `investigate_stream`, `get_prior_knowledge`, `match_pattern`, `find_similar_investigations` | [Ch. 2](agentic-persona-library-ch2-pipeline-personas.md) |
| 1 | Theorist | Hypothesis Generation | Yes | `investigate`, `investigate_stream`, `ask_experts` | [Ch. 2](agentic-persona-library-ch2-pipeline-personas.md) |
| 2 | Detective | Evidence Seeking | Yes | `investigate`, `investigate_stream`, `ask_experts` | [Ch. 2](agentic-persona-library-ch2-pipeline-personas.md) |
| 3 | Logician | Causal Chain Construction | Yes | `investigate`, `investigate_stream`, `ask_experts` | [Ch. 3](agentic-persona-library-ch3-analysis-personas.md) |
| 4 | Skeptic | Adversarial Review | Yes | `investigate`, `investigate_stream`, `ask_experts` | [Ch. 3](agentic-persona-library-ch3-analysis-personas.md) |
| 5 | Judge | Insufficiency Check | Yes | `investigate`, `investigate_stream`, `ask_experts` | [Ch. 3](agentic-persona-library-ch3-analysis-personas.md) |
| 6 | Synthesizer | Final Synthesis | Yes | `investigate`, `investigate_stream`, `ask_experts` | [Ch. 3](agentic-persona-library-ch3-analysis-personas.md) |
| 7 | Learner | Pattern Learning | Yes | `investigate`, `investigate_stream` | [Ch. 4](agentic-persona-library-ch4-learning-personas.md) |
| -- | Reviewer | Inline Feedback | No | (future) | [Ch. 4](agentic-persona-library-ch4-learning-personas.md) |
| -- | Navigator | Tool Selection Guide | No | (proposed) | [Ch. 4](agentic-persona-library-ch4-learning-personas.md) |

---

### Tool-to-Persona Mapping Matrix

The REST API exposes 21 tools. Most are **tool-only** -- they execute deterministic operations (parsing, searching, indexing) with no persona involvement. Three tools are **persona-backed** -- they invoke the investigation pipeline or expert panel, which delegates to one or more personas.

| API Tool | Category | Persona(s) | Notes |
|----------|----------|------------|-------|
| `parse_logs` | Log Analysis | -- | Tool-only, no persona |
| `search_logs` | Log Analysis | -- | Tool-only, no persona |
| `get_log_context` | Log Analysis | -- | Tool-only, no persona |
| `get_log_summary` | Log Analysis | -- | Tool-only, no persona |
| `correlate_events` | Log Analysis | -- | Tool-only, no persona |
| `find_error_source` | Code Analysis | Archivist (indirect) | Source location used by Archivist's RetrievalOrchestrator |
| `lookup_function` | Code Analysis | -- | Tool-only, used as evidence by Detective |
| `get_call_graph` | Code Analysis | Archivist (indirect) | Call graphs enriched by Archivist |
| `search_code` | Code Analysis | -- | Tool-only, used as evidence by Detective |
| `match_pattern` | Knowledge | Archivist | Pattern matching in Phase 0 |
| `find_similar_investigations` | Knowledge | Archivist | Similar case lookup in Phase 0 |
| `get_prior_knowledge` | Knowledge | Archivist | Bundles Phase 0 output |
| `record_finding` | Finding | -- | Tool-only, stores in session/binder |
| `record_hypothesis` | Finding | -- | Tool-only, stores in session/binder |
| `update_hypothesis` | Finding | -- | Tool-only, stores in session/binder |
| `get_findings_summary` | Finding | -- | Tool-only, reads from session/binder |
| `investigate` | Pipeline | All pipeline personas (Phases -1 to 7) | Full pipeline execution |
| `investigate_stream` | Pipeline | All pipeline personas (Phases -1 to 7) | Streaming pipeline with SSE |
| `ask_experts` | Expert | Panel subset (varies by question type) | Expert panel Q&A |
| `init_knowledge_base` | Admin | -- | Administrative, no persona |
| `sync_sources` | Admin | -- | Administrative, no persona |

---

### Document Structure

| Chapter | Title | Content Summary |
|---------|-------|-----------------|
| [Ch. 1](agentic-persona-library-ch1-architecture.md) | Architecture & Foundations | BasePersona ABC, InvestigationContext, collaboration models, orchestration layer, capability registry, session integration, SSE mapping |
| [Ch. 2](agentic-persona-library-ch2-pipeline-personas.md) | Pipeline Personas (Data Gathering) | Chronicler, Archivist, Theorist, Detective -- the four personas that collect and generate input data |
| [Ch. 3](agentic-persona-library-ch3-analysis-personas.md) | Analysis Personas (Reasoning) | Logician, Skeptic, Judge, Synthesizer -- the four personas that reason over collected data |
| [Ch. 4](agentic-persona-library-ch4-learning-personas.md) | Learning & Feedback Personas | Learner, Reviewer, Navigator (proposed) -- personas for pattern extraction, feedback, and tool guidance |
| [Ch. 5](agentic-persona-library-ch5-expert-panel.md) | Expert Panel & Collaboration | PanelOrchestrator, question classification, persona selection, voting, deliberation, synthesis |
| [Ch. 6](agentic-persona-library-ch6-prompt-architecture.md) | Prompt Architecture | PromptLoader, type-safe enums, safe formatting, template structure, per-persona prompt design |
| [Ch. 7](agentic-persona-library-ch7-testing-strategy.md) | Testing & Validation | Per-persona tests, orchestrator tests, expert panel tests, prompt regression testing |

---

### Session Workflow from the Persona Perspective

The following diagram shows how a single `investigate_stream` request flows through the persona system. The session store holds accumulated state; the `InvestigationCoordinator` orchestrates persona execution; each persona emits SSE events as it progresses.

```
Client Request
  |
  v
POST /api/v1/agent/tools/investigate_stream
  |
  v
+----------------------------------------------------------+
|                     Session Store                          |
|  session_id -> { logs, findings, hypotheses, result }     |
+----------------------------+-----------------------------+
                             |
                             v
+----------------------------------------------------------+
|                InvestigationCoordinator                    |
|                                                           |
|  Phase -1: Chronicler  -----> SSE: phase_start/-1         |
|       |    (multi-file triage, if --files)                 |
|       v                                                   |
|  Phase 0: Archivist  -------> SSE: phase_start/0          |
|       |    RetrievalOrchestrator                           |
|       |    -> patterns, similar cases, source locations    |
|       v                                                   |
|  Phase 1: Theorist  --------> SSE: phase_start/1          |
|       |    LLM hypothesis generation                      |
|       |    -> ranked hypotheses in binder                  |
|       v                                                   |
|  Phase 2: Detective  -------> SSE: phase_start/2          |
|       |    EvidenceOrchestrator (up to 10 iterations)      |
|       |    -> evidence items, updated scores               |
|       v                                                   |
|  Phase 3: Logician  --------> SSE: phase_start/3          |
|       |    LLM causal chain construction                   |
|       |    -> causal chains in binder                      |
|       v                                                   |
|  Phase 4: Skeptic -----------> SSE: phase_start/4          |
|       |    LLM adversarial challenges                      |
|       |    -> challenges in binder                         |
|       v                                                   |
|  Phase 5: Judge  -----------> SSE: phase_start/5          |
|       |    LLM outcome assessment                         |
|       |    -> outcome determination                        |
|       v                                                   |
|  Phase 6: Synthesizer  -----> SSE: phase_start/6          |
|       |    LLM final synthesis                            |
|       |    -> InvestigationResult                          |
|       v                                                   |
|  Phase 7: Learner  ---------> SSE: phase_complete/7       |
|       |    LLM pattern extraction                         |
|       |    -> patterns stored in knowledge base            |
|       v                                                   |
|  SSE: complete -> full InvestigationResult                 |
+----------------------------------------------------------+
```

Each persona follows the `prepare -> contribute -> reflect` lifecycle within its phase. The `PersonaExecutor` (or `UnifiedPersonaExecutor`) wraps this lifecycle and maps the persona's `Contribution` output to the pipeline's typed data contracts (`prior_knowledge`, `hypotheses`, `evidence`, `causal_chains`, `challenges`, `outcome`, `result`). All artifacts are stored in the shared `WorkBinder`, which serves as the cross-phase artifact store within the session.

---

> **Agentic Persona Library** | [Agentic REST API Design](agentic-rest-service-design.md)
