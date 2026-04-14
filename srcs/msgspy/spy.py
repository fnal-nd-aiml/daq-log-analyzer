"""
File: spy.py
Purpose: MessageSpy orchestrator — manages receiver and writer threads.
Category: Utility
Author: artdaq team
Depends: None
Exports: MessageSpy
Complexity: Low | Lines: 75
"""

import logging
from queue import Queue
from threading import Event
from typing import Any
from .config import MsgSpyConfig
from .filter import MessageFilter
from .receiver import ReceiverThread
from .writer import WriterThread

logger = logging.getLogger(__name__)


class MessageSpy:

    def __init__(self, config: MsgSpyConfig) -> None:
        self._config = config
        self._stop_event = Event()
        self._queue: Queue[bytes] = Queue(maxsize=config.queue_size)
        self._receiver = ReceiverThread(config, self._queue, self._stop_event)
        has_filters = bool(config.filters) or config.throttle.enabled
        self._filter: MessageFilter | None = None
        if has_filters:
            self._filter = MessageFilter(filters=config.filters, throttle=config.throttle, write_raw=config.write_raw)
        self._writer = WriterThread(
            queue=self._queue,
            stop_event=self._stop_event,
            output_path=config.output_path,
            append=config.append,
            write_raw=config.write_raw,
            batch_size=config.batch_size,
            flush_interval_ms=config.flush_interval_ms,
            message_filter=self._filter,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        logger.info(
            "Starting MessageSpy on %s:%d → %s", self._config.bind_address, self._config.port, self._config.output_path
        )
        self._stop_event.clear()
        self._writer.start()
        self._receiver.start()
        self._started = True

    def stop(self, timeout: float = 5.0) -> None:
        if not self._started:
            return
        logger.info("Stopping MessageSpy...")
        self._stop_event.set()
        self._receiver.join(timeout=timeout)
        self._writer.join(timeout=timeout)
        self._started = False
        logger.info("MessageSpy stopped. %s", self.stats)

    @property
    def stats(self) -> dict[str, Any]:
        s: dict[str, Any] = {
            "packets_received": self._receiver.packets_received,
            "packets_dropped": self._receiver.packets_dropped,
            "messages_written": self._writer.messages_written,
            "queue_depth": self._queue.qsize(),
        }
        if self._filter is not None:
            s["messages_filtered"] = self._filter.messages_filtered
            s["messages_throttled"] = self._filter.messages_throttled
        return s

    def __enter__(self) -> "MessageSpy":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
