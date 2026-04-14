> **Agentic Persona Library** | [← Analysis Personas](agentic-persona-library-ch3-analysis-personas.md) | [Table of Contents](agentic-persona-library.md) | [Next: Expert Panel →](agentic-persona-library-ch5-expert-panel.md)

---

# Chapter 4: Learning & Feedback Personas

This chapter covers personas that operate outside the core investigation loop: the Learner (Phase 7), the Reviewer (Phase 8, inline feedback), and the Navigator (proposed tool selection guide). These personas handle post-investigation learning and meta-level guidance rather than active root cause analysis.

The Learner is the only persona in this group with a full class implementation and LLM integration. The Reviewer exists as a conceptual persona with metadata registered in the persona registry but no dedicated class -- its feedback functionality is handled by the existing `PatternLearner` in `srcs/knowledge/pattern_learner.py`. The Navigator is a proposed rule-based persona that could guide agentic clients in tool selection.

---

## LEARNER (Phase 7)

### 1. Identity

| Property | Value |
|----------|-------|
| Phase | 7 |
| Name | Learner |
| Role | Pattern Learning |
| Color | `dim` |
| Thinking Phrase | `"Remembering for next time..."` |
| Prompt Key | `learner` |
| Uses LLM | Yes |
| Description | Extracts and stores patterns for future investigations |

**Traits**: observant, pattern-seeking, adaptive, reflective, forward-looking

**Thinking Style**: Pattern extraction -- identifies recurring patterns, extracts lessons learned, updates knowledge base, improves future investigation efficiency.

The Learner is the final persona in the investigation pipeline. Where every other persona focuses on the current investigation, the Learner looks forward: what can be learned from this case to make future investigations faster and more accurate? The Learner mines completed investigations for generalizable error signatures, root cause templates, effective evidence strategies, and calibration data.

### 2. Responsibilities

**Pipeline role**: Extracts and stores patterns from completed investigations for future use. Uses the LLM to identify generalizable error patterns, root cause patterns, evidence patterns, strategy recommendations, and calibration data. Falls back to rule-based extraction when the LLM is unavailable.

**Expert panel role**: Not included in `ask_experts` panels. The Learner operates post-investigation only.

**Artifacts produced**:

| Artifact | Type | Description |
|----------|------|-------------|
| Error Pattern | `ErrorPatternInfo` | Generalizable error signature with message template, contextual indicators, and false positive risk |
| Root Cause Pattern | `RootCausePatternInfo` | Reusable root cause description with confirming and refuting evidence lists |
| Evidence Patterns | `list[EvidencePatternInfo]` | Which types of evidence were most useful, with query templates and usefulness scores |
| Strategy Recommendations | `StrategyInfo` | Preferred investigation approach, key queries, shortcuts, and pitfalls |
| Calibration Data | `CalibrationInfo` | Stated confidence vs. actual accuracy with calibration adjustment direction |
| Lessons Learned | `list[str]` | Free-text insights for future investigations |

All of these are bundled into a single `PatternExtractionResponse` Pydantic model returned from the LLM.

**Artifacts consumed**: Complete investigation state -- the Learner reads contributions from all upstream personas (Archivist through Synthesizer), hypotheses, evidence items, causal chains, challenges, and the final investigation outcome from the Judge and Synthesizer.

### 3. Tool Mapping

| API Tool | Invokes Learner? | Capabilities Used |
|----------|-----------------|-------------------|
| `investigate` | Yes (Phase 7, if `enable_learning=true`) | Full pattern extraction |
| `investigate_stream` | Yes (Phase 7, if `enable_learning=true`) | Full extraction + SSE progress |
| All others | No | -- |

The Learner is only invoked as the final phase of the investigation pipeline. It is never invoked directly by an API tool, nor does it participate in the expert panel. Its activation is controlled by the `enable_learning` parameter on the `investigate` and `investigate_stream` tools (default: `true`).

### 4. Implementation

**Class**: `LearnerPersona` in `srcs/persona/learner.py`

**Internal models** (defined in the same file as Pydantic `BaseModel` subclasses):

```python
class ErrorPatternInfo(BaseModel):
    signature: str = ""
    message_template: str = ""
    contextual_indicators: List[str] = []
    false_positive_risk: str = "medium"

class RootCausePatternInfo(BaseModel):
    description_template: str = ""
    category: str = ""
    confirming_evidence: List[str] = []
    refuting_evidence: List[str] = []

class EvidencePatternInfo(BaseModel):
    type: str
    query_template: str = ""
    strength: str = "MODERATE"
    usefulness_score: float = 0.5

class StrategyInfo(BaseModel):
    preferred_approach: str = "hybrid"
    key_queries: List[str] = []
    shortcuts: List[str] = []
    pitfalls: List[str] = []

class CalibrationInfo(BaseModel):
    stated_confidence: float = 0.5
    actual_accuracy: str = "unknown"
    calibration_adjustment: str = "maintain"
    sample_size_note: str = ""

class PatternExtractionResponse(BaseModel):
    error_pattern: ErrorPatternInfo
    root_cause_pattern: RootCausePatternInfo
    evidence_patterns: List[EvidencePatternInfo] = []
    strategy_recommendations: StrategyInfo
    calibration: CalibrationInfo
    lessons_learned: List[str] = []
```

**Key methods**:

| Method | Description |
|--------|-------------|
| `prepare(context)` | No special preparation required. The Learner operates on already-completed investigation artifacts. |
| `contribute(context)` | Main work method. First checks `_should_extract_patterns()` to verify the investigation was sufficiently successful. If so, attempts LLM-based extraction via `_extract_with_llm()`. On LLM failure, falls back to `_extract_patterns_rules()`. Returns a `Contribution` with content dict. |
| `reflect(context)` | Evaluates extraction quality. Uses LLM extraction results if available, otherwise falls back to rule-based reflection. Reports insights (patterns found, shortcuts), uncertainties (high false positive risk, overconfidence), and suggestions (lessons learned). |
| `_should_extract_patterns(context)` | Guards pattern extraction. Checks Synthesizer confidence (must be >= 0.4) and Judge outcome (must not be INSUFFICIENT). Returns `False` to skip learning for low-quality investigations. |
| `_extract_with_llm(context)` | Constructs the `PATTERN_EXTRACTION` user prompt with investigation summary data, calls `_call_llm_structured()` with `PatternExtractionResponse` response model, returns parsed result or `None` on failure. |
| `_extract_patterns_rules(context)` | Rule-based fallback. Extracts error pattern from trigger error, root cause pattern from accepted hypotheses, evidence patterns from strong evidence items, calibration data from synthesizer contributions, and lessons learned from investigation gaps. |
| `_build_content_from_llm(extraction)` | Converts `PatternExtractionResponse` to content dict for the `Contribution`. Computes `patterns_learned` count and sets `extraction_method: "llm"`. |
| `_build_reasoning_from_llm(extraction)` | Builds reasoning string describing what was extracted (error signature, root cause category, evidence pattern count, lesson count, shortcut count). |

**LLM interaction**: The Learner uses `_call_llm_structured()` (inherited from `BasePersona`) with:
- System prompt: `SystemPromptType.LEARNER`
- Response model: `PatternExtractionResponse`
- Prompt key: `"pattern_extraction"`

This records both the LLM request and response as artifacts in the WorkBinder for full traceability.

**Content dict keys** (in `Contribution.content`):

When LLM extraction succeeds:
```python
{
    "error_pattern": {...},           # ErrorPatternInfo as dict
    "root_cause_pattern": {...},      # RootCausePatternInfo as dict
    "evidence_patterns": [...],       # List of EvidencePatternInfo dicts
    "strategy_recommendations": {...}, # StrategyInfo as dict
    "calibration": {...},             # CalibrationInfo as dict
    "lessons_learned": [...],         # List of strings
    "patterns_learned": N,            # Count of extracted patterns
    "extraction_method": "llm",
}
```

When rule-based fallback is used:
```python
{
    "error_pattern": {...} | None,     # Component, function, message fragment
    "root_cause_pattern": {...} | None, # Description, source, score
    "evidence_patterns": [...],        # Type, source, strength
    "calibration_update": {...} | None, # Stated confidence, outcome
    "lessons_learned": [...],          # Generated from investigation gaps
    "confidence": 0.5-0.7,            # Quality estimate
    "extraction_method": "rules",
}
```

**Fallback behavior**: If the LLM call fails (provider unreachable, parse error, timeout), the Learner falls back to `_extract_patterns_rules()`, which produces a simpler pattern using direct field extraction from the investigation context. This guarantees the Learner always produces a contribution, even without LLM access.

### 5. Prompt Anatomy

**System prompt**: `srcs/prompts/templates/system/learner.md`

The Learner system prompt defines its identity as a pattern extraction specialist. Key sections:

| Section | Content |
|---------|---------|
| IDENTITY | "You observe, extract, and preserve patterns from investigations to improve future ones." |
| EXPERTISE | Pattern recognition, knowledge base updating, calibration data collection, lesson identification, trend analysis |
| THINKING STYLE | Observant, pattern-seeking, adaptive, reflective, forward-looking |
| EXTRACTION FRAMEWORK | Five-part framework: error patterns, root cause patterns, evidence patterns, calibration data, lessons learned |
| CONSTRAINTS | Extract generalizable patterns, verify sample sizes, track both successful and unsuccessful patterns, update rather than overwrite |

The system prompt includes `{base_knowledge}` which is expanded at load time with the shared artdaq domain knowledge from `base.md`.

**User prompt**: `srcs/prompts/templates/user/pattern_extraction.md`

Template with 11 placeholders populated from the completed investigation:

| Placeholder | Source |
|-------------|--------|
| `{investigation_id}` | `binder.id[:8]` |
| `{outcome}` | Judge contribution content (`CONFIDENT`, `PROBABLE`, etc.) |
| `{confidence}` | Judge contribution confidence (formatted to 2 decimal places) |
| `{root_cause}` | Top-scored hypothesis description |
| `{error_message}` | Trigger error message |
| `{error_component}` | Trigger error component |
| `{error_function}` | Trigger error function |
| `{hypotheses_summary}` | Top 5 hypotheses with scores and sources |
| `{evidence_summary}` | Top 10 evidence items with strength and type |
| `{what_worked}` | High-validity causal chains, strong evidence counts |
| `{what_didnt_work}` | Low-validity chains, missing strong evidence |

The user prompt includes `{include:artifacts/schemas/pattern_extraction}` which provides the JSON response schema for structured output parsing.

### 6. Session State Interaction

**Reads**:

| State | Access Method | Purpose |
|-------|---------------|---------|
| Investigation result | `context.contributions` (judge, synthesizer) | Determine outcome and confidence |
| Hypotheses | `binder.get_hypotheses()` | Extract root cause pattern |
| Evidence items | `binder.get_evidence_items()` | Identify effective evidence types |
| Causal chains | `binder.get_causal_chains()` | Evaluate chain validity for lessons |
| Trigger error | `context.error` | Extract error pattern signature |
| All contributions | `context.contributions` | Analyze investigation quality |

**Writes**:

| State | Destination | Purpose |
|-------|-------------|---------|
| Extracted patterns | Knowledge base (SQLite + ChromaDB) via `PatternLearner` | Persist for future investigations |
| LLM exchanges | WorkBinder (via `_call_llm_structured`) | Full traceability of LLM requests/responses |
| Contribution | `context.contributions` | Available to coordinator for final summary |

**Binder**: Records LLM request and response artifacts through the `_call_llm_structured()` helper inherited from `BasePersona`. The request artifact captures the full system prompt, user prompt, model name, and temperature. The response artifact captures the parsed `PatternExtractionResponse`, latency, and success status.

### 7. SSE Events

When the investigation runs through `investigate_stream`, the Learner phase emits the following SSE events:

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 7, phase_name: "Pattern Learning"}` | Phase 7 begins execution |
| `llm_request` | `{phase: 7, model_name: "...", prompt_key: "pattern_extraction"}` | LLM called for pattern extraction |
| `llm_response` | `{phase: 7, response_model: "PatternExtractionResponse", latency_ms: N}` | LLM response received and parsed |
| `phase_complete` | `{phase: 7, data: {patterns_extracted: N, extraction_method: "llm"|"rules"}}` | Phase done, patterns counted |

If the investigation confidence is too low and learning is skipped, the `phase_complete` event includes `{patterns_extracted: 0, reason: "Investigation outcome insufficient"}`.

### 8. Expert Panel Behavior

The Learner is **not included** in `ask_experts` panels. The `PERSONA_SELECTION` mapping in `PanelOrchestrator` does not reference phase 7 for any question type. The Learner is strictly a post-investigation persona.

However, the `LearnerPersona` class does implement `answer_question(context: QuestionContext)` for completeness. When invoked directly, it contributes learning-focused content:

| Content Key | Description |
|-------------|-------------|
| `learning_opportunities` | What can be learned from this Q&A (based on question type) |
| `related_topics` | Suggested artdaq topics for deeper understanding |
| `resources` | Recommended learning resources (documentation, tutorials) |
| `follow_up_questions` | Suggested follow-up questions for deeper learning |
| `answer` | Learning-focused answer text |

This implementation exists for forward compatibility but is not currently exercised by the panel orchestrator.

### 9. Configuration & Tuning

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| `enable_auto_learning` | `InvestigationConfig` | `true` | Whether Phase 7 runs at all |
| `enable_learning` | `investigate` API request | `true` | Per-request override |
| Minimum synthesizer confidence | `_should_extract_patterns()` | 0.4 | Below this, patterns are not extracted |
| Judge outcome gate | `_should_extract_patterns()` | Not INSUFFICIENT | INSUFFICIENT outcomes skip learning |
| LLM temperature | Provider default | Varies | Uses provider's configured temperature |

The Learner only runs when:
1. The investigation reaches Phase 7 (all prior phases completed successfully)
2. `enable_auto_learning` / `enable_learning` is `true`
3. The investigation produced a sufficiently confident result (synthesizer confidence >= 0.4 and Judge outcome is not INSUFFICIENT)

### 10. Error Handling & Fallbacks

| Error Condition | Handling | Result |
|----------------|----------|--------|
| LLM provider unavailable | Falls back to `_extract_patterns_rules()` | Rule-based patterns with `extraction_method: "rules"` and lower confidence (0.5) |
| LLM response parse failure | Caught in `_extract_with_llm()`, returns `None` | Triggers rule-based fallback |
| Prompt formatting error | Caught in `_extract_with_llm()`, logs warning, returns `None` | Triggers rule-based fallback |
| Knowledge base unavailable | Patterns returned in contribution but not persisted | Warning logged, contribution still produced |
| Investigation insufficient | `_should_extract_patterns()` returns `False` | Contribution with `patterns_learned: 0` and `reason: "Investigation outcome insufficient"`, confidence 0.3 |
| No trigger error | Rule-based extraction produces `error_pattern: None` | Partial extraction with available data |
| No accepted hypotheses | Rule-based extraction produces `root_cause_pattern: None` | Partial extraction, confidence stays at 0.5 |

The Learner is designed to be resilient -- it should never cause an investigation to fail. All exceptions are caught and handled with graceful degradation.

### 11. Testing Contract

```
test_learner_extracts_patterns
  - Given a completed investigation with accepted hypothesis and strong evidence
  - Mock LLMProvider.generate_structured to return PatternExtractionResponse
  - When contribute(context) is called
  - Assert Contribution.content has all expected keys
  - Assert patterns_learned > 0
  - Assert extraction_method == "llm"

test_learner_stores_in_kb
  - Given extracted patterns from a completed investigation
  - When patterns are passed to PatternLearner
  - Assert error_pattern stored in SQLite
  - Assert root_cause_pattern associated with error_pattern
  - Assert ChromaDB embeddings updated

test_learner_llm_fallback
  - Given a completed investigation context with LLM provider
  - Mock LLMProvider.generate_structured to raise Exception
  - When contribute(context) is called
  - Assert Contribution.content has extraction_method == "rules"
  - Assert error_pattern extracted from context.error
  - Assert root_cause_pattern extracted from accepted hypotheses

test_learner_skipped_when_disabled
  - Given enable_auto_learning=false in InvestigationConfig
  - When pipeline executes Phase 7
  - Assert Phase 7 is skipped entirely
  - Assert no LLM calls made for pattern extraction

test_learner_skips_insufficient_outcome
  - Given Judge outcome == INSUFFICIENT
  - When contribute(context) is called
  - Assert _should_extract_patterns returns False
  - Assert Contribution has patterns_learned: 0

test_learner_skips_low_confidence
  - Given Synthesizer contribution with confidence < 0.4
  - When contribute(context) is called
  - Assert _should_extract_patterns returns False

test_learner_reflect_with_llm_extraction
  - Given a successful LLM extraction stored in _llm_extraction
  - When reflect(context) is called
  - Assert Reflection contains insights about extracted patterns
  - Assert uncertainties flagged for high false_positive_risk

test_learner_reflect_without_llm
  - Given no LLM extraction (fallback path)
  - When reflect(context) is called
  - Assert Reflection uses rule-based analysis
  - Assert suggestions include lessons from _generate_lessons_rules

test_learner_critique_endorsement
  - When critique(contribution) is called
  - Assert Critique evaluates learning value
  - When endorse(contribution) is called on contribution with reasoning
  - Assert endorsement is True

test_learner_rules_lessons
  - Given investigation with no evidence and limited hypothesis sources
  - When _generate_lessons_rules(context) is called
  - Assert lessons include "early evidence gathering" and "diversifying hypothesis generation"
```

**Mock requirements**: `LLMProvider` (for `generate_structured`), `KnowledgeBase` (for pattern storage), `WorkBinder` (for artifact recording and hypothesis/evidence/chain retrieval).

---

## REVIEWER (Phase 8 -- Inline Feedback)

> **Implementation status**: The Reviewer is a **conceptual persona** with metadata registered in the persona registry but no dedicated `ReviewerPersona` class. Feedback processing is handled by `PatternLearner.apply_feedback()` in `srcs/knowledge/pattern_learner.py`. A dedicated class is a future proposal (see Section 11 below).

### 1. Identity

| Property | Value |
|----------|-------|
| Phase | 8 |
| Name | Reviewer |
| Role | User Feedback |
| Color | `bright_green` |
| Thinking Phrase | `"Your feedback helps me learn..."` |
| Prompt Key | `None` |
| Uses LLM | No |
| Description | Solicits user feedback on investigation results and incorporates corrections |

**Traits**: evaluative, constructive, precise

**Thinking Style**: Feedback analysis -- evaluates investigation quality and provides inline annotations. The Reviewer does not reason about the investigation content itself; it processes user feedback to improve future pattern accuracy and confidence calibration.

### 2. Responsibilities

**Pipeline role**: Not part of the main investigation pipeline. The Reviewer is invoked when user feedback is submitted via the `feedback` CLI command or the `POST /api/v1/agent/feedback` API endpoint. It processes correct/incorrect feedback to update pattern accuracy and calibration data in the knowledge base.

**Expert panel role**: Not included in `ask_experts` panels.

**Artifacts produced**:

| Artifact | Description |
|----------|-------------|
| Updated calibration data | Adjusts confidence calibration buckets based on was_correct feedback |
| Pattern accuracy adjustments | Updates error pattern hit counts and accuracy scores |
| Root cause pattern reinforcement | Strengthens or weakens root cause associations based on feedback |

**Artifacts consumed**:

| Artifact | Description |
|----------|-------------|
| Investigation feedback | User-provided correct/incorrect signal with optional actual cause |
| Stored patterns | Previously learned error and root cause patterns |
| Calibration buckets | Existing confidence calibration data |

### 3. Tool Mapping

The Reviewer does not map directly to any agentic API tool. Feedback flows through:

| Interface | Endpoint / Command | Handler |
|-----------|-------------------|---------|
| CLI | `./run.sh feedback <id> --correct` | `srcs/cli/main.py` |
| API | `POST /api/v1/agent/feedback` | `srcs/api/routes.py` (proposed) |
| Slack | Reaction-based feedback | `srcs/slack/handler.py` |

All interfaces ultimately call `PatternLearner.apply_feedback()` in `srcs/knowledge/pattern_learner.py`.

### 4. Implementation

The Reviewer persona is currently defined at the **conceptual level**. Its metadata is registered in the persona registry:

```python
# srcs/persona/personas.py
PHASE_REVIEWER = 8

PERSONAS[PHASE_REVIEWER] = Persona(
    phase=PHASE_REVIEWER,
    name="Reviewer",
    role="User Feedback",
    color="bright_green",
    thinking_phrase="Your feedback helps me learn...",
    prompt_key=None,
    uses_llm=False,
    description="Solicits user feedback on investigation results and incorporates corrections",
)
```

There is **no dedicated `ReviewerPersona` class** that extends `BasePersona`. The feedback functionality is handled by the existing `PatternLearner` class:

**Feedback processing** (`srcs/knowledge/pattern_learner.py`):

```python
class PatternLearner:
    async def apply_feedback(
        self,
        investigation_id: str,
        was_correct: bool,
        actual_cause: str = None,
        feedback_source: str = "cli",
    ):
        """Apply user feedback to update pattern accuracy and calibration."""
        # 1. Load the investigation from the knowledge base
        # 2. Find associated error patterns
        # 3. Update pattern accuracy (hit count, correct count)
        # 4. Update calibration buckets
        # 5. If actual_cause provided, create/update root cause pattern
```

### 5. Prompt Anatomy

The Reviewer does not use LLM prompts. Its `prompt_key` is `None` and `uses_llm` is `False`. All feedback processing is algorithmic.

### 6-7. Session State & SSE Events

Since the Reviewer operates outside the investigation pipeline, it does not interact with investigation session state or emit SSE events during investigation. Feedback submissions are standalone operations that modify the knowledge base directly.

### 8. Expert Panel Behavior

Not included in expert panels. The Reviewer has no `answer_question()` implementation.

### 9. Configuration & Tuning

Feedback processing is configured through `LearningConfig` in `srcs/knowledge/learning_config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_pattern_confidence` | 0.3 | Minimum confidence for pattern creation |
| `min_similar_count` | 3 | Minimum similar cases before creating a new pattern |
| `decay_months` | 6 | Months before unused patterns begin to decay |
| `decay_factor` | 0.95 | Monthly decay multiplier for stale patterns |

### 10. Error Handling

| Error Condition | Handling |
|----------------|----------|
| Investigation not found | Returns error message to caller |
| No associated patterns | Logs warning, skips pattern update |
| Database write failure | Logs error, raises to caller |

### 11. Future Implementation

In the agentic API context, a dedicated `ReviewerPersona` class could be implemented to provide capabilities beyond simple feedback recording:

| Capability | Description |
|------------|-------------|
| Feedback pattern analysis | Analyze feedback patterns across multiple investigations to identify systematic issues |
| Calibration adjustment suggestions | Recommend calibration bucket adjustments based on accumulated feedback |
| Over/under-confidence detection | Identify when specific error types or components consistently produce miscalibrated confidence |
| Meta-learning reports | Generate reports on how the system's accuracy is trending over time |
| Active feedback solicitation | Identify investigations where feedback would be most valuable for learning |

A future `ReviewerPersona` implementation would:

```python
class ReviewerPersona(BasePersona):
    """Processes feedback and generates meta-learning insights."""

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_REVIEWER]

    @property
    def traits(self) -> list[str]:
        return ["evaluative", "constructive", "precise"]

    async def contribute(self, context: InvestigationContext) -> Contribution:
        """Analyze feedback patterns for this investigation type."""
        # Query historical feedback for similar error patterns
        # Identify calibration drift
        # Suggest accuracy improvements
        ...

    async def answer_question(self, context: QuestionContext) -> Contribution:
        """Contribute feedback-informed insights to Q&A."""
        # "Based on feedback from 15 similar investigations,
        #  this diagnosis is correct 80% of the time..."
        ...
```

This remains a design proposal. The current feedback system via `PatternLearner.apply_feedback()` is functional and covers the core use case.

---

## NAVIGATOR (Proposed)

### 1. Identity

| Property | Value |
|----------|-------|
| Phase | -- (meta-level) |
| Name | Navigator |
| Role | Tool Selection Guide |
| Color | `bright_blue` (proposed) |
| Thinking Phrase | N/A |
| Prompt Key | `None` |
| Uses LLM | No |
| Description | Analyzes session state and recommends optimal next tools for the calling agent |

**Traits**: strategic, efficient, contextual, directive

**Thinking Style**: Strategic planning -- analyzes current session state, identifies what has been accomplished and what remains, and recommends which API tools the calling agent should invoke next.

### 2. Responsibilities

**Purpose**: In the agentic REST API architecture (see [Chapter 1: Architecture](agentic-rest-service-design-ch1-architecture.md)), the calling LLM must choose which of the 21 available tools to invoke at each step. This is a non-trivial decision that requires understanding the investigation workflow. The Navigator persona could reduce the cognitive burden on the calling agent by providing explicit tool recommendations.

**Why proposed**: The current tool design provides self-contained individual tools with clear purposes, and the tool descriptions in the API schema are designed to be sufficient for an LLM agent to make good selections. However, in practice, agents may:

- Invoke tools in suboptimal order (e.g., calling `investigate` before `parse_logs`)
- Miss useful tools (e.g., not calling `correlate_events` when multiple components are involved)
- Repeat redundant calls (e.g., calling `get_prior_knowledge` after `match_pattern` has already covered patterns)
- Fail to recognize when an investigation is complete

A Navigator could address these issues without requiring the calling agent to learn the full investigation workflow.

**Rule-based (no LLM required)**: The Navigator would operate entirely through session state analysis. It examines what tools have been called, what data is available, and what investigation gaps remain, then produces ranked recommendations. No LLM calls are needed.

### 3. Tool Mapping

The Navigator could be exposed in two ways:

**Option A: Dedicated endpoint**

```
POST /api/v1/agent/tools/suggest_next_tool
```

Request:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Response:
```json
{
  "suggestions": [
    {
      "tool": "parse_logs",
      "reason": "No logs parsed yet. Log parsing is required before investigation.",
      "priority": 1
    },
    {
      "tool": "get_log_summary",
      "reason": "After parsing, a summary helps identify the primary error.",
      "priority": 2
    }
  ],
  "investigation_status": "not_started",
  "completion_pct": 0
}
```

**Option B: Inline `suggested_next` field**

Every tool response could include an optional `suggested_next` field:

```json
{
  "logs": [...],
  "total": 150,
  "suggested_next": [
    {"tool": "search_logs", "reason": "Search for ERROR-level entries to find the trigger error"},
    {"tool": "get_log_summary", "reason": "Get aggregate statistics for the parsed logs"}
  ]
}
```

Option B is less intrusive and does not require the agent to make an extra API call, but Option A provides richer context including overall investigation status.

### 4. Implementation (Proposed)

```python
from dataclasses import dataclass


@dataclass
class ToolSuggestion:
    """A recommended next tool invocation."""

    tool: str
    reason: str
    priority: int
    required_params: dict | None = None


class NavigatorPersona:
    """Rule-based tool recommendation engine.

    Analyzes session state and recommends optimal next tools
    for the calling agent. Does not use LLM -- all logic is
    rule-based state analysis.
    """

    def suggest_next(self, session_state: dict) -> list[ToolSuggestion]:
        """Analyze session and suggest next tools.

        Args:
            session_state: Current session state dict containing
                keys like 'logs_parsed', 'trigger_error',
                'investigation_result', 'patterns_matched', etc.

        Returns:
            Ranked list of tool suggestions
        """
        suggestions: list[ToolSuggestion] = []

        # Stage 1: Log parsing
        if not session_state.get("logs_parsed"):
            suggestions.append(ToolSuggestion(
                tool="parse_logs",
                reason="No logs parsed yet. Start by parsing log content.",
                priority=1,
            ))
            return suggestions  # Nothing else makes sense yet

        # Stage 2: Error identification
        if not session_state.get("trigger_error"):
            suggestions.append(ToolSuggestion(
                tool="search_logs",
                reason="Search for ERROR-level entries to identify the trigger error.",
                priority=1,
            ))
            suggestions.append(ToolSuggestion(
                tool="get_log_summary",
                reason="Get aggregate statistics to understand error distribution.",
                priority=2,
            ))
            return suggestions

        # Stage 3: Pre-investigation enrichment
        if not session_state.get("investigation_result"):
            if not session_state.get("error_source"):
                suggestions.append(ToolSuggestion(
                    tool="find_error_source",
                    reason="Locate where the trigger error originates in source code.",
                    priority=1,
                ))
            if not session_state.get("prior_knowledge"):
                suggestions.append(ToolSuggestion(
                    tool="get_prior_knowledge",
                    reason="Check for known patterns and similar past investigations.",
                    priority=2,
                ))
            suggestions.append(ToolSuggestion(
                tool="investigate",
                reason="Trigger error identified. Ready for full investigation.",
                priority=3 if suggestions else 1,
            ))
            return suggestions

        # Stage 4: Post-investigation follow-up
        result = session_state.get("investigation_result", {})
        outcome = result.get("outcome", "")

        if outcome in ("UNCERTAIN", "INSUFFICIENT"):
            suggestions.append(ToolSuggestion(
                tool="get_call_graph",
                reason="Investigation inconclusive. Explore call graph for additional context.",
                priority=1,
            ))
            suggestions.append(ToolSuggestion(
                tool="search_code",
                reason="Search for related code patterns that may provide missing evidence.",
                priority=2,
            ))
        elif outcome in ("CONFIDENT", "PROBABLE"):
            suggestions.append(ToolSuggestion(
                tool="ask_experts",
                reason="Investigation complete. Ask experts for additional context or recommendations.",
                priority=1,
            ))

        return suggestions

    def get_investigation_status(self, session_state: dict) -> dict:
        """Get overall investigation status summary.

        Returns:
            Dict with status, completion_pct, and phase descriptions
        """
        stages = {
            "logs_parsed": bool(session_state.get("logs_parsed")),
            "trigger_identified": bool(session_state.get("trigger_error")),
            "source_located": bool(session_state.get("error_source")),
            "prior_knowledge": bool(session_state.get("prior_knowledge")),
            "investigation_complete": bool(session_state.get("investigation_result")),
            "feedback_provided": bool(session_state.get("feedback")),
        }

        completed = sum(1 for v in stages.values() if v)
        total = len(stages)

        if not stages["logs_parsed"]:
            status = "not_started"
        elif not stages["trigger_identified"]:
            status = "parsing_complete"
        elif not stages["investigation_complete"]:
            status = "investigating"
        elif not stages["feedback_provided"]:
            status = "awaiting_feedback"
        else:
            status = "complete"

        return {
            "status": status,
            "completion_pct": int((completed / total) * 100),
            "stages": stages,
        }
```

### 5. Prompt Anatomy

Not applicable. The Navigator is entirely rule-based and does not use LLM prompts.

### 6. Session State Interaction

**Reads**: The Navigator reads session state to determine what tools have been invoked and what data is available. Key session state keys:

| Key | Type | Set By |
|-----|------|--------|
| `logs_parsed` | `bool` | `parse_logs` tool |
| `parsed_logs` | `list[Log]` | `parse_logs` tool |
| `trigger_error` | `Log` | `search_logs` or `get_log_context` |
| `error_source` | `SourceLocationResult` | `find_error_source` tool |
| `prior_knowledge` | `PriorKnowledge` | `get_prior_knowledge` tool |
| `patterns_matched` | `list[PatternMatch]` | `match_pattern` tool |
| `investigation_result` | `InvestigationResult` | `investigate` tool |
| `feedback` | `dict` | `feedback` tool |

**Writes**: The Navigator does not modify session state. It is read-only.

### 7. SSE Events

Not applicable. The Navigator produces a synchronous response.

### 8. Expert Panel Behavior

Not applicable. The Navigator is not a panel participant.

### 9. Configuration & Tuning

| Parameter | Proposed Default | Description |
|-----------|-----------------|-------------|
| `enable_navigator` | `false` | Whether the Navigator endpoint is available |
| `inline_suggestions` | `false` | Whether to include `suggested_next` in all tool responses |
| `max_suggestions` | 3 | Maximum suggestions per response |

### 10. Error Handling

The Navigator is simple and stateless. Its primary failure mode is an invalid or missing session, which would return the standard `session_not_found` error. Invalid session state is handled by treating missing keys as "not yet done" (defaulting to `False`/`None`).

### 11. Design Decision

**Decision**: Start with **Option B** (inline `suggested_next` fields in tool responses). This provides guidance without requiring the agent to learn a new tool or make an extra API call.

If agents consistently make poor tool selections in practice, escalate to a dedicated Navigator endpoint (Option A) in a future iteration.

**Rationale**: The calling agent/LLM may already handle tool selection adequately based on tool descriptions alone. A dedicated endpoint adds complexity and an additional API call whose value is unproven. Inline suggestions achieve the same goal with zero overhead.

**Interaction with other designs**: The Navigator concept is related to the discussion of agentic workflows in [Chapter 6: Client Refactoring](agentic-rest-service-design-ch6-client-refactoring.md). The client-side agent loop described there could benefit from server-side tool recommendations, reducing the amount of workflow knowledge embedded in client code.

---

## Persona Comparison

| Property | Learner | Reviewer | Navigator |
|----------|---------|----------|-----------|
| Phase | 7 | 8 | -- |
| Pipeline position | Final phase | Post-investigation | Meta-level |
| Uses LLM | Yes | No | No |
| Has class impl | Yes (`LearnerPersona`) | No (conceptual -- uses `PatternLearner`) | No (proposed -- Option B inline) |
| In expert panel | No | No | No |
| Modifies KB | Yes (via PatternLearner) | Yes (via apply_feedback) | No |
| Session interaction | Reads investigation state | Reads feedback input | Reads session state |
| SSE events | Yes (phase 7) | No | No |
| Can fail investigation | No (resilient) | N/A (standalone) | N/A (standalone) |

---

> [← Analysis Personas](agentic-persona-library-ch3-analysis-personas.md) | [Table of Contents](agentic-persona-library.md) | [Next: Expert Panel →](agentic-persona-library-ch5-expert-panel.md)
