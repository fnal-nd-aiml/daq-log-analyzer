"""
File: base.py
Purpose: Unified KnowledgeBase interface.
Category: Utility
Author: artdaq team
Depends: llm, models, pydantic
Exports: DatabaseBackend, PostgresConfig, StorageConfig, KnowledgeBase
Complexity: High | Lines: 258
"""

import logging
import os
import re
from enum import Enum
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from srcs.llm import LLMProvider
from srcs.models import (
    CalibrationData,
    ErrorSignature,
    EvidenceQueryTemplate,
    Investigation,
    InvestigationOutcome,
    Log,
    PatternMatch,
    PriorKnowledge,
    RecommendedHypothesis,
    RootCausePattern,
    SimilarInvestigation,
)
from .chroma_store import ChromaStore
from .sqlite_store import SQLiteStore
from .store_interface import StructuredStore

logger = logging.getLogger(__name__)


class DatabaseBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class PostgresConfig(BaseModel):
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    database: str = Field(default="daq_analyzer", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: str = Field(default="", description="Database password (prefer env var)")
    min_connections: int = Field(default=2, description="Minimum pool connections")
    max_connections: int = Field(default=10, description="Maximum pool connections")
    ssl: bool = Field(default=False, description="Enable SSL connection")

    def get_password(self) -> str:
        return os.environ.get("ARTDAQ_POSTGRES_PASSWORD", self.password)


class StorageConfig(BaseModel):
    model_config = {"use_enum_values": True}
    backend: DatabaseBackend = Field(
        default=DatabaseBackend.SQLITE, description="Database backend: 'sqlite' or 'postgresql'"
    )
    sqlite_path: str = Field(default="./data/knowledge.db", description="Path to SQLite database file")
    chroma_path: str = Field(default="./data/chroma", description="Path to ChromaDB persistence directory")
    postgres: PostgresConfig | None = Field(
        default=None, description="PostgreSQL configuration (required if backend is 'postgresql')"
    )

    def __init__(
        self,
        backend: DatabaseBackend | str = DatabaseBackend.SQLITE,
        sqlite_path: str = "./data/knowledge.db",
        chroma_path: str = "./data/chroma",
        postgres: PostgresConfig | dict | None = None,
        **kwargs,
    ) -> None:
        if isinstance(backend, str):
            backend = DatabaseBackend(backend)
        if isinstance(postgres, dict):
            postgres = PostgresConfig(**postgres)
        super().__init__(backend=backend, sqlite_path=sqlite_path, chroma_path=chroma_path, postgres=postgres, **kwargs)


class KnowledgeBase:

    def __init__(self, config: StorageConfig, llm: "LLMProvider") -> None:
        self.config = config
        self.llm = llm
        self._store: StructuredStore | None = None
        self._initialized = False
        self._sqlite_store = SQLiteStore(config.sqlite_path)
        self.chroma = ChromaStore(config.chroma_path, llm.embed)

    async def initialize(self) -> None:
        if self._initialized:
            return
        from .store_factory import create_structured_store

        self._store = await create_structured_store(self.config)
        self._initialized = True
        logger.info("KnowledgeBase initialized with %s backend", self.config.backend)

    @property
    def store(self) -> "StructuredStore":
        if self._store is not None:
            return self._store
        return self._sqlite_store

    @property
    def sqlite(self) -> "StructuredStore":
        return self.store

    async def close(self) -> None:
        if self._store is not None:
            await self._store.close()
            self._store = None
            self._initialized = False

    async def find_pattern(self, signature: ErrorSignature) -> PatternMatch | None:
        return await self.sqlite.find_pattern(signature)

    async def find_matching_pattern(self, signature: ErrorSignature) -> PatternMatch | None:
        return await self.find_pattern(signature)

    async def get_pattern_root_causes(self, pattern_id: str) -> list[RootCausePattern]:
        return await self.sqlite.get_pattern_root_causes(pattern_id)

    async def get_patterns_by_ids(self, pattern_ids: list[str]) -> list:
        return await self.sqlite.get_patterns_by_ids(pattern_ids)

    async def get_pattern_statistics(self) -> dict:
        return await self.sqlite.get_pattern_statistics()

    async def find_similar_investigations(
        self, error: Log, context: list[Log], n: int = 5
    ) -> list[SimilarInvestigation]:
        description = self._create_description(error, context)
        return await self.chroma.find_similar_investigations(description, n)

    async def get_investigation(self, investigation_id: str) -> Investigation | None:
        return await self.sqlite.get_investigation(investigation_id)

    async def get_recent_investigations(self, limit: int = 100, offset: int = 0) -> list[Investigation]:
        return await self.sqlite.get_recent_investigations(limit, offset)

    async def count_investigations(self) -> int:
        return await self.sqlite.count_investigations()

    async def store_investigation(self, investigation: Investigation) -> None:
        await self.sqlite.store_investigation(investigation)
        description = self._create_description(investigation.trigger_error, investigation.context_logs)
        root_cause = None
        if investigation.hypotheses:
            sorted_hyps = sorted(investigation.hypotheses, key=lambda h: h.score, reverse=True)
            top_hyp = sorted_hyps[0]
            if investigation.outcome in (InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE):
                root_cause = top_hyp.description
            elif top_hyp.score > 0.5:
                root_cause = top_hyp.description
            elif top_hyp.score > 0.3 and len(investigation.hypotheses) == 1:
                root_cause = top_hyp.description
        metadata = self._create_metadata(investigation, root_cause)
        try:
            await self.chroma.store_investigation_embedding(investigation.id, description, metadata)
        except Exception as e:
            logger.warning("Failed to store embedding: %s", e)

    async def get_calibration(self, model: str) -> CalibrationData | None:
        return await self.sqlite.get_calibration(model)

    async def update_calibration(self, model: str, stated: float, actual: bool) -> None:
        await self.sqlite.update_calibration(model, stated, actual)

    async def get_prior_knowledge(self, error: Log, context: list[Log]) -> PriorKnowledge:
        prior = PriorKnowledge()
        signature = self._extract_signature(error)
        pattern_match = await self.find_pattern(signature)
        if pattern_match:
            prior.matched_patterns.append(pattern_match)
            root_causes = await self.get_pattern_root_causes(pattern_match.pattern.id)
            for rc in root_causes:
                base_prior = 0.6 + rc.frequency * 0.2
                if pattern_match.pattern.user_verified:
                    base_prior = min(0.95, base_prior * 1.5)
                prior.recommended_hypotheses.append(
                    RecommendedHypothesis(
                        description=rc.description, source=f"pattern:{pattern_match.pattern.id}", prior=base_prior
                    )
                )
                for evidence_pattern in rc.confirming_evidence_patterns:
                    prior.recommended_queries.append(
                        EvidenceQueryTemplate(
                            query_type="log_search",
                            query_template=evidence_pattern,
                            expected_result="Would confirm hypothesis",
                        )
                    )
        similar = await self.find_similar_investigations(error, context)
        prior.similar_investigations = similar
        for sim in similar[:5]:
            if not sim.root_cause:
                continue
            use_case = False
            prior_val = 0.0
            if sim.was_correct is False:
                continue
            elif sim.was_correct:
                prior_val = min(0.95, (0.5 + sim.similarity_score * 0.3) * 1.5)
                use_case = True
            elif sim.similarity_score > 0.9:
                prior_val = min((0.4 + sim.similarity_score * 0.3) * 0.6, 0.45)
                use_case = True
            elif sim.similarity_score > 0.8 and sim.outcome in ("CONFIDENT", "PROBABLE"):
                prior_val = min((0.3 + sim.similarity_score * 0.2) * 0.6, 0.35)
                use_case = True
            elif sim.similarity_score > 0.7 and sim.outcome == "CONFIDENT":
                prior_val = min((0.25 + sim.similarity_score * 0.15) * 0.6, 0.3)
                use_case = True
            if use_case:
                prior.recommended_hypotheses.append(
                    RecommendedHypothesis(
                        description=sim.root_cause, source=f"similar:{sim.investigation_id}", prior=prior_val
                    )
                )
        return prior

    def _create_description(self, error: Log, context: list[Log]) -> str:
        parts = [f"Error: {error.message}", f"Component: {error.component}"]
        if error.function:
            parts.append(f"Function: {error.function}")
        warning_count = sum((1 for log in context if log.level == "WARNING"))
        error_count = sum((1 for log in context if log.level == "ERROR"))
        if warning_count > 0:
            parts.append(f"Context: {warning_count} warnings before error")
        if error_count > 1:
            parts.append(f"Context: {error_count - 1} other errors before this")
        return " | ".join(parts)

    def _extract_signature(self, error: Log) -> ErrorSignature:
        return ErrorSignature(
            function=error.function,
            message_pattern=self._normalize_message(error.message),
            level=error.level,
            component=error.component,
        )

    def _normalize_message(self, message: str) -> str:
        pattern = message
        pattern = re.sub(
            "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "{UUID}", pattern
        )
        pattern = re.sub("0x[0-9a-fA-F]+", "{HEX}", pattern)
        pattern = re.sub("\\d+\\.\\d+", "{FLOAT}", pattern)
        pattern = re.sub("\\b\\d+\\b", "{N}", pattern)
        return pattern

    def _create_metadata(self, investigation: Investigation, root_cause: str | None) -> dict:
        return {
            "outcome": investigation.outcome.value if investigation.outcome else None,
            "root_cause": root_cause,
            "component": investigation.trigger_error.component,
            "function": investigation.trigger_error.function,
            "was_correct": None,
        }

    async def find_similar_functions(self, description: str, n: int = 10, file_filter: str | None = None) -> list[dict]:
        return await self.chroma.find_similar_functions(description, n, file_filter)
