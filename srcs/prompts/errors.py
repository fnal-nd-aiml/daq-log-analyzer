"""
File: errors.py
Purpose: Custom exceptions for the prompts module.
Category: Utility
Author: artdaq team
Depends: None
Exports: PromptError, PromptNotFoundError, MissingPlaceholderError, UnexpectedPlaceholderError, IncludeCycleError, ...
Complexity: Medium | Lines: 40
"""

class PromptError(Exception):
    pass

class PromptNotFoundError(PromptError):

    def __init__(self, prompt_type: str, path: str) -> None:
        self.prompt_type = prompt_type
        self.path = path
        super().__init__(f'Prompt not found: {prompt_type} at {path}')

class MissingPlaceholderError(PromptError):

    def __init__(self, prompt_type: str, missing: frozenset[str]) -> None:
        self.prompt_type = prompt_type
        self.missing = missing
        missing_str = ', '.join(sorted(missing))
        super().__init__(f'Missing required placeholder(s) for {prompt_type}: {missing_str}')

class UnexpectedPlaceholderError(PromptError):

    def __init__(self, prompt_type: str, unexpected: frozenset[str]) -> None:
        self.prompt_type = prompt_type
        self.unexpected = unexpected
        unexpected_str = ', '.join(sorted(unexpected))
        super().__init__(f'Unexpected placeholder(s) for {prompt_type}: {unexpected_str}')

class IncludeCycleError(PromptError):

    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        cycle_str = ' -> '.join(cycle_path)
        super().__init__(f'Circular include detected: {cycle_str}')

class IncludeNotFoundError(PromptError):

    def __init__(self, include_path: str, referenced_from: str) -> None:
        self.include_path = include_path
        self.referenced_from = referenced_from
        super().__init__(f'Include not found: {include_path} (referenced from {referenced_from})')
__all__ = ['PromptError', 'PromptNotFoundError', 'MissingPlaceholderError', 'UnexpectedPlaceholderError', 'IncludeCycleError', 'IncludeNotFoundError']