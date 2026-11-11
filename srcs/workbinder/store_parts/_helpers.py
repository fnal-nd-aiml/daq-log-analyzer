"""
File: _helpers.py
Purpose: Serialization helpers shared by the BinderStore mixins.
Category: Utility
Author: artdaq team
Depends: None
Exports: None
Complexity: Low | Lines: 12
"""

from __future__ import annotations
from datetime import datetime
from typing import Any

def _json_serializer(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(mode='json')
    if hasattr(obj, 'value'):
        return obj.value
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')