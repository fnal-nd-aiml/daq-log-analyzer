"""
File: summarizer.py
Purpose: LLM-based function summarization for semantic search.
Category: Utility
Author: artdaq team
Depends: provider, token_utils
Exports: FunctionSummary, SummarizerConfig, FunctionSummarizer, detect_language
Complexity: Medium | Lines: 131
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from srcs.llm.provider import LLMProvider
logger = logging.getLogger(__name__)


@dataclass
class FunctionSummary:
    function_name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    summary: str
    embedding: list[float] | None = None
    class_name: str | None = None
    module: str | None = None


@dataclass
class SummarizerConfig:
    max_source_length: int = 2000
    min_source_length: int = 50
    include_docstring: bool = True
    batch_size: int = 10


class FunctionSummarizer:
    SUMMARY_PROMPT = "Analyze this {language} function and provide a concise 1-2 sentence summary describing:\n1. What the function does (its purpose)\n2. Key inputs and outputs\n3. Any important side effects or behaviors\n\nFunction:\n```{language}\n{source}\n```\n\nRespond with ONLY the summary, no additional text or formatting."

    def __init__(self, llm: "LLMProvider", config: SummarizerConfig | None = None):
        self.llm = llm
        self.config = config or SummarizerConfig()

    async def summarize_function(self, source: str, name: str, file_path: str, language: str = "cpp") -> str:
        if len(source) < self.config.min_source_length:
            return f"Simple function {name}"
        from srcs.llm.token_utils import truncate_if_needed

        source = truncate_if_needed(
            source, max_tokens=self.config.max_source_length // 4, label=f"summarizer source:{name}"
        )
        prompt = self.SUMMARY_PROMPT.format(language=language, source=source)
        try:
            summary = await self.llm.generate(prompt)
            return summary.strip()
        except Exception as e:
            logger.warning(f"Failed to summarize function {name}: {e}")
            return f"Function {name} in {Path(file_path).name}"

    async def summarize_function_with_embedding(
        self,
        source: str,
        name: str,
        file_path: str,
        start_line: int,
        end_line: int,
        signature: str,
        language: str = "cpp",
        class_name: str | None = None,
    ) -> FunctionSummary:
        summary_text = await self.summarize_function(source, name, file_path, language)
        embed_text = f"{name}: {summary_text}"
        if class_name:
            embed_text = f"{class_name}::{name}: {summary_text}"
        try:
            embedding = await self.llm.embed(embed_text)
        except Exception as e:
            logger.warning(f"Failed to generate embedding for {name}: {e}")
            embedding = None
        return FunctionSummary(
            function_name=name,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            summary=summary_text,
            embedding=embedding,
            class_name=class_name,
            module=Path(file_path).stem,
        )

    async def summarize_batch(
        self, functions: list[dict], language: str = "cpp", progress_callback: Callable[[int, int], None] | None = None
    ) -> list[FunctionSummary]:
        summaries = []
        total = len(functions)
        for i, func in enumerate(functions):
            if progress_callback:
                progress_callback(i, total)
            try:
                summary = await self.summarize_function_with_embedding(
                    source=func["source"],
                    name=func["name"],
                    file_path=func["file_path"],
                    start_line=func["start_line"],
                    end_line=func["end_line"],
                    signature=func["signature"],
                    language=language,
                    class_name=func.get("class_name"),
                )
                summaries.append(summary)
            except Exception as e:
                logger.warning(f"Failed to process function {func['name']}: {e}")
        if progress_callback:
            progress_callback(total, total)
        return summaries


def detect_language(file_path: str | Path) -> str:
    ext = Path(file_path).suffix.lower()
    language_map = {
        ".cpp": "cpp",
        ".cxx": "cpp",
        ".cc": "cpp",
        ".c": "c",
        ".h": "cpp",
        ".hpp": "cpp",
        ".hxx": "cpp",
        ".py": "python",
        ".java": "java",
        ".js": "javascript",
        ".ts": "typescript",
        ".go": "go",
        ".rs": "rust",
    }
    return language_map.get(ext, "text")
