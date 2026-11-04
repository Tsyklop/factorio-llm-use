import json
import socket
import struct
import threading
import unittest

from factorio_llm_use.bridge import Bridge, BridgeError


def read_exact(connection, size):
    data = b""
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise ConnectionError("test peer disconnected")
        data += part
    return data


def read_packet(connection):
    size = struct.unpack("<i", read_exact(connection, 4))[0]
    payload = read_exact(connection, size)
    return (*struct.unpack("<ii", payload[:8]), payload[8:-2].decode())


def send_packet(connection, ident, kind, body, fragmented=False):
    payload = struct.pack("<ii", ident, kind) + body.encode() + b"\0\0"
    payload = struct.pack("<i", len(payload)) + payload
    if fragmented:
        for i in range(0, len(payload), 3):
            connection.sendall(payload[i : i + 3])
    else:
        connection.sendall(payload)


class SourceServer:
    def __init__(self, handler, connections=1):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(3)
        self.port = self.listener.getsockname()[1]
        self.error = None

        def serve():
            try:
                for index in range(connections):
                    connection, _ = self.listener.accept()
                    with connection:
                        handler(connection, index)
            except Exception as exc:
                self.error = exc

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()

    def close(self):
        self.thread.join(timeout=4)
        self.listener.close()
        if self.error:
            raise self.error


class RconTests(unittest.TestCase):
    @staticmethod
    def authenticate(connection):
        ident, kind, password = read_packet(connection)
        if kind != 3 or password != "test-secret":
            raise AssertionError("incorrect authentication packet")
        send_packet(connection, ident, 0, "")
        send_packet(connection, ident, 2, "")

    def test_fragmented_unicode_packet_round_trip(self):
        def handler(connection, _):
            self.authenticate(connection)
            ident, kind, command = read_packet(connection)
            self.assertEqual((kind, command), (2, "/example"))
            send_packet(connection, ident, 0, "RAILS / Нефтянка / 日本語", fragmented=True)

        server = SourceServer(handler)
        try:
            value = Bridge("test-secret", port=server.port).command("/example")
            self.assertEqual(value, "RAILS / Нефтянка / 日本語")
        finally:
            server.close()

    def test_authentication_rejection_is_explicit(self):
        def handler(connection, _):
            read_packet(connection)
            send_packet(connection, -1, 2, "")

        server = SourceServer(handler)
        try:
            with self.assertRaisesRegex(BridgeError, "authentication failed"):
                Bridge("test-secret", port=server.port).command("/example")
        finally:
            server.close()

    def test_invalid_packet_size_is_rejected(self):
        def handler(connection, _):
            read_packet(connection)
            connection.sendall(struct.pack("<i", 5))

        server = SourceServer(handler)
        try:
            with self.assertRaisesRegex(BridgeError, "packet size"):
                Bridge("test-secret", port=server.port).command("/example")
        finally:
            server.close()

    def test_response_from_another_request_is_not_accepted(self):
        def handler(connection, _):
            self.authenticate(connection)
            ident, _, _ = read_packet(connection)
            send_packet(connection, ident, 0, json.dumps({"id": "other", "ok": True}))

        server = SourceServer(handler)
        try:
            with self.assertRaisesRegex(BridgeError, "No matching mod response"):
                Bridge("test-secret", port=server.port).call("place_entity")
        finally:
            server.close()

    def test_retry_after_lost_response_retains_request_identity(self):
        requests = []
        world_count = 0
        cache = {}

        def handler(connection, index):
            nonlocal world_count
            self.authenticate(connection)
            ident, _, command = read_packet(connection)
            request = json.loads(command.removeprefix("/llm-use "))
            requests.append(request["id"])
            if request["id"] not in cache:
                world_count += 1
                cache[request["id"]] = {
                    "id": request["id"],
                    "ok": True,
                    "result": {"world_count": world_count},
                }
            if index:
                send_packet(connection, ident, 0, json.dumps(cache[request["id"]]))

        server = SourceServer(handler, connections=2)
        try:
            response = Bridge("test-secret", port=server.port).call("place_entity")
            self.assertEqual(requests[0], requests[1])
            self.assertEqual(response["result"]["world_count"], 1)
        finally:
            server.close()

    def test_rejected_game_operation_preserves_its_reason(self):
        def handler(connection, _):
            self.authenticate(connection)
            ident, _, command = read_packet(connection)
            request = json.loads(command.removeprefix("/llm-use "))
            send_packet(
                connection,
                ident,
                0,
                json.dumps(
                    {"id": request["id"], "ok": False, "error": "Missing real construction items"}
                ),
            )

        server = SourceServer(handler)
        try:
            with self.assertRaisesRegex(BridgeError, "Missing real construction items"):
                Bridge("test-secret", port=server.port).call("place_entity")
        finally:
            server.close()

    def test_non_loopback_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            Bridge("test-secret", host="example.com")


if __name__ == "__main__":
    unittest.main()
