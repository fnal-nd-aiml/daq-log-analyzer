"""
File: doc_loader.py
Purpose: Documentation loader for data/docs/ component references.
Category: Utility
Author: artdaq team
Depends: provider, prompts, pydantic
Exports: ErrorDiagnosis, DocExtraction, DocStore, LLMDocExtractor, extract_names_from_message, ...
Complexity: Medium | Lines: 290
"""

from __future__ import annotations
import hashlib
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING
import yaml
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from srcs.llm.provider import LLMProvider
logger = logging.getLogger(__name__)
_DEFAULT_MAP_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "docs" / "sub-component-map.yaml"
_MAX_CACHE_ENTRIES = 50


def _load_subcomponent_map(path: Path | str = _DEFAULT_MAP_PATH) -> dict[str, str]:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    if not resolved.is_file():
        logger.warning("Sub-component map not found: %s", resolved)
        return {}
    try:
        with open(resolved) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            logger.warning("Sub-component map is not a dict: %s", resolved)
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except Exception as e:
        logger.warning("Failed to load sub-component map: %s", e)
        return {}


_SUBCOMPONENT_MAP: dict[str, str] = _load_subcomponent_map()


class ErrorDiagnosis(BaseModel):
    error_pattern: str = Field(description="The error message pattern")
    root_cause: str = Field(description="Documented root cause")
    resolution: str = Field(description="Documented fix/resolution")
    confidence: str = Field(default="related", description='How well the doc matches: "exact", "likely", "related"')


class DocExtraction(BaseModel):
    error_diagnoses: list[ErrorDiagnosis] = Field(
        default_factory=list, description="Error message → root cause mappings from doc"
    )
    cascade_chains: list[str] = Field(default_factory=list, description="Relevant error cascade descriptions")
    configuration_hints: list[str] = Field(default_factory=list, description="Relevant FHiCL/config parameters")
    relevant_context: str = Field(default="", description="Free-text relevant background")
    reasoning: str = Field(default="", description="Why these sections were selected")

    def format_for_prompt(self, max_chars: int = 8000) -> str:
        parts: list[str] = []
        used = 0
        if self.error_diagnoses:
            diag_lines = ["### Error Diagnoses"]
            for d in self.error_diagnoses:
                entry = f"- **{d.error_pattern}** [{d.confidence}]\n  Root cause: {d.root_cause}\n  Resolution: {d.resolution}"
                diag_lines.append(entry)
            diag_text = "\n".join(diag_lines)
            if used + len(diag_text) <= max_chars:
                parts.append(diag_text)
                used += len(diag_text)
        if self.cascade_chains:
            chain_lines = ["### Cascade Chains"]
            for chain in self.cascade_chains:
                chain_lines.append(f"- {chain}")
            chain_text = "\n".join(chain_lines)
            if used + len(chain_text) <= max_chars:
                parts.append(chain_text)
                used += len(chain_text)
        if self.configuration_hints:
            config_lines = ["### Configuration Hints"]
            for hint in self.configuration_hints:
                config_lines.append(f"- {hint}")
            config_text = "\n".join(config_lines)
            if used + len(config_text) <= max_chars:
                parts.append(config_text)
                used += len(config_text)
        if self.relevant_context:
            budget = max_chars - used
            if budget > 50:
                ctx = self.relevant_context[:budget]
                if len(self.relevant_context) > budget:
                    ctx += "..."
                parts.append(f"### Context\n{ctx}")
        return "\n\n".join(parts) if parts else ""


class DocStore:

    def __init__(self, docs_dir: str | None = None, subcomponent_map_path: str | None = None) -> None:
        if docs_dir is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            docs_dir = str(project_root / "data" / "docs")
        self._docs_dir = docs_dir
        self._docs: dict[str, str] = {}
        if subcomponent_map_path is not None:
            self._subcomponent_map = _load_subcomponent_map(subcomponent_map_path)
        else:
            self._subcomponent_map = _SUBCOMPONENT_MAP

    @property
    def subcomponent_map(self) -> dict[str, str]:
        return self._subcomponent_map

    def load_all(self) -> None:
        docs_path = Path(self._docs_dir)
        if not docs_path.is_dir():
            logger.warning("Docs directory not found: %s", self._docs_dir)
            return
        for md_file in sorted(docs_path.glob("*.md")):
            name = md_file.stem
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Could not read %s", md_file)
                continue
            self._docs[name] = text
        logger.debug("Loaded %d doc files from %s", len(self._docs), self._docs_dir)

    def has_doc(self, name: str) -> bool:
        return name in self._docs

    def get_doc_names(self) -> list[str]:
        return sorted(self._docs.keys())

    def get_doc_index(self) -> str:
        if not self._docs:
            return ""
        lines: list[str] = []
        for name in sorted(self._docs.keys()):
            text = self._docs[name]
            headings: list[str] = []
            for line in text.split("\n"):
                match = re.match("^(#{1,2})\\s+(.+)$", line)
                if match:
                    headings.append(match.group(2).strip())
            heading_str = "; ".join(headings) if headings else "(no sections)"
            lines.append(f"- {name}.md: {heading_str}")
        return "\n".join(lines)

    def get_full_text(self, doc_name: str) -> str:
        return self._docs.get(doc_name, "")

    def match_components(self, components: set[str]) -> dict[str, str]:
        matched: dict[str, str] = {}
        for comp in components:
            if not comp:
                continue
            if comp in self._docs:
                matched[comp] = comp
                continue
            mapped = self._subcomponent_map.get(comp)
            if mapped and mapped in self._docs:
                matched[comp] = mapped
                continue
            for doc_name in self._docs:
                if comp.startswith(doc_name) or doc_name.startswith(comp):
                    matched[comp] = doc_name
                    break
        return matched


class LLMDocExtractor:

    def __init__(self, doc_store: DocStore, llm: LLMProvider) -> None:
        self._doc_store = doc_store
        self._llm = llm
        self._cache: OrderedDict[str, DocExtraction] = OrderedDict()

    async def extract_for_investigation(
        self, components: set[str], error_messages: list[str], max_chars: int = 12000
    ) -> str:
        if not self._doc_store._docs:
            return ""
        matched = self._doc_store.match_components(components)
        if not matched:
            return ""
        unique_doc_names: list[str] = list(dict.fromkeys(matched.values()))
        parts: list[str] = []
        total_used = 0
        budget_per_doc = max(2000, max_chars // max(len(unique_doc_names), 1))
        for doc_name in unique_doc_names:
            if total_used >= max_chars:
                break
            doc_budget = min(budget_per_doc, max_chars - total_used)
            extraction = await self._extract_single(doc_name, error_messages)
            if extraction is None:
                continue
            formatted = extraction.format_for_prompt(max_chars=doc_budget)
            if formatted:
                section = f"## Reference: {doc_name}\n{formatted}"
                parts.append(section)
                total_used += len(section)
        return "\n\n".join(parts) if parts else ""

    async def extract_compact_reference(
        self, components: set[str], error_messages: list[str], max_chars: int = 4000
    ) -> str:
        if not self._doc_store._docs:
            return ""
        matched = self._doc_store.match_components(components)
        if not matched:
            return ""
        unique_doc_names: list[str] = list(dict.fromkeys(matched.values()))
        parts: list[str] = []
        total_used = 0
        for doc_name in unique_doc_names:
            extraction = await self._extract_single(doc_name, error_messages)
            if extraction is None or not extraction.error_diagnoses:
                continue
            diag_lines: list[str] = []
            for d in extraction.error_diagnoses:
                entry = f"- {d.error_pattern} [{d.confidence}]: {d.root_cause} → {d.resolution}"
                diag_lines.append(entry)
            diag_text = "\n".join(diag_lines)
            if total_used + len(diag_text) + len(doc_name) + 5 <= max_chars:
                parts.append(f"# {doc_name}\n{diag_text}")
                total_used += len(diag_text) + len(doc_name) + 5
        return "\n".join(parts) if parts else ""

    async def _extract_single(self, doc_name: str, error_messages: list[str]) -> DocExtraction | None:
        cache_key = self._cache_key(doc_name, error_messages)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]
        doc_text = self._doc_store.get_full_text(doc_name)
        if not doc_text:
            return None
        try:
            extraction = await self._call_llm_extraction(doc_name, doc_text, error_messages)
        except Exception as e:
            logger.warning("LLM doc extraction failed for %s: %s", doc_name, e)
            return None
        self._cache[cache_key] = extraction
        if len(self._cache) > _MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)
        return extraction

    async def _call_llm_extraction(self, doc_name: str, doc_text: str, error_messages: list[str]) -> DocExtraction:
        from srcs.prompts import UserPromptType, get_user_prompt

        template = get_user_prompt(UserPromptType.DOC_EXTRACTION)
        errors_text = "\n".join((f"- {msg}" for msg in error_messages[:20]))
        prompt = template.format(doc_name=doc_name, doc_content=doc_text, error_messages=errors_text)
        result = await self._llm.generate_structured(prompt=prompt, response_model=DocExtraction)
        return result

    @staticmethod
    def _cache_key(doc_name: str, error_messages: list[str]) -> str:
        normalized = []
        for msg in error_messages:
            norm = re.sub("\\d+", "N", msg)
            norm = re.sub("0x[0-9a-fA-F]+", "HEX", norm)
            normalized.append(norm)
        combined = doc_name + "|" + "|".join(sorted(normalized))
        return hashlib.md5(combined.encode()).hexdigest()


def extract_names_from_message(message: str, subcomponent_map: dict[str, str] | None = None) -> set[str]:
    if not message:
        return set()
    if subcomponent_map is None:
        subcomponent_map = _SUBCOMPONENT_MAP
    names: set[str] = set()
    colon_match = re.match("^([A-Za-z_][A-Za-z0-9_]*)\\s*:", message)
    if colon_match:
        full_name = colon_match.group(1)
        names.add(full_name)
        parts = full_name.split("_")
        for part in parts:
            if len(part) >= 4:
                names.add(part)
    camel_case = re.findall("\\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\\b", message)
    for ident in camel_case:
        if len(ident) >= 8:
            names.add(ident)
    acronym_camel = re.findall("\\b([A-Z]{2,}[a-z]+(?:[A-Z][a-z]+)*)\\b", message)
    for ident in acronym_camel:
        if len(ident) >= 8:
            names.add(ident)
    for key in subcomponent_map:
        if key in message:
            names.add(key)
    return names
