"""
File: contracts.py
Purpose: Data contracts for pipeline data flow.
Category: Utility
Author: artdaq team
Depends: models
Exports: DataContractError, DataContracts
Complexity: Medium | Lines: 91
"""

from typing import Any
from srcs.models import (
    CausalChain,
    Challenge,
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationOutcome,
    InvestigationResult,
    Log,
    PriorKnowledge,
)


class DataContractError(Exception):

    def __init__(self, key: str, expected: type, got: type, message: str | None = None):
        self.key = key
        self.expected = expected
        self.got = got
        self.message = message or f"Data contract violation for '{key}': expected {expected}, got {got}"
        super().__init__(self.message)


class DataContracts:
    CONTRACTS: dict[str, type] = {
        "trigger_error": Log,
        "context_logs": list,
        "prior_knowledge": PriorKnowledge,
        "hypotheses": list,
        "evidence": Evidence,
        "causal_chains": list,
        "challenges": list,
        "outcome": InvestigationOutcome,
        "result": InvestigationResult,
        "patterns": list,
        "source_files": list,
        "investigation": Investigation,
    }
    DETAILED_CONTRACTS: dict[str, tuple[type, type | None]] = {
        "trigger_error": (Log, None),
        "context_logs": (list, Log),
        "prior_knowledge": (PriorKnowledge, None),
        "hypotheses": (list, Hypothesis),
        "evidence": (Evidence, None),
        "causal_chains": (list, CausalChain),
        "challenges": (list, Challenge),
        "outcome": (InvestigationOutcome, None),
        "result": (InvestigationResult, None),
        "investigation": (Investigation, None),
    }

    @classmethod
    def validate(cls, key: str, value: Any, strict: bool = False) -> None:
        if key not in cls.CONTRACTS:
            return
        expected = cls.CONTRACTS[key]
        if value is None:
            return
        if not isinstance(value, expected):
            raise DataContractError(key, expected, type(value))
        if strict and key in cls.DETAILED_CONTRACTS:
            container_type, element_type = cls.DETAILED_CONTRACTS[key]
            if container_type is list and element_type is not None and isinstance(value, list):
                cls._validate_list_elements(key, value, element_type)

    @classmethod
    def _validate_list_elements(cls, key: str, value: list, element_type: type) -> None:
        for i, item in enumerate(value):
            if not isinstance(item, element_type):
                raise DataContractError(
                    key,
                    element_type,
                    type(item),
                    f"Data contract violation for '{key}[{i}]': expected {element_type.__name__}, got {type(item).__name__}",
                )

    @classmethod
    def validate_context(cls, context: dict[str, Any], strict: bool = False) -> None:
        for key, value in context.items():
            cls.validate(key, value, strict=strict)

    @classmethod
    def get_contract(cls, key: str) -> type | None:
        return cls.CONTRACTS.get(key)

    @classmethod
    def register(cls, key: str, expected_type: type, element_type: type | None = None) -> None:
        cls.CONTRACTS[key] = expected_type
        if element_type is not None:
            cls.DETAILED_CONTRACTS[key] = (expected_type, element_type)
