"""
File: retrieval_orchestrator.py
Purpose: Retrieval Orchestrator - Manages prior knowledge retrieval.
Category: Utility
Author: artdaq team
Depends: dataflow, tools, indexer, source_locator, knowledge, ...
Exports: ParsedNumericValue, ParsedErrorContext, InterpretedHint, InterpretedHints, RetrievalOrchestrator
Complexity: High | Lines: 830
"""

from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field
from srcs.agent.dataflow import CodeHintExtractor, DataflowTracer, NumericExtractor
from srcs.agent.tools import ArchivistTools
from srcs.extraction.source_locator import SourceLocator
from srcs.knowledge import KnowledgeBase
from srcs.models import FeedbackSummary, Log, PriorKnowledge
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt

if TYPE_CHECKING:
    from srcs.agent.dataflow import NumericAnalysis
    from srcs.extraction.indexer import CodeIndex
    from srcs.knowledge.chroma_store import ChromaStore
    from srcs.llm import LLMProvider
    from srcs.workbinder import BinderStore, WorkBinder
logger = logging.getLogger(__name__)


class ParsedNumericValue(BaseModel):
    value: int | float = Field(description="The numeric value")
    unit: str = Field(description="Unit of measurement (us, ms, s, bytes, count)")
    label: str = Field(description="What this value represents (e.g., 'timeout_threshold')")
    raw_text: str = Field(description="Original text from error message")


class ParsedErrorContext(BaseModel):
    function_name: str = Field(default="", description="Function name where error occurred")
    error_type: str = Field(default="", description="Type of error (timeout, buffer_overflow, null_pointer, etc.)")
    numeric_values: list[ParsedNumericValue] = Field(
        default_factory=list, description="Extracted numeric values with their meanings"
    )
    timestamp_analysis: str = Field(default="", description="Analysis of timestamp relationships if present")
    timeout_analysis: str = Field(default="", description="Analysis of timeout values if present")
    data_gap_description: str = Field(
        default="", description="Description of any data gaps or latency issues identified"
    )
    likely_cause: str = Field(default="", description="Most likely cause based on numeric analysis")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence in the analysis (0.0-1.0)")


class InterpretedHint(BaseModel):
    original_index: int = Field(description="Zero-based index of the original hint being interpreted")
    hypothesis: str = Field(
        description="The hint rewritten as a specific, testable hypothesis about what could cause the error"
    )
    is_diagnostic: bool = Field(
        description="True if this hint is diagnostically relevant to the error. False for implementation notes, status messages, or iteration logic that don't describe a potential cause"
    )


class InterpretedHints(BaseModel):
    hints: list[InterpretedHint] = Field(default_factory=list, description="List of interpreted hints")


class RetrievalOrchestrator:

    def __init__(
        self,
        kb: KnowledgeBase,
        source_roots: list[Path] | None = None,
        code_index: "CodeIndex | None" = None,
        chroma_store: "ChromaStore | None" = None,
        llm_provider: "LLMProvider | None" = None,
        binder_store: "BinderStore | None" = None,
    ) -> None:
        self.kb = kb
        self._source_roots = source_roots or []
        self._code_index = code_index
        self._chroma_store = chroma_store
        self._llm_provider = llm_provider
        self._binder_store = binder_store
        self._hint_extractor = CodeHintExtractor()
        self._numeric_extractor = NumericExtractor()
        self._dataflow_tracer = DataflowTracer(code_index, source_roots)
        self._archivist_tools = ArchivistTools(
            code_index=code_index, llm_provider=llm_provider, source_roots=source_roots
        )

    async def retrieve(self, error: Log, context: list[Log], binder: "WorkBinder") -> PriorKnowledge:
        prior = await self.kb.get_prior_knowledge(error, context)
        logger.info("Parsing numeric values from error message")
        parsed_context = await self._parse_error_numeric_context(error.message, binder)
        if parsed_context:
            logger.info(
                f"Numeric parsing result: likely_cause={(parsed_context.likely_cause[:50] if parsed_context.likely_cause else 'None')}..., values={len(parsed_context.numeric_values)}, confidence={parsed_context.confidence}"
            )
            if parsed_context.likely_cause:
                numeric_hypotheses = self._generate_hypotheses_from_numeric_analysis(parsed_context)
                prior.recommended_hypotheses.extend(numeric_hypotheses)
                logger.info(f"Generated {len(numeric_hypotheses)} hypotheses from numeric analysis")
        else:
            logger.info("No numeric context parsed from error message")
        if self._source_roots:
            try:
                source_locations = await self._find_error_source(error)
                prior.source_locations = source_locations
                if source_locations:
                    logger.info(f"Found {len(source_locations)} source locations")
                    for loc in source_locations[:2]:
                        logger.info(
                            f"  Location: {loc.file_path}:{loc.line_number} (body: {len(loc.function_body or '')} chars)"
                        )
                    auto_queries = self._generate_queries_from_locations(source_locations)
                    prior.recommended_queries.extend(auto_queries)
                    logger.info(f"Generated {len(auto_queries)} evidence queries")
                    code_hints = self._extract_code_hints(source_locations)
                    logger.info(f"Extracted {len(code_hints)} code hints")
                    if code_hints:
                        hint_hypotheses = await self._generate_hypotheses_from_hints(code_hints, error.message)
                        prior.recommended_hypotheses.extend(hint_hypotheses)
                        logger.info(f"Generated {len(hint_hypotheses)} hypotheses from hints")
                    dataflow_queries = await self._generate_dataflow_queries(source_locations)
                    prior.recommended_queries.extend(dataflow_queries)
                    await self._enrich_with_call_graph_context(source_locations, error.message)
                    await self._populate_binder(binder, source_locations, error.message)
            except Exception as e:
                logger.warning(f"Failed to find error source location: {e}")
        if self._binder_store and prior.similar_investigations:
            try:
                feedback_summaries = await self._retrieve_feedback_from_similar(prior.similar_investigations)
                prior.feedback_from_similar = feedback_summaries
                if feedback_summaries:
                    logger.info(f"Retrieved {len(feedback_summaries)} feedback items from similar investigations")
            except Exception as e:
                logger.warning(f"Failed to retrieve feedback from similar cases: {e}")
        return prior

    async def _retrieve_feedback_from_similar(self, similar_investigations: list) -> list[FeedbackSummary]:
        summaries: list[FeedbackSummary] = []
        for sim in similar_investigations[:5]:
            try:
                binder = await self._binder_store.load_binder_for_investigation(sim.investigation_id)
                if not binder:
                    continue
                feedback_items = binder.get_feedback()
                for fb in feedback_items:
                    summaries.append(
                        FeedbackSummary(
                            investigation_id=fb.investigation_id,
                            was_correct=fb.was_correct,
                            actual_cause=fb.actual_cause,
                            what_was_wrong=fb.what_was_wrong,
                            suggestions=fb.suggestions,
                            additional_notes=fb.additional_notes,
                        )
                    )
            except Exception as e:
                logger.debug(f"No feedback for investigation {sim.investigation_id}: {e}")
        return summaries

    async def _find_error_source(self, error: Log) -> list:
        from srcs.models.source_location import SourceLocation

        if not self._source_roots:
            return []
        locator = SourceLocator(
            source_roots=self._source_roots, code_index=self._code_index, chroma_store=self._chroma_store
        )
        if self._code_index and error.function:
            file_line_match = re.match("^([\\w.]+\\.\\w{1,4}):(\\d+)$", error.function.strip())
            if file_line_match:
                filename = file_line_match.group(1)
                error_line = int(file_line_match.group(2))
                logger.info(f"Parsed file:line from error.function: {filename}:{error_line}")
                try:
                    all_funcs = self._code_index.find_function("%", file_filter=filename)
                    if all_funcs:
                        matching_func = None
                        for func in all_funcs:
                            if func.start_line <= error_line <= (func.end_line or func.start_line):
                                matching_func = func
                                break
                        if matching_func:
                            func_body = self._code_index.get_function_source(matching_func.name)
                            callers = self._code_index.get_callers(matching_func.name)
                            callees = self._code_index.get_callees(matching_func.name)
                            loc = SourceLocation(
                                file_path=str(matching_func.file_path),
                                line_number=error_line,
                                matched_line=matching_func.signature or matching_func.name,
                                context_before=[],
                                context_after=[],
                                match_score=0.98,
                                search_pattern=f"file_line:{filename}:{error_line}",
                                is_log_statement=False,
                                function_name=matching_func.name,
                                function_signature=matching_func.signature,
                                function_start_line=matching_func.start_line,
                                function_end_line=matching_func.end_line,
                                class_name=matching_func.class_name,
                                function_body=func_body,
                                callers=callers,
                                callees=callees,
                            )
                            logger.info(
                                f"Found function '{matching_func.name}' from error.function file:line reference"
                            )
                            return [loc]
                        logger.debug(f"No function containing line {error_line} in {filename}")
                except Exception as e:
                    logger.debug(f"file:line lookup failed for {error.function}: {e}")
        logger.info(f"Code index available: {self._code_index is not None}")
        if self._code_index:
            func_names = locator.extract_function_names(error.message)
            logger.info(f"Extracted function names from error: {func_names}")
            for func_name in func_names[:3]:
                results = self._code_index.find_function(func_name)
                logger.info(f"Exact search for '{func_name}': {len(results)} results")
                if not results and "_" in func_name:
                    partial = func_name.split("_")[-1]
                    if len(partial) >= 5:
                        results = self._code_index.find_function(f"%{partial}%")
                if not results:
                    results = self._code_index.find_function(f"%{func_name}%")
                    logger.info(f"Wildcard search for '%{func_name}%': {len(results)} results")
                if results:
                    logger.info(f"Found {len(results)} function(s) for '{func_name}'")
                    locations = []
                    for func in results[:3]:
                        func_body = self._code_index.get_function_source(func.name)
                        callers = self._code_index.get_callers(func.name)
                        callees = self._code_index.get_callees(func.name)
                        loc = SourceLocation(
                            file_path=str(func.file_path),
                            line_number=func.start_line,
                            matched_line=func.signature or func.name,
                            context_before=[],
                            context_after=[],
                            match_score=0.95,
                            search_pattern=f"function:{func_name}",
                            is_log_statement=False,
                            function_name=func.name,
                            function_signature=func.signature,
                            function_start_line=func.start_line,
                            function_end_line=func.end_line,
                            class_name=func.class_name,
                            function_body=func_body,
                            callers=callers,
                            callees=callees,
                        )
                        locations.append(loc)
                    if locations:
                        logger.info(f"Found function '{func_name}' directly from error message")
                        return locations
        result = await locator.find_source(error.message, max_results=3, component=error.component)
        return result.locations

    def _generate_queries_from_locations(self, source_locations: list) -> list:
        from srcs.models.knowledge import EvidenceQueryTemplate

        queries = []
        seen_functions: set[str] = set()
        confident_locations = [loc for loc in source_locations if loc.match_score and loc.match_score > 0.5][:3]
        for loc in confident_locations:
            if loc.function_name and loc.function_name not in seen_functions:
                seen_functions.add(loc.function_name)
                queries.append(
                    EvidenceQueryTemplate(
                        query_type="function_lookup",
                        query_template=loc.function_name,
                        expected_result=f"Error source: {loc.function_name} at {loc.file_path}:{loc.line_number}",
                        full_source=True,
                    )
                )
            if loc.callers:
                for caller in loc.callers[:3]:
                    caller_name = caller.get("name") or caller.get("caller_name")
                    if caller_name and caller_name not in seen_functions:
                        seen_functions.add(caller_name)
                        queries.append(
                            EvidenceQueryTemplate(
                                query_type="function_lookup",
                                query_template=caller_name,
                                expected_result=f"Caller of {loc.function_name}: may show error trigger path",
                                full_source=True,
                            )
                        )
            if loc.class_name:
                queries.append(
                    EvidenceQueryTemplate(
                        query_type="class_lookup",
                        query_template=loc.class_name,
                        expected_result=f"Class definition for {loc.class_name}",
                    )
                )
        return queries[:8]

    def _extract_code_hints(self, source_locations: list) -> list[dict]:
        all_hints: list[dict] = []
        for loc in source_locations[:3]:
            if not loc.function_body:
                continue
            explicit_hints = self._hint_extractor.find_explicit_cause_hints(loc.function_body)
            for explicit_hint in explicit_hints:
                all_hints.append(
                    {
                        "type": "explicit_cause",
                        "content": explicit_hint["content"],
                        "source_function": loc.function_name,
                        "source_file": loc.file_path,
                        "confidence": loc.match_score or 0.5,
                        "is_authoritative": True,
                        "full_match": explicit_hint.get("full_match", ""),
                    }
                )
            causal_hints = self._hint_extractor.find_causal_hints(loc.function_body)
            for causal_hint in causal_hints:
                all_hints.append(
                    {
                        "type": "causal",
                        "content": causal_hint,
                        "source_function": loc.function_name,
                        "source_file": loc.file_path,
                        "confidence": loc.match_score or 0.5,
                        "is_authoritative": False,
                    }
                )
            general_hints = self._hint_extractor.extract_hints(loc.function_body)
            for general_hint in general_hints:
                all_hints.append(
                    {
                        "type": general_hint["type"],
                        "content": general_hint["content"],
                        "source_function": loc.function_name,
                        "source_file": loc.file_path,
                        "confidence": (loc.match_score or 0.5) * 0.8,
                        "is_authoritative": False,
                    }
                )
        seen = set()
        unique_hints = []
        for hint in all_hints:
            key = hint["content"].lower()[:50]
            if key not in seen:
                seen.add(key)
                unique_hints.append(hint)
        unique_hints.sort(key=lambda h: (not h.get("is_authoritative", False), -h["confidence"]))
        return unique_hints[:10]

    async def _generate_hypotheses_from_hints(self, hints: list[dict], error_message: str) -> list:
        if self._llm_provider:
            try:
                interpreted = await self._interpret_hints_with_llm(hints, error_message)
                if interpreted:
                    return interpreted
            except Exception as e:
                logger.warning(f"LLM hint interpretation failed: {e}")
        return self._generate_hypotheses_from_hints_rules(hints)

    async def _interpret_hints_with_llm(self, hints: list[dict], error_message: str) -> list | None:
        from srcs.models.knowledge import RecommendedHypothesis

        if not self._llm_provider or not hints:
            return None
        hint_lines = []
        for i, hint in enumerate(hints):
            func = hint.get("source_function", "unknown")
            hint_lines.append(f"[{i}] Type: {hint['type']}, Function: {func}\n    Text: {hint['content']}")
        hints_text = "\n".join(hint_lines)
        template = get_user_prompt(UserPromptType.HINT_INTERPRETATION)
        prompt = template.format(error_message=error_message, hints_text=hints_text)
        system_prompt = get_system_prompt(SystemPromptType.HINT_INTERPRETATION)
        try:
            result = await self._llm_provider.generate_structured(prompt, InterpretedHints, system_prompt=system_prompt)
        except Exception as e:
            logger.warning(f"LLM structured hint interpretation failed: {e}")
            return None
        if not result or not result.hints:
            return None
        hypotheses = []
        for interp in result.hints:
            if not interp.is_diagnostic:
                continue
            idx = interp.original_index
            if idx < 0 or idx >= len(hints):
                continue
            hint = hints[idx]
            is_authoritative = hint.get("is_authoritative", False)
            if hint["type"] == "explicit_cause":
                prior = min(0.95, 0.9 + hint["confidence"] * 0.05)
                source = "code_hint:explicit_cause"
            elif hint["type"] == "causal":
                prior = min(0.85, 0.7 + hint["confidence"] * 0.15)
                source = "code_hint:causal"
            elif hint["type"] in ("log_message", "exception_message"):
                prior = min(0.7, 0.5 + hint["confidence"] * 0.2)
                source = "code_hint:message"
            else:
                prior = min(0.5, 0.3 + hint["confidence"] * 0.2)
                source = f"code_hint:{hint['type']}"
            description = interp.hypothesis
            if hint.get("source_function"):
                description = f"{description} (from {hint['source_function']})"
            hypotheses.append(
                RecommendedHypothesis(
                    description=description, source=source, prior=prior, is_authoritative=is_authoritative
                )
            )
        logger.info(f"LLM interpreted {len(hints)} hints -> {len(hypotheses)} diagnostic hypotheses")
        return hypotheses[:5]

    def _generate_hypotheses_from_hints_rules(self, hints: list[dict]) -> list:
        from srcs.models.knowledge import RecommendedHypothesis

        hypotheses = []
        for hint in hints:
            is_authoritative = hint.get("is_authoritative", False)
            if hint["type"] == "explicit_cause":
                prior = min(0.95, 0.9 + hint["confidence"] * 0.05)
                source = "code_hint:explicit_cause"
            elif hint["type"] == "causal":
                prior = min(0.85, 0.7 + hint["confidence"] * 0.15)
                source = "code_hint:causal"
            elif hint["type"] in ("log_message", "exception_message"):
                prior = min(0.7, 0.5 + hint["confidence"] * 0.2)
                source = "code_hint:message"
            else:
                prior = min(0.5, 0.3 + hint["confidence"] * 0.2)
                source = f"code_hint:{hint['type']}"
            description = hint["content"]
            if hint.get("source_function"):
                description = f"{description} (from {hint['source_function']})"
            hypotheses.append(
                RecommendedHypothesis(
                    description=description, source=source, prior=prior, is_authoritative=is_authoritative
                )
            )
        return hypotheses[:5]

    async def _generate_dataflow_queries(self, source_locations: list) -> list:
        from srcs.models.knowledge import EvidenceQueryTemplate

        queries = []
        seen_functions: set[str] = set()
        for loc in source_locations[:2]:
            if not loc.function_body:
                continue
            try:
                chain, hints = await self._dataflow_tracer.trace_from_error(loc)
                for node in chain.nodes:
                    if node.function_name and node.function_name not in seen_functions:
                        seen_functions.add(node.function_name)
                        queries.append(
                            EvidenceQueryTemplate(
                                query_type="function_lookup",
                                query_template=node.function_name,
                                expected_result=f"Dataflow: {node.data_source} -> {node.variable_name}",
                                full_source=True,
                            )
                        )
                if chain.root_source and chain.root_source not in ("unknown", "error_point"):
                    queries.append(
                        EvidenceQueryTemplate(
                            query_type="code_search",
                            query_template=chain.root_source,
                            expected_result=f"Root data source: {chain.root_source}",
                        )
                    )
            except Exception as e:
                logger.debug(f"Dataflow tracing failed for {loc.function_name}: {e}")
        return queries[:6]

    async def _enrich_with_call_graph_context(self, source_locations: list, error_message: str) -> None:
        for loc in source_locations[:3]:
            if not loc.function_name:
                continue
            try:
                call_graph = await self._archivist_tools.get_call_graph_with_bodies(loc.function_name)
                if "error" in call_graph:
                    continue
                detailed_summaries = []
                purpose_dict: dict[str, str] = {}
                if self._llm_provider:
                    detailed_summaries = await self._archivist_tools.summarize_call_graph(
                        call_graph, error_context=error_message, error_file=loc.file_path, error_line=loc.line_number
                    )
                    purpose_dict = self._archivist_tools.summaries_to_purpose_dict(detailed_summaries)
                diagram = self._archivist_tools.generate_call_graph_diagram(call_graph, detailed_summaries)
                if call_graph.get("callers"):
                    loc.callers = call_graph["callers"]
                    for caller in loc.callers:
                        name = caller.get("caller_name")
                        if name and name in purpose_dict:
                            caller["summary"] = purpose_dict[name]
                if call_graph.get("callees"):
                    loc.callees = call_graph["callees"]
                    for callee in loc.callees:
                        name = callee.get("callee_name")
                        if name and name in purpose_dict:
                            callee["summary"] = purpose_dict[name]
                loc.call_graph_diagram = diagram
                loc.function_summaries = [s.model_dump() for s in detailed_summaries]
            except Exception as e:
                logger.debug(f"Failed to enrich call graph for {loc.function_name}: {e}")

    async def _populate_binder(self, binder: "WorkBinder", source_locations: list, error_message: str) -> None:
        persona_name = "Archivist"
        phase = 0
        for loc in source_locations[:5]:
            try:
                binder.add_source_location(
                    file_path=loc.file_path,
                    line_number=loc.line_number,
                    created_by=persona_name,
                    phase=phase,
                    match_score=loc.match_score or 0.0,
                    matched_line=loc.matched_line,
                    function_name=loc.function_name,
                    function_body=loc.function_body,
                    function_signature=loc.function_signature,
                    context_before=loc.context_before,
                    context_after=loc.context_after,
                )
                if loc.function_name and (loc.callers or loc.callees):
                    binder.add_call_graph(
                        center_function=loc.function_name,
                        callers=loc.callers or [],
                        callees=loc.callees or [],
                        created_by=persona_name,
                        phase=phase,
                        diagram=loc.call_graph_diagram,
                    )
                for summary_dict in loc.function_summaries:
                    try:
                        func_name = summary_dict.get("function_name", "unknown")
                        role = "CALLEE"
                        if loc.callers:
                            for c in loc.callers:
                                if c.get("caller_name") == func_name:
                                    role = "CALLER"
                                    break
                        binder.add_function_summary(
                            function_name=func_name,
                            purpose=summary_dict.get("purpose", ""),
                            mechanism=summary_dict.get("mechanism", ""),
                            data_flow=summary_dict.get("data_flow", ""),
                            error_paths=summary_dict.get("error_paths", ""),
                            error_line_relevance=summary_dict.get("error_line_relevance", ""),
                            center_function=loc.function_name or "",
                            role=role,
                            created_by=persona_name,
                            phase=phase,
                            file_path=loc.file_path,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to add function summary for {summary_dict.get('function_name')}: {e}")
                if loc.function_body and loc.function_name:
                    binder.add_code_snippet(
                        file_path=loc.file_path,
                        start_line=loc.line_number,
                        end_line=loc.line_number + loc.function_body.count("\n"),
                        content=loc.function_body,
                        created_by=persona_name,
                        phase=phase,
                        language="cpp",
                        function_name=loc.function_name,
                    )
            except Exception as e:
                logger.debug(f"Failed to add artifact for {loc.file_path}: {e}")

    def _extract_function_calls_from_body(self, function_body: str) -> list[str]:
        calls = []
        call_pattern = re.compile("(?:->|\\.)?([a-zA-Z_]\\w*(?:::\\w+)*)\\s*\\(", re.MULTILINE)
        for match in call_pattern.finditer(function_body):
            func_name = match.group(1)
            if func_name.lower() not in ("if", "for", "while", "switch", "catch", "sizeof"):
                calls.append(func_name)
        seen = set()
        unique_calls = []
        for call in calls:
            if call not in seen:
                seen.add(call)
                unique_calls.append(call)
        return unique_calls

    async def _parse_error_numeric_context(self, error_message: str, binder: "WorkBinder") -> ParsedErrorContext | None:
        numeric_analysis = self._numeric_extractor.analyze(error_message)
        if not numeric_analysis.values:
            logger.debug("No numeric values found in error message")
            return None
        if self._llm_provider:
            try:
                parsed_context = await self._llm_parse_error_context(error_message, numeric_analysis)
                if parsed_context:
                    self._store_parsed_context_in_binder(binder, parsed_context)
                    evidence_ids = self._inject_numeric_evidence(binder, parsed_context, numeric_analysis)
                    if evidence_ids:
                        logger.info(f"Injected {len(evidence_ids)} numeric evidence artifacts")
                return parsed_context
            except Exception as e:
                logger.warning(f"LLM numeric parsing failed: {e}")
                return self._create_context_from_regex_analysis(numeric_analysis)
        else:
            return self._create_context_from_regex_analysis(numeric_analysis)

    async def _llm_parse_error_context(
        self, error_message: str, numeric_analysis: "NumericAnalysis"
    ) -> ParsedErrorContext | None:
        values_text = self._numeric_extractor.format_for_hypothesis(numeric_analysis)
        template = get_user_prompt(UserPromptType.ERROR_CONTEXT_PARSING)
        prompt = template.format(error_message=error_message, numeric_values=values_text)
        system_prompt = get_system_prompt(SystemPromptType.ERROR_CONTEXT_PARSING)
        if self._llm_provider is None:
            return None
        try:
            result = await self._llm_provider.generate_structured(
                prompt, ParsedErrorContext, system_prompt=system_prompt
            )
            return result
        except Exception as e:
            logger.warning(f"LLM structured generation failed: {e}")
            return None

    def _create_context_from_regex_analysis(self, numeric_analysis: "NumericAnalysis") -> ParsedErrorContext:
        parsed_values = []
        for v in numeric_analysis.values:
            parsed_values.append(
                ParsedNumericValue(value=v.value, unit=v.unit, label=v.value_type, raw_text=v.raw_match)
            )
        timestamp_analysis = ""
        if numeric_analysis.timestamp_gap_us:
            timestamp_analysis = f"Timestamp gap of {numeric_analysis.timestamp_gap_human} detected"
        timeout_analysis = ""
        if numeric_analysis.timeout_exceeded_by_us:
            timeout_analysis = f"Timeout exceeded by {self._numeric_extractor._format_duration(numeric_analysis.timeout_exceeded_by_us)} ({numeric_analysis.timeout_exceeded_percent:.0f}% over limit)"
        likely_cause = ""
        confidence = 0.3
        if numeric_analysis.buffer_behind_window_us:
            likely_cause = f"Upstream data production latency: buffer's latest data is {numeric_analysis.buffer_behind_window_human} behind the request window. Data IS arriving but too slowly to close the window before the timeout."
            confidence = 0.85
        elif numeric_analysis.timeout_exceeded_by_us and numeric_analysis.timestamp_gap_us:
            likely_cause = (
                f"Data is arriving {numeric_analysis.timestamp_gap_human} behind schedule, causing timeout violation"
            )
        elif numeric_analysis.timeout_exceeded_by_us:
            likely_cause = "Operation exceeded configured timeout threshold"
        elif numeric_analysis.timestamp_gap_us:
            likely_cause = f"Data latency of {numeric_analysis.timestamp_gap_human}"
        if confidence <= 0.3 and likely_cause:
            confidence = 0.6
            if numeric_analysis.timeout_exceeded_by_us and numeric_analysis.timestamp_gap_us:
                confidence = 0.85
            elif numeric_analysis.timeout_exceeded_by_us or numeric_analysis.timestamp_gap_us:
                confidence = 0.75
        return ParsedErrorContext(
            function_name="",
            error_type="timeout" if numeric_analysis.timeout_exceeded_by_us else "unknown",
            numeric_values=parsed_values,
            timestamp_analysis=timestamp_analysis,
            timeout_analysis=timeout_analysis,
            data_gap_description=numeric_analysis.interpretation,
            likely_cause=likely_cause,
            confidence=confidence,
        )

    def _store_parsed_context_in_binder(self, binder: "WorkBinder", parsed_context: ParsedErrorContext) -> None:
        content_parts = []
        if parsed_context.timestamp_analysis:
            content_parts.append(f"**Timestamp Analysis**: {parsed_context.timestamp_analysis}")
        if parsed_context.timeout_analysis:
            content_parts.append(f"**Timeout Analysis**: {parsed_context.timeout_analysis}")
        if parsed_context.data_gap_description:
            content_parts.append(f"**Data Gap**: {parsed_context.data_gap_description}")
        if parsed_context.likely_cause:
            content_parts.append(f"**Likely Cause**: {parsed_context.likely_cause}")
        if parsed_context.numeric_values:
            values_text = ", ".join((f"{v.label}={v.value}{v.unit}" for v in parsed_context.numeric_values[:5]))
            content_parts.append(f"**Key Values**: {values_text}")
        content = "\n".join(content_parts)
        try:
            binder.add_finding(
                persona="Archivist",
                finding_type="observation",
                content=content,
                confidence=parsed_context.confidence,
                phase=0,
                tags=["numeric_analysis", "error_context"],
            )
            logger.info("Stored parsed numeric context in binder")
        except Exception as e:
            logger.debug(f"Failed to store parsed context in binder: {e}")

    def _inject_numeric_evidence(
        self, binder: "WorkBinder", parsed_context: ParsedErrorContext, numeric_analysis: "NumericAnalysis"
    ) -> list[str]:
        evidence_ids: list[str] = []
        base_strength = "MODERATE"
        if parsed_context.timestamp_analysis:
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Timestamp analysis: {parsed_context.timestamp_analysis}",
                source="numeric_analysis:timestamp",
                strength=base_strength,
                created_by="Archivist",
                phase=0,
                tags=["numeric_evidence", "error_derived", "pending_hypothesis_link:numeric_analysis"],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected timestamp analysis evidence: {ev_id}")
        if numeric_analysis.timestamp_gap_us:
            gap_ticks = numeric_analysis.timestamp_gap_us
            gap_seconds = gap_ticks / 1000000
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Calculated timestamp gap: {gap_ticks:,} us (= {gap_seconds:.3f} seconds). {numeric_analysis.timestamp_gap_human}",
                source="numeric_analysis:timestamp_gap_calculated",
                strength="MODERATE",
                created_by="Archivist",
                phase=0,
                tags=["numeric_evidence", "error_derived", "timestamp_gap", "pending_hypothesis_link:numeric_analysis"],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected timestamp gap evidence: {ev_id}")
        if numeric_analysis.timeout_exceeded_by_us:
            exceeded = numeric_analysis.timeout_exceeded_by_us
            percent = numeric_analysis.timeout_exceeded_percent or 0
            exceeded_seconds = exceeded / 1000000
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Timeout exceeded by {exceeded:,} us (= {exceeded_seconds:.3f} seconds), {percent:.1f}% over limit",
                source="numeric_analysis:timeout_exceeded_calculated",
                strength="MODERATE",
                created_by="Archivist",
                phase=0,
                tags=[
                    "numeric_evidence",
                    "error_derived",
                    "timeout_exceeded",
                    "pending_hypothesis_link:numeric_analysis",
                ],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected timeout exceeded evidence: {ev_id}")
        if parsed_context.timeout_analysis and (not numeric_analysis.timeout_exceeded_by_us):
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Timeout analysis: {parsed_context.timeout_analysis}",
                source="numeric_analysis:timeout",
                strength=base_strength,
                created_by="Archivist",
                phase=0,
                tags=["numeric_evidence", "error_derived", "pending_hypothesis_link:numeric_analysis"],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected timeout analysis evidence: {ev_id}")
        if numeric_analysis.buffer_behind_window_us:
            gap = numeric_analysis.buffer_behind_window_us
            gap_seconds = gap / 1000000
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Cross-range analysis: buffer's latest data is {gap:,} us (= {gap_seconds:.3f} seconds) behind the request window maximum. Data IS arriving but too slowly to close the window before the timeout.",
                source="numeric_analysis:buffer_behind_window",
                strength="MODERATE",
                created_by="Archivist",
                phase=0,
                tags=[
                    "numeric_evidence",
                    "error_derived",
                    "buffer_behind_window",
                    "pending_hypothesis_link:numeric_analysis",
                ],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected buffer-behind-window evidence: {ev_id}")
        if parsed_context.data_gap_description:
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Data gap: {parsed_context.data_gap_description}",
                source="numeric_analysis:data_gap",
                strength=base_strength,
                created_by="Archivist",
                phase=0,
                tags=["numeric_evidence", "error_derived", "data_gap", "pending_hypothesis_link:numeric_analysis"],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected data gap evidence: {ev_id}")
        if parsed_context.likely_cause:
            cause_strength = "MODERATE"
            ev_id = binder.add_evidence(
                evidence_type="numeric",
                content=f"Likely cause from numeric analysis: {parsed_context.likely_cause}",
                source="numeric_analysis:likely_cause",
                strength=cause_strength,
                created_by="Archivist",
                phase=0,
                tags=["numeric_evidence", "error_derived", "likely_cause", "pending_hypothesis_link:numeric_analysis"],
            )
            evidence_ids.append(ev_id)
            logger.debug(f"Injected likely cause evidence: {ev_id}")
        return evidence_ids

    def _generate_hypotheses_from_numeric_analysis(self, parsed_context: ParsedErrorContext) -> list:
        from srcs.models.knowledge import RecommendedHypothesis

        hypotheses = []
        if parsed_context.likely_cause:
            prior = min(0.85, 0.7 + parsed_context.confidence * 0.15)
            description = parsed_context.likely_cause
            if parsed_context.timestamp_analysis:
                description = f"{description}. {parsed_context.timestamp_analysis}"
            if parsed_context.timeout_analysis:
                description = f"{description}. {parsed_context.timeout_analysis}"
            hypotheses.append(
                RecommendedHypothesis(
                    description=description, source="numeric_analysis", prior=prior, is_authoritative=False
                )
            )
        if parsed_context.data_gap_description and parsed_context.timestamp_analysis:
            hypotheses.append(
                RecommendedHypothesis(
                    description=f"Data pipeline latency: {parsed_context.timestamp_analysis}. {parsed_context.data_gap_description}",
                    source="numeric_analysis:data_gap",
                    prior=0.75,
                    is_authoritative=False,
                )
            )
        if parsed_context.timeout_analysis and (not any(("timeout" in h.description.lower() for h in hypotheses))):
            hypotheses.append(
                RecommendedHypothesis(
                    description=f"Timeout violation: {parsed_context.timeout_analysis}",
                    source="numeric_analysis:timeout",
                    prior=0.7,
                    is_authoritative=False,
                )
            )
        return hypotheses[:3]
