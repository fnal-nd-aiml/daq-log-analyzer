"""
File: crud.py
Purpose: Core artifact CRUD, indexing and generic queries.
Category: Utility
Author: artdaq team
Depends: None
Exports: ArtifactCrudMixin
Complexity: Medium | Lines: 159
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from ..artifacts import Annotation, Artifact, ArtifactHistory, ArtifactType, Finding
from ._state import BinderState
from .query import BinderQuery
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class ArtifactCrudMixin(BinderState):

    def add_artifact(self, artifact: Artifact, record_history: bool=True) -> str:
        self._artifacts[artifact.id] = artifact
        self.updated_at = datetime.now()
        for tag in artifact.tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = set()
            self._tags_index[tag].add(artifact.id)
        if artifact.function_name:
            if artifact.function_name not in self._function_index:
                self._function_index[artifact.function_name] = set()
            self._function_index[artifact.function_name].add(artifact.id)
        if record_history:
            self._history.append(ArtifactHistory(artifact_id=artifact.id, modified_by=artifact.created_by, action='create', changes={'artifact': artifact.model_dump()}))
        return artifact.id

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def update_artifact(self, artifact_id: str, updates: dict[str, Any], modified_by: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        before = {}
        after = {}
        for field_name, new_value in updates.items():
            if hasattr(artifact, field_name):
                before[field_name] = getattr(artifact, field_name)
                setattr(artifact, field_name, new_value)
                after[field_name] = new_value
        artifact.updated_at = datetime.now()
        self.updated_at = datetime.now()
        if 'tags' in updates:
            for tag in before.get('tags', []):
                if tag in self._tags_index:
                    self._tags_index[tag].discard(artifact_id)
            for tag in updates['tags']:
                if tag not in self._tags_index:
                    self._tags_index[tag] = set()
                self._tags_index[tag].add(artifact_id)
        if 'function_name' in updates:
            old_func = before.get('function_name')
            new_func = updates['function_name']
            if old_func and old_func in self._function_index:
                self._function_index[old_func].discard(artifact_id)
            if new_func:
                if new_func not in self._function_index:
                    self._function_index[new_func] = set()
                self._function_index[new_func].add(artifact_id)
        self._history.append(ArtifactHistory(artifact_id=artifact_id, modified_by=modified_by, action='update', changes={'before': before, 'after': after}))
        return True

    def mark_deleted(self, artifact_id: str, deleted_by: str, reason: str | None=None) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        artifact.is_deleted = True
        artifact.deleted_by = deleted_by
        artifact.deleted_reason = reason
        artifact.updated_at = datetime.now()
        self.updated_at = datetime.now()
        self._history.append(ArtifactHistory(artifact_id=artifact_id, modified_by=deleted_by, action='delete', changes={'reason': reason}))
        return True

    def restore_artifact(self, artifact_id: str, restored_by: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return False
        artifact.is_deleted = False
        artifact.deleted_by = None
        artifact.deleted_reason = None
        artifact.updated_at = datetime.now()
        self.updated_at = datetime.now()
        self._history.append(ArtifactHistory(artifact_id=artifact_id, modified_by=restored_by, action='restore', changes={}))
        return True

    def query(self, query: BinderQuery) -> list[Artifact]:
        results = []
        for artifact in self._artifacts.values():
            if artifact.is_deleted and (not query.include_deleted):
                continue
            if query.artifact_type and artifact.artifact_type != query.artifact_type:
                continue
            if query.created_by and artifact.created_by != query.created_by:
                continue
            if query.phase is not None and artifact.phase != query.phase:
                continue
            if query.function_name and artifact.function_name != query.function_name:
                continue
            if query.priority and artifact.priority != query.priority:
                continue
            if query.tags:
                if not all((tag in artifact.tags for tag in query.tags)):
                    continue
            results.append(artifact)
        return results[query.offset:query.offset + query.limit]

    def get_by_type(self, artifact_type: ArtifactType) -> list[Artifact]:
        return self.query(BinderQuery(artifact_type=artifact_type))

    def get_by_tag(self, tag: str) -> list[Artifact]:
        artifact_ids = self._tags_index.get(tag, set())
        return [self._artifacts[aid] for aid in artifact_ids if aid in self._artifacts and (not self._artifacts[aid].is_deleted)]

    def get_by_function(self, function_name: str) -> list[Artifact]:
        artifact_ids = self._function_index.get(function_name, set())
        return [self._artifacts[aid] for aid in artifact_ids if aid in self._artifacts and (not self._artifacts[aid].is_deleted)]

    def get_history(self, artifact_id: str | None=None) -> list[ArtifactHistory]:
        if artifact_id:
            return [h for h in self._history if h.artifact_id == artifact_id]
        return list(self._history)

    def get_annotations(self, artifact_id: str) -> list[Annotation]:
        annotations = []
        for artifact in self._artifacts.values():
            if isinstance(artifact, Annotation) and artifact.target_artifact_id == artifact_id and (not artifact.is_deleted):
                annotations.append(artifact)
        return annotations

    def get_related_artifacts(self, artifact_id: str) -> list[Artifact]:
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return []
        related = set()
        for a in self._artifacts.values():
            if a.is_deleted or a.id == artifact_id:
                continue
            if isinstance(a, Finding) and artifact_id in a.related_artifacts:
                related.add(a.id)
            if isinstance(a, Annotation) and a.target_artifact_id == artifact_id:
                related.add(a.id)
            if artifact.function_name and a.function_name == artifact.function_name:
                related.add(a.id)
        return [self._artifacts[aid] for aid in related]

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for artifact in self._artifacts.values():
            if artifact.is_deleted:
                continue
            type_name = artifact.artifact_type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts

    def get_all_tags(self) -> list[str]:
        return list(self._tags_index.keys())