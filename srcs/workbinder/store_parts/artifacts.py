"""
File: artifacts.py
Purpose: Typed queries for hypotheses, evidence, chains and challenges.
Category: Utility
Author: artdaq team
Depends: None
Exports: ArtifactQueriesMixin
Complexity: Low | Lines: 60
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from ..artifacts import Artifact
from ._state import StoreState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class ArtifactQueriesMixin(StoreState):

    async def get_hypotheses(self, binder_id: str, min_score: float | None=None, source: str | None=None, limit: int=50) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='hypothesis_artifact', limit=limit)
        result = []
        for artifact in artifacts:
            if hasattr(artifact, 'score') and min_score is not None:
                if artifact.score < min_score:
                    continue
            if hasattr(artifact, 'source') and source is not None:
                if artifact.source != source:
                    continue
            result.append(artifact)
        return result

    async def get_evidence_items(self, binder_id: str, evidence_type: str | None=None, strength: str | None=None, limit: int=100) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='evidence_artifact', limit=limit)
        result = []
        for artifact in artifacts:
            if hasattr(artifact, 'evidence_type') and evidence_type is not None:
                if artifact.evidence_type != evidence_type:
                    continue
            if hasattr(artifact, 'strength') and strength is not None:
                if artifact.strength != strength:
                    continue
            result.append(artifact)
        return result

    async def get_causal_chains(self, binder_id: str, hypothesis_id: str | None=None, limit: int=20) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='causal_chain', limit=limit)
        if hypothesis_id is not None:
            result = []
            for artifact in artifacts:
                if hasattr(artifact, 'hypothesis_id'):
                    if artifact.hypothesis_id == hypothesis_id:
                        result.append(artifact)
            return result
        return artifacts

    async def get_challenges(self, binder_id: str, resolved: bool | None=None, severity: str | None=None, limit: int=50) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type='challenge', limit=limit)
        result = []
        for artifact in artifacts:
            if resolved is not None and hasattr(artifact, 'resolved'):
                if artifact.resolved != resolved:
                    continue
            if severity is not None and hasattr(artifact, 'severity'):
                if artifact.severity != severity:
                    continue
            result.append(artifact)
        return result