"""
File: relevance.py
Purpose: Relevance - Per-persona artifact profiles and relevance-based selec...
Category: Utility
Author: artdaq team
Depends: None
Exports: ArtifactProfile, select_artifacts, render_selected_artifacts
Complexity: Medium | Lines: 125
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
from .artifact_renderer import render_artifact
from .artifacts_types import Artifact, ArtifactType

if TYPE_CHECKING:
    from .binder import WorkBinder


@dataclass
class ArtifactProfile:
    artifact_type: ArtifactType
    base_priority: float
    max_count: int


PERSONA_PROFILES: dict[str, list[ArtifactProfile]] = {
    "theorist": [
        ArtifactProfile(ArtifactType.FUNCTION_SUMMARY, 0.9, 5),
        ArtifactProfile(ArtifactType.CODE_SNIPPET, 0.8, 3),
        ArtifactProfile(ArtifactType.CALL_GRAPH, 0.8, 3),
        ArtifactProfile(ArtifactType.SOURCE_LOCATION, 0.7, 3),
        ArtifactProfile(ArtifactType.FINDING, 0.7, 5),
        ArtifactProfile(ArtifactType.ERROR_CONTEXT, 0.6, 1),
    ],
    "logician": [
        ArtifactProfile(ArtifactType.FUNCTION_SUMMARY, 1.0, 5),
        ArtifactProfile(ArtifactType.CALL_GRAPH, 0.9, 3),
        ArtifactProfile(ArtifactType.CODE_SNIPPET, 0.9, 5),
        ArtifactProfile(ArtifactType.HYPOTHESIS_ARTIFACT, 0.8, 5),
        ArtifactProfile(ArtifactType.EVIDENCE_ARTIFACT, 0.8, 10),
        ArtifactProfile(ArtifactType.SOURCE_LOCATION, 0.7, 3),
    ],
    "skeptic": [
        ArtifactProfile(ArtifactType.CAUSAL_CHAIN, 1.0, 5),
        ArtifactProfile(ArtifactType.HYPOTHESIS_ARTIFACT, 0.9, 5),
        ArtifactProfile(ArtifactType.EVIDENCE_ARTIFACT, 0.9, 10),
        ArtifactProfile(ArtifactType.FUNCTION_SUMMARY, 0.8, 5),
        ArtifactProfile(ArtifactType.CODE_SNIPPET, 0.8, 3),
        ArtifactProfile(ArtifactType.CALL_GRAPH, 0.7, 3),
    ],
    "judge": [
        ArtifactProfile(ArtifactType.HYPOTHESIS_ARTIFACT, 1.0, 5),
        ArtifactProfile(ArtifactType.EVIDENCE_ARTIFACT, 1.0, 10),
        ArtifactProfile(ArtifactType.CAUSAL_CHAIN, 0.9, 5),
        ArtifactProfile(ArtifactType.CHALLENGE, 0.9, 10),
        ArtifactProfile(ArtifactType.PERSONA_CONTRIBUTION, 0.7, 3),
    ],
    "synthesizer": [
        ArtifactProfile(ArtifactType.HYPOTHESIS_ARTIFACT, 1.0, 5),
        ArtifactProfile(ArtifactType.EVIDENCE_ARTIFACT, 1.0, 10),
        ArtifactProfile(ArtifactType.CAUSAL_CHAIN, 0.9, 5),
        ArtifactProfile(ArtifactType.CHALLENGE, 0.9, 10),
        ArtifactProfile(ArtifactType.CODE_SNIPPET, 0.8, 3),
        ArtifactProfile(ArtifactType.FUNCTION_SUMMARY, 0.8, 5),
        ArtifactProfile(ArtifactType.FEEDBACK, 0.7, 5),
        ArtifactProfile(ArtifactType.CALL_GRAPH, 0.7, 3),
        ArtifactProfile(ArtifactType.SOURCE_LOCATION, 0.7, 3),
        ArtifactProfile(ArtifactType.FINDING, 0.6, 5),
        ArtifactProfile(ArtifactType.PERSONA_CONTRIBUTION, 0.6, 3),
        ArtifactProfile(ArtifactType.LOG_BUNDLE, 0.5, 1),
    ],
    "detective": [
        ArtifactProfile(ArtifactType.LOG_BUNDLE, 0.9, 1),
        ArtifactProfile(ArtifactType.ERROR_CONTEXT, 0.9, 1),
        ArtifactProfile(ArtifactType.SOURCE_LOCATION, 0.8, 3),
        ArtifactProfile(ArtifactType.CALL_GRAPH, 0.8, 3),
        ArtifactProfile(ArtifactType.CODE_SNIPPET, 0.8, 5),
        ArtifactProfile(ArtifactType.FUNCTION_SUMMARY, 0.9, 5),
        ArtifactProfile(ArtifactType.FINDING, 0.7, 5),
        ArtifactProfile(ArtifactType.HYPOTHESIS_ARTIFACT, 1.0, 10),
        ArtifactProfile(ArtifactType.EVIDENCE_ARTIFACT, 0.8, 10),
    ],
    "learner": [
        ArtifactProfile(ArtifactType.HYPOTHESIS_ARTIFACT, 1.0, 5),
        ArtifactProfile(ArtifactType.EVIDENCE_ARTIFACT, 0.9, 10),
        ArtifactProfile(ArtifactType.FEEDBACK, 1.0, 10),
        ArtifactProfile(ArtifactType.CAUSAL_CHAIN, 0.8, 3),
        ArtifactProfile(ArtifactType.CHALLENGE, 0.7, 5),
        ArtifactProfile(ArtifactType.CONCLUSION, 1.0, 1),
    ],
}


def select_artifacts(binder: WorkBinder, persona: str, artifact_type: ArtifactType | None = None) -> list[Artifact]:
    profile = PERSONA_PROFILES.get(persona.lower(), [])
    if not profile:
        return []
    profile_map: dict[ArtifactType, ArtifactProfile] = {p.artifact_type: p for p in profile}
    if artifact_type is not None:
        if artifact_type not in profile_map:
            return []
        profile_map = {artifact_type: profile_map[artifact_type]}
    all_artifacts = [a for a in binder._artifacts.values() if not a.is_deleted and a.artifact_type in profile_map]
    if all_artifacts:
        timestamps = [a.created_at.timestamp() for a in all_artifacts]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        ts_range = max_ts - min_ts if max_ts > min_ts else 1.0
        scored: list[tuple[float, Artifact]] = []
        for artifact in all_artifacts:
            prof = profile_map[artifact.artifact_type]
            recency = (artifact.created_at.timestamp() - min_ts) / ts_range
            score = prof.base_priority * 0.8 + recency * 0.2
            scored.append((score, artifact))
        scored.sort(key=lambda x: x[0], reverse=True)
    else:
        scored = []
    type_counts: dict[ArtifactType, int] = {}
    result: list[Artifact] = []
    for _score, artifact in scored:
        atype = artifact.artifact_type
        current = type_counts.get(atype, 0)
        if current < profile_map[atype].max_count:
            result.append(artifact)
            type_counts[atype] = current + 1
    return result


def render_selected_artifacts(binder: WorkBinder, persona: str, artifact_type: ArtifactType | None = None) -> str:
    artifacts = select_artifacts(binder, persona, artifact_type)
    if not artifacts:
        return ""
    return "\n\n".join((render_artifact(a) for a in artifacts))
