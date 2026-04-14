> **Agentic Persona Library** | [← Pipeline Personas](agentic-persona-library-ch2-pipeline-personas.md) | [Table of Contents](agentic-persona-library.md) | [Next: Learning Personas →](agentic-persona-library-ch4-learning-personas.md)

---

# Chapter 3: Analysis Personas -- Reasoning

Phases 0 through 2 produce raw material: prior knowledge, hypotheses, and evidence. Phases 3 through 6 are where the investigation converts that raw material into conclusions. The four personas covered in this chapter -- the Logician, the Skeptic, the Judge, and the Synthesizer -- form the analytical spine of the investigation pipeline. They operate in strict sequence, each consuming the output of its predecessor and producing progressively more refined assessments.

These personas are reasoning-intensive. Where upstream personas interact heavily with external data sources (knowledge base queries, code index lookups, LLM-driven evidence plans), the analysis personas work primarily with the artifacts already collected, applying logical rigor, adversarial skepticism, judicial evaluation, and integrative synthesis to reach a defensible conclusion.

The data flow through the analysis personas follows a convergence pattern:

```
Evidence + Hypotheses (from Detective)
  |
  v
Logician ──► Causal Chains
  |            (step-by-step reasoning with evidence)
  v
Skeptic ──► Challenges
  |                    (weaknesses, alternatives)
  v
Judge ──► Outcome Determination
  |         (CONFIDENT, PROBABLE, UNCERTAIN,
  |          CONTRADICTORY, INSUFFICIENT)
  v
Synthesizer ──► InvestigationResult
                  (executive summary, root cause,
                   recommendations, confidence)
```

Each persona reads from the WorkBinder and writes back to it. The binder serves as the single source of truth for all investigation artifacts, ensuring that every persona operates on the same consistent view of the investigation state. LLM calls are recorded as request/response artifact pairs in the binder for full traceability.

The analysis personas also participate in the expert panel Q&A system (see [Chapter 5: Pipeline, Expert & Admin Tools](agentic-rest-service-design-ch5-pipeline-admin-tools.md), Tool 19: `ask_experts`). In Q&A mode, each persona contributes its specialized perspective: the Logician validates causal reasoning, the Skeptic challenges assumptions, the Judge assesses evidence quality, and the Synthesizer merges all contributions into a unified answer.

---

## Logician (Phase 3)

### 1. Identity

| Attribute | Value |
|-----------|-------|
| **Phase** | 3 |
| **Name** | Logician |
| **Role** | Causal Chain Construction |
| **Color** | `green` |
| **Thinking Phrase** | "Following the chain of events..." |
| **Prompt Key** | `logician` |
| **Uses LLM** | Yes |
| **Description** | Builds explicit causal chains from evidence |

**Traits**: rigorous, systematic, causal, precise, mechanism-focused

**Thinking Style**: Causal reasoning -- builds explicit cause-effect chains, requires mechanisms for each step, identifies assumptions, verifies temporal ordering.

The Logician occupies the critical transition point in the pipeline where hypotheses and evidence are first organized into structured reasoning. Without this persona, the investigation would have a collection of hypotheses ranked by score and a bag of evidence items, but no explicit articulation of *how* the hypothesized root cause leads to the observed error through a chain of mechanistic steps.

### 2. Responsibilities

**Pipeline role**: Builds explicit causal chains connecting hypothesized root causes to the observed error through mechanistic steps. For each top-scoring hypothesis (up to `max_chains`, filtered by `min_chain_score`), the Logician constructs a `CausalChain` where every step has a claim, a mechanism, and ideally supporting evidence references. Steps without evidence are marked as assumptions. After construction, the Logician verifies evidence references against actual evidence items, links additional code-based evidence via pattern matching, and calculates quality scores (logical validity, evidence coverage).

**Expert panel role**: Validates causal reasoning in Q&A answers. For WHY and TROUBLESHOOT questions, the Logician builds step-by-step causal explanations and identifies assumptions in the reasoning.

**Artifacts produced**:

| Artifact | Type | Description |
|----------|------|-------------|
| Causal chains | `list[CausalChain]` | Each with `hypothesis_id`, `steps`, `logical_validity`, `evidence_coverage`, `gaps`, `assumptions` |
| Contribution content | `dict` | Keys: `chains_built`, `average_validity`, `average_coverage`, `total_steps`, `assumptions_made`, `gaps_identified`, `chain_details` |

**Artifacts consumed**:

| Artifact | Source | Description |
|----------|--------|-------------|
| Hypotheses | Theorist (Phase 1) via binder | `HypothesisArtifact` list, sorted by score, filtered by `min_chain_score` |
| Evidence | Detective (Phase 2) via binder | `EvidenceArtifact` list, converted to `Evidence` model |

### 3. Tool Mapping

| API Tool | Invokes Logician? | Capabilities Used |
|----------|-------------------|-------------------|
| `investigate` | Yes (Phase 3) | Full chain construction |
| `investigate_stream` | Yes (Phase 3) | Full construction + SSE progress |
| `ask_experts` | Yes (for WHY, TROUBLESHOOT questions) | Causal reasoning validation |

See [Chapter 5: Pipeline, Expert & Admin Tools](agentic-rest-service-design-ch5-pipeline-admin-tools.md) for the full API specification of these tools.

### 4. Implementation

**Class**: `LogicianPersona` in `srcs/persona/logician.py`

**Inheritance**: Extends `BasePersona` (from `srcs/persona/base.py`)

**Instance state**:

```python
class LogicianPersona(BasePersona):
    def __init__(self) -> None:
        self._llm: LLMProvider | None = None
        self._max_hypotheses: int = 3
        self._min_score: float = 0.2
        self._built_chains: list[CausalChain] = []
        self._documentation_context: str = ""
```

**Key methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `prepare` | `async (context: InvestigationContext) -> None` | Stores LLM reference, loads `max_chains` and `min_chain_score` from `context.config` |
| `contribute` | `async (context: InvestigationContext) -> Contribution` | Calls `_build_chains`, stores chains in `_built_chains`, builds content dict and confidence |
| `_build_chains` | `async (context: InvestigationContext) -> list[CausalChain]` | Delegates to `_build_all` with binder, max_hypotheses, min_score |
| `_build_all` | `async (binder, max_hypotheses, min_score) -> list[CausalChain]` | Reads hypotheses and evidence from binder, sorts by score, filters by min_score, builds chain per hypothesis via `_build` |
| `_build` | `async (hypothesis, evidence, binder) -> CausalChain` | Constructs chain via LLM (`_construct`), verifies evidence references (`_verify`), calculates scores (`_calculate_scores`), writes chain to binder via `binder.add_causal_chain()` |
| `_construct` | `async (hypothesis, evidence) -> CausalChain` | Calls LLM with `CAUSAL_CHAIN_WITH_EVIDENCE` prompt template, parses `ChainResponse` structured output, creates `CausalStep` objects; falls back to `_create_fallback_chain` on failure |
| `_verify` | `(chain, evidence) -> CausalChain` | Validates evidence_ids against actual evidence items, removes invalid references, marks unsupported steps as assumptions, links additional code evidence via `_link_evidence_to_step` |
| `_calculate_scores` | `(chain) -> CausalChain` | Sets `logical_validity` (proportion of steps with mechanisms), `evidence_coverage` (proportion of non-assumption steps), collects `gaps` and `assumptions` |
| `_link_evidence_to_step` | `(step, evidence) -> list[str]` | Pattern-matches step claims and mechanisms against code evidence content (null/pointer, exception, timeout, config, function name patterns) |
| `reflect` | `async (context) -> Reflection` | Analyzes chain quality: validity, coverage, assumption ratios, strong evidence linkage |
| `critique` | `async (contribution) -> Critique` | Evaluates contributions for causal reasoning quality, identifies missing mechanisms |
| `endorse` | `async (contribution) -> bool` | Endorses contributions with causal language ("because", "causes", "leads to") or confidence > 0.7 |
| `answer_question` | `async (context: QuestionContext) -> Contribution` | Builds logical analysis with causal_analysis, logical_steps, assumptions based on question type |

**Chain construction data flow**:

```
_build_all()
  |-- Read hypotheses from binder (sorted by score, top N)
  |-- Read evidence from binder (convert to Evidence model)
  |-- For each hypothesis above min_score:
  |     |-- _build(hypothesis, evidence, binder)
  |           |-- _construct(hypothesis, evidence)
  |           |     |-- Format CAUSAL_CHAIN_WITH_EVIDENCE prompt
  |           |     |-- LLM.generate_structured(prompt, ChainResponse)
  |           |     |-- Map ChainStepItem -> CausalStep
  |           |     |-- On failure: _create_fallback_chain()
  |           |-- _verify(chain, evidence)
  |           |     |-- Validate evidence_ids exist and are found
  |           |     |-- _link_evidence_to_step() for code evidence
  |           |     |-- Mark unsupported steps as assumptions
  |           |-- _calculate_scores(chain)
  |           |-- binder.add_causal_chain()
  |-- Return list[CausalChain]
```

**Confidence calculation**:

```python
score = (avg_validity * 0.6) + (avg_coverage * 0.4)
if len(chains) >= 3: score += 0.1
elif len(chains) >= 2: score += 0.05
return min(0.9, max(0.2, score))
```

### 5. Prompt Anatomy

**System prompt**: `srcs/prompts/templates/system/logician.md`

Loaded via `get_system_prompt(SystemPromptType.LOGICIAN)`. Defines the Logician's identity, role, and structured output format for causal chain construction.

**User prompts**:

| Template | File | Placeholders | When Used |
|----------|------|-------------|-----------|
| `CAUSAL_CHAIN_WITH_EVIDENCE` | `srcs/prompts/templates/user/causal_chain_with_evidence.md` | `hypothesis`, `evidence_list` | Primary: when evidence is available |
| `CAUSAL_CHAIN` | `srcs/prompts/templates/user/causal_chain.md` | `hypothesis`, `evidence` | Fallback: when no evidence items |

The `evidence_list` placeholder is formatted by `_format_evidence_list()`, which produces a line per evidence item:

```
- ev-001 [STRONG]: code - Fragment timeout check in getNext_() at line 482...
- ev-002 [MODERATE]: log - BoardReader_01 timeout after 5000ms on link 0x0100...
```

**Q&A variant**: `srcs/prompts/templates/system/qa/qa_logician.md` (loaded via `SystemPromptType.QA_LOGICIAN`)

**Structured output model**: `ChainResponse` from `srcs/workbinder/artifacts/parsers/causal_chain.py`

```python
class ChainStepItem(BaseModel):
    claim: str
    mechanism: str = ""
    evidence: List[str] = []
    is_assumption: bool = False

class ChainResponse(BaseModel):
    steps: List[ChainStepItem]
```

### 6. Session State Interaction

**Reads from binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Hypotheses | `binder.get_hypotheses()` | Source for chain construction, filtered by score |
| Evidence items | `binder.get_evidence_items()` | Evidence to reference in chain steps |

**Writes to binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Causal chains | `binder.add_causal_chain()` | Stores each chain with hypothesis_id, steps, scores |
| LLM exchanges | `binder.record_llm_request()` / `binder.record_llm_response()` | Full traceability of LLM calls (via `_call_llm_structured` in BasePersona) |
| Contribution | Via coordinator | Stored in context.contributions |

**Binder artifact structure** (per chain):

```python
binder.add_causal_chain(
    hypothesis_id=hypothesis.binder_artifact_id,  # Links to HypothesisArtifact
    steps=[{
        "step_order": int,
        "claim": str,
        "mechanism": str,
        "evidence_ids": list[str],
        "is_assumption": bool,
        "assumption_note": str | None,
        "evidence_strength": str,
    }],
    created_by="Logician",
    phase=3,
    logical_validity=float,
    evidence_coverage=float,
)
```

### 7. SSE Events

When invoked via `investigate_stream` (see [Chapter 5](agentic-rest-service-design-ch5-pipeline-admin-tools.md), Tool 18), the Logician emits the following SSE events:

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 3, phase_name: "Causal Chain Construction", message: "Building reasoning chains..."}` | Phase begins |
| `llm_request` | `{phase: 3, model_name: "...", system_prompt_length: N, user_prompt_length: N}` | Per-hypothesis chain generation LLM call |
| `llm_response` | `{phase: 3, model_name: "...", response_model: "ChainResponse", parse_failed: bool}` | Chain parsed from LLM response |
| `phase_complete` | `{phase: 3, phase_name: "Causal Chain Construction", data: {chains_built: N}}` | Phase done |

Multiple `llm_request`/`llm_response` pairs may be emitted when chains are built for multiple hypotheses.

### 8. Expert Panel Behavior

**Question types**: WHY, TROUBLESHOOT

**`answer_question(context: QuestionContext) -> Contribution`**:

The Logician contributes to the expert panel by providing logical analysis tailored to the question type:

| Question Type | Response Style | Content Keys |
|---------------|---------------|-------------|
| WHY | Causal chain from root cause to symptom | `causal_analysis`, `answer`, `assumptions` |
| TROUBLESHOOT | Step-by-step diagnostic logic | `logical_steps`, `answer`, `assumptions` |
| HOW_TO | Procedural sequence with verification | `logical_steps`, `answer` |
| General | Principle-based logical analysis | `answer`, `key_points` |

**Q&A prompt variant**: `SystemPromptType.QA_LOGICIAN` (loaded from `srcs/prompts/templates/system/qa/qa_logician.md`)

The Logician's Q&A contributions focus on mechanism explanations: *how* does A lead to B, what are the intermediate steps, and what assumptions does the reasoning depend on.

### 9. Configuration & Tuning

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| `max_chains` | 3 | `context.config.max_chains` | Maximum number of hypotheses to build chains for |
| `min_chain_score` | 0.2 | `context.config.min_chain_score` | Minimum hypothesis score to warrant chain construction |
| LLM temperature | Provider default | LLM config | Temperature for chain generation |

**Tuning guidance**:

- Increasing `max_chains` above 3 provides more coverage but increases LLM call count linearly. The top 3 hypotheses typically capture the most likely root causes.
- Lowering `min_chain_score` below 0.2 may generate chains for very weak hypotheses, adding noise. Raise it to 0.3-0.4 for faster investigations with fewer speculative chains.
- Chain quality depends heavily on evidence quality from Phase 2. If chains consistently have low evidence coverage, the issue is likely insufficient evidence gathering rather than chain construction parameters.

### 10. Error Handling & Fallbacks

| Failure Mode | Detection | Fallback | Impact |
|-------------|-----------|----------|--------|
| LLM unavailable | `self._llm is None` | `_create_fallback_chain()`: minimal 2-step chain (root cause claim + "caused the observed error") | Chains have minimal detail, all steps marked as assumptions |
| LLM call fails | Exception in `generate_structured()` | Same fallback chain; exception logged | Same as above |
| Parse failure | `ChainResponse` validation fails | Caught by `generate_structured` exception handling, falls back to fallback chain | LLM output discarded entirely |
| No hypotheses | `context.hypotheses` empty | Returns empty chain list; logged as warning | Phase produces no chains; downstream phases handle empty input |
| No evidence | `evidence.items` empty | Uses `CAUSAL_CHAIN` prompt (without explicit evidence list); all chain steps become assumptions | Chains built but with low evidence coverage |
| Invalid evidence refs | Evidence ID not found in `evidence.items` | Reference removed from step, step marked as assumption | Chain quality degrades gracefully |
| Hypothesis missing binder_artifact_id | `hypothesis.binder_artifact_id` is None | `ValueError` raised; chain for that hypothesis skipped | Other hypotheses still processed |

**Fallback chain structure**:

```python
CausalChain(
    hypothesis_id=hypothesis.id,
    steps=[
        CausalStep(
            step_order=0,
            claim=f"Root cause: {hypothesis.description[:100]}",
            mechanism="Mechanism requires further investigation",
            evidence_ids=hypothesis.supporting_evidence_ids[:3],
            is_assumption=(len(hypothesis.supporting_evidence_ids) == 0),
        ),
        CausalStep(
            step_order=1,
            claim="This caused the observed error",
            mechanism="Direct causation",
            evidence_ids=[],
            is_assumption=True,
            assumption_note="Causal link assumed pending verification",
        ),
    ],
)
```

### 11. Testing Contract

| Test | Input | Expected Output | Key Assertion |
|------|-------|-----------------|---------------|
| `test_logician_builds_chains` | Valid hypotheses + evidence in context | `list[CausalChain]` with steps | Chains built > 0, each chain has steps |
| `test_logician_respects_max_chains` | 5 hypotheses, `max_chains=2` | Only 2 chains built | `len(chains) <= 2` |
| `test_logician_filters_by_min_score` | Hypotheses with scores [0.1, 0.3, 0.5] and `min_score=0.25` | Chains for 0.3 and 0.5 only | 0.1-scored hypothesis skipped |
| `test_logician_chain_has_steps` | Valid hypothesis and evidence | Each chain has >= 1 `CausalStep` with mechanism | `len(chain.steps) >= 1`, `step.mechanism is not None` |
| `test_logician_llm_fallback` | LLM raises exception | Fallback chain generated | Chain has 2 steps, both assumptions |
| `test_logician_verifies_evidence_refs` | Chain with invalid evidence IDs | Invalid refs removed, steps marked as assumptions | `step.is_assumption is True` for steps with no valid refs |
| `test_logician_links_code_evidence` | Chain step mentioning "timeout", code evidence with "timeout" | Code evidence linked to step | `evidence_id in step.evidence_ids` |
| `test_logician_answer_question` | WHY question context | Contribution with causal analysis | `content["causal_analysis"]` is non-empty |
| `test_logician_endorses_causal_reasoning` | Contribution with "because" in reasoning | `True` | Endorsement granted |
| `test_logician_rejects_non_causal` | Contribution without causal language and low confidence | `False` | Endorsement denied |

**Mock requirements**: `LLMProvider` (for `generate_structured`), `WorkBinder` (for artifact read/write)

---

## Skeptic (Phase 4)

### 1. Identity

| Attribute | Value |
|-----------|-------|
| **Phase** | 4 |
| **Name** | Skeptic |
| **Role** | Adversarial Review |
| **Color** | `red` |
| **Thinking Phrase** | "But wait..." |
| **Prompt Key** | `skeptic` |
| **Uses LLM** | Yes |
| **Description** | Challenges conclusions through critical analysis |

**Traits**: skeptical, challenging, contrarian, thorough, critical

**Thinking Style**: Adversarial analysis -- challenges assumptions, identifies weaknesses, proposes alternative explanations, stress-tests conclusions before acceptance.

The Skeptic is the investigation's quality gate. By deliberately challenging the conclusions of the Logician and the evidence gathered by the Detective, this persona ensures that only well-supported conclusions survive to the Judge. Challenges that can be resolved through existing evidence are marked as resolved; those that cannot are passed through as warnings that calibrate the final confidence score.

### 2. Responsibilities

**Pipeline role**: Challenges conclusions through two complementary mechanisms:

1. **LLM-generated challenges**: Uses the adversarial review prompt to generate creative challenges against the top hypothesis and its causal chain. The LLM identifies logical flaws, alternative explanations, and gaps in the reasoning that structured checks might miss.

2. **Structural challenges**: Programmatically checks for measurable weaknesses -- low evidence coverage, excessive assumptions, low logical validity, and absence of strong evidence. These challenges are always generated regardless of LLM availability.

After generating challenges, the Skeptic attempts to resolve each one using existing evidence and hypothesis scores. HIGH-severity challenges always trigger resolution attempts; MEDIUM-severity challenges also receive resolution attempts.

**Expert panel role**: Provides contrarian perspective on all question types. Challenges assumptions in other personas' contributions, raises alternative explanations, and identifies edge cases.

**Artifacts produced**:

| Artifact | Type | Description |
|----------|------|-------------|
| Challenges | `list[Challenge]` | Each with `challenge_type`, `content`, `severity`, `requires_response`, `resolved`, `resolution` |
| Contribution content | `dict` | Keys: `challenges_raised`, `high_severity`, `medium_severity`, `low_severity`, `challenge_types`, `unresolved`, `resolved`, `challenge_details` |

**Artifacts consumed**:

| Artifact | Source | Description |
|----------|--------|-------------|
| Hypotheses | Theorist via binder | Top hypothesis for challenge targeting |
| Causal chains | Logician via binder | Chain quality for structural checks |
| Evidence | Detective via binder | Evidence for resolution attempts |
| Prior knowledge | Archivist via context | Context for challenge generation |

### 3. Tool Mapping

| API Tool | Invokes Skeptic? | Capabilities Used |
|----------|--------------------------|-------------------|
| `investigate` | Yes (Phase 4) | Full adversarial review |
| `investigate_stream` | Yes (Phase 4) | Full review + SSE progress |
| `ask_experts` | Yes (all question types) | Critical perspective |

The Skeptic is always included in expert panel Q&A regardless of question type, providing an adversarial perspective on every answer.

### 4. Implementation

**Class**: `SkepticPersona` in `srcs/persona/skeptic.py`

**Inheritance**: Extends `BasePersona`

**Instance state**:

```python
class SkepticPersona(BasePersona):
    def __init__(self) -> None:
        self._llm: LLMProvider | None = None
        self._generated_challenges: list[Challenge] = []
        self._documentation_context: str = ""
```

**Key methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `prepare` | `async (context) -> None` | Stores LLM reference |
| `contribute` | `async (context) -> Contribution` | Calls `_conduct_review`, stores challenges, builds content dict |
| `_conduct_review` | `async (context) -> list[Challenge]` | Delegates to `_review_from_binder` |
| `_review_from_binder` | `async (binder) -> list[Challenge]` | Reads top hypothesis, chain, and evidence from binder; calls `_review` |
| `_review` | `async (hypothesis, chain, evidence, prior, binder) -> list[Challenge]` | Generates LLM challenges + structural challenges, attempts resolutions, writes all challenges to binder |
| `_generate_challenges` | `async (hypothesis, chain, evidence) -> list[Challenge]` | Calls LLM with `ADVERSARIAL_REVIEW` prompt, parses `ChallengeResponse` structured output |
| `_check_structural_issues` | `(chain, evidence) -> list[Challenge]` | Checks evidence coverage < 0.5 (HIGH), assumption ratio > 50% (MEDIUM), logical validity < 0.5 (MEDIUM), no strong evidence (MEDIUM) |
| `_attempt_resolution` | `(challenge, hypothesis, chain, evidence) -> str | None` | Attempts to resolve challenge using available evidence and hypothesis scores |
| `reflect` | `async (context) -> Reflection` | Analyzes challenge results, resolution rates, unresolved HIGH issues |
| `critique` | `async (contribution) -> Critique` | Maximum skepticism: flags overconfidence, certainty language, missing alternatives |
| `endorse` | `async (contribution) -> bool` | Only endorses contributions showing epistemic humility ("may", "possible", "caveat") and confidence < 0.9 |
| `answer_question` | `async (context) -> Contribution` | Identifies caveats, edge cases, alternative considerations, critiques prior contributions |

**Challenge generation data flow**:

```
_review_from_binder(binder)
  |-- Read top hypothesis from binder (highest score)
  |-- Read causal chain for top hypothesis from binder
  |-- Read evidence from binder
  |-- _review(hypothesis, chain, evidence, prior, binder)
        |-- _generate_challenges(hypothesis, chain, evidence)
        |     |-- Determine evidence availability by type
        |     |-- Format ADVERSARIAL_REVIEW prompt
        |     |-- LLM.generate_structured(prompt, ChallengeResponse)
        |     |-- Map ChallengeItem -> Challenge
        |-- _check_structural_issues(chain, evidence)
        |     |-- Check evidence_coverage < 0.5 -> HIGH
        |     |-- Check assumption_count > steps/2 -> MEDIUM
        |     |-- Check logical_validity < 0.5 -> MEDIUM
        |     |-- Check no strong evidence -> MEDIUM
        |-- For each challenge:
        |     |-- _attempt_resolution(challenge, hypothesis, chain, evidence)
        |     |-- If resolved: set challenge.resolution and challenge.resolved
        |-- binder.add_challenge() for each challenge
        |-- Return list[Challenge]
```

**Challenge types** (from LLM and structural checks):

| Type | Source | Typical Severity | Description |
|------|--------|-----------------|-------------|
| `weak_evidence` | Structural | HIGH or MEDIUM | Evidence coverage below threshold or no strong evidence |
| `missing_evidence` | Structural | MEDIUM | Too many assumption steps in chain |
| `logical_flaw` | Structural or LLM | MEDIUM | Low logical validity or reasoning gaps |
| `alternative` | LLM | MEDIUM | Alternative explanation not ruled out |
| (LLM-defined) | LLM | Varies | Creative challenges from adversarial prompt |

**Resolution strategies**:

| Challenge Type | Resolution Condition | Resolution Text |
|---------------|---------------------|----------------|
| `weak_evidence` | Strong evidence exists | "Strong evidence exists: [content]..." |
| `weak_evidence` | >= 3 moderate evidence items | "No single strong evidence, but N moderate items provide cumulative support" |
| `alternative` | Hypothesis score > 0.6 | "Hypothesis score of N% indicates strong support relative to alternatives" |
| `logical_flaw` | Chain validity > 0.7 | "Chain logical validity is N%, indicating well-explained causal mechanisms" |
| `missing_evidence` | Strong evidence available | "Strong evidence compensates for assumptions in chain" |
| Any MEDIUM | Hypothesis score > 0.7 + evidence | "Hypothesis score with evidence addresses this concern" |

### 5. Prompt Anatomy

**System prompt**: `srcs/prompts/templates/system/skeptic.md`

Loaded via `get_system_prompt(SystemPromptType.SKEPTIC)`. Defines the adversarial reviewer identity and structured output format for challenge generation.

**User prompt**: `srcs/prompts/templates/user/adversarial_review.md`

Loaded via `get_user_prompt(UserPromptType.ADVERSARIAL_REVIEW)`.

**Placeholders**:

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `hypothesis` | Top hypothesis description | The hypothesis being challenged |
| `chain` | Formatted via `_format_chain()` | Causal chain steps with evidence strength and mechanisms |
| `evidence` | `evidence.summary()` | Summary of all collected evidence |
| `evidence_availability` | Computed from evidence types | Per-type availability flags (e.g., "Log files: NOT AVAILABLE") |

The `evidence_availability` placeholder is critical because it prevents the Skeptic from generating invalid challenges about missing evidence types that were never expected. For example, in a code-only investigation without log files, the prompt explicitly states "Log files: NOT AVAILABLE (do not challenge for missing logs)".

**Q&A variant**: `srcs/prompts/templates/system/qa/qa_skeptic.md` (loaded via `SystemPromptType.QA_SKEPTIC`)

**Structured output model**: `ChallengeResponse` from `srcs/workbinder/artifacts/parsers/challenge.py`

```python
class ChallengeItem(BaseModel):
    type: str
    content: str
    severity: str = "MEDIUM"

class ChallengeResponse(BaseModel):
    challenges: List[ChallengeItem]
```

### 6. Session State Interaction

**Reads from binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Hypotheses | `binder.get_hypotheses()` | Top hypothesis to challenge |
| Causal chains | `binder.get_causal_chains()` | Chain quality for structural checks |
| Evidence items | `binder.get_evidence_items()` | Evidence for resolution attempts |

**Writes to binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Challenges | `binder.add_challenge()` | Each challenge with target hypothesis, severity, resolution status |
| LLM exchanges | Via `BasePersona._call_llm_structured` inherited behavior | Traceability |

**Binder artifact structure** (per challenge):

```python
binder.add_challenge(
    target_hypothesis_id=hypothesis.id,
    content=challenge.content,
    severity=challenge.severity,         # "HIGH", "MEDIUM", "LOW"
    requires_response=challenge.requires_response,
    resolved=challenge.resolved,
    resolution=challenge.resolution,     # str | None
    created_by="Skeptic",
    phase=4,
)
```

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 4, phase_name: "Adversarial Review", message: "Challenging conclusions..."}` | Phase begins |
| `llm_request` | `{phase: 4, model_name: "...", system_prompt_length: N, user_prompt_length: N}` | Challenge generation LLM call |
| `llm_response` | `{phase: 4, model_name: "...", response_model: "ChallengeResponse", parse_failed: bool}` | Challenges parsed |
| `phase_complete` | `{phase: 4, phase_name: "Adversarial Review", data: {challenges_raised: N, challenges_resolved: N}}` | Phase done |

### 8. Expert Panel Behavior

**Question types**: All (always included for adversarial perspective)

**`answer_question(context: QuestionContext) -> Contribution`**:

The Skeptic's Q&A contribution is structured as a critical review:

| Content Key | Type | Description |
|-------------|------|-------------|
| `caveats` | `list[str]` | Environment-dependent caveats, version-specific warnings |
| `edge_cases` | `list[str]` | Scenarios where the standard answer fails |
| `alternative_considerations` | `list[str]` | Reframing of the question or alternative root causes |
| `potential_issues` | `list[str]` | Overconfidence flags and missing caveats from prior contributions |
| `answer` | `str` | Critical-perspective answer noting limitations |

The Skeptic analyzes prior contributions for overconfidence (confidence > 0.8), missing caveats, and unchallenged assumptions. It generates caveats specific to the question domain (timeout, config, error keywords).

**Q&A prompt variant**: `SystemPromptType.QA_SKEPTIC`

### 9. Configuration & Tuning

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| LLM temperature | Provider default | LLM config | Temperature for challenge generation |

The Skeptic has no special configuration parameters. Structural challenges are always generated based on fixed thresholds:

| Structural Check | Threshold | Severity |
|-----------------|-----------|----------|
| Evidence coverage | < 0.5 | HIGH |
| Assumption ratio | > 50% of steps | MEDIUM |
| Logical validity | < 0.5 | MEDIUM |
| Strong evidence count | 0 | MEDIUM |

**Tuning guidance**:

- The structural thresholds are deliberately conservative. Loosening them (e.g., allowing coverage < 0.3 before flagging) would reduce challenge noise but risk passing weak conclusions through to the Judge.
- LLM-generated challenges provide creative adversarial analysis that structural checks cannot replicate. If LLM is unavailable, the investigation still receives structural feedback but misses nuanced challenges about alternative explanations and reasoning gaps.

### 10. Error Handling & Fallbacks

| Failure Mode | Detection | Fallback | Impact |
|-------------|-----------|----------|--------|
| LLM unavailable | `self._llm is None` | Returns empty list from `_generate_challenges`; structural challenges still generated | Only structural challenges available; LLM-generated creative challenges missing |
| LLM call fails | Exception in `generate_structured()` | Returns empty challenge list; exception logged | Same as LLM unavailable |
| Parse failure | `ChallengeResponse` validation fails | Empty challenge list returned | Same as LLM unavailable |
| No hypotheses in binder | `hypothesis_artifacts` empty | Returns empty challenge list; logged as warning | Phase produces no challenges; downstream phases handle gracefully |
| No causal chains | `chain_artifacts` empty | Creates default empty chain; structural checks still run against empty chain | Structural checks may flag chain quality issues |
| No evidence | `evidence_artifacts` empty | Raises "insufficient evidence" as structural challenge | Correctly flags evidence gap |

The Skeptic is designed for graceful degradation: the structural challenges provide a minimum baseline of adversarial review even when the LLM is completely unavailable. This is a deliberate design choice -- the investigation should always receive *some* critical feedback.

### 11. Testing Contract

| Test | Input | Expected Output | Key Assertion |
|------|-------|-----------------|---------------|
| `test_skeptic_generates_challenges` | Valid hypothesis, chain, and evidence | `list[Challenge]` with at least 1 entry | `len(challenges) >= 1` |
| `test_skeptic_includes_structural` | Chain with evidence_coverage < 0.5 | Challenges include `weak_evidence` type | `any(c.challenge_type == "weak_evidence" for c in challenges)` |
| `test_skeptic_resolution_attempted` | Challenge with resolvable conditions | Resolved challenge has resolution text | `challenge.resolved is True`, `challenge.resolution is not None` |
| `test_skeptic_llm_fallback` | LLM raises exception | Only structural challenges returned | `len(challenges) > 0`, all from structural checks |
| `test_skeptic_answer_question` | Any question context | Contribution with caveats | `len(content["caveats"]) > 0` |
| `test_skeptic_endorses_carefully` | Contribution with high confidence, no caveats | `False` | Endorsement denied for overconfident contribution |
| `test_skeptic_endorses_humble` | Contribution with "may"/"possible" and confidence < 0.9 | `True` | Endorsement granted for epistemically humble contribution |
| `test_skeptic_critiques_overconfidence` | Contribution with confidence > 0.9 | Critique with HIGH severity | `critique.severity == "HIGH"` |
| `test_skeptic_evidence_availability` | Code-only investigation (no log evidence) | Prompt includes "Log files: NOT AVAILABLE" | No challenge about missing logs |

**Mock requirements**: `LLMProvider` (for `generate_structured`), `WorkBinder` (for artifact read/write)

---

## Judge (Phase 5)

### 1. Identity

| Attribute | Value |
|-----------|-------|
| **Phase** | 5 |
| **Name** | Judge |
| **Role** | Insufficiency Check |
| **Color** | `yellow` |
| **Thinking Phrase** | "Weighing the evidence..." |
| **Prompt Key** | `judge` |
| **Uses LLM** | Yes |
| **Description** | Assesses whether evidence is sufficient for conclusion |

**Traits**: impartial, evaluative, decisive, fair, standards-driven

**Thinking Style**: Judicial evaluation -- applies consistent standards, weighs evidence objectively, renders verdicts based on sufficiency of proof, distinguishes certainty from probability.

The Judge is the decision point of the investigation pipeline. It receives the full body of evidence, hypotheses, causal chains, and challenges, and renders a verdict: is there enough evidence to reach a conclusion, and if so, how confident should we be? This verdict determines the structure of the final output produced by the Synthesizer.

### 2. Responsibilities

**Pipeline role**: Assesses evidence sufficiency and determines the investigation outcome. The outcome is one of five values:

| Outcome | Meaning | Conditions |
|---------|---------|------------|
| `CONFIDENT` | Strong conclusion supported by evidence | Strong evidence >= 2, top hypothesis score > 0.7, no unresolved HIGH challenges |
| `PROBABLE` | Likely conclusion with some gaps | Evidence count > 0, top hypothesis score > 0.5 |
| `UNCERTAIN` | Multiple viable hypotheses, cannot discriminate | Some evidence but inconclusive |
| `CONTRADICTORY` | Conflicting strong evidence | Conflicting evidence pointing to different causes |
| `INSUFFICIENT` | Not enough evidence to conclude | No meaningful evidence collected |

The Judge uses LLM-based assessment as the primary path, falling back to rule-based assessment when the LLM is unavailable. The LLM assessment receives a comprehensive evidence summary including the Detective's enhanced artifacts (evidence quality score, evidence gap analysis, alternative investigation paths).

**Expert panel role**: Assesses evidence quality and renders judgment on confidence levels in Q&A answers.

**Artifacts produced**:

| Artifact | Type | Description |
|----------|------|-------------|
| Outcome assessment | `OutcomeAssessment` (Pydantic) | `outcome`, `confidence_score`, `reasoning`, `criteria_met`, `criteria_not_met`, `evidence_gaps`, `unresolved_concerns`, `recommendation` |
| Contribution content | `dict` | All `OutcomeAssessment` fields plus `assessment_method` ("llm" or "rules") |

**Artifacts consumed**:

| Artifact | Source | Description |
|----------|--------|-------------|
| Hypotheses | Theorist via binder | Hypothesis scores and descriptions |
| Evidence | Detective via binder | Evidence counts by strength, detailed items |
| Causal chains | Logician via binder | Chain validity and coverage scores |
| Challenges | Skeptic via binder | Challenge counts by severity, resolution status |
| Detective contribution | Detective via binder | Enhanced artifacts: evidence_quality_score, evidence_gap_analysis, alternative_paths |

### 3. Tool Mapping

| API Tool | Invokes Judge? | Capabilities Used |
|----------|---------------|-------------------|
| `investigate` | Yes (Phase 5) | Full assessment |
| `investigate_stream` | Yes (Phase 5) | Full assessment + SSE progress |
| `ask_experts` | Yes (for TROUBLESHOOT, WHY questions) | Evidence quality assessment |

### 4. Implementation

**Class**: `JudgePersona` in `srcs/persona/judge.py`

**Inheritance**: Extends `BasePersona`

**Internal model**:

```python
class OutcomeAssessment(BaseModel):
    """LLM response for outcome assessment."""
    outcome: str                          # "CONFIDENT", "PROBABLE", etc.
    confidence_score: float               # 0.0-1.0
    reasoning: str                        # Explanation of the verdict
    criteria_met: List[str] = []          # Decision criteria satisfied
    criteria_not_met: List[str] = []      # Decision criteria not satisfied
    evidence_gaps: List[str] = []         # Identified evidence gaps
    unresolved_concerns: List[str] = []   # Concerns from challenges
    recommendation: str = ""              # Recommended next steps
```

**Instance state**:

```python
class JudgePersona(BasePersona):
    def __init__(self) -> None:
        self._llm_assessment: OutcomeAssessment | None = None
```

**Key methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `prepare` | `async (context) -> None` | No-op (LLM used in contribute) |
| `contribute` | `async (context) -> Contribution` | Tries LLM assessment first, falls back to rule-based |
| `_assess_with_llm` | `async (context) -> OutcomeAssessment | None` | Gathers comprehensive evidence summary from binder, formats `OUTCOME_ASSESSMENT` prompt with all placeholders, calls LLM with `OutcomeAssessment` response model |
| `_assess_sufficiency_rules` | `(context) -> dict` | Rule-based fallback: evaluates evidence counts, hypothesis scores, challenge resolution rates |
| `_build_content_from_llm` | `(assessment) -> dict` | Maps `OutcomeAssessment` fields to contribution content dict |
| `_build_reasoning_rules` | `(assessment) -> str` | Builds reasoning string from rule-based assessment |
| `reflect` | `async (context) -> Reflection` | Outcome-specific insights and suggestions |
| `critique` | `async (contribution) -> Critique` | Evaluates evidentiary standards: citation requirements, confidence/language consistency |
| `endorse` | `async (contribution) -> bool` | Endorses well-reasoned contributions with appropriate confidence (< 0.9) |
| `answer_question` | `async (context) -> Contribution` | Assesses contribution quality across the panel |

**Assessment data flow (LLM path)**:

```
_assess_with_llm(context)
  |-- Read hypotheses from binder (top 5 by score)
  |-- Read evidence from binder (counts by strength)
  |-- Read causal chains from binder (validity, coverage)
  |-- Read challenges from binder (unresolved HIGH/MEDIUM counts)
  |-- Read Detective contribution from binder:
  |     |-- evidence_quality_score (overall, strength, diversity, coverage, discrimination)
  |     |-- evidence_gap_analysis (gaps list with severity)
  |     |-- alternative_paths (suggested investigation directions)
  |-- Determine evidence mode (FULL-CONTEXT vs LIMITED-INPUT)
  |-- Format OUTCOME_ASSESSMENT prompt with 26+ placeholders
  |-- LLM.generate_structured(prompt, OutcomeAssessment)
  |-- Return OutcomeAssessment or None on failure
```

**Rule-based assessment logic**:

```python
# Default: INSUFFICIENT
if hypotheses exist:
    supported = [h for h if h.supporting_evidence_ids and h.score > 0.5]
    if best.score > 0.7 and strong_evidence >= 2:
        outcome = "CONFIDENT", confidence = 0.85
    elif best.score > 0.5:
        outcome = "PROBABLE", confidence = 0.65

# Downgrade on unresolved challenges:
if unresolved_HIGH > 0:
    CONFIDENT -> PROBABLE, confidence = 0.6
if unresolved_MEDIUM >= 3:
    CONFIDENT -> PROBABLE, confidence = 0.65
```

### 5. Prompt Anatomy

**System prompt**: `srcs/prompts/templates/system/judge.md`

Loaded via `get_system_prompt(SystemPromptType.JUDGE)`. Defines the judicial evaluator identity and the five-outcome decision framework.

**User prompt**: `srcs/prompts/templates/user/outcome_assessment.md`

Loaded via `get_user_prompt(UserPromptType.OUTCOME_ASSESSMENT)`.

**Placeholders** (26 total):

| Category | Placeholders | Source |
|----------|-------------|--------|
| Error context | `error_message` | `context.error.message` |
| Hypotheses | `hypotheses_summary`, `top_hypothesis`, `top_score` | Binder hypotheses |
| Evidence counts | `evidence_count`, `strong_evidence_count`, `moderate_evidence_count`, `weak_evidence_count` | Binder evidence |
| Evidence details | `evidence_details` | First 10 evidence items with strength and type |
| Chains | `causal_chains_summary` | Chain validity and coverage per hypothesis |
| Challenges | `challenges_summary`, `unresolved_high_count`, `unresolved_medium_count` | Binder challenges |
| Context mode | `has_context_logs`, `evidence_mode` | Evidence type analysis |
| Quality scores | `evidence_quality_score`, `quality_strength_score`, `quality_diversity_score`, `quality_coverage_score`, `quality_discrimination_score` | Detective's evidence_quality_score |
| Types | `evidence_types_present`, `evidence_types_missing` | Detective's quality assessment |
| Gaps | `evidence_gap_analysis`, `evidence_gap_count`, `most_critical_gap` | Detective's gap analysis |
| Alternatives | `alternative_paths` | Detective's suggested investigation paths |

This is the most placeholder-rich prompt in the entire system, reflecting the Judge's need to consider all aspects of the investigation before rendering a verdict.

**Q&A variant**: None (uses base `SystemPromptType.JUDGE` system prompt for Q&A)

**Structured output model**: `OutcomeAssessment` (defined in `srcs/persona/judge.py`, not in the parsers module)

### 6. Session State Interaction

**Reads from binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Hypotheses | `binder.get_hypotheses()` | Hypothesis scores and descriptions |
| Evidence items | `binder.get_evidence_items()` | Evidence strength distribution |
| Causal chains | `binder.get_causal_chains()` | Chain quality scores |
| Challenges | `binder.get_challenges()` | Challenge severity and resolution status |
| Detective contribution | `binder.get_persona_contributions(persona_id="detective")` | Enhanced artifacts (quality scores, gaps, paths) |

**Writes to binder**:

| Data | Method | Purpose |
|------|--------|---------|
| LLM exchanges | Via `_call_llm_structured` | Records assessment prompt and response |
| Contribution | Via coordinator | Stored in context.contributions, consumed by Synthesizer |

The Judge's contribution content dict is read directly by the Synthesizer in Phase 6 to determine the outcome and extract evidence gaps and criteria not met.

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 5, phase_name: "Insufficiency Check", message: "Weighing the evidence..."}` | Phase begins |
| `llm_request` | `{phase: 5, model_name: "...", system_prompt_length: N, user_prompt_length: N}` | Outcome assessment LLM call |
| `llm_response` | `{phase: 5, model_name: "...", response_model: "OutcomeAssessment", parse_failed: bool}` | Assessment parsed |
| `phase_complete` | `{phase: 5, phase_name: "Insufficiency Check", data: {outcome: "CONFIDENT", confidence: 0.82}}` | Phase done |

### 8. Expert Panel Behavior

**Question types**: TROUBLESHOOT, WHY

**`answer_question(context: QuestionContext) -> Contribution`**:

The Judge's Q&A contribution assesses the quality of all other contributions:

| Content Key | Type | Description |
|-------------|------|-------------|
| `quality_assessment` | `dict[str, dict]` | Per-persona quality scores (confidence, has_reasoning, has_evidence, has_caveats, quality_score) |
| `reliability_score` | `float` | Overall reliability across all contributions |
| `recommendations` | `list[str]` | Suggestions for improving answer quality |
| `answer` | `str` | Balanced assessment-based answer |
| `key_points` | `list[str]` | Top contributions by quality score |

**Quality scoring**:

```python
score = 0.5  # Base
if has_reasoning: score += 0.1
if has_evidence: score += 0.15
if appropriate_confidence (0.3-0.8): score += 0.1
if has_caveats: score += 0.1
# max 0.95
```

### 9. Configuration & Tuning

The Judge has no special configuration parameters. The outcome thresholds in the rule-based fallback are fixed:

| Outcome | Conditions (Rule-Based) |
|---------|------------------------|
| `CONFIDENT` | `strong_evidence >= 2` AND `top_hypothesis.score > 0.7` AND `unresolved_HIGH == 0` |
| `PROBABLE` | `evidence_count > 0` AND `top_hypothesis.score > 0.5` |
| `UNCERTAIN` | Some evidence but no hypothesis above 0.5 |
| `CONTRADICTORY` | Conflicting strong evidence |
| `INSUFFICIENT` | No meaningful evidence |

**Downgrade rules**:

| Condition | Effect |
|-----------|--------|
| Any unresolved HIGH challenge | `CONFIDENT` -> `PROBABLE` (confidence 0.6) |
| >= 3 unresolved MEDIUM challenges | `CONFIDENT` -> `PROBABLE` (confidence 0.65) |

The LLM-based assessment path does not use these fixed thresholds; instead, it receives the full context and applies its own judgment based on the comprehensive evidence summary. The LLM path generally produces more nuanced outcomes because it can weigh qualitative factors that the rule-based path cannot.

### 10. Error Handling & Fallbacks

| Failure Mode | Detection | Fallback | Impact |
|-------------|-----------|----------|--------|
| LLM unavailable | `context.llm is None` | Rule-based assessment via `_assess_sufficiency_rules()` | Less nuanced outcome; fixed thresholds instead of qualitative judgment |
| LLM call fails | Exception in `_call_llm_structured()` | Same rule-based fallback | Same as above |
| Prompt formatting fails | Exception in `user_prompt_template.format()` | Returns `None`, triggers rule-based fallback | Missing placeholder data; logged as warning |
| Parse failure | `OutcomeAssessment` validation fails | Rule-based fallback | Same as LLM unavailable |
| No hypotheses | `context.hypotheses` empty | `INSUFFICIENT` outcome with reasoning gap "No hypotheses generated" | Correct outcome for empty investigation |
| No evidence | `context.evidence` empty | `INSUFFICIENT` outcome with reasoning gap "No evidence collected" | Correct outcome |
| Detective contribution missing | `detective_contributions` empty | Placeholder values "N/A" for quality scores, gap analysis, alternative paths | Assessment proceeds without enhanced quality metrics |

The rule-based fallback produces the same `OutcomeAssessment`-compatible structure (as a dict), ensuring that the Synthesizer receives consistent input regardless of which assessment path was used.

### 11. Testing Contract

| Test | Input | Expected Output | Key Assertion |
|------|-------|-----------------|---------------|
| `test_judge_assesses_confident` | Strong evidence + high hypothesis score + no unresolved HIGH challenges | `outcome == "CONFIDENT"` | Confidence >= 0.8 |
| `test_judge_assesses_probable` | Moderate evidence + moderate hypothesis score | `outcome == "PROBABLE"` | Confidence 0.5-0.8 |
| `test_judge_assesses_insufficient` | No evidence, no hypotheses | `outcome == "INSUFFICIENT"` | Reasoning gaps include "No evidence collected" |
| `test_judge_downgrades_on_challenges` | CONFIDENT conditions but unresolved HIGH challenge | `outcome == "PROBABLE"` | Downgrade from CONFIDENT |
| `test_judge_llm_assessment` | LLM returns valid `OutcomeAssessment` | LLM assessment used directly | `content["assessment_method"] == "llm"` |
| `test_judge_rule_based_fallback` | No LLM available | Rule-based assessment | `content["assessment_method"] == "rules"` |
| `test_judge_uses_detective_artifacts` | Detective contribution with evidence_quality_score | Quality scores appear in prompt | Prompt contains evidence quality data |
| `test_judge_answer_question` | TROUBLESHOOT question context | Contribution with quality assessment | `content["reliability_score"]` is float |
| `test_judge_endorses_well_reasoned` | Contribution with reasoning and confidence < 0.9 | `True` | Endorsement granted |
| `test_judge_rejects_unsupported_confidence` | Contribution with confidence > 0.8 but no evidence in reasoning | Critique with "lacks explicit evidence citation" | Issue flagged |

**Mock requirements**: `LLMProvider` (for `generate_structured`), `WorkBinder` (for artifact read/write)

---

## Synthesizer (Phase 6)

### 1. Identity

| Attribute | Value |
|-----------|-------|
| **Phase** | 6 |
| **Name** | Synthesizer |
| **Role** | Final Synthesis |
| **Color** | `white` |
| **Thinking Phrase** | "Bringing it all together..." |
| **Prompt Key** | `synthesizer` |
| **Uses LLM** | Yes |
| **Description** | Synthesizes final investigation result |

**Traits**: integrative, holistic, communicative, action-oriented, clear

**Thinking Style**: Integrative synthesis -- combines diverse inputs, creates coherent narrative, ensures actionability, communicates clearly for the intended audience.

The Synthesizer is the final persona in the main investigation pipeline. It receives the Judge's outcome determination and all upstream artifacts, and produces the `InvestigationResult` that is returned to the caller. This result includes an executive summary, root cause identification (for CONFIDENT/PROBABLE outcomes), causal chain narrative, key evidence, debugging steps, caveats, and calibrated confidence scores.

The Synthesizer is also the most complex persona in terms of output structure, as it must produce outcome-specific results: a CONFIDENT investigation populates root cause and recommendations, while an INSUFFICIENT investigation populates the insufficient reason and missing evidence suggestions.

### 2. Responsibilities

**Pipeline role**: Brings together all investigation findings into a coherent final result. The Synthesizer performs two distinct synthesis tasks:

1. **Contribution synthesis** (`contribute` method): Uses LLM or rules to generate a `SynthesisResponse` with executive summary, root cause info, causal narrative, key evidence, debugging steps, caveats, and confidence. This is stored as the persona's contribution.

2. **Result synthesis** (`synthesize` / `synthesize_from_binder` methods): Constructs the full `InvestigationResult` model with outcome-specific content, confidence calibration, recommendations, alternatives, and binder conclusion artifact. This is the final pipeline output.

**Expert panel role**: Synthesizes all panel contributions into a unified answer. The Synthesizer is always included in expert panel Q&A as the final answer merger.

**Artifacts produced**:

| Artifact | Type | Description |
|----------|------|-------------|
| Investigation result | `InvestigationResult` | Complete pipeline output with outcome-specific fields |
| Synthesis response | `SynthesisResponse` | LLM-generated synthesis (when available) |
| Calibrated confidence | `CalibratedConfidence` | Raw + calibrated confidence with derivation and notes |
| Binder conclusion | Via `binder.add_conclusion()` | Final conclusion artifact in binder |

**Artifacts consumed**:

| Artifact | Source | Description |
|----------|--------|-------------|
| All hypotheses | Theorist via binder | Ranked for root cause selection and alternatives |
| All evidence | Detective via binder | For evidence summary and key evidence selection |
| Causal chains | Logician via binder | For causal narrative |
| Challenges | Skeptic via binder | For caveats and unresolved concerns |
| Outcome | Judge via binder contributions | CONFIDENT/PROBABLE/UNCERTAIN/CONTRADICTORY/INSUFFICIENT |
| Source locations | Archivist via binder | Code context, file paths, function names |
| Numeric findings | Via binder tags | Quantitative context from Phase 0 |
| Code snippets | Via binder | Code context from Phase 0 |
| Detective contribution | Via binder | Alternative paths for INSUFFICIENT suggestions |

### 3. Tool Mapping

| API Tool | Invokes Synthesizer? | Capabilities Used |
|----------|---------------------|-------------------|
| `investigate` | Yes (Phase 6) | Full synthesis |
| `investigate_stream` | Yes (Phase 6) | Full synthesis + SSE progress |
| `ask_experts` | Yes (always included) | Answer synthesis |

The Synthesizer is always included in expert panel Q&A regardless of question type, serving as the final integrator of all persona contributions.

### 4. Implementation

**Class**: `SynthesizerPersona` in `srcs/persona/synthesizer.py`

**Inheritance**: Extends `BasePersona`

**Internal models**:

```python
class RootCauseInfo(BaseModel):
    description: str
    code_location: str = ""
    mechanism: str = ""

class KeyEvidence(BaseModel):
    type: str
    content: str
    significance: str

class DebuggingStep(BaseModel):
    action: str
    purpose: str
    expected_result: str = ""

class ConfidenceInfo(BaseModel):
    level: str              # "high", "medium", "low"
    raw_score: float
    calibrated_score: float = 0.0
    reasoning: str = ""

class SynthesisResponse(BaseModel):
    executive_summary: str
    root_cause: RootCauseInfo
    causal_narrative: List[str] = []
    key_evidence: List[KeyEvidence] = []
    debugging_steps: List[DebuggingStep] = []
    caveats: List[str] = []
    confidence: ConfidenceInfo
```

**Instance state**:

```python
class SynthesizerPersona(BasePersona):
    def __init__(self) -> None:
        self._llm_synthesis: SynthesisResponse | None = None
        self._kb: KnowledgeBase | None = None
```

**Key methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `prepare` | `async (context) -> None` | No-op |
| `contribute` | `async (context) -> Contribution` | Tries LLM synthesis first, falls back to rule-based |
| `_synthesize_with_llm` | `async (context) -> SynthesisResponse | None` | Gathers all artifacts from binder, formats `FINAL_SYNTHESIS` prompt with 16 placeholders, calls LLM with `SynthesisResponse` model |
| `_synthesize_rules` | `(context) -> dict` | Rule-based fallback: constructs result from Judge outcome, top hypothesis, evidence summary |
| `synthesize` | `async (investigation, outcome, hypotheses, chains, evidence, prior, binder) -> InvestigationResult` | Full result synthesis with outcome-specific logic |
| `synthesize_from_binder` | `async (binder, investigation, outcome) -> InvestigationResult` | Reads all inputs from binder, delegates to `synthesize` |
| `_synthesize_confident` | `async (result, hypothesis, chain, evidence, challenges, prior, all_hypotheses) -> InvestigationResult` | CONFIDENT/PROBABLE path: root cause, confidence calibration, code context, sub-causes, key files, debugging steps, recommendations |
| `_synthesize_uncertain` | `(result, hypotheses, evidence) -> InvestigationResult` | UNCERTAIN path: viable hypotheses, discrimination needed |
| `_synthesize_insufficient` | `(result, hypotheses, evidence, detective_contribution) -> InvestigationResult` | INSUFFICIENT path: reason, missing evidence (uses Detective's alternative paths if available) |
| `_synthesize_contradictory` | `(result, hypotheses, evidence) -> InvestigationResult` | CONTRADICTORY path: contradictory evidence notes |
| `_calculate_raw_confidence` | `(hypothesis, chain, evidence, challenges) -> float` | Composite score from hypothesis score, evidence strength, chain quality, challenge penalties |
| `_check_evidence_alignment` | `(hypotheses, evidence) -> dict[str, float]` | Keyword overlap between hypothesis descriptions and evidence content |
| `reflect` | `async (context) -> Reflection` | Assesses synthesis quality: root cause identification, evidence highlights, debugging steps, caveats |
| `endorse` | `async (contribution) -> bool` | Endorses clear, well-reasoned contributions with both content and reasoning |
| `answer_question` | `async (context) -> Contribution` | Merges all panel contributions into unified answer with key points, action items, sources |

**LLM synthesis data flow**:

```
_synthesize_with_llm(context)
  |-- Read investigation_id, error_message, error_component from binder/context
  |-- Read Judge contribution -> outcome, confidence
  |-- Read hypotheses from binder -> ranked list with evidence alignment
  |-- Read evidence from binder -> formatted summary
  |-- Read causal chains from binder -> step claims
  |-- Read challenges from binder -> severity and resolution status
  |-- Read source locations from binder -> file:line (function)
  |-- Read numeric findings from binder -> quantitative context
  |-- Read code snippets from binder -> function bodies
  |-- Read Judge's evidence_gaps and criteria_not_met
  |-- Format FINAL_SYNTHESIS prompt with 16 placeholders
  |-- LLM.generate_structured(prompt, SynthesisResponse)
  |-- Return SynthesisResponse or None on failure
```

**Result synthesis data flow (CONFIDENT/PROBABLE path)**:

```
_synthesize_confident(result, hypothesis, chain, evidence, challenges, prior, all_hypotheses)
  |-- _calculate_raw_confidence(hypothesis, chain, evidence, challenges)
  |     |-- base = 0.3 + (hypothesis.score * 0.3) + (hypothesis.prior * 0.1)
  |     |-- + strong_support * 0.1 + supporting * 0.02 - contradicting * 0.08
  |     |-- + chain.evidence_coverage * 0.1 + chain.logical_validity * 0.05
  |     |-- Challenge penalties: HIGH * 0.15, MEDIUM * 0.05
  |-- calculate_calibrated_confidence(raw, calibration_data)
  |     |-- Bucket-specific calibration (n>=10) or overall bias correction
  |     |-- Wilson score intervals for small samples
  |-- _extract_code_context(prior) -> snippet, location, data_flow
  |-- _extract_key_files(prior, evidence) -> list[KeyFile]
  |-- _generate_debugging_steps(hypothesis, prior, evidence) -> list[str]
  |-- _generate_sub_causes(hypothesis, all_hypotheses, evidence) -> list[SubCause]
  |-- _generate_caveats(hypothesis, chain, evidence) -> list[str]
  |-- _generate_recommendations(hypothesis, chain) -> list[str]
  |-- Build InvestigationConclusion with all fields
  |-- Return populated InvestigationResult
```

**Confidence calibration**: Uses `calculate_calibrated_confidence()` from `srcs/knowledge/calibration.py`. This function applies bucket-specific calibration when sufficient historical data exists (>= 10 samples in the confidence bucket), or overall bias correction otherwise. Wilson score intervals provide conservative estimates for small sample sizes. See the `KnowledgeBase` module documentation for calibration details.

### 5. Prompt Anatomy

**System prompt**: `srcs/prompts/templates/system/synthesizer.md`

Loaded via `get_system_prompt(SystemPromptType.SYNTHESIZER)`. Defines the synthesis expert identity and structured output format.

**User prompt**: `srcs/prompts/templates/user/final_synthesis.md`

Loaded via `get_user_prompt(UserPromptType.FINAL_SYNTHESIS)`.

**Placeholders** (16):

| Placeholder | Source | Description |
|-------------|--------|-------------|
| `investigation_id` | `binder.id[:8]` | Short investigation ID |
| `error_message` | `context.error.message` | Original trigger error |
| `error_component` | `context.error.component` | Component that produced the error |
| `started_at` | `datetime.now().isoformat()` | Investigation start time |
| `duration` | Computed | Investigation duration |
| `outcome` | Judge contribution | CONFIDENT/PROBABLE/etc. |
| `confidence` | Judge contribution | Raw confidence score |
| `hypotheses_ranked` | Binder hypotheses | Ranked list with score, evidence alignment, source |
| `evidence_summary` | Binder evidence | Evidence items with strength and type |
| `causal_chain` | Binder chains | Step claims from top chain |
| `challenges_summary` | Binder challenges | Challenge severity, content, resolution status |
| `source_locations` | Binder source locations | Top 3 file:line (function) [match score] |
| `numeric_context` | Binder tagged findings | Numeric analysis results from Phase 0 |
| `code_context` | Binder code snippets | Top 3 function bodies with file paths |
| `judge_evidence_gaps` | Judge contribution | Evidence gaps identified by Judge |
| `judge_criteria_not_met` | Judge contribution | Decision criteria the investigation did not meet |

**Q&A variant**: None (Synthesizer uses base system prompt for Q&A)

**Structured output model**: `SynthesisResponse` (defined in `srcs/persona/synthesizer.py`)

### 6. Session State Interaction

**Reads from binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Hypotheses | `binder.get_hypotheses()` | Root cause selection, alternatives |
| Evidence items | `binder.get_evidence_items()` | Evidence summary, key evidence |
| Causal chains | `binder.get_causal_chains()` | Causal narrative |
| Challenges | `binder.get_challenges()` | Caveats, unresolved concerns |
| Source locations | `binder.get_source_locations()` | Code context |
| Code snippets | `binder.get_code_snippets()` | Function bodies |
| Numeric findings | `binder.get_by_tag("numeric_analysis")` | Quantitative context |
| Judge contribution | `binder.get_persona_contributions(persona_id="judge")` | Outcome and evidence gaps |
| Detective contribution | `binder.get_persona_contributions(persona_id="detective")` | Alternative paths |

**Writes to binder**:

| Data | Method | Purpose |
|------|--------|---------|
| Conclusion | `binder.add_conclusion()` | Final conclusion with root cause, confidence, debugging steps, caveats, unresolved challenges |
| LLM exchanges | Via `_call_llm_structured` | Records synthesis prompt and response |

**Binder conclusion structure**:

```python
binder.add_conclusion(
    root_cause=str,                    # Root cause description or insufficient reason
    confidence_raw=float,              # Raw confidence (0.0-1.0)
    confidence_calibrated=float,       # Calibrated confidence
    outcome=str,                       # "CONFIDENT", "PROBABLE", etc.
    code_location=str | None,          # file:line in function()
    code_snippet=str | None,           # Relevant source code
    data_flow=str | None,              # Call graph / data flow path
    caveats=list[str],                 # Caveats and limitations
    debugging_steps=list[str],         # Recommended debugging steps
    unresolved_challenges=list[str],   # Unresolved HIGH challenges
    created_by="Synthesizer",
    phase=6,
)
```

### 7. SSE Events

| Event | Payload | When |
|-------|---------|------|
| `phase_start` | `{phase: 6, phase_name: "Final Synthesis", message: "Bringing it all together..."}` | Phase begins |
| `llm_request` | `{phase: 6, model_name: "...", system_prompt_length: N, user_prompt_length: N}` | Synthesis generation LLM call |
| `llm_response` | `{phase: 6, model_name: "...", response_model: "SynthesisResponse", parse_failed: bool}` | Synthesis parsed |
| `phase_complete` | `{phase: 6, phase_name: "Final Synthesis", data: {outcome: "CONFIDENT"}}` | Phase done |

### 8. Expert Panel Behavior

**Question types**: All (always included as the synthesizer of panel answers)

**`answer_question(context: QuestionContext) -> Contribution`**:

The Synthesizer's Q&A contribution merges all persona contributions into a unified answer:

| Content Key | Type | Description |
|-------------|------|-------------|
| `answer` | `str` | Merged answer from all contributions (deduplicates concepts, keeps top 3 unique perspectives) |
| `key_points` | `list[str]` | Deduplicated key points from all contributions (max 10) |
| `action_items` | `list[str]` | Question-type-specific action items (max 5) |
| `sources` | `list[str]` | Deduplicated source references from all contributions |
| `summary` | `str` | Brief summary of key points and caveats |

**Answer merging strategy**: The `_merge_answers` method combines multiple answer strings by tracking seen concepts (word sets). Each answer is included only if it contributes at least 5 new words not already covered by previous answers. This prevents repetitive content while preserving diverse perspectives.

**Confidence calculation**: Average confidence across all contributions plus a diversity bonus (0.1 per contribution, capped at 0.2), capped at 0.9 overall.

### 9. Configuration & Tuning

| Parameter | Default | Source | Description |
|-----------|---------|--------|-------------|
| LLM temperature | Provider default | LLM config | Temperature for synthesis generation |
| Calibration data | Historical | `KnowledgeBase.get_calibration("default")` | Bucket-specific accuracy data for confidence calibration |

The Synthesizer has no persona-specific configuration parameters. Its behavior is primarily determined by the outcome from the Judge and the quality of artifacts from upstream phases.

**Tuning guidance**:

- The confidence calibration system is the primary tuning mechanism. As the system accumulates investigation feedback (via the Learning phase and user corrections), calibration improves automatically.
- The `_generate_sub_causes` method produces domain-specific sub-cause distributions (fragment/generator, timeout, null/pointer, config, exception categories). These distributions are hardcoded based on domain expertise and should be updated if the distribution of actual root causes shifts significantly.
- Evidence alignment scoring (`_check_evidence_alignment`) uses keyword overlap, which can be noisy for short hypothesis descriptions. This affects root cause selection in the rule-based path when the top-scoring hypothesis has poor evidence alignment.

### 10. Error Handling & Fallbacks

| Failure Mode | Detection | Fallback | Impact |
|-------------|-----------|----------|--------|
| LLM unavailable | `context.llm is None` | Rule-based synthesis via `_synthesize_rules()` | Less polished output; structured fields still populated |
| LLM call fails | Exception in `_call_llm_structured()` | Same rule-based fallback | Same as above |
| Prompt formatting fails | Exception in `user_prompt_template.format()` | Returns `None`, triggers rule-based fallback | Missing data; logged as warning |
| Parse failure | `SynthesisResponse` validation fails | Rule-based fallback | Same as LLM unavailable |
| Calibration unavailable | `KnowledgeBase.get_calibration()` raises or returns `None` | Raw confidence used without calibration adjustment | Confidence not adjusted; notes indicate "No calibration data available" |
| No Judge outcome | `judge_contributions` empty | Defaults to `INSUFFICIENT` with confidence 0.5 | Conservative outcome |
| No hypotheses | `context.hypotheses` empty | `root_cause = None`; INSUFFICIENT outcome | No root cause identified |
| No evidence | `context.evidence` empty or no items | Empty evidence summary; affects outcome assessment | Likely INSUFFICIENT outcome |

**Outcome-specific fallback paths**:

| Outcome | LLM Path | Rule-Based Fallback |
|---------|----------|-------------------|
| CONFIDENT/PROBABLE | Full `SynthesisResponse` with narrative | Root cause from top hypothesis, evidence summary, basic recommendations |
| UNCERTAIN | Not synthesized separately by LLM | Viable hypotheses list, discrimination needed, code-only recommendations if no logs |
| INSUFFICIENT | Not synthesized separately by LLM | Insufficient reason, missing evidence list (from Detective's alternative paths or generic suggestions) |
| CONTRADICTORY | Not synthesized separately by LLM | Contradictory evidence notes, clarification suggestions |

### 11. Testing Contract

| Test | Input | Expected Output | Key Assertion |
|------|-------|-----------------|---------------|
| `test_synthesizer_produces_result` | Valid context with all phases completed | `InvestigationResult` with outcome | `result.outcome is not None` |
| `test_synthesizer_confident_has_root_cause` | CONFIDENT outcome, top hypothesis | Root cause populated | `result.root_cause is not None`, `result.root_cause.root_cause` is non-empty |
| `test_synthesizer_probable_has_root_cause` | PROBABLE outcome | Root cause populated | Same as CONFIDENT |
| `test_synthesizer_insufficient_has_reason` | INSUFFICIENT outcome | Insufficient reason populated | `result.insufficient_reason is not None` |
| `test_synthesizer_uncertain_has_viable_hypotheses` | UNCERTAIN outcome, multiple hypotheses | Viable hypotheses list | `len(result.viable_hypotheses) > 0` |
| `test_synthesizer_calibrates_confidence` | Raw confidence + calibration data | Calibrated confidence differs from raw | `result.root_cause.confidence.calibrated != result.root_cause.confidence.raw` |
| `test_synthesizer_no_calibration_uses_raw` | Raw confidence, no calibration data | Calibrated equals raw | `calibrated == raw` |
| `test_synthesizer_llm_synthesis` | LLM returns valid `SynthesisResponse` | LLM synthesis used | `content["synthesis_method"] == "llm"` |
| `test_synthesizer_rule_based_fallback` | No LLM available | Rule-based result | `content["synthesis_method"] == "rules"` |
| `test_synthesizer_evidence_alignment` | Multiple hypotheses with varying evidence overlap | Top-aligned hypothesis selected for root cause | Evidence-aligned hypothesis preferred when top-scored has poor alignment |
| `test_synthesizer_answer_question` | Panel Q&A context with 3 contributions | Synthesized answer with merged content | `len(content["key_points"]) > 0` |
| `test_synthesizer_generates_sub_causes` | Timeout-related hypothesis | Sub-causes with domain-specific distribution | Sub-causes include "Network latency", "Hardware response delay", etc. |
| `test_synthesizer_generates_debugging_steps` | Fragment-related hypothesis with source locations | Debugging steps with code references | Steps include "Search logs for" and "Review source code at" |
| `test_synthesizer_writes_conclusion_to_binder` | Successful synthesis | `binder.add_conclusion()` called | Conclusion artifact contains root cause and confidence |

**Mock requirements**: `LLMProvider` (for `generate_structured`), `WorkBinder` (for artifact read/write), `KnowledgeBase` (for calibration data)

---

## Cross-Persona Data Dependencies

The four analysis personas form a strict linear dependency chain. The following table summarizes what each persona reads and writes, showing how data flows through the analysis pipeline:

| Phase | Persona | Reads From | Writes To | Key Constraint |
|-------|---------|-----------|----------|---------------|
| 3 | Logician | Hypotheses (P1), Evidence (P2) | Causal chains | Requires at least 1 hypothesis above `min_chain_score` |
| 4 | Skeptic | Hypotheses (P1), Chains (P3), Evidence (P2) | Challenges | Structural challenges always generated; LLM challenges optional |
| 5 | Judge | Hypotheses (P1), Evidence (P2), Chains (P3), Challenges (P4), Detective contribution (P2) | Outcome assessment | LLM assessment preferred; rule-based fallback available |
| 6 | Synthesizer | All upstream + Judge outcome | InvestigationResult + Binder conclusion | Outcome determines result structure |

**Empty input handling**: Each persona is designed to handle missing upstream data gracefully. If evidence is empty, chains will be assumption-heavy. If chains are empty, the Skeptic targets hypotheses directly. If challenges are empty, the Judge sees no impediments. If the outcome is missing, the Synthesizer defaults to INSUFFICIENT. This cascading graceful degradation ensures the pipeline always produces *some* result, even under adverse conditions.

---

> [← Pipeline Personas](agentic-persona-library-ch2-pipeline-personas.md) | [Table of Contents](agentic-persona-library.md) | [Next: Learning Personas →](agentic-persona-library-ch4-learning-personas.md)
