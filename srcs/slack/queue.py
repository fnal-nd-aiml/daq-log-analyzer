"""
File: queue.py
Purpose: Task queue for long-running Slack commands.
Category: Utility
Author: artdaq team
Depends: None
Exports: QueuedTask, TaskQueue
Complexity: Low | Lines: 51
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class QueuedTask:
    channel: str
    user: str
    command: str
    coro: Coroutine[Any, Any, None]
    ack_message_ts: str | None = None


class TaskQueue:

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth
        self._queue: asyncio.Queue[QueuedTask] = asyncio.Queue(maxsize=max_depth)
        self._worker_task: asyncio.Task[None] | None = None

    def is_full(self) -> bool:
        return self._queue.qsize() >= self.max_depth

    def queue_size(self) -> int:
        return self._queue.qsize()

    async def submit(self, task: QueuedTask) -> bool:
        if self.is_full():
            return False
        await self._queue.put(task)
        self._ensure_worker_running()
        return True

    def _ensure_worker_running(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        while not self._queue.empty():
            task = await self._queue.get()
            try:
                logger.debug(f"Processing queued task: {task.command} for user {task.user}")
                await task.coro
            except Exception as e:
                logger.exception(f"Error processing queued task {task.command}: {e}")
            finally:
                self._queue.task_done()
