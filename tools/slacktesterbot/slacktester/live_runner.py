import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from slack_sdk.web.async_client import AsyncWebClient
from tools.slacktesterbot.slacktester.config import TesterConfig

@dataclass
class LiveCommandResult:
    command_sent: str = ''
    bot_responses: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0
    timed_out: bool = False

class LiveTestRunner:

    def __init__(self, config: TesterConfig, client: AsyncWebClient, channel_id: str) -> None:
        self.config = config
        self.client = client
        self.channel_id = channel_id
        self.target_bot_id = config.slack.target_bot_id
        self.response_timeout = 30
        self._last_ts: str | None = None

    async def send_command(self, command: str, wait_for_response: bool=True, response_timeout: float | None=None) -> LiveCommandResult:
        start_time = time.time()
        result = LiveCommandResult(command_sent=command)
        timeout = response_timeout or self.response_timeout
        try:
            if self.target_bot_id:
                message = f'<@{self.target_bot_id}> {command}'
            else:
                message = command
            response = await self.client.chat_postMessage(channel=self.channel_id, text=message)
            if not response.get('ok'):
                result.error = f"Failed to send message: {response.get('error')}"
                return result
            message_ts = response.get('ts')
            self._last_ts = message_ts
            if not wait_for_response:
                result.duration_ms = int((time.time() - start_time) * 1000)
                return result
            result.bot_responses = await self._wait_for_responses(message_ts=message_ts, timeout=timeout)
            if not result.bot_responses:
                result.timed_out = True
        except Exception as e:
            result.error = str(e)
        finally:
            result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    async def send_command_with_files(self, command: str, file_paths: list[Path], wait_for_response: bool=True, response_timeout: float | None=None) -> LiveCommandResult:
        start_time = time.time()
        result = LiveCommandResult(command_sent=command)
        timeout = response_timeout or self.response_timeout
        try:
            if self.target_bot_id:
                initial_comment = f'<@{self.target_bot_id}> {command}'
            else:
                initial_comment = command
            auth = await self.client.auth_test()
            our_user_id = auth.get('user_id')
            pre_upload_ts = f'{time.time():.6f}'
            file_uploads = [{'file': str(path), 'filename': path.name} for path in file_paths]
            await self.client.files_upload_v2(file_uploads=file_uploads, channel=self.channel_id, initial_comment=initial_comment)
            self._last_ts = pre_upload_ts
            if not wait_for_response:
                result.duration_ms = int((time.time() - start_time) * 1000)
                return result
            result.bot_responses = await self._wait_for_responses(message_ts=pre_upload_ts, timeout=timeout, skip_user_id=our_user_id, expected_responses=len(file_paths))
            if not result.bot_responses:
                result.timed_out = True
        except Exception as e:
            result.error = str(e)
        finally:
            result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    async def _wait_for_responses(self, message_ts: str, timeout: float, skip_user_id: str | None=None, expected_responses: int=1) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        start_time = time.time()
        last_check_ts = message_ts
        while time.time() - start_time < timeout:
            await asyncio.sleep(1)
            try:
                history = await self.client.conversations_history(channel=self.channel_id, oldest=message_ts, limit=20)
                if not history.get('ok'):
                    continue
                messages = history.get('messages', [])
                for msg in messages:
                    msg_ts = msg.get('ts', '')
                    if msg_ts == message_ts:
                        continue
                    if skip_user_id and msg.get('user') == skip_user_id:
                        continue
                    bot_id = msg.get('bot_id')
                    if bot_id and msg_ts > last_check_ts:
                        responses.append({'ts': msg_ts, 'text': msg.get('text', ''), 'blocks': msg.get('blocks', []), 'thread_ts': msg.get('thread_ts')})
                        last_check_ts = msg_ts
                try:
                    replies = await self.client.conversations_replies(channel=self.channel_id, ts=message_ts, limit=20)
                    if replies.get('ok'):
                        for msg in replies.get('messages', []):
                            msg_ts = msg.get('ts', '')
                            if msg_ts == message_ts:
                                continue
                            if skip_user_id and msg.get('user') == skip_user_id:
                                continue
                            bot_id = msg.get('bot_id')
                            if bot_id:
                                existing = [r for r in responses if r['ts'] == msg_ts]
                                if not existing:
                                    responses.append({'ts': msg_ts, 'text': msg.get('text', ''), 'blocks': msg.get('blocks', []), 'thread_ts': msg.get('thread_ts')})
                except Exception:
                    pass
                if responses and len(responses) >= expected_responses:
                    await asyncio.sleep(3)
                    break
            except Exception as e:
                print(f'Error polling for responses: {e}')
        return responses

    def _extract_text_from_blocks(self, blocks: list[dict[str, Any]]) -> str:
        texts = []
        for block in blocks:
            block_type = block.get('type', '')
            if block_type == 'section':
                text_obj = block.get('text', {})
                if isinstance(text_obj, dict):
                    texts.append(text_obj.get('text', ''))
                elif isinstance(text_obj, str):
                    texts.append(text_obj)
                for field in block.get('fields', []):
                    if isinstance(field, dict):
                        texts.append(field.get('text', ''))
            elif block_type == 'header':
                text_obj = block.get('text', {})
                if isinstance(text_obj, dict):
                    texts.append(text_obj.get('text', ''))
            elif block_type == 'context':
                for elem in block.get('elements', []):
                    if isinstance(elem, dict):
                        texts.append(elem.get('text', ''))
        return ' '.join(texts)

    def get_all_text(self, responses: list[dict[str, Any]]) -> str:
        all_texts = []
        for r in responses:
            text = r.get('text', '')
            if text:
                all_texts.append(text)
            blocks = r.get('blocks', [])
            if blocks:
                block_text = self._extract_text_from_blocks(blocks)
                if block_text:
                    all_texts.append(block_text)
        return ' '.join(all_texts)

    async def run_test(self, name: str, command: str, expected_contains: list[str] | None=None, expected_not_contains: list[str] | None=None, timeout: float=30) -> dict[str, Any]:
        result = await self.send_command(command, response_timeout=timeout)
        test_result = {'name': name, 'command': command, 'passed': False, 'duration_ms': result.duration_ms, 'error': result.error, 'timed_out': result.timed_out, 'response_count': len(result.bot_responses), 'responses': result.bot_responses}
        if result.error:
            return test_result
        if result.timed_out:
            test_result['error'] = 'Timed out waiting for bot response'
            return test_result
        if not result.bot_responses:
            test_result['error'] = 'No response from bot'
            return test_result
        all_text = self.get_all_text(result.bot_responses)
        if expected_contains:
            for expected in expected_contains:
                if expected.lower() not in all_text.lower():
                    test_result['error'] = f"Expected '{expected}' not found in response"
                    return test_result
        if expected_not_contains:
            for unexpected in expected_not_contains:
                if unexpected.lower() in all_text.lower():
                    test_result['error'] = f"Unexpected '{unexpected}' found in response"
                    return test_result
        test_result['passed'] = True
        return test_result