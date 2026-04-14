"""
File: coordinator.py
Purpose: Investigation coordinator - orchestrates pipeline-driven investigat...
Category: Utility
Author: artdaq team
Depends: extraction, knowledge, learning, llm, models, ...
Exports: HypothesisConfig, EvidenceConfig, OutcomeConfig, CausalChainConfig, InvestigationConfig, ...
Complexity: High | Lines: 308
"""

import logging
from typing import TYPE_CHECKING
from pydantic import BaseModel
from srcs.knowledge import KnowledgeBase
from srcs.knowledge.learning import PatternLearner
from srcs.llm import LLMProvider
from srcs.models import Challenge, Evidence, Hypothesis, InvestigationOutcome, InvestigationResult, Log
from srcs.source import SourceConfig
from .callbacks import InvestigationCallback
from .tools import CodeForensicsTools, CodeTools

if TYPE_CHECKING:
    from srcs.extraction import CodeIndex
    from srcs.llm import RecordingLLMProvider
    from srcs.pipeline import PipelineConfig, PipelineEngine
logger = logging.getLogger(__name__)


class HypothesisConfig(BaseModel):
    code_hint_prior_min: float = 0.7
    code_hint_prior_max: float = 0.85
    explicit_cause_prior_min: float = 0.9
    explicit_cause_prior_max: float = 0.95
    pattern_prior_min: float = 0.6
    pattern_prior_max: float = 0.8
    similar_prior_min: float = 0.3
    similar_prior_max: float = 0.5
    fresh_prior_max: float = 0.3
    alternative_prior: float = 0.1
    merge_similarity_threshold: float = 0.8
    merge_prior_cap: float = 0.95
    merge_other_prior_factor: float = 0.3
    enable_llm_deduplication: bool = True
    llm_dedup_similarity_threshold: float = 0.8
    llm_dedup_min_hypotheses: int = 4
    authoritative_hint_threshold: float = 0.85
    max_fresh_if_code_hints: int = 2
    code_hint_probability_share: float = 0.7
    max_alternatives: int = 3
    max_code_hint_hypotheses: int = 5
    max_parsed_hypotheses: int = 5


class EvidenceConfig(BaseModel):
    strength_strong: float = 0.25
    strength_moderate: float = 0.15
    strength_weak: float = 0.05
    targeted_boost_factor: float = 1.5
    targeted_contradict_factor: float = 1.0
    absence_contradict_factor: float = 0.5
    non_targeted_code_factor: float = 0.75
    non_targeted_log_factor: float = 0.5
    code_hint_match_factor: float = 1.0
    term_match_threshold: float = 0.4
    category_relevance_score: float = 0.15
    weak_term_relevance_score: float = 0.05
    consecutive_failure_limit: int = 3
    min_success_rate: float = 0.1
    min_attempts_for_rate: int = 5
    clear_winner_score: float = 0.7
    clear_winner_margin: float = 0.3
    code_hint_early_stop_score: float = 0.5
    code_hint_early_stop_margin: float = 0.2
    min_iterations_before_stop: int = 3
    max_queries_per_iteration: int = 5
    max_log_queries_code_centric: int = 1


class OutcomeConfig(BaseModel):
    confident_score_threshold: float = 0.7
    probable_score_threshold: float = 0.5
    code_hint_probable_threshold: float = 0.6
    viable_threshold: float = 0.4
    high_challenge_penalty: float = 0.15
    medium_challenge_penalty: float = 0.05
    min_confidence_floor: float = 0.3


class CausalChainConfig(BaseModel):
    max_chains: int = 3
    min_hypothesis_score: float = 0.2
    min_evidence_coverage: float = 0.5
    min_logical_validity: float = 0.5


class InvestigationConfig(BaseModel):
    max_hypotheses: int = 10
    max_evidence_iterations: int = 10
    max_chain_depth: int = 8
    confidence_floor: float = 0.1
    confidence_ceiling: float = 0.95
    tier1_pattern_confidence: float = 0.9
    tier1_pattern_accuracy: float = 0.85
    tier1_min_samples: int = 20
    code_hint_fast_path_prior_threshold: float = 0.9
    code_hint_fast_path_match_threshold: float = 0.7
    enable_auto_learning: bool = True
    default_function_source_length: int = 2000
    docs_max_chars: int = 12000
    subcomponent_map_path: str = "data/docs/sub-component-map.yaml"
    hypothesis: HypothesisConfig = HypothesisConfig()
    evidence: EvidenceConfig = EvidenceConfig()
    outcome: OutcomeConfig = OutcomeConfig()
    causal_chain: CausalChainConfig = CausalChainConfig()


class InvestigationCoordinator:
    pattern_learner: PatternLearner | None

    def __init__(
        self,
        kb: KnowledgeBase,
        llm: LLMProvider,
        config: InvestigationConfig | None = None,
        db_path: str | None = None,
        source_config: SourceConfig | None = None,
        code_index: "CodeIndex | None" = None,
    ):
        self.kb = kb
        self.llm = llm
        self.config = config or InvestigationConfig()
        self.code_tools = CodeTools(code_index=code_index, source_config=source_config) if source_config else None
        source_roots = []
        if source_config and source_config.has_repositories():
            from srcs.source import RepositoryManager

            manager = RepositoryManager(source_config)
            source_roots = manager.get_existing_repo_paths()
        if code_index is None and self.code_tools:
            code_index = self.code_tools._ensure_index()
        self.forensics_tools = (
            CodeForensicsTools(code_index=code_index, source_roots=source_roots, source_config=source_config)
            if source_config
            else None
        )
        self._source_roots = source_roots
        self._code_index = code_index
        if db_path:
            self.pattern_learner = PatternLearner(db_path)
        elif hasattr(kb, "sqlite") and hasattr(kb.sqlite, "db_path"):
            self.pattern_learner = PatternLearner(str(kb.sqlite.db_path))
        else:
            self.pattern_learner = None
            logger.warning("Pattern learner not initialized - no db_path provided")
        self._pipeline_engine: "PipelineEngine | None" = None
        self._pipeline_config: "PipelineConfig | None" = None
        self.recording_llm: "RecordingLLMProvider | None" = None

    def configure_pipeline(self, pipeline_config: "PipelineConfig") -> None:
        self._pipeline_config = pipeline_config
        self._pipeline_engine = None
        logger.info("Coordinator configured with pipeline")

    def _get_pipeline_engine(self) -> "PipelineEngine":
        if self._pipeline_engine is not None:
            return self._pipeline_engine
        if self._pipeline_config is None:
            raise ValueError("Pipeline configuration required. Please add a 'pipeline' section to config.yaml.")
        from srcs.persona import (
            ArchivistPersona,
            ChroniclerPersona,
            DetectivePersona,
            JudgePersona,
            LearnerPersona,
            LogicianPersona,
            SkepticPersona,
            SynthesizerPersona,
            TheoristPersona,
        )
        from srcs.pipeline import PipelineEngine
        from srcs.pipeline.executor import ExecutorRegistry
        from srcs.pipeline.persona_executor import UnifiedPersonaExecutor

        registry = ExecutorRegistry()
        persona_mapping: dict[int, type] = {
            -1: ChroniclerPersona,
            0: ArchivistPersona,
            1: TheoristPersona,
            2: DetectivePersona,
            3: LogicianPersona,
            4: SkepticPersona,
            5: JudgePersona,
            6: SynthesizerPersona,
            7: LearnerPersona,
        }
        for phase, persona_class in persona_mapping.items():
            executor = UnifiedPersonaExecutor(phase, persona_class)
            registry.register(executor)
        from srcs.extraction import SourceLocator

        source_locator = None
        if self._source_roots:
            source_locator = SourceLocator(
                source_roots=self._source_roots,
                code_index=self._code_index,
                chroma_store=self.kb.chroma if self.kb else None,
            )
        self._pipeline_engine = PipelineEngine(
            config=self._pipeline_config,
            executor_registry=registry,
            validate_contracts=True,
            kb=self.kb,
            investigation_config=self.config,
            recording_llm=self.recording_llm,
            llm=self.llm,
            code_index=self._code_index,
            source_locator=source_locator,
        )
        return self._pipeline_engine

    async def resume_investigation(
        self, investigation_id: str, callback: InvestigationCallback | None = None
    ) -> InvestigationResult:
        from copy import deepcopy
        from srcs.workbinder import BinderStore

        db_path: str | None = None
        if hasattr(self.kb, "config"):
            db_path = self.kb.config.sqlite_path
        if not db_path:
            raise ValueError("Cannot resume: no database path available")
        store = BinderStore(db_path)
        binder, resume_phase, _resume_ctx = await store.load_for_resume(investigation_id)
        investigation = await self.kb.get_investigation(investigation_id)
        if investigation is None:
            raise ValueError(f"Investigation not found: {investigation_id}")
        resume_phase_num = binder.resume_investigation()
        investigation.binder = binder
        if self._pipeline_config is None:
            raise ValueError("Pipeline configuration required for resume.")
        phase_id_map = {
            -1: "log_bundle_analysis",
            0: "prior_retrieval",
            1: "hypothesis_generation",
            2: "evidence_seeking",
            3: "causal_chains",
            4: "adversarial_review",
            5: "outcome_assessment",
            6: "synthesis",
            7: "learning",
        }
        phase_id = phase_id_map.get(resume_phase_num)
        config_phase_ids = {p.id for p in self._pipeline_config.phases}
        if phase_id and phase_id not in config_phase_ids:
            phase_id = None
        resume_config = deepcopy(self._pipeline_config)
        resume_config.start_at = phase_id
        original_config = self._pipeline_config
        original_engine = self._pipeline_engine
        try:
            self._pipeline_config = resume_config
            self._pipeline_engine = None
            engine = self._get_pipeline_engine()
            result = await engine.execute(
                investigation.trigger_error, investigation.context_logs, callback, investigation=investigation
            )
            return result
        finally:
            self._pipeline_config = original_config
            self._pipeline_engine = original_engine

    async def investigate(
        self,
        error: Log,
        context: list[Log],
        callback: InvestigationCallback | None = None,
        source_files: list | None = None,
    ) -> InvestigationResult:
        engine = self._get_pipeline_engine()
        return await engine.execute(error, context, callback, source_files=source_files)

    def _assess_outcome(
        self, hypotheses: list[Hypothesis], evidence: Evidence, challenges: list[Challenge]
    ) -> InvestigationOutcome:
        if not hypotheses:
            return InvestigationOutcome.INSUFFICIENT
        top = hypotheses[0]
        unresolved_high = [c for c in challenges if c.requires_response and (not c.resolved) and (c.severity == "HIGH")]
        unresolved = [c for c in challenges if c.requires_response and (not c.resolved)]
        contradicting = len(top.contradicting_evidence_ids)
        supporting = len(top.supporting_evidence_ids)
        if contradicting > 0 and contradicting >= supporting:
            return InvestigationOutcome.CONTRADICTORY
        is_code_hint = top.source.startswith("code_hint:")
        is_explicit_cause = top.source == "code_hint:explicit_cause"
        confident_threshold = self.config.outcome.confident_score_threshold
        if top.score > confident_threshold and len(unresolved_high) == 0:
            return InvestigationOutcome.CONFIDENT
        code_hint_threshold = self.config.outcome.code_hint_probable_threshold
        if is_explicit_cause and top.score > code_hint_threshold:
            logger.debug(f"Code hint (explicit_cause) with score {top.score:.2f} -> PROBABLE")
            return InvestigationOutcome.PROBABLE
        if is_code_hint and top.score > code_hint_threshold and (len(unresolved_high) == 0):
            logger.debug(f"Code hint with score {top.score:.2f} -> PROBABLE")
            return InvestigationOutcome.PROBABLE
        probable_threshold = self.config.outcome.probable_score_threshold
        if top.score > probable_threshold and len(unresolved) <= 1:
            return InvestigationOutcome.PROBABLE
        viable_threshold = self.config.outcome.viable_threshold
        relative_threshold = top.score * 0.5
        effective_threshold = max(viable_threshold, relative_threshold)
        viable = [h for h in hypotheses if h.score > effective_threshold]
        if len(viable) > 1:
            logger.debug(
                f"Multiple viable hypotheses ({len(viable)}) with scores above {effective_threshold:.2f} -> UNCERTAIN"
            )
            return InvestigationOutcome.UNCERTAIN
        return InvestigationOutcome.INSUFFICIENT
