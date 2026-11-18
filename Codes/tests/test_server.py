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
from quizlib.protocol import FrameBuffer, MessageType as M, encode_frame, request
from tests import ROOT, Program, RunningSystem, bank_fixture, free_port, require_loopback


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


class ServerStartupTests(unittest.TestCase):
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
