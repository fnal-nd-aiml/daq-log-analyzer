"""
File: coordinator.py
Purpose: Investigation coordinator - orchestrates pipeline-driven investigat...
Category: Utility
Author: artdaq team
Depends: extraction, knowledge, learning, llm, models, ...
Exports: InvestigationCoordinator
Complexity: Medium | Lines: 110
"""

import logging
from typing import TYPE_CHECKING
from srcs.knowledge import KnowledgeBase
from srcs.knowledge.learning import PatternLearner
from srcs.llm import LLMProvider
from srcs.models import InvestigationResult, Log
from srcs.models.callbacks import InvestigationCallback
from srcs.models.investigation_config import CausalChainConfig, EvidenceConfig, HypothesisConfig, InvestigationConfig, OutcomeConfig
from srcs.source import SourceConfig
from .tools import CodeForensicsTools, CodeTools
if TYPE_CHECKING:
    from srcs.extraction import CodeIndex
    from srcs.llm import RecordingLLMProvider
    from srcs.pipeline import PipelineConfig, PipelineEngine
logger = logging.getLogger(__name__)

class InvestigationCoordinator:
    pattern_learner: PatternLearner | None

    def __init__(self, kb: KnowledgeBase, llm: LLMProvider, config: InvestigationConfig | None=None, db_path: str | None=None, source_config: SourceConfig | None=None, code_index: 'CodeIndex | None'=None):
        self.kb = kb
        self.llm = llm
        self.config = config or InvestigationConfig()
        self.code_tools = CodeTools(code_index=code_index, source_config=source_config) if source_config else None
        source_roots = []
        if source_config and source_config.has_repositories():
            from srcs.source import RepositoryManager
            manager = RepositoryManager(source_config)
            source_roots = manager.get_existing_repo_paths()
        self.forensics_tools = CodeForensicsTools(code_index=code_index, source_roots=source_roots, source_config=source_config) if source_config else None
        self._source_roots = source_roots
        self._code_index = code_index
        if db_path:
            self.pattern_learner = PatternLearner(db_path)
        elif hasattr(kb, 'sqlite') and hasattr(kb.sqlite, 'db_path'):
            self.pattern_learner = PatternLearner(str(kb.sqlite.db_path))
        else:
            self.pattern_learner = None
            logger.warning('Pattern learner not initialized - no db_path provided')
        self._pipeline_engine: 'PipelineEngine | None' = None
        self._pipeline_config: 'PipelineConfig | None' = None
        self.recording_llm: 'RecordingLLMProvider | None' = None

    def configure_pipeline(self, pipeline_config: 'PipelineConfig') -> None:
        self._pipeline_config = pipeline_config
        self._pipeline_engine = None
        logger.info('Coordinator configured with pipeline')

    def _get_pipeline_engine(self) -> 'PipelineEngine':
        if self._pipeline_engine is not None:
            return self._pipeline_engine
        if self._pipeline_config is None:
            raise ValueError("Pipeline configuration required. Please add a 'pipeline' section to config.yaml.")
        from srcs.persona.registry import get_persona_class
        from srcs.pipeline import PipelineEngine
        from srcs.pipeline.executor import ExecutorRegistry
        from srcs.pipeline.persona_executor import UnifiedPersonaExecutor
        registry = ExecutorRegistry()
        for phase_config in self._pipeline_config.phases:
            if not phase_config.executor:
                continue
            phase_number, persona_class = get_persona_class(phase_config.executor)
            registry.register(UnifiedPersonaExecutor(phase_number, persona_class))
        from srcs.extraction import SourceLocator
        source_locator = None
        if self._source_roots:
            source_locator = SourceLocator(source_roots=self._source_roots, code_index=self._code_index, chroma_store=self.kb.chroma if self.kb else None)
        self._pipeline_engine = PipelineEngine(config=self._pipeline_config, executor_registry=registry, validate_contracts=True, kb=self.kb, investigation_config=self.config, recording_llm=self.recording_llm, llm=self.llm, code_index=self._code_index, source_locator=source_locator)
        return self._pipeline_engine

    async def resume_investigation(self, investigation_id: str, callback: InvestigationCallback | None=None) -> InvestigationResult:
        from copy import deepcopy
        from srcs.workbinder import BinderStore
        db_path: str | None = None
        if hasattr(self.kb, 'config'):
            db_path = self.kb.config.sqlite_path
        if not db_path:
            raise ValueError('Cannot resume: no database path available')
        store = BinderStore(db_path)
        binder, resume_phase, _resume_ctx = await store.load_for_resume(investigation_id)
        investigation = await self.kb.get_investigation(investigation_id)
        if investigation is None:
            raise ValueError(f'Investigation not found: {investigation_id}')
        resume_phase_num = binder.resume_investigation()
        investigation.binder = binder
        if self._pipeline_config is None:
            raise ValueError('Pipeline configuration required for resume.')
        phase_id_map = {-1: 'log_bundle_analysis', 0: 'prior_retrieval', 1: 'hypothesis_generation', 2: 'evidence_seeking', 3: 'causal_chains', 4: 'adversarial_review', 5: 'outcome_assessment', 6: 'synthesis', 7: 'learning'}
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
            result = await engine.execute(investigation.trigger_error, investigation.context_logs, callback, investigation=investigation)
            return result
        finally:
            self._pipeline_config = original_config
            self._pipeline_engine = original_engine

    async def investigate(self, error: Log, context: list[Log], callback: InvestigationCallback | None=None, source_files: list | None=None) -> InvestigationResult:
        engine = self._get_pipeline_engine()
        return await engine.execute(error, context, callback, source_files=source_files)
__all__ = ['CausalChainConfig', 'EvidenceConfig', 'HypothesisConfig', 'InvestigationConfig', 'InvestigationCoordinator', 'OutcomeConfig']