> **Agentic Persona Library** | [← Learning Personas](agentic-persona-library-ch4-learning-personas.md) | [Table of Contents](agentic-persona-library.md) | [Next: Prompt Architecture →](agentic-persona-library-ch6-prompt-architecture.md)

---

# Chapter 5: Expert Panel & Collaboration

The expert panel system enables collaborative question answering by assembling a dynamically selected group of personas, gathering their individual contributions, running consensus voting, deliberating on disagreements, and synthesizing a unified answer. This chapter documents the `PanelOrchestrator`, its `CoordinatorPersona`, question classification, persona selection, voting mechanics, deliberation protocol, synthesis logic, SSE event model, and all supporting data models.

Cross-reference: The `ask_experts` API tool that exposes the panel is documented in [Chapter 5: Pipeline, Expert & Admin Tools](agentic-rest-service-design-ch5-pipeline-admin-tools.md#tool-19-ask_experts).

---

## 1. PanelOrchestrator Overview

**Class**: `PanelOrchestrator` in `srcs/persona/orchestrator.py`

**Main method**: `answer(question, related_logs, callback)` returns `PanelResponse`

The `PanelOrchestrator` manages the full lifecycle of a collaborative Q&A session. It does not participate as a persona itself -- it is the orchestration layer that coordinates multiple persona instances.

### Workflow

```
                    ┌─────────────────────────────────────────┐
                    │         PanelOrchestrator.answer()       │
                    └───────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  1. Classify Question Type     │
                    │  (_classify_question)          │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  2. Select Personas            │
                    │  (PERSONA_SELECTION mapping)   │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  3. Gather Contributions       │
                    │  (sequential, with prior       │
                    │   contribution visibility)     │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  4. Voting Round               │
                    │  (endorse/critique per         │
                    │   contribution)                │
                    └───────────────┬───────────────┘
                                    │
                              ┌─────▼─────┐
                              │ Consensus  │
                              │ >= 0.7 ?   │
                              └─────┬──────┘
                                    │
                        ┌───────────┼───────────┐
                        │ Yes                   │ No
                        │                       │
                        │         ┌─────────────▼────────────┐
                        │         │  5. Deliberation Rounds   │
                        │         │  (up to 2 rounds)         │
                        │         └─────────────┬─────────────┘
                        │                       │
                        │         ┌─────────────▼─────────────┐
                        │         │  Re-vote after deliberation│
                        │         └─────────────┬─────────────┘
                        │                       │
                        └───────────┬───────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  6. Synthesize Response        │
                    │  (_synthesize_response)        │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  Return PanelResponse          │
                    └───────────────────────────────┘
```

### Constructor

```python
class PanelOrchestrator:
    def __init__(self, llm_provider: Any = None) -> None:
```

The `llm_provider` parameter is stored for potential future use in LLM-based question classification. Currently, question classification is keyword-based and does not use the LLM.

The orchestrator lazily instantiates persona instances via `_get_persona(phase)`, which maps phase numbers to persona classes:

| Phase | Class |
|-------|-------|
| 0 | `ArchivistPersona` |
| 1 | `TheoristPersona` |
| 2 | `DetectivePersona` |
| 3 | `LogicianPersona` |
| 4 | `SkepticPersona` |
| 5 | `JudgePersona` |
| 6 | `SynthesizerPersona` |
| 7 | `LearnerPersona` |

Persona instances are cached in `self._personas: dict[int, BasePersona]` and reused across multiple questions within the same orchestrator lifetime.

### Callback System

The `answer()` method accepts an optional `QACallback`:

```python
QAEvent = dict[str, Any]
QACallback = Callable[[QAEvent], None]
```

The callback receives event dicts with an `"event"` key indicating the type. This is the mechanism used by the `ask_experts` API tool to emit SSE events during streaming mode.

---

## 2. Question Classification

**Method**: `PanelOrchestrator._classify_question(question: str) -> QuestionType`

Question classification determines which personas are selected and how the panel approaches the question. Classification is entirely keyword-based -- no LLM calls are made.

### Classification Logic

The classifier checks keywords in priority order. The first match wins:

| Priority | QuestionType | Keywords / Patterns | Example |
|----------|-------------|-------------------|---------|
| 1 (highest) | `TROUBLESHOOT` | `error`, `fail`, `crash`, `timeout`, `problem`, `issue`, `not working`, `doesn't work`, `broken`, `exception` | "I'm seeing a timeout error on BoardReader_01" |
| 2 | `HOW_TO` | `how do i`, `how to`, `how can i`, `how should i` | "How do I configure fragment timeout?" |
| 3 | `WHY` | Starts with `why ` or contains ` why ` | "Why does EventBuilder stall when BoardReader times out?" |
| 4 | `WHAT_IS` | `what is`, `what are`, `what does`, `explain` | "What is the fragment timeout parameter?" |
| 5 | `COMPARE` | `difference between`, `compare`, `vs`, `versus`, `which is better`, `pros and cons` | "Difference between fragment timeout and request timeout?" |
| 6 | `BEST_PRACTICE` | `best practice`, `best way`, `recommended`, `should i`, `is it good to`, `proper way` | "What's the best way to set timeout parameters?" |
| 7 (default) | `HOW_TO` | Any question that doesn't match above patterns | "Configure the EventBuilder for high rate" |

**Design notes**:

- Troubleshooting has highest priority because error-related keywords can co-occur with other patterns ("How do I fix this error?" should route to TROUBLESHOOT, not HOW_TO).
- The default is HOW_TO, which provides the broadest coverage for general questions.
- Classification is case-insensitive (`question.lower()`).
- All keyword matching uses substring containment (`keyword in question_lower`), not word boundary matching.

### QuestionType Enum

```python
class QuestionType(str, Enum):
    HOW_TO = "how_to"
    WHY = "why"
    WHAT_IS = "what_is"
    TROUBLESHOOT = "troubleshoot"
    COMPARE = "compare"
    BEST_PRACTICE = "best_practice"
```

Defined in `srcs/models/question.py`. Inherits from both `str` and `Enum`, making values directly serializable to JSON strings.

---

## 3. Persona Selection

**Constant**: `PanelOrchestrator.PERSONA_SELECTION: dict[QuestionType, list[int]]`

After question classification, the orchestrator selects which personas will participate based on the `PERSONA_SELECTION` mapping. Each entry maps a `QuestionType` to a list of phase numbers.

### Selection Mapping

| QuestionType | Phase Numbers | Personas | Rationale |
|-------------|---------------|----------|-----------|
| `HOW_TO` | `[0, 6, 3]` | Archivist, Synthesizer, Logician | Need code references from the Archivist, step-by-step synthesis from the Synthesizer, and logical structure from the Logician |
| `WHY` | `[1, 3, 2]` | Theorist, Logician, Detective | Need hypothetical explanations from the Theorist, causal reasoning from the Logician, and evidence-based analysis from the Detective |
| `WHAT_IS` | `[0, 6]` | Archivist, Synthesizer | Need definitions and references from the Archivist, clear explanation from the Synthesizer |
| `TROUBLESHOOT` | `[0, 1, 2, 3, 4, 5, 6]` | All 7 main personas | Full investigation perspective -- troubleshooting questions benefit from every persona's expertise |
| `COMPARE` | `[0, 4, 5]` | Archivist, Skeptic, Judge | Need factual references from the Archivist, critical comparison from the Skeptic, and balanced judgment from the Judge |
| `BEST_PRACTICE` | `[0, 5, 6]` | Archivist, Judge, Synthesizer | Need evidence-based references from the Archivist, quality assessment from the Judge, and clear recommendations from the Synthesizer |

**Default**: If a `QuestionType` is not found in the mapping (which should not occur with the current enum), all 7 main personas are selected: `[0, 1, 2, 3, 4, 5, 6]`.

**Notable exclusions**:

- The **Learner** (phase 7) is never included in any panel. It operates only in the investigation pipeline.
- The **Reviewer** (phase 8) is never included. It handles feedback, not questions.
- The **Chronicler** (phase -1) is never included. It handles multi-file log triage, not Q&A.

### Selection Order

The order of phase numbers in each list determines the **contribution order**. Since contributions are gathered sequentially with prior-contribution visibility, earlier personas set the context for later ones. For example, in `TROUBLESHOOT`, the Archivist goes first to establish code references, then the Theorist generates hypotheses based on those references, then the Detective seeks evidence, and so on.

---

## 4. Contribution Gathering

**Step 3 of the workflow**: Contributions are gathered sequentially, not in parallel. Each persona sees all prior contributions when making its own contribution.

### Sequential Contribution Protocol

```python
for persona in personas:
    contribution = await persona.answer_question(context)
    context.add_contribution(contribution)
```

The `QuestionContext.add_contribution()` method appends each contribution to the shared `contributions` list. When the next persona's `answer_question()` is called, it receives the same context object, which now includes all prior contributions.

### Prior Contribution Visibility

Each persona can access prior contributions via `context.get_prior_contributions_summary()`:

```python
def get_prior_contributions_summary(self) -> str:
    """Get a summary of prior contributions for context."""
    if not self.contributions:
        return "No prior contributions yet."

    summaries = []
    for contrib in self.contributions:
        content_preview = str(contrib.content)[:200]
        summaries.append(
            f"- {contrib.persona_id.title()}: {content_preview}"
        )
    return "\n".join(summaries)
```

This means:
- The first persona in the list sees no prior contributions
- The second persona sees the first persona's contribution
- The Nth persona sees all N-1 prior contributions

This design enables personas to build on each other's work, avoid redundancy, and fill gaps identified by earlier contributors.

### Contribution Structure

Each persona's `answer_question()` returns a `Contribution` dataclass:

```python
@dataclass
class Contribution:
    persona_id: str       # e.g., "archivist", "theorist"
    phase: int            # Phase number (0-7)
    content: Any          # Dict with answer, key_points, sources, etc.
    confidence: float     # 0.0-1.0
    reasoning: str        # How the persona arrived at this contribution
```

The `content` field typically contains a dict with keys like `answer`, `key_points`, `sources`, `caveats`, `citations`, and persona-specific fields. The exact content structure varies by persona (see individual persona chapters for details).

### Error Handling

If a persona fails to contribute (raises an exception), the orchestrator catches the exception, logs a warning, and continues with the remaining personas. The failed persona's contribution is simply absent from the context.

```python
try:
    contribution = await persona.answer_question(context)
    context.add_contribution(contribution)
except Exception as e:
    logger.warning(
        f"Persona {persona.metadata.name} failed to contribute: {e}"
    )
```

The callback (if provided) receives a `contribution_error` event for failed contributions.

---

## 5. Voting & Consensus

**Step 4 of the workflow**: After all contributions are gathered, the orchestrator runs a voting round where each persona endorses or critiques every other persona's contribution.

### Voting Protocol

```python
async def _voting_round(
    self,
    context: QuestionContext,
    personas: list[BasePersona],
) -> dict[str, VotingResult]:
```

For each contribution, every other persona (excluding the contributor) either:
- **Endorses** the contribution (`persona.endorse(contribution) -> True`)
- **Critiques** the contribution (`persona.critique(contribution) -> Critique`)

A persona that does not endorse automatically triggers a critique call.

### Consensus Score Calculation

```python
consensus_score = endorsements / (len(personas) - 1)
```

The consensus score for each contribution is the ratio of endorsements to the number of other personas. For example, if a panel has 7 personas and a contribution receives 5 endorsements, its consensus score is `5 / 6 = 0.833`.

### Consensus Threshold

```python
CONSENSUS_THRESHOLD = 0.7
```

If **any** contribution's consensus score falls below 0.7, the orchestrator triggers deliberation. The threshold is checked against the minimum consensus score across all contributions:

```python
min_consensus = min(
    (v.consensus_score for v in voting_results.values()),
    default=1.0,
)
if min_consensus < self.CONSENSUS_THRESHOLD and len(context.contributions) > 1:
    # Trigger deliberation
```

The `len(context.contributions) > 1` guard prevents deliberation when there is only a single contribution (since there is nothing to disagree about).

### VotingResult

```python
@dataclass
class VotingResult:
    endorsements: int
    critiques: list[Critique] = field(default_factory=list)
    consensus_score: float = 0.0
```

One `VotingResult` is produced per contribution, keyed by `persona_id` in the results dict. The voting results are stored in `context.voting_results` for use by the synthesis step.

### Endorse/Critique Methods

Each persona implements `endorse()` and `critique()` from the `BasePersona` abstract class:

**Endorsement**: Returns `True` if the persona agrees with the contribution's approach and conclusions. Endorsement criteria vary by persona -- for example, the Skeptic has stricter endorsement criteria than the Archivist.

**Critique**: Returns a `Critique` dataclass when the persona does not endorse:

```python
@dataclass
class Critique:
    target_contribution: Contribution
    issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    severity: str = "MEDIUM"     # HIGH, MEDIUM, LOW
    recommendations: list[str] = field(default_factory=list)
```

### Voting Error Handling

If a persona fails to endorse or critique (raises an exception), the vote is skipped for that persona-contribution pair. This means the consensus score may be calculated from fewer votes than expected, but the voting round still completes.

---

## 6. Deliberation

**Step 5 of the workflow**: Triggered when the minimum consensus score is below `CONSENSUS_THRESHOLD` (0.7). Deliberation gives personas an opportunity to discuss disagreements and potentially revise their positions.

### Deliberation Constants

```python
MAX_DELIBERATION_ROUNDS = 2
```

### Deliberation Protocol

```python
async def _deliberation_rounds(
    self,
    context: QuestionContext,
    personas: list[BasePersona],
    max_rounds: int | None = None,
) -> list[Discussion]:
```

Each deliberation round:

1. **Identify disagreements**: `_identify_disagreements(context)` examines voting results to find contributions with consensus below the threshold. It extracts the specific issues from critiques and formulates them as discussion topics.

2. **Limit scope**: At most 3 disagreement topics are addressed per round (to prevent unbounded discussion).

3. **Facilitate discussion**: For each topic, a `Discussion` record is created. Each persona receives the topic and responds via `respond_to()`:

```python
response = await persona.respond_to(
    personas[0],  # Use first persona as facilitator
    f"Consider this issue: {topic}. "
    f"How does this affect your contribution?",
)
discussion.add_exchange(persona.metadata.name.lower(), response)
```

4. **Record discussion**: The `Discussion` is appended to `context.discussions`.

5. **Re-vote**: After all deliberation rounds complete, a new voting round is run. If consensus improves above the threshold, deliberation stops. If not, the orchestrator proceeds to synthesis with the best available consensus.

### Disagreement Identification

```python
def _identify_disagreements(self, context: QuestionContext) -> list[str]:
```

This method scans `context.voting_results` for contributions with `consensus_score < CONSENSUS_THRESHOLD`. For each such contribution, it extracts the `issues` from each `Critique` and formats them as topic strings:

```
"{persona_id}'s contribution: {issue_text}"
```

At most 3 disagreement topics are returned (the first 3 unique issues found).

### Discussion Dataclass

```python
@dataclass
class Discussion:
    topic: str
    participants: list[str] = field(default_factory=list)
    exchanges: list[tuple[str, str]] = field(default_factory=list)
    conclusion: str | None = None
    consensus_reached: bool = False

    def add_exchange(self, persona_id: str, message: str) -> None:
        self.exchanges.append((persona_id, message))
```

The `Discussion` tracks:
- The topic being discussed
- Which personas participated
- The full exchange history (persona_id, message pairs)
- Whether a conclusion was reached
- Whether consensus was achieved

### Resolution

If deliberation fails to achieve consensus after `MAX_DELIBERATION_ROUNDS`, the `CoordinatorPersona` can render a resolution decision via `escalate_disagreement()`:

```python
@dataclass
class Resolution:
    disagreement_summary: str
    resolution_type: str           # "consensus", "majority", "coordinator_decision"
    resolution: str
    dissenting_views: list[str] = field(default_factory=list)
```

In the current implementation, unresolved disagreements are carried forward to synthesis as `dissenting_views` rather than being forcibly resolved.

---

## 7. Synthesis

**Step 6 of the workflow**: After voting (and optional deliberation), the orchestrator synthesizes all contributions into a single `PanelResponse`.

### Synthesis Method

```python
def _synthesize_response(
    self,
    context: QuestionContext,
    voting_results: dict[str, VotingResult],
) -> PanelResponse:
```

### Score-Weighted Contribution Ranking

Each contribution is scored by combining its consensus score with its persona confidence:

```python
combined_score = vote_result.consensus_score * contribution.confidence
```

Contributions are sorted by combined score in descending order. The highest-scored contributions have the most influence on the final answer.

### Answer Assembly

The synthesis extracts content from each contribution (ordered by combined score) and aggregates:

| Field | Source | Aggregation |
|-------|--------|-------------|
| `answer` | `content["answer"]`, `content["response"]`, or `content["analysis"]` | Joined with `\n\n` |
| `key_points` | `content["key_points"]` | Merged, deduplicated, limited to 10 |
| `sources` | `content["sources"]` | Merged, deduplicated |
| `caveats` | `content["caveats"]` | Merged, deduplicated |
| `dissenting_views` | Contributions with consensus < 0.7 | `"{PersonaName}: {reasoning}"` |
| `contributions_summary` | All contributions | `{PersonaName: reasoning}` dict |
| `citations` | `content["citations"]` | Aggregated, deduplicated, sorted by relevance, limited to 10 |

If `content` is a string rather than a dict, it is used directly as an answer part.

If no answer parts are extracted, the synthesis falls back to using the reasoning from the highest-scored contribution. If there are no contributions at all, the answer defaults to: `"Unable to formulate an answer with the available information."`

### Confidence Calculation

Overall confidence is a weighted average of persona confidences, where the weight is the combined score:

```python
weighted_confidence = sum(
    score * contrib.confidence
    for score, contrib in scored_contributions
) / total_weight
```

If `total_weight` is zero, the confidence defaults to 0.5. If there are no contributions at all, it defaults to 0.3.

### Citation Aggregation

```python
def _aggregate_citations(
    self,
    citations: list[SourceCitation],
) -> list[SourceCitation]:
```

Citations are deduplicated by `(type, reference)` tuple. When duplicates exist, the citation with the higher `relevance` score is kept. The final list is sorted by relevance (descending) and limited to the top 10 citations.

Citations are extracted from contribution content. Both `SourceCitation` dataclass instances and raw dicts are accepted and normalized.

### PanelResponse Construction

The final response is constructed via the `PanelResponse.from_citations()` class method, which converts `SourceCitation` objects to serializable dicts:

```python
return PanelResponse.from_citations(
    question_id=context.question_id,
    answer=answer,
    confidence=weighted_confidence,
    citations=unique_citations,
    key_points=key_points,
    sources=sources,
    caveats=caveats,
    dissenting_views=dissenting_views,
    contributions_summary=contributions_summary,
)
```

---

## 8. CoordinatorPersona

**Class**: `CoordinatorPersona` in `srcs/persona/coordinator.py`

The `CoordinatorPersona` is a special persona that manages the investigation process. Unlike phase-specific personas, it operates across all phases and has authority over panel management, discussion facilitation, and disagreement resolution.

### Identity

| Property | Value |
|----------|-------|
| Phase | -1 (special -- not a standard phase) |
| Name | Coordinator |
| Role | Panel Orchestration |
| Color | `bold white` |
| Thinking Phrase | `"Orchestrating the panel..."` |
| Uses LLM | No |

**Traits**: diplomatic, organized, decisive, impartial, synthesizing

**Thinking Style**: Systematic orchestration -- manages flow, facilitates collaboration, synthesizes diverse perspectives, and ensures thorough investigation.

Note: The `CoordinatorPersona` creates a synthetic `Persona` instance in its `metadata` property (rather than referencing the `PERSONAS` registry) because it uses phase -1 which is shared with the Chronicler in the registry.

### Panel Management Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `assemble_panel` | `(phases: list[int]) -> list[BasePersona]` | Instantiate persona objects for specified phases |
| `request_contribution` | `(persona, context) -> Contribution` | Prepare and get contribution from a specific persona |
| `synthesize_contributions` | `(contributions) -> Summary` | Produce key points, areas of agreement/disagreement |
| `facilitate_discussion` | `(topic, participants?) -> Discussion` | Open and moderate a discussion on a topic |
| `escalate_disagreement` | `(personas, topic) -> Resolution` | Resolve a disagreement, rendering a coordinator decision if needed |

### Flow Control Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `determine_next_phase` | `(context) -> int` | Identify which phase should execute next (standard order 0-7) |
| `should_reconvene` | `(context) -> bool` | Whether the panel should reconvene (low confidence in critical phases) |

### Summary Dataclass

The `synthesize_contributions()` method produces a `Summary`:

```python
@dataclass
class Summary:
    key_points: list[str] = field(default_factory=list)
    areas_of_agreement: list[str] = field(default_factory=list)
    areas_of_disagreement: list[str] = field(default_factory=list)
    overall_assessment: str = ""
```

Agreement is detected when multiple personas have high confidence (> 0.7). Disagreement is detected when any persona has low confidence (< 0.4).

### Relationship to PanelOrchestrator

The `CoordinatorPersona` and `PanelOrchestrator` serve complementary but distinct roles:

| Aspect | PanelOrchestrator | CoordinatorPersona |
|--------|-------------------|--------------------|
| Nature | Orchestration engine | Persona instance |
| Implements | Workflow logic (classify, select, vote, deliberate, synthesize) | Panel management methods (assemble, facilitate, escalate) |
| Used in | `ask_experts` API tool | Available for investigation pipeline and Q&A |
| Instantiation | Created per API request | Can be instantiated by the orchestrator or coordinator pipeline |
| State | Caches persona instances | Maintains current panel reference |

Currently, the `PanelOrchestrator` handles the full Q&A workflow directly without delegating to `CoordinatorPersona`. The `CoordinatorPersona` exists as infrastructure for more sophisticated panel management patterns, such as multi-round investigations where the coordinator decides which phases to re-run based on evidence quality.

---

## 9. SSE Events for ask_experts

When the `ask_experts` tool is called with `stream: true`, the `PanelOrchestrator` emits SSE events through the callback mechanism. The callback maps `QAEvent` dicts to SSE event frames.

### Event Sequence

```
classification
    │
    ▼
persona_selection
    │
    ▼
contribution_start ──► contribution_complete    (repeated per persona)
    │                       │
    ▼                       ▼
    └───────────────────────┘
    │
    ▼
voting_complete
    │
    ├── consensus >= 0.7 ──────────────────────► synthesis_complete
    │
    └── consensus < 0.7 ──► deliberation_start
                                │
                                ▼
                            deliberation_complete
                                │
                                ▼
                            (re-vote implicit)
                                │
                                ▼
                            synthesis_complete
```

### Event Reference

| Event Type | Payload Schema | When Emitted |
|-----------|---------------|--------------|
| `classification` | `{event: "classification", question_type: "troubleshoot"}` | After `_classify_question()` determines the question type |
| `panel_selected` | `{event: "panel_selected", personas: ["Archivist", "Theorist", ...]}` | After persona selection from `PERSONA_SELECTION` mapping |
| `contribution_start` | `{event: "contribution_start", persona: "Archivist"}` | Before each persona's `answer_question()` is called |
| `contribution_complete` | `{event: "contribution_complete", persona: "Archivist", confidence: 0.8}` | After a persona successfully contributes |
| `contribution_error` | `{event: "contribution_error", persona: "Theorist", error: "..."}` | When a persona fails to contribute (exception caught) |
| `voting_complete` | `{event: "voting_complete", results: {persona_id: {score: 0.85, endorsements: 5}}}` | After the voting round completes |
| `deliberation_start` | `{event: "deliberation_start"}` | When consensus is below threshold and deliberation begins |
| `deliberation_complete` | `{event: "deliberation_complete", new_consensus: 0.82}` | After deliberation rounds and re-voting complete |
| `synthesis_complete` | `{event: "synthesis_complete", confidence: 0.85}` | After the final `PanelResponse` is synthesized |

### SSE Frame Format

Events are emitted as standard SSE frames through the API layer:

```
event: classification
data: {"question_type": "troubleshoot"}

event: panel_selected
data: {"personas": ["Archivist", "Theorist", "Detective", "Logician", "Skeptic", "Judge", "Synthesizer"]}

event: contribution_complete
data: {"persona": "Archivist", "confidence": 0.8}

event: voting_complete
data: {"results": {"archivist": {"score": 0.85, "endorsements": 5}, "theorist": {"score": 0.72, "endorsements": 4}}}

event: synthesis_complete
data: {"confidence": 0.85}
```

The `complete` event (final event) contains the full `PanelResponse` JSON, which is the same payload returned in non-streaming mode.

### Error Events

If the orchestrator encounters an unrecoverable error, an `error` event is emitted:

```
event: error
data: {"code": "panel_error", "message": "Panel orchestration failed during contribution phase"}
```

Individual persona failures during contribution are reported as `contribution_error` events and do not halt the panel -- the orchestrator continues with remaining personas.

---

## 10. Q&A Data Models

All Q&A data models are defined in `srcs/models/question.py`. This section provides the complete field-level reference for each model.

### QuestionType

```python
class QuestionType(str, Enum):
    """Types of questions the panel can answer."""

    HOW_TO = "how_to"           # "How do I configure X?"
    WHY = "why"                 # "Why does X happen?"
    WHAT_IS = "what_is"         # "What is X?"
    TROUBLESHOOT = "troubleshoot" # "I'm seeing error X"
    COMPARE = "compare"         # "Difference between X and Y?"
    BEST_PRACTICE = "best_practice" # "What's the best way to do X?"
```

Inherits from `str` for direct JSON serialization. Used by `_classify_question()` to route questions to the appropriate persona panel.

### QuestionContext

```python
@dataclass
class QuestionContext:
    """Context shared across personas during Q&A."""
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `question` | `str` | (required) | The question being answered |
| `question_type` | `QuestionType` | (required) | Classified type of question |
| `question_id` | `str` | `generate_id()` | Auto-generated unique identifier (8-char UUID prefix) |
| `related_logs` | `list[Log]` | `[]` | Optional log entries related to the question |
| `contributions` | `list[Contribution]` | `[]` | All contributions made so far by all personas |
| `discussions` | `list[Discussion]` | `[]` | Discussion records from deliberation rounds |
| `voting_results` | `dict[str, VotingResult]` | `{}` | Results of voting rounds, keyed by persona ID |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_contributions_by_persona` | `(persona_id: str) -> list[Contribution]` | Filter contributions by persona ID |
| `add_contribution` | `(contribution: Contribution) -> None` | Append a contribution to the list |
| `get_prior_contributions_summary` | `() -> str` | Formatted summary of all prior contributions (first 200 chars each) |

### PanelResponse

```python
class PanelResponse(BaseModel):
    """Final response from the panel of experts."""
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `question_id` | `str` | (required) | -- | ID linking to the original question |
| `answer` | `str` | (required) | -- | The synthesized answer text |
| `confidence` | `float` | `0.5` | `ge=0.0, le=1.0` | Overall confidence in the answer |
| `key_points` | `list[str]` | `[]` | -- | Main points extracted from contributions |
| `sources` | `list[str]` | `[]` | -- | Sources consulted (file paths, URLs) |
| `caveats` | `list[str]` | `[]` | -- | Important caveats or limitations |
| `dissenting_views` | `list[str]` | `[]` | -- | Alternative perspectives not adopted |
| `contributions_summary` | `dict[str, str]` | `{}` | -- | Summary of each persona's contribution (`{PersonaName: reasoning}`) |
| `citations` | `list[dict[str, Any]]` | `[]` | -- | Source citations as serialized dicts |

**Class method**:

```python
@classmethod
def from_citations(
    cls,
    question_id: str,
    answer: str,
    confidence: float,
    citations: list[SourceCitation],
    **kwargs: Any,
) -> PanelResponse:
```

Converts `SourceCitation` dataclass instances to dicts for Pydantic serialization. Each citation dict has keys: `type`, `reference`, `excerpt`, `relevance`, `line_range`.

### VotingResult

```python
@dataclass
class VotingResult:
    """Result of voting round for a contribution."""
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `endorsements` | `int` | (required) | Number of personas endorsing this contribution |
| `critiques` | `list[Critique]` | `[]` | Critiques from non-endorsing personas |
| `consensus_score` | `float` | `0.0` | Agreement ratio: `endorsements / (total_personas - 1)` |

### SourceCitation

```python
@dataclass
class SourceCitation:
    """A citation to source code or documentation."""
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | (required) | Citation type: `"code"`, `"documentation"`, `"pattern"`, `"prior_qa"` |
| `reference` | `str` | (required) | File path, URL, or pattern ID |
| `excerpt` | `str` | (required) | Relevant snippet or summary |
| `relevance` | `float` | `0.0` | Relevance score (0.0 to 1.0) |
| `line_range` | `tuple[int, int] \| None` | `None` | For code citations: (start_line, end_line) |

### QuestionRequest

```python
class QuestionRequest(BaseModel):
    """API request model for asking a question."""
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `question` | `str` | (required) | `min_length=1` | The question to ask the panel |
| `related_logs` | `list[dict[str, Any]]` | `[]` | -- | Optional related log entries as dicts |

### QuestionResponse

```python
class QuestionResponse(BaseModel):
    """API response model for a panel answer."""
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `question` | `str` | (required) | The original question text |
| `question_type` | `str` | (required) | Classified question type (e.g., `"troubleshoot"`) |
| `response` | `PanelResponse` | (required) | The panel's synthesized response |

### QAFeedbackRequest

```python
class QAFeedbackRequest(BaseModel):
    """Request model for Q&A feedback."""
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `qa_id` | `str` | (required) | -- | Q&A session ID (matches `question_id`) |
| `helpful` | `bool` | (required) | -- | Whether the answer was helpful |
| `feedback_text` | `str \| None` | `None` | -- | Optional free-text feedback |

### Supporting Dataclasses (from `srcs/persona/base.py`)

These dataclasses are used by the panel system but defined in the base persona module:

**Contribution**:

| Field | Type | Description |
|-------|------|-------------|
| `persona_id` | `str` | Identifier of the contributing persona (e.g., `"theorist"`) |
| `phase` | `int` | Phase number when this contribution was made |
| `content` | `Any` | The actual contribution content (type varies by persona) |
| `confidence` | `float` | Persona's confidence in this contribution (0.0-1.0) |
| `reasoning` | `str` | Explanation of how the persona arrived at this contribution |

**Critique**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `target_contribution` | `Contribution` | (required) | The contribution being critiqued |
| `issues` | `list[str]` | `[]` | Identified problems or weaknesses |
| `strengths` | `list[str]` | `[]` | Acknowledged strengths |
| `severity` | `str` | `"MEDIUM"` | Overall severity: `HIGH`, `MEDIUM`, `LOW` |
| `recommendations` | `list[str]` | `[]` | Suggested improvements |

**Discussion**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `topic` | `str` | (required) | The topic being discussed |
| `participants` | `list[str]` | `[]` | Persona IDs involved |
| `exchanges` | `list[tuple[str, str]]` | `[]` | `(persona_id, message)` pairs |
| `conclusion` | `str \| None` | `None` | Final conclusion, if reached |
| `consensus_reached` | `bool` | `False` | Whether participants agreed |

**Resolution**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `disagreement_summary` | `str` | (required) | What was disagreed upon |
| `resolution_type` | `str` | (required) | `"consensus"`, `"majority"`, or `"coordinator_decision"` |
| `resolution` | `str` | (required) | The actual resolution text |
| `dissenting_views` | `list[str]` | `[]` | Views that were not adopted |

**Summary**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key_points` | `list[str]` | `[]` | Main points from contributions |
| `areas_of_agreement` | `list[str]` | `[]` | Where personas agree |
| `areas_of_disagreement` | `list[str]` | `[]` | Where personas disagree |
| `overall_assessment` | `str` | `""` | Coordinator's overall assessment |

### Model Relationship Diagram

```
QuestionRequest
    │
    ▼
PanelOrchestrator.answer()
    │
    ├── creates ──► QuestionContext
    │                   │
    │                   ├── accumulates ──► Contribution (per persona)
    │                   │
    │                   ├── records ──► Discussion (during deliberation)
    │                   │
    │                   └── stores ──► VotingResult (per contribution)
    │
    └── produces ──► PanelResponse
                         │
                         ├── contains ──► SourceCitation[] (as dicts)
                         │
                         └── wrapped by ──► QuestionResponse (API layer)

QAFeedbackRequest ──► PatternLearner.apply_feedback()
```

---

## Panel Example: Troubleshoot Question

To illustrate the full workflow, here is a traced example of a troubleshoot question flowing through the panel:

**Input**: `"What causes fragment timeouts in BoardReaders and how do I diagnose them?"`

**Step 1 -- Classification**: `_classify_question()` detects `"timeout"` keyword, returns `QuestionType.TROUBLESHOOT`.

**Step 2 -- Persona Selection**: `PERSONA_SELECTION[TROUBLESHOOT]` = `[0, 1, 2, 3, 4, 5, 6]` (all 7 main personas).

**Step 3 -- Contributions** (sequential):

| Order | Persona | Key Content |
|-------|---------|-------------|
| 1 | Archivist | Locates `BoardReaderCore.cc`, `Globals.cc` source code references for timeout handling |
| 2 | Theorist | Proposes 3 hypothetical causes (hardware link failure, firmware hang, config mismatch) |
| 3 | Detective | Identifies diagnostic evidence patterns and timeline analysis approach |
| 4 | Logician | Validates causal chain: FE silence -> BoardReader timeout -> EventBuilder stall |
| 5 | Skeptic | Challenges hardware-first assumption, raises network congestion alternative |
| 6 | Judge | Assesses evidence quality, confirms hardware failure as most common cause |
| 7 | Synthesizer | Combines all perspectives into unified diagnostic guide |

**Step 4 -- Voting**: Each persona endorses/critiques the others. The Archivist receives 6/6 endorsements (score 1.0). The Skeptic receives 4/6 endorsements (score 0.67 -- below threshold).

**Step 5 -- Deliberation**: Triggered because Skeptic consensus < 0.7. Round 1 focuses on "whether hardware or configuration is more likely." After discussion, re-vote yields Skeptic score of 0.83.

**Step 6 -- Synthesis**: Contributions weighted by `consensus_score * confidence`. Archivist and Synthesizer rank highest. Answer assembled from all 7 contributions. Skeptic's network congestion concern included as dissenting view. Overall confidence: 0.85.

**Output**: `PanelResponse` with structured answer, 3 key points, 2 code sources, 1 caveat, 1 dissenting view, 7 contribution summaries, and 2 code citations.

---

> [← Learning Personas](agentic-persona-library-ch4-learning-personas.md) | [Table of Contents](agentic-persona-library.md) | [Next: Prompt Architecture →](agentic-persona-library-ch6-prompt-architecture.md)
