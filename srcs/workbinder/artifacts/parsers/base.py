"""
File: base.py
Purpose: Base parser abstract class for LLM response parsing.
Category: Utility
Author: artdaq team
Depends: artifacts_types, pydantic
Exports: BaseParser
Complexity: Low | Lines: 21
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar
from pydantic import BaseModel
from srcs.workbinder.artifacts_types import Artifact
LLMResponseT = TypeVar('LLMResponseT', bound=BaseModel)
DomainModelT = TypeVar('DomainModelT')
ArtifactT = TypeVar('ArtifactT', bound=Artifact)

class BaseParser(ABC, Generic[LLMResponseT, DomainModelT, ArtifactT]):

    @abstractmethod
    def parse_llm_response(self, raw_json: str) -> LLMResponseT:
        ...

    @abstractmethod
    def to_domain_model(self, item: Any, **context: Any) -> DomainModelT:
        ...

    @abstractmethod
    def to_artifact(self, domain_model: Any, created_by: str, phase: int, **kwargs: Any) -> ArtifactT:
        ...