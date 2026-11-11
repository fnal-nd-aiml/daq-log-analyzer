"""
File: base.py
Purpose: Base utilities for all models.
Category: Data
Author: artdaq team
Depends: pydantic
Exports: BaseModelConfig, generate_id
Complexity: Low | Lines: 8
"""

import uuid
from pydantic import BaseModel, ConfigDict

def generate_id() -> str:
    return str(uuid.uuid4()).replace('-', '')[:16]

class BaseModelConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)