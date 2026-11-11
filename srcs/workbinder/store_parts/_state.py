"""
File: _state.py
Purpose: Shared state and cross-mixin surface for the BinderStore mixins.
Category: Utility
Author: artdaq team
Depends: None
Exports: StoreState
Complexity: Low | Lines: 39
"""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
if TYPE_CHECKING:
    from ..artifacts import Artifact
    from ..binder import WorkBinder

class StoreState:
    _db_path: Path
    _initialized: bool
    SCHEMA: ClassVar[str]
    ARTIFACT_CLASSES: dict[Any, Any]

    async def _ensure_initialized(self) -> None:
        raise NotImplementedError

    async def save_binder(self, binder: WorkBinder) -> None:
        raise NotImplementedError

    async def load_binder(self, binder_id: str) -> WorkBinder | None:
        raise NotImplementedError

    async def load_binder_for_investigation(self, investigation_id: str) -> WorkBinder | None:
        raise NotImplementedError

    def _row_to_artifact(self, row: Any) -> Artifact | None:
        raise NotImplementedError

    async def get_binder_id_for_investigation(self, investigation_id: str) -> str | None:
        raise NotImplementedError

    async def list_binders(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def query_artifacts(self, *args: Any, **kwargs: Any) -> list[Artifact]:
        raise NotImplementedError

    async def _save_artifact(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError