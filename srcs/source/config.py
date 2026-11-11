"""
File: config.py
Purpose: Pydantic configuration models for source repository management.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: RepositoryConfig, AuthConfig, SourceConfig
Complexity: Low | Lines: 53
"""

import os
import re
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

class RepositoryConfig(BaseModel):
    url: str = Field(..., description='Git repository URL (HTTPS or SSH)')
    branch: str | None = Field(None, description='Branch to clone/checkout (default: repo default)')
    sparse_paths: list[str] | None = Field(None, description='Paths for sparse checkout (clone only these directories)')
    timeout: int = Field(300, description='Git operation timeout in seconds')

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        https_pattern = '^https?://[^\\s/$.?#].[^\\s]*\\.git$'
        ssh_pattern = '^git@[^\\s:]+:[^\\s]+\\.git$'
        if not (re.match(https_pattern, v) or re.match(ssh_pattern, v)):
            raise ValueError(f'Invalid repository URL: {v}. Must be HTTPS (https://...) or SSH (git@...) URL ending in .git')
        return v

    def get_repo_name(self) -> str:
        name = self.url.rstrip('/').removesuffix('.git')
        return name.split('/')[-1].split(':')[-1]

class AuthConfig(BaseModel):
    github_token: str | None = Field(None, description='GitHub personal access token for HTTPS authentication')
    ssh_key_path: str | None = Field(None, description='Path to SSH private key')
    allow_insecure_ssh: bool = Field(False, description='Disable SSH host key verification (insecure, use only for testing)')

    def get_github_token(self) -> str | None:
        if self.github_token:
            return self.github_token
        return os.environ.get('ARTDAQ_GITHUB_TOKEN')

    def get_ssh_key_path(self) -> Path | None:
        if self.ssh_key_path:
            path = Path(self.ssh_key_path).expanduser()
            if path.exists():
                return path
        return None

class SourceConfig(BaseModel):
    repos_path: str = Field('./data/repos', description='Directory to store cloned repositories')
    repositories: list[RepositoryConfig] = Field(default_factory=list, description='List of repositories to clone')
    auth: AuthConfig = Field(default_factory=AuthConfig, description='Authentication settings')
    auto_update: bool = Field(True, description='Automatically update repos during init')
    auto_index: bool = Field(True, description='Automatically index repos after clone/update')

    def get_repos_path(self) -> Path:
        return Path(self.repos_path).resolve()

    def has_repositories(self) -> bool:
        return len(self.repositories) > 0