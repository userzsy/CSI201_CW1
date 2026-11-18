"""Share TCP framing and envelopes between the client and server.
为客户端和服务器提供统一的 TCP 帧、消息结构和错误定义。

Version 1: 4-byte network-order length + UTF-8 JSON object.
版本 1 使用四字节大端长度加 UTF-8 JSON 对象。

All six envelope fields are mandatory. Requests have request_id, direct
responses repeat it, and events have event_id instead. Unknown envelope members
are allowed; unknown message types and unsupported versions are rejected.
六个字段必须齐全；响应匹配请求 ID，事件使用事件 ID。允许额外字段，拒绝未知类型和版本。
"""

# ============================================================
# 1. Imports and Frame Limit / 导入与帧长度限制
# ============================================================

import json
import struct
import uuid
from enum import StrEnum

MAX_PAYLOAD = 65_536


# ============================================================
# 2. Message Types and Error Codes / 消息类型与错误码
# ============================================================

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


# ============================================================
# 3. Protocol and Application Errors / 协议错误与业务错误
# ============================================================

class ProtocolError(ValueError):
    """Unsafe frame/envelope: close this connection. 帧或消息结构不安全，关闭该连接。"""


class ApplicationError(ValueError):
    """Recoverable request error; keep the connection. 可恢复的请求错误，保留连接。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ============================================================
# 4. Common Envelope Validation / 统一消息结构校验
# ============================================================

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


# ============================================================
# 5. Request, Response and Event Helpers / 请求、响应与事件构造
# ============================================================

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


# ============================================================
# 6. Frame Encoding / 帧编码
# ============================================================

def encode_frame(message):
    validate_envelope(message)
    try:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("Message cannot be encoded as UTF-8 JSON") from exc
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ProtocolError("Payload length outside 1-65536 bytes")
    return struct.pack("!I", len(payload)) + payload


# ============================================================
# 7. Buffered Decoding and Validation / 缓冲解码与校验
# ============================================================

def _reject_constant(value):
    raise ValueError(f"Non-JSON number: {value}")


class FrameBuffer:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        """Yield messages in stream order, retaining an incomplete final frame.

        Yielding preserves valid messages preceding a malformed frame in the
        same recv: callers dispatch them before the decoding exception occurs.
        保留不完整的尾部；同一次接收中若后续帧有误，之前的有效消息仍先交给调用方。
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
