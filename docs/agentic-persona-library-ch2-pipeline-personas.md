> **Agentic Persona Library** | [<- Architecture](agentic-persona-library-ch1-architecture.md) | [Table of Contents](agentic-persona-library.md) | [Next: Analysis Personas ->](agentic-persona-library-ch3-analysis-personas.md)

---

# Chapter 2: Pipeline Personas -- Data Gathering

This chapter covers the four upstream personas that gather raw material for the investigation: the **Chronicler** (Phase -1), **Archivist** (Phase 0), **Theorist** (Phase 1), and **Detective** (Phase 2). These personas are data-intensive, rely on orchestration layers for complex retrieval and generation logic, and produce the evidence and hypotheses that downstream personas consume.

Together, they form a progressive refinement pipeline. Raw log files enter at the top and are successively transformed into a merged timeline, enriched prior knowledge, ranked hypotheses, and finally a scored evidence collection. Each persona reads the artifacts produced by its predecessor and writes new artifacts for its successor.

```
Log Files ──► Chronicler ──► Merged Timeline
                                    │
                                    ▼
                              Archivist ──► Prior Knowledge
                                    │         (patterns, similar cases,
                                    │          source locations, code hints)
                                    ▼
                              Theorist ──► Ranked Hypotheses
                                    │         (from 5 tiers)
                                    ▼
                              Detective ──► Evidence Collection
                                              (items, gap analysis,
                                               quality scores)
```

Each persona section below follows the standard 11-section template established in [Chapter 1](agentic-persona-library-ch1-architecture.md).

---

## Chronicler (Phase -1)

### 1. Identity

| Field | Value |
|-------|-------|
| **Phase** | -1 |
| **Name** | Chronicler |
| **Role** | Multi-File Log Triage |
| **Color** | `bright_blue` |
| **Thinking Phrase** | `"Reading the chronicles..."` |
| **Prompt Key** | `chronicler` |
| **Uses LLM** | Yes |

**Traits:** chronological, causal, systematic, concise

**Thinking Style:** Read events in time order across all sources, identify which error came first and caused others. Temporal analysis -- merges multi-file logs chronologically, identifies the primary trigger error across files, maps the error cascade, and produces a structured narrative for downstream phases.

### 2. Responsibilities

**Pipeline Role.** The Chronicler is a conditional pre-phase that only runs when the `--files` flag provides multiple log files. It parses all source files, merges their entries into a single chronological timeline, calls the LLM to interpret the unified narrative, identifies the primary trigger error, maps the cascade across boards, and produces a structured `LogBundleArtifact` with errors and clues for the Archivist.

**Expert Panel Role.** The Chronicler is not typically included in `ask_experts` panels. It is a pre-processing persona that runs before the main investigation pipeline.

**Artifacts Produced:**

| Artifact | Type | Description |
|----------|------|-------------|
| Merged timeline | `str` | Chronologically ordered log entries annotated with source board identifiers |
| Primary error identification | `LogBundleErrorEntry` | The first error in the timeline that triggered the cascade |
| File-to-component mapping | `list[dict]` | Filename to error count mapping for each source file |
| `LOG_BUNDLE` binder artifact | `LogBundleArtifact` | Full structured artifact with narrative, errors, clues |
| Clues for Archivist | `list[LogBundleClue]` | Typed clues with suggested searches for guided retrieval |

**Artifacts Consumed:**

| Artifact | Source | Description |
|----------|--------|-------------|
| Raw source files | `context.source_files` (`list[SourceFile]`) | Multi-file log content with filenames and error line hints |

### 3. Tool Mapping

| API Tool | Invokes Chronicler? | Capabilities Used |
|----------|---------------------|-------------------|
| `investigate` | Yes (when `source_files > 1`) | Log parsing, temporal ordering, LLM narrative analysis |
| `investigate_stream` | Yes (when `source_files > 1`) | Log parsing, temporal ordering, LLM narrative analysis |
| All others | No | -- |

Cross-reference: [investigate](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-17-investigate)

### 4. Implementation

**Class:** `ChroniclerPersona` in `srcs/persona/chronicler.py`

**Structured Response Model:**

```python
class ChroniclerNarrativeResponse(BaseModel):
    annotated_narrative: str       # 2-4 paragraph narrative of the merged timeline
    primary_error_file: str        # Filename containing the primary/root error
    primary_error_message: str     # The exact error message that triggered the cascade
    primary_error_line: int | None # Line number of the primary error if known
    cascade_description: str       # How the primary error cascaded to other boards
    clues: list[dict[str, Any]]    # Clues for the Archivist to investigate
    affected_boards: list[str]     # Board identifiers affected by the cascade
    cascade_chain: list[str]       # Ordered chain of cascade propagation
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `prepare` | `async def prepare(self, context: InvestigationContext) -> None` | No-op for Chronicler |
| `contribute` | `async def contribute(self, context: InvestigationContext) -> Contribution` | Main entry point. Skips if `source_files` is `None` or has only one file. Otherwise: parses all files via `parse_log_content`, validates file content quality, sorts entries chronologically, builds merged timeline string, calls LLM with `LOG_BUNDLE_ANALYSIS` prompt, parses response into `ChroniclerNarrativeResponse`, creates `LOG_BUNDLE` binder artifact, locates primary error `Log` object in source files |
| `reflect` | `async def reflect(self, context: InvestigationContext) -> Reflection` | Reports merge statistics and timestamp accuracy uncertainties |
| `answer_question` | `async def answer_question(self, context: QuestionContext) -> Contribution` | Returns generic answer -- Chronicler is not a Q&A persona |
| `_validate_file_content_quality` | `@staticmethod (logs, filename) -> bool` | Detects HTML or non-log content by checking structured vs. fallback entry ratios |
| `_heuristic_analysis` | `(all_errors, source_files) -> ChroniclerNarrativeResponse` | Fallback when LLM fails: uses first chronological error as primary |
| `_identify_boardreaders` | `async def _identify_boardreaders(self, context, timeline) -> BoardReaderIdentification` | Step 1.5: LLM identifies BoardReader types, components, and error messages from the timeline |
| `_select_primary_error_llm` | `async def _select_primary_error_llm(self, context, errors, narrative) -> PrimaryErrorSelection` | Step 2.5: LLM selects the primary error from candidate errors |
| `_find_primary_in_sources` | `(source_files, primary_filename, primary_message) -> tuple[Log, list[Log]]` | Locates the primary error `Log` object and its context in the original source files |

**Execution Flow:**

```
contribute()
  ├── Check source_files count (skip if <= 1)
  ├── For each SourceFile:
  │     ├── parse_log_content(sf.content)
  │     ├── _validate_file_content_quality(logs, sf.filename)
  │     └── Annotate entries with (timestamp, filename, log_entry)
  ├── Sort all entries chronologically
  ├── Build merged timeline string with [board] prefixes
  ├── Extract all ERROR/FATAL entries → all_errors
  ├── Truncate timeline if > 30,000 chars (_truncate_timeline)
  ├── Step 1: Timeline Extraction (LLM)
  │     ├── user_prompt = get_user_prompt(UserPromptType.LOG_TIMELINE_EXTRACTION)
  │     └── _call_llm_structured(context, prompt, TimelineExtractionResponse)
  ├── Step 1.5: BoardReader Identification (LLM)
  │     ├── user_prompt = get_user_prompt(UserPromptType.BOARDREADER_IDENTIFICATION)
  │     └── _identify_boardreaders(context) → BoardReaderIdentification
  ├── Step 2: Narrative Analysis (LLM)
  │     ├── user_prompt = get_user_prompt(UserPromptType.LOG_BUNDLE_ANALYSIS).format(...)
  │     └── _call_llm_structured(context, prompt, ChroniclerNarrativeResponse)
  ├── Step 2.5: Primary Error Selection (LLM)
  │     ├── user_prompt = get_user_prompt(UserPromptType.PRIMARY_ERROR_SELECTION)
  │     └── _select_primary_error_llm(context) → PrimaryErrorSelection
  ├── On LLM failure → _heuristic_analysis(all_errors, source_files)
  ├── Build LogBundleErrorEntry for primary error
  ├── Build LogBundleClue list from response clues
  ├── binder.add_log_bundle(...)  → artifact_id
  ├── _find_primary_in_sources(...)  → (primary_log, primary_context)
  └── Return Contribution(persona_id="chronicler", phase=-1, ...)
```

**Content Dict Keys:**

| Key | Type | Description |
|-----|------|-------------|
| `log_bundle_id` | `str` | Binder artifact ID for the LOG_BUNDLE |
| `file_count` | `int` | Number of source files analyzed |
| `total_errors` | `int` | Total ERROR/FATAL entries across all files |
| `primary_error` | `Log` | (optional) Primary error Log object |
| `primary_context` | `list[Log]` | (optional) Context logs around primary error |
| `primary_file` | `str` | (optional) Filename containing primary error |
| `skipped` | `bool` | True if phase was skipped (single file or no files) |

### 5. Prompt Anatomy

| Prompt | Template Path | Type |
|--------|---------------|------|
| System | `srcs/prompts/templates/system/chronicler.md` | `SystemPromptType.CHRONICLER` |
| User (Step 1) | `srcs/prompts/templates/user/log_timeline_extraction.md` | `UserPromptType.LOG_TIMELINE_EXTRACTION` |
| User (Step 1.5) | `srcs/prompts/templates/user/boardreader_identification.md` | `UserPromptType.BOARDREADER_IDENTIFICATION` |
| User (Step 2) | `srcs/prompts/templates/user/log_bundle_analysis.md` | `UserPromptType.LOG_BUNDLE_ANALYSIS` |
| User (Step 2.5) | `srcs/prompts/templates/user/primary_error_selection.md` | `UserPromptType.PRIMARY_ERROR_SELECTION` |

**Placeholders:**

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `{file_count}` | `str(len(source_files))` | Number of log files |
| `{file_list}` | Formatted list | Each file with its error count |
| `{merged_timeline}` | Merged string | Chronologically sorted, board-annotated log lines |
| `{total_errors}` | `str(len(all_errors))` | Total error count across all files |

**Include Dependencies:** None (standalone prompts).

### 6. Session State Interaction

| Operation | Field | Description |
|-----------|-------|-------------|
| Reads | `context.source_files` | List of `SourceFile` objects with content and metadata |
| Writes | `context.error` | Not directly -- primary error is returned in `Contribution.content` for the coordinator to set |
| Writes | `context.context_logs` | Not directly -- primary context is returned in `Contribution.content` |
| Binder | `binder.add_log_bundle(...)` | Creates `LOG_BUNDLE` artifact with full analysis |
| Binder | `_call_llm_structured(...)` | Records LLM request/response artifacts via `BasePersona` helper |

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: -1, phase_name: "Multi-File Log Triage", message: "Reading the chronicles..."}` | Phase begins |
| `llm_request` | `{phase: -1, model_name: ..., system_prompt_length: N, user_prompt_length: N}` | LLM call for log bundle analysis |
| `llm_response` | `{phase: -1, response_model: "ChroniclerNarrativeResponse", parse_failed: bool}` | LLM response received |
| `phase_complete` | `{phase: -1, data: {files_analyzed: N, primary_error: "...", total_errors: N}}` | Phase done |

### 8. Expert Panel Behavior

Not typically included in expert panels. The Chronicler is a pre-processing persona that runs before the main pipeline. Its `answer_question()` method returns a low-confidence generic response.

### 9. Configuration and Tuning

| Parameter | Value | Notes |
|-----------|-------|-------|
| Activation condition | `len(source_files) > 1` | Only runs for multi-file investigations |
| Max timeline chars | 30,000 | Truncation threshold for LLM context window |
| Timeline truncation strategy | Keep error lines +/- 3 context lines, first 20, last 20 | Prioritizes ERROR/FATAL entries |
| Content quality threshold | 0 structured + >10 fallback entries | Detects HTML/non-log content |
| LLM temperature | Default from provider config | No persona-specific override |
| Confidence score | 0.7 (primary found) / 0.4 (no primary) / 0.1 (all files skipped) | Based on analysis outcome |

### 10. Error Handling and Fallbacks

| Failure Mode | Recovery Strategy |
|-------------|-------------------|
| LLM call fails | `_heuristic_analysis()`: uses first chronological error as primary, generates basic clues |
| LLM parse fails | Same as LLM failure -- `_heuristic_analysis()` fallback |
| All files contain HTML/non-log content | Returns skipped contribution with `reason` and `skipped_files` |
| No parseable log entries | Returns skipped contribution with confidence 0.1 |
| Single source file or no source files | Phase is skipped entirely (returns `skipped: True` contribution) |
| Timeline exceeds context window | `_truncate_timeline()` preserves error lines and surrounding context |

### 11. Testing Contract

| Test | Description |
|------|-------------|
| `test_chronicler_merges_multiple_files` | 3 source files with interleaved timestamps produce a merged timeline in chronological order |
| `test_chronicler_identifies_primary_error` | Primary error correctly identified from cross-file analysis |
| `test_chronicler_skips_single_file` | Single source file produces `skipped: True` contribution |
| `test_chronicler_skips_no_files` | No source files produces `skipped: True` contribution |
| `test_chronicler_llm_fallback` | LLM raises exception; heuristic analysis succeeds with first error as primary |
| `test_chronicler_validates_content_quality` | HTML file content (0 structured, >10 fallback) is rejected |
| `test_chronicler_creates_log_bundle_artifact` | Binder receives `LOG_BUNDLE` artifact with correct structure |
| `test_chronicler_truncates_long_timeline` | Timeline exceeding 30,000 chars is truncated preserving error context |
| `test_chronicler_extracts_board_names` | Various filename patterns produce correct short board identifiers |

**Mock Requirements:** `LLMProvider` (for `generate_structured`), `WorkBinder` (for `add_log_bundle`), `SourceFile` list with `content`, `filename`, and `error_line` attributes.

---

## Archivist (Phase 0)

### 1. Identity

| Field | Value |
|-------|-------|
| **Phase** | 0 |
| **Name** | Archivist |
| **Role** | Prior Knowledge Retrieval |
| **Color** | `blue` |
| **Thinking Phrase** | `"Searching the archives..."` |
| **Prompt Key** | `archivist` |
| **Uses LLM** | Yes |

**Traits:** methodical, thorough, historical, organized, pattern-seeking

**Thinking Style:** Systematic retrieval -- searches through historical records, identifies relevant patterns and precedents, connects current issues to past cases. The Archivist approaches each investigation by first checking what the system already knows before generating new analysis.

### 2. Responsibilities

**Pipeline Role.** The Archivist retrieves all prior knowledge that informs downstream phases. This includes: querying the knowledge base for matching error patterns, finding similar past investigations, locating the error in source code via the `RetrievalOrchestrator`, extracting diagnostic hints from code comments, tracing dataflow upstream, enriching call graphs with LLM summaries, parsing numeric values from error messages, and consuming clues from the Chronicler's `LOG_BUNDLE` artifact when available.

The Archivist also produces enhanced artifacts: `ResolutionDigest` (what fixed similar cases), `ConfigurationContext` (relevant config parameters), and `DiagnosticHistory` (success rate for this error type). Finally, the LLM is called to summarize all findings into a `PriorKnowledgeSummary` with relevance assessments, key insights, and recommended focus areas.

**Expert Panel Role.** Provides source code references and historical context for Q&A. Participates in panels for WHY, TROUBLESHOOT, and WHAT_IS question types.

**Artifacts Produced:**

| Artifact | Type | Description |
|----------|------|-------------|
| Prior knowledge bundle | `PriorKnowledge` | Matched patterns, similar investigations, recommended hypotheses, recommended queries, source locations |
| Resolution digest | `list[ResolutionDigest]` | What fixed similar cases, with category and applicability notes |
| Configuration context | `ConfigurationContext` | Relevant config parameters extracted from logs |
| Diagnostic history | `DiagnosticHistory` | Historical success rate for this error type |
| LLM summary | `PriorKnowledgeSummary` | Relevance assessment, key insights, recommended focus areas |
| Source location artifacts | Binder `SourceLocation` | File path, line number, function body, match score |
| Call graph artifacts | Binder `CallGraph` | Center function, callers, callees, ASCII diagram |
| Function summary artifacts | Binder `FunctionSummary` | Purpose, mechanism, data flow, error paths per function |
| Code snippet artifacts | Binder `CodeSnippet` | Full function bodies for error-related code |
| Numeric evidence artifacts | Binder `Evidence` | Timestamp gaps, timeout calculations, data gap analysis |

**Artifacts Consumed:**

| Artifact | Source | Description |
|----------|--------|-------------|
| Trigger error | `context.error` (`Log`) | The primary error to investigate |
| Context logs | `context.context_logs` (`list[Log]`) | Surrounding log entries |
| LOG_BUNDLE | Binder (from Chronicler) | Multi-file analysis clues for guided retrieval |

### 3. Tool Mapping

| API Tool | Invokes Archivist? | Capabilities Used |
|----------|---------------------|-------------------|
| `investigate` | Yes (Phase 0) | Full retrieval pipeline |
| `investigate_stream` | Yes (Phase 0) | Full retrieval + SSE events |
| `get_prior_knowledge` | Yes (direct) | Full retrieval |
| `match_pattern` | Partial | Pattern matching only |
| `find_similar_investigations` | Partial | Similar case lookup only |
| `find_error_source` | Indirect | Source location used by `RetrievalOrchestrator` |
| `get_call_graph` | Indirect | Call graphs enriched by `RetrievalOrchestrator` |
| `ask_experts` | Yes (for WHY, TROUBLESHOOT, WHAT_IS questions) | Source code references, known patterns |

Cross-reference: [get_prior_knowledge](agentic-rest-service-design-ch4-knowledge-finding-tools.md), [match_pattern](agentic-rest-service-design-ch4-knowledge-finding-tools.md)

### 4. Implementation

**Class:** `ArchivistPersona` in `srcs/persona/archivist.py`

**Orchestrator:** `RetrievalOrchestrator` in `srcs/persona/orchestration/retrieval_orchestrator.py`

**Structured Response Models:**

```python
class PriorKnowledgeSummary(BaseModel):
    relevance_assessment: dict[str, str]      # Ratings for patterns, similar_cases, source_locations
    key_insights: list[str]                   # Key insights from prior knowledge
    recommended_focus_areas: list[str]        # Where to focus the investigation
    data_flow_summary: str                    # Summary of data flow around the error
    overall_confidence: str                   # high/medium/low
    confidence_reasoning: str                 # Explanation for the confidence level

class ParsedErrorContext(BaseModel):          # From RetrievalOrchestrator
    function_name: str                        # Function where error occurred
    error_type: str                           # timeout, buffer_overflow, data_gap, etc.
    numeric_values: list[ParsedNumericValue]   # Extracted numeric values with meanings
    timestamp_analysis: str                   # Timestamp relationship analysis
    timeout_analysis: str                     # Timeout value analysis
    data_gap_description: str                 # Data gap or latency description
    likely_cause: str                         # Most likely cause from numeric analysis
    confidence: float                         # 0.0-1.0
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `def __init__(self) -> None` | Initializes `_orchestrator`, `_retrieved_prior`, `_summary` to None |
| `prepare` | `async def prepare(self, context: InvestigationContext) -> None` | Creates `RetrievalOrchestrator` with KB, source_roots, code_index, chroma_store, llm_provider. Creates `NullKB` fallback if no KB available |
| `contribute` | `async def contribute(self, context: InvestigationContext) -> Contribution` | Retrieves prior knowledge, enriches from LOG_BUNDLE, extracts enhanced artifacts (resolutions, config, diagnostic history), stores in context, optionally summarizes with LLM |
| `_retrieve_prior_knowledge` | `async def _retrieve_prior_knowledge(self, context) -> PriorKnowledge` | Delegates to `orchestrator.retrieve(error, context_logs, binder)`. Returns empty PriorKnowledge on failure |
| `_enrich_from_log_bundle` | `def _enrich_from_log_bundle(self, prior, log_bundle) -> None` | Converts Chronicler clues to recommended hypotheses and queries |
| `_summarize_with_llm` | `async def _summarize_with_llm(self, context, prior) -> PriorKnowledgeSummary` | Calls `_call_llm_structured` with `PRIOR_KNOWLEDGE_SUMMARY` prompt |
| `_extract_resolutions` | `def _extract_resolutions(self, similar_investigations) -> list[ResolutionDigest]` | Infers resolution category and action from root cause descriptions |
| `_analyze_configuration` | `def _analyze_configuration(self, error, context_logs, similar) -> ConfigurationContext` | Regex-based extraction of config parameters from log text |
| `_get_diagnostic_history` | `def _get_diagnostic_history(self, error, similar) -> DiagnosticHistory` | Calculates resolution rate, common root causes, avg confidence |
| `_calculate_confidence` | `def _calculate_confidence(self, prior) -> float` | 0.3 base, boosted by pattern matches, source locations, similar cases, authoritative hints. Capped at 0.95 |
| `answer_question` | `async def answer_question(self, context: QuestionContext) -> Contribution` | Provides historical context based on question keywords (BoardReader, EventBuilder, timeout, config) |
| `critique` | `async def critique(self, contribution) -> Critique` | Critiques claims of uniqueness without archival verification; flags high confidence without historical validation |
| `endorse` | `async def endorse(self, contribution) -> bool` | Endorses contributions that reference patterns, historical precedent, or have confidence > 0.6 |

**RetrievalOrchestrator Execution Flow:**

```
orchestrator.retrieve(error, context_logs, binder)
  ├── kb.get_prior_knowledge(error, context_logs)  → base PriorKnowledge
  ├── _parse_error_numeric_context(error.message, binder)
  │     ├── NumericExtractor.analyze(error.message)  → regex values
  │     ├── LLM: generate_structured(ParsedErrorContext)  → semantic analysis
  │     ├── _store_parsed_context_in_binder()  → Finding artifact
  │     ├── _inject_numeric_evidence()  → MODERATE Evidence artifacts
  │     └── _generate_hypotheses_from_numeric_analysis()  → RecommendedHypothesis list
  ├── _find_error_source(error)
  │     ├── CodeIndex.find_function() for extracted function names
  │     └── Fallback: SourceLocator.find_source(error.message)
  ├── _generate_queries_from_locations()  → function_lookup, class_lookup queries
  ├── _extract_code_hints(source_locations)
  │     ├── CodeHintExtractor.find_explicit_cause_hints()  → authoritative
  │     ├── CodeHintExtractor.find_causal_hints()  → causal
  │     └── CodeHintExtractor.extract_hints()  → general
  ├── _generate_hypotheses_from_hints(hints, error.message)
  │     ├── LLM: generate_structured(InterpretedHints)  → filtered, rewritten
  │     └── Fallback: _generate_hypotheses_from_hints_rules()
  ├── _generate_dataflow_queries(source_locations)
  │     └── DataflowTracer.trace_from_error()  → upstream queries
  ├── _enrich_with_call_graph_context(source_locations, error.message)
  │     ├── ArchivistTools.get_call_graph_with_bodies()
  │     ├── ArchivistTools.summarize_call_graph()  → LLM summaries
  │     └── ArchivistTools.generate_call_graph_diagram()  → ASCII diagram
  └── _populate_binder(binder, source_locations, error.message)
        ├── binder.add_source_location()
        ├── binder.add_call_graph()
        ├── binder.add_function_summary()
        └── binder.add_code_snippet()
```

**Content Dict Keys:**

| Key | Type | Description |
|-----|------|-------------|
| `matched_patterns` | `list[dict]` | Pattern ID and confidence for each match |
| `similar_investigations` | `list[dict]` | Investigation ID and similarity score |
| `source_locations` | `list[dict]` | File path, line number, function name, match score |
| `recommended_hypotheses` | `list[dict]` | Description, source, prior, is_authoritative |
| `recommended_queries` | `list[dict]` | Query type and template |
| `resolution_digest` | `list[dict]` | (optional) Resolution details from similar cases |
| `configuration_context` | `dict` | (optional) Component, relevant params, deviations |
| `diagnostic_history` | `dict` | (optional) Error signature, occurrence stats, common causes |
| `llm_summary` | `dict` | (optional) Relevance assessment, insights, focus areas, confidence |

### 5. Prompt Anatomy

| Prompt | Template Path | Type |
|--------|---------------|------|
| System | `srcs/prompts/templates/system/archivist.md` | `SystemPromptType.ARCHIVIST` |
| User | `srcs/prompts/templates/user/prior_knowledge_summary.md` | `UserPromptType.PRIOR_KNOWLEDGE_SUMMARY` |
| Call graph summary | `srcs/prompts/templates/user/call_graph_summary.md` | `UserPromptType.CALL_GRAPH_SUMMARY` |

**Placeholders (prior_knowledge_summary):**

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `{error_message}` | `context.error.message` | The trigger error message text |
| `{error_component}` | `context.error.component` or `"Unknown"` | artdaq component name |
| `{error_function}` | From source locations | Function name where error originates |
| `{error_timestamp}` | `str(context.error.timestamp)` | ISO timestamp of the error |
| `{matched_patterns}` | Formatted text | Top 5 patterns with confidence, description, accuracy |
| `{similar_investigations}` | Formatted text | Top 5 similar cases with similarity score and root cause |
| `{source_locations}` | Formatted text | Top 5 locations with file path, line, function, score |
| `{call_graph_context}` | Formatted text | Callers, callees, and diagrams for top 3 locations |

**Include Dependencies:** None (standalone prompts).

### 6. Session State Interaction

| Operation | Field | Description |
|-----------|-------|-------------|
| Reads | `context.error` | Trigger error for pattern matching and source location |
| Reads | `context.context_logs` | Context logs for configuration extraction |
| Reads | `context.source_locator` | For extracting source roots |
| Reads | `context.kb` | Knowledge base for pattern and similarity queries |
| Reads | `context.code_index` | Code index for function lookup and call graphs |
| Writes | `context.prior_knowledge` | Full `PriorKnowledge` bundle with all retrieved data |
| Binder reads | `binder.get_log_bundle()` | Reads LOG_BUNDLE from Chronicler |
| Binder writes | `binder.add_source_location()` | Source location artifacts |
| Binder writes | `binder.add_call_graph()` | Call graph artifacts |
| Binder writes | `binder.add_function_summary()` | Per-function LLM summaries |
| Binder writes | `binder.add_code_snippet()` | Function body code snippets |
| Binder writes | `binder.add_evidence()` | Numeric analysis evidence items |
| Binder writes | `binder.add_finding()` | Numeric analysis findings |
| Binder writes | `_call_llm_structured()` | LLM request/response artifacts |

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 0, phase_name: "Prior Knowledge Retrieval", message: "Searching the archives..."}` | Phase begins |
| `data_query` | `{phase: 0, source: "sqlite/chromadb", operation: "match_pattern/find_similar"}` | Knowledge base queries |
| `data_result` | `{phase: 0, source: "sqlite/chromadb", result_count: N}` | Knowledge base query results |
| `llm_request` | `{phase: 0, model_name: ..., system_prompt_length: N, user_prompt_length: N}` | LLM calls (summary, call graph, numeric parsing, hint interpretation) |
| `llm_response` | `{phase: 0, response_model: "PriorKnowledgeSummary/ParsedErrorContext/InterpretedHints", parse_failed: bool}` | LLM responses |
| `phase_progress` | `{phase: 0, message: "Found N source locations, extracting code hints..."}` | Progress updates |
| `phase_complete` | `{phase: 0, data: {patterns_found: N, similar_cases: N, source_locations: N, code_hints: N}}` | Phase done |

### 8. Expert Panel Behavior

**Question Types:** WHY, TROUBLESHOOT, WHAT_IS

**`answer_question()` behavior:** Provides domain-specific historical context based on question keywords. Checks for BoardReader, EventBuilder, timeout, and configuration topics and returns relevant patterns, documented solutions, and source code references.

**Q&A Prompt Variant:** Uses `SystemPromptType.ARCHIVIST` (no dedicated QA variant). The Archivist does not have a `qa_archivist.md` template.

**Critique behavior:** Challenges claims of unprecedented nature without archival verification. Flags high-confidence conclusions that lack historical validation.

**Endorsement criteria:** Endorses contributions that reference patterns, historical precedent, previous cases, or have confidence > 0.6.

### 9. Configuration and Tuning

| Parameter | Value | Notes |
|-----------|-------|-------|
| Source roots | `list[Path]` | Extracted from `context.source_locator._source_roots` |
| KB and ChromaDB | Required | Must be initialized for full retrieval |
| Code index | Required for source location | Built from source repository sync |
| Max source locations | 3 (find), 5 (binder) | Top locations by match score |
| Max code hints | 10 | After deduplication and sorting |
| Max auto-generated queries | 8 | From source location analysis |
| Max dataflow queries | 6 | From upstream tracing |
| Confidence base | 0.3 | Boosted by findings, capped at 0.95 |
| Authoritative hint boost | 0.85 | For `is_authoritative` recommended hypotheses |
| LLM temperature | Default from provider | No persona-specific override |

### 10. Error Handling and Fallbacks

| Failure Mode | Recovery Strategy |
|-------------|-------------------|
| KB unavailable | `_create_null_kb()` returns empty `PriorKnowledge` (patterns=[], similar=[]) |
| Retrieval orchestrator fails | Returns empty `PriorKnowledge`, logs warning |
| Source locator fails | Skips source location, logs warning, continues with KB-only results |
| Code index unavailable | Skips code hints, call graph enrichment, and dataflow tracing |
| LLM summarization fails | Skips `llm_summary` in content dict, logs warning, continues |
| LLM hint interpretation fails | Falls back to `_generate_hypotheses_from_hints_rules()` (rule-based) |
| LLM numeric parsing fails | Falls back to `_create_context_from_regex_analysis()` (regex-only) |
| LOG_BUNDLE not available | Skips `_enrich_from_log_bundle()`, continues normally |

### 11. Testing Contract

| Test | Description |
|------|-------------|
| `test_archivist_retrieves_patterns` | Known error pattern in KB produces matched pattern with high confidence |
| `test_archivist_finds_source_location` | Error message with known function name produces correct source file and line |
| `test_archivist_extracts_code_hints` | Source function with causal comments produces diagnostic code hints |
| `test_archivist_traces_dataflow` | Function with known callers produces upstream dataflow queries |
| `test_archivist_handles_empty_kb` | Empty KB produces empty `PriorKnowledge`, no crash |
| `test_archivist_enriches_from_log_bundle` | LOG_BUNDLE with clues produces recommended hypotheses and queries in PriorKnowledge |
| `test_archivist_extracts_resolutions` | Similar investigations with known root causes produce ResolutionDigest list |
| `test_archivist_analyzes_configuration` | Error message with timeout values produces ConfigurationContext |
| `test_archivist_gets_diagnostic_history` | Multiple similar cases produce DiagnosticHistory with resolution rate |
| `test_archivist_summarizes_with_llm` | Meaningful findings trigger LLM summarization producing PriorKnowledgeSummary |
| `test_archivist_answer_question` | WHY question about BoardReader produces historical context and source references |
| `test_archivist_critique_no_history` | High-confidence contribution without historical terms produces MEDIUM critique |
| `test_archivist_endorses_historical` | Contribution referencing patterns produces True endorsement |
| `test_archivist_null_kb_fallback` | No KB available uses NullKB fallback, returns empty results |

**Mock Requirements:** `KnowledgeBase`, `ChromaStore`, `CodeIndex`, `SourceLocator`, `LLMProvider`, `WorkBinder`.

---

## Theorist (Phase 1)

### 1. Identity

| Field | Value |
|-------|-------|
| **Phase** | 1 |
| **Name** | Theorist |
| **Role** | Hypothesis Generation |
| **Color** | `magenta` |
| **Thinking Phrase** | `"What if..."` |
| **Prompt Key** | `theorist` |
| **Uses LLM** | Yes |

**Traits:** creative, speculative, multi-perspective, probabilistic, generative

**Thinking Style:** Divergent thinking -- generates multiple competing explanations, considers unlikely possibilities, assigns probabilities based on evidence strength, ensures coverage across failure categories. The Theorist approaches problems by generating more hypotheses than will survive, then filtering and ranking.

### 2. Responsibilities

**Pipeline Role.** The Theorist generates ranked root cause hypotheses from 5 tiers of decreasing authority:

| Tier | Source | Prior Range | Description |
|------|--------|-------------|-------------|
| 0a | Numeric analysis | 0.70-0.85 | Quantitative analysis from error message values |
| 0b | Code hints | 0.70-0.85 (explicit cause: 0.90-0.95) | Diagnostic comments in source code |
| 1 | Pattern matches | 0.60-0.80 | Historical error patterns from knowledge base |
| 2 | Similar cases | 0.30-0.50 | Root causes from similar past investigations |
| 3 | Fresh LLM | max 0.20 (config: `fresh_prior_max`) | Novel hypotheses generated by the LLM |
| 4 | Alternatives | 0.10 (config: `alternative_prior`) | Deliberate category-filling alternatives |

After generation, hypotheses undergo deduplication (LLM-based if enabled, keyword-based otherwise), normalization (two-tier system to protect code hint probability share), and sorting by prior. Enhanced reports are produced: `TierGenerationReport`, `DeduplicationReport`, `CategoryCoverageAnalysis`, and `PriorJustificationReport`.

**Expert Panel Role.** Proposes hypothetical causes ranked by probability. Participates in panels for WHY, TROUBLESHOOT, and COMPARE question types.

**Artifacts Produced:**

| Artifact | Type | Description |
|----------|------|-------------|
| Hypotheses | `list[Hypothesis]` | Ranked by normalized prior, with source, score, description |
| Hypothesis binder artifacts | Binder `HypothesisArtifact` | One per hypothesis with rank, prior, source |
| Tier generation report | `TierGenerationReport` | Breakdown by tier with counts and averages |
| Deduplication report | `DeduplicationReport` | Method used, merged groups, threshold |
| Category coverage analysis | `CategoryCoverageAnalysis` | Coverage across failure categories |
| Prior justification report | `PriorJustificationReport` | Base rates, adjustments, normalization |

**Artifacts Consumed:**

| Artifact | Source | Description |
|----------|--------|-------------|
| Prior knowledge | `context.prior_knowledge` (from Archivist) | Patterns, similar cases, recommended hypotheses, source locations |
| Trigger error | `context.error` (`Log`) | Error message, component, function, timestamp |
| Context logs | `context.context_logs` (`list[Log]`) | Last 20 entries for prompt context |

### 3. Tool Mapping

| API Tool | Invokes Theorist? | Capabilities Used |
|----------|-------------------|-------------------|
| `investigate` | Yes (Phase 1) | Full hypothesis generation |
| `investigate_stream` | Yes (Phase 1) | Full generation + SSE events |
| `ask_experts` | Yes (for WHY, TROUBLESHOOT, COMPARE questions) | Hypothesis proposal |

### 4. Implementation

**Class:** `TheoristPersona` in `srcs/persona/theorist.py`

**Structured Response Models:**

```python
class HypothesisResponse(BaseModel):    # From srcs/workbinder/artifacts/parsers.py
    hypotheses: list[HypothesisItem]    # Generated hypotheses with description, prior, category

class DeduplicationResponse(BaseModel):
    groups: list[list[int]]             # Groups of semantically equivalent indices (1-based)
    distinct: list[int]                 # Unique/distinct hypothesis indices (1-based)
```

**Key Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `def __init__(self) -> None` | Initializes LLM, KB, config references and report tracking state |
| `prepare` | `async def prepare(self, context: InvestigationContext) -> None` | Loads `HypothesisConfig` from `context.config`, stores LLM and KB references |
| `contribute` | `async def contribute(self, context: InvestigationContext) -> Contribution` | Calls `_generate_hypotheses`, stores in `context.hypotheses`, builds content dict with enhanced reports |
| `_generate_hypotheses` | `async def _generate_hypotheses(self, context) -> list[Hypothesis]` | Delegates to `_generate()` with error, context_logs, prior, binder |
| `_generate` | `async def _generate(self, error, context_logs, prior, binder) -> list[Hypothesis]` | Main generation pipeline: 5 tiers, dedup, normalize, sort, write to binder |
| `_generate_fresh` | `async def _generate_fresh(self, error, context_logs, prior, exclude, binder) -> list[Hypothesis]` | LLM-based hypothesis generation with `HYPOTHESIS_GENERATION` prompt |
| `_generate_alternatives` | `def _generate_alternatives(self, error, existing) -> list[Hypothesis]` | Fills missing categories (hardware, configuration, timing, resource, software) |
| `_deduplicate_with_llm` | `async def _deduplicate_with_llm(self, hypotheses) -> list[Hypothesis]` | LLM identifies semantic duplicates, merges them with combined priors |
| `_merge_similar_hypotheses` | `def _merge_similar_hypotheses(self, hypotheses, similarity_threshold) -> list[Hypothesis]` | Keyword-based Jaccard similarity merging |
| `_normalize_priors` | `def _normalize_priors(self, hypotheses) -> list[Hypothesis]` | Two-tier normalization: code hints get `code_hint_probability_share`, others share remainder |
| `_build_tier_report` | `def _build_tier_report(self, hypotheses) -> TierGenerationReport` | Builds tier breakdown from tracked generation data |
| `_build_dedup_report` | `def _build_dedup_report(self, hypotheses) -> DeduplicationReport` | Reports on deduplication method, merges, threshold |
| `_build_coverage_analysis` | `def _build_coverage_analysis(self, hypotheses) -> CategoryCoverageAnalysis` | Checks coverage across 6 expected categories |
| `_build_prior_report` | `def _build_prior_report(self, hypotheses) -> PriorJustificationReport` | Explains prior assignment with base rates and adjustments |
| `answer_question` | `async def answer_question(self, context: QuestionContext) -> Contribution` | Generates theoretical explanations based on question type (WHY, TROUBLESHOOT, HOW_TO) |
| `critique` | `async def critique(self, contribution) -> Critique` | Flags overly certain conclusions ("only", "must be") and high confidence without alternatives |
| `endorse` | `async def endorse(self, contribution) -> bool` | Endorses contributions that consider alternatives or have confidence <= 0.8 |

**Generation Pipeline Flow:**

```
_generate(error, context_logs, prior, binder)
  ├── Reset tracking state
  ├── Tier 0a: Numeric analysis hypotheses from prior.recommended_hypotheses
  ├── Tier 0b: Code hint hypotheses from prior.recommended_hypotheses
  ├── Tier 1: Pattern match hypotheses from prior.recommended_hypotheses
  ├── Tier 2: Similar case hypotheses from prior.recommended_hypotheses
  ├── LLM deduplication (if enabled and >= min_hypotheses)
  │     └── _deduplicate_with_llm() → merged hypotheses
  ├── Check for authoritative code hints → fast_path flag
  ├── Tier 3: _generate_fresh() via LLM (limited if fast_path)
  │     ├── Build prompt with HYPOTHESIS_GENERATION template
  │     ├── LLM: generate_structured(HypothesisResponse)
  │     └── Fallback: _parse_text_response() from plain text
  ├── Tier 4: _generate_alternatives() for missing categories
  ├── _merge_similar_hypotheses() → keyword dedup
  ├── Second-pass dedup (threshold=0.5) if > 8 hypotheses
  ├── _normalize_priors() → two-tier normalization
  ├── Sort by prior (descending)
  ├── Write each hypothesis to binder via binder.add_hypothesis()
  │     └── Link pending numeric evidence to numeric_analysis hypotheses
  └── Return sorted hypotheses
```

**Content Dict Keys:**

| Key | Type | Description |
|-----|------|-------------|
| `hypotheses` | `list[dict]` | ID, description, source, prior, score for each hypothesis |
| `count` | `int` | Total number of generated hypotheses |
| `categories` | `list[str]` | Covered failure categories |
| `has_code_hints` | `bool` | Whether any hypothesis came from code hints |
| `has_pattern_match` | `bool` | Whether any hypothesis came from pattern matches |
| `tier_generation_report` | `dict` | Tier breakdowns, fast path status, primary tier |
| `deduplication_report` | `dict` | Method, counts, merged groups, threshold |
| `category_coverage_analysis` | `dict` | Categories, coverage score, missing, suggestions |
| `prior_justification_report` | `dict` | Per-hypothesis base rates, adjustments, normalization |

### 5. Prompt Anatomy

| Prompt | Template Path | Type |
|--------|---------------|------|
| System | `srcs/prompts/templates/system/theorist.md` | `SystemPromptType.THEORIST` |
| User | `srcs/prompts/templates/user/hypothesis_generation.md` | `UserPromptType.HYPOTHESIS_GENERATION` |
| Q&A System | `srcs/prompts/templates/system/qa/qa_theorist.md` | `SystemPromptType.QA_THEORIST` |

**Placeholders (hypothesis_generation):**

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `{error_message}` | `error.message` | The trigger error message text |
| `{error_component}` | `error.component` or from source locations | artdaq component name |
| `{error_function}` | `error.function` or from source locations | Function name from error or code analysis |
| `{error_timestamp}` | `error.timestamp.isoformat()` | ISO timestamp of the error |
| `{context_logs}` | `_format_logs(context_logs)` | Last 20 context log entries |
| `{prior_knowledge}` | `_format_prior(prior)` | Full prior knowledge with patterns, similar cases, source locations, resolution history, config context, diagnostic history |
| `{code_context}` | `_format_code_context(prior)` | Source locations with callers, callees, function bodies |

**Additional Context Appended:**

- Numeric analysis context from binder or `NumericExtractor`
- Binder context via `BinderSerializer.serialize_for_prompt()`

### 6. Session State Interaction

| Operation | Field | Description |
|-----------|-------|-------------|
| Reads | `context.error` | Trigger error for hypothesis generation |
| Reads | `context.context_logs` | Context for LLM prompt |
| Reads | `context.prior_knowledge` | All prior knowledge from Archivist |
| Reads | `context.config.hypothesis_config` | HypothesisConfig settings |
| Writes | `context.hypotheses` | Generated and ranked hypothesis list |
| Binder writes | `binder.add_hypothesis()` | One artifact per hypothesis with rank and prior |
| Binder writes | `binder.link_evidence_to_hypothesis()` | Links pending numeric evidence |
| Binder reads | `binder.get_by_tag("numeric_analysis")` | Checks for Phase 0 numeric findings |
| Binder reads | `binder.get_evidence_items()` | For pending numeric evidence linking |

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 1, phase_name: "Hypothesis Generation", message: "What if..."}` | Phase begins |
| `llm_request` | `{phase: 1, model_name: ..., system_prompt_length: N, user_prompt_length: N}` | LLM calls (fresh generation, deduplication) |
| `llm_response` | `{phase: 1, response_model: "HypothesisResponse/DeduplicationResponse", parse_failed: bool}` | LLM responses |
| `phase_progress` | `{phase: 1, message: "Generated N hypotheses from M tiers"}` | After generation |
| `phase_complete` | `{phase: 1, data: {hypotheses_generated: N, top_hypothesis: "...", top_prior: 0.75, categories: [...]}}` | Phase done |

### 8. Expert Panel Behavior

**Question Types:** WHY, TROUBLESHOOT, COMPARE

**`answer_question()` behavior:** Generates theoretical explanations based on question type. For WHY questions, provides multi-factor explanations about common artdaq failure modes. For TROUBLESHOOT questions, provides probability-ranked root cause theories. For HOW_TO questions, provides alternative approaches with trade-offs.

**Q&A Prompt Variant:** `SystemPromptType.QA_THEORIST` (`srcs/prompts/templates/system/qa/qa_theorist.md`)

**Critique behavior:** Flags overly certain language ("only", "must be") and very high confidence (>0.9) without alternatives mentioned. Recommends generating alternative hypotheses before concluding.

**Endorsement criteria:** Endorses contributions that consider alternatives, mention possibilities, or have confidence <= 0.8.

### 9. Configuration and Tuning

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| `max_hypotheses` | 10 | `HypothesisConfig` | Maximum total hypotheses |
| `fresh_prior_max` | 0.20 | `HypothesisConfig` | Maximum prior for LLM-generated hypotheses |
| `alternative_prior` | 0.10 | `HypothesisConfig` | Prior for category-filling alternatives |
| `max_alternatives` | 5 | `HypothesisConfig` | Maximum alternative hypotheses |
| `max_fresh_if_code_hints` | 2 | `HypothesisConfig` | Fresh LLM limit when authoritative hints exist |
| `code_hint_probability_share` | 0.50 | `HypothesisConfig` | Probability mass reserved for code hint tier |
| `merge_similarity_threshold` | 0.80 | `HypothesisConfig` | Jaccard similarity threshold for keyword merging |
| `merge_prior_cap` | 0.95 | `HypothesisConfig` | Maximum prior after merging |
| `merge_other_prior_factor` | 0.30 | `HypothesisConfig` | Weight for non-best priors in merge |
| `enable_llm_deduplication` | True | `HypothesisConfig` | Whether to use LLM for semantic dedup |
| `llm_dedup_min_hypotheses` | 4 | `HypothesisConfig` | Minimum hypotheses to trigger LLM dedup |
| `authoritative_hint_threshold` | 0.80 | `HypothesisConfig` | Threshold for triggering fast path |
| LLM temperature | Default from provider | -- | No persona-specific override |

**Tiered Scoring Base Rates:**

| Source Prefix | Base Rate |
|---------------|-----------|
| `numeric_analysis` | 0.75 |
| `code_hint:explicit_cause` | 0.85 |
| `code_hint:*` | 0.75 |
| `pattern:*` | 0.70 |
| `similar:*` | 0.40 |
| `fresh:*` | 0.20 |
| `alternative:*` | 0.10 |

### 10. Error Handling and Fallbacks

| Failure Mode | Recovery Strategy |
|-------------|-------------------|
| LLM not initialized | Returns empty hypothesis list with warning |
| LLM structured generation fails | Falls back to `_parse_text_response()` which parses numbered/bulleted lines from plain text |
| LLM deduplication fails | Logs warning, continues with keyword-based merging only |
| No prior knowledge | Proceeds with LLM-only generation (Tiers 3-4 only), lower confidence |
| Hypotheses already in context | Returns existing hypotheses without regeneration |
| LLM dedup reduces below 2 | Re-adds highest-prior merged-away hypothesis to maintain minimum count |
| HypothesisConfig not available | Creates default `HypothesisConfig()` |

### 11. Testing Contract

| Test | Description |
|------|-------------|
| `test_theorist_generates_hypotheses` | Valid context with prior knowledge produces list of Hypothesis with scores and priors |
| `test_theorist_uses_tiered_scoring` | Code hint hypotheses have higher priors than LLM-generated ones |
| `test_theorist_respects_max_hypotheses` | Generated count does not exceed `max_hypotheses` config |
| `test_theorist_llm_fallback` | LLM fails; hypotheses generated from prior knowledge patterns and code hints only |
| `test_theorist_text_parse_fallback` | Structured generation fails; plain text response parsed into hypotheses |
| `test_theorist_generates_alternatives` | Missing categories (hardware, timing) generate low-prior alternative hypotheses |
| `test_theorist_deduplicates` | Similar hypotheses are merged with combined priors |
| `test_theorist_normalizes_priors` | After normalization, priors sum to approximately 1.0; code hints retain their share |
| `test_theorist_fast_path` | Authoritative code hint triggers fast path: limits fresh generation to `max_fresh_if_code_hints` |
| `test_theorist_writes_to_binder` | Each hypothesis creates a binder artifact with correct rank and prior |
| `test_theorist_answer_question` | WHY question produces ranked hypothetical causes |
| `test_theorist_critique_certainty` | Contribution with "must be" language produces MEDIUM critique |
| `test_theorist_endorses_alternatives` | Contribution mentioning alternatives produces True endorsement |
| `test_theorist_coverage_analysis` | Hypotheses spanning 4+ categories produce high coverage score |

**Mock Requirements:** `LLMProvider` (for `generate_structured` and `generate`), `KnowledgeBase`, `WorkBinder`, `PriorKnowledge` with populated recommended hypotheses, `HypothesisConfig`.

---

## Detective (Phase 2)

### 1. Identity

| Field | Value |
|-------|-------|
| **Phase** | 2 |
| **Name** | Detective |
| **Role** | Evidence Seeking |
| **Color** | `cyan` |
| **Thinking Phrase** | `"Let me check..."` |
| **Prompt Key** | `detective` |
| **Uses LLM** | Yes |

**Traits:** analytical, persistent, detail-oriented, methodical, evidence-focused

**Thinking Style:** Investigative analysis -- seeks discriminating evidence, evaluates source quality, tracks evidence gaps, updates hypothesis rankings based on findings. The Detective is relentless in pursuit of facts and never accepts a hypothesis without testing it against available evidence.

### 2. Responsibilities

**Pipeline Role.** The Detective iteratively seeks discriminating evidence to evaluate and rank hypotheses using the `EvidenceOrchestrator`. The evidence loop runs for up to 10 iterations (configurable), using an adaptive strategy that pivots between balanced, code-centric, and log-centric modes based on available context. The Detective also produces three enhanced analysis artifacts: `EvidenceGapAnalysis`, `EvidenceQualityScore`, and `AlternativeInvestigationPaths`.

Evidence is gathered using real tool queries (function lookup, class lookup, code search, log search, similar cases, pattern lookup, variable tracing, error path analysis, caller chain analysis). Query effectiveness is tracked in real-time, and ineffective query types are automatically skipped.

**Expert Panel Role.** Provides factual information from codebase, docs, and logs with citations. Participates in panels for TROUBLESHOOT, WHY, and HOW_TO question types.

**Artifacts Produced:**

| Artifact | Type | Description |
|----------|------|-------------|
| Evidence collection | `Evidence` | All evidence items with type, content, source, strength |
| Updated hypotheses | `list[Hypothesis]` | Hypotheses with updated scores, supporting/contradicting IDs |
| Evidence gap analysis | `EvidenceGapAnalysis` | Per-hypothesis gap classification and recommended queries |
| Evidence quality score | `EvidenceQualityScore` | Component scores: strength, diversity, coverage, discrimination |
| Alternative paths | `AlternativeInvestigationPaths` | Suggested investigation paths based on missing evidence |
| Evidence binder artifacts | Binder `EvidenceArtifact` | One per evidence item with targeting fields |
| Evidence-hypothesis links | Binder links | Supports/contradicts relationships |
| Updated hypothesis scores | Binder updates | Score and rank updates on hypothesis artifacts |

**Artifacts Consumed:**

| Artifact | Source | Description |
|----------|--------|-------------|
| Hypotheses | `context.hypotheses` (from Theorist) | Ranked hypotheses to evaluate |
| Prior knowledge | `context.prior_knowledge` (from Archivist) | Recommended queries, source locations |
| Trigger error | `context.error` (`Log`) | Error message for evidence gathering |
| Context logs | `context.context_logs` (`list[Log]`) | Runtime log context |
| Code snippets | Binder (from Archivist) | Source code for LLM code analysis |
| Initial evidence | `context.evidence` | Any evidence already collected |

### 3. Tool Mapping

| API Tool | Invokes Detective? | Capabilities Used |
|----------|---------------------|-------------------|
| `investigate` | Yes (Phase 2) | Full evidence seeking pipeline |
| `investigate_stream` | Yes (Phase 2) | Full seeking + SSE events |
| `ask_experts` | Yes (for TROUBLESHOOT, WHY, HOW_TO questions) | Evidence-based facts with citations |

### 4. Implementation

**Class:** `DetectivePersona` in `srcs/persona/detective.py`

**Orchestrator:** `EvidenceOrchestrator` in `srcs/persona/orchestration/evidence_orchestrator.py`

**Key Methods (DetectivePersona):**

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `def __init__(self) -> None` | Initializes `_orchestrator`, `_collected_evidence`, `_updated_hypotheses` |
| `prepare` | `async def prepare(self, context: InvestigationContext) -> None` | Creates `EvidenceOrchestrator` with LLM, KB, tools, config, max_iterations |
| `contribute` | `async def contribute(self, context: InvestigationContext) -> Contribution` | Calls `_seek_evidence`, updates context, builds content dict with gap analysis, quality score, alternative paths |
| `_seek_evidence` | `async def _seek_evidence(self, context) -> tuple[Evidence, list[Hypothesis]]` | Delegates to `orchestrator.seek()`. Returns initial evidence and original hypotheses on failure |
| `_build_content_dict` | `def _build_content_dict(self, evidence, hypotheses) -> dict[str, Any]` | Computes enhanced analysis artifacts and builds full content dict |
| `_calculate_confidence` | `def _calculate_confidence(self, evidence) -> float` | Maps strong evidence count to confidence: 3+ strong=0.85, 2=0.75, 1=0.65, 3+ moderate=0.55, 1+ moderate=0.45, else 0.35 |
| `_analyze_evidence_gaps` | `def _analyze_evidence_gaps(self, evidence, hypotheses) -> EvidenceGapAnalysis` | Classifies gaps: `no_evidence`, `no_supporting`, `no_contradicting`, `weak_only` |
| `_calculate_quality_score` | `def _calculate_quality_score(self, evidence, hypotheses) -> EvidenceQualityScore` | Components: strength (0.3), diversity (0.2), coverage (0.3), discrimination (0.2) |
| `_suggest_alternative_paths` | `def _suggest_alternative_paths(self, evidence, hypotheses, gap_analysis) -> AlternativeInvestigationPaths` | Suggests `config_check`, `code_analysis`, `upstream_trace`, `temporal_analysis` |
| `reflect` | `async def reflect(self, context) -> Reflection` | Analyzes evidence quality, gaps, code vs. log balance |
| `answer_question` | `async def answer_question(self, context: QuestionContext) -> Contribution` | Gathers domain-specific evidence, formulates evidence-based answers, generates citations |
| `critique` | `async def critique(self, contribution) -> Critique` | Flags conclusions lacking evidence support; acknowledges strong evidence and code+log balance |
| `endorse` | `async def endorse(self, contribution) -> bool` | Endorses contributions citing evidence, findings, observations, or with confidence > 0.7 |

**Key Methods (EvidenceOrchestrator):**

| Method | Signature | Description |
|--------|-----------|-------------|
| `seek` | `async def seek(self, hypotheses, initial_evidence, prior, binder) -> tuple[Evidence, list[Hypothesis]]` | Main evidence loop: strategy init, early source lookup, iterate (identify queries, execute, update scores), binder code analysis, write to binder |
| `_identify_queries` | `async def _identify_queries(self, hypotheses, evidence, prior) -> list[dict]` | Uses recommended queries from prior + LLM-generated discriminating queries |
| `_early_source_lookup` | `async def _early_source_lookup(self, hypotheses, prior) -> Evidence` | Forces first-iteration source code lookup for known function names |
| `_generate_queries` | `async def _generate_queries(self, hypotheses, evidence) -> list[dict]` | LLM generates queries using `EVIDENCE_QUERY` prompt with `SystemPromptType.DETECTIVE` |
| `_generate_fallback_queries` | `def _generate_fallback_queries(self, hypotheses, evidence) -> list[dict]` | Regex extraction of function/class names from hypothesis descriptions |
| `_execute_queries` | `async def _execute_queries(self, queries, existing_evidence) -> Evidence` | Routes to appropriate tools, tracks effectiveness, preserves targeting info |
| `_execute_single_query` | `async def _execute_single_query(self, query_type, query_str, query) -> list[EvidenceItem]` | Routes: `log_search`, `component_logs`, `similar_cases`, `time_window`, `function_lookup`, `class_lookup`, `code_search`, `log_source`, `pattern_lookup`, `accuracy_check`, `trace_variable`, `error_path`, `caller_chain` |
| `_analyze_binder_code_snippets` | `async def _analyze_binder_code_snippets(self, hypotheses, binder) -> Evidence` | Sends top binder code snippets + top hypotheses to LLM for code analysis |
| `_update_scores` | `def _update_scores(self, hypotheses, new_evidence) -> list[Hypothesis]` | Targeted scoring (counterfactual) + non-targeted scoring (code pattern analysis) |
| `_should_stop` | `def _should_stop(self, hypotheses, iteration) -> bool` | Clear winner, max iterations, or code hint with clear lead |

**Evidence Orchestrator Execution Flow:**

```
orchestrator.seek(hypotheses, initial_evidence, prior, binder)
  ├── Initialize EvidenceStrategy(has_context_logs, context_log_count)
  ├── For iteration in range(max_iterations):
  │     ├── If iteration == 0:
  │     │     └── _early_source_lookup(hypotheses, prior) → early evidence
  │     ├── _identify_queries(hypotheses, evidence, prior)
  │     │     ├── Use prior.recommended_queries
  │     │     └── _generate_queries() via LLM or _generate_fallback_queries()
  │     ├── strategy.prioritize_queries(queries)
  │     ├── Filter: strategy.should_skip_query() for exhausted types
  │     ├── _execute_queries(queries[:max_per_iter], existing_evidence)
  │     │     ├── Route to tools: code_tools, investigation_tools, forensics_tools
  │     │     ├── Record found/not-found with targeting info
  │     │     └── Track effectiveness: strategy.record_query_result()
  │     ├── _merge_evidence(evidence, new_evidence)
  │     ├── _update_scores(hypotheses, new_evidence)
  │     └── _should_stop(hypotheses, iteration)?
  ├── _analyze_binder_code_snippets(hypotheses, binder) → code evidence
  ├── Build mem_to_binder_id mapping for hypothesis linking
  ├── For each evidence item:
  │     ├── binder.add_evidence(type, content, source, strength, targeting...)
  │     ├── Link to targeted hypothesis (supports/contradicts)
  │     └── Link to relevant hypotheses by keyword matching
  ├── Update hypothesis scores in binder
  └── Return (evidence, hypotheses)
```

**Content Dict Keys:**

| Key | Type | Description |
|-----|------|-------------|
| `items_found` | `int` | Total evidence items collected |
| `strong_evidence` | `int` | Count of STRONG evidence |
| `moderate_evidence` | `int` | Count of MODERATE evidence |
| `weak_evidence` | `int` | Count of WEAK evidence |
| `by_type` | `dict[str, int]` | Evidence count by type |
| `hypotheses_updated` | `int` | Number of hypotheses with updated scores |
| `top_hypothesis` | `dict` | ID, description, score of the leading hypothesis |
| `supporting_evidence_count` | `int` | Total supporting evidence links |
| `contradicting_evidence_count` | `int` | Total contradicting evidence links |
| `evidence_gap_analysis` | `dict` | Gaps, coverage counts, recommended queries |
| `evidence_quality_score` | `dict` | Component scores, flags, type presence |
| `alternative_paths` | `dict` | Suggested paths, insufficiency reason, most promising |

### 5. Prompt Anatomy

| Prompt | Template Path | Type |
|--------|---------------|------|
| System | `srcs/prompts/templates/system/detective.md` | `SystemPromptType.DETECTIVE` |
| User | `srcs/prompts/templates/user/evidence_query.md` | `UserPromptType.EVIDENCE_QUERY` |
| Q&A System | `srcs/prompts/templates/system/qa/qa_detective.md` | `SystemPromptType.QA_DETECTIVE` |

**Placeholders (evidence_query):**

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `{investigation_mode}` | `_get_investigation_mode()` | Current mode: balanced, code_centric, log_centric |
| `{mode_specific_guidance}` | `_get_mode_guidance()` | Detailed guidance based on current mode |
| `{analyzed_functions}` | `_format_analyzed_functions()` | Already-analyzed function names to avoid duplicates |
| `{query_effectiveness}` | `_format_query_effectiveness()` | Per-type success rate and status |
| `{hypotheses}` | `_format_hypotheses(hypotheses)` | Top 5 hypotheses with ID, description, prior, score |
| `{evidence}` | `evidence.summary()` | Current evidence summary |

### 6. Session State Interaction

| Operation | Field | Description |
|-----------|-------|-------------|
| Reads | `context.hypotheses` | Hypotheses from Theorist to evaluate |
| Reads | `context.prior_knowledge` | Recommended queries and source locations |
| Reads | `context.evidence` | Any initial evidence |
| Reads | `context.error` | Trigger error |
| Reads | `context.context_logs` | Context for log-based queries |
| Reads | `context.config.evidence_config` | EvidenceConfig settings |
| Reads | `context.config.max_evidence_iterations` | Maximum loop iterations |
| Writes | `context.evidence` | Complete evidence collection |
| Writes | `context.hypotheses` | Updated hypothesis list with new scores |
| Binder reads | `binder.get_code_snippets()` | Code snippets from Phase 0 for LLM analysis |
| Binder reads | `binder.get_hypotheses()` | Hypothesis artifacts for ID mapping |
| Binder writes | `binder.add_evidence()` | Evidence items with targeting fields |
| Binder writes | `binder.link_evidence_to_hypothesis()` | Supports/contradicts links |
| Binder writes | `binder.update_artifact()` | Updated hypothesis scores and ranks |

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 2, phase_name: "Evidence Seeking", message: "Let me check..."}` | Phase begins |
| `llm_request` | `{phase: 2, model_name: ..., system_prompt_length: N, user_prompt_length: N}` | Each query plan generation |
| `llm_response` | `{phase: 2, response_model: "QueryResponse", parse_failed: bool}` | Query plan parsed |
| `data_query` | `{phase: 2, source: "code_tools/investigation_tools/forensics_tools", operation: "function_lookup/log_search/..."}` | Tool query executed |
| `data_result` | `{phase: 2, result_count: N, query_type: "..."}` | Tool query result |
| `phase_progress` | `{phase: 2, message: "Evidence iteration 3/10: 7 items collected", data: {iteration: 3, evidence_count: 7, mode: "code_centric"}}` | Each iteration |
| `phase_complete` | `{phase: 2, data: {total_evidence: N, iterations_used: N, strong: N, moderate: N, weak: N}}` | Phase done |

### 8. Expert Panel Behavior

**Question Types:** TROUBLESHOOT, WHY, HOW_TO

**`answer_question()` behavior:** Gathers domain-specific evidence points based on question keywords (BoardReader, EventBuilder, timeout, config, fragment). Formulates evidence-based answers and generates source citations with type, reference, excerpt, and relevance score.

**Q&A Prompt Variant:** `SystemPromptType.QA_DETECTIVE` (`srcs/prompts/templates/system/qa/qa_detective.md`)

**Critique behavior:** Checks if conclusions are grounded in evidence. Flags high confidence without strong evidence cited. Acknowledges contributions that use both code and log evidence.

**Endorsement criteria:** Endorses contributions that cite evidence, findings, logs, traces, observations, or code references, or have confidence > 0.7.

### 9. Configuration and Tuning

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| `max_iterations` | 10 | `InvestigationConfig.max_evidence_iterations` | Maximum evidence-seeking loop iterations |
| `max_queries_per_iteration` | 5 | `EvidenceConfig.max_queries_per_iteration` | Queries executed per iteration |
| `consecutive_failure_limit` | 3 | `EvidenceConfig` | Consecutive failures before skipping query type |
| `min_success_rate` | 0.1 | `EvidenceConfig` | Minimum success rate to continue query type |
| `min_attempts_for_rate` | 5 | `EvidenceConfig` | Minimum attempts before evaluating success rate |
| `min_iterations_before_stop` | 2 | `EvidenceConfig` | Minimum iterations before early stopping |
| `clear_winner_score` | 0.5 | `EvidenceConfig` | Score threshold for clear winner |
| `clear_winner_margin` | 0.2 | `EvidenceConfig` | Margin between top two hypotheses |
| `code_hint_early_stop_score` | 0.4 | `EvidenceConfig` | Early stop threshold for code hint hypotheses |
| `code_hint_early_stop_margin` | 0.15 | `EvidenceConfig` | Margin for code hint early stopping |
| `targeted_boost_factor` | 1.5 | `EvidenceConfig` | Boost for targeted evidence matching expected_if_true |
| `targeted_contradict_factor` | 1.0 | `EvidenceConfig` | Penalty for targeted evidence matching expected_if_false |
| `absence_contradict_factor` | 0.3 | `EvidenceConfig` | Penalty for expected but absent evidence |
| `non_targeted_code_factor` | 0.75 | `EvidenceConfig` | Weight for non-targeted code evidence |
| `non_targeted_log_factor` | 0.5 | `EvidenceConfig` | Weight for non-targeted log evidence |
| `code_hint_match_factor` | 1.5 | `EvidenceConfig` | Bonus for evidence matching code hint source |
| `strength_strong` | 0.8 | `EvidenceConfig` | Score multiplier for STRONG evidence |
| `strength_moderate` | 0.4 | `EvidenceConfig` | Score multiplier for MODERATE evidence |
| `strength_weak` | 0.15 | `EvidenceConfig` | Score multiplier for WEAK evidence |
| `category_relevance_score` | 0.1 | `EvidenceConfig` | Relevance score for category-level match |
| `weak_term_relevance_score` | 0.05 | `EvidenceConfig` | Relevance score for weak term match |
| `term_match_threshold` | 0.3 | `EvidenceConfig` | Fraction of terms required for content match |
| `default_function_source_length` | 2000 | Constructor | Max chars for LLM-generated function queries (0 = no limit for `full_source=True`) |

**Confidence Thresholds:**

| Strong Evidence Count | Moderate Count | Confidence |
|----------------------|----------------|------------|
| >= 3 | any | 0.85 |
| >= 2 | any | 0.75 |
| >= 1 | any | 0.65 |
| 0 | >= 3 | 0.55 |
| 0 | >= 1 | 0.45 |
| 0 | 0 | 0.35 |
| no items | -- | 0.20 |

**Adaptive Strategy Modes:**

| Mode | Trigger | Behavior |
|------|---------|----------|
| `balanced` | Default when context logs available | Equal weight to code and log queries |
| `code_centric` | No context logs (count == 0) | Skip all log queries; prioritize function_lookup, code_search, class_lookup |
| Transition | Log queries consistently fail | Automatically suppresses via `should_skip_query()` |

### 10. Error Handling and Fallbacks

| Failure Mode | Recovery Strategy |
|-------------|-------------------|
| Orchestrator unavailable (no LLM or KB) | Returns empty `Evidence()` with `context.hypotheses` unchanged |
| Evidence seeking fails (exception in `orchestrator.seek`) | Returns initial evidence and original hypotheses |
| LLM query generation fails | Falls back to `_generate_fallback_queries()`: regex extraction of identifiers from hypothesis descriptions |
| Individual tool query fails | Logs warning, records not-found result, continues to next query |
| All query types exhausted | Stops iteration loop, uses whatever evidence was collected |
| Code snippet analysis fails | Logs warning, continues without binder code analysis evidence |
| Strategy adaptation | Automatically pivots to code_centric if log queries consistently fail; tracks per-type effectiveness |
| Hypothesis binder ID mapping fails | Falls back to description-based matching |
| No hypotheses in context | Returns empty evidence with confidence 0.2 |

### 11. Testing Contract

| Test | Description |
|------|-------------|
| `test_detective_seeks_evidence` | Valid context with hypotheses produces Evidence with items |
| `test_detective_updates_hypothesis_scores` | Evidence links cause hypothesis scores to update correctly |
| `test_detective_analyzes_gaps` | Hypotheses with partial evidence produce correct gap classification (no_evidence, no_supporting, no_contradicting, weak_only) |
| `test_detective_calculates_quality_score` | Mixed evidence produces correct component scores (strength, diversity, coverage, discrimination) |
| `test_detective_suggests_alternative_paths` | Missing evidence types produce appropriate path suggestions (config_check, code_analysis, upstream_trace, temporal_analysis) |
| `test_detective_fallback_empty_orchestrator` | No LLM/KB produces empty evidence, no crash |
| `test_detective_fallback_queries` | LLM query generation fails; regex-based fallback produces valid queries from hypothesis descriptions |
| `test_detective_adaptive_strategy` | Code-centric mode skips log queries and prioritizes code queries |
| `test_detective_early_source_lookup` | Known function names in hypotheses trigger first-iteration source code lookup |
| `test_detective_binder_code_analysis` | Code snippets in binder produce code_analysis evidence via LLM |
| `test_detective_targeted_scoring` | Targeted evidence boosts/penalizes target hypothesis more than non-targeted |
| `test_detective_code_hint_match` | Evidence from code hint function gets bonus scoring |
| `test_detective_writes_to_binder` | Evidence items written to binder with correct targeting fields and hypothesis links |
| `test_detective_answer_question` | TROUBLESHOOT question produces evidence-based answer with citations |
| `test_detective_endorses_evidence_based` | Contribution citing evidence terms produces True endorsement |
| `test_detective_critique_no_evidence` | Contribution lacking evidence terms produces MEDIUM critique |
| `test_detective_stopping_conditions` | Clear winner, max iterations, and code hint lead all trigger stop correctly |

**Mock Requirements:** `LLMProvider` (for `generate_structured`, `generate`), `KnowledgeBase`, `WorkBinder` (with `get_code_snippets`, `get_hypotheses`, `add_evidence`, `link_evidence_to_hypothesis`, `update_artifact`), `EvidenceOrchestrator`, `InvestigationTools`, `CodeTools`, `CodeForensicsTools`, `PatternTools`, `EvidenceConfig`.

---

> [<- Architecture](agentic-persona-library-ch1-architecture.md) | [Table of Contents](agentic-persona-library.md) | [Next: Analysis Personas ->](agentic-persona-library-ch3-analysis-personas.md)
