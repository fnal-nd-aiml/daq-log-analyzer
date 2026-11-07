# User Prompts Reference Guide

This document describes all user prompts (task templates) used in the investigation pipeline. User prompts tell the LLM "what to do" for a given phase.

## Table of Contents

1. [Overview](#overview)
2. [How User Prompts Work](#how-user-prompts-work)
3. [Prompt Reference](#prompt-reference)
4. [Placeholder Reference](#placeholder-reference)
5. [Writing Effective User Prompts](#writing-effective-user-prompts)
6. [Common Patterns](#common-patterns)

---

## Overview

### What Are User Prompts?

User prompts define **tasks** - what the LLM should do. Each user prompt provides:
- **Context**: The data the LLM needs (error, logs, hypotheses, etc.)
- **Instructions**: What to do with the data
- **Output Format**: The JSON structure to produce

### System vs User Prompts

| Aspect | System Prompt | User Prompt |
|--------|---------------|-------------|
| Defines | Who the LLM is | What the LLM does |
| Content | Identity, expertise, constraints | Context, task, output format |
| Changes | Rarely (per persona) | Every request (filled with data) |
| Location | `system/` directory | `user/` directory |

### Directory Structure

```
user/
├── PROMPTS.md                    # This documentation file
├── CLAUDE.md                     # Brief overview for Claude Code
├── hypothesis_generation.md      # Phase 1: Generate hypotheses
├── evidence_query.md             # Phase 2: Generate evidence queries
├── causal_chain.md               # Phase 3: Build causal chains (basic)
├── causal_chain_with_evidence.md # Phase 3: Build chains (with evidence list)
├── adversarial_review.md         # Phase 4: Generate challenges
├── outcome_assessment.md         # Phase 5: Assess outcome
├── final_synthesis.md            # Phase 6: Synthesize results
├── prior_knowledge_summary.md    # Phase 0: Summarize prior knowledge
├── pattern_extraction.md         # Phase 7: Extract patterns
└── call_graph_summary.md         # Phase 0: Summarize call graphs
```

---

## How User Prompts Work

### Template Loading and Formatting

User prompts are templates with `{placeholder}` values:

```python
from srcs.persona.prompts import PromptLoader

loader = PromptLoader()
template = loader.get_user_prompt("hypothesis_generation")

# Format with actual values
prompt = template.format(
    error_message="Null pointer exception in processFragment",
    error_component="BoardReader",
    error_function="processFragment",
    error_timestamp="2026-02-02 10:15:32",
    context_logs="[10:15:30] Starting fragment processing...",
    prior_knowledge="Pattern match: null_fragment_generator (85%)",
    code_context="Function signature: void processFragment(Fragment* f)"
)
```

### Include Resolution

User prompts can include artifact specifications:

```markdown
Generate hypotheses as JSON array.

{include:artifacts/schemas/hypothesis}    <-- Replaced with schema content

Respond with ONLY valid JSON...
```

### Prompt Flow in Investigation

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         User Prompt Template                             │
│                                                                          │
│  TASK: Generate root cause hypotheses for this error.                   │
│                                                                          │
│  ERROR:                                                                  │
│  - Message: {error_message}        <─┐                                  │
│  - Component: {error_component}      │ Filled at runtime                │
│  - Function: {error_function}        │                                  │
│  - Time: {error_timestamp}         <─┘                                  │
│                                                                          │
│  CONTEXT LOGS:                                                          │
│  {context_logs}                    <── Filled at runtime                │
│                                                                          │
│  {include:artifacts/schemas/hypothesis}  <── Resolved at load time      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Prompt Reference

### hypothesis_generation.md

**Phase**: 1 (Theorist)

**Purpose**: Generate root cause hypotheses for an error

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{error_message}` | string | The error message text |
| `{error_component}` | string | Component where error occurred |
| `{error_function}` | string | Function where error occurred |
| `{error_timestamp}` | string | When the error happened |
| `{context_logs}` | string | Log entries before the error |
| `{prior_knowledge}` | string | Patterns, similar cases, source locations |
| `{code_context}` | string | Relevant source code snippets |

**Output Format**: JSON with `hypotheses` array

**Key Features**:
- **Code Hint Priority**: Developer comments get 0.90+ priors
- **Multiple Source Locations**: Must consider ALL locations
- **Explicit Causal Statements**: Don't dilute with similar hypotheses

**Example Output**:
```json
{"hypotheses": [
    {
        "description": "Null pointer in processFragment due to uninitialized generator",
        "category": "software",
        "prior": 0.75,
        "confirming_evidence": "Log showing generator init failure",
        "refuting_evidence": "Log showing successful init"
    }
]}
```

---

### evidence_query.md

**Phase**: 2 (Detective)

**Purpose**: Generate queries to gather discriminating evidence

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{investigation_mode}` | string | "code_centric" or "balanced" |
| `{mode_specific_guidance}` | string | Mode-appropriate instructions |
| `{analyzed_functions}` | string | Functions already looked up (avoid duplicates) |
| `{query_effectiveness}` | string | Success rates per query type |
| `{hypotheses}` | string | Current hypotheses to test |
| `{evidence}` | string | Evidence collected so far |

**Output Format**: JSON with `queries` array

**Key Features**:
- **Code Hint Validation**: Validate developer explanations first
- **Avoid Repetition**: Don't re-request analyzed functions
- **Query Effectiveness**: Skip ineffective query types

**Included Artifacts**:
- `{include:artifacts/enums/query_types}` - Available query types
- `{include:artifacts/schemas/evidence_query}` - Query format

**Example Output**:
```json
{"queries": [
    {
        "query_type": "function_lookup",
        "query": "processFragment",
        "targets_hypothesis": "null_pointer_hypothesis",
        "expected_if_true": "No null check before dereference",
        "expected_if_false": "Proper null check exists",
        "full_source": true
    }
]}
```

---

### causal_chain.md

**Phase**: 3 (Logician)

**Purpose**: Build causal chain from root cause to error (basic version)

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{hypothesis}` | string | The hypothesis to build chain for |
| `{evidence}` | string | Available evidence |

**Output Format**: JSON with `steps` array

**Included Artifacts**:
- `{include:artifacts/schemas/causal_chain_step}` - Step format

**Example Output**:
```json
{"steps": [
    {
        "claim": "Generator initialization fails silently",
        "mechanism": "Init function catches exception but doesn't set error flag",
        "evidence": ["ev_001"],
        "is_assumption": false
    },
    {
        "claim": "processFragment dereferences null generator",
        "mechanism": "No null check before generator_->getFragment()",
        "evidence": ["ev_003"],
        "is_assumption": false
    }
]}
```

---

### causal_chain_with_evidence.md

**Phase**: 3 (Logician)

**Purpose**: Build causal chain with explicit evidence list (enhanced version)

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{hypothesis}` | string | The hypothesis to build chain for |
| `{evidence_list}` | string | Formatted list of available evidence IDs |

**Key Difference from causal_chain.md**:
- Provides explicit evidence ID list
- Emphasizes: "ONLY cite evidence IDs from the list above"
- Better for ensuring valid evidence references

**Included Artifacts**:
- `{include:artifacts/schemas/causal_chain_step}` - Step format

---

### adversarial_review.md

**Phase**: 4 (Skeptic)

**Purpose**: Challenge the conclusion and find weaknesses

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{hypothesis}` | string | The hypothesis being challenged |
| `{chain}` | string | The causal chain for this hypothesis |
| `{evidence}` | string | Supporting evidence |

**Output Format**: JSON with `challenges` array

**Key Features**:
- **Code-Based Challenge Guidance**: Questions about execution paths, race conditions, etc.
- **Severity Guide**: HIGH/MEDIUM/LOW criteria

**Included Artifacts**:
- `{include:artifacts/schemas/challenge}` - Challenge format

**Example Output**:
```json
{"challenges": [
    {
        "type": "alternative",
        "content": "Null could also come from race condition where another thread clears generator",
        "severity": "MEDIUM"
    },
    {
        "type": "missing",
        "content": "No evidence about thread synchronization in this code path",
        "severity": "MEDIUM"
    }
]}
```

---

### outcome_assessment.md

**Phase**: 5 (Judge)

**Purpose**: Evaluate evidence and determine investigation outcome

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{error_message}` | string | The error being investigated |
| `{hypotheses_summary}` | string | Summary of all hypotheses |
| `{top_hypothesis}` | string | Leading hypothesis |
| `{top_score}` | string | Score of leading hypothesis |
| `{evidence_count}` | int | Total evidence items |
| `{strong_evidence_count}` | int | Strong evidence count |
| `{moderate_evidence_count}` | int | Moderate evidence count |
| `{weak_evidence_count}` | int | Weak evidence count |
| `{evidence_details}` | string | Detailed evidence list |
| `{causal_chains_summary}` | string | Summary of causal chains |
| `{challenges_summary}` | string | Summary of challenges |
| `{unresolved_high_count}` | int | Unresolved HIGH challenges |
| `{unresolved_medium_count}` | int | Unresolved MEDIUM challenges |

**Included Artifacts**:
- `{include:artifacts/enums/outcome_types}` - Outcome criteria
- `{include:artifacts/schemas/outcome_assessment}` - Response format

**Example Output**:
```json
{
    "outcome": "PROBABLE",
    "confidence_score": 0.65,
    "reasoning": "Strong code evidence but no runtime confirmation",
    "criteria_met": ["Top hypothesis > 0.5", "No HIGH challenges"],
    "criteria_not_met": ["Less than 2 strong evidence"],
    "evidence_gaps": ["No runtime logs"],
    "unresolved_concerns": ["Race condition alternative"],
    "recommendation": "Accept as probable; add null check defensively"
}
```

---

### final_synthesis.md

**Phase**: 6 (Synthesizer)

**Purpose**: Create final investigation report

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{investigation_id}` | string | Unique investigation identifier |
| `{error_message}` | string | The error investigated |
| `{error_component}` | string | Component where error occurred |
| `{started_at}` | string | Investigation start time |
| `{duration}` | string | Investigation duration |
| `{outcome}` | string | CONFIDENT/PROBABLE/etc. |
| `{confidence}` | string | Confidence score |
| `{root_cause}` | string | Root cause description |
| `{evidence_summary}` | string | Key evidence summary |
| `{causal_chain}` | string | Causal chain summary |
| `{challenges_summary}` | string | Challenges and resolutions |
| `{source_locations}` | string | Relevant source code locations |

**Included Artifacts**:
- `{include:artifacts/schemas/synthesis_response}` - Response format

**Sections Required**:
1. Executive Summary (2-3 sentences)
2. Root Cause Explanation
3. Causal Narrative
4. Evidence Highlight
5. Debugging Steps
6. Caveats
7. Confidence Assessment

---

### prior_knowledge_summary.md

**Phase**: 0 (Archivist)

**Purpose**: Summarize retrieved prior knowledge

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{error_message}` | string | The error being investigated |
| `{error_component}` | string | Component where error occurred |
| `{error_function}` | string | Function where error occurred |
| `{error_timestamp}` | string | When the error happened |
| `{matched_patterns}` | string | Patterns from knowledge base |
| `{similar_investigations}` | string | Similar past cases |
| `{source_locations}` | string | Source code locations |
| `{call_graph_context}` | string | Call graph information |

**Included Artifacts**:
- `{include:artifacts/schemas/prior_knowledge_summary}` - Response format

---

### pattern_extraction.md

**Phase**: 7 (Learner)

**Purpose**: Extract patterns for future learning

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{investigation_id}` | string | Investigation identifier |
| `{outcome}` | string | Investigation outcome |
| `{confidence}` | string | Confidence level |
| `{root_cause}` | string | Root cause found |
| `{error_message}` | string | Error message |
| `{error_component}` | string | Component |
| `{error_function}` | string | Function |
| `{hypotheses_summary}` | string | Hypotheses evaluated |
| `{evidence_summary}` | string | Evidence collected |
| `{what_worked}` | string | Successful approaches |
| `{what_didnt_work}` | string | Failed approaches |

**Included Artifacts**:
- `{include:artifacts/schemas/pattern_extraction}` - Response format

---

### call_graph_summary.md

**Phase**: 0 (Archivist)

**Purpose**: Summarize functions in a call graph

**Input Placeholders**:

| Placeholder | Type | Description |
|-------------|------|-------------|
| `{error_function}` | string | Function where error occurred |
| `{functions_list}` | string | Functions to summarize |
| `{error_context}` | string | Context about the error |

**Included Artifacts**:
- `{include:artifacts/schemas/call_graph_summary}` - Response format

**Note**: This is a simpler prompt focused on concise function summaries.

---

## Placeholder Reference

### Standard Placeholders

These placeholders are used across multiple prompts:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{error_message}` | Error text | "Null pointer exception" |
| `{error_component}` | artdaq component | "BoardReader" |
| `{error_function}` | Function name | "processFragment" |
| `{error_timestamp}` | ISO timestamp | "2026-02-02T10:15:32" |
| `{context_logs}` | Surrounding log entries | "[10:15:30] Starting..." |
| `{hypothesis}` | Single hypothesis text | "Null pointer due to..." |
| `{hypotheses}` | Multiple hypotheses | JSON or formatted text |
| `{evidence}` | Evidence items | JSON or formatted text |
| `{outcome}` | Investigation outcome | "PROBABLE" |
| `{confidence}` | Confidence score | "0.65" |

### Mode-Specific Placeholders

| Placeholder | Used In | Description |
|-------------|---------|-------------|
| `{investigation_mode}` | evidence_query | "code_centric" or "balanced" |
| `{mode_specific_guidance}` | evidence_query | Mode-appropriate instructions |
| `{analyzed_functions}` | evidence_query | Functions already analyzed |
| `{query_effectiveness}` | evidence_query | Success rates per query type |

### Summary Placeholders

| Placeholder | Used In | Description |
|-------------|---------|-------------|
| `{hypotheses_summary}` | outcome_assessment, pattern_extraction | Formatted hypothesis list |
| `{evidence_summary}` | final_synthesis, pattern_extraction | Key evidence summary |
| `{causal_chains_summary}` | outcome_assessment | Chain summaries |
| `{challenges_summary}` | outcome_assessment, final_synthesis | Challenge summaries |

---

## Writing Effective User Prompts

### Required Sections

1. **Task Statement**
   ```markdown
   TASK: [Clear verb phrase describing what to do]
   ```

2. **Context Section(s)**
   ```markdown
   ## Error Being Investigated

   {error_message}
   ```

3. **Instructions**
   ```markdown
   What queries would help discriminate between hypotheses?
   - Focus on queries that would...
   - Prioritize...
   - DO NOT...
   ```

4. **Output Format**
   ```markdown
   {include:artifacts/schemas/[schema_name]}

   Respond with ONLY valid JSON (no markdown code blocks):
   {{"key": [...]}}
   ```

### Best Practices

**Be Explicit About Output**:
```markdown
# Good
Respond with ONLY valid JSON (no markdown code blocks):
{{"hypotheses": [...]}}

# Bad
Return JSON.
```

**Use Includes for Schemas**:
```markdown
# Good
{include:artifacts/schemas/hypothesis}

# Bad
Each hypothesis needs:
- description: ...
- category: ...
```

**Provide Clear Constraints**:
```markdown
# Good
- DO NOT request functions listed in "Already Analyzed" above
- SKIP query types marked as ineffective above

# Bad
- Be efficient
```

**Show Expected Structure**:
```markdown
# Good
{{"hypotheses": [...]}}

# Bad
Return a list of hypotheses
```

### Using Placeholders

**Naming Convention**:
- Use `snake_case`: `{error_message}`, `{context_logs}`
- Be descriptive: `{unresolved_high_count}` not `{high_count}`

**Grouping Related Data**:
```markdown
## Error Being Investigated

- Message: {error_message}
- Component: {error_component}
- Function: {error_function}
- Time: {error_timestamp}
```

**Providing Context for Lists**:
```markdown
## Already Analyzed (DO NOT REQUEST AGAIN):
{analyzed_functions}
```

---

## Common Patterns

### Pattern 1: Task + Context + Instructions + Format

```markdown
TASK: [What to do]

## Context Section 1
{placeholder}

## Context Section 2
{placeholder}

## Instructions
- Point 1
- Point 2

{include:artifacts/schemas/[schema]}

Respond with ONLY valid JSON (no markdown code blocks):
{{"key": [...]}}
```

### Pattern 2: Critical Guidance Sections

For important guidance, use headers and bold:
```markdown
## CODE HINT PRIORITY (CRITICAL)

**Developer comments are AUTHORITATIVE evidence.**
```

### Pattern 3: Conditional Instructions

When behavior depends on context:
```markdown
## Investigation Mode: {investigation_mode}
{mode_specific_guidance}
```

### Pattern 4: Avoidance Lists

To prevent repetition:
```markdown
## Already Analyzed (DO NOT REQUEST AGAIN):
{analyzed_functions}
```

### Pattern 5: Effectiveness Tracking

To guide query selection:
```markdown
## Query Type Effectiveness:
{query_effectiveness}

- SKIP query types marked as ineffective above
```

### Pattern 6: JSON Response Template

Always end with explicit format:
```markdown
Respond with ONLY valid JSON (no markdown code blocks):
{{"key": [...]}}
```

---

## Quick Reference

| Prompt | Phase | Primary Input | Primary Output |
|--------|-------|---------------|----------------|
| hypothesis_generation | 1 | error + context + prior knowledge | `{"hypotheses": [...]}` |
| evidence_query | 2 | hypotheses + current evidence | `{"queries": [...]}` |
| causal_chain | 3 | hypothesis + evidence | `{"steps": [...]}` |
| causal_chain_with_evidence | 3 | hypothesis + evidence_list | `{"steps": [...]}` |
| adversarial_review | 4 | hypothesis + chain + evidence | `{"challenges": [...]}` |
| outcome_assessment | 5 | all summaries + counts | single object |
| final_synthesis | 6 | all artifacts | single object |
| prior_knowledge_summary | 0 | error + retrieved knowledge | single object |
| pattern_extraction | 7 | investigation results | single object |
| call_graph_summary | 0 | functions list | `{"func": "summary"}` |

---

*Last updated: 2026-02-02*
