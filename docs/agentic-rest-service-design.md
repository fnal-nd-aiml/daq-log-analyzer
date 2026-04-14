# Agentic REST API Design Document

**artdaq Deep Investigation Agent — Complete API Redesign**

This document specifies the agentic REST API that replaces direct `InvestigationCoordinator` usage across all client interfaces (CLI, Slack, MCP, external). The API exposes individual investigation capabilities as session-based tools, enabling composable investigation workflows.

---

## Document Structure

| Chapter | Title | Content | Tools |
|---------|-------|---------|-------|
| [Chapter 1](agentic-rest-service-design-ch1-architecture.md) | Architecture & Session Management | Problem statement, target architecture, session lifecycle, SSE streaming, error handling, API client library, session endpoints | — |
| [Chapter 2](agentic-rest-service-design-ch2-log-analysis-tools.md) | Log Analysis Tools | Parse, search, contextualize, summarize, and correlate log data | `parse_logs`, `search_logs`, `get_log_context`, `get_log_summary`, `correlate_events` |
| [Chapter 3](agentic-rest-service-design-ch3-code-analysis-tools.md) | Code Analysis Tools | Find error origins, look up functions, trace call graphs, search symbols, summarize functions | `find_error_source`, `lookup_function`, `get_call_graph`, `summarize_function`, `search_code` |
| [Chapter 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md) | Knowledge & Finding Tools | Pattern matching, similar investigations, prior knowledge, findings, hypotheses | `match_pattern`, `find_similar_investigations`, `get_prior_knowledge`, `record_finding`, `record_hypothesis`, `update_hypothesis`, `get_findings_summary` |
| [Chapter 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md) | Pipeline, Expert & Admin Tools | Full investigation pipeline, expert panel Q&A, knowledge base admin | `investigate`, `investigate_stream`, `ask_experts`, `init_knowledge_base`, `sync_sources` |
| [Chapter 6](agentic-rest-service-design-ch6-client-refactoring.md) | Client Refactoring Guide | API client library design, CLI/Slack/MCP migration with before/after code | — |
| [Chapter 7](agentic-rest-service-design-ch7-testing-strategy.md) | Testing Strategy | Per-tool unit tests, integration tests, SSE stream testing, client library testing | — |

---

## Tool Quick Reference

All tools are invoked as `POST /api/v1/agent/tools/{tool_name}` within a session context.

### Log Analysis
| Tool | Purpose | Chapter |
|------|---------|---------|
| `parse_logs` | Parse raw log content into structured entries | [Ch. 2](agentic-rest-service-design-ch2-log-analysis-tools.md#tool-1-parse_logs) |
| `search_logs` | Search parsed logs by pattern, severity, component, time range | [Ch. 2](agentic-rest-service-design-ch2-log-analysis-tools.md#tool-2-search_logs) |
| `get_log_context` | Get N lines before/after a specific log line | [Ch. 2](agentic-rest-service-design-ch2-log-analysis-tools.md#tool-3-get_log_context) |
| `get_log_summary` | Aggregated statistics: error counts, timeline, affected components | [Ch. 2](agentic-rest-service-design-ch2-log-analysis-tools.md#tool-4-get_log_summary) |
| `correlate_events` | Cross-component event correlation in time window | [Ch. 2](agentic-rest-service-design-ch2-log-analysis-tools.md#tool-5-correlate_events) |

### Code Analysis
| Tool | Purpose | Chapter |
|------|---------|---------|
| `find_error_source` | Find where an error message originates in source code | [Ch. 3](agentic-rest-service-design-ch3-code-analysis-tools.md#tool-6-find_error_source) |
| `lookup_function` | Get function details from the code index | [Ch. 3](agentic-rest-service-design-ch3-code-analysis-tools.md#tool-7-lookup_function) |
| `get_call_graph` | Get callers and callees of a function | [Ch. 3](agentic-rest-service-design-ch3-code-analysis-tools.md#tool-8-get_call_graph) |
| `summarize_function` | Summarize a function using LLM-based analysis | [Ch. 3](agentic-rest-service-design-ch3-code-analysis-tools.md#tool-9-summarize_function) |
| `search_code` | Search code symbols by name or pattern | [Ch. 3](agentic-rest-service-design-ch3-code-analysis-tools.md#tool-10-search_code) |

### Knowledge
| Tool | Purpose | Chapter |
|------|---------|---------|
| `match_pattern` | Match error against learned patterns | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-10-match_pattern) |
| `find_similar_investigations` | Find similar past investigation cases | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-11-find_similar_investigations) |
| `get_prior_knowledge` | Get combined prior knowledge bundle | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-12-get_prior_knowledge) |

### Finding & Hypothesis
| Tool | Purpose | Chapter |
|------|---------|---------|
| `record_finding` | Record an intermediate finding with evidence | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-13-record_finding) |
| `record_hypothesis` | Record a root cause hypothesis | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-14-record_hypothesis) |
| `update_hypothesis` | Update hypothesis score based on evidence | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-15-update_hypothesis) |
| `get_findings_summary` | Get all findings and hypotheses in session | [Ch. 4](agentic-rest-service-design-ch4-knowledge-finding-tools.md#tool-16-get_findings_summary) |

### Pipeline & Expert
| Tool | Purpose | Chapter |
|------|---------|---------|
| `investigate` | Run full 7-phase investigation pipeline (synchronous) | [Ch. 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-17-investigate) |
| `investigate_stream` | Run full pipeline with SSE progress streaming | [Ch. 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-18-investigate_stream) |
| `ask_experts` | Ask expert panel a DAQ-related question | [Ch. 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-19-ask_experts) |

### Admin
| Tool | Purpose | Chapter |
|------|---------|---------|
| `init_knowledge_base` | Initialize knowledge base and sync sources | [Ch. 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-20-init_knowledge_base) |
| `sync_sources` | Sync configured source repositories | [Ch. 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-21-sync_sources) |

---

## Session Workflow

```
1. POST /api/v1/agent/sessions              → Create session
2. POST /api/v1/agent/tools/parse_logs      → Parse log file(s)
3. POST /api/v1/agent/tools/search_logs     → Search for patterns
4. POST /api/v1/agent/tools/find_error_source → Locate in source code
5. POST /api/v1/agent/tools/record_finding  → Record what was found
6. POST /api/v1/agent/tools/record_hypothesis → Record root cause guess
7. ... (continue with any tools in any order)
8. DELETE /api/v1/agent/sessions/{id}        → Close session
```

---

## URL Prefix

All agentic endpoints live under `/api/v1/agent/`:

| Path Pattern | Purpose |
|-------------|---------|
| `POST /api/v1/agent/sessions` | Create session |
| `GET /api/v1/agent/sessions/{id}` | Get session state |
| `DELETE /api/v1/agent/sessions/{id}` | Close session |
| `GET /api/v1/agent/tools` | List all registered tools |
| `POST /api/v1/agent/tools/{tool_name}` | Invoke a tool (including `investigate_stream`, `ask_experts`) |
