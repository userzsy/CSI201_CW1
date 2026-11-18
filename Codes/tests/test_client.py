"""Test client commands and protocol events without a live server."""


# Imports

import json
import threading
import unittest

from client import COMMANDS, QuizClient, parse_command
from quizlib.protocol import MessageType as M, ProtocolError, decode_frame, event, response, error


# CLI Command Cases

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

    # Event State and Response Validation

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

    # Receiver Shutdown

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


# Automatic Room Pagination

class ClientPaginationTests(unittest.TestCase):
    def setUp(self):
        class CapturedSocket:
            def __init__(self):
                self.messages = []
                self.on_send = None

            def sendall(self, frame):
                self.messages.append(decode_frame(frame))
                if self.on_send is not None:
                    self.on_send()

            def recv(self, length):
                return b""

            def shutdown(self, how):
                pass

            def close(self):
                pass

        self.output = []
        self.client = QuizClient("127.0.0.1", 1, "observer", "Observer", self.output.append)
        self.client.session_id = "sid"
        self.client.socket = CapturedSocket()
        self.sent = self.client.socket.messages
        self.addCleanup(self.client.close)

    def page(self, codes, cursor):
        message = response(M.LIST_ROOMS_RESPONSE, self.sent[-1]["request_id"], "sid",
                           {"rooms": [{"room_code": code} for code in codes], "next_cursor": cursor})
        self.client.handle_message(message)

    def test_pages_are_accumulated_and_only_one_complete_result_is_displayed(self):
        self.client.command("/rooms")
        self.assertIsNone(self.sent[0]["payload"].get("cursor"))
        self.page(["R000001", "R000002"], "R000002")
        self.assertFalse(self.output)
        self.assertEqual(len(self.client.room_listing), 2)
        self.assertEqual(self.sent[-1]["payload"], {"cursor": "R000002"})
        self.assertNotEqual(self.sent[0]["request_id"], self.sent[1]["request_id"])
        self.page(["R000003"], None)
        self.assertEqual(len(self.output), 1)
        body = json.loads(self.output[0].partition(" ")[2])
        self.assertEqual([room["room_code"] for room in body["rooms"]],
                         ["R000001", "R000002", "R000003"])
        self.assertIsNone(body["next_cursor"])
        self.assertIsNone(self.client.room_listing)
        self.assertFalse(self.client.pending)

    def test_empty_and_single_page_lists(self):
        for codes in ([], ["R000001"]):
            with self.subTest(codes=codes):
                self.client.command("/rooms")
                self.page(codes, None)
                body = json.loads(self.output[-1].partition(" ")[2])
                self.assertEqual([room["room_code"] for room in body["rooms"]], codes)
                self.assertIsNone(self.client.room_listing)
        self.assertEqual(len(self.sent), 2)

    def test_repeated_backward_and_invalid_cursors_abort_incomplete_results(self):
        for cursor in ("R000002", "R000001", "", 3, []):
            with self.subTest(cursor=cursor):
                self.client.command("/rooms")
                self.page(["R000002"], "R000002")
                with self.assertRaises(ProtocolError):
                    self.page(["R000003"], cursor)
                self.assertIsNone(self.client.room_listing)
                self.assertFalse(self.client.pending)
        self.assertFalse(self.output)

    def test_duplicate_or_unsorted_entries_are_rejected(self):
        for codes in (["R000002", "R000002"], ["R000002", "R000001"]):
            with self.subTest(codes=codes):
                self.client.command("/rooms")
                with self.assertRaises(ProtocolError):
                    self.page(codes, None)
                self.assertIsNone(self.client.room_listing)
        self.client.command("/rooms")
        self.page(["R000002"], "R000002")
        with self.assertRaises(ProtocolError):
            self.page(["R000002"], None)
        self.assertFalse(self.output)

    def test_error_clears_partial_results_and_allows_a_new_listing(self):
        self.client.command("/rooms")
        self.page(["R000001"], "R000001")
        self.client.handle_message(error(self.sent[-1]["request_id"], "sid", "INTERNAL_ERROR", "failed"))
        self.assertIsNone(self.client.room_listing)
        self.assertEqual(len(self.output), 1)
        self.assertTrue(self.output[0].startswith("ERROR_RESPONSE "))
        self.client.command("/rooms")
        self.page([], None)
        self.assertEqual(len(self.output), 2)

    def test_overlapping_rooms_commands_do_not_replace_the_active_accumulator(self):
        self.client.command("/rooms")
        with self.assertRaisesRegex(ValueError, "already in progress"):
            self.client.command("/rooms")
        self.assertEqual(len(self.sent), 1)
        self.page(["R000001"], None)
        self.assertEqual(len(self.output), 1)

    def test_disconnect_discards_incomplete_results(self):
        self.client.command("/rooms")
        self.page(["R000001"], "R000001")
        self.client._receive()
        self.assertIsNone(self.client.room_listing)
        self.assertFalse(self.client.pending)
        self.assertTrue(self.client.stopped.is_set())
        self.assertFalse(any(line.startswith("LIST_ROOMS_RESPONSE ") for line in self.output))

    def test_next_page_send_releases_the_state_lock(self):
        self.client.command("/rooms")

        def check_lock():
            acquired = threading.Event()

            def worker():
                with self.client.state_lock:
                    acquired.set()

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            self.assertTrue(acquired.wait(1), "state_lock held while sending the next page")
            thread.join(timeout=1)

        self.client.socket.on_send = check_lock
        self.page(["R000001"], "R000001")
        self.page([], None)

    def test_unmatched_page_response_is_rejected(self):
        self.client.command("/rooms")
        with self.assertRaisesRegex(ProtocolError, "Unmatched server response"):
            self.client.handle_message(response(M.LIST_ROOMS_RESPONSE, "wrong", "sid",
                                                {"rooms": [], "next_cursor": None}))

    def test_interleaved_responses_do_not_corrupt_room_pages(self):
        self.client.command("/rooms")
        self.page(["R000001"], "R000001")
        page_request = self.client.room_request_id
        self.client.command("/quizzes")
        self.client.handle_message(response(M.LIST_QUIZZES_RESPONSE, self.sent[-1]["request_id"],
                                            "sid", {"quizzes": []}))
        self.client.handle_message(response(M.LIST_ROOMS_RESPONSE, page_request, "sid",
                                            {"rooms": [{"room_code": "R000002"}], "next_cursor": None}))
        self.assertEqual(len(self.output), 2)
        rooms = json.loads(self.output[-1].partition(" ")[2])["rooms"]
        self.assertEqual([room["room_code"] for room in rooms], ["R000001", "R000002"])

    def test_empty_page_with_a_cursor_is_rejected(self):
        self.client.command("/rooms")
        with self.assertRaises(ProtocolError):
            self.page([], "R000001")
        self.assertIsNone(self.client.room_listing)
        self.assertEqual(len(self.sent), 1)
