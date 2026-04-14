"""
File: evidence_orchestrator.py
Purpose: Evidence Orchestrator - Manages iterative evidence seeking.
Category: Utility
Author: artdaq team
Depends: coordinator, tools, knowledge, llm, token_utils, ...
Exports: ArtifactAssessment, ArtifactEvaluationResponse, EvidenceOrchestrator
Complexity: High | Lines: 1101
"""

import logging
import re
from typing import TYPE_CHECKING
from pydantic import BaseModel
from srcs.knowledge import KnowledgeBase
from srcs.llm import LLMProvider
from srcs.models import Evidence, EvidenceItem, Hypothesis, PriorKnowledge
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts.parsers import QueryResponse
from srcs.workbinder.relevance import select_artifacts
from .strategy import EvidenceStrategy

if TYPE_CHECKING:
    from srcs.agent.coordinator import EvidenceConfig
    from srcs.agent.tools import CodeForensicsTools, CodeTools, InvestigationTools, PatternTools
    from srcs.workbinder import WorkBinder
logger = logging.getLogger(__name__)


class ArtifactAssessment(BaseModel):
    artifact_id: str = ""
    hypothesis_id: str = ""
    relationship: str = "neutral"
    strength: str = "WEAK"
    reasoning: str = ""


class ArtifactEvaluationResponse(BaseModel):
    assessments: list[ArtifactAssessment] = []


class EvidenceOrchestrator:

    def __init__(
        self,
        llm: LLMProvider,
        kb: KnowledgeBase,
        max_iterations: int = 10,
        investigation_tools: "InvestigationTools | None" = None,
        code_tools: "CodeTools | None" = None,
        pattern_tools: "PatternTools | None" = None,
        forensics_tools: "CodeForensicsTools | None" = None,
        default_function_source_length: int = 2000,
        config: "EvidenceConfig | None" = None,
    ):
        from srcs.agent.coordinator import EvidenceConfig

        self.llm = llm
        self.kb = kb
        self.max_iterations = max_iterations
        self._investigation_tools = investigation_tools
        self._code_tools = code_tools
        self._pattern_tools = pattern_tools
        self._forensics_tools = forensics_tools
        self._default_function_source_length = default_function_source_length
        self._strategy: EvidenceStrategy | None = None
        self._binder: "WorkBinder | None" = None
        self._analyzed_functions: set[str] = set()
        self.config = config or EvidenceConfig()

    def _get_max_tokens(self) -> int:
        if self.llm is not None and hasattr(self.llm, "config"):
            return self.llm.config.max_tokens or 50000
        return 50000

    async def seek(
        self, hypotheses: list[Hypothesis], initial_evidence: Evidence, prior: PriorKnowledge, binder: "WorkBinder"
    ) -> tuple[Evidence, list[Hypothesis]]:
        evidence = initial_evidence
        self._prior = prior
        self._binder = binder
        self._analyzed_functions.clear()
        if self._investigation_tools and self._investigation_tools.context_logs:
            context_log_count = len(self._investigation_tools.context_logs)
        else:
            context_log_count = len([item for item in initial_evidence.items.values() if item.evidence_type == "log"])
        self._strategy = EvidenceStrategy(
            has_context_logs=context_log_count > 0,
            context_log_count=context_log_count,
            consecutive_failure_limit=self.config.consecutive_failure_limit,
            min_success_rate=self.config.min_success_rate,
            min_attempts_for_rate=self.config.min_attempts_for_rate,
        )
        if context_log_count == 0:
            self._strategy.mode = "code_centric"
            logger.info("No context logs available, using code-centric strategy")
        artifact_evidence = await self._evaluate_binder_artifacts(hypotheses, binder)
        if artifact_evidence.items:
            evidence = self._merge_evidence(evidence, artifact_evidence)
            hypotheses = self._update_scores(hypotheses, artifact_evidence)
            logger.info(f"Binder artifact evaluation: {len(artifact_evidence.items)} evidence items")
        for iteration in range(self.max_iterations):
            logger.debug(
                f"Evidence seeking iteration {iteration + 1}/{self.max_iterations} (mode: {self._strategy.mode})"
            )
            if iteration == 0:
                early_evidence = await self._early_source_lookup(hypotheses, prior)
                if early_evidence.items:
                    evidence = self._merge_evidence(evidence, early_evidence)
                    hypotheses = self._update_scores(hypotheses, early_evidence)
                    logger.info(f"Early source lookup found {len(early_evidence.items)} evidence items")
            queries = await self._identify_queries(hypotheses, evidence, prior)
            if not queries:
                logger.debug("No more queries identified, stopping")
                break
            queries = self._strategy.prioritize_queries(queries)
            queries = [q for q in queries if not self._strategy.should_skip_query(q.get("query_type", ""))]
            if not queries:
                logger.debug("All query types exhausted or skipped, stopping")
                break
            max_queries = self.config.max_queries_per_iteration
            new_evidence = await self._execute_queries(queries[:max_queries], evidence)
            if not new_evidence.items:
                logger.debug("No new evidence found, stopping")
                break
            evidence = self._merge_evidence(evidence, new_evidence)
            hypotheses = self._update_scores(hypotheses, new_evidence)
            if self._should_stop(hypotheses, iteration):
                logger.debug("Stopping condition met")
                break
        mem_to_binder_id: dict[str, str] = {}
        for h in hypotheses:
            if h.binder_artifact_id:
                mem_to_binder_id[h.id] = h.binder_artifact_id
            else:
                binder_hypotheses = binder.get_hypotheses()
                for bh in binder_hypotheses:
                    if bh.description == h.description:
                        mem_to_binder_id[h.id] = bh.id
                        break
        for item in evidence.items.values():
            evidence_id = binder.add_evidence(
                evidence_type=item.evidence_type,
                content=item.content,
                source=item.source,
                strength=item.strength,
                created_by="Detective",
                phase=2,
                found=item.found,
                targets_hypothesis_id=item.targets_hypothesis_id,
                expected_if_true=item.expected_if_true,
                expected_if_false=item.expected_if_false,
            )
            linked_to_target = False
            if item.targets_hypothesis_id:
                for h in hypotheses:
                    if h.id == item.targets_hypothesis_id:
                        binder_hyp_id = mem_to_binder_id.get(h.id)
                        if not binder_hyp_id:
                            continue
                        if item.found and item.expected_if_true:
                            binder.link_evidence_to_hypothesis(evidence_id, binder_hyp_id, "supports", "Detective")
                            linked_to_target = True
                        elif item.found and item.expected_if_false:
                            binder.link_evidence_to_hypothesis(evidence_id, binder_hyp_id, "contradicts", "Detective")
                            linked_to_target = True
                        elif item.found:
                            binder.link_evidence_to_hypothesis(evidence_id, binder_hyp_id, "supports", "Detective")
                            linked_to_target = True
            if not linked_to_target and item.found:
                evidence_keywords = self._extract_evidence_keywords(item)
                for h in hypotheses:
                    binder_hyp_id = mem_to_binder_id.get(h.id)
                    if not binder_hyp_id:
                        continue
                    h_lower = h.description.lower()
                    for keyword in evidence_keywords:
                        if keyword.lower() in h_lower:
                            binder.link_evidence_to_hypothesis(evidence_id, binder_hyp_id, "supports", "Detective")
                            break
        for h in hypotheses:
            binder_hyp_id = mem_to_binder_id.get(h.id)
            if binder_hyp_id:
                binder.update_artifact(binder_hyp_id, {"score": h.score, "rank": hypotheses.index(h)}, "Detective")
        return (evidence, hypotheses)

    async def _evaluate_binder_artifacts(self, hypotheses: list[Hypothesis], binder: "WorkBinder") -> Evidence:
        from srcs.workbinder.artifact_renderer import render_artifact

        evidence = Evidence(items={})
        if not hypotheses:
            return evidence
        artifacts = select_artifacts(binder, "detective")
        if not artifacts:
            logger.info("No upstream artifacts to evaluate")
            return evidence
        from srcs.llm.token_utils import truncate_if_needed

        rendered_parts = []
        for artifact in artifacts:
            rendered = render_artifact(artifact)
            if rendered:
                rendered_parts.append(rendered)
        if not rendered_parts:
            return evidence
        artifact_text = truncate_if_needed(
            "\n\n".join(rendered_parts), max_tokens=self._get_max_tokens() // 3, label="upstream artifacts"
        )
        top_hyps = sorted(hypotheses, key=lambda h: h.score, reverse=True)[:8]
        hyp_lines = []
        for i, h in enumerate(top_hyps):
            hyp_lines.append(f"{i + 1}. [id={h.id}] [score={h.score:.2f}] {h.description}")
            if h.confirming_evidence_design:
                hyp_lines.append(f"   Confirming: {h.confirming_evidence_design}")
            if h.refuting_evidence_design:
                hyp_lines.append(f"   Refuting: {h.refuting_evidence_design}")
        hyp_text = "\n".join(hyp_lines)
        template = get_user_prompt(UserPromptType.ARTIFACT_EVALUATION)
        prompt = template.format(artifact_text=artifact_text, hypotheses=hyp_text)
        system_prompt = get_system_prompt(SystemPromptType.ARTIFACT_EVALUATION)
        try:
            response = await self.llm.generate_structured(
                prompt, ArtifactEvaluationResponse, system_prompt=system_prompt
            )
        except Exception as e:
            logger.warning(f"Artifact evaluation LLM call failed: {e}")
            try:
                raw = await self.llm.generate(prompt, system_prompt=system_prompt)
                if raw:
                    from srcs.workbinder.artifacts.parsers.json_utils import parse_json_response

                    response = parse_json_response(raw, ArtifactEvaluationResponse)
                else:
                    return evidence
            except Exception as e2:
                logger.warning(f"Artifact evaluation fallback also failed: {e2}")
                return evidence
        if not response or not response.assessments:
            return evidence
        for assessment in response.assessments:
            if assessment.relationship == "neutral":
                continue
            if assessment.relationship == "supports":
                exp_true = assessment.reasoning[:100]
                exp_false = None
            else:
                exp_true = None
                exp_false = assessment.reasoning[:100]
            item = EvidenceItem(
                evidence_type="artifact_evaluation",
                content=assessment.reasoning,
                source=f"artifact_eval:{assessment.artifact_id}→{assessment.hypothesis_id}",
                strength=assessment.strength,
                found=True,
                targets_hypothesis_id=assessment.hypothesis_id,
                expected_if_true=exp_true,
                expected_if_false=exp_false,
            )
            key = f"artifact_eval_{assessment.artifact_id}_{assessment.hypothesis_id}"
            evidence.items[key] = item
        logger.info(
            f"Artifact evaluation produced {len(evidence.items)} evidence items from {len(artifacts)} upstream artifacts"
        )
        return evidence

    async def _analyze_binder_code_snippets(self, hypotheses: list[Hypothesis], binder: "WorkBinder") -> Evidence:
        evidence = Evidence(items={})
        try:
            snippets = binder.get_code_snippets()
        except Exception:
            return evidence
        if not snippets:
            return evidence
        sorted_snippets = sorted(snippets, key=lambda s: getattr(s, "match_score", 0) or 0, reverse=True)[:2]
        top_hyps = sorted(hypotheses, key=lambda h: h.score, reverse=True)[:3]
        if not top_hyps:
            return evidence
        snippet_text = ""
        for i, s in enumerate(sorted_snippets):
            from srcs.llm.token_utils import truncate_if_needed

            content = truncate_if_needed(s.content, max_tokens=self._get_max_tokens() // 10, label="evidence snippet")
            func_name = getattr(s, "snippet_function_name", "") or ""
            file_path = getattr(s, "file_path", "") or ""
            start = getattr(s, "start_line", "") or ""
            end = getattr(s, "end_line", "") or ""
            snippet_text += f"\n### Snippet {i + 1}: {func_name} ({file_path}:{start}-{end})\n```\n{content}\n```\n"
        hyp_text = ""
        for i, h in enumerate(top_hyps):
            hyp_text += f"\n{i + 1}. [score={h.score:.2f}] {h.description}"
        template = get_user_prompt(UserPromptType.BINDER_CODE_ANALYSIS)
        prompt = template.format(snippet_text=snippet_text, hypotheses=hyp_text)
        system_prompt = get_system_prompt(SystemPromptType.BINDER_CODE_ANALYSIS)
        try:
            response = await self.llm.generate(prompt, system_prompt=system_prompt)
        except Exception as e:
            logger.warning(f"Binder code snippet analysis failed: {e}")
            return evidence
        if not response or not response.strip():
            return evidence
        item = EvidenceItem(
            evidence_type="code_analysis",
            content=response.strip(),
            source="binder_code_snippet_analysis",
            strength="STRONG",
            found=True,
        )
        evidence.items[f"code_analysis_binder_{id(item)}"] = item
        logger.info("Produced code_analysis evidence from binder snippets")
        return evidence

    async def _identify_queries(
        self, hypotheses: list[Hypothesis], evidence: Evidence, prior: PriorKnowledge
    ) -> list[dict]:
        queries = []
        for template in prior.recommended_queries:
            queries.append(
                {
                    "query_type": template.query_type,
                    "query": template.query_template,
                    "from_prior": True,
                    "full_source": template.full_source,
                }
            )
        viable = [h for h in hypotheses if h.score > -0.5]
        if len(viable) > 1:
            try:
                new_queries = await self._generate_queries(hypotheses, evidence)
                queries.extend(new_queries)
            except Exception as e:
                logger.warning(f"Failed to generate queries: {e}")
        return queries[:10]

    async def _early_source_lookup(self, hypotheses: list[Hypothesis], prior: PriorKnowledge) -> Evidence:
        evidence = Evidence()
        if not self._code_tools:
            return evidence
        func_names_to_lookup: list[str] = []
        seen_funcs: set[str] = set()
        if prior.source_locations:
            for loc in prior.source_locations[:3]:
                if loc.function_name and loc.function_name not in seen_funcs:
                    seen_funcs.add(loc.function_name)
                    func_names_to_lookup.append(loc.function_name)
        func_patterns = [
            "\\b([A-Z][a-zA-Z0-9]*(?:_[A-Za-z0-9]+)+)\\b",
            "\\b([A-Z][a-zA-Z0-9]+::[a-zA-Z_][a-zA-Z0-9_]+)\\b",
        ]
        for h in hypotheses[:5]:
            for pattern in func_patterns:
                for match in re.finditer(pattern, h.description):
                    func_name = match.group(1)
                    if func_name not in seen_funcs and len(func_name) >= 8:
                        seen_funcs.add(func_name)
                        func_names_to_lookup.append(func_name)
        for query in prior.recommended_queries:
            if query.query_type == "function_lookup":
                func_name = query.query_template
                if func_name not in seen_funcs:
                    seen_funcs.add(func_name)
                    func_names_to_lookup.append(func_name)
        for func_name in func_names_to_lookup[:5]:
            if func_name in self._analyzed_functions:
                continue
            try:
                results = await self._code_tools.lookup_function(func_name, max_source_length=0)
                self._analyzed_functions.add(func_name.lower())
                if results:
                    for item in results:
                        item.strength = "STRONG"
                        evidence.add(item)
                        logger.debug(f"Early lookup found source for: {func_name}")
            except Exception as e:
                logger.debug(f"Early source lookup failed for {func_name}: {e}")
        return evidence

    async def _generate_queries(self, hypotheses: list[Hypothesis], evidence: Evidence) -> list[dict]:
        template = get_user_prompt(UserPromptType.EVIDENCE_QUERY)
        prompt = template.format(
            hypotheses=self._format_hypotheses(hypotheses),
            evidence=evidence.summary(),
            investigation_mode=self._get_investigation_mode(),
            mode_specific_guidance=self._get_mode_guidance(),
            analyzed_functions=self._format_analyzed_functions(),
            query_effectiveness=self._format_query_effectiveness(),
            documentation_context=self._get_documentation_context(),
            upstream_context=self._get_upstream_context(),
            chronicler_context=self._get_chronicler_context(),
            artifact_context=self._get_artifact_context(),
        )
        try:
            system_prompt = get_system_prompt(SystemPromptType.DETECTIVE)
            response = await self.llm.generate_structured(prompt, QueryResponse, system_prompt=system_prompt)
            return [q.model_dump() for q in response.queries]
        except Exception as e:
            logger.warning(f"Structured query generation failed: {e}")
            return self._generate_fallback_queries(hypotheses, evidence)

    def _generate_fallback_queries(self, hypotheses: list[Hypothesis], evidence: Evidence) -> list[dict]:
        queries: list[dict] = []
        seen_targets: set[str] = set()
        camel_underscore = re.compile("\\b([A-Z][a-zA-Z0-9]*(?:_[A-Za-z0-9]+)+)\\b")
        namespace_func = re.compile("\\b([A-Za-z][a-zA-Z0-9]*::[a-zA-Z_][a-zA-Z0-9_:]+)\\b")
        camel_class = re.compile("\\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\\b")
        for h in hypotheses[:5]:
            desc = h.description
            for match in namespace_func.finditer(desc):
                target = match.group(1)
                if target not in seen_targets and len(target) >= 8:
                    seen_targets.add(target)
                    queries.append(
                        {
                            "query_type": "function_lookup",
                            "query": target,
                            "from_fallback": True,
                            "full_source": True,
                            "targets_hypothesis_id": h.id,
                        }
                    )
            for match in camel_underscore.finditer(desc):
                target = match.group(1)
                if target not in seen_targets and len(target) >= 8:
                    seen_targets.add(target)
                    queries.append(
                        {
                            "query_type": "function_lookup",
                            "query": target,
                            "from_fallback": True,
                            "full_source": True,
                            "targets_hypothesis_id": h.id,
                        }
                    )
            for match in camel_class.finditer(desc):
                target = match.group(1)
                if target not in seen_targets and len(target) >= 8:
                    seen_targets.add(target)
                    queries.append(
                        {
                            "query_type": "class_lookup",
                            "query": target,
                            "from_fallback": True,
                            "targets_hypothesis_id": h.id,
                        }
                    )
        for h in hypotheses[:3]:
            words = h.description.split()
            significant = [
                w
                for w in words
                if len(w) >= 6
                and w.lower()
                not in {
                    "should",
                    "could",
                    "would",
                    "caused",
                    "because",
                    "likely",
                    "possibly",
                    "probably",
                    "returned",
                    "received",
                    "function",
                    "method",
                    "called",
                    "occurs",
                    "happen",
                }
                and (not w[0].islower())
            ]
            for term in significant[:2]:
                if term not in seen_targets:
                    seen_targets.add(term)
                    queries.append(
                        {
                            "query_type": "code_search",
                            "query": term,
                            "from_fallback": True,
                            "targets_hypothesis_id": h.id,
                        }
                    )
        if hypotheses:
            top_h = hypotheses[0]
            queries.append(
                {
                    "query_type": "similar_cases",
                    "query": top_h.description,
                    "from_fallback": True,
                    "targets_hypothesis_id": top_h.id,
                }
            )
        queries = queries[:10]
        if queries:
            logger.info(f"Generated {len(queries)} fallback queries from context")
        else:
            logger.warning("No fallback queries could be generated from context")
        return queries

    def _get_investigation_mode(self) -> str:
        if self._strategy:
            return self._strategy.mode
        return "balanced"

    def _get_mode_guidance(self) -> str:
        if self._strategy and self._strategy.mode == "code_centric":
            return "WARNING: No runtime logs available. Log queries will have very limited results.\nPRIORITIZE: function_lookup, class_lookup, code_search, similar_cases, pattern_lookup.\nDEPRIORITIZE: log_search, log_source, component_logs (limit to 1 per iteration max).\nFocus on testing hypotheses using CODE STRUCTURE rather than runtime behavior.\nUse code analysis to validate the mechanisms described in hypotheses."
        if self._strategy and self._strategy.has_context_logs:
            count = self._strategy.context_log_count
            return f"Runtime log data IS available ({count} log entries from submitted log files).\nPRIORITIZE log queries to find runtime evidence:\n  - log_search: search for specific error messages or patterns in the logs\n  - component_logs: retrieve all messages from a specific component\n  - time_window: get logs within a time range around the error\nCombine log queries with code queries (function_lookup, class_lookup) for full coverage."
        return "Balance code and log queries based on availability and effectiveness."

    def _get_documentation_context(self) -> str:
        prior: PriorKnowledge | None = getattr(self, "_prior", None)
        if prior is not None and prior.documentation_context:
            return prior.documentation_context
        return "(no component documentation available)"

    def _get_artifact_context(self) -> str:
        binder = getattr(self, "_binder", None)
        if binder is None:
            return "(no artifact context available)"
        try:
            from srcs.workbinder.relevance import render_selected_artifacts

            context = render_selected_artifacts(binder, "detective")
            return context if context else "(no artifact context available)"
        except Exception:
            return "(no artifact context available)"

    def _get_chronicler_context(self) -> str:
        binder = getattr(self, "_binder", None)
        if binder is None:
            return "(no Chronicler context available)"
        parts: list[str] = []
        log_bundle = binder.get_log_bundle()
        if log_bundle is not None:
            primary_error = getattr(log_bundle, "primary_error", None)
            if primary_error:
                msg = getattr(primary_error, "message", "")
                fname = getattr(primary_error, "filename", "")
                if msg:
                    pe_text = msg
                    if fname:
                        pe_text += f" (file: {fname})"
                    parts.append(f"### Primary Error\n{pe_text}")
            narrative = getattr(log_bundle, "annotated_narrative", "")
            if narrative:
                parts.append(f"### Analytical Narrative\n{narrative}")
            cascade_desc = getattr(log_bundle, "cascade_description", "")
            if cascade_desc:
                parts.append(f"### Cascade Description\n{cascade_desc}")
            chain = getattr(log_bundle, "cascade_chain", [])
            if chain:
                chain_lines = []
                for link in chain:
                    chain_lines.append(f"- {link.from_board} → {link.to_board}: {link.mechanism}")
                parts.append("### Cascade Chain\n" + "\n".join(chain_lines))
            boards = getattr(log_bundle, "affected_boards", [])
            if boards:
                board_lines = []
                for b in boards:
                    line = f"- {b.board_name} ({b.role})"
                    if getattr(b, "failure_mode", None):
                        line += f": {b.failure_mode}"
                    if getattr(b, "key_error_message", None):
                        line += f" — Key error: {b.key_error_message}"
                    board_lines.append(line)
                parts.append("### Affected Boards\n" + "\n".join(board_lines))
            error_timeline = getattr(log_bundle, "error_timeline", [])
            if error_timeline:
                et_lines = []
                for err in error_timeline[:10]:
                    ts = ""
                    if getattr(err, "timestamp", None):
                        ts = err.timestamp.isoformat() + " "
                    primary = " [PRIMARY]" if err.is_primary else ""
                    et_lines.append(f"- {ts}[{err.level}] {err.message}{primary}")
                parts.append("### Error Timeline\n" + "\n".join(et_lines))
            clues = getattr(log_bundle, "clues", [])
            if clues:
                clue_lines = []
                for clue in clues[:5]:
                    desc = getattr(clue, "description", "")
                    search = getattr(clue, "suggested_search", "")
                    if desc:
                        line = f"- {desc}"
                        if search:
                            line += f" (search: {search})"
                        clue_lines.append(line)
                if clue_lines:
                    parts.append("### Investigation Clues\n" + "\n".join(clue_lines))
        br_id = binder.get_boardreader_identification()
        if br_id is not None:
            br_lines = []
            br_types = getattr(br_id, "boardreader_types", [])
            if br_types:
                br_lines.append(f"Boardreader types: {', '.join(br_types)}")
            components = getattr(br_id, "components", [])
            if components:
                br_lines.append(f"Components: {', '.join(components)}")
            if br_lines:
                parts.append("### Identified Components\n" + "\n".join(br_lines))
        timeline = binder.get_merged_timeline()
        if timeline is not None:
            stat_lines = []
            total = getattr(timeline, "total_entries", 0)
            if total:
                stat_lines.append(f"Total entries: {total}")
            errors = getattr(timeline, "total_errors", 0)
            if errors:
                stat_lines.append(f"Errors: {errors}")
            warnings = getattr(timeline, "total_warnings", 0)
            if warnings:
                stat_lines.append(f"Warnings: {warnings}")
            fc = getattr(timeline, "file_count", 0)
            if fc:
                stat_lines.append(f"Files: {fc}")
            earliest = getattr(timeline, "earliest_timestamp", "")
            latest = getattr(timeline, "latest_timestamp", "")
            if earliest and latest:
                stat_lines.append(f"Time span: {earliest} → {latest}")
            if stat_lines:
                parts.append("### Timeline Statistics\n" + "\n".join(stat_lines))
        return "\n\n".join(parts) if parts else "(no Chronicler context available)"

    def _get_upstream_context(self) -> str:
        prior: PriorKnowledge | None = getattr(self, "_prior", None)
        if prior is None:
            return "(no upstream context available)"
        parts: list[str] = []
        if prior.resolution_digest:
            actions = [rd.resolution_action for rd in prior.resolution_digest[:3] if rd.resolution_action]
            if actions:
                parts.append(
                    """Resolution actions from similar cases:
"""
                    + "\n".join((f"  - {a}" for a in actions))
                )
        config_ctx = prior.configuration_context
        if config_ctx is not None:
            flags = getattr(config_ctx, "deviation_flags", [])
            if flags:
                parts.append("Config deviations:\n" + "\n".join((f"  - {f}" for f in flags[:3])))
        diag = prior.diagnostic_history
        if diag is not None:
            causes = getattr(diag, "common_root_causes", [])
            if causes:
                cause_strs = [f"{cause} ({freq:.0%})" for cause, freq in causes[:3]]
                parts.append("Common root causes:\n" + "\n".join((f"  - {c}" for c in cause_strs)))
        if prior.enriched_case_summaries:
            for summary in prior.enriched_case_summaries[:2]:
                parts.append(f"Past case: {summary}")
        source_locs = getattr(prior, "source_locations", [])
        if source_locs:
            loc_lines = []
            for loc in source_locs[:3]:
                fn = getattr(loc, "function_name", "") or "unknown"
                fp = getattr(loc, "file_path", "")
                ln = getattr(loc, "line_number", 0)
                score = getattr(loc, "match_score", 0.0)
                summary = getattr(loc, "function_summary", "") or ""
                line = f"- {fn} ({fp}:{ln}, score={score:.2f})"
                if summary:
                    line += f"\n    Summary: {summary[:200]}"
                loc_lines.append(line)
            parts.append("Source locations found:\n" + "\n".join(loc_lines))
            func_summary_lines: list[str] = []
            for loc in source_locs[:2]:
                summaries = getattr(loc, "function_summaries", [])
                for fs in summaries[:3]:
                    name = fs.get("function_name", "unknown")
                    purpose = fs.get("purpose", "")
                    error_paths = fs.get("error_paths", "")
                    if purpose:
                        line = f"- {name}: {purpose[:150]}"
                        if error_paths:
                            line += f"\n    Error paths: {error_paths[:150]}"
                        func_summary_lines.append(line)
            if func_summary_lines:
                parts.append("Key function summaries:\n" + "\n".join(func_summary_lines))
        return "\n".join(parts) if parts else "(no upstream context available)"

    def _format_analyzed_functions(self) -> str:
        if self._analyzed_functions:
            return ", ".join(sorted(self._analyzed_functions))
        return "None yet"

    def _format_query_effectiveness(self) -> str:
        if not self._strategy or not self._strategy.query_stats:
            return "No data yet - this is the first query round."
        lines = []
        for qt, stats in sorted(self._strategy.query_stats.items()):
            status = "effective" if stats.is_effective else "SKIP (ineffective)"
            rate = f"{stats.success_rate:.0%}" if stats.attempts > 0 else "N/A"
            lines.append(f"- {qt}: {rate} success rate ({stats.attempts} attempts) - {status}")
        return "\n".join(lines) if lines else "No data yet"

    async def _execute_queries(self, queries: list[dict], existing_evidence: Evidence) -> Evidence:
        evidence = Evidence()
        if self._strategy and self._strategy.mode == "code_centric":
            log_query_types = {"log_search", "log_source", "component_logs", "time_window"}
            log_queries = [q for q in queries if q.get("query_type") in log_query_types]
            code_queries = [q for q in queries if q.get("query_type") not in log_query_types]
            if self._strategy.has_context_logs:
                queries = code_queries + log_queries[:1]
            else:
                queries = code_queries
            if log_queries:
                allowed = len(queries) - len(code_queries)
                logger.debug(f"Code-centric mode: {len(log_queries)} log queries -> {allowed} allowed")
        for query in queries:
            query_type = query.get("query_type", "unknown")
            query_str = query.get("query", "")
            query_key = f"{query_type}:{query_str}"
            if any((query_key in item.source for item in existing_evidence.items.values())):
                continue
            results = await self._execute_single_query(query_type, query_str, query)
            found = bool(results)
            if self._strategy:
                self._strategy.record_query_result(query_type, found)
            if results:
                for item in results:
                    item.targets_hypothesis_id = query.get("targets_hypothesis_id")
                    item.expected_if_true = query.get("expected_if_true")
                    item.expected_if_false = query.get("expected_if_false")
                    evidence.add(item)
            else:
                item = EvidenceItem(
                    evidence_type=query_type,
                    content=f"Query executed but found no results: {query_str}",
                    source=f"query:{query_key}",
                    strength="WEAK",
                    found=False,
                    targets_hypothesis_id=query.get("targets_hypothesis_id"),
                    expected_if_true=query.get("expected_if_true"),
                    expected_if_false=query.get("expected_if_false"),
                )
                evidence.add(item)
        return evidence

    async def _execute_single_query(self, query_type: str, query_str: str, query: dict) -> list[EvidenceItem]:
        results: list[EvidenceItem] = []
        if query_type == "function_lookup":
            func_key = query_str.split("::")[-1].lower()
            if func_key in self._analyzed_functions:
                logger.debug(f"Skipping duplicate function lookup: {query_str}")
                return []
            self._analyzed_functions.add(func_key)
        try:
            if query_type == "log_search" and self._investigation_tools:
                results = await self._investigation_tools.search_logs(query_str)
            elif query_type == "component_logs" and self._investigation_tools:
                component = query.get("component", query_str)
                results = await self._investigation_tools.get_logs_by_component(component)
            elif query_type == "similar_cases" and self._investigation_tools:
                results = await self._investigation_tools.lookup_similar_cases(query_str)
            elif query_type == "time_window" and self._investigation_tools:
                start = query.get("start_seconds", 5.0)
                end = query.get("end_seconds", 1.0)
                if self._investigation_tools.context_logs:
                    ref_log = self._investigation_tools.context_logs[0]
                    results = await self._investigation_tools.get_logs_in_window(start, end, ref_log)
            elif query_type == "function_lookup" and self._code_tools:
                if query.get("full_source") is True:
                    max_source_length = 0
                else:
                    max_source_length = self._default_function_source_length
                results = await self._code_tools.lookup_function(query_str, max_source_length=max_source_length)
            elif query_type == "class_lookup" and self._code_tools:
                results = await self._code_tools.lookup_class(query_str)
            elif query_type == "code_search" and self._code_tools:
                results = await self._code_tools.search_symbols(query_str)
            elif query_type == "log_source" and self._code_tools:
                results = await self._code_tools.get_log_source(query_str)
            elif query_type == "pattern_lookup" and self._pattern_tools:
                results = await self._pattern_tools.lookup_error_pattern(query_str)
            elif query_type == "accuracy_check" and self._pattern_tools:
                pattern_id = query.get("pattern_id")
                results = await self._pattern_tools.get_historical_accuracy(pattern_id)
            elif query_type == "trace_variable" and self._forensics_tools:
                var_name = query.get("variable", query_str)
                file_path = query.get("file_path", "")
                line_number = query.get("line_number", 0)
                results = await self._forensics_tools.trace_variable(var_name, file_path, line_number)
            elif query_type == "error_path" and self._forensics_tools:
                results = await self._forensics_tools.find_error_path(query_str)
            elif query_type == "caller_chain" and self._forensics_tools:
                max_depth = query.get("max_depth", 5)
                results = await self._forensics_tools.get_caller_chain(query_str, max_depth)
            else:
                logger.debug(f"No tool available for query type '{query_type}', creating stub")
                results = [
                    EvidenceItem(
                        evidence_type=query_type,
                        content=f"Query executed: {query_str}",
                        source=f"query:{query_type}:{query_str}",
                        strength=self._determine_fallback_strength(query_type),
                        found=True,
                    )
                ]
        except Exception as e:
            logger.warning(f"Query execution failed for {query_type}: {e}")
        return results

    def _determine_fallback_strength(self, query_type: str) -> str:
        if query_type in ("function_lookup", "pattern_lookup", "log_source"):
            return "MODERATE"
        return "WEAK"

    def _update_scores(self, hypotheses: list[Hypothesis], new_evidence: Evidence) -> list[Hypothesis]:
        for h in hypotheses:
            for item in new_evidence.items.values():
                is_targeted = item.targets_hypothesis_id == h.id
                if is_targeted:
                    score_delta = self._score_targeted_evidence(item, h)
                    if score_delta > 0:
                        h.score += score_delta
                        h.supporting_evidence_ids.append(item.id)
                    elif score_delta < 0:
                        h.score += score_delta
                        h.contradicting_evidence_ids.append(item.id)
                else:
                    relevance = self._assess_relevance(item, h)
                    strength_mult = self._strength_multiplier(item.strength)
                    is_code_evidence = item.evidence_type in (
                        "function_lookup",
                        "class_lookup",
                        "code_search",
                        "log_source",
                        "trace_variable",
                        "error_path",
                        "caller_chain",
                    )
                    is_code_hint_match = self._is_code_hint_evidence_match(item, h)
                    if is_code_hint_match:
                        non_targeted_factor = self.config.code_hint_match_factor
                    elif is_code_evidence:
                        non_targeted_factor = self.config.non_targeted_code_factor
                    else:
                        non_targeted_factor = self.config.non_targeted_log_factor
                    if relevance > 0:
                        h.score += relevance * strength_mult * non_targeted_factor
                        h.supporting_evidence_ids.append(item.id)
                    elif relevance < 0:
                        h.score += relevance * strength_mult * non_targeted_factor
                        h.contradicting_evidence_ids.append(item.id)
        hypotheses.sort(key=lambda h: h.score, reverse=True)
        for h in hypotheses:
            h.score = max(-1.0, min(1.0, h.score))
        return hypotheses

    def _extract_evidence_keywords(self, item: EvidenceItem) -> list[str]:
        keywords = []
        if item.source:
            parts = item.source.split(":")
            if len(parts) > 1:
                keywords.append(parts[-1])
            ns_match = re.search("([A-Za-z]+::[\\w_]+)", item.source)
            if ns_match:
                keywords.append(ns_match.group(1))
        func_patterns = [
            "\\b([A-Z][a-zA-Z0-9]*(?:_[A-Za-z0-9]+)+)\\b",
            "\\b([A-Za-z]+::[a-zA-Z_][a-zA-Z0-9_]+)\\b",
            "\\b([a-z]+_[a-z_]+)\\b",
        ]
        content = item.content
        for pattern in func_patterns:
            for match in re.finditer(pattern, content):
                term = match.group(1)
                if len(term) >= 8:
                    keywords.append(term)
        seen = set()
        unique = []
        for k in keywords:
            k_lower = k.lower()
            if k_lower not in seen and len(k) >= 5:
                seen.add(k_lower)
                unique.append(k)
        return unique[:10]

    def _is_code_hint_evidence_match(self, item: EvidenceItem, hypothesis: Hypothesis) -> bool:
        if not hypothesis.source.startswith("code_hint:"):
            return False
        if "(from " in hypothesis.description:
            func_match = hypothesis.description.split("(from ")[-1].rstrip(")")
            if func_match and func_match.lower() in item.source.lower():
                return True
            if func_match and func_match.lower() in item.content.lower():
                return True
        return False

    def _score_targeted_evidence(self, item: EvidenceItem, hypothesis: Hypothesis) -> float:
        content_lower = item.content.lower()
        strength_mult = self._strength_multiplier(item.strength)
        if not item.found:
            if item.expected_if_true:
                return -strength_mult * self.config.absence_contradict_factor
            return 0.0
        if item.expected_if_true:
            expected_terms = self._extract_key_terms(item.expected_if_true)
            if self._content_matches_terms(content_lower, expected_terms):
                return strength_mult * self.config.targeted_boost_factor
        if item.expected_if_false:
            expected_terms = self._extract_key_terms(item.expected_if_false)
            if self._content_matches_terms(content_lower, expected_terms):
                return -strength_mult * self.config.targeted_contradict_factor
        relevance = self._assess_relevance(item, hypothesis)
        return relevance * strength_mult

    def _extract_key_terms(self, expectation: str) -> list[str]:
        words = re.split("[\\s,;:]+", expectation.lower())
        stopwords = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "if",
            "then",
            "else",
            "when",
            "where",
            "which",
            "that",
            "this",
            "these",
            "those",
            "of",
            "to",
            "for",
            "with",
            "on",
            "at",
            "by",
            "from",
            "or",
            "and",
            "not",
            "no",
            "yes",
            "we",
            "find",
            "see",
            "found",
            "shows",
            "show",
            "indicates",
        }
        return [w for w in words if len(w) > 3 and w not in stopwords]

    def _content_matches_terms(self, content: str, terms: list[str]) -> bool:
        if not terms:
            return False
        threshold = self.config.term_match_threshold
        matches = sum((1 for term in terms if term in content))
        return matches >= len(terms) * threshold

    def _assess_relevance(self, item: EvidenceItem, hypothesis: Hypothesis) -> float:
        desc_lower = hypothesis.description.lower()
        content_lower = item.content.lower()
        relevance = 0.0
        if any(
            (
                term in desc_lower
                for term in ["race condition", "concurrency", "thread", "synchronization", "deadlock", "mutex"]
            )
        ):
            if any(
                (
                    s in content_lower
                    for s in ["mutex", "lock_guard", "unique_lock", "atomic", "synchronized", "critical_section"]
                )
            ):
                relevance -= 0.25
            if re.search("std::thread|pthread|boost::thread", content_lower):
                if not any((s in content_lower for s in ["mutex", "lock", "atomic"])):
                    relevance += 0.2
        if any((term in desc_lower for term in ["configuration", "config", "parameter", "setting", "fhicl", "fcl"])):
            if re.search("config|param|fhicl|pset|getenv|get_if_present", content_lower):
                relevance += 0.2
            if re.search("default|fallback|missing.*param", content_lower):
                relevance += 0.15
        if any((term in desc_lower for term in ["resource", "memory", "allocation", "exhaustion", "leak", "buffer"])):
            if re.search("alloc|malloc|new\\s+|make_unique|make_shared|buffer|capacity", content_lower):
                relevance += 0.2
            if re.search("delete|free|release|reset\\(\\)", content_lower):
                relevance += 0.1
            if re.search("size\\s*>\\s*|capacity|limit|max_", content_lower):
                relevance += 0.15
        if any(
            (term in desc_lower for term in ["null", "nullptr", "pointer", "invalid", "bad.*pointer", "uninitialized"])
        ):
            if re.search("nullptr|NULL|==\\s*null|!=\\s*null|!\\s*\\w+\\s*\\)", content_lower):
                relevance += 0.3
            if re.search("if\\s*\\(\\s*!\\s*\\w+", content_lower):
                relevance += 0.2
        if any((term in desc_lower for term in ["timeout", "timing", "delay", "latency", "deadline", "expired"])):
            if re.search("timeout|deadline|duration|sleep|wait|elapsed", content_lower):
                relevance += 0.25
            if re.search("chrono|time_point|milliseconds|seconds", content_lower):
                relevance += 0.15
        if any((term in desc_lower for term in ["hardware", "device", "driver", "communication", "board", "register"])):
            if re.search("hardware|device|driver|register|i/o|port", content_lower):
                relevance += 0.2
            if re.search("read|write|send|receive|transfer", content_lower):
                relevance += 0.1
        if any((term in desc_lower for term in ["fragment", "data.*flow", "generator", "data.*source", "buffer"])):
            if re.search("fragment|frag_ptr|FragmentPtr", content_lower):
                relevance += 0.25
            if re.search("generator|source|producer", content_lower):
                relevance += 0.15
        if any((term in desc_lower for term in ["exception", "error.*handling", "throw", "catch", "unhandled"])):
            if re.search("try\\s*\\{|catch\\s*\\(|throw\\s+", content_lower):
                relevance += 0.2
            if re.search("noexcept|nothrow", content_lower):
                relevance -= 0.1
        if relevance == 0.0:
            categories = ["hardware", "software", "configuration", "timing", "resource"]
            for cat in categories:
                if cat in desc_lower and cat in content_lower:
                    relevance = self.config.category_relevance_score
                    break
            if relevance == 0.0:
                significant_words = [
                    w
                    for w in desc_lower.split()
                    if len(w) > 4 and w not in ("error", "issue", "problem", "cause", "might", "could")
                ]
                if any((word in content_lower for word in significant_words[:5])):
                    relevance = self.config.weak_term_relevance_score
        return max(-1.0, min(1.0, relevance))

    def _should_stop(self, hypotheses: list[Hypothesis], iteration: int) -> bool:
        if iteration >= self.max_iterations - 1:
            return True
        if not hypotheses:
            return True
        min_iters = self.config.min_iterations_before_stop
        if iteration < min_iters:
            return False
        top = hypotheses[0]
        clear_winner_score = self.config.clear_winner_score
        clear_winner_margin = self.config.clear_winner_margin
        if top.score > clear_winner_score:
            second_score = hypotheses[1].score if len(hypotheses) > 1 else 0
            if len(hypotheses) < 2 or second_score < clear_winner_score - clear_winner_margin:
                logger.debug(f"Stopping: clear winner with score {top.score:.2f} vs second place {second_score:.2f}")
                return True
        code_hint_hypos = [h for h in hypotheses if h.source.startswith("code_hint:")]
        if code_hint_hypos:
            top_hint = max(code_hint_hypos, key=lambda h: h.score)
            early_stop_score = self.config.code_hint_early_stop_score
            early_stop_margin = self.config.code_hint_early_stop_margin
            if top_hint.score > early_stop_score:
                non_hint_hypos = [h for h in hypotheses if not h.source.startswith("code_hint:")]
                if non_hint_hypos:
                    top_non_hint = max(non_hint_hypos, key=lambda h: h.score)
                    if top_hint.score > top_non_hint.score + early_stop_margin:
                        logger.debug(
                            f"Stopping: code hint '{top_hint.description[:30]}...' has clear lead ({top_hint.score:.2f} vs {top_non_hint.score:.2f})"
                        )
                        return True
                else:
                    logger.debug(f"Stopping: only code hint hypotheses remain, top score {top_hint.score:.2f}")
                    return True
        return False

    def _strength_multiplier(self, strength: str) -> float:
        return {
            "STRONG": self.config.strength_strong,
            "MODERATE": self.config.strength_moderate,
            "WEAK": self.config.strength_weak,
        }.get(strength, self.config.strength_weak)

    def _merge_evidence(self, existing: Evidence, new: Evidence) -> Evidence:
        merged = Evidence(items=dict(existing.items))
        for item_id, item in new.items.items():
            merged.items[item_id] = item
        return merged

    def _format_hypotheses(self, hypotheses: list[Hypothesis]) -> str:
        lines = []
        for h in hypotheses[:5]:
            entry = f"- [{h.id}] {h.description} (prior: {h.prior:.1%}, score: {h.score:+.2f})"
            if getattr(h, "confirming_evidence_design", None):
                entry += f"\n  Confirming evidence: {h.confirming_evidence_design}"
            if getattr(h, "refuting_evidence_design", None):
                entry += f"\n  Refuting evidence: {h.refuting_evidence_design}"
            lines.append(entry)
        return "\n".join(lines) if lines else "No hypotheses"
