"""
File: chronicler.py
Purpose: Chronicler persona - Phase -1: Multi-File Log Triage.
Category: Utility
Author: artdaq team
Depends: doc_loader, token_utils, log_parser, question, prompts, ...
Exports: BoardReaderIdentification, PrimaryErrorSelection, ChroniclerNarrativeResponse, ChroniclerPersona
Complexity: High | Lines: 767
"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from srcs.prompts import SystemPromptType, UserPromptType, get_system_prompt, get_user_prompt
from srcs.workbinder.artifacts.parsers import LogBundleParser, MergedTimelineParser
from srcs.workbinder.artifacts.parsers.merged_timeline import TimelineResponse
from srcs.workbinder.artifacts_types import LogBundleErrorEntry
from .base import BasePersona, Contribution, Critique, InvestigationContext, Reflection
from .personas import PERSONAS, PHASE_CHRONICLER, Persona

if TYPE_CHECKING:
    from srcs.models.question import QuestionContext
logger = logging.getLogger(__name__)


class BoardReaderIdentification(BaseModel):
    boardreader_types: list[str] = Field(
        default_factory=list,
        description="List of boardreader/component types identified (e.g., 'CAENV1730Readout', 'BernCRTData', 'ICARUSTriggerV3')",
    )
    components: list[str] = Field(
        default_factory=list,
        description="Additional component names found in logs (e.g., 'FragmentBuffer', 'WorkerThread', 'PoolBuffer')",
    )
    error_messages: list[str] = Field(
        default_factory=list, description="Key error messages to match against documentation"
    )


class PrimaryErrorSelection(BaseModel):
    primary_error_filename: str = Field(
        default="", description="Filename or board name of the primary root-cause error"
    )
    primary_error_message: str = Field(
        default="", description="Exact or partial error message that triggered the cascade"
    )
    reasoning: str = Field(default="", description="One sentence explaining why this is the root cause")


class ChroniclerNarrativeResponse(BaseModel):
    annotated_narrative: str = Field(default="", description="2-4 paragraph narrative of the merged timeline")
    primary_error_file: str = Field(default="", description="Filename containing the primary/root error")
    primary_error_message: str = Field(default="", description="The exact error message that triggered the cascade")
    primary_error_line: int | None = Field(default=None, description="Line number of the primary error if known")
    cascade_description: str = Field(default="", description="How the primary error cascaded to other boards")
    clues: list[dict[str, Any]] = Field(default_factory=list, description="Clues for the Archivist to investigate")
    affected_boards: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-board analysis (BoardAnalysis schema)"
    )
    cascade_chain: list[dict[str, Any]] = Field(default_factory=list, description="Causal links (CascadeLink schema)")


class ChroniclerPersona(BasePersona):

    @property
    def metadata(self) -> Persona:
        return PERSONAS[PHASE_CHRONICLER]

    @property
    def traits(self) -> list[str]:
        return ["chronological", "causal", "systematic", "concise"]

    @property
    def thinking_style(self) -> str:
        return "Read events in time order across all sources, identify which error came first and caused others"

    async def prepare(self, context: InvestigationContext) -> None:
        pass

    async def contribute(self, context: InvestigationContext) -> Contribution:
        source_files = getattr(context, "source_files", None)
        if not source_files:
            return Contribution(
                persona_id="chronicler",
                phase=PHASE_CHRONICLER,
                content={"skipped": True},
                confidence=1.0,
                reasoning="No source files - Chronicler not needed",
            )
        logger.info(f"Chronicler analyzing {len(source_files)} files")
        from srcs.models.log_parser import parse_log_content

        file_error_counts: dict[str, int] = {}
        all_errors: list[LogBundleErrorEntry] = []
        skipped_files: list[str] = []
        valid_files: list[Any] = []
        for sf in source_files:
            logs = parse_log_content(sf.content)
            if not self._validate_file_content_quality(logs, sf.filename):
                skipped_files.append(sf.filename)
                continue
            valid_files.append(sf)
            error_count = 0
            for log_entry in logs:
                if log_entry.level in ("ERROR", "FATAL"):
                    error_count += 1
                    all_errors.append(
                        LogBundleErrorEntry(
                            filename=sf.filename,
                            timestamp=log_entry.timestamp,
                            level=log_entry.level,
                            component=log_entry.component,
                            message=log_entry.message,
                        )
                    )
            file_error_counts[sf.filename] = error_count
        if not valid_files:
            if skipped_files:
                reason = "All files failed content quality validation"
                detail = "HTML/non-log content instead of DAQ log data"
            else:
                reason = "No parseable log entries found in any file"
                detail = "unrecognized log format"
            logger.warning(f"No entries from {len(source_files)} files (skipped: {skipped_files})")
            return Contribution(
                persona_id="chronicler",
                phase=PHASE_CHRONICLER,
                content={"skipped": True, "skipped_files": skipped_files, "reason": reason},
                confidence=0.1,
                reasoning=f"All {len(source_files)} files appear to contain {detail}",
            )
        raw_sections = _build_raw_file_sections(valid_files, file_error_counts)
        file_list_lines = []
        for sf in source_files:
            ec = file_error_counts.get(sf.filename, 0)
            file_list_lines.append(f"- {sf.filename}: {ec} errors")
        file_list = "\n".join(file_list_lines)
        from srcs.llm.token_utils import CHARS_PER_TOKEN

        llm_max_tokens = 50000
        if context.llm is not None and hasattr(context.llm, "config"):
            configured = context.llm.config.max_tokens or 50000
            llm_max_tokens = max(configured, 50000)
        max_content_chars = int(llm_max_tokens * CHARS_PER_TOKEN * 0.4)
        if len(raw_sections) > max_content_chars:
            logger.warning(
                "Raw content (%d chars) exceeds budget (%d chars), truncating", len(raw_sections), max_content_chars
            )
            raw_sections = _truncate_raw_sections(valid_files, file_error_counts, max_content_chars)
        system_prompt = get_system_prompt(SystemPromptType.CHRONICLER)
        formatted_timeline: str | None = None
        timeline_response: TimelineResponse | None = None
        parser = MergedTimelineParser()
        try:
            step1_template = get_user_prompt(UserPromptType.LOG_TIMELINE_EXTRACTION)
            step1_prompt = step1_template.format(
                file_count=str(len(source_files)), file_list=file_list, raw_file_contents=raw_sections
            )
            llm = context.require_llm()
            binder = context.require_binder()
            cfg = getattr(llm, "config", None)
            model_name = getattr(cfg, "model", None) or "unknown"
            temperature = getattr(cfg, "temperature", 0.1) or 0.1
            request_id = binder.record_llm_request(
                persona="Chronicler",
                prompt_key="log_timeline_extraction",
                system_prompt=system_prompt,
                user_prompt=step1_prompt,
                model=model_name,
                temperature=temperature,
                phase=PHASE_CHRONICLER,
            )
            import time as _time

            start_time = _time.time()
            raw_response = await llm.generate(step1_prompt, system_prompt, max_tokens=llm_max_tokens)
            latency_ms = (_time.time() - start_time) * 1000
            if raw_response and raw_response.strip():
                parsed = parser.parse_llm_response(raw_response)
                has_entries = bool(parsed.entries)
                timeline_response = parsed if has_entries else None
                binder.record_llm_response(
                    request_id=request_id,
                    raw_response=raw_response[:2000],
                    parsed_content=parsed.model_dump() if has_entries else None,
                    tokens_used=0,
                    latency_ms=latency_ms,
                    parse_success=has_entries,
                    parse_errors=[] if has_entries else ["Failed to parse timeline from raw response"],
                    phase=PHASE_CHRONICLER,
                )
                if has_entries:
                    logger.info("Step 1 complete: %d entries extracted", len(parsed.entries))
                else:
                    logger.warning("Step 1: LLM responded but no entries parsed")
            else:
                binder.record_llm_response(
                    request_id=request_id,
                    raw_response="(empty)",
                    parsed_content=None,
                    tokens_used=0,
                    latency_ms=latency_ms,
                    parse_success=False,
                    parse_errors=["LLM returned empty response"],
                    phase=PHASE_CHRONICLER,
                )
                logger.warning("Step 1: LLM returned empty response")
        except Exception as e:
            logger.warning("Chronicler Step 1 (timeline extraction) failed: %s", e)
        if timeline_response and timeline_response.entries:
            binder = context.require_binder()
            timeline_entries = [parser.to_domain_model(e) for e in timeline_response.entries]
            binder.add_merged_timeline(
                entries=timeline_entries,
                total_entries=timeline_response.total_entries,
                total_errors=timeline_response.total_errors,
                total_warnings=timeline_response.total_warnings,
                total_info=timeline_response.total_info,
                file_count=timeline_response.file_count,
                earliest_timestamp=timeline_response.earliest_timestamp,
                latest_timestamp=timeline_response.latest_timestamp,
                created_by="Chronicler",
                phase=PHASE_CHRONICLER,
            )
            formatted_timeline = MergedTimelineParser.format_timeline(timeline_response.entries)
            logger.info("Step 1 complete: %d entries extracted", len(timeline_response.entries))
        if timeline_response and timeline_response.entries:
            step2_content = json.dumps(timeline_response.entries, indent=None, ensure_ascii=False)
        elif formatted_timeline:
            step2_content = (
                """The following entries were parsed from raw `%MSG` blocks, merged across all files, and sorted chronologically. Each entry shows board name, timestamp, severity, component, and message content.

"""
                + formatted_timeline
            )
        else:
            step2_content = (
                """The following are RAW log file contents. Each file section contains `%MSG` blocks that you must parse. The format is:
`%MSG-{level} {component}: {context} {timestamp} CST {source}:{line}`
followed by body lines, terminated by `%MSG`.

"""
                + raw_sections
            )
        boardreader_id = await self._identify_boardreaders(context, step2_content, all_errors, system_prompt)
        binder = context.require_binder()
        binder.add_boardreader_identification(
            boardreader_types=boardreader_id.boardreader_types,
            components=boardreader_id.components,
            error_messages=boardreader_id.error_messages,
            created_by="Chronicler",
            phase=PHASE_CHRONICLER,
        )
        components = set(boardreader_id.boardreader_types + boardreader_id.components)
        error_messages = boardreader_id.error_messages
        from srcs.knowledge.doc_loader import DocStore, LLMDocExtractor

        map_path = None
        docs_max = 12000
        if context.config is not None:
            map_path = context.config.subcomponent_map_path
            docs_max = context.config.docs_max_chars
        doc_store = DocStore(subcomponent_map_path=map_path)
        doc_store.load_all()
        llm = context.require_llm()
        extractor = LLMDocExtractor(doc_store, llm)
        doc_context = await extractor.extract_for_investigation(
            components, error_messages, max_chars=min(docs_max, max_content_chars // 4)
        )
        compact_doc_ref = await extractor.extract_compact_reference(components, error_messages, max_chars=docs_max // 3)
        step2_template = get_user_prompt(UserPromptType.LOG_BUNDLE_ANALYSIS)
        step2_prompt = step2_template.format(
            file_count=str(len(source_files)),
            file_list=file_list,
            merged_timeline=step2_content,
            total_errors=str(len(all_errors)),
            component_documentation=doc_context or "(no matching documentation)",
        )
        try:
            response = await self._call_llm_structured(
                context,
                step2_prompt,
                ChroniclerNarrativeResponse,
                system_prompt,
                "log_bundle_analysis",
                max_tokens=llm_max_tokens,
            )
            if self._is_empty_response(response):
                logger.warning("Chronicler Step 2 returned empty response, falling back to heuristic")
                llm_primary = await self._select_primary_error_llm(context, all_errors, compact_doc_ref, system_prompt)
                response = self._heuristic_analysis(all_errors, source_files, llm_primary)
        except Exception as e:
            logger.warning(f"Chronicler Step 2 (narrative analysis) failed: {e}")
            llm_primary = await self._select_primary_error_llm(context, all_errors, compact_doc_ref, system_prompt)
            response = self._heuristic_analysis(all_errors, source_files, llm_primary)
        log_bundle_parser = LogBundleParser()
        bundle_parts = log_bundle_parser.to_domain_model(response)
        primary_error = bundle_parts["primary_error"]
        clues = bundle_parts["clues"]
        board_analyses = bundle_parts["affected_boards"]
        cascade_links = bundle_parts["cascade_chain"]
        binder = context.require_binder()
        source_file_meta = [
            {"filename": sf.filename, "error_count": file_error_counts.get(sf.filename, 0)} for sf in source_files
        ]
        artifact_id = binder.add_log_bundle(
            source_files=source_file_meta,
            merged_timeline=step2_content,
            annotated_narrative=response.annotated_narrative,
            primary_error=primary_error,
            error_timeline=all_errors,
            cascade_description=response.cascade_description,
            clues=clues,
            affected_boards=board_analyses,
            cascade_chain=cascade_links,
            documentation_reference=compact_doc_ref,
            created_by="Chronicler",
            phase=PHASE_CHRONICLER,
        )
        primary_log = None
        primary_context: list[Any] = []
        if response.primary_error_file:
            primary_log, primary_context = self._find_primary_in_sources(
                source_files, response.primary_error_file, response.primary_error_message
            )
        content: dict[str, Any] = {
            "log_bundle_id": artifact_id,
            "file_count": len(source_files),
            "total_errors": len(all_errors),
        }
        if primary_log is not None:
            content["primary_error"] = primary_log
            content["primary_context"] = primary_context
            content["primary_file"] = response.primary_error_file
        return Contribution(
            persona_id="chronicler",
            phase=PHASE_CHRONICLER,
            content=content,
            confidence=0.7 if primary_log else 0.4,
            reasoning=(
                f"Analyzed {len(source_files)} files, identified primary error in {response.primary_error_file}"
                if response.primary_error_file
                else f"Analyzed {len(source_files)} files, no clear primary error"
            ),
        )

    async def reflect(self, context: InvestigationContext) -> Reflection:
        source_files = getattr(context, "source_files", None)
        if not source_files:
            return Reflection()
        return Reflection(
            insights=[f"Merged {len(source_files)} log files into chronological timeline"],
            uncertainties=["Primary error identification depends on timestamp accuracy"],
            suggestions=["Archivist should use LOG_BUNDLE clues for guided retrieval"],
        )

    async def respond_to(self, other: "BasePersona", message: str) -> str:
        return "The Chronicler focuses on timeline analysis across multiple log files."

    async def critique(self, contribution: Contribution) -> Critique:
        return Critique(target_contribution=contribution, issues=[], strengths=["Contribution noted"], severity="LOW")

    async def endorse(self, contribution: Contribution) -> bool:
        return True

    async def answer_question(self, context: "QuestionContext") -> Contribution:
        return Contribution(
            persona_id="chronicler",
            phase=PHASE_CHRONICLER,
            content={"answer": "The Chronicler specializes in multi-file log analysis."},
            confidence=0.3,
            reasoning="General answer - Chronicler is not a Q&A persona",
        )

    async def _identify_boardreaders(
        self,
        context: InvestigationContext,
        step2_content: str,
        all_errors: list[LogBundleErrorEntry],
        system_prompt: str,
    ) -> BoardReaderIdentification:
        from srcs.knowledge.doc_loader import DocStore

        map_path = None
        if context.config is not None:
            map_path = context.config.subcomponent_map_path
        id_doc_store = DocStore(subcomponent_map_path=map_path)
        id_doc_store.load_all()
        available_docs = id_doc_store.get_doc_names()
        content_for_id = step2_content[:8000]
        available_docs_text = "\n".join((f"- {name}.md" for name in available_docs))
        template = get_user_prompt(UserPromptType.BOARDREADER_IDENTIFICATION)
        prompt = template.format(available_docs=available_docs_text, log_content=content_for_id)
        try:
            binder = context.require_binder()
            llm = context.require_llm()
            cfg = getattr(llm, "config", None)
            model_name = getattr(cfg, "model", None) or "unknown"
            temperature = getattr(cfg, "temperature", 0.1) or 0.1
            request_id = binder.record_llm_request(
                persona="Chronicler",
                prompt_key="boardreader_identification",
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=model_name,
                temperature=temperature,
                phase=PHASE_CHRONICLER,
            )
            import time as _time

            start_time = _time.time()
            result = await self._call_llm_structured(
                context, prompt, BoardReaderIdentification, system_prompt, "boardreader_identification"
            )
            latency_ms = (_time.time() - start_time) * 1000
            binder.record_llm_response(
                request_id=request_id,
                raw_response=result.model_dump_json()[:2000],
                parsed_content=result.model_dump(),
                tokens_used=0,
                latency_ms=latency_ms,
                parse_success=True,
                phase=PHASE_CHRONICLER,
            )
            logger.info(
                "Step 1.5: identified boardreaders=%s, components=%s", result.boardreader_types, result.components
            )
            if not result.error_messages:
                result.error_messages = [err.message for err in all_errors[:20]]
            return result
        except Exception as e:
            logger.warning(
                "Chronicler Step 1.5 (boardreader identification) failed: %s; falling back to heuristic extraction", e
            )
            return self._heuristic_boardreader_extraction(step2_content, all_errors)

    @staticmethod
    def _heuristic_boardreader_extraction(
        step2_content: str, all_errors: list[LogBundleErrorEntry]
    ) -> BoardReaderIdentification:
        from srcs.knowledge.doc_loader import DocStore, extract_names_from_message

        components: set[str] = set()
        error_messages: list[str] = []
        try:
            entries = json.loads(step2_content)
            if isinstance(entries, list):
                for entry in entries:
                    comp = entry.get("component", "")
                    if comp:
                        components.add(comp)
                    msg = entry.get("message", "")
                    if msg:
                        error_messages.append(msg)
        except (json.JSONDecodeError, TypeError):
            pass
        if not components:
            for err in all_errors:
                if err.component:
                    components.add(err.component)
                error_messages.append(err.message)
        all_candidates: set[str] = set(components)
        for msg in error_messages:
            all_candidates.update(extract_names_from_message(msg))
        doc_store = DocStore()
        doc_store.load_all()
        matched = doc_store.match_components(all_candidates)
        resolved: set[str] = set()
        for doc_name in matched.values():
            resolved.add(doc_name)
        return BoardReaderIdentification(
            boardreader_types=sorted(resolved), components=list(components), error_messages=error_messages[:20]
        )

    @staticmethod
    def _is_empty_response(response: ChroniclerNarrativeResponse) -> bool:
        has_primary = bool(response.primary_error_message.strip())
        has_boards = len(response.affected_boards) > 0
        return not has_primary and (not has_boards)

    @staticmethod
    def _validate_file_content_quality(logs: list[Any], filename: str) -> bool:
        if not logs:
            return True
        structured_count = 0
        fallback_count = 0
        for log_entry in logs:
            if log_entry.component and log_entry.component != "Unknown":
                structured_count += 1
            else:
                fallback_count += 1
        if structured_count == 0 and fallback_count > 10:
            logger.warning(
                f"File {filename} has 0 structured entries and {fallback_count} fallback entries - likely HTML content"
            )
            return False
        return True

    @staticmethod
    def _select_best_primary_error(all_errors: list[LogBundleErrorEntry]) -> LogBundleErrorEntry | None:
        if not all_errors:
            return None
        if len(all_errors) == 1:
            return all_errors[0]
        _ROOT_CAUSE_KEYWORDS = (
            "hardware",
            "wrong event size",
            "timeout",
            "dropped",
            "buffer overflow",
            "tried to write",
            "into a",
            "fragment timeout",
            "readout error",
            "board not responding",
        )
        file_error_counts: dict[str, int] = {}
        for err in all_errors:
            file_error_counts[err.filename] = file_error_counts.get(err.filename, 0) + 1
        timestamps = [e.timestamp for e in all_errors if e.timestamp is not None]
        earliest = min(timestamps) if timestamps else None
        latest = max(timestamps) if timestamps else None
        time_range = (latest - earliest).total_seconds() if earliest and latest and (latest != earliest) else 1.0
        best_error: LogBundleErrorEntry | None = None
        best_score = float("-inf")
        for err in all_errors:
            score = 0.0
            if err.level == "FATAL":
                score += 10.0
            if err.timestamp is not None and earliest is not None:
                elapsed = (err.timestamp - earliest).total_seconds()
                score += 5.0 * (1.0 - elapsed / time_range)
            msg_lower = err.message.lower()
            for kw in _ROOT_CAUSE_KEYWORDS:
                if kw in msg_lower:
                    score += 3.0
                    break
            fc = file_error_counts.get(err.filename, 1)
            if fc > 3:
                score -= 1.0
            if score > best_score:
                best_score = score
                best_error = err
        return best_error

    async def _select_primary_error_llm(
        self,
        context: InvestigationContext,
        all_errors: list[LogBundleErrorEntry],
        compact_doc_ref: str,
        system_prompt: str,
    ) -> LogBundleErrorEntry | None:
        if not all_errors:
            return None
        try:
            error_lines: list[str] = []
            for i, err in enumerate(all_errors[:40]):
                msg_preview = err.message.replace("\n", " ")
                ts = err.timestamp.strftime("%H:%M:%S") if err.timestamp else "??:??:??"
                error_lines.append(f"{i + 1}. [{_extract_board_name(err.filename)}] {ts} {err.level}: {msg_preview}")
            error_list = "\n".join(error_lines)
            doc_section = f"\n\nComponent documentation:\n{compact_doc_ref}" if compact_doc_ref else ""
            template = get_user_prompt(UserPromptType.PRIMARY_ERROR_SELECTION)
            prompt = template.format(error_list=error_list, doc_section=doc_section)
            result = await self._call_llm_structured(
                context, prompt, PrimaryErrorSelection, system_prompt, "primary_error_selection"
            )
            if result.primary_error_message:
                prefix = result.primary_error_message
                for err in all_errors:
                    if prefix in err.message:
                        logger.info(
                            "Step 2.5: selected primary via message match: [%s] %s...",
                            _extract_board_name(err.filename),
                            err.message[:60],
                        )
                        return err
            if result.primary_error_filename:
                selected_board = _extract_board_name(result.primary_error_filename)
                for err in all_errors:
                    if _extract_board_name(err.filename) == selected_board:
                        logger.info(
                            "Step 2.5: selected primary via board match: [%s] %s...", selected_board, err.message[:60]
                        )
                        return err
            return None
        except Exception as e:
            logger.warning("Chronicler Step 2.5 (primary error selection) failed: %s", e)
            return None

    def _heuristic_analysis(
        self,
        all_errors: list[LogBundleErrorEntry],
        source_files: list[Any],
        primary_override: LogBundleErrorEntry | None = None,
    ) -> ChroniclerNarrativeResponse:
        primary = primary_override or self._select_best_primary_error(all_errors)
        primary_file = primary.filename if primary else ""
        primary_message = primary.message if primary else ""
        primary_board = _extract_board_name(primary_file) if primary_file else ""
        boards_seen: dict[str, list[LogBundleErrorEntry]] = {}
        for err in all_errors:
            board = _extract_board_name(err.filename)
            boards_seen.setdefault(board, []).append(err)
        affected: list[dict[str, Any]] = []
        for board, errs in boards_seen.items():
            is_primary_board = board == primary_board
            affected.append(
                {
                    "board_name": board,
                    "filename": errs[0].filename,
                    "role": "primary_failure" if is_primary_board else "affected",
                    "failure_mode": errs[0].message,
                    "key_error_message": errs[0].message,
                    "error_count": len(errs),
                }
            )
        cascade_chain: list[dict[str, Any]] = []
        if primary_board:
            for board, errs in boards_seen.items():
                if board != primary_board:
                    cascade_chain.append(
                        {
                            "from_board": primary_board,
                            "to_board": board,
                            "mechanism": "temporal correlation after primary failure",
                            "evidence": f"Errors in {board} follow primary failure in {primary_board}",
                        }
                    )
        cascade_desc = (
            f"Primary failure in {primary_board} ({primary_message}), cascading to {len(cascade_chain)} other board(s)"
            if primary_board and cascade_chain
            else "Unable to determine cascade without LLM analysis"
        )
        return ChroniclerNarrativeResponse(
            annotated_narrative=f"Heuristic analysis of {len(source_files)} files. Primary error in {primary_file}: {primary_message}",
            primary_error_file=primary_file,
            primary_error_message=primary_message,
            cascade_description=cascade_desc,
            clues=(
                [
                    {
                        "clue_type": "error_pattern",
                        "description": f"Primary error: {primary_message}",
                        "source_file": primary_file,
                        "relevance": "HIGH",
                    }
                ]
                if primary_message
                else []
            ),
            affected_boards=affected,
            cascade_chain=cascade_chain,
        )

    def _find_primary_in_sources(
        self, source_files: list[Any], primary_filename: str, primary_message: str
    ) -> tuple[Any, list[Any]]:
        from srcs.models.log_parser import extract_error_and_context, parse_log_content

        primary_board = _extract_board_name(primary_filename)
        matched_sf = None
        for sf in source_files:
            if sf.filename == primary_filename:
                matched_sf = sf
                break
            if _extract_board_name(sf.filename) == primary_board:
                matched_sf = sf
                break
        search_order = ([matched_sf] if matched_sf else []) + [sf for sf in source_files if sf is not matched_sf]
        for sf in search_order:
            logs = parse_log_content(sf.content)
            if not logs:
                continue
            for log_entry in logs:
                if log_entry.level in ("ERROR", "FATAL") and primary_message in log_entry.message:
                    context_entries: list[Any] = []
                    for ctx_sf in source_files:
                        ctx_logs = parse_log_content(ctx_sf.content)
                        for cl in ctx_logs:
                            if not (cl.message == log_entry.message and cl.level == log_entry.level):
                                context_entries.append(cl)
                    context_entries.sort(key=lambda e: e.timestamp or datetime.min)
                    return (log_entry, context_entries[:100])
            if sf is matched_sf:
                error, ctx = extract_error_and_context(logs, sf.error_line, 60)
                return (error, ctx)
        return (None, [])


def _extract_board_name(filename: str) -> str:
    name = filename
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if name.endswith(".log"):
        name = name[:-4]
    if "-" in name:
        parts = name.split("-", 1)
        if parts[0].startswith("run") and parts[0][3:].isdigit():
            suffix = parts[1]
            for prefix in ("icaruspmt", "icarus", "sbnd"):
                if suffix.startswith(prefix):
                    suffix = suffix[len(prefix) :]
                    break
            if suffix.startswith("_"):
                suffix = suffix[1:]
            return suffix
    return name


def _build_raw_file_sections(valid_files: list[Any], file_error_counts: dict[str, int]) -> str:
    sections: list[str] = []
    for sf in valid_files:
        board = _extract_board_name(sf.filename)
        ec = file_error_counts.get(sf.filename, 0)
        header = f"### [{board}] {sf.filename} ({ec} errors)"
        sections.append(f"{header}\n```\n{sf.content}\n```")
    return "\n\n".join(sections)


def _truncate_raw_sections(valid_files: list[Any], file_error_counts: dict[str, int], max_chars: int) -> str:
    total_raw = sum((len(sf.content) for sf in valid_files))
    if total_raw == 0:
        return ""
    overhead_per_file = 100
    usable = max_chars - overhead_per_file * len(valid_files)
    if usable < 200 * len(valid_files):
        usable = 200 * len(valid_files)
    sections: list[str] = []
    for sf in valid_files:
        board = _extract_board_name(sf.filename)
        ec = file_error_counts.get(sf.filename, 0)
        header = f"### [{board}] {sf.filename} ({ec} errors)"
        file_budget = int(usable * len(sf.content) / total_raw)
        file_budget = max(file_budget, 200)
        if len(sf.content) > file_budget:
            content = _truncate_file_content(sf.content, file_budget)
        else:
            content = sf.content
        sections.append(f"{header}\n```\n{content}\n```")
    return "\n\n".join(sections)


def _truncate_file_content(content: str, max_chars: int) -> str:
    lines = content.split("\n")
    if len(lines) <= 15:
        return content
    important: set[int] = set()
    for i, line in enumerate(lines):
        is_error = False
        for marker in ("%MSG-e", "%MSG-s", "%MSG-w", "ERROR", "FATAL"):
            if marker in line:
                is_error = True
                break
        if is_error:
            for j in range(max(0, i - 3), min(len(lines), i + 4)):
                important.add(j)
    head = set(range(min(5, len(lines))))
    tail = set(range(max(0, len(lines) - 5), len(lines)))
    all_keep = sorted(head | important | tail)
    result_lines: list[str] = []
    total = 0
    prev_idx = -2
    for idx in all_keep:
        line = lines[idx]
        if total + len(line) + 1 > max_chars:
            result_lines.append(f"... [{len(lines) - idx} lines omitted] ...")
            break
        if idx > prev_idx + 1:
            omitted = idx - prev_idx - 1
            result_lines.append(f"... [{omitted} lines omitted] ...")
        result_lines.append(line)
        total += len(line) + 1
        prev_idx = idx
    return "\n".join(result_lines)
