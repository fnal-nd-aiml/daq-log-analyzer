"""
File: errors.py
Purpose: Exception classes for source repository management.
Category: Utility
Author: artdaq team
Depends: None
Exports: SourceError, CloneError, UpdateError, AuthenticationError, ConfigurationError
Complexity: Medium | Lines: 29
"""

class SourceError(Exception):
    pass

class CloneError(SourceError):

    def __init__(self, url: str, message: str):
        self.url = url
        self.message = message
        super().__init__(f'Failed to clone {url}: {message}')

class UpdateError(SourceError):

    def __init__(self, repo_path: str, message: str):
        self.repo_path = repo_path
        self.message = message
        super().__init__(f'Failed to update {repo_path}: {message}')

class AuthenticationError(SourceError):

    def __init__(self, url: str, message: str):
        self.url = url
        self.message = message
        super().__init__(f'Authentication failed for {url}: {message}')

class ConfigurationError(SourceError):

    def __init__(self, message: str):
        self.message = message
        super().__init__(f'Source configuration error: {message}')