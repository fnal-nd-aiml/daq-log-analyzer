"""
File: archivist.py
Purpose: Archivist persona - Phase 0: Prior Knowledge Retrieval.
Category: Utility
Author: artdaq team
Depends: knowledge, doc_loader, models, logs, question, ...
Exports: PriorKnowledgeSummary, ArchivistPersona
Complexity: High | Lines: 652
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from .base import BasePersona, CollaborativePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_ARCHIVIST, Persona
if TYPE_CHECKING:
    from srcs.models.question import QuestionContext
from srcs.models.knowledge import ConfigParam, ConfigurationContext, DiagnosticHistory, PriorKnowledge, RecommendedHypothesis, ResolutionDigest, SimilarInvestigation
from srcs.models.logs import Log
logger = logging.getLogger(__name__)

class PriorKnowledgeSummary(BaseModel):
    relevance_assessment: dict[str, str] = Field(default_factory=dict, description='Relevance ratings for patterns, similar_cases, source_locations')
    key_insights: list[str] = Field(default_factory=list, description='Key insights from the prior knowledge')
    recommended_focus_areas: list[str] = Field(default_factory=list, description='Recommended focus areas for investigation')
    data_flow_summary: str = Field(default='', description='Summary of data flow around the error')
    overall_confidence: str = Field(default='low', description='Overall confidence in prior knowledge (high/medium/low)')
    confidence_reasoning: str = Field(default='', description='Explanation for the confidence level')

class ArchivistPersona(CollaborativePersona):

    def __init__(self) -> None:
        self._orchestrator: Any = None
        self._retrieved_prior: PriorKnowledge | None = None
        self._summary: PriorKnowledgeSummary | None = None

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_ARCHIVIST]

    @property
    def traits(self) -> list[str]:
        return ['methodical', 'thorough', 'historical', 'organized', 'pattern-seeking']

    @property
    def thinking_style(self) -> str:
        return 'Systematic retrieval - searches through historical records, identifies relevant patterns and precedents, connects current issues to past cases'

    async def prepare(self, context: InvestigationContext) -> None:
        from srcs.persona.orchestration import RetrievalOrchestrator
        source_roots: list[Path] = []
        if context.source_locator is not None:
            locator_roots = getattr(context.source_locator, '_source_roots', None)
            if locator_roots:
                source_roots = list(locator_roots)
        chroma_store = None
        if context.kb is not None:
            chroma_store = getattr(context.kb, '_chroma_store', None)
        binder_store = None
        if context.kb is not None:
            db_path = getattr(getattr(context.kb, 'config', None), 'sqlite_path', None)
            if db_path:
                from srcs.workbinder import BinderStore
                binder_store = BinderStore(db_path)
        self._orchestrator = RetrievalOrchestrator(kb=context.require_kb() if context.kb else self._create_null_kb(), source_roots=source_roots if source_roots else None, code_index=context.code_index, chroma_store=chroma_store, llm_provider=context.llm, binder_store=binder_store)

    def _create_null_kb(self) -> Any:
        from srcs.knowledge import KnowledgeBase

        class NullKB(KnowledgeBase):

            async def get_prior_knowledge(self, error: Any, context: Any) -> Any:
                from srcs.models import PriorKnowledge
                return PriorKnowledge(matched_patterns=[], similar_investigations=[], recommended_hypotheses=[], recommended_queries=[])
        return NullKB.__new__(NullKB)

    async def contribute(self, context: InvestigationContext) -> Contribution:
        prior = await self._retrieve_prior_knowledge(context)
        self._retrieved_prior = prior
        binder = context.require_binder()
        log_bundle = binder.get_log_bundle()
        if log_bundle is not None:
            logger.info('Using LOG_BUNDLE from Chronicler for guided retrieval')
            self._enrich_from_log_bundle(prior, log_bundle)
        br_id = binder.get_boardreader_identification()
        if br_id is not None:
            self._enrich_from_boardreader_id(prior, br_id)
        if log_bundle is not None:
            await self._enrich_similar_from_chronicler(context, prior, log_bundle, br_id)
        await self._load_documentation_context(context, prior, log_bundle)
        prior.resolution_digest = self._extract_resolutions(prior.similar_investigations)
        prior.configuration_context = self._analyze_configuration(context.error, context.context_logs, prior.similar_investigations)
        prior.diagnostic_history = self._get_diagnostic_history(context.error, prior.similar_investigations)
        await self._enrich_similar_with_synthesis(context, prior)
        context.prior_knowledge = prior
        content = self._build_content_dict(prior)
        if context.llm is not None and self._has_meaningful_findings(prior):
            try:
                summary = await self._summarize_with_llm(context, prior)
                self._summary = summary
                content['llm_summary'] = {'relevance_assessment': summary.relevance_assessment, 'key_insights': summary.key_insights, 'recommended_focus_areas': summary.recommended_focus_areas, 'data_flow_summary': summary.data_flow_summary, 'overall_confidence': summary.overall_confidence, 'confidence_reasoning': summary.confidence_reasoning}
            except Exception as e:
                logger.warning(f'LLM summarization failed: {e}')
                self._summary = None
        confidence = self._calculate_confidence(prior)
        return Contribution(persona_id='archivist', phase=PHASE_ARCHIVIST, content=content, confidence=confidence, reasoning=self._build_reasoning(prior))

    async def _retrieve_prior_knowledge(self, context: InvestigationContext) -> PriorKnowledge:
        if context.prior_knowledge is not None:
            return context.prior_knowledge
        if self._orchestrator is None:
            await self.prepare(context)
        binder = context.binder
        try:
            prior: PriorKnowledge = await self._orchestrator.retrieve(context.error, context.context_logs, binder=binder)
            return prior
        except Exception as e:
            logger.warning(f'Prior knowledge retrieval failed: {e}')
            return PriorKnowledge(matched_patterns=[], similar_investigations=[], recommended_hypotheses=[], recommended_queries=[])

    def _has_meaningful_findings(self, prior: PriorKnowledge) -> bool:
        return bool(prior.matched_patterns or prior.similar_investigations or prior.source_locations)

    def _enrich_from_log_bundle(self, prior: PriorKnowledge, log_bundle: Any) -> None:
        for clue in log_bundle.clues:
            if clue.clue_type == 'error_pattern':
                prior.recommended_hypotheses.append(RecommendedHypothesis(description=clue.description, source='chronicler', prior=0.6, is_authoritative=False))
            if clue.suggested_search:
                from srcs.models.knowledge import EvidenceQueryTemplate
                prior.recommended_queries.append(EvidenceQueryTemplate(query_type='code_search', query_template=clue.suggested_search))
        if log_bundle.primary_error is not None:
            primary_msg = log_bundle.primary_error.message
            primary_file = log_bundle.primary_error.filename
            prior.recommended_hypotheses.insert(0, RecommendedHypothesis(description=f'Primary error from {primary_file}: {primary_msg} (identified by Chronicler from multi-file analysis)', source='chronicler', prior=0.7, is_authoritative=True))
        for board in getattr(log_bundle, 'affected_boards', []):
            if board.role == 'primary_failure':
                continue
            if board.failure_mode:
                prior.recommended_hypotheses.append(RecommendedHypothesis(description=f'Board {board.board_name} ({board.role}): {board.failure_mode}', source='chronicler', prior=0.4 if board.role == 'secondary_cascade' else 0.2, is_authoritative=False))
            if board.source_location:
                from srcs.models.knowledge import EvidenceQueryTemplate
                prior.recommended_queries.append(EvidenceQueryTemplate(query_type='code_search', query_template=board.source_location))
        for link in getattr(log_bundle, 'cascade_chain', []):
            if link.mechanism:
                prior.recommended_hypotheses.append(RecommendedHypothesis(description=f'Cascade: {link.from_board} -> {link.to_board} via {link.mechanism}', source='chronicler', prior=0.5, is_authoritative=False))
        logger.info(f'Enriched prior knowledge with {len(log_bundle.clues)} clues from LOG_BUNDLE')

    def _enrich_from_boardreader_id(self, prior: PriorKnowledge, br_id: Any) -> None:
        from srcs.models.knowledge import EvidenceQueryTemplate
        added = 0
        existing_templates = {q.query_template for q in prior.recommended_queries}
        for br_type in br_id.boardreader_types:
            if br_type not in existing_templates:
                prior.recommended_queries.append(EvidenceQueryTemplate(query_type='code_search', query_template=br_type))
                added += 1
        for component in br_id.components:
            if component not in existing_templates:
                prior.recommended_queries.append(EvidenceQueryTemplate(query_type='code_search', query_template=component))
                added += 1
        if added:
            logger.info('Enriched retrieval with %d queries from BOARDREADER_IDENTIFICATION', added)

    async def _enrich_similar_from_chronicler(self, context: InvestigationContext, prior: PriorKnowledge, log_bundle: Any, br_id: Any | None) -> None:
        if context.kb is None:
            return
        chroma = getattr(context.kb, '_chroma_store', None)
        if chroma is None:
            return
        desc_parts = []
        primary = getattr(log_bundle, 'primary_error', None)
        if primary is not None:
            desc_parts.append(f'Error: {primary.message}')
            if primary.filename:
                desc_parts.append(f'File: {primary.filename}')
        boards = getattr(log_bundle, 'affected_boards', [])
        if boards:
            board_names = [b.board_name for b in boards]
            desc_parts.append(f"Boards: {', '.join(board_names)}")
        cascade_chain = getattr(log_bundle, 'cascade_chain', [])
        if cascade_chain:
            first_link = cascade_chain[0]
            mechanism = getattr(first_link, 'mechanism', '')
            desc_parts.append(f'Cascade: {first_link.from_board} -> {first_link.to_board}' + (f' via {mechanism}' if mechanism else ''))
        if br_id is not None and br_id.boardreader_types:
            desc_parts.append(f"Components: {', '.join(br_id.boardreader_types)}")
        if not desc_parts:
            return
        enriched_desc = ' | '.join(desc_parts)
        if primary is None or primary.message == context.error.message:
            if len(desc_parts) <= 1:
                return
        try:
            enriched_results = await chroma.find_similar_investigations(enriched_desc, n=5)
        except Exception as e:
            logger.debug('Enriched similarity search failed: %s', e)
            return
        if not enriched_results:
            return
        existing_ids = {s.investigation_id for s in prior.similar_investigations}
        added = 0
        for result in enriched_results:
            if result.investigation_id not in existing_ids:
                prior.similar_investigations.append(result)
                existing_ids.add(result.investigation_id)
                added += 1
            else:
                for existing in prior.similar_investigations:
                    if existing.investigation_id == result.investigation_id and result.similarity_score > existing.similarity_score:
                        existing.similarity_score = result.similarity_score
                        break
        if added:
            logger.info('Enriched similarity search found %d additional similar investigations (query: %s)', added, enriched_desc[:100])

    async def _load_documentation_context(self, context: InvestigationContext, prior: PriorKnowledge, log_bundle: Any) -> None:
        if log_bundle is not None:
            doc_ref = getattr(log_bundle, 'documentation_reference', '')
            if doc_ref:
                prior.documentation_context = doc_ref
                logger.info('Reused documentation_reference from LOG_BUNDLE (%d chars)', len(doc_ref))
                return
        from srcs.knowledge.doc_loader import DocStore, LLMDocExtractor, extract_names_from_message
        components: set[str] = set()
        error_messages: list[str] = []
        if context.error:
            if context.error.component and context.error.component != 'Unknown':
                components.add(context.error.component)
            if context.error.function:
                components.add(context.error.function)
            error_messages.append(context.error.message)
        for log_entry in context.context_logs:
            if log_entry.component:
                components.add(log_entry.component)
            if log_entry.message:
                error_messages.append(log_entry.message)
        import re
        for loc in prior.source_locations:
            if loc.file_path:
                basename = loc.file_path.rsplit('/', 1)[-1]
                stem = re.sub('\\.(cc|cpp|h|hh|cxx)$', '', basename)
                stem = re.sub('_(generator|source|module|readout|boardreader|dispatcher|algo|writer|reader)$', '', stem)
                if stem:
                    components.add(stem)
        map_path = None
        docs_max = 12000
        if context.config is not None:
            map_path = context.config.subcomponent_map_path
            docs_max = context.config.docs_max_chars
        doc_store = DocStore(subcomponent_map_path=map_path)
        doc_store.load_all()
        if not components and (not error_messages):
            return
        if error_messages:
            heuristic_names: set[str] = set()
            for msg in error_messages:
                heuristic_names.update(extract_names_from_message(msg, subcomponent_map=doc_store.subcomponent_map))
            if heuristic_names:
                components.update(heuristic_names)
        doc_context = ''
        if context.llm is not None:
            try:
                extractor = LLMDocExtractor(doc_store, context.llm)
                doc_context = await extractor.extract_for_investigation(components, error_messages, max_chars=docs_max)
            except Exception as e:
                logger.warning('LLM doc extraction failed: %s', e)
        else:
            matched = doc_store.match_components(components)
            if matched:
                unique_docs = list(dict.fromkeys(matched.values()))
                parts: list[str] = []
                for doc_name in unique_docs[:3]:
                    text = doc_store.get_full_text(doc_name)
                    if text:
                        parts.append(f'## {doc_name}\n{text}')
                doc_context = '\n\n'.join(parts)
        if doc_context:
            prior.documentation_context = doc_context
            logger.info('Loaded documentation context (%d chars, components=%s)', len(doc_context), components)
        else:
            logger.debug('No documentation matched (components=%s)', components)

    async def _enrich_similar_with_synthesis(self, context: InvestigationContext, prior: PriorKnowledge) -> None:
        if not prior.similar_investigations or context.kb is None:
            return
        for sim in prior.similar_investigations[:5]:
            try:
                investigation = await context.kb.get_investigation(sim.investigation_id)
                if investigation is None:
                    continue
                parts: list[str] = []
                parts.append(f'Case {sim.investigation_id[:8]} (similarity: {sim.similarity_score:.0%})')
                if investigation.outcome is not None:
                    parts.append(f'  Outcome: {investigation.outcome.value}')
                if investigation.hypotheses:
                    sorted_hyps = sorted(investigation.hypotheses, key=lambda h: h.score, reverse=True)
                    hyp_lines = []
                    for h in sorted_hyps[:3]:
                        hyp_lines.append(f'    - [{h.score:.0%}] {h.description[:120]}')
                    parts.append('  Top hypotheses:\n' + '\n'.join(hyp_lines))
                if investigation.causal_chains:
                    chain = investigation.causal_chains[0]
                    step_lines = []
                    for step in chain.steps[:4]:
                        step_lines.append(f'    {step.step_order}. {step.claim[:100]}')
                    parts.append('  Causal chain:\n' + '\n'.join(step_lines))
                if sim.root_cause:
                    parts.append(f'  Root cause: {sim.root_cause}')
                prior.enriched_case_summaries.append('\n'.join(parts))
            except Exception as e:
                logger.debug(f'Failed to enrich similar investigation {sim.investigation_id}: {e}')

    async def _summarize_with_llm(self, context: InvestigationContext, prior: PriorKnowledge) -> PriorKnowledgeSummary:
        prompt = self._format_summary_prompt(context, prior, binder=context.binder)
        system_prompt = get_system_prompt(SystemPromptType.ARCHIVIST)
        summary = await self._call_llm_structured(context=context, prompt=prompt, response_model=PriorKnowledgeSummary, system_prompt=system_prompt, prompt_key='prior_knowledge_summary')
        return summary

    def _format_summary_prompt(self, context: InvestigationContext, prior: PriorKnowledge, binder: Any=None) -> str:
        template = get_user_prompt(UserPromptType.PRIOR_KNOWLEDGE_SUMMARY)
        patterns_text = 'None found'
        if prior.matched_patterns:
            patterns_lines = []
            for match in prior.matched_patterns[:5]:
                pattern = match.pattern
                accuracy = pattern.times_correct / pattern.times_seen if pattern.times_seen > 0 else 0.0
                signature = pattern.signature_message_pattern or pattern.name
                patterns_lines.append(f"- Pattern: {signature}\n  Confidence: {match.confidence:.0%}\n  Description: {pattern.description or 'No description'}\n  Accuracy: {accuracy:.0%} (seen {pattern.times_seen} times)")
            patterns_text = '\n'.join(patterns_lines)
        similar_text = 'None found'
        if prior.similar_investigations:
            similar_lines = []
            for sim in prior.similar_investigations[:5]:
                similar_lines.append(f"- Investigation {sim.investigation_id}\n  Similarity: {sim.similarity_score:.0%}\n  Root Cause: {sim.root_cause or 'Unknown'}")
            similar_text = '\n'.join(similar_lines)
        locations_text = 'None found'
        if prior.source_locations:
            locations_lines = []
            for loc in prior.source_locations[:5]:
                loc_info = f'- {loc.file_path}:{loc.line_number}'
                if loc.function_name:
                    loc_info += f' ({loc.function_name})'
                if loc.match_score:
                    loc_info += f' [score: {loc.match_score:.0%}]'
                locations_lines.append(loc_info)
            locations_text = '\n'.join(locations_lines)
        call_graph_text = 'No call graph information available'
        if prior.source_locations:
            graph_lines = []
            for loc in prior.source_locations[:3]:
                if loc.callers or loc.callees:
                    graph_lines.append(f'Function: {loc.function_name}')
                    if loc.callers:
                        caller_names = [c.get('caller_name', c.get('name', '?')) for c in loc.callers[:3]]
                        graph_lines.append(f"  Called by: {', '.join(caller_names)}")
                    if loc.callees:
                        callee_names = [c.get('callee_name', c.get('name', '?')) for c in loc.callees[:3]]
                        graph_lines.append(f"  Calls: {', '.join(callee_names)}")
                if loc.call_graph_diagram:
                    graph_lines.append(f'\n{loc.call_graph_diagram}')
            if graph_lines:
                call_graph_text = '\n'.join(graph_lines)
        chronicler_analysis = 'Not available (single-file investigation)'
        if binder is not None:
            log_bundle = binder.get_log_bundle()
            if log_bundle is not None:
                parts = []
                narrative = getattr(log_bundle, 'annotated_narrative', '')
                if narrative:
                    parts.append(f'### Narrative\n{narrative}')
                primary = getattr(log_bundle, 'primary_error', None)
                if primary is not None:
                    parts.append(f'### Primary Error\n- Message: {primary.message}\n- File: {primary.filename}')
                cascade_desc = getattr(log_bundle, 'cascade_description', '')
                if cascade_desc:
                    parts.append(f'### Cascade Description\n{cascade_desc}')
                cascade_chain = getattr(log_bundle, 'cascade_chain', [])
                if cascade_chain:
                    chain_lines = []
                    for link in cascade_chain:
                        mechanism = getattr(link, 'mechanism', '')
                        chain_lines.append(f'- {link.from_board} -> {link.to_board}' + (f' via {mechanism}' if mechanism else ''))
                    parts.append('### Cascade Chain\n' + '\n'.join(chain_lines))
                boards = getattr(log_bundle, 'affected_boards', [])
                if boards:
                    board_lines = []
                    for b in boards:
                        board_lines.append(f"- {b.board_name} ({b.role}): {b.failure_mode or 'unknown'}")
                    parts.append('### Affected Boards\n' + '\n'.join(board_lines))
                clues = getattr(log_bundle, 'clues', [])
                if clues:
                    clue_lines = []
                    for c in clues:
                        clue_lines.append(f'- [{c.clue_type}] {c.description}')
                    parts.append('### Investigation Clues\n' + '\n'.join(clue_lines))
                if parts:
                    chronicler_analysis = '\n\n'.join(parts)
            br_id = binder.get_boardreader_identification()
            if br_id is not None:
                br_parts = []
                if br_id.boardreader_types:
                    br_parts.append('Types: ' + ', '.join(br_id.boardreader_types))
                if br_id.components:
                    br_parts.append('Components: ' + ', '.join(br_id.components))
                if br_parts:
                    section = '### Identified Components\n' + '\n'.join(br_parts)
                    if chronicler_analysis.startswith('Not available'):
                        chronicler_analysis = section
                    else:
                        chronicler_analysis += '\n\n' + section
            timeline = binder.get_merged_timeline()
            if timeline is not None:
                stats_parts = []
                if timeline.total_entries:
                    stats_parts.append(f'{timeline.total_entries} entries')
                if timeline.total_errors:
                    stats_parts.append(f'{timeline.total_errors} errors')
                if timeline.total_warnings:
                    stats_parts.append(f'{timeline.total_warnings} warnings')
                if timeline.file_count:
                    stats_parts.append(f'{timeline.file_count} files')
                if timeline.earliest_timestamp and timeline.latest_timestamp:
                    stats_parts.append(f'span: {timeline.earliest_timestamp} to {timeline.latest_timestamp}')
                if stats_parts:
                    section = '### Timeline Statistics\n' + ', '.join(stats_parts)
                    if chronicler_analysis.startswith('Not available'):
                        chronicler_analysis = section
                    else:
                        chronicler_analysis += '\n\n' + section
        return template.format(error_message=context.error.message, error_component=context.error.component or 'Unknown', error_function=self._get_error_function(prior), error_timestamp=str(context.error.timestamp), matched_patterns=patterns_text, similar_investigations=similar_text, source_locations=locations_text, call_graph_context=call_graph_text, chronicler_analysis=chronicler_analysis)

    def _get_error_function(self, prior: PriorKnowledge) -> str:
        if prior.source_locations:
            for loc in prior.source_locations:
                if loc.function_name:
                    return loc.function_name
        return 'Unknown'

    def _extract_resolutions(self, similar_investigations: list[SimilarInvestigation]) -> list[ResolutionDigest]:
        resolutions = []
        for sim in similar_investigations:
            if sim.root_cause and sim.root_cause.lower() != 'unknown':
                category = self._infer_resolution_category(sim.root_cause)
                resolutions.append(ResolutionDigest(investigation_id=sim.investigation_id, root_cause=sim.root_cause, resolution_action=self._infer_resolution_action(sim.root_cause), resolution_category=category, resolution_success=sim.was_correct, confidence=sim.similarity_score, applicability_notes=self._generate_applicability_note(sim)))
        return resolutions

    def _infer_resolution_category(self, root_cause: str) -> str:
        root_cause_lower = root_cause.lower()
        if any((term in root_cause_lower for term in ['config', 'parameter', 'setting', 'fcl'])):
            return 'config_change'
        if any((term in root_cause_lower for term in ['bug', 'fix', 'code', 'logic'])):
            return 'code_fix'
        if any((term in root_cause_lower for term in ['hardware', 'device', 'cable', 'power'])):
            return 'hardware'
        if any((term in root_cause_lower for term in ['workaround', 'restart', 'retry'])):
            return 'workaround'
        return 'unknown'

    def _infer_resolution_action(self, root_cause: str) -> str | None:
        root_cause_lower = root_cause.lower()
        if 'timeout' in root_cause_lower:
            return 'Adjust timeout configuration'
        if 'buffer' in root_cause_lower:
            return 'Adjust buffer size or allocation'
        if 'missing' in root_cause_lower:
            return 'Check for missing data or configuration'
        if 'synchronization' in root_cause_lower or 'sync' in root_cause_lower:
            return 'Check timing and synchronization settings'
        return None

    def _generate_applicability_note(self, sim: SimilarInvestigation) -> str:
        notes = []
        if sim.similarity_score >= 0.9:
            notes.append('Very high similarity - likely applicable')
        elif sim.similarity_score >= 0.7:
            notes.append('High similarity - consider applicability')
        else:
            notes.append('Moderate similarity - verify relevance')
        if sim.was_correct is True:
            notes.append('Previous diagnosis confirmed correct')
        elif sim.was_correct is False:
            notes.append('Previous diagnosis was incorrect')
        return '; '.join(notes)

    def _analyze_configuration(self, error: Log, context_logs: list[Log], similar_investigations: list[SimilarInvestigation]) -> ConfigurationContext | None:
        import re
        relevant_params: list[ConfigParam] = []
        deviation_flags: list[str] = []
        config_patterns = [('timeout[_=:]?\\s*(\\d+)', 'timeout'), ('buffer[_\\s]?size[_=:]?\\s*(\\d+)', 'buffer_size'), ('max[_\\s]?(?:events?|fragments?)[_=:]?\\s*(\\d+)', 'max_events'), ('port[_=:]?\\s*(\\d+)', 'port'), ('(?:data[_\\s]?)?rate[_=:]?\\s*(\\d+)', 'data_rate')]
        all_text = error.message + ' ' + ' '.join((log.message for log in context_logs))
        for pattern, param_name in config_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                current_value = matches[-1]
                relevant_params.append(ConfigParam(name=param_name, current_value=current_value, source='log'))
        if not relevant_params:
            return None
        component = error.component or 'unknown'
        return ConfigurationContext(component=component, relevant_params=relevant_params, config_from_similar_successes={}, deviation_flags=deviation_flags)

    def _get_diagnostic_history(self, error: Log, similar_investigations: list[SimilarInvestigation]) -> DiagnosticHistory | None:
        if not similar_investigations:
            return None
        total = len(similar_investigations)
        resolved = sum((1 for sim in similar_investigations if sim.root_cause and sim.root_cause.lower() != 'unknown'))
        resolution_rate = resolved / total if total > 0 else 0.0
        avg_confidence = sum((sim.similarity_score for sim in similar_investigations)) / total if total > 0 else 0.0
        root_cause_counts: dict[str, int] = {}
        for sim in similar_investigations:
            if sim.root_cause and sim.root_cause.lower() != 'unknown':
                cause = sim.root_cause[:100]
                root_cause_counts[cause] = root_cause_counts.get(cause, 0) + 1
        common_root_causes = [(cause, count / total) for cause, count in sorted(root_cause_counts.items(), key=lambda x: x[1], reverse=True)[:5]]
        error_signature = self._generate_error_signature(error.message)
        return DiagnosticHistory(error_signature=error_signature, total_occurrences=total, resolved_count=resolved, resolution_rate=resolution_rate, avg_confidence=avg_confidence, common_root_causes=common_root_causes)

    def _generate_error_signature(self, error_message: str) -> str:
        import re
        signature = error_message
        signature = re.sub('\\d+', '{N}', signature)
        signature = re.sub('0x[0-9a-fA-F]+', '{HEX}', signature)
        return signature[:200]

    def _build_content_dict(self, prior: PriorKnowledge) -> dict[str, Any]:
        content: dict[str, Any] = {'matched_patterns': [{'pattern_id': p.pattern.id, 'confidence': p.confidence} for p in prior.matched_patterns], 'similar_investigations': [{'investigation_id': s.investigation_id, 'score': s.similarity_score} for s in prior.similar_investigations], 'source_locations': [{'file_path': loc.file_path, 'line_number': loc.line_number, 'function_name': loc.function_name, 'match_score': loc.match_score} for loc in prior.source_locations], 'recommended_hypotheses': [{'description': h.description, 'source': h.source, 'prior': h.prior, 'is_authoritative': getattr(h, 'is_authoritative', False)} for h in prior.recommended_hypotheses], 'recommended_queries': [{'query_type': q.query_type, 'query_template': q.query_template} for q in prior.recommended_queries]}
        if prior.resolution_digest:
            content['resolution_digest'] = [{'investigation_id': r.investigation_id, 'root_cause': r.root_cause, 'resolution_action': r.resolution_action, 'resolution_category': r.resolution_category, 'resolution_success': r.resolution_success, 'confidence': r.confidence, 'applicability_notes': r.applicability_notes} for r in prior.resolution_digest]
        if prior.configuration_context:
            content['configuration_context'] = {'component': prior.configuration_context.component, 'relevant_params': [{'name': p.name, 'current_value': p.current_value, 'source': p.source, 'note': p.note} for p in prior.configuration_context.relevant_params], 'config_from_similar_successes': prior.configuration_context.config_from_similar_successes, 'deviation_flags': prior.configuration_context.deviation_flags}
        if prior.diagnostic_history:
            content['diagnostic_history'] = {'error_signature': prior.diagnostic_history.error_signature, 'total_occurrences': prior.diagnostic_history.total_occurrences, 'resolved_count': prior.diagnostic_history.resolved_count, 'resolution_rate': prior.diagnostic_history.resolution_rate, 'avg_confidence': prior.diagnostic_history.avg_confidence, 'common_root_causes': [{'cause': cause, 'frequency': freq} for cause, freq in prior.diagnostic_history.common_root_causes]}
        return content

    def _calculate_confidence(self, prior: PriorKnowledge) -> float:
        confidence = 0.3
        if prior.matched_patterns:
            best_match = max((p.confidence for p in prior.matched_patterns))
            confidence = max(confidence, best_match * 0.9)
        if prior.source_locations:
            confidence = max(confidence, 0.5)
            best_score = max((loc.match_score or 0.0 for loc in prior.source_locations))
            if best_score > 0.7:
                confidence = max(confidence, 0.7)
        if prior.similar_investigations:
            confidence = max(confidence, 0.4)
        if prior.recommended_hypotheses:
            auth_hints = [h for h in prior.recommended_hypotheses if getattr(h, 'is_authoritative', False)]
            if auth_hints:
                confidence = max(confidence, 0.85)
        return min(confidence, 0.95)

    def _build_reasoning(self, prior: PriorKnowledge) -> str:
        parts = []
        if prior.matched_patterns:
            best_pattern = max(prior.matched_patterns, key=lambda p: p.confidence)
            parts.append(f'Found {len(prior.matched_patterns)} matching patterns (best: {best_pattern.confidence:.0%} confidence)')
        if prior.similar_investigations:
            best_similar = max(prior.similar_investigations, key=lambda s: s.similarity_score)
            parts.append(f'Found {len(prior.similar_investigations)} similar investigations (best: {best_similar.similarity_score:.0%} similar)')
        if prior.source_locations:
            parts.append(f'Located {len(prior.source_locations)} source code locations')
        if prior.recommended_hypotheses:
            auth_count = sum((1 for h in prior.recommended_hypotheses if getattr(h, 'is_authoritative', False)))
            if auth_count:
                parts.append(f'Found {auth_count} authoritative code hints')
            else:
                parts.append(f'Generated {len(prior.recommended_hypotheses)} hypothesis recommendations')
        if prior.resolution_digest:
            resolved_count = sum((1 for r in prior.resolution_digest if r.resolution_success is True))
            parts.append(f'Extracted {len(prior.resolution_digest)} resolutions ({resolved_count} confirmed successful)')
        if prior.diagnostic_history:
            parts.append(f'Diagnostic history: {prior.diagnostic_history.resolution_rate:.0%} resolution rate ({prior.diagnostic_history.total_occurrences} occurrences)')
        if prior.configuration_context:
            parts.append(f'Configuration context: {len(prior.configuration_context.relevant_params)} relevant params for {prior.configuration_context.component}')
        if self._summary:
            parts.append(f'LLM analysis: {self._summary.overall_confidence} confidence')
        if not parts:
            return 'No relevant prior knowledge found - investigation will proceed without historical context'
        return '; '.join(parts)

    async def reflect(self, context: InvestigationContext) -> Reflection:
        insights = []
        uncertainties = []
        suggestions = []
        prior = self._retrieved_prior or context.prior_knowledge
        if prior:
            if prior.matched_patterns:
                best_match = max(prior.matched_patterns, key=lambda p: p.confidence)
                pattern = best_match.pattern
                accuracy = pattern.times_correct / pattern.times_seen if pattern.times_seen > 0 else 0.0
                insights.append(f'Best pattern match has {best_match.confidence:.0%} confidence - historical accuracy: {accuracy:.0%}')
            if prior.source_locations:
                insights.append(f'Error traced to {len(prior.source_locations)} source locations')
            else:
                uncertainties.append('Could not locate source code for this error message')
                suggestions.append('Manual source code search may be needed')
            if not prior.similar_investigations:
                uncertainties.append('No similar past investigations found')
            if self._summary:
                insights.extend(self._summary.key_insights[:2])
                suggestions.extend(self._summary.recommended_focus_areas[:2])
        else:
            uncertainties.append('No prior knowledge available for this error')
            suggestions.append('This appears to be a novel error pattern')
        return Reflection(insights=insights, uncertainties=uncertainties, suggestions=suggestions)

    async def respond_to(self, other: BasePersona, message: str) -> str:
        return f'Let me check the archives for information related to your question, {other.metadata.name}. Historical records may shed light on this.'

    async def critique(self, contribution: Contribution) -> Critique:
        issues = []
        strengths = []
        recommendations = []
        content_str = str(contribution.content).lower()
        reasoning_str = str(contribution.reasoning).lower()
        if 'unprecedented' in content_str:
            issues.append('Claim of unprecedented nature should be verified against archives')
            recommendations.append('Cross-reference with similar error patterns before concluding uniqueness')
        if 'historical' in reasoning_str or 'pattern' in reasoning_str:
            strengths.append('Good use of historical context')
        if contribution.confidence > 0.8 and (not any((term in reasoning_str for term in ['pattern', 'historical', 'similar']))):
            issues.append('High confidence without historical validation')
            recommendations.append('Consider historical pattern accuracy before high-confidence claims')
        return Critique(target_contribution=contribution, issues=issues, strengths=strengths, severity='LOW' if not issues else 'MEDIUM', recommendations=recommendations)

    async def endorse(self, contribution: Contribution) -> bool:
        content_str = str(contribution.content).lower()
        reasoning_str = str(contribution.reasoning).lower()
        considers_history = any((term in content_str or term in reasoning_str for term in ['pattern', 'historical', 'previous', 'similar', 'precedent']))
        return considers_history or contribution.confidence > 0.6

    async def answer_question(self, context: 'QuestionContext') -> Contribution:
        question = context.question
        content: dict[str, Any] = {'similar_questions': [], 'relevant_patterns': [], 'documented_solutions': [], 'historical_context': '', 'sources': []}
        if 'boardreader' in question.lower():
            content['historical_context'] = 'BoardReader is a common source of timeout and data acquisition issues. Historical patterns show that buffer sizes, timing parameters, and hardware communication settings are frequent root causes.'
            content['relevant_patterns'].append('BoardReader timeout patterns')
            content['sources'].append('artdaq/Plugins/BoardReader*.cc')
        if 'eventbuilder' in question.lower():
            content['historical_context'] = 'EventBuilder issues often relate to fragment synchronization, window management, and memory allocation. Historical records show correlation with data rates and fragment counts.'
            content['relevant_patterns'].append('EventBuilder synchronization patterns')
            content['sources'].append('artdaq/DAQrate/EventBuilder*.cc')
        if 'timeout' in question.lower():
            content['documented_solutions'].extend(['Increase timeout values in FCL configuration', 'Check network connectivity and latency', 'Verify hardware is responding within expected time'])
        if 'config' in question.lower() or 'fcl' in question.lower():
            content['historical_context'] = 'FCL configuration issues are well-documented. Common areas include parameter naming, path resolution, and compatibility between versions.'
            content['sources'].append('artdaq documentation')
        reasoning_parts = []
        if content['relevant_patterns']:
            reasoning_parts.append(f"Found {len(content['relevant_patterns'])} relevant historical patterns")
        if content['documented_solutions']:
            reasoning_parts.append(f"Retrieved {len(content['documented_solutions'])} documented solutions")
        if content['historical_context']:
            reasoning_parts.append('Historical context available')
        reasoning = '; '.join(reasoning_parts) if reasoning_parts else 'Limited historical records for this topic'
        confidence = 0.7 if content['relevant_patterns'] else 0.5
        return Contribution(persona_id='archivist', phase=PHASE_ARCHIVIST, content=content, confidence=confidence, reasoning=reasoning)

    def _extract_keywords(self, question: str) -> list[str]:
        artdaq_terms = ['boardreader', 'eventbuilder', 'datalogger', 'dispatcher', 'fragment', 'event', 'trigger', 'timing', 'sync', 'buffer', 'timeout', 'config', 'fcl', 'fhicl']
        words = question.lower().split()
        return [w for w in words if w in artdaq_terms]