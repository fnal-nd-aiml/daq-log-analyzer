import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from tools.slacktesterbot.slacktester.config import TesterConfig
from tools.slacktesterbot.slacktester.mock_client import MockEvent, MockFile, MockSlackClient

@dataclass
class CommandResult:
    text: str | None = None
    blocks: list[dict[str, Any]] | None = None
    all_messages: list[dict[str, Any]] = field(default_factory=list)
    parse_result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = 0

class MockTestRunner:

    def __init__(self, config: TesterConfig) -> None:
        self.config = config
        self.mock_client = MockSlackClient()
        self._bot_user_id = 'U_BOT_USER'

    def reset(self) -> None:
        self.mock_client.reset()

    async def parse_command(self, text: str) -> dict[str, Any] | None:
        from srcs.slack.commands import parse_command
        result = parse_command(text, self._bot_user_id)
        if result is None:
            return None
        return {'command': result.command, 'args': result.args, 'options': result.options, 'raw_text': result.raw_text}

    async def parse_specific_command(self, command: str, text: str) -> dict[str, Any] | None:
        from srcs.slack.commands import ParsedCommand, parse_ask_command, parse_config_command, parse_feedback_command, parse_init_command, parse_investigate_command, parse_list_command, parse_message_command, parse_sync_source_command, parse_workbinder_command
        parsed_dict = await self.parse_command(text)
        if parsed_dict is None:
            return None
        cmd = ParsedCommand(command=parsed_dict['command'], args=parsed_dict['args'], options=parsed_dict['options'], raw_text=parsed_dict['raw_text'])
        parsers = {'investigate': lambda: parse_investigate_command(cmd), 'message': lambda: parse_message_command(cmd), 'feedback': lambda: parse_feedback_command(cmd), 'ask': lambda: parse_ask_command(cmd), 'list': lambda: parse_list_command(cmd), 'config': lambda: parse_config_command(cmd), 'workbinder': lambda: parse_workbinder_command(cmd), 'sync-source': lambda: parse_sync_source_command(cmd), 'init': lambda: parse_init_command(cmd)}
        if command not in parsers:
            return parsed_dict
        specific_result = parsers[command]()
        return specific_result

    async def get_help_text(self, command: str | None=None) -> str:
        from srcs.slack.commands import get_help_text
        return get_help_text(command)

    async def format_error(self, message: str) -> dict[str, Any]:
        from srcs.slack.formatter import format_error
        blocks = format_error(message)
        return {'blocks': blocks}

    async def format_success(self, message: str) -> dict[str, Any]:
        from srcs.slack.formatter import format_success
        blocks = format_success(message)
        return {'blocks': blocks}

    async def send_command(self, text: str, files: list[Path] | None=None) -> CommandResult:
        start_time = time.time()
        self.reset()
        result = CommandResult()
        try:
            parsed = await self.parse_command(text)
            result.parse_result = parsed
            if parsed is None:
                result.error = 'Failed to parse command'
                return result
            command = parsed['command']
            if command == 'help':
                cmd_arg = parsed['args'][0] if parsed['args'] else None
                help_text = await self.get_help_text(cmd_arg)
                result.text = help_text
                return result
            if command == 'version':
                from srcs import __version__
                result.text = f':information_source: Log Analyzer Slack Bot v{__version__}'
                return result
            specific = await self.parse_specific_command(command, text)
            result.parse_result = specific
        except Exception as e:
            result.error = str(e)
        finally:
            result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    async def test_config_store(self, channel_id: str='C_TEST') -> dict[str, Any]:
        from srcs.slack.config_store import ConfigStore
        temp_dir = Path(tempfile.mkdtemp())
        store = ConfigStore(data_dir=temp_dir, output_defaults=None)
        config = store.get_config(channel_id)
        initial = {'verbose': config.verbose, 'llm_logging': config.llm_logging, 'full_output': config.full_output}
        store.set_setting(channel_id, 'verbose', True)
        after_set = store.get_config(channel_id)
        formatted = store.format_config(channel_id)
        return {'initial': initial, 'after_set': {'verbose': after_set.verbose, 'llm_logging': after_set.llm_logging, 'full_output': after_set.full_output}, 'formatted': formatted}

    async def test_formatter(self, format_type: str, **kwargs: Any) -> dict[str, Any]:
        from srcs.slack import formatter
        formatters = {'error': lambda: formatter.format_error(kwargs.get('message', 'Test error')), 'success': lambda: formatter.format_success(kwargs.get('message', 'Test success')), 'investigation_list': lambda: formatter.format_investigation_list(kwargs.get('investigations', []), kwargs.get('limit', 10))}
        if format_type not in formatters:
            return {'error': f'Unknown formatter: {format_type}'}
        blocks = formatters[format_type]()
        return {'blocks': blocks}

    def create_mock_event(self, text: str, files: list[tuple[str, str]] | None=None) -> MockEvent:
        mock_files = None
        if files:
            mock_files = [MockFile(name=name, url_private=url) for name, url in files]
        return MockEvent(text=text, files=mock_files)