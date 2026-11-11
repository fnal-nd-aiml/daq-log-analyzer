"""
File: writer.py
Purpose: Batched buffered file writer thread for MessageFacility messages.
Category: Utility
Author: artdaq team
Depends: None
Exports: WriterThread, _PREFIX_RE
Complexity: Low | Lines: 101
"""

from __future__ import annotations
import logging
import re
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .filter import MessageFilter
logger = logging.getLogger(__name__)
_PREFIX_RE = re.compile('^UDPMFMESSAGE\\d+\\|')

class WriterThread(Thread):

    def __init__(self, queue: Queue[bytes], stop_event: Event, output_path: Path, append: bool=False, write_raw: bool=True, batch_size: int=200, flush_interval_ms: int=100, message_filter: MessageFilter | None=None) -> None:
        super().__init__(name='msgspy-writer', daemon=True)
        self._queue = queue
        self._stop_event = stop_event
        self._output_path = output_path
        self._append = append
        self._write_raw = write_raw
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_ms / 1000.0
        self._filter = message_filter
        self.messages_written: int = 0

    def run(self) -> None:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = 'ab' if self._append else 'wb'
        f = open(self._output_path, mode, buffering=65536)
        last_flush = time.monotonic()
        try:
            while not self._stop_event.is_set():
                try:
                    data = self._queue.get(timeout=self._flush_interval_s)
                except Empty:
                    now = time.monotonic()
                    if now - last_flush >= self._flush_interval_s:
                        f.flush()
                        last_flush = now
                    continue
                batch = [data]
                for _ in range(self._batch_size - 1):
                    try:
                        batch.append(self._queue.get_nowait())
                    except Empty:
                        break
                for item in batch:
                    if self._filter is not None:
                        lines = self._filter.process(item)
                        for line in lines:
                            f.write(line)
                            f.write(b'\n')
                        if lines:
                            self.messages_written += 1
                    elif self._write_raw:
                        f.write(item)
                        f.write(b'\n')
                        self.messages_written += 1
                    else:
                        text = item.decode('utf-8', errors='replace')
                        cleaned = _PREFIX_RE.sub('', text)
                        f.write(cleaned.encode('utf-8'))
                        f.write(b'\n')
                        self.messages_written += 1
                now = time.monotonic()
                if now - last_flush >= self._flush_interval_s:
                    f.flush()
                    last_flush = now
            while not self._queue.empty():
                try:
                    data = self._queue.get_nowait()
                except Empty:
                    break
                if self._filter is not None:
                    lines = self._filter.process(data)
                    for line in lines:
                        f.write(line)
                        f.write(b'\n')
                    if lines:
                        self.messages_written += 1
                elif self._write_raw:
                    f.write(data)
                    f.write(b'\n')
                    self.messages_written += 1
                else:
                    text = data.decode('utf-8', errors='replace')
                    cleaned = _PREFIX_RE.sub('', text)
                    f.write(cleaned.encode('utf-8'))
                    f.write(b'\n')
                    self.messages_written += 1
            if self._filter is not None:
                summary = self._filter.flush_throttle()
                if summary is not None:
                    f.write(summary)
                    f.write(b'\n')
            f.flush()
        finally:
            f.close()
            logger.info('Writer stopped: messages_written=%d', self.messages_written)