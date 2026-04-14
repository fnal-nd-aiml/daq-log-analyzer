# Permissions Matrix Audit

## Purpose

This document audits the [Permissions Matrix](agentic-workbinder-library.md#permissions-matrix) against the actual artifact usage in LLM prompts across all investigation personas. The matrix documents which artifacts each persona can read (R), write (W), or read+write (RW). This audit verifies whether those read claims hold in the implementation.

---

## How Artifacts Reach LLM Prompts

There are three mechanisms by which binder artifacts are injected into persona LLM prompts:

1. **Relevance-based selection** (`srcs/workbinder/relevance.py`) — `render_selected_artifacts(binder, persona)` uses per-persona profiles (`PERSONA_PROFILES`) to select, rank, and render artifacts into prompt text. Each profile entry specifies an artifact type, a base priority (0.0–1.0), and a max count.

2. **Direct binder reads** — Persona code calls binder methods (`get_hypotheses()`, `get_log_bundle()`, `get_boardreader_identification()`, `get_merged_timeline()`, etc.) and formats the results into prompt placeholders or structured context.

3. **PriorKnowledge propagation** — The `PriorKnowledge` model carries Archivist-produced fields (`resolution_digest`, `configuration_context`, `diagnostic_history`, `enriched_case_summaries`, `documentation_context`) that downstream personas format into prompt placeholders.

Personas without a relevance profile rely entirely on direct reads and PriorKnowledge.

---

## Per-Persona Verification

### Phase -1: Chronicler — MATCHES

| Artifact | Matrix | Mechanism | Verified |
|----------|--------|-----------|----------|
| LOG_BUNDLE | W | `binder.add_log_bundle()` in `chronicler.py` | Yes |
| MERGED_TIMELINE | W | `binder.add_merged_timeline()` in `chronicler.py` | Yes |
| BOARDREADER_ID | W | `binder.add_boardreader_identification()` in `chronicler.py` | Yes |
| All others | - | Binder is empty at start of investigation | Yes |

No relevance profile. Chronicler only writes. No discrepancies.

---

### Phase 0: Archivist — MATCHES

| Artifact | Matrix | Mechanism | Verified |
|----------|--------|-----------|----------|
| LOG_BUNDLE | R | `binder.get_log_bundle()` in `archivist.py` — full narrative, primary_error, cascade_chain, affected_boards, clues | Yes |
| MERGED_TIMELINE | R | `binder.get_merged_timeline()` in `archivist.py` — stats only (counts, time span) | Yes |
| BOARDREADER_ID | R | `binder.get_boardreader_identification()` in `archivist.py` — boardreader_types, components | Yes |
| ERROR_CONTEXT | W | `binder.add_error_context()` via retrieval orchestrator | Yes |
| SOURCE_LOCATION | W | `binder.add_source_location()` via retrieval orchestrator | Yes |
| CALL_GRAPH | W | `binder.add_call_graph()` via retrieval orchestrator | Yes |
| CODE_SNIPPET | W | `binder.add_code_snippet()` via retrieval orchestrator | Yes |
| FUNCTION_SUMMARY | W | `binder.add_function_summary()` via retrieval orchestrator | Yes |

No relevance profile. Reads LOG_BUNDLE, MERGED_TIMELINE, and BOARDREADER_ID directly via `_format_summary_prompt()`. All three Chronicler artifacts are consumed both in the LLM prompt and programmatically (enrichment methods). No discrepancies.

---

### Phase 1: Theorist — MATCHES (with extras)

| Artifact | Matrix | Relevance Profile | Direct Read | Verified |
|----------|--------|--------------------|-------------|----------|
| LOG_BUNDLE | R | priority 1.0, max 1 | `_format_chronicler_context()` — narrative, cascade, boards, chain, primary_error, clues | Yes |
| MERGED_TIMELINE | R | — | `_format_chronicler_context()` — stats (counts, time span) | Yes |
| BOARDREADER_ID | R | — | `_format_chronicler_context()` — boardreader_types, components | Yes |
| ERROR_CONTEXT | R | priority 0.6, max 1 | — | Yes |
| SOURCE_LOCATION | R | priority 0.7, max 3 | — | Yes |
| CALL_GRAPH | R | priority 0.8, max 3 | — | Yes |
| CODE_SNIPPET | R | priority 0.8, max 3 | — | Yes |
| FUNCTION_SUMMARY | R | priority 0.9, max 5 | — | Yes |
| HYPOTHESIS | W | — | `binder.add_hypothesis()` | Yes |

**Direct reads added:** `_format_chronicler_context()` reads LOG_BUNDLE (primary_error as structured field, clues with suggested_search), BOARDREADER_ID (boardreader_types, components), and MERGED_TIMELINE (total_entries, total_errors, total_warnings, file_count, time span) directly from the binder, in addition to the relevance-profile-based LOG_BUNDLE inclusion.

**PriorKnowledge fields in prompt:** `_format_prior()` includes resolution_digest, configuration_context, diagnostic_history, documentation_context. `_format_prior_case_intelligence()` includes enriched_case_summaries, matched_patterns, similar_investigations.

**Extras not in matrix:** The Theorist's relevance profile also includes `PERSONA_CONTRIBUTION` (1.0, max 3) and `FINDING` (0.7, max 5). These are cross-cutting artifacts not tracked in the permissions matrix.

No discrepancies on tracked artifacts.

---

### Phase 2: Detective — MATCHES (with extras)

| Artifact | Matrix | Relevance Profile | Direct Read | Verified |
|----------|--------|--------------------|-------------|----------|
| LOG_BUNDLE | R | priority 0.9, max 1 | `_get_chronicler_context()` — primary_error, cascade_chain, affected_boards | Yes |
| MERGED_TIMELINE | R | — | `detective.py:prepare()` — entries converted to Log objects (component@board_name) | Yes |
| BOARDREADER_ID | R | — | `_get_chronicler_context()` — boardreader_types | Yes |
| ERROR_CONTEXT | R | priority 0.9, max 1 | From investigation context | Yes |
| SOURCE_LOCATION | R | priority 0.8, max 3 | From prior knowledge | Yes |
| CALL_GRAPH | R | priority 0.8, max 3 | From prior knowledge | Yes |
| CODE_SNIPPET | R | priority 0.8, max 5 | `_analyze_binder_code_snippets()` | Yes |
| FUNCTION_SUMMARY | R | priority 0.9, max 5 | From binder code analysis | Yes |
| FINDING | R | priority 0.7, max 5 | — | Yes |
| HYPOTHESIS | R | priority 1.0, max 10 | `binder.get_hypotheses()` via `_format_hypotheses()` — description, prior, score, evidence design | Yes |
| EVIDENCE | RW | priority 0.8, max 10 | `binder.add_evidence()` + reads own | Yes |

**Relevance profile** (`PERSONA_PROFILES["detective"]`): Now includes full verbatim artifact bodies from Chronicler (LOG_BUNDLE), Archivist (ERROR_CONTEXT, SOURCE_LOCATION, CALL_GRAPH, CODE_SNIPPET, FUNCTION_SUMMARY, FINDING), and Theorist (HYPOTHESIS_ARTIFACT, EVIDENCE_ARTIFACT) phases. Rendered via `render_selected_artifacts(binder, "detective")` in `EvidenceOrchestrator._get_artifact_context()` and injected into the `{artifact_context}` placeholder of the `evidence_query.md` user prompt.

**Chronicler artifact reads** (via `EvidenceOrchestrator._get_chronicler_context()`): LOG_BUNDLE (primary_error.message, cascade_chain as compact `from → to: mechanism`, affected_boards as `name (role)`), BOARDREADER_ID (boardreader_types). These are injected into the `{chronicler_context}` placeholder of the `evidence_query.md` user prompt.

**MERGED_TIMELINE entry conversion** (`detective.py:prepare()`): Full timeline entries are converted to Log objects for `InvestigationTools`. When both `component` and `board_name` exist and differ, they are combined as `component@board_name` to preserve board identity.

**PriorKnowledge fields in prompt** (via `EvidenceOrchestrator._get_upstream_context()`): resolution_digest (first 3 action strings), configuration_context.deviation_flags (first 3), diagnostic_history.common_root_causes (first 3 with frequency), enriched_case_summaries (first 2). These are injected into the `{upstream_context}` placeholder.

**System prompt:** `detective.md` includes an UPSTREAM CONTEXT section describing Chronicler and Archivist artifacts, plus an ARTIFACT REFERENCE section explaining each artifact type and how to use it for evidence seeking.

No discrepancies.

---

### Phase 3: Logician — 2 DISCREPANCIES

| Artifact | Matrix | Relevance Profile | Direct Read | Verified |
|----------|--------|--------------------|-------------|----------|
| LOG_BUNDLE | R | **not listed** | — | **NO** |
| MERGED_TIMELINE | R | **not listed** | — | **NO** |
| BOARDREADER_ID | R | **not listed** | — | **NO** |
| ERROR_CONTEXT | R | **not listed** | — | **NO** |
| SOURCE_LOCATION | R | priority 0.7, max 3 | — | Yes |
| CALL_GRAPH | R | priority 0.9, max 3 | — | Yes |
| CODE_SNIPPET | R | priority 0.9, max 5 | — | Yes |
| FUNCTION_SUMMARY | R | priority 1.0, max 5 | — | Yes |
| HYPOTHESIS | R | priority 0.8, max 5 | `binder.get_hypotheses()` | Yes |
| EVIDENCE | R | priority 0.8, max 10 | `binder.get_evidence_items()` | Yes |
| CAUSAL_CHAIN | W | — | `binder.add_causal_chain()` | Yes |

**Missing reads:**
- `LOG_BUNDLE` — Not in relevance profile, not read directly. Never reaches Logician LLM prompt.
- `MERGED_TIMELINE` — Not in relevance profile, not read directly.
- `BOARDREADER_ID` — Not in relevance profile, not read directly.
- `ERROR_CONTEXT` — Not in relevance profile, not read directly. Never reaches Logician LLM prompt.

**PriorKnowledge in prompt:** `documentation_context` only.

---

### Phase 4: Devil's Advocate (Skeptic) — 3 DISCREPANCIES

| Artifact | Matrix | Relevance Profile | Direct Read | Verified |
|----------|--------|--------------------|-------------|----------|
| LOG_BUNDLE | R | **not listed** | — | **NO** |
| MERGED_TIMELINE | R | **not listed** | — | **NO** |
| BOARDREADER_ID | R | **not listed** | — | **NO** |
| ERROR_CONTEXT | R | **not listed** | — | **NO** |
| SOURCE_LOCATION | R | **not listed** | — | **NO** |
| CALL_GRAPH | R | priority 0.7, max 3 | — | Yes |
| CODE_SNIPPET | R | priority 0.8, max 3 | — | Yes |
| FUNCTION_SUMMARY | R | priority 0.8, max 5 | — | Yes |
| HYPOTHESIS | R | priority 0.9, max 5 | `binder.get_hypotheses()` | Yes |
| EVIDENCE | R | priority 0.9, max 10 | `binder.get_evidence_items()` | Yes |
| CAUSAL_CHAIN | R | priority 1.0, max 5 | `binder.get_causal_chains()` | Yes |
| CHALLENGE | W | — | `binder.add_challenge()` | Yes |

**Missing reads:**
- `LOG_BUNDLE` — Not in relevance profile, not read directly.
- `MERGED_TIMELINE` — Not in relevance profile, not read directly.
- `BOARDREADER_ID` — Not in relevance profile, not read directly.
- `ERROR_CONTEXT` — Not in relevance profile, not read directly.
- `SOURCE_LOCATION` — Not in relevance profile, not read directly.

**PriorKnowledge in prompt:** `documentation_context` only.

---

### Phase 5: Judge — 6 DISCREPANCIES

| Artifact | Matrix | Relevance Profile | Direct Read | Verified |
|----------|--------|--------------------|-------------|----------|
| LOG_BUNDLE | R | **not listed** | — | **NO** |
| MERGED_TIMELINE | R | **not listed** | — | **NO** |
| BOARDREADER_ID | R | **not listed** | — | **NO** |
| ERROR_CONTEXT | R | **not listed** | — | **NO** |
| SOURCE_LOCATION | R | **not listed** | — | **NO** |
| CALL_GRAPH | R | **not listed** | — | **NO** |
| CODE_SNIPPET | R | **not listed** | — | **NO** |
| FUNCTION_SUMMARY | R | **not listed** | — | **NO** |
| HYPOTHESIS | R | priority 1.0, max 5 | `binder.get_hypotheses()` | Yes |
| EVIDENCE | R | priority 1.0, max 10 | `binder.get_evidence_items()` | Yes |
| CAUSAL_CHAIN | R | priority 0.9, max 5 | `binder.get_causal_chains()` | Yes |
| CHALLENGE | R | priority 0.9, max 10 | `binder.get_challenges()` | Yes |

**Missing reads:**
- `LOG_BUNDLE` — Not in relevance profile, not read directly.
- `MERGED_TIMELINE` — Not in relevance profile, not read directly.
- `BOARDREADER_ID` — Not in relevance profile, not read directly.
- `ERROR_CONTEXT` — Not in relevance profile, not read directly.
- `SOURCE_LOCATION` — Not in relevance profile, not read directly.
- `CALL_GRAPH` — Not in relevance profile, not read directly.
- `CODE_SNIPPET` — Not in relevance profile, not read directly.
- `FUNCTION_SUMMARY` — Not in relevance profile, not read directly.

The Judge reads no Phase -1 or Phase 0 artifacts at all. It operates entirely on Phase 1–4 investigation artifacts (hypotheses, evidence, chains, challenges) plus `PERSONA_CONTRIBUTION` from the Detective (evidence_quality_score, evidence_gap_analysis, alternative_paths).

---

### Phase 6: Synthesizer — 1 DISCREPANCY

| Artifact | Matrix | Relevance Profile | Direct Read | Verified |
|----------|--------|--------------------|-------------|----------|
| LOG_BUNDLE | R | priority 0.5, max 1 | — | Yes |
| MERGED_TIMELINE | R | **not listed** | — | **NO** |
| BOARDREADER_ID | R | **not listed** | — | **NO** |
| ERROR_CONTEXT | R | **not listed** | — | **NO** |
| SOURCE_LOCATION | R | priority 0.7, max 3 | `binder.get_source_locations()` | Yes |
| CALL_GRAPH | R | priority 0.7, max 3 | — | Yes |
| CODE_SNIPPET | R | priority 0.8, max 3 | — | Yes |
| FUNCTION_SUMMARY | R | priority 0.8, max 5 | — | Yes |
| HYPOTHESIS | R | priority 1.0, max 5 | Direct read | Yes |
| EVIDENCE | R | priority 1.0, max 10 | Direct read | Yes |
| CAUSAL_CHAIN | R | priority 0.9, max 5 | Direct read | Yes |
| CHALLENGE | R | priority 0.9, max 10 | Direct read | Yes |
| CONCLUSION | W | — | `binder.add_conclusion()` | Yes |

**Missing reads:**
- `MERGED_TIMELINE` — Not in relevance profile, not read directly.
- `BOARDREADER_ID` — Not in relevance profile, not read directly.
- `ERROR_CONTEXT` — Not in relevance profile, not read directly as a binder artifact. The error message does reach the Synthesizer through coordinator-level prompt placeholders, but not as a binder artifact read.

**PriorKnowledge in prompt:** `documentation_context` only.

**Extras not in matrix:** The Synthesizer's relevance profile also includes `FINDING` (0.6, max 5) and `PERSONA_CONTRIBUTION` (0.6, max 3).

---

## Discrepancy Summary

| Persona | Missing Artifact Reads (matrix says R, implementation does not) |
|---------|----------------------------------------------------------------|
| Logician (Phase 3) | `LOG_BUNDLE`, `MERGED_TIMELINE`, `BOARDREADER_ID`, `ERROR_CONTEXT` |
| Skeptic (Phase 4) | `LOG_BUNDLE`, `MERGED_TIMELINE`, `BOARDREADER_ID`, `ERROR_CONTEXT`, `SOURCE_LOCATION` |
| Judge (Phase 5) | `LOG_BUNDLE`, `MERGED_TIMELINE`, `BOARDREADER_ID`, `ERROR_CONTEXT`, `SOURCE_LOCATION`, `CALL_GRAPH`, `CODE_SNIPPET`, `FUNCTION_SUMMARY` |
| Synthesizer (Phase 6) | `MERGED_TIMELINE`, `BOARDREADER_ID`, `ERROR_CONTEXT` |

**Total: 20 matrix cells claim R but the artifact is not fed into the persona's LLM prompt.**

### Corrected Matrix (reflecting actual implementation)

| Artifact | -1: Chronicler | 0: Archivist | 1: Theorist | 2: Detective | 3: Logician | 4: Devil's Advocate | 5: Judge | 6: Synthesizer |
|----------|----------------|--------------|-------------|--------------|-------------|---------------------|----------|----------------|
| LOG_BUNDLE | W | R | R | R | **-** | **-** | **-** | R |
| MERGED_TIMELINE | W | R | R | R | **-** | **-** | **-** | **-** |
| BOARDREADER_ID | W | R | R | R | **-** | **-** | **-** | **-** |
| ERROR_CONTEXT | - | W | R | R | **-** | **-** | **-** | **-** |
| SOURCE_LOCATION | - | W | R | R | R | **-** | **-** | R |
| CALL_GRAPH | - | W | R | R | R | R | **-** | R |
| CODE_SNIPPET | - | W | R | R | R | R | **-** | R |
| FUNCTION_SUMMARY | - | W | R | R | R | R | **-** | R |
| HYPOTHESIS | - | - | W | R | R | R | R | R |
| EVIDENCE | - | - | - | RW | R | R | R | R |
| CAUSAL_CHAIN | - | - | - | - | W | R | R | R |
| CHALLENGE | - | - | - | - | - | W | R | R |
| CONCLUSION | - | - | - | - | - | - | - | W |

Cells that changed from the original matrix are shown in **bold**.

---

## PriorKnowledge Propagation

The `PriorKnowledge` model carries Archivist-produced fields that are not binder artifacts but flow through the pipeline via the `prior` parameter. This table shows which fields reach each persona's LLM prompt:

| PriorKnowledge Field | 0: Archivist | 1: Theorist | 2: Detective | 3: Logician | 4: Skeptic | 6: Synthesizer |
|---------------------|:---:|:---:|:---:|:---:|:---:|:---:|
| `matched_patterns` | R | R | - | - | - | - |
| `similar_investigations` | R | R | - | - | - | - |
| `source_locations` | R | R | - | - | - | - |
| `recommended_hypotheses` | - | R | - | - | - | - |
| `enriched_case_summaries` | - | R | R | - | - | - |
| `resolution_digest` | - | R | R | - | - | - |
| `configuration_context` | - | R | R | - | - | - |
| `diagnostic_history` | - | R | R | - | - | - |
| `documentation_context` | - | R | R | R | R | R |
| `code_hints` | - | R (via hyp) | - | - | - | - |

The Detective's PriorKnowledge reads (resolution_digest, configuration_context, diagnostic_history, enriched_case_summaries) are via `EvidenceOrchestrator._get_upstream_context()`, injected into the `{upstream_context}` placeholder in `evidence_query.md`.

---

## Assessment

The discrepancies follow a clear pattern: the matrix documents an idealized "read-forward" model where every later phase can read every earlier artifact. The implementation is more selective — each persona only reads the artifacts relevant to its task.

This is intentional design rather than a bug:

- **Judge** operates on distilled investigation artifacts (hypotheses, evidence, chains, challenges) to assess sufficiency. Raw code and log context would add noise to an outcome-determination prompt.
- **Logician** constructs causal chains from hypotheses, evidence, and code context. It does not need the raw merged log timeline or the original error context artifact since the relevant information is already distilled into hypotheses and evidence.
- **Skeptic** challenges reasoning structure. Source locations and raw Chronicler artifacts are less relevant than the causal chain and evidence it critiques.

However, there are cases where adding missing artifacts could improve prompt quality:

| Candidate | Rationale |
|-----------|-----------|
| Logician + ERROR_CONTEXT | The error message helps ground causal chains in the actual failure |
| Skeptic + SOURCE_LOCATION | Source locations help validate code-based claims in causal chains |
| Synthesizer + ERROR_CONTEXT | The error context artifact has richer detail than the prompt placeholder |

---

## Cross-Cutting Artifacts Not Tracked in Matrix

The following artifact types are read by personas but not listed in the permissions matrix:

| Artifact | Personas That Read It |
|----------|-----------------------|
| PERSONA_CONTRIBUTION | Theorist, Judge, Synthesizer |
| FINDING | Theorist, Synthesizer |

These are cross-cutting artifacts that any persona can write at any time. Consider adding them to the matrix or documenting them as out-of-scope.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-02-22 | Added MERGED_TIMELINE and BOARDREADER_ID rows to all persona tables |
| 2026-02-22 | Updated Archivist: now reads MERGED_TIMELINE (stats) and BOARDREADER_ID directly |
| 2026-02-22 | Updated Theorist: now reads MERGED_TIMELINE (stats), BOARDREADER_ID, LOG_BUNDLE.primary_error, and LOG_BUNDLE.clues via `_format_chronicler_context()` |
| 2026-02-22 | Updated Detective: now reads LOG_BUNDLE (primary_error, cascade_chain, affected_boards) and BOARDREADER_ID via `_get_chronicler_context()`; reads resolution_digest, configuration_context, diagnostic_history, enriched_case_summaries via `_get_upstream_context()`; preserves MERGED_TIMELINE board_name as `component@board_name` |
| 2026-02-22 | Added PriorKnowledge Propagation table |
| 2026-02-22 | Updated discrepancy count from 12 to 20 (MERGED_TIMELINE and BOARDREADER_ID added as missing reads for Logician, Skeptic, Judge, Synthesizer) |
| 2026-02-22 | Added mechanism 3 (PriorKnowledge propagation) to "How Artifacts Reach LLM Prompts" |

---

## Source References

| File | Role |
|------|------|
| `srcs/workbinder/relevance.py:30-84` | `PERSONA_PROFILES` defining per-persona artifact selection |
| `srcs/persona/chronicler.py` | Chronicler implementation |
| `srcs/persona/archivist.py` | Archivist implementation |
| `srcs/persona/theorist.py` | Theorist implementation |
| `srcs/persona/detective.py` | Detective implementation |
| `srcs/persona/orchestration/evidence_orchestrator.py` | Detective evidence orchestrator (Chronicler/upstream context) |
| `srcs/persona/logician.py` | Logician implementation |
| `srcs/persona/skeptic.py` | Skeptic implementation |
| `srcs/persona/judge.py` | Judge implementation |
| `srcs/persona/synthesizer.py` | Synthesizer implementation |
| `srcs/persona/orchestration/retrieval_orchestrator.py` | Archivist retrieval orchestrator |
| `srcs/prompts/templates/user/evidence_query.md` | Detective user prompt template |
| `srcs/prompts/templates/system/theorist.md` | Theorist system prompt (CHRONICLER CONTEXT section) |
| `srcs/prompts/templates/system/detective.md` | Detective system prompt (UPSTREAM CONTEXT section) |
| `docs/agentic-workbinder-library.md` | Original permissions matrix |
