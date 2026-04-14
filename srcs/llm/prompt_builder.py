"""
File: prompt_builder.py
Purpose: Centralized prompt building for LLM interactions.
Category: Utility
Author: artdaq team
Depends: token_utils, knowledge, logs, prompts
Exports: PromptContext, PromptBuilder
Complexity: Medium | Lines: 184
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from srcs.prompts import PromptLoader, SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt

if TYPE_CHECKING:
    from srcs.models.knowledge import PriorKnowledge
    from srcs.models.logs import Log


@dataclass
class PromptContext:
    error: "Log | None" = None
    error_message: str = ""
    error_component: str = "Unknown"
    error_function: str = "unknown"
    error_timestamp: str = ""
    context_logs: list["Log"] = field(default_factory=list)
    formatted_logs: str = ""
    prior: "PriorKnowledge | None" = None
    formatted_prior: str = ""
    code_context: str = ""
    hypotheses: list[Any] = field(default_factory=list)
    evidence: Any = None
    causal_chains: list[Any] = field(default_factory=list)
    binder_context: str = ""


class PromptBuilder:
    SECTION_ORDER = [
        "error_context",
        "logs",
        "prior_knowledge",
        "code_context",
        "hypotheses",
        "evidence",
        "binder_context",
        "instructions",
    ]

    def __init__(self) -> None:
        self._loader = PromptLoader()

    def build(
        self,
        template_name: str | UserPromptType,
        context: PromptContext,
        include_sections: list[str] | None = None,
        max_tokens: int = 0,
    ) -> str:
        if isinstance(template_name, str):
            template_name = UserPromptType(template_name)
        template = get_user_prompt(template_name)
        format_kwargs = self._build_format_kwargs(context, include_sections)
        try:
            prompt = template.format(**format_kwargs)
        except KeyError as e:
            missing_key = str(e).strip("'")
            format_kwargs[missing_key] = ""
            prompt = template.format(**format_kwargs)
        if max_tokens > 0:
            prompt = self._truncate_to_tokens(prompt, max_tokens)
        return prompt

    def build_system_prompt(self, persona_key: str | SystemPromptType) -> str:
        if isinstance(persona_key, str):
            persona_key = SystemPromptType(persona_key)
        return get_system_prompt(persona_key)

    def format_logs(self, logs: list["Log"], max_logs: int = 20) -> str:
        if not logs:
            return "No context logs available."
        lines = []
        for log in logs[:max_logs]:
            component = log.component or "unknown"
            function = log.function or "unknown"
            lines.append(f"[{log.timestamp}] [{log.level}] [{component}] [{function}] {log.message}")
        if len(logs) > max_logs:
            lines.append(f"... ({len(logs) - max_logs} more logs)")
        return "\n".join(lines)

    def format_prior_knowledge(self, prior: "PriorKnowledge") -> str:
        sections = []
        if prior.matched_patterns:
            patterns = ["Matched Patterns:"]
            for mp in prior.matched_patterns[:3]:
                patterns.append(f"  - {mp.pattern.signature[:100]} (confidence: {mp.confidence:.2f})")
            sections.append("\n".join(patterns))
        if prior.similar_investigations:
            similar = ["Similar Past Investigations:"]
            for si in prior.similar_investigations[:3]:
                similar.append(f"  - {si.similarity:.2f}: {si.root_cause[:100]}")
            sections.append("\n".join(similar))
        if prior.recommended_hypotheses:
            hypos = ["Recommended Hypotheses:"]
            for rh in prior.recommended_hypotheses[:5]:
                hypos.append(f"  - [{rh.source}] {rh.description} (prior: {rh.prior:.2f})")
            sections.append("\n".join(hypos))
        if prior.source_locations:
            locs = ["Source Locations:"]
            for loc in prior.source_locations[:3]:
                locs.append(f"  - {loc.file_path}:{loc.line_number} (score: {loc.match_score:.2f})")
            sections.append("\n".join(locs))
        if not sections:
            return "No prior knowledge available."
        return "\n\n".join(sections)

    def format_code_context(self, prior: "PriorKnowledge") -> str:
        if not prior.source_locations:
            return "No code context available."
        sections = []
        for loc in prior.source_locations[:2]:
            section = [f"File: {loc.file_path}:{loc.line_number}"]
            if loc.function_name:
                section.append(f"Function: {loc.function_name}")
            if loc.function_body:
                section.append(f"Code:\n```\n{loc.function_body}\n```")
            sections.append("\n".join(section))
        return "\n\n".join(sections)

    def format_hypotheses(self, hypotheses: list[Any], max_count: int = 5) -> str:
        if not hypotheses:
            return "No hypotheses generated yet."
        lines = ["Current Hypotheses:"]
        for i, h in enumerate(hypotheses[:max_count]):
            score_str = f"score: {h.score:.2f}" if hasattr(h, "score") else ""
            prior_str = f"prior: {h.prior:.2f}" if hasattr(h, "prior") else ""
            lines.append(f"{i + 1}. {h.description} ({prior_str}, {score_str})")
        return "\n".join(lines)

    def format_evidence(self, evidence: Any) -> str:
        if evidence is None:
            return "No evidence collected yet."
        if hasattr(evidence, "summary"):
            return evidence.summary()
        if hasattr(evidence, "items"):
            items = list(evidence.items.values())
            if not items:
                return "No evidence items."
            lines = ["Collected Evidence:"]
            for item in items[:10]:
                strength = getattr(item, "strength", "UNKNOWN")
                lines.append(f"  - [{strength}] {item.evidence_type}: {item.content}")
            return "\n".join(lines)
        return "No evidence available."

    def _build_format_kwargs(self, context: PromptContext, include_sections: list[str] | None) -> dict[str, str]:
        kwargs: dict[str, str] = {}
        if context.error:
            kwargs["error_message"] = context.error.message
            kwargs["error_component"] = context.error.component or "Unknown"
            kwargs["error_function"] = context.error.function or "unknown"
            kwargs["error_timestamp"] = str(context.error.timestamp)
        else:
            kwargs["error_message"] = context.error_message
            kwargs["error_component"] = context.error_component
            kwargs["error_function"] = context.error_function
            kwargs["error_timestamp"] = context.error_timestamp
        if context.formatted_logs:
            kwargs["context_logs"] = context.formatted_logs
        elif context.context_logs:
            kwargs["context_logs"] = self.format_logs(context.context_logs)
        else:
            kwargs["context_logs"] = "No context logs available."
        if context.formatted_prior:
            kwargs["prior_knowledge"] = context.formatted_prior
        elif context.prior:
            kwargs["prior_knowledge"] = self.format_prior_knowledge(context.prior)
        else:
            kwargs["prior_knowledge"] = "No prior knowledge available."
        if context.code_context:
            kwargs["code_context"] = context.code_context
        elif context.prior:
            kwargs["code_context"] = self.format_code_context(context.prior)
        else:
            kwargs["code_context"] = "No code context available."
        kwargs["hypotheses"] = self.format_hypotheses(context.hypotheses)
        kwargs["evidence"] = self.format_evidence(context.evidence)
        kwargs["binder_context"] = context.binder_context
        return kwargs

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        from srcs.llm.token_utils import truncate_if_needed

        return truncate_if_needed(text, max_tokens, label="prompt")
