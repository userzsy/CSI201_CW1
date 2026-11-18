"""Test startup, cleanup and actual TCP handling in the submitted server."""


# Imports

import contextlib
import io
import json
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from server import Connection, QuizServer, main
from quizlib.protocol import (ApplicationError, FrameBuffer, MAX_PAYLOAD, MessageType as M,
                              ProtocolError, encode_frame, request)
from tests import ROOT, RunningSystem, SeededServer, bank_fixture, free_port, require_loopback


# Wire-Level Test Peer

class Peer:
    def __init__(self, port):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.frames = FrameBuffer()
        self.received = []

    def receive(self):
        while not self.received:
            data = self.socket.recv(65_536)
            if not data:
                raise EOFError("Server disconnected")
            self.received.extend(self.frames.feed(data))
        return self.received.pop(0)

    def close(self):
        self.socket.close()


# Startup Validation and Shutdown

class ServerStartupTests(unittest.TestCase):
    def test_invalid_unicode_bank_is_rejected_before_listening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bank.json"
            bank = bank_fixture()
            bank["quizzes"][0]["questions"][1]["options"]["B"] = "\udfff"
            path.write_bytes(json.dumps(bank, ensure_ascii=True).encode("utf-8"))
            port = free_port()
            args = ["--host", "127.0.0.1", "--port", str(port), "--questions", str(path)]
            result = subprocess.run([sys.executable, str(ROOT / "server.py")] + args,
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("SERVER_READY", result.stdout)
            self.assertIn("STARTUP_ERROR", result.stderr)
            self.assertIn("options.B: must contain valid UTF-8 text", result.stderr)
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
            with patch("server.socket.socket") as constructor, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 1)
                constructor.assert_not_called()

    def test_invalid_banks_exit_without_ready_or_listening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bank.json"
            for data in (None, b"", b"{", b'{"schema_version":1,"quizzes":[]}', b"\xff"):
                if data is not None:
                    path.write_bytes(data)
                port = free_port()
                result = subprocess.run([sys.executable, str(ROOT / "server.py"), "--host", "127.0.0.1",
                                         "--port", str(port), "--questions", str(path)],
                                        capture_output=True, text=True, timeout=8)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("SERVER_READY", result.stdout)
                self.assertIn("STARTUP_ERROR", result.stderr)
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)

    def test_validation_precedes_socket_creation(self):
        with patch("server.socket.socket") as constructor, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--host", "127.0.0.1", "--port", "9999",
                                   "--questions", "missing-bank.json"]), 1)
            constructor.assert_not_called()

    def test_invalid_arguments(self):
        for port in ("0", "65536", "abc"):
            with self.subTest(port=port), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--host", "127.0.0.1", "--port", port, "--questions", "irrelevant"])

    def test_stop_releases_socket_sessions_and_rooms(self):
        require_loopback()
        server = QuizServer("127.0.0.1", 0, bank_fixture())
        thread = threading.Thread(target=server.serve_forever)
        with contextlib.redirect_stdout(io.StringIO()):
            thread.start()
            deadline = time.monotonic() + 3
            while not server.running and thread.is_alive() and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertTrue(server.running)
            peer = Peer(server.port)
            try:
                peer.socket.sendall(encode_frame(request(M.LOGIN_REQUEST, {"user_id": "u", "name": "Alice"})))
                self.assertEqual(peer.receive()["type"], M.LOGIN_RESPONSE)
                server.stop()
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
                self.assertFalse(server.sessions.by_user)
                self.assertFalse(server.connections)
                self.assertFalse(server.rooms.rooms)
            finally:
                peer.close()
                server.stop()
                thread.join(timeout=3)

    @unittest.skipIf(sys.platform == "win32", "POSIX SIGINT test; repeat in Linux examiner image")
    def test_ctrl_c_shutdown_subprocess(self):
        system = RunningSystem()
        try:
            system.client("a")
            system.server.process.send_signal(signal.SIGINT)
            system.server.wait("SERVER_STOPPED")
            self.assertEqual(system.server.process.wait(timeout=3), 0)
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", system.port)), 0)
        finally:
            system.close()


# TCP Framing, Sessions and Recovery

class ServerWireTests(unittest.TestCase):
    def setUp(self):
        self.system = RunningSystem()
        self.addCleanup(self.system.close)

    def peer(self):
        peer = Peer(self.system.port)
        self.addCleanup(peer.close)
        return peer

    def login(self, peer, user_id="u"):
        peer.socket.sendall(encode_frame(request(M.LOGIN_REQUEST, {"user_id": user_id, "name": "Alice"})))
        return peer.receive()

    def test_fragmented_login_and_coalesced_requests(self):
        peer = self.peer()
        frame = encode_frame(request(M.LOGIN_REQUEST, {"user_id": "u", "name": "中文"}, request_id="login"))
        for value in frame:
            peer.socket.sendall(bytes([value]))
        login = peer.receive()
        self.assertEqual(login["request_id"], "login")
        sid = login["payload"]["session_id"]
        self.assertEqual(login["session_id"], sid)
        messages = [request(M.LIST_QUIZZES_REQUEST, session_id=sid, request_id="one"),
                    request(M.LIST_ROOMS_REQUEST, session_id=sid, request_id="two")]
        peer.socket.sendall(b"".join(map(encode_frame, messages)))
        replies = [peer.receive(), peer.receive()]
        self.assertEqual([r["request_id"] for r in replies], ["one", "two"])
        self.assertEqual(set(replies[0]["payload"]["quizzes"][0]),
                         {"quiz_id", "title", "description", "question_count"})

    def test_bad_frames_close_only_the_offending_connection(self):
        good = self.peer()
        sid = self.login(good)["session_id"]
        for payload in (b"\xff", b"{", b"[]", b'{"version":1}'):
            bad = self.peer()
            bad.socket.sendall(struct.pack("!I", len(payload)) + payload)
            result = bad.receive()
            self.assertEqual(result["payload"]["code"], "INVALID_MESSAGE")
            self.assertEqual(bad.socket.recv(1), b"")
            good.socket.sendall(encode_frame(request(M.LIST_ROOMS_REQUEST, session_id=sid)))
            self.assertEqual(good.receive()["type"], M.LIST_ROOMS_RESPONSE)
        for header in (0, 65537):
            bad = self.peer()
            bad.socket.sendall(struct.pack("!I", header))
            self.assertEqual(bad.receive()["payload"]["code"], "INVALID_MESSAGE")

    def test_session_bound_to_connection_and_payload_types(self):
        first, second = self.peer(), self.peer()
        sid = self.login(first)["session_id"]
        second.socket.sendall(encode_frame(request(M.LIST_ROOMS_REQUEST, session_id=sid)))
        self.assertEqual(second.receive()["payload"]["code"], "INVALID_SESSION")
        first.socket.sendall(encode_frame(request(M.CREATE_ROOM_REQUEST, {"quiz_id": []}, sid)))
        self.assertEqual(first.receive()["payload"]["code"], "INVALID_MESSAGE")
        first.socket.sendall(encode_frame(request(M.READY_REQUEST, {"ready": True}, sid)))
        self.assertEqual(first.receive()["payload"]["code"], "NOT_IN_ROOM")

    def test_duplicate_identity_and_reuse_after_logout(self):
        first, second = self.peer(), self.peer()
        sid = self.login(first)["session_id"]
        self.assertEqual(self.login(second)["payload"]["code"], "DUPLICATE_USER")
        first.socket.sendall(encode_frame(request(M.LOGOUT_REQUEST, session_id=sid)))
        self.assertEqual(first.socket.recv(1), b"")
        self.assertEqual(self.login(second)["type"], M.LOGIN_RESPONSE)

    # Focused Output Buffer Tests

    def test_partial_send_retains_unsent_bytes(self):
        class PartialSocket:
            def send(self, data):
                self.seen = bytes(data)
                return 3

        server = QuizServer("127.0.0.1", 0, bank_fixture())
        self.addCleanup(server.selector.close)
        sock = PartialSocket()
        connection = Connection(sock, outgoing=bytearray(b"abcdef"))
        server.connections[sock] = connection
        with patch.object(server, "_interest"):
            server._write(connection)
        self.assertEqual(sock.seen, b"abcdef")
        self.assertEqual(connection.outgoing, b"def")

    def test_slow_client_backpressure_is_deferred(self):
        server = QuizServer("127.0.0.1", 0, bank_fixture())
        self.addCleanup(server.selector.close)
        fake_socket = object()
        connection = Connection(fake_socket, outgoing=bytearray(1_048_576))
        server.connections[fake_socket] = connection
        server._queue(connection, request(M.LIST_ROOMS_REQUEST))
        self.assertTrue(connection.abort)
        self.assertIn(fake_socket, server.connections)


# Room Pagination Regression

class ServerPaginationTests(unittest.TestCase):
    def test_160_rooms_over_real_tcp_with_bounded_frames_and_reused_connection(self):
        seeded = SeededServer(160)
        self.addCleanup(seeded.close)
        peer = Peer(seeded.server.port)
        self.addCleanup(peer.close)
        peer.socket.sendall(encode_frame(request(M.LOGIN_REQUEST,
                                                {"user_id": "observer", "name": "Observer"})))
        sid = peer.receive()["session_id"]
        cursor, codes, sizes = None, [], []
        for page in range(161):
            request_id = f"page-{page:03d}-" + "😀" * 110
            peer.socket.sendall(encode_frame(request(M.LIST_ROOMS_REQUEST, {"cursor": cursor},
                                                    sid, request_id)))
            message = peer.receive()
            self.assertEqual(message["type"], M.LIST_ROOMS_RESPONSE)
            self.assertEqual(message["request_id"], request_id)
            self.assertEqual(message["session_id"], sid)
            sizes.append(len(encode_frame(message)) - 4)
            self.assertLessEqual(sizes[-1], MAX_PAYLOAD)
            rooms = message["payload"]["rooms"]
            self.assertTrue(all("players" not in room for room in rooms))
            codes.extend(room["room_code"] for room in rooms)
            next_cursor = message["payload"]["next_cursor"]
            if next_cursor is None:
                break
            self.assertTrue(rooms)
            self.assertEqual(next_cursor, codes[-1])
            if cursor is not None:
                self.assertGreater(next_cursor, cursor)
            cursor = next_cursor
        else:
            self.fail("Pagination did not terminate")
        self.assertGreater(len(sizes), 1)
        self.assertEqual(len(codes), 160)
        self.assertEqual(len(set(codes)), 160)
        self.assertEqual(codes, seeded.codes)
        print(f"ROOM_PAGINATION rooms={len(codes)} pages={len(sizes)} max_payload_bytes={max(sizes)}")
        peer.socket.sendall(encode_frame(request(M.LIST_QUIZZES_REQUEST, session_id=sid)))
        self.assertEqual(peer.receive()["type"], M.LIST_QUIZZES_RESPONSE)
        peer.socket.sendall(encode_frame(request(M.LIST_ROOMS_REQUEST, {"cursor": []}, sid)))
        self.assertEqual(peer.receive()["payload"]["code"], "INVALID_MESSAGE")
        peer.socket.sendall(encode_frame(request(M.LIST_QUIZZES_REQUEST, session_id=sid)))
        self.assertEqual(peer.receive()["type"], M.LIST_QUIZZES_RESPONSE)


class ServerPageSizingTests(unittest.TestCase):
    def setUp(self):
        bank = bank_fixture()
        bank["quizzes"][0]["title"] = "😀" * 100
        self.server = QuizServer("127.0.0.1", 0, bank)
        self.addCleanup(self.server.selector.close)
        for i in range(5):
            session = self.server.sessions.login(str(i), "Player")
            self.server.rooms.create(session, "quiz0")

    def test_page_shrinks_using_encoded_bytes(self):
        with patch("quizlib.protocol.MAX_PAYLOAD", 1200):
            message = self.server._room_list_response("request", "sid", None)
            self.assertLess(len(message["payload"]["rooms"]), 5)
            self.assertLessEqual(len(encode_frame(message)) - 4, 1200)
            self.assertEqual(message["payload"]["next_cursor"],
                             message["payload"]["rooms"][-1]["room_code"])

    def test_serialization_error_is_not_treated_as_an_oversized_page(self):
        with patch("server.encode_frame", side_effect=ProtocolError("encoding failed")) as encoder:
            with self.assertRaises(ApplicationError) as failure:
                self.server._room_list_response("request", "sid", None)
            self.assertEqual(failure.exception.code, "INTERNAL_ERROR")
            encoder.assert_called_once()

    def test_unexpected_single_room_overflow_is_a_recoverable_error(self):
        with patch("quizlib.protocol.MAX_PAYLOAD", 100):
            with self.assertRaises(ApplicationError) as failure:
                self.server._room_list_response("request", "sid", None)
            self.assertEqual(failure.exception.code, "INTERNAL_ERROR")
