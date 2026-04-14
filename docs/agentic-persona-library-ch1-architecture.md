> **Agentic Persona Library** | [Table of Contents](agentic-persona-library.md) | [Next: Pipeline Personas →](agentic-persona-library-ch2-pipeline-personas.md)

---

# Chapter 1: Architecture & Foundations

---

### 1. Design Philosophy

The persona system is built on three core design principles that separate concerns and enable independent evolution of each layer.

**Separation of identity from orchestration.** A persona defines *who* it is -- its traits, thinking style, collaboration methods, and domain expertise. The orchestration layer defines *how* it executes -- iteration loops, strategy adaptation, query effectiveness tracking, and tool invocation. This separation lives in the codebase as a clean boundary:

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Identity | `srcs/persona/<name>.py` | Traits, thinking style, `contribute()`, `critique()`, `endorse()`, `answer_question()` |
| Orchestration | `srcs/persona/orchestration/` | `EvidenceOrchestrator`, `RetrievalOrchestrator`, strategy management |
| Execution | `srcs/pipeline/persona_executor.py` | `PersonaExecutor`, `UnifiedPersonaExecutor` -- lifecycle wrapping within pipeline |
| Coordination | `srcs/persona/coordinator.py` | `CoordinatorPersona` -- panel assembly, discussion facilitation, disagreement resolution |
| Panel | `srcs/persona/orchestrator.py` | `PanelOrchestrator` -- expert Q&A orchestration |

A persona like DetectivePersona imports EvidenceOrchestrator in its `prepare()` method, delegates the iterative evidence loop to it in `contribute()`, and then reflects on the results in `reflect()`. The Detective does not manage iteration counts, query effectiveness thresholds, or strategy pivots -- that is the orchestrator's job.

**Binder-centric artifacts.** All investigation artifacts -- hypotheses, evidence items, causal chains, challenges, LLM request/response pairs, findings, and persona contributions -- are stored in the `WorkBinder`. The binder is the single source of truth for cross-phase data. Personas do not pass large data structures between phases through function arguments; instead, each persona writes to the binder during `contribute()` and subsequent personas read from it. This design:

- Eliminates data duplication between the `InvestigationContext` fields and the actual pipeline state
- Provides full traceability (every artifact has a creator, timestamp, and phase)
- Enables the MCP server to expose binder contents for interactive exploration
- Maps naturally to the session state model in the REST API

**Prepare / Contribute / Reflect lifecycle.** Every persona follows a three-step lifecycle per phase execution:

```
prepare(context)      -- Gather resources, initialize orchestrators, review prior work
     |
     v
contribute(context)   -- Perform the persona's primary work, return Contribution
     |
     v
reflect(context)      -- Self-assess, identify uncertainties, suggest next steps
```

The `PersonaExecutor` calls these three methods in sequence, storing the `Contribution` and `Reflection` as binder artifacts. If any step fails, the executor logs the error and continues -- a failed reflection does not block the pipeline. This defensive design ensures that the pipeline progresses even when individual persona steps encounter edge cases.

---

### 2. BasePersona ABC

`BasePersona` is the abstract base class that all investigation personas inherit from. It is defined in `srcs/persona/base.py` and provides the contract that the pipeline executor, panel orchestrator, and coordinator persona all rely on.

**Properties (abstract):**

```python
@property
@abstractmethod
def metadata(self) -> Persona:
    """Get the persona's metadata from the PERSONAS registry.

    Returns:
        Persona dataclass with name, role, color, phase, etc.
    """
    ...

@property
@abstractmethod
def traits(self) -> list[str]:
    """Get the persona's personality traits.

    Returns:
        List of trait descriptors (e.g., ["methodical", "thorough"])
    """
    ...

@property
@abstractmethod
def thinking_style(self) -> str:
    """Get the persona's thinking style description.

    Returns:
        Description of thinking approach
    """
    ...
```

**Lifecycle methods (abstract):**

| Method | Signature | Returns | Purpose |
|--------|-----------|---------|---------|
| `prepare` | `async def prepare(self, context: InvestigationContext) -> None` | `None` | Initialize resources, review context |
| `contribute` | `async def contribute(self, context: InvestigationContext) -> Contribution` | `Contribution` | Perform primary work |
| `reflect` | `async def reflect(self, context: InvestigationContext) -> Reflection` | `Reflection` | Self-assess, identify uncertainties |

**Collaboration methods (abstract):**

| Method | Signature | Returns | Purpose |
|--------|-----------|---------|---------|
| `respond_to` | `async def respond_to(self, other: BasePersona, message: str) -> str` | `str` | Respond to inter-persona message |
| `critique` | `async def critique(self, contribution: Contribution) -> Critique` | `Critique` | Evaluate another persona's contribution |
| `endorse` | `async def endorse(self, contribution: Contribution) -> bool` | `bool` | Vote on whether to endorse a contribution |
| `answer_question` | `async def answer_question(self, context: QuestionContext) -> Contribution` | `Contribution` | Contribute to expert panel Q&A |

**LLM helper methods (concrete):**

These are non-abstract methods provided by `BasePersona` that wrap LLM calls with automatic artifact recording to the WorkBinder.

```python
async def _call_llm(
    self,
    context: InvestigationContext,
    prompt: str,
    system_prompt: str,
    prompt_key: str,
) -> str:
    """Call LLM and record request/response as binder artifacts.

    Args:
        context: Investigation context with LLM provider and binder
        prompt: User prompt for the LLM
        system_prompt: System prompt defining the LLM's role
        prompt_key: Identifier for this prompt type (e.g., "hypothesis_generation")

    Returns:
        Raw LLM response text

    Raises:
        RuntimeError: If LLM provider is not available
    """
```

```python
async def _call_llm_structured(
    self,
    context: InvestigationContext,
    prompt: str,
    response_model: type[T],
    system_prompt: str,
    prompt_key: str,
) -> T:
    """Call LLM with structured output and record as binder artifacts.

    Uses LLMProvider.generate_structured() with a Pydantic response model.

    Args:
        context: Investigation context with LLM provider and binder
        prompt: User prompt for the LLM
        response_model: Pydantic model class for parsing the response
        system_prompt: System prompt defining the LLM's role
        prompt_key: Identifier for this prompt type

    Returns:
        Parsed response as the specified Pydantic model

    Raises:
        RuntimeError: If LLM provider is not available
        StructuredOutputError: If response parsing fails
    """
```

Both methods follow the same pattern:

1. Call `context.require_llm()` and `context.require_binder()` to get validated dependencies
2. Record an LLM request artifact in the binder via `binder.record_llm_request()`
3. Call the LLM provider (`generate()` or `generate_structured()`)
4. Record the LLM response artifact via `binder.record_llm_response()`, including latency and parse status
5. On exception, record a failed response artifact before re-raising

This ensures every LLM interaction is fully traceable in the binder.

**Trait exhibition (concrete):**

```python
def exhibit_trait(self, trait: str, context: Any) -> str:
    """Exhibit a specific trait in response to context.

    Returns a characteristic phrase for the given trait, or empty string
    if the trait is not in the persona's trait list.

    Built-in trait phrases:
        methodical  -> "Let me proceed step by step..."
        thorough    -> "I should examine this from all angles..."
        creative    -> "What if we consider an unexpected possibility..."
        skeptical   -> "I'm not convinced. Let me challenge this..."
        analytical  -> "Looking at the data patterns..."
        integrative -> "Bringing together the various threads..."
        observant   -> "I notice something interesting here..."
    """
```

---

### 3. InvestigationContext

`InvestigationContext` is the shared state object passed to every persona lifecycle method. It is defined as a `@dataclass` in `srcs/persona/base.py` and provides both direct field access and computed properties that delegate to the WorkBinder.

**Core fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `error` | `Log` | (required) | The trigger error log being investigated |
| `context_logs` | `list[Log]` | `[]` | Surrounding log entries for temporal context |
| `binder` | `WorkBinder` | `None` | WorkBinder containing all investigation artifacts |
| `prior_knowledge` | `PriorKnowledge \| None` | `None` | Retrieved patterns and similar cases (set by Archivist) |
| `hypotheses` | `list[Hypothesis]` | `[]` | Generated hypotheses (set by Theorist) |
| `evidence` | `Evidence \| None` | `None` | Collected evidence (set by Detective) |
| `contributions` | `list[Contribution]` | `[]` | All contributions made by all personas |
| `source_files` | `list[Any] \| None` | `None` | Multi-file source data for Chronicler |

**Dependency fields (injected by executor):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `llm` | `LLMProvider \| None` | `None` | LLM provider for generating responses |
| `kb` | `KnowledgeBase \| None` | `None` | Knowledge base for pattern storage and retrieval |
| `code_index` | `CodeIndex \| None` | `None` | Code index for source code lookup |
| `source_locator` | `SourceLocator \| None` | `None` | Source locator for finding error origins |
| `config` | `InvestigationConfig \| None` | `None` | Investigation configuration settings |

**Computed properties from binder:**

These methods delegate to the WorkBinder, providing a convenient interface for personas to access typed artifacts without importing binder internals directly.

| Method | Returns | Description |
|--------|---------|-------------|
| `get_hypotheses_from_binder()` | `list[HypothesisArtifact]` | Get all hypothesis artifacts |
| `get_evidence_from_binder()` | `list[EvidenceArtifact]` | Get all evidence item artifacts |
| `get_contributions_from_binder(persona_id?, phase?)` | `list[PersonaContributionArtifact]` | Get contributions, optionally filtered |
| `get_findings_from_binder(persona_id?)` | `list[Finding]` | Get findings, optionally filtered by persona |
| `get_causal_chains_from_binder()` | `list[CausalChainArtifact]` | Get all causal chain artifacts |
| `get_challenges_from_binder()` | `list[ChallengeArtifact]` | Get all adversarial challenge artifacts |
| `get_llm_exchanges_from_binder(phase?)` | `list[tuple[LLMRequest, LLMResponse \| None]]` | Get LLM request/response pairs |
| `has_binder()` | `bool` | Check if binder is available |

All binder-delegating methods return empty lists if the binder is `None`, ensuring null safety without requiring callers to check.

**Contribution query methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_contributions_by_persona` | `(persona_id: str) -> list[Contribution]` | Filter contributions by persona ID |
| `get_contributions_by_phase` | `(phase: int) -> list[Contribution]` | Filter contributions by phase number |
| `add_contribution` | `(contribution: Contribution) -> None` | Append a contribution to the list |

**Dependency accessors with validation:**

Each `require_*` method returns the dependency if available, or raises `RuntimeError` with a descriptive message if not. This pattern prevents silent `None` propagation and gives clear error messages during development.

| Method | Returns | Raises |
|--------|---------|--------|
| `require_llm()` | `LLMProvider` | `RuntimeError("LLM provider required but not available in context")` |
| `require_kb()` | `KnowledgeBase` | `RuntimeError("KnowledgeBase required but not available in context")` |
| `require_code_index()` | `CodeIndex` | `RuntimeError("CodeIndex required but not available in context")` |
| `require_source_locator()` | `SourceLocator` | `RuntimeError("SourceLocator required but not available in context")` |
| `require_binder()` | `WorkBinder` | `RuntimeError("WorkBinder required but not available in context")` |

**Dependency injection pattern.** The `InvestigationContext` is constructed by the `PersonaExecutor` or `UnifiedPersonaExecutor` in `srcs/pipeline/persona_executor.py`. The executor's `_build_context()` method extracts all dependencies from the pipeline `inputs` dictionary:

```python
def _build_context(self, inputs: dict[str, Any], binder: WorkBinder | None) -> InvestigationContext:
    return InvestigationContext(
        error=inputs.get("trigger_error"),
        context_logs=inputs.get("context_logs", []),
        binder=binder,
        prior_knowledge=inputs.get("prior_knowledge"),
        hypotheses=inputs.get("hypotheses", []),
        evidence=inputs.get("evidence"),
        contributions=inputs.get("contributions", []),
        source_files=inputs.get("source_files"),
        llm=inputs.get("llm"),
        kb=inputs.get("kb"),
        code_index=inputs.get("code_index"),
        source_locator=inputs.get("source_locator"),
        config=inputs.get("config"),
    )
```

This means the pipeline engine controls what each persona has access to. If a persona's phase configuration does not list `llm` in its inputs, the persona will receive `llm=None` and `require_llm()` will raise -- a design-time signal that the phase configuration is incomplete.

---

### 4. Collaboration Models

All collaboration data models are defined as `@dataclass` types in `srcs/persona/base.py`. They represent the structured output of persona interactions during investigation and expert panel discussions.

**Contribution:**

The primary output of every persona's `contribute()` method.

```python
@dataclass
class Contribution:
    persona_id: str      # Identifier of the contributing persona (e.g., "theorist")
    phase: int           # Phase number when this contribution was made
    content: Any         # The actual contribution content (type varies by phase)
    confidence: float    # Persona's confidence in this contribution (0.0-1.0)
    reasoning: str       # Explanation of how the persona arrived at this contribution
```

| Field | Type | Description |
|-------|------|-------------|
| `persona_id` | `str` | Lowercase persona name: `"archivist"`, `"theorist"`, `"detective"`, etc. |
| `phase` | `int` | Phase number (-1 to 7) when the contribution was made |
| `content` | `Any` | Phase-specific content. Archivist: `dict` with patterns/locations. Theorist: `list[Hypothesis]`. Detective: `dict` with evidence stats. |
| `confidence` | `float` | 0.0 to 1.0. Each persona calculates this based on the quality of its output. |
| `reasoning` | `str` | Human-readable explanation. Used by the Coordinator in synthesis and by the PanelOrchestrator in voting. |

**Reflection:**

Produced by every persona's `reflect()` method after contributing.

```python
@dataclass
class Reflection:
    insights: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
```

| Field | Type | Description |
|-------|------|-------------|
| `insights` | `list[str]` | Key insights gained during the work (stored as `FindingType.OBSERVATION` in binder) |
| `uncertainties` | `list[str]` | Areas where the persona is uncertain (stored as `FindingType.QUESTION` in binder) |
| `suggestions` | `list[str]` | Suggestions for next steps (stored as `FindingType.RECOMMENDATION` in binder) |

**Critique:**

Produced by `critique()` during voting rounds in the PanelOrchestrator, or during adversarial review.

```python
@dataclass
class Critique:
    target_contribution: Contribution
    issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    severity: str = "MEDIUM"                          # "HIGH", "MEDIUM", "LOW"
    recommendations: list[str] = field(default_factory=list)
```

| Field | Type | Description |
|-------|------|-------------|
| `target_contribution` | `Contribution` | The contribution being critiqued |
| `issues` | `list[str]` | Identified problems or weaknesses |
| `strengths` | `list[str]` | Acknowledged strengths |
| `severity` | `str` | Overall severity: `"HIGH"`, `"MEDIUM"`, `"LOW"` |
| `recommendations` | `list[str]` | Suggested improvements |

**Discussion:**

Record of a facilitated discussion, used by `CoordinatorPersona.facilitate_discussion()` and `PanelOrchestrator._deliberation_rounds()`.

```python
@dataclass
class Discussion:
    topic: str
    participants: list[str] = field(default_factory=list)
    exchanges: list[tuple[str, str]] = field(default_factory=list)
    conclusion: str | None = None
    consensus_reached: bool = False

    def add_exchange(self, persona_id: str, message: str) -> None:
        """Add an exchange to the discussion."""
        self.exchanges.append((persona_id, message))
```

| Field | Type | Description |
|-------|------|-------------|
| `topic` | `str` | What is being discussed |
| `participants` | `list[str]` | Persona IDs involved (lowercase names) |
| `exchanges` | `list[tuple[str, str]]` | Sequence of `(persona_id, message)` tuples |
| `conclusion` | `str \| None` | Final conclusion reached, if any |
| `consensus_reached` | `bool` | Whether participants reached agreement |

**Resolution:**

Produced when the `CoordinatorPersona` mediates conflicting views via `escalate_disagreement()`.

```python
@dataclass
class Resolution:
    disagreement_summary: str
    resolution_type: str      # "consensus", "majority", "coordinator_decision"
    resolution: str
    dissenting_views: list[str] = field(default_factory=list)
```

| Field | Type | Description |
|-------|------|-------------|
| `disagreement_summary` | `str` | Description of what was disagreed upon |
| `resolution_type` | `str` | How it was resolved: `"consensus"`, `"majority"`, `"coordinator_decision"` |
| `resolution` | `str` | The actual resolution text |
| `dissenting_views` | `list[str]` | Views that were not adopted |

**Summary:**

Used by `CoordinatorPersona.synthesize_contributions()` to aggregate panel output.

```python
@dataclass
class Summary:
    key_points: list[str] = field(default_factory=list)
    areas_of_agreement: list[str] = field(default_factory=list)
    areas_of_disagreement: list[str] = field(default_factory=list)
    overall_assessment: str = ""
```

| Field | Type | Description |
|-------|------|-------------|
| `key_points` | `list[str]` | Main points extracted from contributions (one per persona) |
| `areas_of_agreement` | `list[str]` | Where multiple personas agree (e.g., "Multiple personas have high confidence") |
| `areas_of_disagreement` | `list[str]` | Where personas disagree (e.g., "Some personas have low confidence") |
| `overall_assessment` | `str` | Coordinator's synthesis statement |

---

### 5. Orchestration Layer

The orchestration layer lives in `srcs/persona/orchestration/` and provides the execution mechanics for the two most complex personas: the Archivist (Phase 0) and the Detective (Phase 2). Each orchestrator encapsulates iteration logic, tool invocation, strategy management, and binder artifact recording -- concerns that are too complex to embed directly in persona `contribute()` methods.

#### 5.1 RetrievalOrchestrator

**File:** `srcs/persona/orchestration/retrieval_orchestrator.py`

Manages prior knowledge retrieval for the `ArchivistPersona`. Called from `ArchivistPersona.contribute()`.

```python
class RetrievalOrchestrator:
    def __init__(
        self,
        kb: KnowledgeBase,
        source_roots: list[Path] | None = None,
        code_index: CodeIndex | None = None,
        chroma_store: ChromaStore | None = None,
        llm_provider: LLMProvider | None = None,
    ): ...

    async def retrieve(
        self,
        error: Log,
        context: list[Log],
        binder: WorkBinder | None = None,
    ) -> PriorKnowledge: ...
```

**Retrieval pipeline within `retrieve()`:**

| Step | Description | Output |
|------|-------------|--------|
| 1. Pattern matching | Query KnowledgeBase for matching error patterns | `matched_patterns` |
| 2. Similar investigation lookup | Semantic search via ChromaDB for similar past cases | `similar_investigations` |
| 3. Source location finding | Use `SourceLocator` to find the error's origin in source code | `source_locations` |
| 4. Code hint extraction | Extract causal comments, error messages, diagnostic hints from source | `recommended_hypotheses` |
| 5. Dataflow tracing | Trace variable dataflow for upstream investigation leads | `recommended_queries` |
| 6. Call graph enrichment | Fetch call graphs with function bodies, generate LLM summaries and ASCII diagrams | enriched `source_locations` |
| 7. Numeric value parsing | LLM-parse timestamps, timeouts, durations from error message | `ParsedErrorContext` |

**Dependencies used:**

| Dependency | Role |
|------------|------|
| `KnowledgeBase` | Pattern matching (`get_prior_knowledge`), similar case lookup |
| `SourceLocator` | Error origin finding in source tree |
| `CodeIndex` | Function/class lookup, call graph retrieval |
| `ChromaStore` | Semantic similarity search |
| `LLMProvider` | Call graph summarization, hint interpretation, numeric parsing |
| `CodeHintExtractor` | Extract diagnostic comments from source code |
| `DataflowTracer` | Trace variable dataflow paths |
| `NumericExtractor` | Extract and classify numeric values |
| `ArchivistTools` | Call graph bodies and diagram generation |

#### 5.2 EvidenceOrchestrator

**File:** `srcs/persona/orchestration/evidence_orchestrator.py`

Manages the iterative evidence seeking loop for the `DetectivePersona`. Called from `DetectivePersona.contribute()`.

```python
class EvidenceOrchestrator:
    def __init__(
        self,
        llm: LLMProvider,
        kb: KnowledgeBase,
        max_iterations: int = 10,
        investigation_tools: InvestigationTools | None = None,
        code_tools: CodeTools | None = None,
        pattern_tools: PatternTools | None = None,
        forensics_tools: CodeForensicsTools | None = None,
        default_function_source_length: int = 2000,
        config: EvidenceConfig | None = None,
    ): ...

    async def seek(
        self,
        hypotheses: list[Hypothesis],
        initial_evidence: Evidence,
        prior: PriorKnowledge,
        binder: WorkBinder | None = None,
    ) -> tuple[Evidence, list[Hypothesis]]: ...
```

**Evidence seeking loop within `seek()`:**

```
for iteration in range(max_iterations):
    1. Ask LLM what queries to run next (based on current hypotheses + evidence)
    2. Apply strategy: skip ineffective query types, prioritize by mode
    3. Execute queries using tool classes (log search, code lookup, etc.)
    4. Score evidence relevance to hypotheses (LLM or regex fallback)
    5. Update hypothesis scores based on supporting/contradicting evidence
    6. Record evidence items and hypothesis updates in binder
    7. Check stopping criteria (sufficient discrimination, all queries exhausted)
```

**Adaptive strategy mechanics:**

| Trigger | Strategy Change |
|---------|----------------|
| Context logs empty or minimal | Start in `code_centric` mode |
| 2+ log query types have consecutive failure >= 3 | Pivot from `balanced` to `code_centric` |
| Log queries return rich results | Stay in `balanced` mode |
| Code queries consistently fail | May pivot to `log_centric` |

#### 5.3 EvidenceStrategy

**File:** `srcs/persona/orchestration/strategy.py`

Tracks query effectiveness and manages the evidence seeking mode.

```python
@dataclass
class EvidenceStrategy:
    has_context_logs: bool = True
    context_log_count: int = 0
    query_stats: dict[str, QueryEffectiveness] = field(default_factory=dict)
    mode: str = "balanced"  # "balanced", "code_centric", "log_centric"

    # Configurable thresholds
    consecutive_failure_limit: int = 3
    min_success_rate: float = 0.1
    min_attempts_for_rate: int = 5

    LOG_QUERY_TYPES = {"log_search", "component_logs", "time_window"}
    CODE_QUERY_TYPES = {"function_lookup", "class_lookup", "code_search", "log_source"}
```

| Method | Signature | Purpose |
|--------|-----------|---------|
| `record_query_result` | `(query_type: str, found: bool) -> None` | Record success/failure, trigger strategy update |
| `should_skip_query` | `(query_type: str) -> bool` | Check if query type should be skipped |
| `prioritize_queries` | `(queries: list[dict]) -> list[dict]` | Reorder queries based on current mode |

#### 5.4 QueryEffectiveness

**File:** `srcs/persona/orchestration/strategy.py`

Tracks per-query-type statistics for adaptive strategy decisions.

```python
@dataclass
class QueryEffectiveness:
    query_type: str
    attempts: int = 0
    successes: int = 0
    consecutive_failures: int = 0
    consecutive_failure_limit: int = 3
    min_success_rate: float = 0.1
    min_attempts_for_rate: int = 5

    @property
    def success_rate(self) -> float: ...

    @property
    def is_effective(self) -> bool:
        """Returns False if:
        - consecutive_failures >= consecutive_failure_limit (default: 3), OR
        - attempts >= min_attempts_for_rate AND success_rate < min_success_rate
        """
        ...
```

#### 5.5 LLMRelevanceAssessor

**File:** `srcs/persona/orchestration/relevance.py`

Scores evidence relevance to hypotheses using LLM with regex fallback.

```python
class LLMRelevanceAssessor:
    def __init__(
        self,
        llm: LLMProvider | None = None,
        use_llm: bool | None = None,       # Auto-detects if None
    ): ...

    async def assess(
        self,
        evidence: EvidenceItem,
        hypothesis: Hypothesis,
        binder: WorkBinder | None = None,
    ) -> float:
        """Returns relevance score from -1.0 (contradicts) to 1.0 (supports)."""
        ...
```

**Assessment pipeline:**

1. If LLM is available and `use_llm` is True, call `_llm_assess()` which uses `generate_structured()` with `RelevanceAssessment` Pydantic model
2. If LLM call fails or LLM is unavailable, fall through to `_regex_assess()`
3. Regex assessment uses pattern matching for common hypothesis categories: race conditions, configuration issues, resource exhaustion, network/timeout, null pointer, exception handling
4. Records LLM exchanges to binder when available

**RelevanceAssessment model (for LLM structured output):**

```python
class RelevanceAssessment(BaseModel):
    relevance_score: float         # -1.0 to 1.0
    reasoning: str
    supports: bool
    contradicts: bool
    key_terms_matched: list[str]
```

---

### 6. Capability Registry

The capability registry (`srcs/persona/capabilities.py`) maps abstract capability names to concrete tool methods. This allows personas to declare what capabilities they need without knowing the tool class hierarchy.

**Capability class:**

```python
class Capability:
    name: str            # Unique capability identifier (e.g., "log_search")
    description: str     # Human-readable description
    tool_class: str      # Class name that provides this capability (e.g., "InvestigationTools")
    method_name: str     # Method name on the tool class (e.g., "search_logs")
```

**Built-in capabilities (BUILTIN_CAPABILITIES):**

| Category | Capability Name | Tool Class | Method |
|----------|----------------|------------|--------|
| Log/Investigation | `log_search` | `InvestigationTools` | `search_logs` |
| Log/Investigation | `similar_investigation_lookup` | `InvestigationTools` | `lookup_similar_cases` |
| Log/Investigation | `time_window_search` | `InvestigationTools` | `get_logs_in_window` |
| Code | `code_lookup` | `CodeTools` | `lookup_function` |
| Code | `class_lookup` | `CodeTools` | `lookup_class` |
| Code | `code_search` | `CodeTools` | `search_symbols` |
| Code Forensics | `function_trace` | `CodeForensicsTools` | `trace_variable` |
| Code Forensics | `dataflow_analysis` | `CodeForensicsTools` | `find_error_path` |
| Code Forensics | `caller_chain` | `CodeForensicsTools` | `get_caller_chain` |
| Pattern | `pattern_lookup` | `PatternTools` | `lookup_error_pattern` |
| Pattern | `accuracy_check` | `PatternTools` | `get_historical_accuracy` |
| Binder (Read) | `binder_list` | `BinderTools` | `list_artifacts` |
| Binder (Read) | `binder_get` | `BinderTools` | `get_artifact` |
| Binder (Read) | `binder_search` | `BinderTools` | `search_binder` |
| Binder (Read) | `binder_related` | `BinderTools` | `get_related_artifacts` |
| Binder (Read) | `binder_history` | `BinderTools` | `get_artifact_history` |
| Binder (Read) | `binder_stats` | `BinderTools` | `get_binder_stats` |
| Binder (Write) | `binder_add_finding` | `BinderTools` | `add_finding` |
| Binder (Write) | `binder_annotate` | `BinderTools` | `annotate_artifact` |
| Binder (Write) | `binder_update` | `BinderTools` | `update_artifact` |
| Binder (Code) | `binder_expand_call_graph` | `BinderTools` | `expand_call_graph` |
| Binder (Code) | `binder_get_function` | `BinderTools` | `get_function_source` |
| Binder (Code) | `binder_get_class` | `BinderTools` | `get_class_definition` |

**CapabilityRegistry API:**

```python
class CapabilityRegistry:
    def __init__(self) -> None:
        """Initialize registry with BUILTIN_CAPABILITIES."""

    def register_capability(self, capability: Capability) -> None:
        """Register a new capability definition."""

    def register_tool(self, tool_class_name: str, instance: Any) -> None:
        """Register a tool instance for capability resolution."""

    def get_capability(self, name: str) -> Capability | None:
        """Get capability definition by name."""

    def resolve_capability(self, name: str) -> Callable[..., Coroutine] | None:
        """Resolve a capability to its async method implementation.
        Returns None if capability or tool instance not registered."""

    def list_capabilities(self) -> list[str]:
        """List all registered capability names."""

    def get_capabilities_for_persona(
        self, capability_names: list[str]
    ) -> dict[str, Any]:
        """Get resolved capabilities for a persona.
        Returns dict of capability_name -> resolved async method."""
```

**Global registry and convenience functions:**

```python
def get_capability_registry() -> CapabilityRegistry:
    """Get the global singleton registry instance."""

def register_tools(
    investigation_tools: InvestigationTools | None = None,
    code_tools: CodeTools | None = None,
    forensics_tools: CodeForensicsTools | None = None,
    pattern_tools: PatternTools | None = None,
    binder_tools: BinderTools | None = None,
) -> None:
    """Register tool instances with the global registry."""
```

The global `register_tools()` function is called during server initialization to make all tool implementations available for capability resolution. The `BINDER_CAPABILITIES` list groups all binder-related capability names for universal persona access -- every persona can read from and write to the binder.

---

### 7. Session Integration

This section describes how the persona system maps to the session-based REST API architecture defined in [Chapter 1 of the Agentic REST API Design Document](agentic-rest-service-design-ch1-architecture.md).

**WorkBinder as the session artifact store.** Within a single investigation session, the `WorkBinder` is the authoritative store for all artifacts produced by personas. The mapping between session state fields and binder artifact types is:

| Session State Field | Binder Artifact Type | Written By | Read By |
|--------------------|-----------------------|------------|---------|
| `state.findings` | `ArtifactType.FINDING` | All personas (via `reflect()`) | `get_findings_summary` tool |
| `state.hypotheses` | `ArtifactType.HYPOTHESIS` | Theorist, Detective (updates) | Logician, Skeptic, Judge, Synthesizer |
| `state.tool_history` | `ArtifactType.LLM_REQUEST`, `ArtifactType.LLM_RESPONSE` | All LLM-using personas | Debugging, audit |
| -- | `ArtifactType.EVIDENCE` | Detective | Logician, Judge, Synthesizer |
| -- | `ArtifactType.CAUSAL_CHAIN` | Logician | Skeptic, Judge, Synthesizer |
| -- | `ArtifactType.CHALLENGE` | Skeptic | Judge, Synthesizer |
| -- | `ArtifactType.PERSONA_CONTRIBUTION` | All personas | Coordinator, Synthesizer |
| -- | `ArtifactType.LOG_BUNDLE` | Chronicler | Archivist |

**Persona lifecycle within a session.** When the `investigate` or `investigate_stream` tool is invoked on a session, the following sequence occurs:

1. The API handler retrieves the session from the session store
2. A `WorkBinder` is created (or retrieved from the session's existing investigation)
3. The `PipelineEngine` executes each phase via `UnifiedPersonaExecutor`
4. Each executor calls `_build_context()` to create an `InvestigationContext` from the pipeline inputs, injecting the binder and all dependencies
5. The persona's `prepare()`, `contribute()`, and `reflect()` methods execute within this context
6. The executor's `_store_contribution()` and `_store_reflection()` methods write artifacts to the binder
7. The executor's `_map_outputs()` method converts the persona's `Contribution.content` to typed pipeline outputs (`prior_knowledge`, `hypotheses`, `evidence`, etc.)
8. After all phases complete, the investigation result is stored in the session state

**Session state visibility.** The session's `GET /api/v1/agent/sessions/{id}` endpoint returns the accumulated state, which includes all findings stored by persona reflections, all hypotheses from the Theorist and Detective updates, and the complete tool invocation history. This means a client can observe the investigation's progress at any point.

---

### 8. SSE Event Mapping

When `investigate_stream` is invoked, each persona phase emits Server-Sent Events that the client can consume in real time. The mapping from persona phases to SSE events is defined by the callback system described in [Chapter 5 of the Agentic REST API Design Document](agentic-rest-service-design-ch5-pipeline-admin-tools.md).

**Phase-to-SSE mapping:**

| Phase | Persona | SSE Events Emitted |
|-------|---------|-------------------|
| -1 | Chronicler | `phase_start`, `phase_progress` (per-file), `phase_complete` |
| 0 | Archivist | `phase_start`, `data_query` (pattern/similarity lookups), `data_result`, `llm_request` (summarization), `llm_response`, `phase_complete` |
| 1 | Theorist | `phase_start`, `llm_request`, `llm_response`, `phase_item` (per hypothesis), `phase_complete` |
| 2 | Detective | `phase_start`, `llm_request`/`llm_response` (per iteration), `data_query`/`data_result` (per evidence query), `phase_progress` (iteration count), `phase_complete` |
| 3 | Logician | `phase_start`, `llm_request`, `llm_response`, `phase_item` (per chain), `phase_complete` |
| 4 | Skeptic | `phase_start`, `llm_request`, `llm_response`, `phase_item` (per challenge), `phase_complete` |
| 5 | Judge | `phase_start`, `llm_request`, `llm_response`, `phase_complete` |
| 6 | Synthesizer | `phase_start`, `llm_request`, `llm_response`, `phase_complete` |
| 7 | Learner | `phase_start`, `llm_request`, `llm_response`, `phase_complete` |
| -- | -- | `complete` (full `InvestigationResult`) or `error` |

**SSE event type reference:**

| SSE Event Type | Source Callback | Payload Fields | Description |
|----------------|----------------|----------------|-------------|
| `phase_start` | `PhaseEvent(event_type="start")` | `phase`, `phase_name`, `message` | Persona phase begins execution |
| `phase_progress` | `PhaseEvent(event_type="progress")` | `phase`, `phase_name`, `data`, `message` | Progress within phase (e.g., iteration count) |
| `phase_item` | `PhaseEvent(event_type="item")` | `phase`, `phase_name`, `data` | Individual item produced (hypothesis, chain, challenge) |
| `phase_complete` | `PhaseEvent(event_type="complete")` | `phase`, `phase_name`, `data`, `message` | Persona phase finishes |
| `llm_request` | `LLMEvent(event_type="request")` | `phase`, `model_name`, `prompt_summary` | LLM prompt sent |
| `llm_response` | `LLMEvent(event_type="response")` | `phase`, `model_name`, `tokens_used`, `parse_success` | LLM response received |
| `data_query` | `DataRetrievalEvent(event_type="query")` | `phase`, `source`, `operation`, `query_params` | KB/tool query initiated |
| `data_result` | `DataRetrievalEvent(event_type="result")` | `phase`, `source`, `operation`, `result_count` | KB/tool query completed |
| `complete` | Pipeline finished | `session_id`, `investigation_id`, `outcome`, `result_url` | Full investigation complete |
| `error` | Pipeline exception | `code`, `message`, `details` | Unrecoverable error |

**Detective-specific SSE behavior.** Phase 2 is unique because the `EvidenceOrchestrator` runs up to 10 iterations. Each iteration emits:
- `llm_request` / `llm_response` for query generation
- One or more `data_query` / `data_result` pairs for evidence retrieval
- `phase_progress` with iteration count and evidence stats

This gives clients real-time visibility into the Detective's iterative search process, which is the longest-running phase.

---

### 9. Cross-Phase Artifact Wiring

Personas do not operate in isolation. Each phase's output feeds into subsequent phases through the shared `InvestigationContext` and `WorkBinder`. The following diagram shows the primary data flows between personas:

```
Phase -1: Chronicler
    |
    |  LOG_BUNDLE artifact (primary error, clues, suggested searches)
    v
Phase 0: Archivist
    |
    |  prior_knowledge: PriorKnowledge
    |    - matched_patterns
    |    - similar_investigations
    |    - source_locations (with call graphs)
    |    - recommended_hypotheses (including Chronicler clues)
    |    - recommended_queries
    |    - resolution_digest
    |    - configuration_context
    |    - diagnostic_history
    v
Phase 1: Theorist
    |
    |  hypotheses: list[Hypothesis]
    |    - Tiered scoring: code_hints (0.7-0.85) > patterns (0.6-0.8)
    |      > similar_cases (0.3-0.5) > LLM (<=0.3) > alternatives (0.1)
    v
Phase 2: Detective
    |
    |  evidence: Evidence (items dict, by-type breakdown)
    |  hypotheses: list[Hypothesis] (re-ranked with evidence linkage)
    |    - supporting_evidence_ids per hypothesis
    |    - contradicting_evidence_ids per hypothesis
    |  evidence_gap_analysis: EvidenceGapAnalysis
    |  evidence_quality_score: EvidenceQualityScore
    v
Phase 3: Logician
    |
    |  causal_chains: list[CausalChain]
    |    - Each chain links to a hypothesis_id
    |    - Steps with evidence_ids, claims, mechanisms
    |    - logical_validity and evidence_coverage scores
    v
Phase 4: Skeptic
    |
    |  challenges: list[Challenge]
    |    - challenge_type, content, severity
    |    - requires_response flag
    v
Phase 5: Judge
    |
    |  outcome: InvestigationOutcome
    |    - CONFIDENT, PROBABLE, UNCERTAIN, CONTRADICTORY, INSUFFICIENT
    v
Phase 6: Synthesizer
    |
    |  result: InvestigationResult
    |    - root_cause (for CONFIDENT/PROBABLE)
    |    - viable_hypotheses (for UNCERTAIN)
    |    - calibrated confidence
    |    - evidence_summary, recommendations
    v
Phase 7: Learner
    |
    |  patterns: list (extracted patterns stored in KnowledgeBase)
    v
    (end)
```

**Key cross-phase dependencies:**

| Consumer Phase | Producer Phase | Data Consumed | Purpose |
|---------------|---------------|---------------|---------|
| Archivist (0) | Chronicler (-1) | `LOG_BUNDLE` artifact | Enrich prior knowledge with multi-file clues |
| Theorist (1) | Archivist (0) | `prior_knowledge` | Seed hypotheses from patterns, code hints, similar cases |
| Detective (2) | Theorist (1) | `hypotheses` | Know what to seek evidence for |
| Detective (2) | Archivist (0) | `prior_knowledge` | Use recommended queries as starting points |
| Logician (3) | Detective (2) | `evidence`, `hypotheses` | Build causal chains from evidence-linked hypotheses |
| Skeptic (4) | Logician (3) | `causal_chains` | Challenge chain validity and assumptions |
| Skeptic (4) | Detective (2) | `evidence` | Challenge evidence quality and coverage |
| Judge (5) | All prior phases | `hypotheses`, `evidence`, `causal_chains`, `challenges` | Assess overall evidence sufficiency |
| Synthesizer (6) | Judge (5) | `outcome` | Determine report structure |
| Synthesizer (6) | Detective (2) | `evidence` | Cite evidence in final report |
| Synthesizer (6) | Logician (3) | `causal_chains` | Include causal reasoning |
| Learner (7) | Synthesizer (6) | `result` | Extract patterns from conclusion |

---

### 10. Enhanced Artifacts Overview

Several personas produce enhanced artifacts beyond their primary outputs. These artifacts provide deeper analytical detail for downstream consumers and for the final investigation report.

**Archivist enhanced artifacts (Phase 0):**

| Artifact | Model | Source | Description |
|----------|-------|--------|-------------|
| `ResolutionDigest` | `srcs/models/knowledge.py` | `ArchivistPersona._extract_resolutions()` | Resolution details from similar investigations -- what specifically fixed similar cases |
| `ConfigurationContext` | `srcs/models/knowledge.py` | `ArchivistPersona._analyze_configuration()` | Configuration parameters extracted from logs, compared to successful cases |
| `DiagnosticHistory` | `srcs/models/knowledge.py` | `ArchivistPersona._get_diagnostic_history()` | Historical success rate for this error type signature |

```python
class ResolutionDigest(BaseModel):
    investigation_id: str
    root_cause: str | None = None
    resolution_action: str | None = None     # "Increased timeout from 5s to 15s"
    resolution_category: str = "unknown"     # config_change, code_fix, hardware, workaround
    resolution_success: bool | None = None
    confidence: float = 0.0
    applicability_notes: str = ""

class ConfigurationContext(BaseModel):
    component: str
    relevant_params: list[ConfigParam] = []
    config_from_similar_successes: dict[str, str] = {}
    deviation_flags: list[str] = []

class DiagnosticHistory(BaseModel):
    error_signature: str
    total_occurrences: int = 0
    resolved_count: int = 0
    resolution_rate: float = 0.0
    avg_confidence: float = 0.0
    common_root_causes: list[tuple[str, float]] = []
    avg_time_to_resolve: str | None = None
```

These artifacts are attached to the `PriorKnowledge` object (`prior.resolution_digest`, `prior.configuration_context`, `prior.diagnostic_history`) and propagated through the pipeline for use by the Theorist, Detective, and Synthesizer.

**Detective enhanced artifacts (Phase 2):**

| Artifact | Model | Source | Description |
|----------|-------|--------|-------------|
| `EvidenceGapAnalysis` | `srcs/models/investigation.py` | `DetectivePersona._analyze_evidence_gaps()` | Identifies what evidence is missing for each hypothesis |
| `EvidenceQualityScore` | `srcs/models/investigation.py` | `DetectivePersona._calculate_quality_score()` | Multi-dimensional evidence quality assessment |
| `AlternativeInvestigationPaths` | `srcs/models/investigation.py` | `DetectivePersona._suggest_alternative_paths()` | Suggested alternative approaches when current evidence is insufficient |

```python
class EvidenceGap(BaseModel):
    hypothesis_id: str
    hypothesis_description: str
    gap_type: str                      # "no_evidence", "no_supporting", "no_contradicting", "weak_only"
    missing_evidence_types: list[str]  # ["log", "code", "config"]
    suggested_queries: list[str]
    severity: str                      # "high", "medium", "low"

class EvidenceGapAnalysis(BaseModel):
    gaps: list[EvidenceGap] = []
    fully_covered_hypotheses: int = 0
    partially_covered_hypotheses: int = 0
    uncovered_hypotheses: int = 0
    most_critical_gap: EvidenceGap | None = None
    recommended_next_queries: list[str] = []

class EvidenceQualityScore(BaseModel):
    overall_score: float = 0.0                     # Weighted average (0.0-1.0)
    strength_score: float = 0.0                    # Weight: 0.3
    diversity_score: float = 0.0                   # Weight: 0.2
    coverage_score: float = 0.0                    # Weight: 0.3
    discrimination_score: float = 0.0              # Weight: 0.2
    evidence_types_present: list[str] = []
    evidence_types_missing: list[str] = []
    hypotheses_with_evidence: int = 0
    hypotheses_without_evidence: int = 0
    has_strong_discriminating_evidence: bool = False
    has_code_and_log_evidence: bool = False
    top_hypothesis_supported: bool = False
```

**Quality score component weights:**

| Component | Weight | Calculation |
|-----------|--------|-------------|
| `strength_score` | 0.3 | `(strong * 1.0 + moderate * 0.5) / total` |
| `diversity_score` | 0.2 | `present_types / expected_types` (expected: log, code, config, function) |
| `coverage_score` | 0.3 | `hypotheses_with_evidence / total_hypotheses` |
| `discrimination_score` | 0.2 | Evidence that supports some hypotheses AND contradicts others |

These enhanced artifacts are included in the Detective's `Contribution.content` dictionary and are accessible to the Logician, Skeptic, Judge, and Synthesizer for informed downstream reasoning. The `EvidenceGapAnalysis` is particularly valuable for the Judge's insufficiency determination, and the `EvidenceQualityScore` informs the Synthesizer's confidence calibration.

---

> [Table of Contents](agentic-persona-library.md) | [Next: Pipeline Personas →](agentic-persona-library-ch2-pipeline-personas.md)
