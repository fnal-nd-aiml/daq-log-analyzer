> **Agentic Persona Library** | [← Prompt Architecture](agentic-persona-library-ch6-prompt-architecture.md) | [Table of Contents](agentic-persona-library.md)

---

# Chapter 7: Testing & Validation

The persona library spans prompt loading, persona lifecycle, orchestrator coordination, expert panel Q&A, SSE streaming, and cross-phase artifact wiring. Each layer requires distinct testing strategies. This chapter documents the patterns, fixtures, and mocks needed to test the complete persona system.

---

## 7.1 Per-Persona Unit Tests

Each persona's unit tests verify the three-phase lifecycle: `prepare`, `contribute`, and `reflect`. The test pattern is identical across all personas, with the mock requirements varying based on what each persona accesses.

### Standard Test Pattern

```python
# tests/unit/persona/test_{persona}_persona.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from srcs.persona.base import Contribution, Reflection
from srcs.persona.{persona} import {Persona}Persona


@pytest.mark.asyncio
async def test_{persona}_lifecycle():
    """Test prepare/contribute/reflect lifecycle."""
    persona = {Persona}Persona()
    context = create_test_context(
        error=mock_log_entry(),
        hypotheses=[mock_hypothesis()],
        evidence=mock_evidence(),
        llm=AsyncMock(spec=LLMProvider),
        kb=AsyncMock(spec=KnowledgeBase),
        binder=mock_work_binder(),
    )

    # Prepare -- persona initializes internal state
    await persona.prepare(context)

    # Contribute -- persona produces its phase output
    contribution = await persona.contribute(context)
    assert isinstance(contribution, Contribution)
    assert contribution.persona_id == "{persona_id}"
    assert 0.0 <= contribution.confidence <= 1.0
    assert contribution.content is not None

    # Reflect -- persona reviews its own output
    reflection = await persona.reflect(context)
    assert isinstance(reflection, Reflection)
```

### Mock Requirements Per Persona

Each persona accesses different subsets of the investigation infrastructure. The following table lists the mocks that must be configured for each persona's unit tests to pass:

| Persona | Required Mocks | Reason |
|---------|---------------|--------|
| Chronicler | `LLMProvider`, source files list | Analyzes merged multi-file log timeline via LLM |
| Archivist | `LLMProvider`, `KnowledgeBase`, `ChromaStore`, `CodeIndex`, `SourceLocator`, `WorkBinder` | Queries patterns, similar cases, source locations, and generates call graph summaries |
| Theorist | `LLMProvider`, `WorkBinder` | Generates hypotheses via LLM structured output, reads prior knowledge from binder |
| Detective | `LLMProvider`, `KnowledgeBase`, `WorkBinder`, (`EvidenceOrchestrator`) | Iteratively seeks evidence using tool queries, tracks analyzed functions |
| Logician | `LLMProvider`, `WorkBinder` | Builds causal chains for each hypothesis, reads hypotheses and evidence from binder |
| Skeptic | `LLMProvider`, `WorkBinder` | Reviews chains and challenges conclusions, reads chains and evidence from binder |
| Judge | `LLMProvider`, `WorkBinder` | Assesses outcome based on all accumulated artifacts, reads quality metrics from binder |
| Synthesizer | `LLMProvider`, `WorkBinder`, `KnowledgeBase` | Generates final report, reads all upstream artifacts from binder, stores results |
| Learner | `LLMProvider`, `KnowledgeBase`, `WorkBinder` | Extracts patterns from completed investigation, stores patterns in knowledge base |

### Verifying Contribution Content

Each persona produces a distinct contribution type. Tests should validate the structure beyond just `isinstance`:

```python
# Theorist: contribution contains hypotheses
@pytest.mark.asyncio
async def test_theorist_contributes_hypotheses():
    """Theorist should produce ranked hypotheses."""
    persona = TheoristPersona()
    llm = mock_llm_structured(
        HypothesisResponse,
        {"hypotheses": [
            {"description": "Hardware link failure", "category": "hardware",
             "prior": 0.7, "confirming_evidence": "...", "refuting_evidence": "..."},
        ]},
    )
    context = create_test_context(llm=llm, binder=mock_work_binder())

    await persona.prepare(context)
    contribution = await persona.contribute(context)

    assert contribution.persona_id == "theorist"
    assert len(contribution.content.hypotheses) >= 1
    assert all(0.0 <= h.prior <= 1.0 for h in contribution.content.hypotheses)


# Detective: contribution contains evidence items
@pytest.mark.asyncio
async def test_detective_contributes_evidence():
    """Detective should gather discriminating evidence."""
    persona = DetectivePersona()
    llm = mock_llm_generate('{"queries": [{"query_type": "log_search", ...}]}')
    context = create_test_context(
        llm=llm,
        binder=mock_work_binder_with_hypotheses(),
    )

    await persona.prepare(context)
    contribution = await persona.contribute(context)

    assert contribution.persona_id == "detective"
    assert contribution.content.evidence_count >= 0


# Judge: contribution contains outcome determination
@pytest.mark.asyncio
async def test_judge_contributes_outcome():
    """Judge should render an outcome verdict."""
    persona = JudgePersona()
    llm = mock_llm_structured(
        OutcomeAssessment,
        {"outcome": "PROBABLE", "confidence": 0.65,
         "criteria_met": ["strong_evidence"], "criteria_not_met": []},
    )
    context = create_test_context(
        llm=llm,
        binder=mock_work_binder_with_all_artifacts(),
    )

    await persona.prepare(context)
    contribution = await persona.contribute(context)

    assert contribution.content.outcome in [
        "CONFIDENT", "PROBABLE", "UNCERTAIN", "CONTRADICTORY", "INSUFFICIENT"
    ]
```

---

## 7.2 Orchestrator Tests

### EvidenceOrchestrator Tests

The `EvidenceOrchestrator` drives the Detective's iterative evidence-seeking loop. Tests verify iteration control, adaptive strategy switching, and query effectiveness tracking.

```python
# tests/unit/persona/test_evidence_orchestrator.py

@pytest.mark.asyncio
async def test_evidence_orchestrator_seeks_evidence():
    """Orchestrator should execute at least one query iteration."""
    orchestrator = EvidenceOrchestrator(llm=mock_llm, tools=mock_tools)
    result = await orchestrator.seek(hypotheses, existing_evidence)
    assert result.iterations_completed >= 1
    assert result.evidence_items_found >= 0

@pytest.mark.asyncio
async def test_evidence_orchestrator_adaptive_strategy():
    """Orchestrator should switch from code-centric to log-centric when appropriate."""
    orchestrator = EvidenceOrchestrator(
        llm=mock_llm, tools=mock_tools, mode="code_only"
    )
    result = await orchestrator.seek(hypotheses, existing_evidence)
    assert result.strategy_used in ["code_centric", "log_centric", "balanced"]

@pytest.mark.asyncio
async def test_evidence_orchestrator_query_effectiveness():
    """Orchestrator should track which query types are effective."""
    orchestrator = EvidenceOrchestrator(llm=mock_llm, tools=mock_tools)
    result = await orchestrator.seek(hypotheses, existing_evidence)
    assert isinstance(result.query_effectiveness, dict)
    # Effective queries should have positive scores
    for query_type, score in result.query_effectiveness.items():
        assert isinstance(score, float)

@pytest.mark.asyncio
async def test_evidence_orchestrator_max_iterations():
    """Orchestrator should stop after max_iterations."""
    orchestrator = EvidenceOrchestrator(
        llm=mock_llm, tools=mock_tools, max_iterations=3
    )
    result = await orchestrator.seek(hypotheses, existing_evidence)
    assert result.iterations_completed <= 3

@pytest.mark.asyncio
async def test_evidence_orchestrator_fallback_queries():
    """Orchestrator should generate fallback queries when LLM returns none."""
    llm = mock_llm_generate('{"queries": []}')  # Empty response
    orchestrator = EvidenceOrchestrator(llm=llm, tools=mock_tools)
    result = await orchestrator.seek(hypotheses, existing_evidence)
    # Should still attempt some queries via fallback
    assert result.iterations_completed >= 1
```

### RetrievalOrchestrator Tests

The `RetrievalOrchestrator` drives the Archivist's prior knowledge retrieval. Tests verify knowledge base queries, source location finding, and code hint extraction.

```python
# tests/unit/persona/test_retrieval_orchestrator.py

@pytest.mark.asyncio
async def test_retrieval_orchestrator_retrieves_prior():
    """Orchestrator should query knowledge base for matching patterns."""
    kb = AsyncMock(spec=KnowledgeBase)
    kb.match_patterns.return_value = [mock_pattern(confidence=0.8)]
    orchestrator = RetrievalOrchestrator(kb=kb, code_index=mock_index)
    result = await orchestrator.retrieve(error=mock_error)
    assert len(result.matched_patterns) >= 1

@pytest.mark.asyncio
async def test_retrieval_orchestrator_finds_source():
    """Orchestrator should locate error source in code index."""
    code_index = MagicMock()
    code_index.find_error_source.return_value = [
        {"file": "BoardReader.cc", "line": 245, "function": "getNext_"}
    ]
    orchestrator = RetrievalOrchestrator(kb=mock_kb, code_index=code_index)
    result = await orchestrator.retrieve(error=mock_error)
    assert len(result.source_locations) >= 1

@pytest.mark.asyncio
async def test_retrieval_orchestrator_extracts_code_hints():
    """Orchestrator should extract code hints from source locations."""
    code_index = MagicMock()
    code_index.find_error_source.return_value = [
        {"file": "BoardReader.cc", "line": 245, "function": "getNext_",
         "code_hints": ["This is most likely caused by a timeout on the hardware link"]}
    ]
    orchestrator = RetrievalOrchestrator(kb=mock_kb, code_index=code_index)
    result = await orchestrator.retrieve(error=mock_error)
    assert len(result.code_hints) >= 1

@pytest.mark.asyncio
async def test_retrieval_orchestrator_handles_empty_kb():
    """Orchestrator should handle empty knowledge base gracefully."""
    kb = AsyncMock(spec=KnowledgeBase)
    kb.match_patterns.return_value = []
    kb.find_similar_investigations.return_value = []
    orchestrator = RetrievalOrchestrator(kb=kb, code_index=mock_index)
    result = await orchestrator.retrieve(error=mock_error)
    assert result.matched_patterns == []
    assert result.similar_investigations == []
```

---

## 7.3 Collaboration Tests

Persona collaboration -- critique, endorsement, response, and discussion -- is tested through the interaction protocol defined in `srcs/persona/base.py`.

```python
# tests/unit/persona/test_collaboration.py

@pytest.mark.asyncio
async def test_persona_critique():
    """Persona should critique another's contribution with issues and strengths."""
    reviewer = SkepticPersona()
    contribution = Contribution(
        persona_id="theorist",
        content=mock_hypothesis_content(),
        confidence=0.7,
    )
    context = create_test_context(llm=mock_llm_generate("..."), binder=mock_binder)

    critique = await reviewer.critique(contribution, context)

    assert isinstance(critique, Critique)
    assert critique.reviewer_id == "skeptic"
    assert critique.target_id == "theorist"
    assert isinstance(critique.issues, list)
    assert isinstance(critique.strengths, list)

@pytest.mark.asyncio
async def test_persona_endorse():
    """Persona should endorse an evidence-based contribution."""
    logician = LogicianPersona()
    contribution = Contribution(
        persona_id="detective",
        content=mock_evidence_content(strength="STRONG"),
        confidence=0.85,
    )
    context = create_test_context(llm=mock_llm_generate("true"), binder=mock_binder)

    endorsed = await logician.endorse(contribution, context)

    assert isinstance(endorsed, bool)

@pytest.mark.asyncio
async def test_persona_respond_to():
    """Persona should respond to a contextual message."""
    theorist = TheoristPersona()
    message = "What other failure modes should we consider for this component?"
    context = create_test_context(llm=mock_llm_generate("Consider..."), binder=mock_binder)

    response = await theorist.respond_to(message, context)

    assert isinstance(response, str)
    assert len(response) > 0

@pytest.mark.asyncio
async def test_discussion_facilitation():
    """Coordinator should facilitate a discussion to conclusion."""
    coordinator = CoordinatorPersona()
    contributions = [
        Contribution(persona_id="theorist", content=mock_hypothesis_content(), confidence=0.7),
        Contribution(persona_id="detective", content=mock_evidence_content(), confidence=0.8),
    ]
    context = create_test_context(
        llm=mock_llm_generate('{"conclusion": "...", "consensus": 0.75}'),
        binder=mock_binder,
    )

    discussion = await coordinator.facilitate_discussion(contributions, context)

    assert discussion.conclusion is not None
    assert 0.0 <= discussion.consensus_score <= 1.0

@pytest.mark.asyncio
async def test_resolution():
    """Coordinator should resolve disagreement between personas."""
    coordinator = CoordinatorPersona()
    disagreement = {
        "theorist": Contribution(persona_id="theorist", content=mock_hypothesis_content(),
                                 confidence=0.8),
        "skeptic": Critique(reviewer_id="skeptic", target_id="theorist",
                                    issues=["Insufficient evidence for hardware failure"],
                                    strengths=["Clear causal mechanism"]),
    }
    context = create_test_context(
        llm=mock_llm_generate('{"resolution_type": "compromise", "rationale": "..."}'),
        binder=mock_binder,
    )

    resolution = await coordinator.resolve_disagreement(disagreement, context)

    assert resolution.resolution_type in ["accept", "reject", "compromise", "defer"]
```

---

## 7.4 Expert Panel Integration Tests

The expert panel Q&A workflow (Chapter 5) requires integration tests that verify question classification, persona selection, consensus detection, and the full answer pipeline.

```python
# tests/integration/persona/test_expert_panel.py

@pytest.mark.asyncio
async def test_panel_answer_basic():
    """Panel should produce a structured answer to a simple question."""
    orchestrator = PanelOrchestrator(llm_provider=mock_llm)
    response = await orchestrator.answer("What is a BoardReader?")

    assert isinstance(response, PanelResponse)
    assert response.answer is not None
    assert len(response.answer) > 0
    assert response.experts_consulted >= 1

@pytest.mark.asyncio
async def test_panel_classification():
    """Panel should classify questions by type using keyword matching."""
    orchestrator = PanelOrchestrator()

    assert orchestrator._classify_question(
        "I'm seeing an error in the BoardReader"
    ) == QuestionType.TROUBLESHOOT

    assert orchestrator._classify_question(
        "How do I configure the EventBuilder?"
    ) == QuestionType.HOW_TO

    assert orchestrator._classify_question(
        "What is the architecture of artdaq?"
    ) == QuestionType.EXPLAIN

    assert orchestrator._classify_question(
        "Why does the BoardReader use fragments?"
    ) == QuestionType.WHY

    assert orchestrator._classify_question(
        "Compare BoardReader and EventBuilder"
    ) == QuestionType.COMPARE

@pytest.mark.asyncio
async def test_panel_persona_selection():
    """Panel should select appropriate personas based on question type."""
    orchestrator = PanelOrchestrator(llm_provider=mock_llm)

    # TROUBLESHOOT should engage more personas (full investigation team)
    troubleshoot_personas = orchestrator._select_personas(QuestionType.TROUBLESHOOT)
    assert len(troubleshoot_personas) >= 4

    # HOW_TO should engage fewer, more focused personas
    howto_personas = orchestrator._select_personas(QuestionType.HOW_TO)
    assert len(howto_personas) >= 2
    assert len(howto_personas) <= len(troubleshoot_personas)

@pytest.mark.asyncio
async def test_panel_consensus():
    """Panel should skip deliberation when agreement is high."""
    orchestrator = PanelOrchestrator(llm_provider=mock_llm)
    contributions = [
        Contribution(persona_id="qa_theorist", content="The answer is X", confidence=0.9),
        Contribution(persona_id="qa_detective", content="The answer is X", confidence=0.85),
    ]

    # High agreement should not trigger deliberation rounds
    response = await orchestrator._compile_response(contributions, "Test question")
    assert response.deliberation_rounds == 0

@pytest.mark.asyncio
async def test_panel_deliberation():
    """Panel should deliberate when consensus is low."""
    orchestrator = PanelOrchestrator(llm_provider=mock_llm)
    contributions = [
        Contribution(persona_id="qa_theorist", content="The answer is X", confidence=0.9),
        Contribution(persona_id="qa_skeptic", content="Actually, Y", confidence=0.8),
    ]

    response = await orchestrator._compile_response(contributions, "Test question")
    # Low consensus should trigger at least one deliberation round
    assert response.deliberation_rounds >= 1

@pytest.mark.asyncio
async def test_panel_streaming():
    """Panel streaming should emit correct SSE event sequence."""
    orchestrator = PanelOrchestrator(llm_provider=mock_llm)
    events = []

    async for event in orchestrator.answer_stream("What is a BoardReader?"):
        events.append(event)

    event_types = [e["event"] for e in events]

    # Must have at least one expert contribution and a final result
    assert "expert_start" in event_types
    assert "expert_done" in event_types
    assert "result" in event_types
    assert "done" in event_types

    # done must be last
    assert event_types[-1] == "done"
```

---

## 7.5 SSE Event Tests

Server-Sent Events carry investigation progress from the API to clients. Tests verify event ordering, schema conformance, and error handling.

### Phase Event Ordering

```python
# tests/integration/test_sse_events.py

@pytest.mark.asyncio
async def test_sse_phase_events_in_order():
    """Phases 0-7 should emit phase_start/phase_complete in order."""
    events = await run_streamed_investigation(mock_session_with_logs)

    phase_events = [
        e for e in events if e["event"] in ("phase_start", "phase_complete")
    ]

    # Extract phase numbers in order
    started = []
    completed = []
    for evt in phase_events:
        if evt["event"] == "phase_start":
            started.append(evt["data"]["phase"])
        elif evt["event"] == "phase_complete":
            completed.append(evt["data"]["phase"])

    # Phases should be monotonically non-decreasing
    assert started == sorted(started)
    assert completed == sorted(completed)

    # Every started phase must be completed
    assert set(started) == set(completed)

@pytest.mark.asyncio
async def test_sse_phase_progress_during_evidence():
    """Phase 2 should emit phase_progress events for each evidence iteration."""
    events = await run_streamed_investigation(mock_session_with_logs)

    phase_2_progress = [
        e for e in events
        if e["event"] == "phase_progress" and e["data"].get("phase") == 2
    ]

    # Detective iterates at least once
    assert len(phase_2_progress) >= 1

@pytest.mark.asyncio
async def test_sse_llm_events():
    """LLM phases should emit llm_request/llm_response pairs."""
    events = await run_streamed_investigation(mock_session_with_logs)

    llm_requests = [e for e in events if e["event"] == "llm_request"]
    llm_responses = [e for e in events if e["event"] == "llm_response"]

    # At minimum, hypothesis generation (phase 1) makes an LLM call
    assert len(llm_requests) >= 1
    assert len(llm_responses) >= 1

    # Each request should have required fields
    for req in llm_requests:
        assert "phase" in req["data"]
        assert "model" in req["data"]

@pytest.mark.asyncio
async def test_sse_data_events():
    """Phase 0 should emit data_query/data_result for KB lookups."""
    events = await run_streamed_investigation(mock_session_with_logs)

    data_queries = [
        e for e in events
        if e["event"] == "data_query" and e["data"].get("phase") == 0
    ]
    data_results = [
        e for e in events
        if e["event"] == "data_result" and e["data"].get("phase") == 0
    ]

    # Archivist should query the knowledge base
    assert len(data_queries) >= 1
    assert len(data_results) >= 1

@pytest.mark.asyncio
async def test_sse_complete_contains_result():
    """Final 'result' event should contain the full InvestigationResult."""
    events = await run_streamed_investigation(mock_session_with_logs)

    result_events = [e for e in events if e["event"] == "result"]
    assert len(result_events) == 1

    result = result_events[0]["data"]
    assert "investigation_id" in result
    assert "outcome" in result
    assert result["outcome"] in [
        "CONFIDENT", "PROBABLE", "UNCERTAIN", "CONTRADICTORY", "INSUFFICIENT"
    ]

@pytest.mark.asyncio
async def test_sse_error_event():
    """Pipeline failure should emit an error event with phase_reached."""
    events = await run_streamed_investigation(mock_session_without_logs)

    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) >= 1

    error_data = error_events[0]["data"]
    assert "message" in error_data
```

---

## 7.6 Prompt Regression Tests

Prompt regression tests verify that all templates load correctly, placeholders are validated, includes resolve, and formatting preserves JSON content.

```python
# tests/unit/prompts/test_prompt_loading.py

import pytest

from srcs.prompts import (
    IncludeCycleError,
    MissingPlaceholderError,
    PromptLoader,
    SystemPromptType,
    UserPromptType,
    get_system_prompt,
    get_user_prompt,
)


class TestSystemPromptLoading:
    """Verify every system prompt loads without error."""

    @pytest.mark.parametrize("prompt_type", list(SystemPromptType))
    def test_all_system_prompts_loadable(self, prompt_type: SystemPromptType):
        """Every SystemPromptType should load without error."""
        prompt = get_system_prompt(prompt_type)
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Non-trivial content

    @pytest.mark.parametrize("prompt_type", [
        pt for pt in SystemPromptType
        if not pt.name.startswith("QA_") and pt != SystemPromptType.COORDINATOR
    ])
    def test_base_knowledge_included(self, prompt_type: SystemPromptType):
        """System prompts should contain base knowledge content."""
        prompt = get_system_prompt(prompt_type)
        # Base knowledge defines components
        assert "BoardReader" in prompt
        assert "EventBuilder" in prompt
        # Base knowledge defines evidence principles
        assert "STRONG" in prompt
        assert "MODERATE" in prompt


class TestUserPromptLoading:
    """Verify every user prompt loads and formats correctly."""

    @pytest.mark.parametrize("prompt_type", list(UserPromptType))
    def test_all_user_prompts_loadable(self, prompt_type: UserPromptType):
        """Every UserPromptType should load without error."""
        template = get_user_prompt(prompt_type)
        assert template.content is not None
        assert len(template.content) > 50

    def test_placeholder_validation(self):
        """Missing required placeholders should raise MissingPlaceholderError."""
        template = get_user_prompt(UserPromptType.HYPOTHESIS_GENERATION)
        with pytest.raises(MissingPlaceholderError) as exc_info:
            template.format(error_message="timeout")  # Missing other required fields
        assert "error_component" in exc_info.value.missing or len(exc_info.value.missing) > 0


class TestIncludeResolution:
    """Verify include resolution and cycle detection."""

    def test_include_resolution(self):
        """Prompts with includes should have includes resolved."""
        template = get_user_prompt(UserPromptType.HYPOTHESIS_GENERATION)
        # The hypothesis schema should be resolved (not left as {include:...})
        assert "{include:" not in template.content
        # Content from artifacts/schemas/hypothesis.md should be present
        assert "Hypothesis" in template.content or "hypothesis" in template.content

    def test_include_cycle_detection(self):
        """Circular includes should raise IncludeCycleError."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            templates_dir = Path(tmpdir)

            # Create circular includes: A includes B, B includes A
            system_dir = templates_dir / "system"
            system_dir.mkdir()
            (system_dir / "base.md").write_text("base knowledge")

            user_dir = templates_dir / "user"
            user_dir.mkdir()
            (user_dir / "file_a.md").write_text("Content A\n{include:user/file_b}")
            (user_dir / "file_b.md").write_text("Content B\n{include:user/file_a}")

            loader = PromptLoader(templates_dir=templates_dir)
            with pytest.raises(IncludeCycleError):
                loader._load_raw("user/file_a")


class TestSafeFormatting:
    """Verify safe formatting preserves JSON braces."""

    def test_safe_format_preserves_json(self):
        """Templates with JSON braces should not raise KeyError."""
        template = get_user_prompt(UserPromptType.EVIDENCE_QUERY)
        # evidence_query.md contains JSON like {"queries": [...]}
        # Formatting should not fail on these braces
        formatted = template.format(
            investigation_mode="full_context",
            mode_specific_guidance="Use all available tools",
            analyzed_functions="getNext_",
            query_effectiveness="log_search: effective",
            hypotheses="[hypothesis list]",
            evidence="[evidence list]",
        )
        assert isinstance(formatted, str)
        # JSON braces should still be present
        assert "{" in formatted  # JSON structure preserved

    def test_safe_format_replaces_only_declared(self):
        """Only declared placeholders should be replaced."""
        template = get_user_prompt(UserPromptType.CAUSAL_CHAIN)
        formatted = template.format(
            hypothesis="Hardware link failure",
            evidence="[evidence items]",
        )
        # Declared placeholders should be replaced
        assert "{hypothesis}" not in formatted
        assert "{evidence}" not in formatted
        assert "Hardware link failure" in formatted
```

---

## 7.7 Cross-Phase Artifact Wiring Tests

These tests verify that each phase's output is correctly wired as input to downstream phases through the `WorkBinder`. They test the pipeline's data flow contract without running the full investigation.

```python
# tests/integration/persona/test_artifact_wiring.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from srcs.workbinder.binder import WorkBinder


@pytest.mark.asyncio
async def test_archivist_output_reaches_theorist():
    """Archivist's PriorKnowledge should be available to Theorist."""
    binder = WorkBinder(investigation_id="inv-test")

    # Simulate Archivist writing prior knowledge
    prior_knowledge = {
        "matched_patterns": [{"pattern_id": "p-001", "confidence": 0.8}],
        "similar_investigations": [],
        "source_locations": [{"file": "BoardReader.cc", "line": 245}],
        "call_graph_context": "getNext_ calls readFragment which calls...",
    }
    binder.store_artifact("archivist", "prior_knowledge", prior_knowledge)

    # Theorist should be able to read it
    retrieved = binder.get_artifact("prior_knowledge")
    assert retrieved is not None
    assert retrieved["matched_patterns"][0]["pattern_id"] == "p-001"

@pytest.mark.asyncio
async def test_theorist_output_reaches_detective():
    """Theorist's hypotheses should be available to Detective."""
    binder = WorkBinder(investigation_id="inv-test")

    # Simulate Theorist writing hypotheses
    hypotheses = [
        {"id": "hyp-001", "description": "Hardware link failure", "score": 0.75},
        {"id": "hyp-002", "description": "Configuration mismatch", "score": 0.45},
    ]
    binder.store_artifact("theorist", "hypotheses", hypotheses)

    # Detective should be able to read hypotheses
    retrieved = binder.get_artifact("hypotheses")
    assert retrieved is not None
    assert len(retrieved) == 2
    assert retrieved[0]["id"] == "hyp-001"

@pytest.mark.asyncio
async def test_detective_output_reaches_logician():
    """Detective's evidence and hypotheses should be available to Logician."""
    binder = WorkBinder(investigation_id="inv-test")

    # Simulate Detective writing evidence
    evidence = {
        "ev-001": {"id": "ev-001", "content": "Timeout on link 0x0100", "strength": "STRONG"},
    }
    binder.store_artifact("detective", "evidence", evidence)

    # Simulate hypotheses with updated scores
    hypotheses = [
        {"id": "hyp-001", "description": "Hardware link failure", "score": 0.85},
    ]
    binder.store_artifact("detective", "hypotheses_scored", hypotheses)

    # Logician should access both
    retrieved_evidence = binder.get_artifact("evidence")
    retrieved_hypotheses = binder.get_artifact("hypotheses_scored")
    assert retrieved_evidence is not None
    assert retrieved_hypotheses is not None
    assert "ev-001" in retrieved_evidence

@pytest.mark.asyncio
async def test_detective_artifacts_reach_judge():
    """Detective's gap analysis and quality score should reach Judge."""
    binder = WorkBinder(investigation_id="inv-test")

    # Simulate Detective writing quality metrics
    quality_metrics = {
        "evidence_quality_score": 0.72,
        "quality_strength_score": 0.8,
        "quality_diversity_score": 0.6,
        "quality_coverage_score": 0.7,
        "quality_discrimination_score": 0.65,
        "evidence_gap_analysis": "Missing: hardware diagnostics, timing traces",
        "evidence_gap_count": 2,
        "most_critical_gap": "No hardware link status verification",
    }
    binder.store_artifact("detective", "evidence_quality", quality_metrics)

    # Judge should access quality metrics
    retrieved = binder.get_artifact("evidence_quality")
    assert retrieved is not None
    assert retrieved["evidence_quality_score"] == 0.72
    assert retrieved["evidence_gap_count"] == 2

@pytest.mark.asyncio
async def test_all_outputs_reach_synthesizer():
    """All upstream outputs should be available to Synthesizer."""
    binder = WorkBinder(investigation_id="inv-test")

    # Store artifacts from all phases
    binder.store_artifact("archivist", "prior_knowledge", {"matched_patterns": []})
    binder.store_artifact("theorist", "hypotheses", [{"id": "hyp-001", "score": 0.8}])
    binder.store_artifact("detective", "evidence", {"ev-001": {"strength": "STRONG"}})
    binder.store_artifact("logician", "causal_chains", [{"hypothesis_id": "hyp-001"}])
    binder.store_artifact("skeptic", "challenges", [{"severity": "MEDIUM"}])
    binder.store_artifact("judge", "outcome", {"outcome": "PROBABLE", "confidence": 0.65})

    # Synthesizer should access everything
    assert binder.get_artifact("prior_knowledge") is not None
    assert binder.get_artifact("hypotheses") is not None
    assert binder.get_artifact("evidence") is not None
    assert binder.get_artifact("causal_chains") is not None
    assert binder.get_artifact("challenges") is not None
    assert binder.get_artifact("outcome") is not None

@pytest.mark.asyncio
async def test_binder_stores_all_artifacts():
    """Each phase's contribution should be stored in the binder."""
    binder = WorkBinder(investigation_id="inv-test")

    # Simulate full pipeline artifact storage
    phase_artifacts = {
        "chronicler": ("triage_result", {"primary_error_file": "br01.log"}),
        "archivist": ("prior_knowledge", {"matched_patterns": []}),
        "theorist": ("hypotheses", [{"id": "hyp-001"}]),
        "detective": ("evidence", {"ev-001": {}}),
        "logician": ("causal_chains", [{"id": "chain-001"}]),
        "skeptic": ("challenges", [{"id": "ch-001"}]),
        "judge": ("outcome", {"outcome": "PROBABLE"}),
        "synthesizer": ("synthesis", {"report": "..."}),
        "learner": ("patterns", [{"pattern_id": "p-001"}]),
    }

    for persona, (artifact_type, data) in phase_artifacts.items():
        binder.store_artifact(persona, artifact_type, data)

    # All artifacts should be retrievable
    for persona, (artifact_type, expected_data) in phase_artifacts.items():
        retrieved = binder.get_artifact(artifact_type)
        assert retrieved is not None, f"Missing artifact {artifact_type} from {persona}"
```

---

## 7.8 Fixtures & Mocks

### Standard Test Fixtures

```python
# tests/conftest.py (persona-specific additions)

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from srcs.models import Evidence, EvidenceItem, Hypothesis, Log
from srcs.persona.base import InvestigationContext


@pytest.fixture
def mock_investigation_context():
    """Standard InvestigationContext for persona tests."""
    return InvestigationContext(
        error=Log(
            timestamp=datetime(2026, 2, 14, 10, 32, 15),
            level="ERROR",
            component="BoardReader_01",
            function="getNext_",
            message="Fragment timeout after 5000ms on link 0x0100",
        ),
        context_logs=[
            Log(
                timestamp=datetime(2026, 2, 14, 10, 32, 10),
                level="WARNING",
                component="BoardReader_01",
                function="getNext_",
                message="Slow response from link 0x0100 (3200ms)",
            ),
            Log(
                timestamp=datetime(2026, 2, 14, 10, 32, 5),
                level="INFO",
                component="BoardReader_01",
                function="readData",
                message="Reading fragments from link 0x0100",
            ),
        ],
        binder=create_mock_binder(),
        llm=AsyncMock(spec=LLMProvider),
        kb=AsyncMock(spec=KnowledgeBase),
    )


@pytest.fixture
def mock_hypotheses():
    """Standard hypothesis list for testing."""
    return [
        Hypothesis(
            id="hyp-001",
            description="Hardware link failure on link 0x0100",
            score=0.75,
            source="pattern",
            supporting_evidence_ids=["ev-001"],
            contradicting_evidence_ids=[],
        ),
        Hypothesis(
            id="hyp-002",
            description="Configuration mismatch in timeout parameters",
            score=0.45,
            source="llm",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
        ),
    ]


@pytest.fixture
def mock_evidence():
    """Standard evidence collection for testing."""
    return Evidence(items={
        "ev-001": EvidenceItem(
            id="ev-001",
            evidence_type="log",
            content="Repeated timeout on link 0x0100",
            strength="STRONG",
            source="log_search",
        ),
    })
```

### WorkBinder Mock Factory

```python
def create_mock_binder():
    """Create a WorkBinder mock with standard artifact methods."""
    binder = MagicMock()
    binder.get_hypotheses.return_value = []
    binder.get_evidence_items.return_value = []
    binder.get_causal_chains.return_value = []
    binder.get_challenges.return_value = []
    binder.get_artifact.return_value = None
    binder.store_artifact.return_value = "artifact-001"
    binder.record_llm_request.return_value = "req-001"
    return binder


def mock_work_binder_with_hypotheses():
    """Create a binder mock pre-loaded with hypotheses."""
    binder = create_mock_binder()
    binder.get_hypotheses.return_value = [
        {"id": "hyp-001", "description": "Hardware link failure", "score": 0.75},
        {"id": "hyp-002", "description": "Config mismatch", "score": 0.45},
    ]
    return binder


def mock_work_binder_with_all_artifacts():
    """Create a binder mock pre-loaded with all phase artifacts."""
    binder = create_mock_binder()
    binder.get_hypotheses.return_value = [
        {"id": "hyp-001", "description": "Hardware link failure", "score": 0.85},
    ]
    binder.get_evidence_items.return_value = [
        {"id": "ev-001", "content": "Timeout on link 0x0100", "strength": "STRONG"},
    ]
    binder.get_causal_chains.return_value = [
        {"id": "chain-001", "hypothesis_id": "hyp-001", "steps": []},
    ]
    binder.get_challenges.return_value = [
        {"id": "ch-001", "severity": "MEDIUM", "challenge": "Limited evidence"},
    ]
    binder.get_artifact.side_effect = lambda key: {
        "evidence_quality": {
            "evidence_quality_score": 0.72,
            "evidence_gap_count": 1,
            "most_critical_gap": "No hardware diagnostics",
        },
        "outcome": {"outcome": "PROBABLE", "confidence": 0.65},
    }.get(key)
    return binder
```

### LLM Mock Patterns

```python
def mock_llm_generate(response_text: str) -> AsyncMock:
    """Create LLM mock that returns specified text.

    Usage:
        llm = mock_llm_generate("The analysis shows...")
        result = await llm.generate(system_prompt, user_prompt)
        assert result == "The analysis shows..."
    """
    llm = AsyncMock(spec=LLMProvider)
    llm.generate.return_value = response_text
    llm.config = MagicMock()
    llm.config.model = "test-model"
    llm.config.temperature = 0.1
    return llm


def mock_llm_structured(response_model: type, response_data: dict) -> AsyncMock:
    """Create LLM mock for structured output.

    Usage:
        llm = mock_llm_structured(HypothesisResponse, {"hypotheses": [...]})
        result = await llm.generate_structured(system_prompt, user_prompt, HypothesisResponse)
        assert isinstance(result, HypothesisResponse)
    """
    llm = AsyncMock(spec=LLMProvider)
    llm.generate_structured.return_value = response_model(**response_data)
    llm.config = MagicMock()
    llm.config.model = "test-model"
    llm.config.temperature = 0.1
    return llm


def mock_llm_sequence(responses: list[str]) -> AsyncMock:
    """Create LLM mock that returns different responses on each call.

    Useful for testing iterative phases like evidence seeking where the
    LLM is called multiple times in a loop.

    Usage:
        llm = mock_llm_sequence([
            '{"queries": [{"query_type": "function_lookup", ...}]}',
            '{"queries": []}',  # Empty = stop iterating
        ])
    """
    llm = AsyncMock(spec=LLMProvider)
    llm.generate.side_effect = responses
    llm.config = MagicMock()
    llm.config.model = "test-model"
    llm.config.temperature = 0.1
    return llm
```

### Knowledge Base Mock

```python
def mock_knowledge_base(
    patterns: list | None = None,
    similar: list | None = None,
) -> AsyncMock:
    """Create a KnowledgeBase mock with configurable return values.

    Args:
        patterns: Patterns returned by match_patterns(). Default: empty list.
        similar: Investigations returned by find_similar_investigations(). Default: empty list.
    """
    kb = AsyncMock(spec=KnowledgeBase)
    kb.match_patterns.return_value = patterns or []
    kb.find_similar_investigations.return_value = similar or []
    kb.get_investigation.return_value = None
    kb.store_investigation.return_value = None
    kb.update_calibration.return_value = None
    kb.store_pattern.return_value = "pattern-001"
    return kb
```

### Test Helper: Streamed Investigation Runner

```python
async def run_streamed_investigation(session_fixture) -> list[dict]:
    """Run a streamed investigation and collect all SSE events.

    Used by SSE event tests to avoid duplicating the stream-consumption
    boilerplate.

    Args:
        session_fixture: Pre-configured session with parsed logs.

    Returns:
        List of parsed SSE event dicts with "event" and "data" keys.
    """
    events = []
    async with session_fixture.client.stream(
        "POST",
        "/api/v1/agent/tools/investigate/stream",
        json={"session_id": session_fixture.session_id},
        headers={"Accept": "text/event-stream"},
    ) as response:
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_text, buffer = buffer.split("\n\n", 1)
                parsed = parse_sse_events(event_text + "\n\n")
                events.extend(parsed)
    return events
```

---

### Cross-Reference

For REST API-specific testing patterns (tool endpoint tests, session management tests, client library tests), see [agentic-rest-service-design-ch7-testing-strategy.md](agentic-rest-service-design-ch7-testing-strategy.md).

---

> [← Prompt Architecture](agentic-persona-library-ch6-prompt-architecture.md) | [Table of Contents](agentic-persona-library.md)
