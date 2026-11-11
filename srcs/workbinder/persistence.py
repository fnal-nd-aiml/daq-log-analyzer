"""
File: persistence.py
Purpose: SQLite persistence for Work Binders.
Category: Utility
Author: artdaq team
Depends: None
Exports: BinderStore
Complexity: Medium | Lines: 135
"""

from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from .artifacts import Annotation, Artifact, ArtifactType, BoardReaderIdentificationArtifact, CallGraphNode, CausalChainArtifact, ChallengeArtifact, CodeSnippet, ConclusionArtifact, ErrorContextArtifact, EvidenceArtifact, FeedbackArtifact, Finding, FlowConfigArtifact, FunctionSummaryArtifact, HypothesisArtifact, InvestigationStateArtifact, LLMRequestArtifact, LLMResponseArtifact, LogBundleArtifact, MergedTimelineArtifact, PersonaContributionArtifact, PhaseStateArtifact, SourceLocationArtifact
from .store_parts.artifact_ops import ArtifactOpsMixin
from .store_parts.artifacts import ArtifactQueriesMixin
from .store_parts.audit import AuditQueriesMixin
from .store_parts.binder_io import BinderIoMixin
from .store_parts.calibration import CalibrationQueriesMixin
from .store_parts.llm import LlmTraceabilityMixin
from .store_parts.patterns import PatternQueriesMixin
from .store_parts.state import InvestigationStateQueriesMixin
logger = logging.getLogger(__name__)

def _json_serializer(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(mode='json')
    if hasattr(obj, 'value'):
        return obj.value
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')

class BinderStore(BinderIoMixin, ArtifactOpsMixin, AuditQueriesMixin, PatternQueriesMixin, CalibrationQueriesMixin, ArtifactQueriesMixin, LlmTraceabilityMixin, InvestigationStateQueriesMixin):
    SCHEMA = """
    -- Work binders table
    CREATE TABLE IF NOT EXISTS work_binders (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        status TEXT DEFAULT 'active'
    );

    -- Artifacts table (polymorphic with soft delete)
    CREATE TABLE IF NOT EXISTS binder_artifacts (
        id TEXT PRIMARY KEY,
        binder_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        phase INTEGER,
        function_name TEXT,
        priority TEXT DEFAULT 'normal',
        tags_json TEXT,
        content_json TEXT NOT NULL,
        is_deleted BOOLEAN DEFAULT FALSE,
        deleted_by TEXT,
        deleted_reason TEXT,
        FOREIGN KEY (binder_id) REFERENCES work_binders(id) ON DELETE CASCADE
    );

    -- Artifact history table (tracks all modifications)
    CREATE TABLE IF NOT EXISTS artifact_history (
        id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        modified_by TEXT NOT NULL,
        modified_at TIMESTAMP NOT NULL,
        action TEXT NOT NULL,
        changes_json TEXT NOT NULL,
        FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
    );

    -- Tags table (many-to-many for efficient tag queries)
    CREATE TABLE IF NOT EXISTS artifact_tags (
        artifact_id TEXT NOT NULL,
        tag TEXT NOT NULL,
        PRIMARY KEY (artifact_id, tag),
        FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
    );

    -- Annotations table (separate for efficient queries)
    CREATE TABLE IF NOT EXISTS artifact_annotations (
        id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        target_artifact_id TEXT NOT NULL,
        created_by TEXT NOT NULL,
        annotation_type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
    );

    -- Audit log table (tracks all artifact access for traceability)
    CREATE TABLE IF NOT EXISTS binder_audit_log (
        id TEXT PRIMARY KEY,
        binder_id TEXT NOT NULL,
        persona_name TEXT NOT NULL,
        phase_number INTEGER,
        timestamp TIMESTAMP NOT NULL,
        access_sequence INTEGER NOT NULL,
        operation_type TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        artifact_id TEXT,
        method_name TEXT NOT NULL,
        result_count INTEGER DEFAULT 1,
        success BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (binder_id) REFERENCES work_binders(id) ON DELETE CASCADE
    );

    -- Indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_binder
        ON binder_artifacts(binder_id);
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_type
        ON binder_artifacts(artifact_type);
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_phase
        ON binder_artifacts(phase);
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_function
        ON binder_artifacts(function_name);
    CREATE INDEX IF NOT EXISTS idx_artifact_tags_tag
        ON artifact_tags(tag);
    CREATE INDEX IF NOT EXISTS idx_binders_investigation
        ON work_binders(investigation_id);
    CREATE INDEX IF NOT EXISTS idx_binders_status
        ON work_binders(status);
    CREATE INDEX IF NOT EXISTS idx_annotations_target
        ON artifact_annotations(target_artifact_id);
    CREATE INDEX IF NOT EXISTS idx_audit_log_binder
        ON binder_audit_log(binder_id);
    CREATE INDEX IF NOT EXISTS idx_audit_log_persona
        ON binder_audit_log(persona_name);
    CREATE INDEX IF NOT EXISTS idx_audit_log_phase
        ON binder_audit_log(phase_number);
    CREATE INDEX IF NOT EXISTS idx_audit_log_sequence
        ON binder_audit_log(binder_id, access_sequence);
    """
    ARTIFACT_CLASSES: dict[ArtifactType, type[Artifact]] = {ArtifactType.CALL_GRAPH: CallGraphNode, ArtifactType.CODE_SNIPPET: CodeSnippet, ArtifactType.FINDING: Finding, ArtifactType.ANNOTATION: Annotation, ArtifactType.SOURCE_LOCATION: SourceLocationArtifact, ArtifactType.ERROR_CONTEXT: ErrorContextArtifact, ArtifactType.LLM_REQUEST: LLMRequestArtifact, ArtifactType.LLM_RESPONSE: LLMResponseArtifact, ArtifactType.FLOW_CONFIG: FlowConfigArtifact, ArtifactType.PHASE_STATE: PhaseStateArtifact, ArtifactType.INVESTIGATION_STATE: InvestigationStateArtifact, ArtifactType.PERSONA_CONTRIBUTION: PersonaContributionArtifact, ArtifactType.HYPOTHESIS_ARTIFACT: HypothesisArtifact, ArtifactType.EVIDENCE_ARTIFACT: EvidenceArtifact, ArtifactType.CAUSAL_CHAIN: CausalChainArtifact, ArtifactType.CHALLENGE: ChallengeArtifact, ArtifactType.CONCLUSION: ConclusionArtifact, ArtifactType.FUNCTION_SUMMARY: FunctionSummaryArtifact, ArtifactType.LOG_BUNDLE: LogBundleArtifact, ArtifactType.MERGED_TIMELINE: MergedTimelineArtifact, ArtifactType.BOARDREADER_IDENTIFICATION: BoardReaderIdentificationArtifact, ArtifactType.FEEDBACK: FeedbackArtifact}

    def __init__(self, db_path: Path | str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False