"""
File: errors.py
Purpose: Exception classes for agent module.
Category: Utility
Author: artdaq team
Depends: None
Exports: AgentError, InvestigationError, HypothesisError, EvidenceError, CausalChainError, ...
Complexity: Medium | Lines: 64
"""

class AgentError(Exception):
    pass


class InvestigationError(AgentError):

    def __init__(self, investigation_id: str, phase: str, message: str):
        self.investigation_id = investigation_id
        self.phase = phase
        self.message = message
        super().__init__(f"Investigation {investigation_id} failed in {phase}: {message}")


class HypothesisError(AgentError):

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Hypothesis error: {message}")


class EvidenceError(AgentError):

    def __init__(self, query_type: str, message: str):
        self.query_type = query_type
        self.message = message
        super().__init__(f"Evidence error ({query_type}): {message}")


class CausalChainError(AgentError):

    def __init__(self, hypothesis_id: str, message: str):
        self.hypothesis_id = hypothesis_id
        self.message = message
        super().__init__(f"Causal chain error for hypothesis {hypothesis_id}: {message}")


class PhaseExecutionError(AgentError):

    def __init__(self, phase: int, persona: str, message: str, cause: Exception | None = None):
        self.phase = phase
        self.persona = persona
        self.message = message
        self.cause = cause
        super().__init__(f"Phase {phase} ({persona}) failed: {message}")


class LLMGenerationError(AgentError):

    def __init__(self, prompt_key: str, message: str, raw_response: str | None = None, cause: Exception | None = None):
        self.prompt_key = prompt_key
        self.message = message
        self.raw_response = raw_response
        self.cause = cause
        super().__init__(f"LLM generation error ({prompt_key}): {message}")


class ToolExecutionError(AgentError):

    def __init__(self, tool_name: str, query: str, message: str, cause: Exception | None = None):
        self.tool_name = tool_name
        self.query = query
        self.message = message
        self.cause = cause
        super().__init__(f"Tool {tool_name} failed on '{query}': {message}")
