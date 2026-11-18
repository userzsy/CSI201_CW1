import socket
import threading
import unittest

from client import COMMANDS, QuizClient, parse_command
from quizlib.protocol import MessageType as M, ProtocolError, event, response, error


class ClientTests(unittest.TestCase):
    def test_all_commands(self):
        for command, (kind, field) in COMMANDS.items():
            line = command + (" A" if field == "answer" else " value" if field else "")
            parsed, payload = parse_command(line, "Q1")
            self.assertEqual(parsed, kind)
            if field:
                self.assertIn(field, payload)
        self.assertEqual(parse_command("/help"), (None, {}))
        self.assertEqual(parse_command("/answer B", "Q1")[1], {"question_id": "Q1", "answer": "B"})

    def test_invalid_commands(self):
        for line in ("", "/unknown", "/create", "/ready yes", "/answer E", "/answer a", "/help x"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_command(line)
        with self.assertRaises(ValueError):
            parse_command("/answer A")

    def test_event_tracking_and_error_display(self):
        output = []
        client = QuizClient("127.0.0.1", 1, "u", "Alice", output.append)
        client.session_id = "sid"
        client.handle_message(event(M.PLAYER_STATUS_EVENT, "sid",
                                    {"room_code": "R1", "players": [{"user_id": "u"}]}))
        self.assertEqual(client.room_code, "R1")
        client.handle_message(event(M.QUESTION_EVENT, "sid", {"question_id": "Q1"}))
        self.assertEqual(client.question_id, "Q1")
        client.handle_message(error("r1", "sid", "INVALID_ANSWER", "bad answer"))
        self.assertIn("INVALID_ANSWER", output[-1])
        client.handle_message(event(M.QUESTION_RESULT_EVENT, "sid", {"question_id": "Q1"}))
        self.assertIsNone(client.question_id)
        client.handle_message(event(M.PLAYER_STATUS_EVENT, "sid", {"room_code": "R1", "players": []}))
        self.assertIsNone(client.room_code)

    def test_response_and_session_validation(self):
        client = QuizClient("127.0.0.1", 1, "u", "Alice", lambda x: None)
        with self.assertRaises(ProtocolError):
            client.handle_message(response(M.LIST_ROOMS_RESPONSE, "unknown", "sid", {}))
        client.session_id = "sid"
        with self.assertRaises(ProtocolError):
            client.handle_message(event(M.ROOM_CLOSED_EVENT, "wrong", {}))

    def test_receive_detects_server_disconnect(self):
        class ClosedServer:
            def recv(self, length):
                return b""

            def shutdown(self, how):
                pass

            def close(self):
                pass

        output = []
        client = QuizClient("127.0.0.1", 1, "u", "Alice", output.append)
        client.socket = ClosedServer()
        client.thread = threading.Thread(target=client._receive)
        client.thread.start()
        self.assertTrue(client.stopped.wait(2))
        client.close()
        self.assertTrue(any("DISCONNECTED" in line for line in output))
