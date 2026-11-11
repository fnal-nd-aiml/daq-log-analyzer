"""
File: errors.py
Purpose: Exception classes for knowledge module.
Category: Utility
Author: artdaq team
Depends: None
Exports: KnowledgeError, PatternNotFoundError, InvestigationNotFoundError, StorageError, CalibrationError
Complexity: Medium | Lines: 27
"""

class KnowledgeError(Exception):
    pass

class PatternNotFoundError(KnowledgeError):

    def __init__(self, pattern_id: str):
        self.pattern_id = pattern_id
        super().__init__(f'Pattern not found: {pattern_id}')

class InvestigationNotFoundError(KnowledgeError):

    def __init__(self, investigation_id: str):
        self.investigation_id = investigation_id
        super().__init__(f'Investigation not found: {investigation_id}')

class StorageError(KnowledgeError):

    def __init__(self, operation: str, message: str):
        self.operation = operation
        self.message = message
        super().__init__(f'Storage error during {operation}: {message}')

class CalibrationError(KnowledgeError):

    def __init__(self, message: str):
        self.message = message
        super().__init__(f'Calibration error: {message}')