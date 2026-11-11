"""
File: errors.py
Purpose: Exception classes for extraction module.
Category: Utility
Author: artdaq team
Depends: None
Exports: ExtractionError, ParseError, IndexError, SourceLocatorError
Complexity: Medium | Lines: 22
"""

class ExtractionError(Exception):
    pass

class ParseError(ExtractionError):

    def __init__(self, file_path: str, message: str):
        self.file_path = file_path
        self.message = message
        super().__init__(f'Parse error in {file_path}: {message}')

class IndexError(ExtractionError):

    def __init__(self, message: str):
        self.message = message
        super().__init__(f'Index error: {message}')

class SourceLocatorError(ExtractionError):

    def __init__(self, message: str, error_text: str | None=None):
        self.message = message
        self.error_text = error_text
        super().__init__(f'Source locator error: {message}')