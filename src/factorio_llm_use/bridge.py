"""Serialized Source RCON transport and the mod's request protocol."""

from __future__ import annotations

import json
import socket
import struct
import threading
from typing import Any
from uuid import uuid4


class BridgeError(RuntimeError):
    """A transport error or a rejected game operation."""


class Bridge:
    def __init__(self, password: str, host: str = "127.0.0.1", port: int = 27075):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Use a loopback RCON address")
        if not password or not 0 < port < 65536:
            raise ValueError("A valid RCON password and port are required")
        self.host, self.port, self._password = host, port, password
        self._lock = threading.RLock()

    @staticmethod
    def _read(sock: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            part = sock.recv(size - len(data))
            if not part:
                raise ConnectionError("RCON closed the connection")
            data.extend(part)
        return bytes(data)

    @classmethod
    def _packet(cls, sock: socket.socket) -> tuple[int, int, str]:
        size = struct.unpack("<i", cls._read(sock, 4))[0]
        if not 10 <= size <= 64 * 1024 * 1024:
            raise BridgeError("Invalid RCON packet size")
        data = cls._read(sock, size)
        ident, kind = struct.unpack("<ii", data[:8])
        return ident, kind, data[8:-2].decode("utf-8")

    @staticmethod
    def _send(sock: socket.socket, ident: int, kind: int, text: str) -> None:
        data = struct.pack("<ii", ident, kind) + text.encode("utf-8") + b"\0\0"
        sock.sendall(struct.pack("<i", len(data)) + data)

    def command(self, command: str) -> str:
        with self._lock, socket.create_connection((self.host, self.port), timeout=15) as sock:
            self._send(sock, 1, 3, self._password)
            while True:
                ident, kind, _ = self._packet(sock)
                if ident == -1:
                    raise BridgeError("RCON authentication failed")
                if ident == 1 and kind == 2:
                    break
            self._send(sock, 2, 2, command)
            while True:
                ident, _, text = self._packet(sock)
                if ident == 2:
                    return text

    def call(
        self, operation: str, params: dict[str, Any] | None = None, *, request_id: str | None = None
    ) -> dict[str, Any]:
        request_id = request_id or str(uuid4())
        request = {"id": request_id, "operation": operation, "params": params or {}}
        command = "/llm-use " + json.dumps(request, ensure_ascii=True, separators=(",", ":"))
        # A retry must use the same ID: the mod caches completed requests.
        with self._lock:
            for attempt in range(2):
                try:
                    raw = self.command(command)
                    for line in raw.splitlines():
                        try:
                            response = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(response, dict) and response.get("id") == request_id:
                            if not response.get("ok"):
                                raise BridgeError(response.get("error", "Game operation failed"))
                            return response
                    raise BridgeError("No matching mod response; is Factorio LLM Use enabled?")
                except (OSError, TimeoutError) as exc:
                    if attempt:
                        raise BridgeError(
                            f"RCON unavailable; retain request_id={request_id} when retrying"
                        ) from exc
        raise AssertionError("unreachable")

    def lua(self, code: str) -> str:
        """Explicit administrative escape hatch, outside the constrained agent operations."""
        return self.command("/silent-command " + code)
