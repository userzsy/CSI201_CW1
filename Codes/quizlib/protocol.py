"""Share TCP framing and envelopes between the client and server.

Version 1: 4-byte network-order length + UTF-8 JSON object.

All six envelope fields are mandatory. Requests have request_id, direct
responses repeat it, and events have event_id instead. Unknown envelope members
are allowed; unknown message types and unsupported versions are rejected.
"""


# Imports and Frame Limit

import json
import struct
import uuid
from enum import StrEnum

MAX_PAYLOAD = 65_536


# Message Types and Error Codes

class MessageType(StrEnum):
    LOGIN_REQUEST = "LOGIN_REQUEST"
    LOGIN_RESPONSE = "LOGIN_RESPONSE"
    LIST_QUIZZES_REQUEST = "LIST_QUIZZES_REQUEST"
    LIST_QUIZZES_RESPONSE = "LIST_QUIZZES_RESPONSE"
    LIST_ROOMS_REQUEST = "LIST_ROOMS_REQUEST"
    LIST_ROOMS_RESPONSE = "LIST_ROOMS_RESPONSE"
    CREATE_ROOM_REQUEST = "CREATE_ROOM_REQUEST"
    CREATE_ROOM_RESPONSE = "CREATE_ROOM_RESPONSE"
    JOIN_ROOM_REQUEST = "JOIN_ROOM_REQUEST"
    JOIN_ROOM_RESPONSE = "JOIN_ROOM_RESPONSE"
    PLAYER_LIST_REQUEST = "PLAYER_LIST_REQUEST"
    PLAYER_LIST_RESPONSE = "PLAYER_LIST_RESPONSE"
    READY_REQUEST = "READY_REQUEST"
    START_QUIZ_REQUEST = "START_QUIZ_REQUEST"
    ANSWER_REQUEST = "ANSWER_REQUEST"
    ANSWER_RESPONSE = "ANSWER_RESPONSE"
    LEADERBOARD_REQUEST = "LEADERBOARD_REQUEST"
    LEADERBOARD_RESPONSE = "LEADERBOARD_RESPONSE"
    LEAVE_ROOM_REQUEST = "LEAVE_ROOM_REQUEST"
    LOGOUT_REQUEST = "LOGOUT_REQUEST"
    ERROR_RESPONSE = "ERROR_RESPONSE"
    PLAYER_STATUS_EVENT = "PLAYER_STATUS_EVENT"
    ROOM_CLOSED_EVENT = "ROOM_CLOSED_EVENT"
    QUIZ_STARTED_EVENT = "QUIZ_STARTED_EVENT"
    QUESTION_EVENT = "QUESTION_EVENT"
    QUESTION_RESULT_EVENT = "QUESTION_RESULT_EVENT"
    QUIZ_FINISHED_EVENT = "QUIZ_FINISHED_EVENT"


class ErrorCode(StrEnum):
    INVALID_MESSAGE = "INVALID_MESSAGE"
    INVALID_SESSION = "INVALID_SESSION"
    DUPLICATE_USER = "DUPLICATE_USER"
    QUIZ_NOT_FOUND = "QUIZ_NOT_FOUND"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    ROOM_FULL = "ROOM_FULL"
    ALREADY_IN_ROOM = "ALREADY_IN_ROOM"
    NOT_ROOM_HOST = "NOT_ROOM_HOST"
    PLAYERS_NOT_READY = "PLAYERS_NOT_READY"
    QUESTION_CLOSED = "QUESTION_CLOSED"
    DUPLICATE_ANSWER = "DUPLICATE_ANSWER"
    INVALID_ANSWER = "INVALID_ANSWER"
    INVALID_STATE = "INVALID_STATE"
    NOT_IN_ROOM = "NOT_IN_ROOM"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Protocol and Application Errors

class ProtocolError(ValueError):
    """Unsafe frame/envelope: close this connection."""


class FrameSizeError(ProtocolError):
    """Encoded payload exceeds the frame bound."""


class ApplicationError(ValueError):
    """Recoverable request error; keep the connection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# Common Envelope Validation

def validate_envelope(message):
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object")
    required = {"version", "type", "request_id", "event_id", "session_id", "payload"}
    if not required <= message.keys():
        raise ProtocolError("Missing envelope field")
    if type(message["version"]) is not int or message["version"] != 1:
        raise ProtocolError("Unsupported version")
    if not isinstance(message["type"], str) or message["type"] not in MessageType:
        raise ProtocolError("Unknown message type")
    if not isinstance(message["payload"], dict):
        raise ProtocolError("payload must be an object")
    for key in ("request_id", "event_id", "session_id"):
        value = message[key]
        if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 128):
            raise ProtocolError(f"{key} must be null or a 1-128 character string")
    kind = message["type"]
    if kind.endswith("_EVENT"):
        if message["request_id"] is not None or message["event_id"] is None:
            raise ProtocolError("Events require event_id and null request_id")
    elif kind.endswith("_REQUEST") or kind != MessageType.ERROR_RESPONSE:
        if message["request_id"] is None or message["event_id"] is not None:
            raise ProtocolError("Requests/responses require request_id and null event_id")
    elif message["event_id"] is not None:
        raise ProtocolError("Error responses cannot have event_id")
    return message


# Request, Response and Event Helpers

def _message(kind, payload, request_id=None, session_id=None, event_id=None):
    return validate_envelope({"version": 1, "type": str(kind),
                              "request_id": request_id, "event_id": event_id,
                              "session_id": session_id, "payload": payload})


def request(kind, payload=None, session_id=None, request_id=None):
    return _message(kind, {} if payload is None else payload,
                    request_id or f"req-{uuid.uuid4().hex}", session_id)


def response(kind, request_id, session_id, payload):
    return _message(kind, payload, request_id, session_id)


def event(kind, session_id, payload):
    return _message(kind, payload, session_id=session_id, event_id=f"evt-{uuid.uuid4().hex}")


def error(request_id, session_id, code, message):
    return _message(MessageType.ERROR_RESPONSE,
                    {"code": str(code), "message": message}, request_id, session_id)


# Frame Encoding

def encode_frame(message):
    validate_envelope(message)
    try:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("Message cannot be encoded as UTF-8 JSON") from exc
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise FrameSizeError("Payload length outside 1-65536 bytes")
    return struct.pack("!I", len(payload)) + payload


# Buffered Decoding and Validation

def _reject_constant(value):
    raise ValueError(f"Non-JSON number: {value}")


class FrameBuffer:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        """Yield messages in stream order, retaining an incomplete final frame.

        Yielding preserves valid messages preceding a malformed frame in the
        same recv: callers dispatch them before the decoding exception occurs.
        """
        self.buffer.extend(data)
        while len(self.buffer) >= 4:
            length = struct.unpack("!I", self.buffer[:4])[0]
            if not 1 <= length <= MAX_PAYLOAD:
                raise ProtocolError("Payload length outside 1-65536 bytes")
            if len(self.buffer) < 4 + length:
                return
            payload = bytes(self.buffer[4:4 + length])
            del self.buffer[:4 + length]
            try:
                message = json.loads(payload.decode("utf-8"), parse_constant=_reject_constant)
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise ProtocolError("Invalid UTF-8 or JSON") from exc
            yield validate_envelope(message)


def decode_frame(frame):
    buffer = FrameBuffer()
    messages = list(buffer.feed(frame))
    if buffer.buffer or len(messages) != 1:
        raise ProtocolError("Expected exactly one complete frame")
    return messages[0]
