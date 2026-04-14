"""
File: executor.py
Purpose: Phase executor base class and registry.
Category: Utility
Author: artdaq team
Depends: None
Exports: PhaseExecutor, ExecutorRegistry
Complexity: Low | Lines: 32
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class PhaseExecutor(ABC):

    @property
    @abstractmethod
    def executor_id(self) -> str:
        pass

    @abstractmethod
    async def execute(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        pass


class ExecutorRegistry:

    def __init__(self) -> None:
        self._executors: dict[str, PhaseExecutor] = {}

    def register(self, executor: PhaseExecutor) -> None:
        self._executors[executor.executor_id] = executor

    def get(self, executor_id: str) -> PhaseExecutor | None:
        return self._executors.get(executor_id)

    def list_executors(self) -> list[str]:
        return list(self._executors.keys())
