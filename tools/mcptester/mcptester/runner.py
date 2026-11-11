import json
from dataclasses import dataclass
from typing import Any
from tools.mcptester.mcptester.config import TesterConfig

@dataclass
class ToolResult:
    result: str | None = None
    error: str | None = None
    duration_ms: int = 0

class MockTestRunner:

    def __init__(self, config: TesterConfig) -> None:
        self.config = config
        self._tools: dict[str, Any] = {}
        self._mcp_server: Any = None
        self._fixture_ctx: Any = None

    async def _ensure_server(self) -> None:
        if self._mcp_server is None:
            if self.config.fixture.enabled and self._fixture_ctx is None:
                from tools.mcptester.mcptester.fixture_db import fixture_environment
                self._fixture_ctx = fixture_environment()
                self._fixture_ctx.__enter__()
            from srcs.mcp.server import create_mcp_server
            self._mcp_server = create_mcp_server()

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        await self._ensure_server()
        tool_func = self._get_tool_function(tool_name)
        if tool_func is None:
            raise ValueError(f'Tool not found: {tool_name}')
        if self.config.mock.simulate_delays:
            import asyncio
            await asyncio.sleep(0.1)
        try:
            result = await tool_func(**params)
            return result
        except Exception as e:
            return json.dumps({'error': str(e)})

    def _get_tool_function(self, tool_name: str) -> Any:
        if tool_name in self._tools:
            return self._tools[tool_name]
        if hasattr(self._mcp_server, '_tool_manager'):
            manager = self._mcp_server._tool_manager
            if hasattr(manager, '_tools'):
                tools = manager._tools
                if tool_name in tools:
                    tool = tools[tool_name]
                    if hasattr(tool, 'fn'):
                        self._tools[tool_name] = tool.fn
                        return tool.fn
        from srcs.mcp import server as mcp_server
        if hasattr(mcp_server, tool_name):
            func = getattr(mcp_server, tool_name)
            self._tools[tool_name] = func
            return func
        return None

    async def list_available_tools(self) -> list[str]:
        await self._ensure_server()
        tools = []
        if hasattr(self._mcp_server, '_tool_manager'):
            manager = self._mcp_server._tool_manager
            if hasattr(manager, '_tools'):
                tools = list(manager._tools.keys())
        return sorted(tools)

    def reset(self) -> None:
        self._tools.clear()
        if self._fixture_ctx is not None:
            self._fixture_ctx.__exit__(None, None, None)
            self._fixture_ctx = None

class MockCommandRunner(MockTestRunner):

    def __init__(self, config: TesterConfig) -> None:
        super().__init__(config)
        self._mock_mode = config.mock.mock_llm_responses

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        if self._mock_mode and tool_name in self._get_mock_tools():
            return await self._call_mock_tool(tool_name, params)
        return await super().call_tool(tool_name, params)

    def _get_mock_tools(self) -> set[str]:
        return {'investigate_error', 'analyze_message', 'submit_feedback', 'ask_experts'}

    async def _call_mock_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        if tool_name == 'investigate_error':
            return await self._mock_investigate(params)
        elif tool_name == 'analyze_message':
            return await self._mock_investigate(params)
        elif tool_name == 'submit_feedback':
            return await self._mock_feedback(params)
        elif tool_name == 'ask_experts':
            return await self._mock_ask_experts(params)
        return json.dumps({'error': f'No mock for tool: {tool_name}'})

    async def _mock_investigate(self, params: dict[str, Any]) -> str:
        from tools.mcptester.mcptester.fixtures import SAMPLE_INVESTIGATION_RESULT
        error_message = params.get('error_message') or params.get('message', '')
        result = SAMPLE_INVESTIGATION_RESULT.copy()
        result['investigation_id'] = f'inv_{hash(error_message) % 100000:05d}'
        result['trigger_error']['message'] = error_message
        return json.dumps(result, indent=2)

    async def _mock_feedback(self, params: dict[str, Any]) -> str:
        investigation_id = params.get('investigation_id', '')
        correct = params.get('correct', True)
        actual_cause = params.get('actual_cause')
        if investigation_id == 'nonexistent' or investigation_id.startswith('invalid'):
            return json.dumps({'success': False, 'error': f'Investigation {investigation_id} not found'}, indent=2)
        return json.dumps({'success': True, 'message': 'Feedback recorded successfully', 'stated_confidence': 0.75, 'correct': correct, 'actual_cause': actual_cause, 'patterns_updated': ['pattern001'] if correct else [], 'patterns_created': [] if correct else ['pattern_new001']}, indent=2)

    async def _mock_ask_experts(self, params: dict[str, Any]) -> str:
        from tools.mcptester.mcptester.fixtures import SAMPLE_PANEL_RESPONSE
        question = params.get('question', '')
        result = SAMPLE_PANEL_RESPONSE.copy()
        result['question_id'] = f'q_{hash(question) % 100000:05d}'
        if 'boardreader' in question.lower():
            result['answer'] = 'A BoardReader is a component in the artdaq framework responsible for reading data from hardware boards and producing data fragments.'
        elif 'timeout' in question.lower():
            result['answer'] = 'Timeouts in artdaq typically occur due to network latency, buffer overflow, or hardware communication issues.'
        return json.dumps(result, indent=2)