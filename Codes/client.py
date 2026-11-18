"""Use the shared protocol for terminal commands and asynchronous quiz updates."""


# Imports and Command Reference

import argparse
import json
import queue
import socket
import sys
import threading

from quizlib.protocol import (FrameBuffer, MessageType as M, ProtocolError,
                              encode_frame, request, validate_envelope)

HELP = """/help                   Show commands
/quizzes                List quizzes
/rooms                  List joinable rooms
/create <quiz_id>       Create room (you become host)
/join <room_code>       Join room
/players                Show participants and readiness
/ready                  Set ready
/start                  Start (host only, all ready, at least two players)
/answer <A|B|C|D>       Answer the current question
/score                  Show leaderboard
/leave                  Leave room
/quit                   Log out and exit"""

COMMANDS = {"/quizzes": (M.LIST_QUIZZES_REQUEST, None),
            "/rooms": (M.LIST_ROOMS_REQUEST, None),
            "/create": (M.CREATE_ROOM_REQUEST, "quiz_id"),
            "/join": (M.JOIN_ROOM_REQUEST, "room_code"),
            "/players": (M.PLAYER_LIST_REQUEST, None),
            "/ready": (M.READY_REQUEST, None),
            "/start": (M.START_QUIZ_REQUEST, None),
            "/answer": (M.ANSWER_REQUEST, "answer"),
            "/score": (M.LEADERBOARD_REQUEST, None),
            "/leave": (M.LEAVE_ROOM_REQUEST, None),
            "/quit": (M.LOGOUT_REQUEST, None)}


# CLI Command Parsing

def parse_command(line, question_id=None):
    parts = line.split()
    if not parts:
        raise ValueError("Enter /help for commands")
    if parts == ["/help"]:
        return None, {}
    if parts[0] not in COMMANDS:
        raise ValueError("Unknown command; enter /help")
    kind, field = COMMANDS[parts[0]]
    if len(parts) != (2 if field else 1):
        raise ValueError(f"Wrong arguments for {parts[0]}; enter /help")
    payload = {field: parts[1]} if field else {}
    if kind == M.READY_REQUEST:
        payload["ready"] = True
    if kind == M.ANSWER_REQUEST:
        if parts[1] not in ("A", "B", "C", "D"):
            raise ValueError("Answer must be A, B, C or D")
        if question_id is None:
            raise ValueError("There is no open question")
        payload["question_id"] = question_id
    return kind, payload


# Client State and Login

class QuizClient:
    def __init__(self, server, port, user_id, name, output=print):
        self.server, self.port, self.user_id, self.name = server, port, user_id, name
        self.output = output
        self.socket = None
        self.thread = None
        self.send_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.stopped = threading.Event()
        self.login_done = threading.Event()
        self.session_id = None
        self.room_code = None
        self.question_id = None
        self.pending = {}
        self._sequence = 0
        self.room_listing = None
        self.room_cursor = None
        self.room_request_id = None

    def connect(self):
        self.socket = socket.create_connection((self.server, self.port), timeout=5)
        self.socket.settimeout(None)
        self.output("CONNECTED")
        self.thread = threading.Thread(target=self._receive, name="quiz-receiver", daemon=True)
        self.thread.start()
        self.send(M.LOGIN_REQUEST, {"user_id": self.user_id, "name": self.name})
        if not self.login_done.wait(5) or self.session_id is None:
            self.close()
            raise ConnectionError("Login failed or timed out")

    # Request Sending and Dispatch

    def send(self, kind, payload=None):
        with self.send_lock:
            with self.state_lock:
                self._sequence += 1
                message = request(kind, payload, self.session_id, f"req-{self._sequence:06d}")
                if kind == M.LIST_ROOMS_REQUEST:
                    cursor = message["payload"].get("cursor")
                    if cursor is None:
                        if self.room_listing is not None:
                            raise ValueError("Room listing is already in progress")
                        self.room_listing = []
                        self.room_cursor = None
                    elif self.room_listing is None or cursor != self.room_cursor:
                        raise ValueError("Unexpected room-list cursor")
                    self.room_request_id = message["request_id"]
                # Only operations with direct responses need response correlation.
                if kind not in (M.READY_REQUEST, M.START_QUIZ_REQUEST, M.LEAVE_ROOM_REQUEST, M.LOGOUT_REQUEST):
                    expected = str(kind).removesuffix("_REQUEST") + "_RESPONSE"
                    self.pending[message["request_id"]] = expected
            try:
                self.socket.sendall(encode_frame(message))
            except OSError as exc:
                self.close()
                raise ConnectionError("Server connection lost") from exc
        return message["request_id"]

    def command(self, line):
        with self.state_lock:
            kind, payload = parse_command(line, self.question_id)
        if kind is None:
            self.output(HELP)
        else:
            self.send(kind, payload)
        return kind != M.LOGOUT_REQUEST

    # Responses and Game Events

    def _clear_room_listing(self):
        # Caller holds state_lock; discard partial results on completion, error or disconnect.
        self.pending.pop(self.room_request_id, None)
        self.room_listing = None
        self.room_cursor = None
        self.room_request_id = None

    def _collect_room_page(self, message):
        payload = message["payload"]
        try:
            if self.room_listing is None or message["request_id"] != self.room_request_id:
                raise ProtocolError("Unexpected room-list response")
            rooms, cursor = payload.get("rooms"), payload.get("next_cursor")
            if not isinstance(rooms, list) or "next_cursor" not in payload:
                raise ProtocolError("Invalid room-list page")
            previous = self.room_cursor
            for room in rooms:
                code = room.get("room_code") if isinstance(room, dict) else None
                if not isinstance(code, str) or not code or (previous is not None and code <= previous):
                    raise ProtocolError("Room-list entries must progress without duplicates")
                previous = code
            if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 128
                                       or not rooms or cursor != previous
                                       or (self.room_cursor is not None and cursor <= self.room_cursor)):
                raise ProtocolError("Room-list cursor did not progress")
            self.room_listing.extend(rooms)
            if cursor is not None:
                self.room_cursor = cursor
                return None, cursor
            complete = {"rooms": self.room_listing, "next_cursor": None}
            self._clear_room_listing()
            return complete, None
        except ProtocolError:
            self._clear_room_listing()
            raise

    def handle_message(self, message):
        validate_envelope(message)
        kind, payload = message["type"], message["payload"]
        next_cursor = None
        with self.state_lock:
            if kind.endswith("_REQUEST"):
                raise ProtocolError("Server sent a request")
            if kind.endswith("_RESPONSE") and kind != M.ERROR_RESPONSE:
                if self.pending.pop(message["request_id"], None) != kind:
                    raise ProtocolError("Unmatched server response")
            if kind == M.LOGIN_RESPONSE:
                sid = payload.get("session_id")
                if payload.get("success") is not True or not isinstance(sid, str) or message["session_id"] != sid:
                    raise ProtocolError("Inconsistent login session")
                self.session_id = sid
                self.login_done.set()
            elif self.session_id is not None and message["session_id"] != self.session_id:
                raise ProtocolError("Server message has wrong session")
            if kind == M.ERROR_RESPONSE:
                self.pending.pop(message["request_id"], None)
                if message["request_id"] is None or message["request_id"] == self.room_request_id:
                    self._clear_room_listing()
                if self.session_id is None:
                    self.login_done.set()
            elif kind == M.LIST_ROOMS_RESPONSE:
                payload, next_cursor = self._collect_room_page(message)
            elif kind == M.CREATE_ROOM_RESPONSE:
                self.room_code = payload["room_code"]
            elif kind == M.JOIN_ROOM_RESPONSE:
                self.room_code = payload["room"]["room_code"]
            elif kind == M.PLAYER_STATUS_EVENT:
                if any(p["user_id"] == self.user_id for p in payload["players"]):
                    self.room_code = payload["room_code"]
                elif self.room_code == payload["room_code"]:
                    self.room_code = None
                    self.question_id = None
            elif kind == M.QUESTION_EVENT:
                self.question_id = payload["question_id"]
            elif kind == M.QUESTION_RESULT_EVENT:
                if self.question_id == payload["question_id"]:
                    self.question_id = None
            elif kind in (M.QUIZ_FINISHED_EVENT, M.ROOM_CLOSED_EVENT):
                self.question_id = None
                if kind == M.ROOM_CLOSED_EVENT:
                    self.room_code = None
        if next_cursor is not None:
            # send() takes send_lock before state_lock: never call it while holding state_lock.
            self.send(M.LIST_ROOMS_REQUEST, {"cursor": next_cursor})
            return
        # Each received message occupies one line, usable in terminals and pipe tests.
        # JSON preserves every metadata field, option, award and leaderboard entry.
        if kind == M.LOGIN_RESPONSE:
            visible = {"success": True, "user_id": self.user_id, "name": self.name}
        else:
            visible = payload
        self.output(f"{kind} {json.dumps(visible, ensure_ascii=False)}")

    # Background Receiver and Cleanup

    def _receive(self):
        frames = FrameBuffer()
        try:
            while not self.stopped.is_set():
                data = self.socket.recv(65_536)
                if not data:
                    break
                for message in frames.feed(data):
                    self.handle_message(message)
        except (OSError, ProtocolError, KeyError, TypeError, ValueError) as exc:
            if not self.stopped.is_set():
                self.output(f"CONNECTION_ERROR {exc}")
        finally:
            with self.state_lock:
                self._clear_room_listing()
            if not self.stopped.is_set():
                self.output("DISCONNECTED server connection closed")
            self.stopped.set()
            self.login_done.set()

    def close(self):
        self.stopped.set()
        with self.state_lock:
            self._clear_room_listing()
        if self.socket is not None:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)


# Terminal Input and Program Entry

def _stdin_lines(lines):
    # Isolate the OS's blocking stdin read so server loss can end the main loop
    # even on Windows pipes. All command parsing and dispatch stays in main.
    for line in sys.stdin:
        lines.put(line)
    lines.put(None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--id", required=True, dest="user_id")
    parser.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65_535:
        parser.error("port must be 1-65535")
    client = QuizClient(args.server, args.port, args.user_id, args.name,
                        output=lambda line: print(line, flush=True))
    try:
        client.connect()
        print("Enter /help for commands", flush=True)
        lines = queue.Queue()
        threading.Thread(target=_stdin_lines, args=(lines,), daemon=True).start()
        while not client.stopped.is_set():
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                client.send(M.LOGOUT_REQUEST)
                break
            try:
                if not client.command(line):
                    break
            except ValueError as exc:
                print(f"COMMAND_ERROR {exc}", flush=True)
    except KeyboardInterrupt:
        if client.session_id and not client.stopped.is_set():
            try:
                client.send(M.LOGOUT_REQUEST)
            except ConnectionError:
                pass
    except (OSError, ConnectionError, ProtocolError) as exc:
        print(f"CLIENT_ERROR {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
