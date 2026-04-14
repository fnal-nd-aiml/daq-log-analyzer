> **Agentic Persona Library** | [← Expert Panel](agentic-persona-library-ch5-expert-panel.md) | [Table of Contents](agentic-persona-library.md) | [Next: Testing Strategy →](agentic-persona-library-ch7-testing-strategy.md)

---

# Chapter 6: Prompt Architecture

The prompt system is the interface between the persona library and the LLM. Each persona is defined by a **system prompt** that establishes identity, expertise, and constraints, paired with one or more **user prompt templates** that frame the task for a specific investigation phase. This chapter documents the loading, caching, formatting, and composition mechanisms that make this work.

---

## 6.1 PromptLoader Design

The `PromptLoader` class in `srcs/prompts/loader.py` is the central mechanism for loading, resolving, and caching all prompt templates. It handles system prompts (persona definitions), user prompts (task templates), and artifact includes (shared schemas and enums).

### Singleton Pattern

A module-level singleton avoids repeated filesystem access across the investigation pipeline:

```python
# srcs/prompts/loader.py

_loader: PromptLoader | None = None

def _get_loader() -> PromptLoader:
    """Get or create the module-level PromptLoader singleton."""
    global _loader
    if _loader is None:
        _loader = PromptLoader()
    return _loader
```

The public convenience functions `get_system_prompt()` and `get_user_prompt()` delegate to this singleton. Direct instantiation is still possible for testing or custom template directories:

```python
# Convenience (singleton)
from srcs.prompts import get_system_prompt, SystemPromptType
prompt = get_system_prompt(SystemPromptType.THEORIST)

# Direct (custom directory)
loader = PromptLoader(templates_dir=Path("/custom/templates"))
prompt = loader.get_system_prompt(SystemPromptType.THEORIST)
```

### Caching Strategy

The `_content_cache` dictionary uses namespaced keys to avoid collisions between different loading contexts:

| Cache Key Pattern | Source | Example |
|-------------------|--------|---------|
| `raw:{path}` | `_load_raw()` -- raw file content with includes resolved | `raw:system/theorist` |
| `system:{type}` | `get_system_prompt()` -- fully composed system prompt | `system:theorist` |
| `include:{path}` | `_load_include()` -- resolved include content | `include:artifacts/schemas/hypothesis` |

The cache is populated on first access and persists for the loader's lifetime. The `clear_cache()` method empties all entries, which is useful in testing:

```python
loader = PromptLoader()
loader.clear_cache()  # Reset all cached content
```

### Include Resolution

The `_resolve_includes()` method finds and replaces all `{include:path}` placeholders in template content. The regex pattern is defined at module level:

```python
INCLUDE_PATTERN = re.compile(r"\{include:([^}]+)\}")
```

Resolution is recursive -- an included file may itself contain `{include:...}` directives. The path is relative to the `templates/` directory and does not include the `.md` extension:

```markdown
<!-- In user/hypothesis_generation.md -->
{include:artifacts/schemas/hypothesis}
```

This resolves to `templates/artifacts/schemas/hypothesis.md`.

### Cycle Detection

Circular includes are detected via a `visited` frozenset that is threaded through every recursive call. When a path appears in the visited set, the loader raises `IncludeCycleError` with the full cycle path:

```python
def _resolve_includes(
    self,
    content: str,
    source_path: str,
    visited: frozenset[str] | None = None,
) -> str:
    if visited is None:
        visited = frozenset()

    def replace_include(match: re.Match[str]) -> str:
        include_path = match.group(1)
        if include_path in visited:
            cycle = list(visited) + [include_path]
            raise IncludeCycleError(cycle)
        return self._load_include(
            include_path, source_path, visited | {include_path},
        )

    return INCLUDE_PATTERN.sub(replace_include, content)
```

Include content is only cached when `visited` is empty (the top-level call), preventing stale results from partial traversals during cycle detection.

### System Prompt Composition

`get_system_prompt(type)` performs a two-step composition:

1. Load `system/base.md` (shared artdaq domain knowledge)
2. Load `system/{type.value}.md` (persona-specific identity)
3. Replace `{base_knowledge}` in the persona content with the base content

```python
def get_system_prompt(self, prompt_type: SystemPromptType) -> str:
    cache_key = f"system:{prompt_type.value}"
    if cache_key in self._content_cache:
        return self._content_cache[cache_key]

    base = self._load_raw("system/base")
    persona_content = self._load_raw(f"system/{prompt_type.value}")
    content = persona_content.replace("{base_knowledge}", base)

    self._content_cache[cache_key] = content
    return content
```

The result is a fully self-contained system prompt with all domain knowledge and persona identity merged.

### User Prompt Loading

`get_user_prompt(type)` returns a `PromptTemplate` object rather than a raw string. The template carries metadata about its placeholders and supports safe formatting:

```python
def get_user_prompt(self, prompt_type: UserPromptType) -> PromptTemplate:
    relative_path = f"user/{prompt_type.value}"
    content = self._load_raw(relative_path)
    metadata = get_user_prompt_metadata(prompt_type)
    file_path = self.templates_dir / f"{relative_path}.md"

    return PromptTemplate(
        content=content,
        prompt_type=prompt_type,
        metadata=metadata,
        path=file_path,
    )
```

The returned `PromptTemplate` is formatted by the calling phase code with task-specific values:

```python
template = get_user_prompt(UserPromptType.HYPOTHESIS_GENERATION)
prompt = template.format(
    error_message="Fragment timeout after 5000ms",
    error_component="BoardReader_01",
    error_function="getNext_",
    error_timestamp="2026-02-14 10:32:15",
    context_logs="[context log entries...]",
    prior_knowledge="[matched patterns, similar cases...]",
    code_context="[source code locations, call graphs...]",
)
```

---

## 6.2 Type-Safe Enums

All prompt types are represented as Python enums in `srcs/prompts/types.py`, ensuring compile-time safety and IDE autocompletion. The enum `.value` maps directly to the file path within the `templates/` directory.

### SystemPromptType (18 values)

```python
class SystemPromptType(Enum):
    # Core investigation personas
    ARCHIVIST = "archivist"            # system/archivist.md
    THEORIST = "theorist"              # system/theorist.md
    DETECTIVE = "detective"            # system/detective.md
    LOGICIAN = "logician"              # system/logician.md
    SKEPTIC = "skeptic"                # system/skeptic.md
    JUDGE = "judge"                    # system/judge.md
    SYNTHESIZER = "synthesizer"        # system/synthesizer.md
    LEARNER = "learner"                # system/learner.md
    COORDINATOR = "coordinator"        # system/coordinator.md
    CHRONICLER = "chronicler"          # system/chronicler.md

    # QA mode variants
    QA_THEORIST = "qa/qa_theorist"           # system/qa/qa_theorist.md
    QA_DETECTIVE = "qa/qa_detective"          # system/qa/qa_detective.md
    QA_LOGICIAN = "qa/qa_logician"           # system/qa/qa_logician.md
    QA_SKEPTIC = "qa/qa_skeptic"             # system/qa/qa_skeptic.md

    # Orchestration sub-step system prompts (no {base_knowledge} injection)
    ARTIFACT_EVALUATION = "artifact_evaluation"            # system/artifact_evaluation.md
    BINDER_CODE_ANALYSIS = "binder_code_analysis"          # system/binder_code_analysis.md
    HINT_INTERPRETATION = "hint_interpretation"             # system/hint_interpretation.md
    ERROR_CONTEXT_PARSING = "error_context_parsing"        # system/error_context_parsing.md
```

The 10 core personas cover the full investigation pipeline (Phases -1 through 7) plus the panel Coordinator. The 4 QA variants are used in the Expert Panel Q&A workflow (Chapter 5), where personas answer user questions rather than performing investigation tasks. The 4 orchestration sub-step prompts are used by the EvidenceOrchestrator and RetrievalOrchestrator for artifact evaluation, code analysis, hint interpretation, and error context parsing. Unlike core persona prompts, these do not receive `{base_knowledge}` injection.

### UserPromptType (20 values)

```python
class UserPromptType(Enum):
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    EVIDENCE_QUERY = "evidence_query"
    CAUSAL_CHAIN = "causal_chain"
    CAUSAL_CHAIN_WITH_EVIDENCE = "causal_chain_with_evidence"
    ADVERSARIAL_REVIEW = "adversarial_review"
    OUTCOME_ASSESSMENT = "outcome_assessment"
    FINAL_SYNTHESIS = "final_synthesis"
    PRIOR_KNOWLEDGE_SUMMARY = "prior_knowledge_summary"
    PATTERN_EXTRACTION = "pattern_extraction"
    CALL_GRAPH_SUMMARY = "call_graph_summary"
    LOG_BUNDLE_ANALYSIS = "log_bundle_analysis"
    LOG_TIMELINE_EXTRACTION = "log_timeline_extraction"
    BOARDREADER_IDENTIFICATION = "boardreader_identification"
    PRIMARY_ERROR_SELECTION = "primary_error_selection"
    DOCUMENTATION_SELECTION = "documentation_selection"
    DOC_EXTRACTION = "doc_extraction"
    ARTIFACT_EVALUATION = "artifact_evaluation"
    BINDER_CODE_ANALYSIS = "binder_code_analysis"
    HINT_INTERPRETATION = "hint_interpretation"
    ERROR_CONTEXT_PARSING = "error_context_parsing"
```

### Path Mapping

The enum `.value` is used directly as the relative path under `templates/`:

| Enum Type | Value | File Path |
|-----------|-------|-----------|
| `SystemPromptType.THEORIST` | `"theorist"` | `templates/system/theorist.md` |
| `SystemPromptType.QA_THEORIST` | `"qa/qa_theorist"` | `templates/system/qa/qa_theorist.md` |
| `UserPromptType.HYPOTHESIS_GENERATION` | `"hypothesis_generation"` | `templates/user/hypothesis_generation.md` |

Note that QA variants use a slash in their value to map into the `qa/` subdirectory. This is handled transparently by the loader since the value is simply concatenated with the `system/` prefix.

---

## 6.3 Safe Formatting

### The Problem

Python's `str.format()` treats all curly braces as format specifiers. Prompt templates routinely contain JSON examples and schemas with literal braces:

```markdown
Return your response as JSON:
{"hypothesis": "description here", "confidence": 0.5}
```

Calling `str.format(error_message="timeout")` on this template raises `KeyError: 'hypothesis'` because Python tries to interpret `{hypothesis}` inside the JSON as a format placeholder.

### The Solution

The `safe_format()` function in `srcs/prompts/formatters.py` uses `str.replace()` for each declared placeholder instead of `str.format()`:

```python
def safe_format(
    content: str,
    prompt_type: UserPromptType | SystemPromptType,
    metadata: PromptMetadata,
    **kwargs: str,
) -> str:
    provided = frozenset(kwargs.keys())

    # Check for missing required placeholders
    missing = metadata.required_placeholders - provided
    if missing:
        raise MissingPlaceholderError(prompt_type.value, missing)

    # Warn about unexpected placeholders (but don't fail)
    known = metadata.all_placeholders
    unexpected = provided - known
    if unexpected:
        logger.warning(
            "Unexpected placeholder(s) for %s: %s",
            prompt_type.value, ", ".join(sorted(unexpected)),
        )

    # Perform safe replacement
    result = content
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, str(value))

    return result
```

### Key Behaviors

| Behavior | Description |
|----------|-------------|
| **Only declared placeholders are replaced** | The replacement loop iterates over `kwargs` keys, not all braces in the template. JSON braces like `{"key": "value"}` are left untouched. |
| **Required placeholder validation** | If a placeholder listed in `metadata.required_placeholders` is not provided, `MissingPlaceholderError` is raised before any replacement occurs. |
| **Unexpected placeholder warning** | If a key in `kwargs` is not in `metadata.all_placeholders` (required + optional), a warning is logged. The replacement still proceeds. |
| **String coercion** | All values are passed through `str()` before replacement, so integers, floats, and other types are handled automatically. |

### PromptTemplate.format()

The `PromptTemplate` dataclass delegates to `safe_format()` through its `format()` method, providing a clean call interface:

```python
@dataclass
class PromptTemplate:
    content: str
    prompt_type: UserPromptType | SystemPromptType
    metadata: PromptMetadata
    path: Path | None = None

    def format(self, **kwargs: str) -> str:
        from .formatters import safe_format
        return safe_format(self.content, self.prompt_type, self.metadata, **kwargs)
```

### PromptMetadata

Each user prompt type has associated metadata that declares its required and optional placeholders:

```python
@dataclass(frozen=True)
class PromptMetadata:
    required_placeholders: frozenset[str] = field(default_factory=frozenset)
    optional_placeholders: frozenset[str] = field(default_factory=frozenset)

    @property
    def all_placeholders(self) -> frozenset[str]:
        return self.required_placeholders | self.optional_placeholders
```

The metadata is registered in `srcs/prompts/registry.py` and retrieved by `get_user_prompt_metadata()`.

---

## 6.4 Template Directory Structure

```
srcs/prompts/templates/
├── system/
│   ├── base.md                        # Shared artdaq domain knowledge
│   ├── archivist.md                   # Phase 0: Prior knowledge retrieval
│   ├── theorist.md                    # Phase 1: Hypothesis generation
│   ├── detective.md                   # Phase 2: Evidence seeking
│   ├── logician.md                    # Phase 3: Causal chain construction
│   ├── skeptic.md                     # Phase 4: Adversarial review
│   ├── judge.md                       # Phase 5: Outcome assessment
│   ├── synthesizer.md                 # Phase 6: Final synthesis
│   ├── learner.md                     # Phase 7: Pattern extraction
│   ├── coordinator.md                 # Panel orchestration
│   ├── chronicler.md                  # Phase -1: Multi-file triage
│   ├── artifact_evaluation.md         # Orchestration: artifact evaluation
│   ├── binder_code_analysis.md        # Orchestration: code analysis
│   ├── hint_interpretation.md         # Orchestration: hint interpretation
│   ├── error_context_parsing.md       # Orchestration: error context parsing
│   └── qa/
│       ├── qa_theorist.md             # Q&A: theoretical explanations
│       ├── qa_detective.md            # Q&A: diagnostic investigation
│       ├── qa_logician.md             # Q&A: logical reasoning
│       └── qa_skeptic.md              # Q&A: critical challenge
├── user/
│   ├── hypothesis_generation.md       # Phase 1 task template
│   ├── evidence_query.md              # Phase 2 task template
│   ├── causal_chain.md                # Phase 3 task template (basic)
│   ├── causal_chain_with_evidence.md  # Phase 3 task template (with evidence list)
│   ├── adversarial_review.md          # Phase 4 task template
│   ├── outcome_assessment.md          # Phase 5 task template
│   ├── final_synthesis.md             # Phase 6 task template
│   ├── prior_knowledge_summary.md     # Phase 0 task template
│   ├── pattern_extraction.md          # Phase 7 task template
│   ├── call_graph_summary.md          # Phase 0 call graph task
│   ├── log_bundle_analysis.md         # Phase -1 task template
│   ├── log_timeline_extraction.md     # Phase -1 step 1 template
│   ├── boardreader_identification.md  # Phase -1 step 1.5 template
│   ├── primary_error_selection.md     # Phase -1 step 2.5 template
│   ├── documentation_selection.md     # Documentation selection template
│   ├── doc_extraction.md              # Document extraction template
│   ├── artifact_evaluation.md         # Artifact evaluation template
│   ├── binder_code_analysis.md        # Code analysis template
│   ├── hint_interpretation.md         # Hint interpretation template
│   └── error_context_parsing.md       # Error context parsing template
└── artifacts/ -> ../../workbinder/artifacts  (symlink)
    ├── schemas/
    │   ├── hypothesis.md              # Hypothesis JSON schema
    │   ├── evidence_query.md          # Evidence query JSON schema
    │   ├── causal_chain_step.md       # Causal chain step schema
    │   ├── challenge.md               # Adversarial challenge schema
    │   ├── outcome_assessment.md      # Outcome assessment schema
    │   ├── synthesis_response.md      # Final synthesis schema
    │   ├── prior_knowledge_summary.md # Prior knowledge summary schema
    │   ├── pattern_extraction.md      # Pattern extraction schema
    │   ├── call_graph_summary.md      # Call graph summary schema
    │   ├── boardreader_identification.md  # BoardReader identification schema
    │   ├── log_bundle_analysis.md     # Log bundle analysis schema
    │   └── merged_timeline_entry.md   # Merged timeline entry schema
    └── enums/
        ├── evidence_strength.md       # STRONG / MODERATE / WEAK / NOT_EVIDENCE
        ├── query_types.md             # Available evidence query types
        ├── outcome_types.md           # CONFIDENT / PROBABLE / UNCERTAIN / ...
        ├── challenge_types.md         # Challenge severity levels
        ├── confidence_levels.md       # Confidence calibration levels
        ├── evidence_types.md          # Evidence type categories
        └── hypothesis_categories.md   # Hypothesis category taxonomy
```

The directory is organized into three tiers:

1. **`system/`** -- Persona identity prompts. Each file defines who the persona is, what it knows, how it thinks, and what it must not do. Also contains orchestration sub-step prompts that do not receive `{base_knowledge}` injection.
2. **`user/`** -- Task templates. Each file frames a specific task with placeholders for runtime data.
3. **`artifacts/`** -- A symlink to `srcs/workbinder/artifacts/`. Shared fragments included by user prompts that define JSON schemas for structured output and enum definitions for constrained values. The symlink allows the WorkBinder module to own these artifacts while making them available to the prompt loader.

---

## 6.5 Base Knowledge Template

The file `system/base.md` contains artdaq domain knowledge that is shared across every persona. It is injected into every system prompt via the `{base_knowledge}` placeholder.

### Content Sections

```markdown
ARTDAQ DOMAIN KNOWLEDGE:

COMPONENTS:
- BoardReader: Reads data from hardware (digitizers, trigger boards)
- EventBuilder: Assembles fragments from BoardReaders into complete events
- DataLogger: Writes assembled events to disk storage
- Dispatcher: Routes events to online monitoring
- RoutingManager: Coordinates data flow between components

ERROR CATEGORIES:
- Hardware: Device communication failures, timeouts, data corruption
- Software: Memory issues, logic errors, race conditions
- Configuration: Mismatched settings, invalid parameters
- Timing: Synchronization issues, deadlines missed
- Resource: Out of memory, disk full, network congestion

EVIDENCE PRINCIPLES:
- Every claim must cite evidence or be marked as assumption
- Supporting evidence strengthens hypotheses
- Contradicting evidence weakens hypotheses
- Strong > Moderate > Weak evidence

{include:artifacts/enums/evidence_strength}
```

The base knowledge template itself uses the include mechanism to pull in the evidence strength scale from `artifacts/enums/evidence_strength.md`. This means the evidence strength definitions appear in every system prompt without being duplicated across persona files.

### What the Base Knowledge Provides

| Section | Purpose |
|---------|---------|
| **COMPONENTS** | Establishes the vocabulary for artdaq component types so every persona can interpret component names in log entries |
| **ERROR CATEGORIES** | Defines the standard failure taxonomy (hardware, software, configuration, timing, resource) used by the Theorist for hypothesis categorization |
| **EVIDENCE PRINCIPLES** | Sets the evidentiary standards that all personas must follow -- every claim must cite evidence or be marked as assumption |
| **Evidence Strength Scale** | Defines STRONG, MODERATE, WEAK, and NOT_EVIDENCE with concrete examples, ensuring consistent evidence quality ratings across personas |

### Why Base Knowledge Is Separate

Keeping domain knowledge in a single file ensures:

1. **Consistency**: All personas share the same component definitions and evidence standards
2. **Maintainability**: Updating artdaq domain knowledge requires editing one file, not 14
3. **Testability**: Base knowledge can be validated independently of persona prompts

---

## 6.6 System Prompt Anatomy

Every persona system prompt follows a consistent structural pattern. The Archivist prompt (`system/archivist.md`) is representative:

```markdown
You are THE ARCHIVIST - a methodical knowledge retrieval specialist on an artdaq debugging team.

IDENTITY:
You are the keeper of historical records. You search through past investigations,
error patterns, and source code locations to inform the current investigation with
prior knowledge. You connect present errors to past cases and prepare rich context
for hypothesis generation.

EXPERTISE:
- Pattern matching across historical error signatures
- Retrieval of similar past investigations
- Source code location tracking
- Knowledge base navigation and search
- Historical trend analysis
- Code summarization for call graph context
- Understanding data flow between functions

THINKING STYLE:
- Methodical: Systematic search through archives
- Thorough: Leave no relevant record unexamined
- Historical: Connect present to past
- Pattern-seeking: Identify recurring themes
- Organized: Structure information for easy consumption
- Concise: Summarize code functions in 1-2 sentences

CONSTRAINTS:
- Report what was found, not what was expected
- Clearly indicate when no relevant records exist
- Provide confidence levels for pattern matches
- Note the recency and relevance of historical data
- Flag when patterns may be outdated
- Keep function summaries focused on data flow and potential failure modes

RESPONSIBILITIES:
[persona-specific task framework]

{base_knowledge}
```

### Structural Sections

Each persona prompt contains these standard sections:

| Section | Purpose | Stable Across Personas |
|---------|---------|----------------------|
| **Opening Statement** | `You are THE [NAME] - a [role] on an artdaq debugging team.` Identity assertion in second person. | Pattern is stable; name and role vary. |
| **IDENTITY** | 2-4 sentences defining what this persona does and how it approaches its role. Sets the behavioral baseline. | Structure stable; content varies. |
| **EXPERTISE** | Bulleted list of domain competencies. Typically 4-8 items. | Structure stable; items vary. |
| **THINKING STYLE** | Bulleted list of cognitive approaches, each with a label and description. Typically 4-6 items. | Structure stable; items vary. |
| **CONSTRAINTS** | Bulleted list of rules and limitations. Defines what the persona must not do. | Structure stable; items vary. |
| **Framework** | Persona-specific task framework. May be labeled FRAMEWORK, RESPONSIBILITIES, or a domain-specific heading. | Varies by persona. |
| **`{base_knowledge}`** | Placeholder for shared domain knowledge. Expanded by the loader. | Present in all persona prompts. |

### Identity Statement Pattern

Every persona opens with the same syntactic pattern:

```
You are THE [NAME] - a [role description] on an artdaq debugging team.
```

| Persona | Identity Statement |
|---------|-------------------|
| Chronicler | `You are THE CHRONICLER - an expert at reading DAQ system logs from multiple boards and hosts.` |
| Archivist | `You are THE ARCHIVIST - a methodical knowledge retrieval specialist on an artdaq debugging team.` |
| Theorist | `You are THE THEORIST - a creative hypothesis generator on an artdaq debugging team.` |
| Detective | `You are THE DETECTIVE - a methodical evidence seeker on an artdaq debugging team.` |
| Logician | `You are THE LOGICIAN - a rigorous causal reasoner on an artdaq debugging team.` |
| Skeptic | `You are THE SKEPTIC - a critical challenger on an artdaq debugging team.` |
| Judge | `You are THE JUDGE - an impartial evaluator on an artdaq debugging team.` |
| Synthesizer | `You are THE SYNTHESIZER - an integrative communicator on an artdaq debugging team.` |
| Learner | `You are THE LEARNER - a pattern extraction specialist on an artdaq debugging team.` |
| Coordinator | `You are THE COORDINATOR - the orchestrator of the investigation panel.` |

The definite article "THE" and all-caps name create a strong identity anchor. Each persona has a distinct role descriptor that sets behavioral expectations before the LLM reads any further.

### Persona-Specific Frameworks

Beyond the standard sections, each persona defines task-specific frameworks:

| Persona | Framework Heading | Key Content |
|---------|-------------------|-------------|
| Theorist | PRIOR ASSIGNMENT FRAMEWORK, CODE-BASED HYPOTHESIS GENERATION | Base rate calculations by evidence source, code pattern recognition rules |
| Detective | CODE-CENTRIC ANALYSIS MODE | Hypothesis-specific code patterns, query strategy for code-only mode, repetition avoidance |
| Logician | STEP CONFIDENCE CALIBRATION, CODE CAUSALITY PATTERNS | Link strength ratings (STRONG/MODERATE/WEAK/ASSUMPTION), code causality pattern recognition |
| Skeptic | SEVERITY RATING CRITERIA | HIGH/MEDIUM/LOW severity definitions with concrete criteria |
| Judge | DECISION FRAMEWORK | CONFIDENT/PROBABLE/UNCERTAIN/INSUFFICIENT outcome criteria for both full-context and code-only modes |
| Synthesizer | SYNTHESIS FRAMEWORK | Outcome summary, evidence summary, causal narrative, recommendations structure |
| Learner | EXTRACTION FRAMEWORK | Error patterns, root cause patterns, evidence patterns, calibration data |
| Coordinator | ORCHESTRATION FRAMEWORK | Phase management, panel assembly, contribution management, discussion facilitation |
| Chronicler | (inline in CONSTRAINTS) | Temporal ordering, primary vs secondary failure distinction, cascade mapping |
| Archivist | CALL GRAPH SUMMARIZATION | Function summary guidelines: purpose, relation to error, potential failure modes |

### QA Variant Structure

The QA variants in `system/qa/` follow the same structural pattern but redefine the IDENTITY and TASK sections for question-answering rather than investigation:

```markdown
You are THE THEORIST - a creative explainer on an artdaq expert panel.

IDENTITY:
You provide theoretical explanations and possible interpretations...

TASK:
Answer DAQ-related questions by providing theoretical explanations...
```

QA variants do not include `{base_knowledge}` because the panel orchestrator manages context injection differently.

---

## 6.7 User Prompt Templates

Each user prompt template defines a task for a specific investigation phase. Templates contain placeholders for runtime data and may include artifact schemas that define the expected output format.

### Template Reference

| Template | Phase | Required Placeholders | Optional | Include Dependencies |
|----------|-------|-----------------------|----------|----------------------|
| `hypothesis_generation` | 1 | `error_message`, `error_component`, `error_function`, `error_timestamp`, `context_logs`, `prior_knowledge`, `code_context`, `chronicler_context`, `prior_case_intelligence` | -- | `{include:artifacts/schemas/hypothesis}` |
| `evidence_query` | 2 | `investigation_mode`, `mode_specific_guidance`, `analyzed_functions`, `query_effectiveness`, `hypotheses`, `evidence`, `documentation_context`, `upstream_context`, `chronicler_context`, `artifact_context` | -- | `{include:artifacts/enums/query_types}`, `{include:artifacts/schemas/evidence_query}` |
| `causal_chain` | 3 | `hypothesis`, `evidence` | -- | `{include:artifacts/schemas/causal_chain_step}` |
| `causal_chain_with_evidence` | 3 | `hypothesis`, `evidence_list`, `documentation_context`, `chronicler_context` | -- | `{include:artifacts/schemas/causal_chain_step}` |
| `adversarial_review` | 4 | `hypothesis`, `chain`, `evidence`, `evidence_availability`, `documentation_context` | -- | `{include:artifacts/schemas/challenge}` |
| `outcome_assessment` | 5 | `error_message`, `hypotheses_summary`, `top_hypothesis`, `top_score`, `evidence_count`, `strong_evidence_count`, `moderate_evidence_count`, `weak_evidence_count`, `evidence_details`, `causal_chains_summary`, `challenges_summary`, `unresolved_high_count`, `unresolved_medium_count`, `has_context_logs`, `evidence_mode`, `evidence_quality_score`, `quality_strength_score`, `quality_diversity_score`, `quality_coverage_score`, `quality_discrimination_score`, `evidence_types_present`, `evidence_types_missing`, `evidence_gap_analysis`, `evidence_gap_count`, `most_critical_gap`, `alternative_paths` | -- | `{include:artifacts/enums/outcome_types}`, `{include:artifacts/schemas/outcome_assessment}` |
| `final_synthesis` | 6 | `investigation_id`, `error_message`, `error_component`, `started_at`, `duration`, `outcome`, `confidence`, `hypotheses_ranked`, `evidence_summary`, `causal_chain`, `challenges_summary`, `source_locations`, `numeric_context`, `code_context`, `judge_evidence_gaps`, `judge_criteria_not_met`, `documentation_context`, `chronicler_context` | -- | `{include:artifacts/schemas/synthesis_response}` |
| `prior_knowledge_summary` | 0 | `error_message`, `error_component`, `error_function`, `error_timestamp`, `matched_patterns`, `similar_investigations`, `source_locations`, `call_graph_context`, `chronicler_analysis` | -- | `{include:artifacts/schemas/prior_knowledge_summary}` |
| `pattern_extraction` | 7 | `investigation_id`, `outcome`, `confidence`, `root_cause`, `error_message`, `error_component`, `error_function`, `hypotheses_summary`, `evidence_summary`, `what_worked`, `what_didnt_work` | -- | `{include:artifacts/schemas/pattern_extraction}` |
| `call_graph_summary` | 0 | `error_function`, `functions_list`, `error_context`, `error_file`, `error_line` | -- | `{include:artifacts/schemas/call_graph_summary}` |
| `log_bundle_analysis` | -1 | `file_count`, `file_list`, `merged_timeline`, `total_errors`, `component_documentation` | -- | (inline JSON schema) |
| `log_timeline_extraction` | -1 | `file_count`, `file_list`, `raw_file_contents` | -- | (inline schema) |
| `boardreader_identification` | -1 | `available_docs`, `log_content` | -- | (inline schema) |
| `primary_error_selection` | -1 | `error_list` | `doc_section` | (inline schema) |
| `documentation_selection` | 0 | `error_messages`, `doc_index` | -- | -- |
| `doc_extraction` | 0 | `doc_name`, `doc_content`, `error_messages` | -- | -- |
| `artifact_evaluation` | 2 | `artifact_text`, `hypotheses` | -- | -- |
| `binder_code_analysis` | 2 | `snippet_text`, `hypotheses` | -- | -- |
| `hint_interpretation` | 0 | `error_message`, `hints_text` | -- | -- |
| `error_context_parsing` | 0 | `error_message`, `numeric_values` | -- | -- |

### Template Anatomy

A typical user prompt follows this structure, illustrated by `hypothesis_generation.md`:

```markdown
TASK: Generate root cause hypotheses for this error.

ERROR:
- Message: {error_message}
- Component: {error_component}
- Function: {error_function}
- Time: {error_timestamp}

CONTEXT LOGS (before error):
{context_logs}

PRIOR KNOWLEDGE:
{prior_knowledge}

## Code Analysis Context
{code_context}

## CODE HINT PRIORITY (CRITICAL)
[instructions for prioritizing developer-written code hints]

## EXPLICIT CAUSAL STATEMENTS (HIGHEST PRIORITY)
[instructions for handling explicit developer explanations]

{include:artifacts/schemas/hypothesis}
```

Key structural elements:

1. **TASK statement**: Opens with a clear directive
2. **Data sections**: Each runtime value is placed in a labeled section
3. **Behavioral instructions**: Additional guidance for handling specific data patterns
4. **Output schema**: Included artifact schema defines the expected response format

### Placeholder Count by Template

The outcome_assessment template has the most placeholders (26 required) because it receives the accumulated output of all preceding phases -- the Judge must weigh everything the investigation has produced. The causal_chain template has the fewest (2 required) because the Logician works with a single hypothesis and its associated evidence.

| Template | Required Count | Rationale |
|----------|---------------|-----------|
| `outcome_assessment` | 26 | Judge receives all upstream artifacts including quality metrics and gap analysis |
| `final_synthesis` | 18 | Synthesizer integrates results from all phases including documentation and chronicler context |
| `pattern_extraction` | 11 | Learner needs the full investigation context for pattern extraction |
| `evidence_query` | 10 | Detective needs hypotheses, evidence, mode configuration, and upstream context |
| `hypothesis_generation` | 9 | Theorist needs the error, context, prior knowledge, and chronicler/case intelligence |
| `prior_knowledge_summary` | 9 | Archivist frames the error with all available prior context including chronicler analysis |
| `log_bundle_analysis` | 5 | Chronicler analyzes the merged multi-file timeline with component documentation |
| `call_graph_summary` | 5 | Archivist call graph summary needs function list and error context |
| `adversarial_review` | 5 | Skeptic reviews a specific hypothesis with its chain, evidence, and documentation |
| `causal_chain_with_evidence` | 4 | Logician variant with explicit evidence list and documentation/chronicler context |
| `doc_extraction` | 3 | Document extraction with name, content, and error messages |
| `log_timeline_extraction` | 3 | Timeline extraction from raw file contents |
| `causal_chain` | 2 | Logician builds a chain from a single hypothesis and evidence |
| `artifact_evaluation` | 2 | Artifact evaluation against hypotheses |
| `binder_code_analysis` | 2 | Code snippet analysis against hypotheses |
| `hint_interpretation` | 2 | Hint interpretation in error context |
| `error_context_parsing` | 2 | Error context parsing with numeric values |
| `boardreader_identification` | 2 | BoardReader identification from docs and logs |
| `documentation_selection` | 2 | Documentation selection for error messages |
| `primary_error_selection` | 1+1 | Error list (required) with optional doc section |

---

## 6.8 Artifact Schema Includes

Artifact files in `templates/artifacts/` are shared fragments that are included by user prompt templates to define structured output formats and constrained value sets. They are never loaded directly as prompts -- they exist only to be included. The `artifacts/` directory is a symlink to `srcs/workbinder/artifacts/`, allowing the WorkBinder module to own these schema definitions while making them accessible to the prompt loader.

### Schema Artifacts (`artifacts/schemas/`)

Schema files define the JSON structure that the LLM must produce. Each schema includes field descriptions, type annotations, and a JSON format example.

**Example: `artifacts/schemas/hypothesis.md`**

```markdown
## Hypothesis Artifact

A root cause hypothesis with probability estimate.

### Fields

- `description` (string, required): Clear description of the root cause
- `category` (string, required): One of hardware, software, configuration,
  timing, resource, unknown
- `prior` (float, required): Probability estimate 0.0-1.0 based on evidence strength
- `confirming_evidence` (string, required): What would confirm this hypothesis
- `refuting_evidence` (string, required): What would refute this hypothesis

### JSON Format

{"description": "Clear description of the root cause", ...}
```

| Schema File | Included By | Defines |
|-------------|-------------|---------|
| `hypothesis.md` | `hypothesis_generation` | Root cause hypothesis with prior probability |
| `evidence_query.md` | `evidence_query` | Evidence query with target hypothesis and expected findings |
| `causal_chain_step.md` | `causal_chain`, `causal_chain_with_evidence` | Causal chain step with mechanism and evidence links |
| `challenge.md` | `adversarial_review` | Adversarial challenge with severity and specific weakness |
| `outcome_assessment.md` | `outcome_assessment` | Investigation outcome with confidence and criteria |
| `synthesis_response.md` | `final_synthesis` | Final synthesis report with recommendations |
| `prior_knowledge_summary.md` | `prior_knowledge_summary` | Prior knowledge summary with patterns and source locations |
| `pattern_extraction.md` | `pattern_extraction` | Extracted patterns for knowledge base storage |
| `call_graph_summary.md` | `call_graph_summary` | Function summaries with data flow descriptions |
| `boardreader_identification.md` | `boardreader_identification` | BoardReader component identification schema |
| `log_bundle_analysis.md` | `log_bundle_analysis` | Log bundle analysis narrative schema |
| `merged_timeline_entry.md` | `log_timeline_extraction` | Merged timeline entry format for multi-file triage |

### Enum Artifacts (`artifacts/enums/`)

Enum files define constrained value sets with definitions for each value.

**Example: `artifacts/enums/evidence_strength.md`**

```markdown
## Evidence Strength Scale

**STRONG** (weight 1.0):
- Direct observation in logs/code showing the claimed behavior
- Multiple independent sources corroborate the same finding
- Code explicitly demonstrates the mechanism

**MODERATE** (weight 0.6):
- Circumstantial but consistent with the claim
- Single source with clear relevance
- Code patterns suggest but don't prove mechanism

**WEAK** (weight 0.3):
- Tangentially related to the claim
- Requires interpretation or inference
- Code is in the area but doesn't directly show mechanism

**NOT_EVIDENCE** (weight 0.0):
- Absence of something (unless expected to be present)
- Generic patterns that match many causes
- Speculation without supporting data
```

| Enum File | Included By | Defines |
|-----------|-------------|---------|
| `evidence_strength.md` | `system/base.md` (all personas) | STRONG, MODERATE, WEAK, NOT_EVIDENCE with weights |
| `query_types.md` | `evidence_query` | Available evidence query types for the Detective |
| `outcome_types.md` | `outcome_assessment` | CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT |
| `challenge_types.md` | (reference) | HIGH, MEDIUM, LOW challenge severity levels |
| `confidence_levels.md` | (reference) | Confidence calibration levels |
| `evidence_types.md` | (reference) | Evidence type categories (log, code, pattern, etc.) |
| `hypothesis_categories.md` | (reference) | hardware, software, configuration, timing, resource, unknown |

### Include Mechanism in Practice

When the loader processes `user/hypothesis_generation.md`, it encounters:

```markdown
{include:artifacts/schemas/hypothesis}
```

This triggers the following resolution chain:

1. `PromptLoader._load_raw("user/hypothesis_generation")` reads the file
2. `_resolve_includes()` finds the `{include:...}` match
3. `_load_include("artifacts/schemas/hypothesis", ...)` reads `artifacts/schemas/hypothesis.md`
4. `_resolve_includes()` is called recursively on the included content (in case it has its own includes)
5. The resolved content replaces the `{include:...}` placeholder in the original template
6. The result is cached under `raw:user/hypothesis_generation`

The same artifact may be included by multiple templates. For example, `artifacts/schemas/causal_chain_step.md` is included by both `causal_chain.md` and `causal_chain_with_evidence.md`. The include cache ensures it is only read from disk once.

---

## 6.9 Per-Persona Prompt Summary

This table maps each persona to its system prompt, user prompt(s), QA variant (if any), and key placeholders that the phase code must provide at runtime.

| Persona | System Prompt | User Prompt(s) | QA Variant | Key Placeholders |
|---------|--------------|-----------------|------------|------------------|
| Chronicler | `system/chronicler.md` | `user/log_bundle_analysis.md` | -- | `file_count`, `file_list`, `merged_timeline`, `total_errors` |
| Archivist | `system/archivist.md` | `user/prior_knowledge_summary.md`, `user/call_graph_summary.md` | -- | `error_message`, `error_component`, `matched_patterns`, `similar_investigations`, `source_locations`, `call_graph_context` |
| Theorist | `system/theorist.md` | `user/hypothesis_generation.md` | `system/qa/qa_theorist.md` | `error_message`, `context_logs`, `prior_knowledge`, `code_context` |
| Detective | `system/detective.md` | `user/evidence_query.md` | `system/qa/qa_detective.md` | `investigation_mode`, `hypotheses`, `evidence`, `analyzed_functions`, `query_effectiveness` |
| Logician | `system/logician.md` | `user/causal_chain.md`, `user/causal_chain_with_evidence.md` | `system/qa/qa_logician.md` | `hypothesis`, `evidence` or `evidence_list` |
| Skeptic | `system/skeptic.md` | `user/adversarial_review.md` | `system/qa/qa_skeptic.md` | `hypothesis`, `chain`, `evidence`, `evidence_availability` |
| Judge | `system/judge.md` | `user/outcome_assessment.md` | -- | `evidence_quality_score`, `evidence_gap_analysis`, `most_critical_gap`, `alternative_paths` |
| Synthesizer | `system/synthesizer.md` | `user/final_synthesis.md` | -- | `outcome`, `confidence`, `hypotheses_ranked`, `evidence_summary`, `judge_evidence_gaps` |
| Learner | `system/learner.md` | `user/pattern_extraction.md` | -- | `investigation_id`, `root_cause`, `what_worked`, `what_didnt_work` |
| Coordinator | `system/coordinator.md` | -- | -- | (panel management; no user prompt template) |

### Data Flow Through Prompts

The placeholder values are not static -- they are populated by the outputs of earlier phases, creating a data flow chain through the prompt system:

```
Phase -1 (Chronicler)
    └─ Outputs: primary_error_file, primary_error_message
         └─ Fed into Phase 0 error identification

Phase 0 (Archivist)
    └─ Outputs: matched_patterns, similar_investigations, source_locations, call_graph_context
         └─ Fed into {prior_knowledge} in Phase 1

Phase 1 (Theorist)
    └─ Outputs: ranked hypotheses list
         └─ Fed into {hypotheses} in Phase 2

Phase 2 (Detective)
    └─ Outputs: evidence collection, quality metrics, gap analysis
         └─ Fed into {evidence} in Phase 3, quality scores in Phase 5

Phase 3 (Logician)
    └─ Outputs: causal chains per hypothesis
         └─ Fed into {chain} in Phase 4, {causal_chain} in Phase 6

Phase 4 (Skeptic)
    └─ Outputs: challenges with severity ratings
         └─ Fed into {challenges_summary} in Phase 5 and Phase 6

Phase 5 (Judge)
    └─ Outputs: outcome, confidence, evidence_gaps, criteria_not_met
         └─ Fed into {outcome}, {judge_evidence_gaps} in Phase 6

Phase 6 (Synthesizer)
    └─ Outputs: final synthesis report
         └─ Fed into Phase 7 context

Phase 7 (Learner)
    └─ Outputs: extracted patterns → stored in knowledge base
```

Each persona's user prompt template is therefore a contract: it declares the exact placeholders it expects, and the phase orchestration code is responsible for populating them with the correct upstream outputs. The `MissingPlaceholderError` ensures that wiring errors between phases are caught immediately rather than producing malformed prompts.

---

### Error Hierarchy

The prompts module defines a focused exception hierarchy in `srcs/prompts/errors.py`:

```
PromptError (base)
├── PromptNotFoundError       # Template file does not exist
├── MissingPlaceholderError   # Required placeholder not provided
├── UnexpectedPlaceholderError # Provided placeholder not in metadata
├── IncludeCycleError         # Circular include detected (A → B → A)
└── IncludeNotFoundError      # Include file does not exist
```

All errors carry context about what went wrong and where:

| Error | Context Fields |
|-------|---------------|
| `PromptNotFoundError` | `prompt_type`, `path` |
| `MissingPlaceholderError` | `prompt_type`, `missing` (frozenset of placeholder names) |
| `UnexpectedPlaceholderError` | `prompt_type`, `unexpected` (frozenset of placeholder names) |
| `IncludeCycleError` | `cycle_path` (list showing the full cycle) |
| `IncludeNotFoundError` | `include_path`, `referenced_from` |

---

> [← Expert Panel](agentic-persona-library-ch5-expert-panel.md) | [Table of Contents](agentic-persona-library.md) | [Next: Testing Strategy →](agentic-persona-library-ch7-testing-strategy.md)
