"""
File: server.py
Purpose: MCP Server for Workbinder Artifacts, Access Logs, and Investigation...
Category: Utility
Author: artdaq team
Depends: agent, callbacks, client, config, indexer, ...
Exports: get_db_path, get_coordinator, create_mcp_server, run_mcp_server
Complexity: High | Lines: 1830
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from mcp.server.fastmcp import Context, FastMCP
from srcs.workbinder import BinderStore

if TYPE_CHECKING:
    from srcs.agent import InvestigationCoordinator
    from srcs.api.client import AgentClient
logger = logging.getLogger(__name__)
_client: "AgentClient | None" = None
_client_session_id: str | None = None


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def get_db_path() -> Path:
    data_dir = os.environ.get("ARTDAQ_DATA_DIR", "./data")
    return Path(data_dir) / "knowledge.db"


def _qa_db_path() -> Path:
    data_dir = os.environ.get("ARTDAQ_DATA_DIR", "./data")
    return Path(data_dir) / "qa_sessions.db"


def _get_api_url() -> str | None:
    return os.environ.get("ARTDAQ_API_URL")


async def _get_agent_client() -> "AgentClient | None":
    global _client, _client_session_id
    api_url = _get_api_url()
    if not api_url:
        return None
    if _client is None:
        from srcs.api.client import AgentClient

        _client = AgentClient(api_url)
        await _client.__aenter__()
        session = await _client.create_session()
        _client_session_id = session["session_id"]
        logger.info("Initialized AgentClient for MCP server at %s", api_url)
    return _client


_coordinator: "InvestigationCoordinator | None" = None


async def get_coordinator() -> "InvestigationCoordinator":
    global _coordinator
    if _coordinator is None:
        from srcs.config import CoordinatorFactory, load_config

        config = load_config()
        _coordinator = CoordinatorFactory.create(config)
        logger.info("Initialized investigation coordinator for MCP server")
    return _coordinator


def create_mcp_server(port: int = 8001) -> FastMCP:
    mcp = FastMCP("artdaq-binder", port=port)

    @mcp.tool()
    async def list_binders(status: str | None = None, limit: int = 50) -> str:
        store = BinderStore(get_db_path())
        binders = await store.list_binders(status=status, limit=limit)
        return json.dumps(binders, default=_json_default, indent=2)

    @mcp.tool()
    async def get_binder(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        binder = await store.load_binder(binder_id)
        if not binder:
            return json.dumps({"error": f"Binder not found: {binder_id}"})
        counts = await store.get_artifact_count(binder_id)
        return json.dumps(
            {
                "id": binder.id,
                "investigation_id": binder.investigation_id,
                "status": binder.status,
                "created_at": binder.created_at.isoformat(),
                "updated_at": binder.updated_at.isoformat(),
                "artifact_counts": counts,
            },
            default=_json_default,
            indent=2,
        )

    @mcp.tool()
    async def get_binder_summary(investigation_id: str) -> str:
        store = BinderStore(get_db_path())
        summary = await store.get_investigation_summary(investigation_id)
        if not summary:
            return json.dumps({"error": f"No binder found for investigation: {investigation_id}"})
        return json.dumps(summary, default=_json_default, indent=2)

    @mcp.tool()
    async def get_binder_by_investigation(investigation_id: str) -> str:
        store = BinderStore(get_db_path())
        binder = await store.load_binder_for_investigation(investigation_id)
        if not binder:
            return json.dumps({"error": f"No binder found for investigation: {investigation_id}"})
        return json.dumps(
            {"binder_id": binder.id, "investigation_id": binder.investigation_id, "status": binder.status},
            default=_json_default,
            indent=2,
        )

    @mcp.tool()
    async def search_artifacts(
        binder_id: str,
        artifact_type: str | None = None,
        phase: int | None = None,
        function_name: str | None = None,
        tags: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> str:
        store = BinderStore(get_db_path())
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        artifacts = await store.query_artifacts(
            binder_id=binder_id,
            artifact_type=artifact_type,
            phase=phase,
            function_name=function_name,
            tags=tag_list,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_artifact(binder_id: str, artifact_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, include_deleted=True, limit=1000)
        for artifact in artifacts:
            if artifact.id == artifact_id:
                return json.dumps(artifact.model_dump(mode="json"), default=_json_default, indent=2)
        return json.dumps({"error": f"Artifact not found: {artifact_id}"})

    @mcp.tool()
    async def get_artifact_history(binder_id: str, artifact_id: str) -> str:
        store = BinderStore(get_db_path())
        binder = await store.load_binder(binder_id)
        if not binder:
            return json.dumps({"error": f"Binder not found: {binder_id}"})
        history = [h for h in binder._history if h.artifact_id == artifact_id]
        return json.dumps([h.model_dump(mode="json") for h in history], default=_json_default, indent=2)

    @mcp.tool()
    async def search_artifact_content(binder_id: str, query: str, artifact_types: str | None = None) -> str:
        store = BinderStore(get_db_path())
        type_list = [t.strip() for t in artifact_types.split(",")] if artifact_types else None
        artifacts = await store.search_artifacts(binder_id=binder_id, query=query, artifact_types=type_list)
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def search_audit_log(
        binder_id: str,
        persona_name: str | None = None,
        phase_number: int | None = None,
        operation_type: str | None = None,
        limit: int = 100,
    ) -> str:
        store = BinderStore(get_db_path())
        entries = await store.get_audit_log(
            binder_id=binder_id,
            persona_name=persona_name,
            phase_number=phase_number,
            operation_type=operation_type,
            limit=limit,
        )
        return json.dumps([e.model_dump(mode="json") for e in entries], default=_json_default, indent=2)

    @mcp.tool()
    async def get_artifact_audit_trail(binder_id: str, artifact_id: str) -> str:
        store = BinderStore(get_db_path())
        entries = await store.get_audit_log(binder_id=binder_id, limit=10000)
        artifact_entries = [e for e in entries if e.artifact_id == artifact_id]
        return json.dumps([e.model_dump(mode="json") for e in artifact_entries], default=_json_default, indent=2)

    @mcp.tool()
    async def get_audit_summary(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        entries = await store.get_audit_log(binder_id=binder_id, limit=100000)
        by_persona: dict[str, int] = {}
        by_phase: dict[int, int] = {}
        by_operation: dict[str, int] = {}
        for entry in entries:
            by_persona[entry.persona_name] = by_persona.get(entry.persona_name, 0) + 1
            if entry.phase_number is not None:
                by_phase[entry.phase_number] = by_phase.get(entry.phase_number, 0) + 1
            by_operation[entry.operation_type] = by_operation.get(entry.operation_type, 0) + 1
        return json.dumps(
            {
                "total_entries": len(entries),
                "by_persona": by_persona,
                "by_phase": {str(k): v for k, v in sorted(by_phase.items())},
                "by_operation": by_operation,
            },
            default=_json_default,
            indent=2,
        )

    @mcp.tool()
    async def list_patterns(
        active_only: bool = True,
        min_confidence: float | None = None,
        min_times_seen: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        store = BinderStore(get_db_path())
        patterns, total = await store.list_patterns(
            active_only=active_only,
            min_confidence=min_confidence,
            min_times_seen=min_times_seen,
            limit=limit,
            offset=offset,
        )
        return json.dumps(
            {"patterns": patterns, "total": total, "limit": limit, "offset": offset}, default=_json_default, indent=2
        )

    @mcp.tool()
    async def get_pattern(pattern_id: str) -> str:
        store = BinderStore(get_db_path())
        pattern = await store.get_pattern(pattern_id)
        if not pattern:
            return json.dumps({"error": f"Pattern not found: {pattern_id}"})
        return json.dumps(pattern, default=_json_default, indent=2)

    @mcp.tool()
    async def get_pattern_statistics() -> str:
        store = BinderStore(get_db_path())
        stats = await store.get_pattern_statistics()
        return json.dumps(stats, default=_json_default, indent=2)

    @mcp.tool()
    async def list_calibrations(limit: int = 50) -> str:
        store = BinderStore(get_db_path())
        calibrations = await store.list_calibrations(limit=limit)
        return json.dumps(calibrations, default=_json_default, indent=2)

    @mcp.tool()
    async def get_calibration(model: str, error_type: str | None = None) -> str:
        store = BinderStore(get_db_path())
        calibration = await store.get_calibration(model, error_type)
        if not calibration:
            return json.dumps({"error": f"No calibration found for model: {model}"})
        return json.dumps(calibration, default=_json_default, indent=2)

    @mcp.tool()
    async def get_hypotheses(
        binder_id: str, min_score: float | None = None, source: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        hypotheses = await store.get_hypotheses(binder_id=binder_id, min_score=min_score, source=source, limit=limit)
        return json.dumps([h.model_dump(mode="json") for h in hypotheses], default=_json_default, indent=2)

    @mcp.tool()
    async def get_evidence(
        binder_id: str, evidence_type: str | None = None, strength: str | None = None, limit: int = 100
    ) -> str:
        store = BinderStore(get_db_path())
        evidence = await store.get_evidence_items(
            binder_id=binder_id, evidence_type=evidence_type, strength=strength, limit=limit
        )
        return json.dumps([e.model_dump(mode="json") for e in evidence], default=_json_default, indent=2)

    @mcp.tool()
    async def get_causal_chains(binder_id: str, hypothesis_id: str | None = None, limit: int = 20) -> str:
        store = BinderStore(get_db_path())
        chains = await store.get_causal_chains(binder_id=binder_id, hypothesis_id=hypothesis_id, limit=limit)
        return json.dumps([c.model_dump(mode="json") for c in chains], default=_json_default, indent=2)

    @mcp.tool()
    async def get_challenges(
        binder_id: str, resolved: bool | None = None, severity: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        challenges = await store.get_challenges(binder_id=binder_id, resolved=resolved, severity=severity, limit=limit)
        return json.dumps([c.model_dump(mode="json") for c in challenges], default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_requests(
        binder_id: str,
        persona: str | None = None,
        phase: int | None = None,
        prompt_key: str | None = None,
        limit: int = 100,
    ) -> str:
        store = BinderStore(get_db_path())
        requests = await store.get_llm_requests(
            binder_id=binder_id, persona=persona, phase=phase, prompt_key=prompt_key, limit=limit
        )
        return json.dumps([r.model_dump(mode="json") for r in requests], default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_responses(
        binder_id: str,
        request_id: str | None = None,
        phase: int | None = None,
        parse_success: bool | None = None,
        limit: int = 100,
    ) -> str:
        store = BinderStore(get_db_path())
        responses = await store.get_llm_responses(
            binder_id=binder_id, request_id=request_id, phase=phase, parse_success=parse_success, limit=limit
        )
        return json.dumps([r.model_dump(mode="json") for r in responses], default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_exchanges(binder_id: str, phase: int | None = None) -> str:
        store = BinderStore(get_db_path())
        exchanges = await store.get_llm_exchanges(binder_id=binder_id, phase=phase)
        result = []
        for req, resp in exchanges:
            result.append(
                {"request": req.model_dump(mode="json"), "response": resp.model_dump(mode="json") if resp else None}
            )
        return json.dumps(result, default=_json_default, indent=2)

    @mcp.tool()
    async def get_llm_statistics(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        stats = await store.get_llm_statistics(binder_id)
        return json.dumps(stats, default=_json_default, indent=2)

    @mcp.tool()
    async def get_investigation_state(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        state = await store.get_investigation_state_artifact(binder_id)
        if not state:
            return json.dumps({"error": f"No investigation state found for binder: {binder_id}"})
        return json.dumps(state.model_dump(mode="json"), default=_json_default, indent=2)

    @mcp.tool()
    async def get_phase_states(binder_id: str, status: str | None = None) -> str:
        store = BinderStore(get_db_path())
        states = await store.get_phase_states(binder_id=binder_id, status=status)
        return json.dumps([s.model_dump(mode="json") for s in states], default=_json_default, indent=2)

    @mcp.tool()
    async def list_investigations_with_state(
        outcome: str | None = None, status: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        investigations = await store.list_investigations_with_state(outcome=outcome, status=status, limit=limit)
        return json.dumps(investigations, default=_json_default, indent=2)

    @mcp.tool()
    async def find_similar_investigations(
        error_function: str | None = None, error_message_pattern: str | None = None, limit: int = 10
    ) -> str:
        store = BinderStore(get_db_path())
        similar = await store.get_similar_investigations(
            error_function=error_function, error_message_pattern=error_message_pattern, limit=limit
        )
        return json.dumps(similar, default=_json_default, indent=2)

    @mcp.tool()
    async def get_conclusion(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="conclusion", limit=1)
        if not artifacts:
            return json.dumps({"error": f"No conclusion found for binder: {binder_id}"})
        return json.dumps(artifacts[0].model_dump(mode="json"), default=_json_default, indent=2)

    @mcp.tool()
    async def get_error_context(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="error_context", limit=1)
        if not artifacts:
            return json.dumps({"error": f"No error context found for binder: {binder_id}"})
        return json.dumps(artifacts[0].model_dump(mode="json"), default=_json_default, indent=2)

    @mcp.tool()
    async def get_flow_config(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="flow_config", limit=1)
        if not artifacts:
            return json.dumps({"error": f"No flow config found for binder: {binder_id}"})
        return json.dumps(artifacts[0].model_dump(mode="json"), default=_json_default, indent=2)

    @mcp.tool()
    async def get_log_bundle(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="log_bundle", limit=1)
        if not artifacts:
            return json.dumps({"error": f"No log bundle found for binder: {binder_id}"})
        return json.dumps(artifacts[0].model_dump(mode="json"), default=_json_default, indent=2)

    @mcp.tool()
    async def get_merged_timeline(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="merged_timeline", limit=1)
        if not artifacts:
            return json.dumps({"error": f"No merged timeline found for binder: {binder_id}"})
        return json.dumps(artifacts[0].model_dump(mode="json"), default=_json_default, indent=2)

    @mcp.tool()
    async def get_findings(
        binder_id: str,
        persona: str | None = None,
        finding_type: str | None = None,
        min_confidence: float | None = None,
        limit: int = 50,
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="finding", limit=limit)
        if persona:
            artifacts = [a for a in artifacts if getattr(a, "persona", None) == persona]
        if finding_type:
            artifacts = [
                a
                for a in artifacts
                if (
                    getattr(a, "finding_type", None).value
                    if hasattr(getattr(a, "finding_type", None), "value")
                    else str(getattr(a, "finding_type", None))
                )
                == finding_type
            ]
        if min_confidence is not None:
            artifacts = [a for a in artifacts if getattr(a, "confidence", 0.0) >= min_confidence]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_contributions(
        binder_id: str, persona_id: str | None = None, contribution_phase: int | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="persona_contribution", limit=limit)
        if persona_id:
            artifacts = [a for a in artifacts if getattr(a, "persona_id", None) == persona_id]
        if contribution_phase is not None:
            artifacts = [a for a in artifacts if getattr(a, "contribution_phase", None) == contribution_phase]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_source_locations(
        binder_id: str, file_path: str | None = None, min_match_score: float | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="source_location", limit=limit)
        if file_path:
            artifacts = [a for a in artifacts if file_path in getattr(a, "file_path", "")]
        if min_match_score is not None:
            artifacts = [a for a in artifacts if getattr(a, "match_score", 0.0) >= min_match_score]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_code_snippets(
        binder_id: str, file_path: str | None = None, language: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="code_snippet", limit=limit)
        if file_path:
            artifacts = [a for a in artifacts if file_path in getattr(a, "file_path", "")]
        if language:
            artifacts = [a for a in artifacts if getattr(a, "language", "") == language]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_call_graphs(binder_id: str, center_function: str | None = None, limit: int = 50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="call_graph", limit=limit)
        if center_function:
            artifacts = [a for a in artifacts if getattr(a, "center_function", None) == center_function]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_function_summaries(
        binder_id: str, center_function: str | None = None, role: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="function_summary", limit=limit)
        if center_function:
            artifacts = [a for a in artifacts if getattr(a, "center_function", None) == center_function]
        if role:
            artifacts = [a for a in artifacts if getattr(a, "role", None) == role]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_annotations(
        binder_id: str, target_artifact_id: str | None = None, annotation_type: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="annotation", limit=limit)
        if target_artifact_id:
            artifacts = [a for a in artifacts if getattr(a, "target_artifact_id", None) == target_artifact_id]
        if annotation_type:
            artifacts = [
                a
                for a in artifacts
                if (
                    getattr(a, "annotation_type", None).value
                    if hasattr(getattr(a, "annotation_type", None), "value")
                    else str(getattr(a, "annotation_type", None))
                )
                == annotation_type
            ]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_boardreader_identifications(binder_id: str, limit: int = 50) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(
            binder_id=binder_id, artifact_type="boardreader_identification", limit=limit
        )
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def get_feedback(
        binder_id: str, was_correct: bool | None = None, feedback_source: str | None = None, limit: int = 50
    ) -> str:
        store = BinderStore(get_db_path())
        artifacts = await store.query_artifacts(binder_id=binder_id, artifact_type="feedback", limit=limit)
        if was_correct is not None:
            artifacts = [a for a in artifacts if getattr(a, "was_correct", None) == was_correct]
        if feedback_source:
            artifacts = [a for a in artifacts if getattr(a, "feedback_source", None) == feedback_source]
        return json.dumps([a.model_dump(mode="json") for a in artifacts], default=_json_default, indent=2)

    @mcp.tool()
    async def investigate_error(
        error_message: str,
        log_content: str | None = None,
        error_line: int | None = None,
        context_lines: int = 60,
        additional_files: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        from srcs.agent.callbacks import PhaseEvent
        from srcs.models import Log
        from srcs.models.log_parser import create_log_from_message, extract_error_and_context, parse_log_content

        phase_names = [
            "Prior Knowledge Retrieval",
            "Hypothesis Generation",
            "Evidence Seeking",
            "Causal Chain Construction",
            "Adversarial Review",
            "Insufficiency Check",
            "Synthesis",
            "Pattern Learning",
        ]
        import asyncio

        async def _safe_progress(coro: Any) -> None:
            try:
                await coro
            except Exception:
                pass

        def on_phase(event: PhaseEvent) -> None:
            if ctx:
                phase_name = phase_names[event.phase] if event.phase < len(phase_names) else f"Phase {event.phase}"
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_safe_progress(ctx.report_progress(progress=event.phase + 1, total=8)))
                    loop.create_task(_safe_progress(ctx.info(f"Phase {event.phase}: {phase_name}")))
                except RuntimeError:
                    pass

        try:
            agent = await _get_agent_client()
            if agent is not None and _client_session_id is not None:
                result_data = await agent.investigate(_client_session_id, error_message=error_message)
                return json.dumps(result_data, default=_json_default, indent=2)
            coordinator = await get_coordinator()
            context_logs: list[Log] = []
            if log_content:
                logs = parse_log_content(log_content)
                if logs:
                    error, context_logs = extract_error_and_context(logs, error_line, context_lines)
                else:
                    error = create_log_from_message(error_message)
            else:
                error = create_log_from_message(error_message)
            source_files = None
            if additional_files:
                from srcs.models.logs import SourceFile

                try:
                    files_data = json.loads(additional_files)
                    source_files_list = []
                    if log_content:
                        source_files_list.append(
                            SourceFile(filename="primary.log", content=log_content, error_line=error_line)
                        )
                    for fd in files_data:
                        source_files_list.append(
                            SourceFile(
                                filename=fd.get("filename", "unknown.log"),
                                content=fd.get("content", ""),
                                error_line=fd.get("error_line"),
                            )
                        )
                    if len(source_files_list) > 1:
                        source_files = source_files_list
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse additional_files JSON: {e}")
            result = await coordinator.investigate(error, context_logs, callback=on_phase, source_files=source_files)
            return json.dumps(result.model_dump(mode="json"), default=_json_default, indent=2)
        except Exception as e:
            logger.exception("Investigation failed")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def analyze_message(message: str, ctx: Context | None = None) -> str:
        result: str = await investigate_error(
            error_message=message, log_content=None, error_line=None, context_lines=60, ctx=ctx
        )
        return result

    @mcp.tool()
    async def submit_feedback(
        investigation_id: str,
        correct: bool,
        actual_cause: str | None = None,
        corrected_summary: str | None = None,
        feedback_source: str = "mcp",
    ) -> str:
        from srcs.knowledge import KnowledgeBase, PatternLearner, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigation = await kb.get_investigation(investigation_id)
            if not investigation:
                return json.dumps({"success": False, "error": f"Investigation {investigation_id} not found"}, indent=2)
            stated_confidence = 0.5
            if investigation.hypotheses and investigation.hypotheses[0].score > 0:
                stated_confidence = min(0.95, 0.3 + investigation.hypotheses[0].score * 0.5)
            await kb.update_calibration("default", stated_confidence, correct)
            learner = PatternLearner(str(kb.config.sqlite_path))
            learning_updates = await learner.apply_feedback(
                investigation_id, correct, actual_cause, feedback_source=feedback_source
            )
            return json.dumps(
                {
                    "success": True,
                    "message": "Feedback recorded successfully",
                    "stated_confidence": stated_confidence,
                    "correct": correct,
                    "actual_cause": actual_cause,
                    "feedback_source": feedback_source,
                    "patterns_updated": learning_updates.get("patterns_updated", []),
                    "patterns_created": learning_updates.get("patterns_created", []),
                },
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to submit feedback")
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    async def ask_experts(question: str, log_content: str | None = None, ctx: Context | None = None) -> str:
        import asyncio
        from srcs.models.logs import Log
        from srcs.persona.orchestrator import PanelOrchestrator, QAEvent

        async def _safe_progress(coro: Any) -> None:
            try:
                await coro
            except Exception:
                pass

        def on_event(event: QAEvent) -> None:
            if not ctx:
                return
            event_type = event.get("event", "")
            try:
                loop = asyncio.get_running_loop()
                if event_type == "classification":
                    loop.create_task(
                        _safe_progress(ctx.info(f"Question type: {event.get('question_type', 'unknown')}"))
                    )
                elif event_type == "panel_selected":
                    personas = event.get("personas", [])
                    loop.create_task(_safe_progress(ctx.info(f"Panel assembled: {', '.join(personas)}")))
                    loop.create_task(_safe_progress(ctx.report_progress(progress=1, total=5)))
                elif event_type == "contribution_start":
                    loop.create_task(_safe_progress(ctx.info(f"{event.get('persona', '')} is thinking...")))
                elif event_type == "contribution_complete":
                    loop.create_task(_safe_progress(ctx.report_progress(progress=2, total=5)))
                elif event_type == "voting_complete":
                    loop.create_task(_safe_progress(ctx.report_progress(progress=3, total=5)))
                elif event_type == "deliberation_complete":
                    loop.create_task(_safe_progress(ctx.report_progress(progress=4, total=5)))
                elif event_type == "synthesis_complete":
                    loop.create_task(_safe_progress(ctx.report_progress(progress=5, total=5)))
            except RuntimeError:
                pass

        try:
            agent = await _get_agent_client()
            if agent is not None and _client_session_id is not None:
                result_data = await agent.ask_experts(_client_session_id, question)
                return json.dumps(result_data, default=_json_default, indent=2)
            related_logs: list[Log] = []
            if log_content:
                from srcs.models.log_parser import parse_log_content

                related_logs = parse_log_content(log_content)
            orchestrator = PanelOrchestrator()
            response = await orchestrator.answer(
                question=question, related_logs=related_logs if related_logs else None, callback=on_event
            )
            result = {
                "question_id": response.question_id,
                "answer": response.answer,
                "confidence": response.confidence,
                "key_points": response.key_points,
                "caveats": response.caveats,
                "contributions_summary": response.contributions_summary,
                "dissenting_views": response.dissenting_views,
                "sources": response.sources,
                "citations": response.citations,
            }
            return json.dumps(result, default=_json_default, indent=2)
        except Exception as e:
            logger.exception("Ask experts failed")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def list_investigations(limit: int = 20, offset: int = 0, outcome: str | None = None) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigations = await kb.get_recent_investigations(limit, offset)
            filtered = investigations
            if outcome:
                filtered = [inv for inv in filtered if inv.outcome and inv.outcome.value == outcome]
            summaries = []
            for inv in filtered:
                root_cause = None
                confidence = None
                if inv.hypotheses and inv.hypotheses[0].score > 0:
                    root_cause = inv.hypotheses[0].description
                    confidence = inv.hypotheses[0].score
                summaries.append(
                    {
                        "investigation_id": inv.id,
                        "outcome": inv.outcome.value if inv.outcome else "UNKNOWN",
                        "root_cause": root_cause,
                        "confidence": confidence,
                        "duration_seconds": (
                            (inv.completed_at - inv.started_at).total_seconds() if inv.completed_at else 0.0
                        ),
                        "timestamp": inv.started_at,
                    }
                )
            return json.dumps(
                {"investigations": summaries, "total": len(investigations)}, default=_json_default, indent=2
            )
        except Exception as e:
            logger.exception("Failed to list investigations")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_investigation(investigation_id: str) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigation = await kb.get_investigation(investigation_id)
            if not investigation:
                return json.dumps({"error": f"Investigation not found: {investigation_id}"})
            return json.dumps(
                {
                    "id": investigation.id,
                    "trigger_error": {
                        "timestamp": investigation.trigger_error.timestamp,
                        "level": investigation.trigger_error.level,
                        "component": investigation.trigger_error.component,
                        "function": investigation.trigger_error.function,
                        "message": investigation.trigger_error.message,
                    },
                    "outcome": investigation.outcome.value if investigation.outcome else None,
                    "started_at": investigation.started_at.isoformat(),
                    "completed_at": investigation.completed_at.isoformat() if investigation.completed_at else None,
                    "hypotheses": [
                        {"id": h.id, "description": h.description, "score": h.score, "status": h.status}
                        for h in investigation.hypotheses
                    ],
                    "evidence_count": len(investigation.evidence.items),
                    "causal_chains_count": len(investigation.causal_chains),
                    "challenges_count": len(investigation.challenges),
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get investigation")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_investigation_quality(investigation_id: str) -> str:
        from srcs.agent import QualityAnalyzer, format_quality_report
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            investigation = await kb.get_investigation(investigation_id)
            if not investigation:
                return json.dumps({"error": f"Investigation not found: {investigation_id}"})
            analyzer = QualityAnalyzer()
            report = analyzer.analyze(investigation)
            return json.dumps(
                {
                    "investigation_id": investigation_id,
                    "quality_level": report.quality_level.value,
                    "overall_score": report.overall_score,
                    "report_text": format_quality_report(report),
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get investigation quality")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def list_question_types() -> str:
        from srcs.models.question import QuestionType

        return json.dumps(
            [
                {
                    "type": QuestionType.HOW_TO.value,
                    "description": "How to do something",
                    "example": "How do I configure fragment timeouts?",
                },
                {
                    "type": QuestionType.WHY.value,
                    "description": "Why something happens",
                    "example": "Why might EventBuilder timeout?",
                },
                {
                    "type": QuestionType.WHAT_IS.value,
                    "description": "What something is",
                    "example": "What is a BoardReader?",
                },
                {
                    "type": QuestionType.TROUBLESHOOT.value,
                    "description": "Troubleshooting an issue",
                    "example": "I'm seeing timeout errors in the BoardReader",
                },
                {
                    "type": QuestionType.COMPARE.value,
                    "description": "Comparing options",
                    "example": "What's the difference between push and pull mode?",
                },
                {
                    "type": QuestionType.BEST_PRACTICE.value,
                    "description": "Best practices",
                    "example": "What's the best way to handle data rates?",
                },
            ],
            indent=2,
        )

    @mcp.tool()
    async def get_question(question_id: str) -> str:
        import aiosqlite

        try:
            db_path = _qa_db_path()
            async with aiosqlite.connect(db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute("SELECT * FROM qa_sessions WHERE id = ?", (question_id,)) as cursor:
                    row = await cursor.fetchone()
            if not row:
                return json.dumps({"error": f"Q&A session not found: {question_id}"})
            async with aiosqlite.connect(db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    "SELECT * FROM qa_feedback WHERE qa_session_id = ? ORDER BY created_at", (question_id,)
                ) as cursor:
                    fb_rows = await cursor.fetchall()
            feedback = [
                {
                    "id": fb["id"],
                    "helpful": bool(fb["helpful"]),
                    "feedback_text": fb["feedback_text"],
                    "created_at": fb["created_at"],
                }
                for fb in fb_rows
            ]
            result = {
                "question_id": row["id"],
                "question": row["question"],
                "question_type": row["question_type"],
                "answer": row["answer"],
                "confidence": row["confidence"],
                "key_points": json.loads(row["key_points_json"]) if row["key_points_json"] else [],
                "caveats": json.loads(row["caveats_json"]) if row["caveats_json"] else [],
                "sources": json.loads(row["sources_json"]) if row["sources_json"] else [],
                "citations": json.loads(row["citations_json"]) if row["citations_json"] else [],
                "contributions_summary": (
                    json.loads(row["contributions_summary_json"]) if row["contributions_summary_json"] else {}
                ),
                "related_logs": json.loads(row["related_logs_json"]) if row["related_logs_json"] else None,
                "created_at": row["created_at"],
                "feedback": feedback,
            }
            return json.dumps(result, default=_json_default, indent=2)
        except Exception as e:
            logger.exception("Failed to get question")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def submit_question_feedback(question_id: str, helpful: bool, feedback_text: str | None = None) -> str:
        import aiosqlite

        try:
            db_path = _qa_db_path()
            async with aiosqlite.connect(db_path) as conn:
                async with conn.execute("SELECT id FROM qa_sessions WHERE id = ?", (question_id,)) as cursor:
                    if not await cursor.fetchone():
                        return json.dumps({"error": f"Q&A session not found: {question_id}"})
                await conn.execute(
                    "INSERT INTO qa_feedback (qa_session_id, helpful, feedback_text, created_at) VALUES (?, ?, ?, ?)",
                    (question_id, helpful, feedback_text, datetime.now().isoformat()),
                )
                await conn.commit()
            return json.dumps({"message": "Feedback recorded successfully", "qa_id": question_id}, indent=2)
        except Exception as e:
            logger.exception("Failed to submit question feedback")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_calibration_trend(model: str = "default", error_type: str | None = None, limit: int = 30) -> str:
        from srcs.knowledge import CalibrationHistoryTracker, StorageConfig
        from srcs.knowledge.reporting import format_trend_chart

        try:
            config = StorageConfig()
            tracker = CalibrationHistoryTracker(config.sqlite_path)
            trend = await tracker.get_trend(model, error_type, limit)
            trend_text = format_trend_chart(trend)
            return json.dumps(
                {
                    "model_name": trend.model_name,
                    "data_points": len(trend.timestamps),
                    "recent_biases": trend.biases[-10:] if trend.biases else [],
                    "recent_accuracies": trend.accuracies[-10:] if trend.accuracies else [],
                    "recent_sample_counts": trend.sample_counts[-10:] if trend.sample_counts else [],
                    "trend_text": trend_text,
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get calibration trend")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def record_calibration_snapshot(model: str = "default", error_type: str | None = None) -> str:
        from srcs.knowledge import CalibrationHistoryTracker, StorageConfig

        try:
            config = StorageConfig()
            tracker = CalibrationHistoryTracker(config.sqlite_path)
            await tracker.record_snapshot(model, error_type)
            return json.dumps({"message": f"Snapshot recorded for model {model}"}, indent=2)
        except Exception as e:
            logger.exception("Failed to record calibration snapshot")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_calibration_summary() -> str:
        from srcs.knowledge import CalibrationReporter, StorageConfig

        try:
            config = StorageConfig()
            reporter = CalibrationReporter(config.sqlite_path)
            calibrations = await reporter.get_all_calibrations()
            models = list(set((c.model_name for c in calibrations)))
            total_samples = sum((c.sample_size for c in calibrations))
            if calibrations:
                avg_bias = sum((c.overall_bias for c in calibrations)) / len(calibrations)
                total_correct: float = 0.0
                total = 0
                for c in calibrations:
                    for bucket in c.buckets.values():
                        total_correct += bucket.actual_accuracy * bucket.sample_count
                        total += bucket.sample_count
                avg_accuracy = total_correct / total if total > 0 else 0.0
            else:
                avg_bias = 0.0
                avg_accuracy = 0.0
            return json.dumps(
                {
                    "models": models,
                    "total_samples": total_samples,
                    "average_bias": avg_bias,
                    "average_accuracy": avg_accuracy,
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get calibration summary")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def export_calibration(model: str = "default", error_type: str | None = None) -> str:
        from srcs.knowledge import CalibrationReporter, StorageConfig, export_calibration_json

        try:
            config = StorageConfig()
            reporter = CalibrationReporter(config.sqlite_path)
            report = await reporter.generate_report(model, error_type)
            data = export_calibration_json(report)
            return json.dumps(data, default=_json_default, indent=2)
        except Exception as e:
            logger.exception("Failed to export calibration")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def clear_calibration_history(model: str | None = None) -> str:
        import aiosqlite
        from srcs.knowledge import StorageConfig

        try:
            config = StorageConfig()
            async with aiosqlite.connect(config.sqlite_path) as conn:
                if model:
                    await conn.execute("DELETE FROM calibration_history WHERE model_name = ?", (model,))
                else:
                    await conn.execute("DELETE FROM calibration_history")
                await conn.commit()
            msg = f"Cleared history for model {model}" if model else "Cleared all history"
            return json.dumps({"message": msg})
        except Exception as e:
            logger.exception("Failed to clear calibration history")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_pattern_root_causes(pattern_id: str) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            root_causes = await kb.sqlite.get_pattern_root_causes(pattern_id)
            return json.dumps(
                [
                    {
                        "id": rc.id,
                        "error_pattern_id": rc.error_pattern_id,
                        "description": rc.description,
                        "frequency": rc.frequency,
                    }
                    for rc in root_causes
                ],
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get pattern root causes")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def match_pattern(
        message_pattern: str, function: str | None = None, level: str = "ERROR", component: str | None = None
    ) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider
        from srcs.models import ErrorSignature

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            signature = ErrorSignature(
                function=function, message_pattern=message_pattern, level=level, component=component
            )
            match = await kb.find_pattern(signature)
            if not match:
                return json.dumps(
                    {"matched": False, "pattern": None, "confidence": 0.0, "matched_fields": [], "root_causes": []},
                    indent=2,
                )
            root_causes = await kb.sqlite.get_pattern_root_causes(match.pattern.id)
            return json.dumps(
                {
                    "matched": True,
                    "pattern": {
                        "id": match.pattern.id,
                        "name": match.pattern.name,
                        "description": match.pattern.description,
                        "signature_function": match.pattern.signature_function,
                        "signature_message_pattern": match.pattern.signature_message_pattern,
                        "signature_level": match.pattern.signature_level,
                        "times_seen": match.pattern.times_seen,
                        "times_correct": match.pattern.times_correct,
                        "times_incorrect": match.pattern.times_incorrect,
                        "pattern_confidence": match.pattern.pattern_confidence,
                        "is_active": match.pattern.is_active,
                    },
                    "confidence": match.confidence,
                    "matched_fields": match.matched_fields,
                    "root_causes": [
                        {
                            "id": rc.id,
                            "error_pattern_id": rc.error_pattern_id,
                            "description": rc.description,
                            "frequency": rc.frequency,
                        }
                        for rc in root_causes
                    ],
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to match pattern")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_pattern_accuracy_trend(pattern_id: str, limit: int = 30) -> str:
        import aiosqlite
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            pattern = await kb.sqlite.get_pattern_by_id(pattern_id)
            if not pattern:
                return json.dumps({"error": f"Pattern not found: {pattern_id}"})
            times_seen = pattern.times_seen or 0
            times_correct = pattern.times_correct or 0
            current_accuracy = times_correct / times_seen if times_seen > 0 else 0.0
            async with aiosqlite.connect(kb.config.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    """
                    SELECT
                        date(f.submitted_at) as feedback_date,
                        SUM(CASE WHEN f.was_correct = 1 THEN 1 ELSE 0 END)
                            as correct,
                        COUNT(*) as total
                    FROM investigation_feedback f
                    JOIN investigations i ON f.investigation_id = i.id
                    WHERE i.matched_pattern_id = ?
                    GROUP BY date(f.submitted_at)
                    ORDER BY feedback_date DESC
                    LIMIT ?
                    """,
                    (pattern_id, limit),
                ) as cursor:
                    trend_rows = await cursor.fetchall()
            trend = []
            running_correct = 0
            running_total = 0
            for row in reversed(list(trend_rows)):
                running_correct += row["correct"]
                running_total += row["total"]
                accuracy = running_correct / running_total if running_total > 0 else 0.0
                trend.append({"timestamp": row["feedback_date"], "accuracy": accuracy, "sample_count": running_total})
            trend_direction = "stable"
            if len(trend) >= 3:
                third = len(trend) // 3
                early_acc = sum((t["accuracy"] for t in trend[:third])) / third
                late_acc = sum((t["accuracy"] for t in trend[-third:])) / third
                diff = late_acc - early_acc
                if diff > 0.05:
                    trend_direction = "improving"
                elif diff < -0.05:
                    trend_direction = "declining"
            return json.dumps(
                {
                    "pattern_id": pattern_id,
                    "pattern_name": pattern.name,
                    "current_accuracy": current_accuracy,
                    "current_sample_count": times_seen,
                    "trend": trend,
                    "trend_direction": trend_direction,
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get pattern accuracy trend")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def deactivate_pattern(pattern_id: str) -> str:
        from srcs.knowledge import KnowledgeBase, StorageConfig
        from srcs.llm import LLMConfig, create_llm_provider

        try:
            llm = create_llm_provider(LLMConfig())
            kb = KnowledgeBase(StorageConfig(sqlite_path=str(get_db_path())), llm)
            deactivated = await kb.sqlite.deactivate_pattern(pattern_id)
            if not deactivated:
                return json.dumps({"error": f"Pattern not found: {pattern_id}"})
            return json.dumps({"message": f"Pattern {pattern_id} deactivated"})
        except Exception as e:
            logger.exception("Failed to deactivate pattern")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def list_resumable_investigations() -> str:
        store = BinderStore(get_db_path())
        try:
            resumable = await store.list_resumable_investigations()
            return json.dumps(resumable, default=_json_default, indent=2)
        except Exception as e:
            logger.exception("Failed to list resumable investigations")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def resume_investigation(investigation_id: str, ctx: Context | None = None) -> str:
        import asyncio

        client = await _get_agent_client()
        if client:
            try:
                result = await client.resume_investigation(investigation_id)
                return json.dumps(result, default=_json_default, indent=2)
            except Exception as e:
                logger.warning("REST resume failed, trying direct: %s", e)
        try:
            coordinator = await get_coordinator()
            phase_names = [
                "Prior Knowledge Retrieval",
                "Hypothesis Generation",
                "Evidence Seeking",
                "Causal Chain Construction",
                "Adversarial Review",
                "Insufficiency Check",
                "Synthesis",
                "Pattern Learning",
            ]

            async def _safe_progress(coro: Any) -> None:
                try:
                    await coro
                except Exception:
                    pass

            from srcs.agent.callbacks import PhaseEvent

            def on_phase(event: PhaseEvent) -> None:
                if ctx:
                    phase_name = phase_names[event.phase] if event.phase < len(phase_names) else f"Phase {event.phase}"
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(_safe_progress(ctx.report_progress(progress=event.phase + 1, total=8)))
                        loop.create_task(_safe_progress(ctx.info(f"Phase {event.phase}: {phase_name}")))
                    except RuntimeError:
                        pass

            if ctx:
                await _safe_progress(ctx.info(f"Resuming investigation {investigation_id}"))
            result = await coordinator.resume_investigation(investigation_id, callback=on_phase)
            confidence = 0.0
            if result.root_cause and result.root_cause.confidence:
                confidence = result.root_cause.confidence.calibrated
            return json.dumps(
                {
                    "investigation_id": investigation_id,
                    "outcome": result.outcome.value if result.outcome else "UNKNOWN",
                    "confidence": confidence,
                },
                default=_json_default,
                indent=2,
            )
        except ValueError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            logger.exception("Failed to resume investigation")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def validate_binder(binder_id: str) -> str:
        store = BinderStore(get_db_path())
        try:
            binder = await store.load_binder(binder_id)
            if not binder:
                return json.dumps({"error": f"Binder not found: {binder_id}"})
            try:
                await store.validate_references(binder_id)
                return json.dumps({"binder_id": binder_id, "valid": True, "errors": []}, indent=2)
            except ValueError as e:
                error_lines = str(e).split("\n")
                errors = [line.strip().lstrip("- ") for line in error_lines[1:] if line.strip().startswith("-")]
                return json.dumps({"binder_id": binder_id, "valid": False, "errors": errors}, indent=2)
        except Exception as e:
            logger.exception("Failed to validate binder")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def parse_logs(content: str, error_line: int | None = None, context_lines: int = 60) -> str:
        from srcs.models.log_parser import extract_error_and_context, parse_log_content

        try:
            logs = parse_log_content(content)
            if not logs:
                return json.dumps({"error": "No parseable log entries found in content"})
            error, context = extract_error_and_context(logs, error_line, context_lines)

            def _log_to_dict(log: Any) -> dict:
                return {
                    "timestamp": log.timestamp,
                    "level": log.level,
                    "component": log.component,
                    "function": log.function,
                    "message": log.message,
                    "raw_line": log.raw_line,
                    "line": log.line,
                }

            return json.dumps(
                {
                    "trigger_error": _log_to_dict(error),
                    "context_logs": [_log_to_dict(lg) for lg in context],
                    "total_logs_parsed": len(logs),
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to parse logs")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def create_log_from_message(message: str) -> str:
        from srcs.models.log_parser import create_log_from_message as _create_log

        try:
            log = _create_log(message)
            return json.dumps(
                {
                    "timestamp": log.timestamp,
                    "level": log.level,
                    "component": log.component,
                    "function": log.function,
                    "message": log.message,
                    "raw_line": log.raw_line,
                    "line": log.line,
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to create log from message")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_source_status() -> str:
        import asyncio
        from srcs.config import load_source_config
        from srcs.source import RepositoryManager

        try:
            source_config = load_source_config()
            if source_config is None:
                return json.dumps({"error": "No source configuration found in config.yaml"})
            manager = RepositoryManager(source_config)
            repositories = []
            for repo_config in source_config.repositories:
                repo_name = repo_config.get_repo_name()
                repo_path = manager.get_repo_path(repo_config)
                if repo_path.exists() and (repo_path / ".git").exists():
                    status = await asyncio.to_thread(manager.get_repo_status, repo_path)
                    if status:
                        repositories.append(
                            {
                                "name": repo_name,
                                "status": "cloned",
                                "path": str(status.path),
                                "branch": status.branch,
                                "commit": status.commit,
                                "commit_date": status.commit_date,
                                "is_dirty": status.is_dirty,
                            }
                        )
                    else:
                        repositories.append({"name": repo_name, "status": "unknown"})
                else:
                    repositories.append({"name": repo_name, "status": "not_cloned", "branch": repo_config.branch})
            return json.dumps(
                {"repos_path": str(source_config.get_repos_path()), "repositories": repositories},
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get source status")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def sync_sources() -> str:
        import asyncio
        from srcs.config import load_source_config
        from srcs.source import RepositoryManager

        try:
            source_config = load_source_config()
            if source_config is None:
                return json.dumps({"error": "No source configuration found in config.yaml"})
            if not source_config.has_repositories():
                return json.dumps({"results": [], "success_count": 0, "failure_count": 0}, indent=2)
            manager = RepositoryManager(source_config)
            sync_results = await asyncio.to_thread(manager.sync_all)
            results = []
            success_count = 0
            failure_count = 0
            for r in sync_results:
                results.append(
                    {
                        "repo_name": r.repo_name,
                        "success": r.success,
                        "action": r.action,
                        "message": r.message,
                        "path": str(r.path) if r.path else None,
                    }
                )
                if r.success:
                    success_count += 1
                else:
                    failure_count += 1
            return json.dumps(
                {"results": results, "success_count": success_count, "failure_count": failure_count},
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to sync sources")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def init_knowledge_base(skip_source: bool = False, skip_ollama_check: bool = False) -> str:
        import asyncio
        import yaml

        try:
            config_path = Path("config.yaml")
            if not config_path.exists():
                return json.dumps({"error": "config.yaml not found"})
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
            storage_cfg = config_data.get("storage", {})
            data_dir = Path(storage_cfg.get("sqlite_path", "./data/knowledge.db")).parent
            steps = []
            all_success = True
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                (data_dir / "chroma").mkdir(exist_ok=True)
                steps.append({"step": "create_directories", "success": True, "message": f"Created {data_dir}"})
            except Exception as e:
                steps.append({"step": "create_directories", "success": False, "message": str(e)})
                all_success = False
            try:
                from srcs.knowledge.sqlite_store import SQLiteStore

                db_path = data_dir / "knowledge.db"
                store = SQLiteStore(db_path)
                await store._ensure_initialized()
                steps.append(
                    {"step": "init_database", "success": True, "message": f"SQLite schema initialized at {db_path}"}
                )
            except Exception as e:
                steps.append({"step": "init_database", "success": False, "message": str(e)})
                all_success = False
            if not skip_ollama_check:
                llm_config = config_data.get("llm", {})
                provider = llm_config.get("provider", "ollama")
                if provider == "ollama":
                    steps.append(
                        {"step": "check_ollama", "success": True, "message": "Ollama check: use admin API for details"}
                    )
                else:
                    steps.append(
                        {
                            "step": "check_ollama",
                            "success": True,
                            "message": f"Provider is '{provider}', Ollama check not needed",
                        }
                    )
            else:
                steps.append({"step": "check_ollama", "success": True, "message": "Skipped (skip_ollama_check=true)"})
            if not skip_source:
                from srcs.config import load_source_config
                from srcs.source import RepositoryManager

                source_config = load_source_config()
                if source_config and source_config.has_repositories():
                    try:
                        manager = RepositoryManager(source_config)
                        sync_results = await asyncio.to_thread(manager.sync_all)
                        synced = sum((1 for r in sync_results if r.success))
                        failed = sum((1 for r in sync_results if not r.success))
                        msg = f"{synced} repos synced"
                        if failed:
                            msg += f", {failed} failed"
                            all_success = False
                        steps.append({"step": "sync_source", "success": failed == 0, "message": msg})
                    except Exception as e:
                        steps.append({"step": "sync_source", "success": False, "message": str(e)})
                        all_success = False
                else:
                    steps.append(
                        {"step": "sync_source", "success": True, "message": "No source repositories configured"}
                    )
            else:
                steps.append({"step": "sync_source", "success": True, "message": "Skipped (skip_source=true)"})
            return json.dumps({"success": all_success, "steps": steps}, default=_json_default, indent=2)
        except Exception as e:
            logger.exception("Failed to initialize knowledge base")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_query_effectiveness(error_type: str | None = None, min_samples: int = 5) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner

        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            query_types = await meta_learner.get_best_query_types(error_type, min_samples)
            if not query_types:
                return json.dumps({"query_types": [], "total_queries": 0, "overall_usefulness_rate": 0.0}, indent=2)
            stats = [
                {
                    "query_type": q["query_type"],
                    "times_used": q["times_used"],
                    "times_useful": int(q["usefulness_rate"] * q["times_used"]),
                    "usefulness_rate": q["usefulness_rate"],
                    "avg_evidence_strength": q["avg_evidence_strength"],
                    "avg_result_count": q["avg_result_count"],
                }
                for q in query_types
            ]
            total_queries = sum((s["times_used"] for s in stats))
            total_useful = sum((s["times_useful"] for s in stats))
            overall_rate = total_useful / total_queries if total_queries > 0 else 0.0
            return json.dumps(
                {"query_types": stats, "total_queries": total_queries, "overall_usefulness_rate": overall_rate},
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get query effectiveness")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_quality_metrics(period: str = "week") -> str:
        import aiosqlite
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner

        try:
            from datetime import timedelta

            config = StorageConfig()
            end_date = datetime.now()
            if period == "day":
                start_date = end_date - timedelta(days=1)
            elif period == "month":
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date - timedelta(weeks=1)
            async with aiosqlite.connect(config.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN outcome IN ('CONFIDENT', 'PROBABLE')
                            THEN 1 ELSE 0 END) as successful,
                        AVG(CASE
                            WHEN hypotheses_json IS NOT NULL
                            THEN json_extract(
                                hypotheses_json, '$[0].score')
                            ELSE NULL
                        END) as avg_confidence
                    FROM investigations
                    WHERE timestamp >= ?
                    """,
                    (start_date.isoformat(),),
                ) as cursor:
                    inv_row = await cursor.fetchone()
                total = inv_row["total"] or 0 if inv_row else 0
                successful = inv_row["successful"] or 0 if inv_row else 0
                avg_confidence = inv_row["avg_confidence"] or 0.0 if inv_row else 0.0
                async with conn.execute(
                    """
                    SELECT
                        COUNT(*) as feedback_count,
                        SUM(CASE WHEN was_correct = 1
                            THEN 1 ELSE 0 END) as correct_count
                    FROM investigation_feedback
                    WHERE submitted_at >= ?
                    """,
                    (start_date.isoformat(),),
                ) as cursor:
                    fb_row = await cursor.fetchone()
                feedback_count = fb_row["feedback_count"] or 0 if fb_row else 0
                correct_count = fb_row["correct_count"] or 0 if fb_row else 0
                accuracy = correct_count / feedback_count if feedback_count > 0 else None
            meta_learner = MetaLearner(config.sqlite_path)
            strategies = await meta_learner.get_best_strategies(min_samples=3)
            query_types = await meta_learner.get_best_query_types(min_samples=3)
            success_rate = total and successful / total or 0.0
            top_strategies = [
                {
                    "strategy": s["strategy"],
                    "times_used": s["times_used"],
                    "times_correct": int(s["success_rate"] * s["times_used"]),
                    "success_rate": s["success_rate"],
                    "avg_confidence": s["avg_confidence"],
                    "avg_rank": s["avg_rank"],
                }
                for s in strategies[:5]
            ]
            top_query_types = [
                {
                    "query_type": q["query_type"],
                    "times_used": q["times_used"],
                    "times_useful": int(q["usefulness_rate"] * q["times_used"]),
                    "usefulness_rate": q["usefulness_rate"],
                    "avg_evidence_strength": q["avg_evidence_strength"],
                    "avg_result_count": q["avg_result_count"],
                }
                for q in query_types[:5]
            ]
            return json.dumps(
                {
                    "period": period,
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_investigations": total,
                    "successful_investigations": successful,
                    "success_rate": success_rate,
                    "avg_confidence": avg_confidence,
                    "feedback_count": feedback_count,
                    "accuracy_from_feedback": accuracy,
                    "top_strategies": top_strategies,
                    "top_query_types": top_query_types,
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get quality metrics")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def summarize_function(name: str, file_filter: str | None = None) -> str:
        try:
            client = await _get_agent_client()
            if client and _client_session_id:
                result = await client.summarize_function(_client_session_id, name, file_filter=file_filter)
                return json.dumps(result, default=_json_default, indent=2)
            from srcs.config import load_config
            from srcs.extraction.indexer import CodeIndex, CodeIndexConfig
            from srcs.extraction.summarizer import FunctionSummarizer
            from srcs.llm import LLMConfig, create_llm_provider
            from srcs.source import SourceConfig

            config = load_config()
            source_config = SourceConfig.from_config(config)
            source_roots = []
            if source_config and source_config.has_repositories():
                from srcs.source import RepositoryManager

                manager = RepositoryManager(source_config)
                source_roots = manager.get_existing_repo_paths()
            if not source_roots:
                return json.dumps(
                    {"error": "No source repositories available. Run init_knowledge_base with source sync first."}
                )
            index_path = Path(os.environ.get("ARTDAQ_DATA_DIR", "./data")) / "code_index.db"
            idx_config = CodeIndexConfig(source_roots=source_roots, index_path=str(index_path))
            code_index = CodeIndex(idx_config)
            functions = code_index.find_function(name, file_filter=file_filter)
            if not functions:
                return json.dumps({"error": f"Function '{name}' not found", "functions": [], "total": 0})
            func = functions[0]
            source = ""
            try:
                func_path = Path(func.file_path)
                if func_path.exists() and func.start_line and func.end_line:
                    lines = func_path.read_text().splitlines()
                    source = "\n".join(lines[func.start_line - 1 : func.end_line])
            except Exception as e:
                logger.warning("Failed to read source for %s: %s", name, e)
            if not source:
                return json.dumps(
                    {
                        "name": func.name,
                        "file_path": str(func.file_path),
                        "summary": f"Function {name} (source unavailable)",
                    }
                )
            ext = Path(func.file_path).suffix.lower()
            lang_map = {".py": "python", ".cpp": "cpp", ".cc": "cpp", ".c": "c", ".h": "cpp", ".hpp": "cpp"}
            language = lang_map.get(ext, "cpp")
            llm_config = LLMConfig.from_config(config)
            llm = create_llm_provider(llm_config)
            summarizer = FunctionSummarizer(llm)
            summary = await summarizer.summarize_function(source, name, str(func.file_path), language)
            return json.dumps(
                {
                    "name": func.name,
                    "file_path": str(func.file_path),
                    "start_line": func.start_line,
                    "end_line": func.end_line,
                    "signature": func.signature,
                    "class_name": func.class_name,
                    "summary": summary,
                },
                default=_json_default,
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to summarize function")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_strategy_weights(error_type: str | None = None) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner

        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            weights = await meta_learner.suggest_strategy_weights(error_type)
            return json.dumps({"weights": weights, "error_type": error_type}, indent=2)
        except Exception as e:
            logger.exception("Failed to get strategy weights")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_query_priority(error_type: str | None = None) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner

        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            priority = await meta_learner.suggest_query_priority(error_type)
            return json.dumps({"priority": priority, "error_type": error_type}, indent=2)
        except Exception as e:
            logger.exception("Failed to get query priority")
            return json.dumps({"error": str(e)}, indent=2)

    @mcp.tool()
    async def get_strategy_recommendations(error_type: str | None = None) -> str:
        from srcs.knowledge import StorageConfig
        from srcs.knowledge.learning import MetaLearner

        try:
            config = StorageConfig()
            meta_learner = MetaLearner(config.sqlite_path)
            weights = await meta_learner.suggest_strategy_weights(error_type)
            priority = await meta_learner.suggest_query_priority(error_type)
            strategies = await meta_learner.get_best_strategies(error_type, min_samples=3)
            stats = await meta_learner.get_meta_learning_statistics()
            top_strategies = [
                {
                    "strategy": s["strategy"],
                    "times_used": s["times_used"],
                    "times_correct": int(s["success_rate"] * s["times_used"]),
                    "success_rate": s["success_rate"],
                    "avg_confidence": s["avg_confidence"],
                    "avg_rank": s["avg_rank"],
                }
                for s in strategies[:10]
            ]
            return json.dumps(
                {
                    "weights": weights,
                    "query_priority": priority,
                    "top_strategies": top_strategies,
                    "stats": stats,
                    "error_type": error_type,
                },
                indent=2,
            )
        except Exception as e:
            logger.exception("Failed to get strategy recommendations")
            return json.dumps({"error": str(e)}, indent=2)

    return mcp


def run_mcp_server(transport: str = "stdio", port: int = 8001) -> None:
    mcp = create_mcp_server(port=port)
    if transport == "sse":
        mcp.run(transport="sse")
    elif transport == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
