# Artifacts Reference Guide

This document describes all artifact types used in the investigation pipeline. Artifacts are structured data objects that personas produce and consume during an investigation.

## Table of Contents

1. [Overview](#overview)
2. [How Artifacts Work](#how-artifacts-work)
3. [Using the Include System](#using-the-include-system)
4. [Enumeration Reference](#enumeration-reference)
5. [Schema Reference](#schema-reference)
6. [Investigation Pipeline Flow](#investigation-pipeline-flow)
7. [Common Patterns](#common-patterns)
8. [Troubleshooting](#troubleshooting)

---

## Overview

### What Are Artifacts?

Artifacts are JSON structures that the LLM produces during investigation. Each investigation phase (persona) either:
- **Produces** artifacts (e.g., Theorist produces hypotheses)
- **Consumes** artifacts (e.g., Detective uses hypotheses to generate queries)
- **Both** (e.g., Logician consumes hypotheses and produces causal chains)

### Why Externalize Artifact Definitions?

Before this system, each prompt file defined its own JSON format. This caused:
- Inconsistent field names across prompts
- Duplicated definitions that could drift apart
- Harder maintenance when formats changed

Now, all artifact definitions live in one place (`artifacts/`) and are included where needed.

### Directory Structure

```
artifacts/
├── ARTIFACTS.md          # This documentation file
├── enums/                # Shared value lists (like dropdowns)
│   ├── challenge_types.md
│   ├── confidence_levels.md
│   ├── evidence_strength.md
│   ├── evidence_types.md
│   ├── hypothesis_categories.md
│   ├── outcome_types.md
│   └── query_types.md
└── schemas/              # JSON structure definitions
    ├── call_graph_summary.md
    ├── causal_chain_step.md
    ├── challenge.md
    ├── evidence_query.md
    ├── hypothesis.md
    ├── outcome_assessment.md
    ├── pattern_extraction.md
    ├── prior_knowledge_summary.md
    └── synthesis_response.md
```

---

## How Artifacts Work

### The Investigation Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Archivist  │───>│  Theorist   │───>│  Detective  │───>│  Logician   │
│  (Phase 0)  │    │  (Phase 1)  │    │  (Phase 2)  │    │  (Phase 3)  │
│             │    │             │    │             │    │             │
│ Produces:   │    │ Produces:   │    │ Produces:   │    │ Produces:   │
│ - prior     │    │ - hypothesis│    │ - evidence  │    │ - causal    │
│   knowledge │    │   (array)   │    │   queries   │    │   chain     │
│   summary   │    │             │    │             │    │   steps     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                │
                                                                ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Learner   │<───│ Synthesizer │<───│    Judge    │<───│   Skeptic   │
│  (Phase 7)  │    │  (Phase 6)  │    │  (Phase 5)  │    │  (Phase 4)  │
│             │    │             │    │             │    │             │
│ Produces:   │    │ Produces:   │    │ Produces:   │    │             │
│ - pattern   │    │ - synthesis │    │ - outcome   │    │ Produces:   │
│   extract   │    │   response  │    │   assess    │    │ - challenge │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Artifact Lifecycle

1. **Prompt Loading**: When a prompt file is loaded, `{include:...}` placeholders are replaced with the actual content from artifact files.

2. **LLM Generation**: The LLM reads the schema definition and produces JSON matching that format.

3. **Parsing**: The application parses the JSON response and validates it against Pydantic models.

4. **Storage**: Artifacts are stored in the WorkBinder for later phases to access.

5. **Consumption**: Later phases read artifacts from the WorkBinder to inform their work.

---

## Using the Include System

### Basic Syntax

In any prompt file, use this syntax to include an artifact definition:

```markdown
{include:artifacts/schemas/hypothesis}
{include:artifacts/enums/evidence_strength}
```

**Note**: Do NOT include the `.md` extension - it's added automatically.

### Example: Before and After

**Before** (inline definition):
```markdown
Generate hypotheses as JSON array. Each hypothesis needs:
- description: Clear description of the root cause
- category: One of [hardware, software, configuration, timing, resource, unknown]
- prior: Probability estimate (0.0-1.0) based on evidence strength
- confirming_evidence: What would confirm this hypothesis
- refuting_evidence: What would refute this hypothesis

Respond with ONLY valid JSON...
```

**After** (using includes):
```markdown
Generate hypotheses as JSON array.

{include:artifacts/schemas/hypothesis}

Respond with ONLY valid JSON...
```

### How Resolution Works

The `PromptLoader` class in `srcs/prompts/`:

1. Loads the prompt file
2. Finds all `{include:path}` placeholders using regex
3. Loads each included file (recursively, so includes can have includes)
4. Replaces the placeholder with the file content
5. Caches results for performance

```python
# This is what happens internally
content = "{include:artifacts/enums/evidence_strength}"
# Becomes:
content = """## Evidence Strength Scale

**STRONG** (weight 1.0):
- Direct observation in logs/code showing the claimed behavior
..."""
```

### Creating a New Artifact

1. **Create the schema file** in `artifacts/schemas/your_artifact.md`:
   ```markdown
   ## Your Artifact Name

   Brief description of what this artifact represents.

   ### Fields

   - `field_name` (type, required/optional): Description

   ### JSON Format

   ```json
   {
       "field_name": "example value"
   }
   ```
   ```

2. **Create any new enums** in `artifacts/enums/` if needed

3. **Use includes** in your prompt file:
   ```markdown
   {include:artifacts/schemas/your_artifact}
   ```

4. **Test** by loading the prompt and verifying the include resolved:
   ```python
   from srcs.persona.prompts import PromptLoader
   loader = PromptLoader()
   template = loader.load("user/your_prompt")
   print(template.content)  # Should show resolved includes
   ```

---

## Enumeration Reference

Enums define the allowed values for categorical fields. Using enums ensures consistency across all artifacts.

### evidence_strength

**Purpose**: Rate how strongly evidence supports or refutes a hypothesis.

**Used by**: Detective (evidence collection), Logician (chain building), Judge (assessment)

| Value | Weight | When to Use |
|-------|--------|-------------|
| `STRONG` | 1.0 | Direct observation in logs/code; multiple independent sources; code explicitly shows mechanism |
| `MODERATE` | 0.6 | Circumstantial but consistent; single relevant source; code suggests but doesn't prove |
| `WEAK` | 0.3 | Tangentially related; requires inference; code is nearby but doesn't directly show mechanism |
| `NOT_EVIDENCE` | 0.0 | Absence of something; generic patterns; speculation without data |

**Example**:
```
STRONG: Code shows `if (ptr == nullptr) { LOG_ERROR("bad pointer") }`
        and we see "bad pointer" in the logs.

MODERATE: Function handles configuration, but we don't see the specific
          parameter value that caused the issue.

WEAK: Component "EventBuilder" is mentioned in logs, but not the specific
      function where the error occurred.

NOT_EVIDENCE: "No timeout errors were logged" - absence is not evidence
              unless we expected to see something.
```

---

### evidence_types

**Purpose**: Categorize where evidence came from.

**Used by**: Detective, Synthesizer, Learner

| Value | Description |
|-------|-------------|
| `log` | Evidence extracted from log entries (timestamps, error messages, sequences) |
| `code` | Evidence from source code analysis (functions, control flow, data structures) |
| `config` | Evidence from configuration files (parameters, settings, thresholds) |
| `dataflow` | Evidence from tracing data flow (caller chains, variable values, state changes) |

**Example**:
```json
{
  "type": "code",
  "content": "Function processFragment() has no null check on line 142",
  "significance": "Shows the code path that allows null pointer dereference"
}
```

---

### hypothesis_categories

**Purpose**: Classify the type of root cause being hypothesized.

**Used by**: Theorist (hypothesis generation), Learner (pattern extraction)

| Category | Description | Common Examples |
|----------|-------------|-----------------|
| `hardware` | Physical device issues | Device timeout, data corruption, connection loss |
| `software` | Code/logic problems | Null pointer, race condition, memory leak, exception |
| `configuration` | Settings issues | Wrong parameter, missing value, invalid path |
| `timing` | Temporal problems | Deadline missed, synchronization failure, race window |
| `resource` | Capacity issues | Out of memory, disk full, connection limit, buffer overflow |
| `unknown` | Cannot categorize | Requires more investigation |

**Tip**: If unsure, use `unknown` - it's better to be honest than to guess wrong.

---

### confidence_levels

**Purpose**: Express how confident we are in a conclusion.

**Used by**: Judge, Synthesizer, all personas in their contributions

| Level | Score Range | Meaning |
|-------|-------------|---------|
| `high` | 0.7 - 1.0 | Strong evidence directly supports conclusion; multiple corroborating sources; mechanism verified |
| `medium` | 0.4 - 0.7 | Moderate evidence; some gaps remain; mechanism plausible |
| `low` | 0.0 - 0.4 | Limited evidence; significant gaps; requires assumptions |

**When to use each**:
- **high**: "The code explicitly shows X causes Y, and logs confirm X happened"
- **medium**: "Evidence suggests X, but we haven't verified the complete chain"
- **low**: "This is our best guess, but we lack direct evidence"

---

### outcome_types

**Purpose**: Final verdict on an investigation's success.

**Used by**: Judge (outcome assessment)

| Outcome | Score | Criteria |
|---------|-------|----------|
| `CONFIDENT` | > 0.7 | 2+ strong evidence pieces; top hypothesis > 0.7; all HIGH challenges resolved; clear causal chain |
| `PROBABLE` | 0.5 - 0.7 | 1 strong OR 3 moderate evidence; top hypothesis > 0.5; no unresolved HIGH challenges |
| `UNCERTAIN` | 0.3 - 0.5 | Multiple viable hypotheses; evidence doesn't discriminate; more investigation needed |
| `CONTRADICTORY` | N/A | Contradicting evidence >= supporting; evidence suggests different causes |
| `INSUFFICIENT` | < 0.3 | Inadequate evidence; no hypotheses meet threshold; critical gaps |

**Decision Tree**:
```
                    ┌─────────────────────┐
                    │ Is evidence         │
                    │ contradictory?      │
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              │ Yes                             │ No
              ▼                                 ▼
     ┌────────────────┐              ┌─────────────────────┐
     │ CONTRADICTORY  │              │ Is evidence         │
     └────────────────┘              │ sufficient?         │
                                     └──────────┬──────────┘
                                                │
                           ┌────────────────────┴────────────────────┐
                           │ No                                      │ Yes
                           ▼                                         ▼
                  ┌────────────────┐                    ┌─────────────────────┐
                  │ INSUFFICIENT   │                    │ Score > 0.7?        │
                  └────────────────┘                    └──────────┬──────────┘
                                                                   │
                                              ┌────────────────────┴────────────────────┐
                                              │ Yes                                     │ No
                                              ▼                                         ▼
                                     ┌────────────────┐                    ┌─────────────────────┐
                                     │ CONFIDENT      │                    │ Score > 0.5?        │
                                     └────────────────┘                    └──────────┬──────────┘
                                                                                      │
                                                             ┌────────────────────────┴────────────────────────┐
                                                             │ Yes                                            │ No
                                                             ▼                                                ▼
                                                    ┌────────────────┐                              ┌────────────────┐
                                                    │ PROBABLE       │                              │ UNCERTAIN      │
                                                    └────────────────┘                              └────────────────┘
```

---

### query_types

**Purpose**: Types of queries the Detective can execute to gather evidence.

**Used by**: Detective (evidence seeking)

| Query Type | Description | When to Use |
|------------|-------------|-------------|
| `log_search` | Search log entries by text pattern | Finding specific errors, warnings, or events |
| `log_source` | Find source code that produces a log message | Locating where an error message originates |
| `function_lookup` | Look up function definition by name | Understanding what a function does |
| `class_lookup` | Look up class definition by name | Understanding class structure and methods |
| `code_search` | Search code for symbols/patterns | Finding usages, patterns, or specific code |
| `similar_cases` | Find similar past investigations | Learning from historical patterns |
| `pattern_lookup` | Find known error patterns | Matching against documented failure modes |
| `component_logs` | Get all logs from a component | Understanding component behavior |
| `time_window` | Get logs within a time range | Analyzing sequence of events |
| `accuracy_check` | Check historical pattern accuracy | Validating pattern reliability |

**Tips**:
- Use `log_source` with static text (before dynamic values like numbers)
- Use `function_lookup` with `full_source: true` for control flow analysis
- Use `component_logs` when you know which component but not the specific error

---

### challenge_types

**Purpose**: Categorize weaknesses found during adversarial review.

**Used by**: Skeptic (adversarial review)

| Type | Description | Example |
|------|-------------|---------|
| `logical_flaw` | Problem with the causal reasoning | "Step 2 doesn't follow from Step 1" |
| `weak_evidence` | Evidence doesn't support the claim | "Log entry shows correlation, not causation" |
| `alternative` | Different explanation fits better | "Timeout could also be caused by network issue" |
| `missing` | Evidence gap that should be filled | "No evidence about thread synchronization" |

**Severity Levels**:

| Severity | Meaning | Action Required |
|----------|---------|-----------------|
| `HIGH` | Conclusion likely wrong | Must address before accepting conclusion |
| `MEDIUM` | Needs strengthening | Should address if possible |
| `LOW` | Minor improvement | Nice to address, not critical |

---

## Schema Reference

### hypothesis

**Purpose**: A proposed root cause with probability estimate.

**Produced by**: Theorist (Phase 1)

**Consumed by**: Detective, Logician, Skeptic, Judge

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string | Yes | Clear, specific description of the root cause |
| `category` | string | Yes | One of: hardware, software, configuration, timing, resource, unknown |
| `prior` | float | Yes | Probability estimate 0.0-1.0 |
| `confirming_evidence` | string | Yes | What evidence would confirm this hypothesis |
| `refuting_evidence` | string | Yes | What evidence would refute this hypothesis |

**Example**:
```json
{
  "description": "Null pointer dereference in BoardReader::processFragment() due to uninitialized fragment generator",
  "category": "software",
  "prior": 0.75,
  "confirming_evidence": "Log showing fragment generator initialization failure before the crash",
  "refuting_evidence": "Log showing fragment generator successfully initialized"
}
```

**Prior Assignment Guidelines**:
- 0.90-0.95: Explicit developer comment says "this is caused by X"
- 0.70-0.85: Code hint or diagnostic message points to cause
- 0.60-0.80: Known pattern match from historical data
- 0.30-0.50: Similar past investigation
- 0.20-0.30: Fresh LLM hypothesis without prior evidence
- 0.10-0.20: Alternative/fallback hypothesis

---

### evidence_query

**Purpose**: A query to gather discriminating evidence.

**Produced by**: Detective (Phase 2)

**Consumed by**: Evidence execution system

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query_type` | string | Yes | One of the query_types enum values |
| `query` | string | Yes | The specific search parameter |
| `targets_hypothesis` | string | Yes | Which hypothesis this tests (by ID or description) |
| `expected_if_true` | string | Yes | What we'd find if hypothesis is correct |
| `expected_if_false` | string | Yes | What we'd find if hypothesis is wrong |
| `full_source` | boolean | No | For function_lookup: get complete function body |

**Example**:
```json
{
  "query_type": "function_lookup",
  "query": "processFragment",
  "targets_hypothesis": "null_pointer_in_processFragment",
  "expected_if_true": "Function has no null check before dereferencing fragment pointer",
  "expected_if_false": "Function has proper null check with error handling",
  "full_source": true
}
```

**Query Design Tips**:
1. **Be specific**: "processFragment" not "process"
2. **Target discrimination**: Query should help distinguish between hypotheses
3. **Predict outcomes**: Knowing what to expect helps interpret results
4. **Avoid duplicates**: Check analyzed_functions list before requesting

---

### causal_chain_step

**Purpose**: One step in the chain from root cause to observed error.

**Produced by**: Logician (Phase 3)

**Consumed by**: Skeptic, Judge, Synthesizer

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claim` | string | Yes | The causal claim (X causes Y) |
| `mechanism` | string | Yes | How X actually causes Y |
| `evidence` | array of strings | Yes | Evidence IDs supporting this step |
| `is_assumption` | boolean | Yes | True if no evidence supports this step |

**Example**:
```json
{
  "claim": "Uninitialized fragment generator causes null pointer in processFragment",
  "mechanism": "When generator is not initialized, getFragment() returns nullptr, which processFragment dereferences without checking",
  "evidence": ["ev_001", "ev_003"],
  "is_assumption": false
}
```

**Chain Building Rules**:
1. **Evidence IDs only**: You can ONLY cite IDs from the provided evidence list
2. **Mark assumptions**: If no evidence, set `is_assumption: true`
3. **Explain mechanisms**: Don't just say "A causes B", explain HOW
4. **End at error**: Chain must terminate at the observed error

**Link Strength Guide**:
| Strength | Confidence | Criteria |
|----------|------------|----------|
| STRONG | 0.8-1.0 | Direct code shows A causes B; multiple evidence items |
| MODERATE | 0.5-0.8 | Indirect evidence; plausible mechanism |
| WEAK | 0.2-0.5 | Inference-based; limited evidence |
| ASSUMPTION | < 0.2 | No evidence; mark `is_assumption: true` |

---

### challenge

**Purpose**: A weakness found during adversarial review.

**Produced by**: Skeptic (Phase 4)

**Consumed by**: Judge, Synthesizer

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | One of: logical_flaw, weak_evidence, alternative, missing |
| `content` | string | Yes | Specific description of the challenge |
| `severity` | string | Yes | One of: HIGH, MEDIUM, LOW |

**Example**:
```json
{
  "type": "alternative",
  "content": "The null pointer could also originate from a race condition where another thread clears the generator while processFragment is running",
  "severity": "MEDIUM"
}
```

**Challenge Generation Tips**:
1. **Be specific**: Point to exact steps or evidence
2. **Explain why**: Don't just say "weak" - explain the weakness
3. **Suggest alternatives**: For `alternative` type, propose the other explanation
4. **Consider code paths**: For code evidence, question if it applies in all paths

---

### outcome_assessment

**Purpose**: Judge's evaluation of investigation outcome.

**Produced by**: Judge (Phase 5)

**Consumed by**: Synthesizer, Learner

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `outcome` | string | Yes | CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, or INSUFFICIENT |
| `confidence_score` | float | Yes | Numeric confidence 0.0-1.0 |
| `reasoning` | string | Yes | Detailed explanation of the decision |
| `criteria_met` | array of strings | Yes | Which outcome criteria were satisfied |
| `criteria_not_met` | array of strings | Yes | Which criteria were not satisfied |
| `evidence_gaps` | array of strings | Yes | What evidence is missing |
| `unresolved_concerns` | array of strings | Yes | Challenges not addressed |
| `recommendation` | string | Yes | What to do next |

**Example**:
```json
{
  "outcome": "PROBABLE",
  "confidence_score": 0.65,
  "reasoning": "Strong code evidence supports null pointer hypothesis, but we lack runtime logs to confirm the initialization failure actually occurred.",
  "criteria_met": [
    "Top hypothesis score > 0.5",
    "No unresolved HIGH severity challenges",
    "Clear causal chain established"
  ],
  "criteria_not_met": [
    "Less than 2 pieces of strong evidence (have 1)",
    "Top hypothesis score not > 0.7"
  ],
  "evidence_gaps": [
    "No runtime logs showing initialization sequence",
    "No memory dump to confirm null value"
  ],
  "unresolved_concerns": [
    "Race condition alternative not fully ruled out"
  ],
  "recommendation": "Accept as probable cause but suggest adding null check as defensive fix regardless"
}
```

---

### synthesis_response

**Purpose**: Final investigation report.

**Produced by**: Synthesizer (Phase 6)

**Consumed by**: User, API response, Learner

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `executive_summary` | string | Yes | 2-3 sentence overview |
| `root_cause` | object | Yes | Description, code_location, mechanism |
| `causal_narrative` | array of strings | Yes | Step-by-step explanation |
| `key_evidence` | array of objects | Yes | Most important evidence (type, content, significance) |
| `debugging_steps` | array of objects | Yes | Actionable steps (action, purpose, expected_result) |
| `caveats` | array of strings | Yes | Limitations and uncertainties |
| `confidence` | object | Yes | level, raw_score, calibrated_score, reasoning |

**Example** (abbreviated):
```json
{
  "executive_summary": "Investigation identified a null pointer dereference in BoardReader::processFragment() as the root cause. The fragment generator failed to initialize during startup, causing subsequent fragment processing to crash.",
  "root_cause": {
    "description": "Null pointer dereference due to uninitialized fragment generator",
    "code_location": "BoardReader.cpp:142",
    "mechanism": "When initialization fails silently, generator_ remains nullptr, causing crash on first use"
  },
  "causal_narrative": [
    "Step 1: BoardReader initialization does not verify fragment generator creation succeeded",
    "Step 2: Fragment generator initialization failed (reason unknown from available logs)",
    "Step 3: processFragment() called with nullptr generator, no null check present",
    "Step 4: Dereference of nullptr causes segmentation fault"
  ],
  "key_evidence": [
    {
      "type": "code",
      "content": "Line 142: generator_->getFragment() with no null check",
      "significance": "Shows exact crash location and missing safety check"
    }
  ],
  "debugging_steps": [
    {
      "action": "Add null check before generator_ dereference",
      "purpose": "Prevent crash and provide meaningful error message",
      "expected_result": "Graceful failure with diagnostic logging instead of crash"
    }
  ],
  "caveats": [
    "Root cause of initialization failure not determined",
    "Race condition alternative not fully ruled out"
  ],
  "confidence": {
    "level": "medium",
    "raw_score": 0.65,
    "calibrated_score": 0.60,
    "reasoning": "Strong code evidence but lacking runtime confirmation"
  }
}
```

---

### prior_knowledge_summary

**Purpose**: Summary of retrieved historical knowledge.

**Produced by**: Archivist (Phase 0)

**Consumed by**: Theorist, Detective

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `relevance_assessment` | object | Yes | patterns, similar_cases, source_locations (each: level + explanation) |
| `key_insights` | array of strings | Yes | Important findings from prior knowledge |
| `recommended_focus_areas` | array of strings | Yes | Where investigation should focus |
| `data_flow_summary` | string | Yes | Data flow around error location |
| `overall_confidence` | string | Yes | high, medium, or low |
| `confidence_reasoning` | string | Yes | Why this confidence level |

**Example**:
```json
{
  "relevance_assessment": {
    "patterns": "high - Pattern 'null_fragment_generator' matches with 85% historical accuracy",
    "similar_cases": "medium - 3 similar cases found but different components",
    "source_locations": "high - Error message traced to specific function"
  },
  "key_insights": [
    "This error pattern has occurred 12 times in the past year",
    "Most common cause (73%) is initialization timing issue",
    "Code comments warn about null check requirement"
  ],
  "recommended_focus_areas": [
    "Fragment generator initialization sequence",
    "Startup timing and ordering",
    "Null pointer handling in BoardReader"
  ],
  "data_flow_summary": "Data flows from hardware through FragmentGenerator to BoardReader.processFragment(). The generator is created in init() but may not be ready when processFragment() is first called.",
  "overall_confidence": "high",
  "confidence_reasoning": "Strong pattern match with historical data and clear source location"
}
```

---

### pattern_extraction

**Purpose**: Patterns extracted for future learning.

**Produced by**: Learner (Phase 7)

**Consumed by**: Knowledge base (stored for future investigations)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error_pattern` | object | Yes | signature, message_template, contextual_indicators, false_positive_risk |
| `root_cause_pattern` | object | Yes | description_template, category, confirming_evidence, refuting_evidence |
| `evidence_patterns` | array of objects | Yes | type, query_template, strength, usefulness_score |
| `strategy_recommendations` | object | Yes | preferred_approach, key_queries, shortcuts, pitfalls |
| `calibration` | object | Yes | stated_confidence, actual_accuracy, calibration_adjustment, sample_size_note |
| `lessons_learned` | array of strings | Yes | Key takeaways from this investigation |

This schema is complex - see `schemas/pattern_extraction.md` for full details.

---

### call_graph_summary

**Purpose**: Summaries of functions in a call graph.

**Produced by**: Archivist (for call graph summarization)

**Consumed by**: Theorist (understanding code context)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| (dynamic keys) | string | Yes | Function name → summary string |

**Example**:
```json
{
  "BoardReader::processFragment": "Processes incoming data fragments. Dereferences generator_ without null check. Critical path for data flow.",
  "FragmentGenerator::getFragment": "Returns next fragment from buffer. Returns nullptr if not initialized or buffer empty.",
  "BoardReader::init": "Initializes hardware connection and creates fragment generator. Does not verify generator creation succeeded."
}
```

**Summary Guidelines**:
- 1-2 sentences per function
- Focus on: purpose, data flow, error handling, resource management
- Note relevant safety checks (or lack thereof)

---

## Investigation Pipeline Flow

This diagram shows which artifacts flow between phases:

```
Phase 0: Archivist
├─ Produces: prior_knowledge_summary
├─ Produces: call_graph_summary
└─ Passes to: Theorist

Phase 1: Theorist
├─ Consumes: prior_knowledge_summary
├─ Produces: hypothesis[] (array)
└─ Passes to: Detective

Phase 2: Detective
├─ Consumes: hypothesis[]
├─ Produces: evidence_query[] (array)
├─ Executes queries → collects evidence
└─ Passes to: Logician

Phase 3: Logician
├─ Consumes: hypothesis[], evidence
├─ Produces: causal_chain_step[] (per hypothesis)
└─ Passes to: Skeptic

Phase 4: Skeptic
├─ Consumes: hypothesis[], causal_chain_step[], evidence
├─ Produces: challenge[] (array)
└─ Passes to: Judge

Phase 5: Judge
├─ Consumes: hypothesis[], evidence, causal_chain_step[], challenge[]
├─ Produces: outcome_assessment
└─ Passes to: Synthesizer

Phase 6: Synthesizer
├─ Consumes: ALL previous artifacts
├─ Produces: synthesis_response
└─ Passes to: Learner

Phase 7: Learner
├─ Consumes: ALL previous artifacts
├─ Produces: pattern_extraction
└─ Stores in: Knowledge base
```

---

## Common Patterns

### Pattern 1: Referencing Other Artifacts

When one artifact needs to reference another (e.g., evidence referencing a hypothesis):

```json
{
  "targets_hypothesis": "hyp_001"  // Use the hypothesis ID
}
```

**Don't** include the full hypothesis object - just reference by ID.

### Pattern 2: Handling Missing Information

When information is unavailable:

```json
{
  "code_location": "unknown - not found in available source",
  "is_assumption": true
}
```

Be explicit about what's missing rather than guessing.

### Pattern 3: Confidence Calibration

Always pair confidence with reasoning:

```json
{
  "confidence": {
    "level": "medium",
    "raw_score": 0.65,
    "calibrated_score": 0.60,
    "reasoning": "Strong code evidence (0.8) but no runtime confirmation (0.5), averaged"
  }
}
```

### Pattern 4: Evidence Citation

When citing evidence in causal chains:

```json
{
  "evidence": ["ev_001", "ev_003"],  // Cite by ID
  "is_assumption": false              // Has evidence
}

{
  "evidence": [],                     // No evidence available
  "is_assumption": true               // Must mark as assumption
}
```

---

## Troubleshooting

### Include Not Resolving

**Symptom**: You see `{include:...}` literally in the output.

**Causes**:
1. Wrong path (check spelling, no .md extension)
2. File doesn't exist
3. Using wrong loader (must use PromptLoader, not direct file read)

**Fix**:
```python
from srcs.persona.prompts import PromptLoader
loader = PromptLoader()
template = loader.load("user/your_prompt")  # Resolves includes
```

### JSON Parsing Failures

**Symptom**: LLM response doesn't parse as valid JSON.

**Causes**:
1. LLM added markdown code blocks
2. Missing commas or brackets
3. Trailing commas (not valid JSON)

**Fix**: Ensure prompt says "Respond with ONLY valid JSON (no markdown code blocks)"

### Schema Mismatch

**Symptom**: Pydantic validation fails on LLM response.

**Causes**:
1. Schema changed but prompt not updated
2. LLM hallucinated extra fields
3. Required field missing

**Fix**:
1. Update artifact schema file
2. Re-run tests
3. Check Pydantic model matches schema

### Circular Includes

**Symptom**: RecursionError when loading prompt.

**Cause**: File A includes File B which includes File A.

**Fix**: Restructure includes to avoid cycles. Enums should never include other files.

---

## Quick Reference Card

### Enums (Value Sets)

| Enum | Values |
|------|--------|
| evidence_strength | STRONG, MODERATE, WEAK, NOT_EVIDENCE |
| evidence_types | log, code, config, dataflow |
| hypothesis_categories | hardware, software, configuration, timing, resource, unknown |
| confidence_levels | high, medium, low |
| outcome_types | CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT |
| query_types | log_search, log_source, function_lookup, class_lookup, code_search, similar_cases, pattern_lookup, component_logs, time_window, accuracy_check |
| challenge_types | logical_flaw, weak_evidence, alternative, missing |
| challenge_severity | HIGH, MEDIUM, LOW |

### Schemas (JSON Structures)

| Schema | Key Fields | Producer |
|--------|------------|----------|
| hypothesis | description, category, prior | Theorist |
| evidence_query | query_type, query, targets_hypothesis | Detective |
| causal_chain_step | claim, mechanism, evidence, is_assumption | Logician |
| challenge | type, content, severity | Skeptic |
| outcome_assessment | outcome, confidence_score, reasoning | Judge |
| synthesis_response | executive_summary, root_cause, debugging_steps | Synthesizer |
| prior_knowledge_summary | relevance_assessment, key_insights | Archivist |
| pattern_extraction | error_pattern, root_cause_pattern, lessons_learned | Learner |
| call_graph_summary | {function_name: summary} | Archivist |

---

*Last updated: 2026-02-02*
