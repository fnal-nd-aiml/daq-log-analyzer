"""
File: receiver.py
Purpose: UDP receiver thread for MessageFacility messages.
Category: Utility
Author: artdaq team
Depends: None
Exports: ReceiverThread
Complexity: Low | Lines: 75
"""

import logging
import select
import socket
import struct
from queue import Full, Queue
from threading import Event, Thread
from .config import MsgSpyConfig
from .errors import SocketError
from .parser import validate_raw
logger = logging.getLogger(__name__)

class ReceiverThread(Thread):

    def __init__(self, config: MsgSpyConfig, queue: Queue[bytes], stop_event: Event) -> None:
        super().__init__(name='msgspy-receiver', daemon=True)
        self._config = config
        self._queue = queue
        self._stop_event = stop_event
        self.packets_received: int = 0
        self.packets_dropped: int = 0
        self._sock: socket.socket | None = None

    def _create_socket(self) -> socket.socket:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError as e:
            raise SocketError(f'Failed to create UDP socket: {e}') from e
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._config.socket_buffer_size)
            sock.bind((self._config.bind_address, self._config.port))
        except OSError as e:
            sock.close()
            raise SocketError(f'Failed to bind to {self._config.bind_address}:{self._config.port}: {e}') from e
        if self._config.multicast_group:
            try:
                mreq = struct.pack('4s4s', socket.inet_aton(self._config.multicast_group), socket.inet_aton(self._config.multicast_interface))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError as e:
                sock.close()
                raise SocketError(f'Failed to join multicast group {self._config.multicast_group}: {e}') from e
        return sock

    def run(self) -> None:
        try:
            self._sock = self._create_socket()
        except SocketError:
            logger.exception('Receiver failed to create socket')
            return
        poller = select.poll()
        poller.register(self._sock.fileno(), select.POLLIN)
        timeout_ms = self._config.poll_timeout_ms
        logger.info('Receiver listening on %s:%d', self._config.bind_address, self._config.port)
        try:
            while not self._stop_event.is_set():
                events = poller.poll(timeout_ms)
                if not events:
                    continue
                try:
                    data, _addr = self._sock.recvfrom(65535)
                except OSError:
                    if self._stop_event.is_set():
                        break
                    logger.exception('recvfrom error')
                    continue
                if not validate_raw(data):
                    continue
                self.packets_received += 1
                try:
                    self._queue.put_nowait(data)
                except Full:
                    self.packets_dropped += 1
        finally:
            self._sock.close()
            logger.info('Receiver stopped: received=%d dropped=%d', self.packets_received, self.packets_dropped)