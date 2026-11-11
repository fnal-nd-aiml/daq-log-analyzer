"""
File: manager.py
Purpose: Repository manager for cloning and updating source repositories.
Category: Utility
Author: artdaq team
Depends: None
Exports: RepoStatus, SyncResult, RepositoryManager
Complexity: Medium | Lines: 169
"""

import logging
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from .config import RepositoryConfig, SourceConfig
from .errors import AuthenticationError, CloneError, UpdateError
logger = logging.getLogger(__name__)

@dataclass
class RepoStatus:
    path: Path
    branch: str
    commit: str
    commit_date: str
    is_dirty: bool

@dataclass
class SyncResult:
    repo_name: str
    success: bool
    action: str
    message: str
    path: Path | None = None

class RepositoryManager:

    def __init__(self, config: SourceConfig):
        self.config = config
        self.repos_path = config.get_repos_path()

    def sync_all(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        if not self.config.has_repositories():
            logger.info('No repositories configured')
            return results
        self.repos_path.mkdir(parents=True, exist_ok=True)
        for repo_config in self.config.repositories:
            result = self._sync_repo(repo_config)
            results.append(result)
        return results

    def _sync_repo(self, repo_config: RepositoryConfig) -> SyncResult:
        repo_name = repo_config.get_repo_name()
        repo_path = self.repos_path / repo_name
        try:
            if repo_path.exists() and (repo_path / '.git').exists():
                if self.config.auto_update:
                    self._update_repo(repo_path, repo_config)
                    return SyncResult(repo_name=repo_name, success=True, action='updated', message=f'Updated {repo_name}', path=repo_path)
                else:
                    return SyncResult(repo_name=repo_name, success=True, action='skipped', message=f'Skipped {repo_name} (auto_update disabled)', path=repo_path)
            else:
                self._clone_repo(repo_config, repo_path)
                return SyncResult(repo_name=repo_name, success=True, action='cloned', message=f'Cloned {repo_name}', path=repo_path)
        except (CloneError, UpdateError, AuthenticationError) as e:
            logger.error('Failed to sync %s: %s', repo_name, e)
            if repo_path.exists() and (not (repo_path / '.git').exists()):
                shutil.rmtree(repo_path, ignore_errors=True)
            return SyncResult(repo_name=repo_name, success=False, action='failed', message=str(e), path=None)

    def _clone_repo(self, repo_config: RepositoryConfig, dest_path: Path) -> None:
        cmd = ['git', 'clone', '--depth', '1', '--single-branch']
        if repo_config.branch:
            cmd.extend(['--branch', repo_config.branch])
        cmd.extend([repo_config.url, str(dest_path)])
        env, askpass_path = self._get_git_env(repo_config.url)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=repo_config.timeout, env=env)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if 'Authentication failed' in stderr or 'could not read Username' in stderr:
                    raise AuthenticationError(repo_config.url, stderr)
                raise CloneError(repo_config.url, stderr)
            logger.info('Cloned %s to %s', repo_config.url, dest_path)
        except subprocess.TimeoutExpired:
            raise CloneError(repo_config.url, f'Timeout after {repo_config.timeout}s')
        finally:
            if askpass_path and askpass_path.exists():
                askpass_path.unlink()

    def _update_repo(self, repo_path: Path, repo_config: RepositoryConfig) -> None:
        branch = repo_config.branch or self._get_default_branch(repo_path)
        env, askpass_path = self._get_git_env(repo_config.url)
        try:
            fetch_result = subprocess.run(['git', 'fetch', 'origin'], cwd=repo_path, capture_output=True, text=True, timeout=repo_config.timeout, env=env)
            if fetch_result.returncode != 0:
                raise UpdateError(str(repo_path), fetch_result.stderr.strip())
            reset_result = subprocess.run(['git', 'reset', '--hard', f'origin/{branch}'], cwd=repo_path, capture_output=True, text=True, timeout=60, env=env)
            if reset_result.returncode != 0:
                raise UpdateError(str(repo_path), reset_result.stderr.strip())
            logger.info('Updated %s to origin/%s', repo_path, branch)
        except subprocess.TimeoutExpired:
            raise UpdateError(str(repo_path), f'Timeout after {repo_config.timeout}s')
        finally:
            if askpass_path and askpass_path.exists():
                askpass_path.unlink()

    def _create_askpass_script(self, token: str) -> Path:
        fd, path = tempfile.mkstemp(prefix='git_askpass_', suffix='.sh')
        try:
            script = f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(token)}\n"
            os.write(fd, script.encode())
        finally:
            os.close(fd)
        os.chmod(path, stat.S_IRWXU)
        return Path(path)

    def _get_git_env(self, url: str) -> tuple[dict[str, str], Path | None]:
        env = os.environ.copy()
        askpass_path: Path | None = None
        ssh_key = self.config.auth.get_ssh_key_path()
        if ssh_key:
            ssh_cmd = f'ssh -i {ssh_key}'
            if self.config.auth.allow_insecure_ssh:
                logger.warning('SSH host key verification disabled - this is insecure and vulnerable to MITM attacks. Only use for testing.')
                ssh_cmd += ' -o StrictHostKeyChecking=no'
            env['GIT_SSH_COMMAND'] = ssh_cmd
        token = self.config.auth.get_github_token()
        if token and url.startswith('https://'):
            askpass_path = self._create_askpass_script(token)
            env['GIT_ASKPASS'] = str(askpass_path)
            env['GIT_TERMINAL_PROMPT'] = '0'
        return (env, askpass_path)

    def _get_default_branch(self, repo_path: Path) -> str:
        try:
            result = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], cwd=repo_path, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except subprocess.TimeoutExpired:
            pass
        for branch in ['main', 'master']:
            refs_path = repo_path / '.git' / 'refs' / 'heads' / branch
            if refs_path.exists():
                return branch
        return 'main'

    def get_repo_path(self, repo_config: RepositoryConfig) -> Path:
        return self.repos_path / repo_config.get_repo_name()

    def get_existing_repo_paths(self) -> list[Path]:
        if not self.repos_path.exists():
            return []
        paths = []
        for item in self.repos_path.iterdir():
            if item.is_dir() and (item / '.git').exists():
                paths.append(item)
        return sorted(paths)

    def get_repo_status(self, repo_path: Path) -> RepoStatus | None:
        if not (repo_path / '.git').exists():
            return None
        try:
            branch_result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo_path, capture_output=True, text=True, timeout=10)
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else 'unknown'
            commit_result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=repo_path, capture_output=True, text=True, timeout=10)
            commit = commit_result.stdout.strip() if commit_result.returncode == 0 else 'unknown'
            date_result = subprocess.run(['git', 'log', '-1', '--format=%ci'], cwd=repo_path, capture_output=True, text=True, timeout=10)
            commit_date = date_result.stdout.strip() if date_result.returncode == 0 else 'unknown'
            status_result = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True, timeout=10)
            is_dirty = bool(status_result.stdout.strip()) if status_result.returncode == 0 else False
            return RepoStatus(path=repo_path, branch=branch, commit=commit, commit_date=commit_date, is_dirty=is_dirty)
        except subprocess.TimeoutExpired:
            return None