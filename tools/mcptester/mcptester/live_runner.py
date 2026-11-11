import json
from typing import Any
from mcp import ClientSession
from mcp.client.sse import sse_client
from tools.mcptester.mcptester.config import TesterConfig

class LiveTestRunner:

    def __init__(self, config: TesterConfig, server_url: str, timeout: int=30) -> None:
        self.config = config
        if not server_url.endswith('/sse'):
            server_url = server_url.rstrip('/') + '/sse'
        self.server_url = server_url
        self.timeout = timeout
        self._session: ClientSession | None = None
        self._streams: Any = None

    async def connect(self) -> None:
        if self._session is not None:
            return
        self._streams = sse_client(self.server_url, timeout=float(self.timeout))
        read_stream, write_stream = await self._streams.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

    async def disconnect(self) -> None:
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._streams is not None:
            await self._streams.__aexit__(None, None, None)
            self._streams = None

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        for attempt in range(2):
            if self._session is None:
                await self.connect()
            try:
                result = await self._session.call_tool(tool_name, params)
                if hasattr(result, 'content') and result.content:
                    texts = []
                    for block in result.content:
                        if hasattr(block, 'text'):
                            texts.append(block.text)
                    return '\n'.join(texts) if texts else '{}'
                return '{}'
            except Exception as e:
                error_msg = str(e)
                if 'closed' in error_msg.lower() or 'connection' in error_msg.lower():
                    await self.disconnect()
                    if attempt == 0:
                        continue
                return json.dumps({'error': error_msg})
        return json.dumps({'error': 'Failed after reconnection attempt'})

    async def list_available_tools(self) -> list[str]:
        if self._session is None:
            await self.connect()
        result = await self._session.list_tools()
        return sorted([tool.name for tool in result.tools])

    def reset(self) -> None:
        pass

    async def __aenter__(self) -> 'LiveTestRunner':
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()