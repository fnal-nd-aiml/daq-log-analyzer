import json
from pathlib import Path
from typing import Any
import httpx
from tools.mcptester.mcptester.config import TesterConfig
from tools.mcptester.mcptester.fixture_db import fixture_environment
_TOOL_ROUTES: dict[str, tuple[str, str, list[str]]] = {'list_binders': ('GET', '/api/v1/binders', []), 'get_binder': ('GET', '/api/v1/binders/{binder_id}', ['binder_id']), 'get_binder_summary': ('GET', '/api/v1/binders/{binder_id}/summary', ['binder_id']), 'list_resumable_investigations': ('GET', '/api/v1/binders/resumable', []), 'validate_binder': ('GET', '/api/v1/binders/{binder_id}/validate', ['binder_id']), 'search_artifacts': ('GET', '/api/v1/binders/{binder_id}/artifacts', ['binder_id']), 'get_artifact': ('GET', '/api/v1/binders/{binder_id}/artifacts/{artifact_id}', ['binder_id', 'artifact_id']), 'get_artifact_history': ('GET', '/api/v1/binders/{binder_id}/artifacts/{artifact_id}/history', ['binder_id', 'artifact_id']), 'search_artifact_content': ('POST', '/api/v1/binders/{binder_id}/artifacts/search', ['binder_id']), 'search_audit_log': ('GET', '/api/v1/binders/{binder_id}/audit', ['binder_id']), 'get_artifact_audit_trail': ('GET', '/api/v1/binders/{binder_id}/artifacts/{artifact_id}/audit', ['binder_id', 'artifact_id']), 'get_audit_summary': ('GET', '/api/v1/binders/{binder_id}/audit/summary', ['binder_id']), 'get_hypotheses': ('GET', '/api/v1/binders/{binder_id}/hypotheses', ['binder_id']), 'get_evidence': ('GET', '/api/v1/binders/{binder_id}/evidence', ['binder_id']), 'get_causal_chains': ('GET', '/api/v1/binders/{binder_id}/chains', ['binder_id']), 'get_challenges': ('GET', '/api/v1/binders/{binder_id}/challenges', ['binder_id']), 'get_llm_requests': ('GET', '/api/v1/binders/{binder_id}/llm/requests', ['binder_id']), 'get_llm_responses': ('GET', '/api/v1/binders/{binder_id}/llm/responses', ['binder_id']), 'get_llm_exchanges': ('GET', '/api/v1/binders/{binder_id}/llm/exchanges', ['binder_id']), 'get_llm_statistics': ('GET', '/api/v1/binders/{binder_id}/llm/statistics', ['binder_id']), 'get_investigation_state': ('GET', '/api/v1/binders/{binder_id}/state', ['binder_id']), 'get_phase_states': ('GET', '/api/v1/binders/{binder_id}/phases', ['binder_id']), 'list_investigations_with_state': ('GET', '/api/v1/binders/investigations', []), 'find_similar_investigations': ('POST', '/api/v1/binders/similar', []), 'list_patterns': ('GET', '/api/v1/patterns', []), 'get_pattern': ('GET', '/api/v1/patterns/{pattern_id}', ['pattern_id']), 'get_pattern_statistics': ('GET', '/api/v1/patterns/stats', []), 'get_pattern_root_causes': ('GET', '/api/v1/patterns/{pattern_id}/root-causes', ['pattern_id']), 'match_pattern': ('POST', '/api/v1/patterns/match', []), 'get_pattern_accuracy_trend': ('GET', '/api/v1/patterns/{pattern_id}/accuracy-trend', ['pattern_id']), 'list_calibrations': ('GET', '/api/v1/calibration', []), 'get_calibration': ('GET', '/api/v1/calibration', []), 'get_calibration_trend': ('GET', '/api/v1/calibration/trend', []), 'get_calibration_summary': ('GET', '/api/v1/calibration/summary', []), 'export_calibration': ('GET', '/api/v1/calibration/export', []), 'list_investigations': ('GET', '/api/v1/investigations', []), 'get_investigation': ('GET', '/api/v1/investigations/{investigation_id}', ['investigation_id']), 'get_investigation_quality': ('GET', '/api/v1/investigations/{investigation_id}/quality', ['investigation_id']), 'parse_logs': ('POST', '/api/v1/admin/logs/parse', []), 'create_log_from_message': ('POST', '/api/v1/admin/logs/from-message', []), 'get_source_status': ('GET', '/api/v1/admin/source/status', []), 'get_query_effectiveness': ('GET', '/api/v1/queries/effectiveness', []), 'get_quality_metrics': ('GET', '/api/v1/metrics/{period}', ['period'])}
_PARAM_REMAP: dict[str, dict[str, str]] = {'get_binder_summary': {'investigation_id': 'binder_id'}}
_EXCLUDED_TOOLS = {'investigate_error', 'analyze_message', 'submit_feedback', 'ask_experts', 'sync_sources', 'init_knowledge_base', 'record_calibration_snapshot', 'list_calibrations', 'get_calibration', 'get_calibration_summary', 'export_calibration'}
_RESPONSE_UNWRAP: dict[str, str] = {'list_binders': 'binders', 'search_artifacts': 'artifacts', 'get_artifact_history': 'artifacts', 'search_artifact_content': 'artifacts', 'get_hypotheses': 'artifacts', 'get_evidence': 'artifacts', 'get_causal_chains': 'artifacts', 'get_challenges': 'artifacts', 'get_llm_requests': 'artifacts', 'get_llm_responses': 'artifacts', 'get_phase_states': 'artifacts', 'get_investigation_state': 'artifact'}
_FIELD_RENAMES: dict[str, dict[str, str]] = {'list_binders': {'binder_id': 'id'}, 'get_phase_states': {'phase': 'phase_number'}}

def _normalize_response(tool_name: str, data: Any) -> Any:
    renames = _FIELD_RENAMES.get(tool_name)
    if not renames:
        return data
    if isinstance(data, list):
        return [_rename_fields(item, renames) for item in data]
    elif isinstance(data, dict):
        return _rename_fields(data, renames)
    return data

def _rename_fields(obj: dict, renames: dict[str, str]) -> dict:
    result = {}
    for k, v in obj.items():
        result[renames.get(k, k)] = v
    return result

class RESTTestRunner:

    def __init__(self, config: TesterConfig) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._fixture_ctx: Any = None
        self._fixture_dir: Path | None = None

    async def connect(self) -> None:
        self._fixture_ctx = fixture_environment()
        self._fixture_dir = self._fixture_ctx.__enter__()
        from srcs.api.app import create_app
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(transport=transport, base_url='http://testserver')

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._fixture_ctx:
            self._fixture_ctx.__exit__(None, None, None)
            self._fixture_ctx = None

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name in _EXCLUDED_TOOLS:
            return '__SKIPPED__'
        if tool_name not in _TOOL_ROUTES:
            return json.dumps({'error': f'No REST mapping for tool: {tool_name}'})
        method, path_template, path_param_names = _TOOL_ROUTES[tool_name]
        remaining = dict(params)
        if tool_name in _PARAM_REMAP:
            for mcp_name, rest_name in _PARAM_REMAP[tool_name].items():
                if mcp_name in remaining:
                    remaining[rest_name] = remaining.pop(mcp_name)
        path_values = {}
        for name in path_param_names:
            if name in remaining:
                path_values[name] = remaining.pop(name)
        url = path_template.format(**path_values) if path_values else path_template
        try:
            if method == 'GET':
                query = {k: _serialize_param(v) for k, v in remaining.items()}
                resp = await self._client.get(url, params=query)
            else:
                resp = await self._client.post(url, json=remaining)
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    if isinstance(body, dict) and 'detail' in body:
                        return json.dumps({'error': body['detail']})
                    return json.dumps(body)
                except Exception:
                    return json.dumps({'error': f'HTTP {resp.status_code}: {resp.text[:200]}'})
            if tool_name in _RESPONSE_UNWRAP:
                try:
                    body = resp.json()
                    key = _RESPONSE_UNWRAP[tool_name]
                    if isinstance(body, dict) and key in body:
                        data = _normalize_response(tool_name, body[key])
                        return json.dumps(data, default=str)
                except Exception:
                    pass
            elif tool_name in _FIELD_RENAMES:
                try:
                    body = resp.json()
                    data = _normalize_response(tool_name, body)
                    return json.dumps(data, default=str)
                except Exception:
                    pass
            return resp.text
        except Exception as e:
            return json.dumps({'error': str(e)})

    async def list_available_tools(self) -> list[str]:
        return sorted((t for t in _TOOL_ROUTES if t not in _EXCLUDED_TOOLS))

    def reset(self) -> None:
        pass

    async def __aenter__(self) -> 'RESTTestRunner':
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

def _serialize_param(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)