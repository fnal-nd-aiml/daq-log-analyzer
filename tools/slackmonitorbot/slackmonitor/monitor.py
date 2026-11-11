import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from tools.slackmonitorbot.slackmonitor.formatter import format_message

class SlackMonitor:

    def __init__(self, bot_token: str, app_token: str, output_file: Path | None, status_file: Path, timeout: int | None=None, use_stdout: bool=False, channel: str | None=None, target_bot: str | None=None, announce_on_connect: bool=True):
        self.app = AsyncApp(token=bot_token)
        self.bot_token = bot_token
        self.app_token = app_token
        self.output_file = output_file
        self.status_file = status_file
        self.timeout = timeout
        self.use_stdout = use_stdout
        self.channel = channel
        self.target_bot = target_bot or 'the Slack bot'
        self.announce_on_connect = announce_on_connect
        self.message_count = 0
        self.started_at: datetime | None = None
        self.channel_id: str | None = None
        self._client: AsyncWebClient | None = None
        self._setup_handlers()

    def _setup_handlers(self) -> None:

        @self.app.event('message')
        async def handle_message(event: dict) -> None:
            self.message_count += 1
            self._update_status()
            await self._log_message(event)

        @self.app.event('app_mention')
        async def handle_mention(event: dict) -> None:
            pass

    async def _log_message(self, event: dict) -> None:
        formatted = format_message(event)
        if self.use_stdout:
            print(formatted, flush=True)
        elif self.output_file:
            with open(self.output_file, 'a') as f:
                f.write(formatted)

    def _update_status(self) -> None:
        if not self.started_at:
            return
        status = {'pid': os.getpid(), 'started_at': self.started_at.isoformat(), 'message_count': self.message_count, 'connected': True, 'channel': self.channel}
        self.status_file.write_text(json.dumps(status, indent=2))

    def _write_disconnected_status(self) -> None:
        if not self.started_at:
            return
        status = {'pid': os.getpid(), 'started_at': self.started_at.isoformat(), 'message_count': self.message_count, 'connected': False, 'channel': self.channel}
        self.status_file.write_text(json.dumps(status, indent=2))

    async def _get_channel_id(self, client: AsyncWebClient) -> str | None:
        if not self.channel:
            return None
        if self.channel.startswith('C'):
            return self.channel
        try:
            result = await client.conversations_list(types='public_channel,private_channel')
            channels: list[dict] = result.get('channels', [])
            for ch in channels:
                if ch.get('name') == self.channel:
                    channel_id: str | None = ch.get('id')
                    return channel_id
        except Exception as e:
            print(f'Warning: Could not look up channel: {e}', file=sys.stderr)
        return None

    async def _announce_connection(self, client: AsyncWebClient) -> None:
        if not self.announce_on_connect or not self.channel_id:
            return
        try:
            timeout_info = f' (timeout: {self.timeout}s)' if self.timeout else ''
            message = f':eyes: *Slack Monitor Bot* connected{timeout_info}\nMonitoring messages for `{self.target_bot}` in this channel.\n_Messages are being logged for debugging purposes._'
            await client.chat_postMessage(channel=self.channel_id, text=message)
            print(f'Announced connection in #{self.channel}', file=sys.stderr)
        except Exception as e:
            print(f'Warning: Could not announce connection: {e}', file=sys.stderr)

    async def _announce_disconnect(self) -> None:
        if not self._client or not self.channel_id:
            return
        try:
            message = f':wave: *Slack Monitor Bot* disconnecting.\n_Captured {self.message_count} messages._'
            await self._client.chat_postMessage(channel=self.channel_id, text=message)
            print(f'Announced disconnect in #{self.channel}', file=sys.stderr)
        except Exception as e:
            print(f'Warning: Could not announce disconnect: {e}', file=sys.stderr)

    async def start(self) -> None:
        if self.output_file:
            self.output_file.write_text('')
        self.started_at = datetime.now()
        self._update_status()
        print('Slack Monitor starting...', file=sys.stderr)
        if self.channel:
            print(f'Channel: #{self.channel}', file=sys.stderr)
        if self.output_file:
            print(f'Writing to: {self.output_file}', file=sys.stderr)
        else:
            print('Writing to: stdout', file=sys.stderr)
        if self.timeout:
            print(f'Timeout: {self.timeout} seconds', file=sys.stderr)
        handler = AsyncSocketModeHandler(self.app, self.app_token)
        self._client = AsyncWebClient(token=self.bot_token)
        if self.channel:
            self.channel_id = await self._get_channel_id(self._client)
            if self.channel_id:
                try:
                    await self._client.conversations_join(channel=self.channel_id)
                    print('Joined channel', file=sys.stderr)
                except Exception:
                    pass
                await self._announce_connection(self._client)
            else:
                print(f'Warning: Could not find channel #{self.channel}', file=sys.stderr)
        try:
            if self.timeout:
                try:
                    await asyncio.wait_for(handler.start_async(), timeout=self.timeout)
                except asyncio.TimeoutError:
                    print(f'\nTimeout reached ({self.timeout}s), stopping...', file=sys.stderr)
            else:
                await handler.start_async()
        finally:
            await self._announce_disconnect()
            self._write_disconnected_status()
            try:
                await handler.close_async()
            except Exception:
                pass