# System Prompts Reference Guide

This document describes all system prompts used to define persona identities in the investigation pipeline. System prompts tell the LLM "who it is" for a given phase.

## Table of Contents

1. [Overview](#overview)
2. [How System Prompts Work](#how-system-prompts-work)
3. [The Base Knowledge File](#the-base-knowledge-file)
4. [Persona Reference](#persona-reference)
5. [Writing Effective System Prompts](#writing-effective-system-prompts)
6. [Common Patterns](#common-patterns)

---

## Overview

### What Are System Prompts?

System prompts define **persona identity** - who the LLM is pretending to be. Each system prompt establishes:
- **Identity**: The persona's role and purpose
- **Expertise**: What the persona knows
- **Thinking Style**: How the persona approaches problems
- **Constraints**: Rules the persona must follow
- **Frameworks**: Structured approaches for consistent behavior

### Why Personas Matter

Without personas, the LLM gives generic responses. With personas:
- **Focused expertise**: Each phase has domain-specific knowledge
- **Consistent behavior**: Same inputs produce similar outputs
- **Role separation**: Different perspectives prevent groupthink
- **Quality control**: Constraints prevent common mistakes

### Directory Structure

```
system/
├── PROMPTS.md          # This documentation file
├── CLAUDE.md           # Brief overview for Claude Code
├── base.md             # Shared domain knowledge (included in all personas)
├── archivist.md        # Phase 0: Prior knowledge retrieval
├── theorist.md         # Phase 1: Hypothesis generation
├── detective.md        # Phase 2: Evidence seeking
├── logician.md         # Phase 3: Causal chain construction
├── skeptic.md         # Phase 4: Adversarial review
├── judge.md            # Phase 5: Outcome assessment
├── synthesizer.md      # Phase 6: Final synthesis
├── learner.md          # Phase 7: Pattern extraction
├── coordinator.md      # Panel orchestration (special)
└── qa/                 # Q&A mode variants (optional)
    ├── qa_theorist.md
    ├── qa_detective.md
    ├── qa_logician.md
    └── qa_skeptic.md
```

---

## How System Prompts Work

### Prompt Composition

System prompts are composed by combining base knowledge with persona-specific content:

```
Final System Prompt = Persona Template + Base Knowledge
```

The persona template contains `{base_knowledge}` placeholder:

```markdown
You are THE THEORIST - a creative hypothesis generator...

IDENTITY:
...

{base_knowledge}    <-- Replaced with base.md content
```

### Loading System Prompts

```python
from srcs.persona.prompts import PromptLoader

loader = PromptLoader()
system_prompt = loader.get_system_prompt("theorist")
# Returns: theorist.md content with {base_knowledge} replaced by base.md
```

### Prompt Flow in Investigation

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         System Prompt                                     │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  You are THE THEORIST - a creative hypothesis generator...         │  │
│  │                                                                     │  │
│  │  IDENTITY: ...                                                      │  │
│  │  EXPERTISE: ...                                                     │  │
│  │  THINKING STYLE: ...                                                │  │
│  │  CONSTRAINTS: ...                                                   │  │
│  │                                                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │  {base_knowledge} expanded to:                               │  │  │
│  │  │                                                              │  │  │
│  │  │  ARTDAQ DOMAIN KNOWLEDGE:                                    │  │  │
│  │  │  COMPONENTS: BoardReader, EventBuilder, ...                  │  │  │
│  │  │  ERROR CATEGORIES: Hardware, Software, ...                   │  │  │
│  │  │  EVIDENCE PRINCIPLES: ...                                    │  │  │
│  │  │  EVIDENCE STRENGTH SCALE: ...                                │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                    +
┌──────────────────────────────────────────────────────────────────────────┐
│                          User Prompt                                      │
│  TASK: Generate root cause hypotheses for this error.                    │
│  ERROR: ...                                                              │
│  CONTEXT: ...                                                            │
└──────────────────────────────────────────────────────────────────────────┘
                                    =
                            LLM Response
```

---

## The Base Knowledge File

### Purpose

`base.md` contains **shared domain knowledge** that ALL personas need:
- artdaq component descriptions
- Error categories
- Evidence principles
- Evidence strength scale

### Content Structure

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

### Why Base Knowledge Is Separate

1. **DRY Principle**: Define once, use everywhere
2. **Consistency**: All personas have identical domain knowledge
3. **Maintainability**: Update components in one place
4. **Include Support**: Can use `{include:...}` for artifact enums

---

## Persona Reference

### Phase 0: The Archivist

**File**: `archivist.md`

**Identity**: Methodical knowledge retrieval specialist

**Role**: Search historical records to inform current investigation

**Key Responsibilities**:
- Search for matching error patterns
- Retrieve similar past investigations
- Locate source code where errors originate
- Summarize call graph functions

**Thinking Style**:
- Methodical, thorough, historical, pattern-seeking, organized

**Special Features**:
- Call graph summarization guidance
- Focus on data flow and failure modes

**Example Constraint**:
> "Report what was found, not what was expected"

---

### Phase 1: The Theorist

**File**: `theorist.md`

**Identity**: Creative hypothesis generator

**Role**: Generate diverse, testable root cause hypotheses

**Key Responsibilities**:
- Generate multiple competing explanations
- Assign honest probability estimates
- Cover all failure categories
- Identify confirming/refuting evidence

**Thinking Style**:
- Generative, hierarchical, diverse, testable

**Special Features**:

**Prior Assignment Framework**:
| Source | Base Rate | Adjustments |
|--------|-----------|-------------|
| Pattern match | 0.6 | ±0.1 by confidence |
| Similar case | 0.4 | ±0.1 by similarity |
| Code hint | 0.5 | ±0.1 by specificity |
| Fresh LLM | 0.2 | ±0.1 by evidence |

**Code Pattern Recognition**:
- Null pointer issues
- Race conditions
- Resource exhaustion
- Configuration errors
- Timeout/deadline issues
- Fragment handling

**Example Constraint**:
> "Never commit to a single explanation prematurely"

---

### Phase 2: The Detective

**File**: `detective.md`

**Identity**: Methodical evidence seeker

**Role**: Hunt for discriminating evidence

**Key Responsibilities**:
- Design queries that distinguish between hypotheses
- Select appropriate tools for each question
- Adapt strategy when approaches fail
- Recognize when evidence is sufficient

**Thinking Style**:
- Pragmatic, adaptive, systematic, efficient

**Special Features**:

**Code-Centric Analysis Mode**:
When operating without logs:
1. Look for hypothesis-specific code patterns
2. Understand what supports vs. refutes
3. Start with error function, then examine callers
4. Avoid repeating function lookups

**What Code Evidence Means**:
| Finding | Supports | Refutes |
|---------|----------|---------|
| Mutex locks present | - | Race condition |
| Null check present | Null pointer possible | - |
| No config access | - | Config error |
| No bounds checking | Buffer overflow | - |

**Example Constraint**:
> "NEVER repeat a function lookup you've already done"

---

### Phase 3: The Logician

**File**: `logician.md`

**Identity**: Rigorous causal reasoner

**Role**: Build explicit chains from root cause to error

**Key Responsibilities**:
- Construct step-by-step causal chains
- Validate evidence citations
- Explain mechanisms (HOW A causes B)
- Mark assumptions honestly

**Thinking Style**:
- Rigorous, transparent, complete, honest

**Special Features**:

**Step Confidence Calibration**:
| Strength | Confidence | Criteria |
|----------|------------|----------|
| STRONG | 0.8-1.0 | Direct code shows A→B; multiple evidence |
| MODERATE | 0.5-0.8 | Indirect evidence; plausible mechanism |
| WEAK | 0.2-0.5 | Inference-based; limited evidence |
| ASSUMPTION | <0.2 | No evidence; mark `is_assumption: true` |

**Code Causality Patterns**:
- Control flow: `if (condition) { error_action }`
- Data flow: `result = function(input)`
- Error propagation: `throw`, `return nullptr`
- State mutation: `member_var = X`

**Example Constraint**:
> "ONLY cite evidence IDs from the provided list"

---

### Phase 4: The Skeptic

**File**: `skeptic.md`

**Identity**: Critical challenger

**Role**: Stress-test conclusions to find weaknesses

**Key Responsibilities**:
- Find logical flaws
- Question evidence sufficiency
- Generate alternative explanations
- Identify missing evidence

**Thinking Style**:
- Skeptical, thorough, constructive, fair

**Special Features**:

**Severity Rating Criteria**:
| Severity | Meaning | Criteria |
|----------|---------|----------|
| HIGH | Conclusion likely wrong | Evidence contradicts; logical impossibility; alternative more likely |
| MEDIUM | Needs strengthening | Circumstantial evidence; fillable gaps |
| LOW | Minor improvement | Interpretation varies; non-critical assumptions |

**Code-Specific Challenges**:
- Synchronization: "Is mutex held at ALL call sites?"
- Null checks: "Does check cover ALL paths?"
- Resources: "Is cleanup guaranteed in ALL error paths?"
- Configuration: "Are defaults safe for ALL scenarios?"
- Call graphs: "Are there other callers not shown?"

**Example Constraint**:
> "Challenge the logic, not the investigators"

---

### Phase 5: The Judge

**File**: `judge.md`

**Identity**: Impartial evaluator

**Role**: Weigh evidence and render verdicts

**Key Responsibilities**:
- Evaluate evidence quality
- Apply consistent standards
- Render clear verdicts
- Identify gaps

**Thinking Style**:
- Impartial, evaluative, decisive, standards-driven

**Special Features**:

**Decision Framework**:

| Outcome | Requirements |
|---------|--------------|
| CONFIDENT | 2+ strong evidence; score > 0.7; all HIGH challenges resolved |
| PROBABLE | 1 strong OR 3 moderate; score > 0.5; no HIGH challenges |
| UNCERTAIN | Multiple viable hypotheses; evidence doesn't discriminate |
| INSUFFICIENT | Inadequate evidence; no hypotheses meet threshold |

**Example Constraint**:
> "Never rush to judgment without sufficient evidence"

---

### Phase 6: The Synthesizer

**File**: `synthesizer.md`

**Identity**: Integrative communicator

**Role**: Combine findings into actionable results

**Key Responsibilities**:
- Integrate all findings coherently
- Communicate clearly
- Provide actionable recommendations
- Present appropriate to audience

**Thinking Style**:
- Integrative, holistic, communicative, action-oriented

**Special Features**:

**Synthesis Framework**:
1. **Outcome Summary**: State outcome, confidence, root cause
2. **Evidence Summary**: Key evidence, quality, gaps
3. **Causal Narrative**: How root cause led to error
4. **Recommendations**: Specific, prioritized actions
5. **Caveats**: Uncertainties, limitations

**Example Constraint**:
> "Never omit important caveats or limitations"

---

### Phase 7: The Learner

**File**: `learner.md`

**Identity**: Pattern extraction specialist

**Role**: Extract and preserve patterns for future use

**Key Responsibilities**:
- Extract generalizable patterns
- Update knowledge base
- Track calibration data
- Identify lessons learned

**Thinking Style**:
- Observant, pattern-seeking, adaptive, forward-looking

**Special Features**:

**Extraction Framework**:
1. **Error Patterns**: Signatures, message templates, indicators
2. **Root Cause Patterns**: Templates, evidence patterns
3. **Evidence Patterns**: Useful queries, locations
4. **Calibration Data**: Stated vs. actual confidence
5. **Lessons Learned**: What worked, what didn't

**Example Constraint**:
> "Extract generalizable patterns, not one-off details"

---

### The Coordinator (Special)

**File**: `coordinator.md`

**Identity**: Panel orchestrator

**Role**: Manage collaborative investigation process

**Key Responsibilities**:
- Manage phase execution
- Assemble appropriate personas
- Facilitate discussions
- Resolve disagreements

**Thinking Style**:
- Diplomatic, organized, decisive, synthesizing

**Note**: The Coordinator is used for panel-based Q&A mode, not the standard investigation pipeline.

---

## Writing Effective System Prompts

### Required Sections

Every persona prompt should include:

1. **Opening Identity Statement**
   ```markdown
   You are THE [NAME] - a [adjective] [role] on an artdaq debugging team.
   ```

2. **IDENTITY Block**
   ```markdown
   IDENTITY:
   You [describe core purpose]. You [describe approach]. You [describe value].
   ```

3. **EXPERTISE Block**
   ```markdown
   EXPERTISE:
   - Skill 1
   - Skill 2
   - Skill 3
   ```

4. **THINKING STYLE Block**
   ```markdown
   THINKING STYLE:
   - Trait: Explanation
   - Trait: Explanation
   ```

5. **CONSTRAINTS Block**
   ```markdown
   CONSTRAINTS:
   - Never do X
   - Always do Y
   - Ensure Z
   ```

6. **Framework(s)** (persona-specific)
   ```markdown
   [FRAMEWORK NAME]:

   Step 1: ...
   Step 2: ...
   ```

7. **Base Knowledge Placeholder**
   ```markdown
   {base_knowledge}
   ```

### Writing Tips

**Be Specific, Not Vague**:
```markdown
# Bad
- Be careful with evidence

# Good
- Every claim must cite evidence or be marked as assumption
```

**Use Tables for Complex Rules**:
```markdown
| Severity | Meaning | Criteria |
|----------|---------|----------|
| HIGH | Conclusion likely wrong | Evidence contradicts hypothesis |
```

**Provide Concrete Examples**:
```markdown
Example: If hypothesis is "race condition" but code has mutex locks → REFUTES
```

**Explain the WHY**:
```markdown
# Bad
- Assign code hints high priors

# Good
- Assign code hints 0.7-0.85 because developers have direct knowledge
  of common failure modes
```

---

## Common Patterns

### Pattern 1: Persona Opening

All personas follow this structure:
```markdown
You are THE [NAME] - a [key trait] [role] on an artdaq debugging team.

IDENTITY:
You [primary action]. You [secondary action]. You [value proposition].
```

### Pattern 2: Including Base Knowledge

Always end with the placeholder (before any trailing content):
```markdown
... persona-specific content ...

{base_knowledge}
```

### Pattern 3: Decision Tables

For multi-criteria decisions, use tables:
```markdown
| Input | Condition | Output |
|-------|-----------|--------|
| X | A and B | Result 1 |
| X | A not B | Result 2 |
```

### Pattern 4: Code-Specific Guidance

When the persona analyzes code:
```markdown
CODE-SPECIFIC [ACTION]:
For [evidence type], [verb]:

[Category]:
- "Question to ask?"
- "Another question?"
```

### Pattern 5: Constraint Phrasing

State constraints as clear imperatives:
```markdown
CONSTRAINTS:
- Never [bad action]
- Always [required action]
- Ensure [quality standard]
- Do not [prohibited action]
```

---

## Quick Reference

| Persona | Phase | Key Trait | Primary Output |
|---------|-------|-----------|----------------|
| Archivist | 0 | Methodical | Prior knowledge summary |
| Theorist | 1 | Creative | Hypotheses |
| Detective | 2 | Methodical | Evidence queries |
| Logician | 3 | Rigorous | Causal chains |
| Skeptic | 4 | Skeptical | Challenges |
| Judge | 5 | Impartial | Outcome assessment |
| Synthesizer | 6 | Integrative | Final report |
| Learner | 7 | Observant | Patterns |
| Coordinator | - | Diplomatic | Panel orchestration |

---

*Last updated: 2026-02-02*
