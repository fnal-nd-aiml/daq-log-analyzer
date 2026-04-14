"""
File: loader.py
Purpose: Prompt loader with caching, include resolution, and cycle detection.
Category: Utility
Author: artdaq team
Depends: None
Exports: PromptLoader, get_default_system_prompt, get_system_prompt, get_user_prompt, INCLUDE_PATTERN
Complexity: Medium | Lines: 103
"""

import re
from pathlib import Path
from .errors import IncludeCycleError, IncludeNotFoundError, PromptNotFoundError
from .registry import get_user_prompt_metadata
from .types import PromptTemplate, SystemPromptType, UserPromptType

INCLUDE_PATTERN = re.compile("\\{include:([^}]+)\\}")
_DEFAULT_SYSTEM_PROMPT: str | None = None


def get_default_system_prompt() -> str:
    global _DEFAULT_SYSTEM_PROMPT
    if _DEFAULT_SYSTEM_PROMPT is None:
        _DEFAULT_SYSTEM_PROMPT = _get_loader()._load_raw("system/base")
    return _DEFAULT_SYSTEM_PROMPT


class PromptLoader:

    def __init__(self, templates_dir: Path | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        self.templates_dir = templates_dir
        self._content_cache: dict[str, str] = {}

    def _resolve_includes(self, content: str, source_path: str, visited: frozenset[str] | None = None) -> str:
        if visited is None:
            visited = frozenset()

        def replace_include(match: re.Match[str]) -> str:
            include_path = match.group(1)
            if include_path in visited:
                cycle = list(visited) + [include_path]
                raise IncludeCycleError(cycle)
            return self._load_include(include_path, source_path, visited | {include_path})

        return INCLUDE_PATTERN.sub(replace_include, content)

    def _load_include(self, include_path: str, referenced_from: str, visited: frozenset[str]) -> str:
        cache_key = f"include:{include_path}"
        if cache_key in self._content_cache and (not visited):
            return self._content_cache[cache_key]
        file_path = self.templates_dir / f"{include_path}.md"
        if not file_path.exists():
            raise IncludeNotFoundError(include_path, referenced_from)
        content = file_path.read_text(encoding="utf-8").strip()
        content = self._resolve_includes(content, include_path, visited)
        if not visited:
            self._content_cache[cache_key] = content
        return content

    def _load_raw(self, relative_path: str) -> str:
        cache_key = f"raw:{relative_path}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        file_path = self.templates_dir / f"{relative_path}.md"
        if not file_path.exists():
            raise PromptNotFoundError(relative_path, str(file_path))
        content = file_path.read_text(encoding="utf-8").strip()
        content = self._resolve_includes(content, relative_path)
        self._content_cache[cache_key] = content
        return content

    def get_system_prompt(self, prompt_type: SystemPromptType) -> str:
        cache_key = f"system:{prompt_type.value}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        base = self._load_raw("system/base")
        persona_content = self._load_raw(f"system/{prompt_type.value}")
        content = persona_content.replace("{base_knowledge}", base)
        self._content_cache[cache_key] = content
        return content

    def get_user_prompt(self, prompt_type: UserPromptType) -> PromptTemplate:
        relative_path = f"user/{prompt_type.value}"
        content = self._load_raw(relative_path)
        metadata = get_user_prompt_metadata(prompt_type)
        file_path = self.templates_dir / f"{relative_path}.md"
        return PromptTemplate(content=content, prompt_type=prompt_type, metadata=metadata, path=file_path)

    def clear_cache(self) -> None:
        self._content_cache.clear()


_loader: PromptLoader | None = None


def _get_loader() -> PromptLoader:
    global _loader
    if _loader is None:
        _loader = PromptLoader()
    return _loader


def get_system_prompt(prompt_type: SystemPromptType) -> str:
    return _get_loader().get_system_prompt(prompt_type)


def get_user_prompt(prompt_type: UserPromptType) -> PromptTemplate:
    return _get_loader().get_user_prompt(prompt_type)


__all__ = ["PromptLoader", "get_default_system_prompt", "get_system_prompt", "get_user_prompt"]
