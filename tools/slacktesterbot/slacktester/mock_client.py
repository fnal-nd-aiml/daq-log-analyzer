from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

@dataclass
class MockMessage:
    text: str | None = None
    blocks: list[dict[str, Any]] | None = None
    thread_ts: str | None = None
    channel: str | None = None

@dataclass
class MockSlackClient:
    messages: list[MockMessage] = field(default_factory=list)
    _message_counter: int = 0

    def reset(self) -> None:
        self.messages = []
        self._message_counter = 0

    async def say(self, text: str | None=None, blocks: list[dict[str, Any]] | None=None, thread_ts: str | None=None, channel: str | None=None, **kwargs: Any) -> dict[str, Any]:
        self._message_counter += 1
        msg = MockMessage(text=text, blocks=blocks, thread_ts=thread_ts, channel=channel)
        self.messages.append(msg)
        return {'ok': True, 'ts': f'mock.{self._message_counter}'}

    def create_say_mock(self) -> AsyncMock:
        mock = AsyncMock(side_effect=self.say)
        return mock

    @property
    def last_message(self) -> MockMessage | None:
        return self.messages[-1] if self.messages else None

    def get_all_text(self) -> list[str]:
        return [m.text for m in self.messages if m.text]

    def get_all_blocks(self) -> list[list[dict[str, Any]]]:
        return [m.blocks for m in self.messages if m.blocks]

@dataclass
class MockFile:
    name: str
    url_private: str = 'https://files.slack.com/mock/file'
    mimetype: str = 'text/plain'
    size: int = 1024

@dataclass
class MockEvent:
    text: str
    user: str = 'U_TEST_USER'
    channel: str = 'C_TEST_CHANNEL'
    ts: str = '1234567890.123456'
    files: list[MockFile] | None = None
    channel_type: str = 'channel'

    def to_dict(self) -> dict[str, Any]:
        event: dict[str, Any] = {'text': self.text, 'user': self.user, 'channel': self.channel, 'ts': self.ts, 'channel_type': self.channel_type}
        if self.files:
            event['files'] = [{'name': f.name, 'url_private': f.url_private, 'mimetype': f.mimetype, 'size': f.size} for f in self.files]
        return event