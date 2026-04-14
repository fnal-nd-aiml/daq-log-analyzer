"""
File: errors.py
Purpose: Exception classes for LLM module.
Category: Utility
Author: artdaq team
Depends: None
Exports: LLMError, ProviderError, GenerationError, EmbeddingError, StructuredOutputError
Complexity: Medium | Lines: 41
"""

class LLMError(Exception):
    pass


class ProviderError(LLMError):

    def __init__(self, provider: str, message: str):
        self.provider = provider
        self.message = message
        super().__init__(f"LLM provider error ({provider}): {message}")


class GenerationError(LLMError):

    def __init__(self, message: str, prompt: str | None = None):
        self.message = message
        self.prompt = prompt
        super().__init__(f"Generation error: {message}")


class EmbeddingError(LLMError):

    def __init__(self, message: str):
        self.message = message
        super().__init__(f"Embedding error: {message}")


class StructuredOutputError(LLMError):

    def __init__(
        self, message: str, raw_response: str, expected_schema: str | None = None, model_name: str | None = None
    ):
        self.message = message
        self.raw_response = raw_response
        self.expected_schema = expected_schema
        self.model_name = model_name
        super().__init__(message)

    def __str__(self) -> str:
        preview = self.raw_response[:500] if self.raw_response else "(empty)"
        return f"{self.message}\nRaw response:\n{preview}..."
