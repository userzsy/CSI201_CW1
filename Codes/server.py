"""Coordinate protocol, sessions and rooms in one raw TCP selectors loop.
在单线程事件循环中协调协议、会话与房间；启动参数为 --host、--port、--questions。
"""

# ============================================================
# 1. Imports and Configuration / 导入与配置
# ============================================================

import argparse
from dataclasses import dataclass, field
import selectors
import signal
import socket
import sys

from quizlib.game import RoomManager
from quizlib.protocol import (ApplicationError, ErrorCode as E, FrameBuffer,
                              MessageType as M, ProtocolError, encode_frame,
                              error, event, response)
from quizlib.quiz_loader import QuizValidationError, load_question_bank
from quizlib.session import SessionRegistry

MAX_OUTGOING = 1_048_576


# ============================================================
# 2. Connection and Server State / 连接与服务器状态
# ============================================================

@dataclass(eq=False)
class Connection:
    socket: socket.socket
    frames: FrameBuffer = field(default_factory=FrameBuffer)
    outgoing: bytearray = field(default_factory=bytearray)
    session: object = None
    closing: bool = False
    abort: bool = False


class QuizServer:
    def __init__(self, host, port, bank):
        self.host, self.port, self.bank = host, port, bank
        self.selector = selectors.DefaultSelector()
        self.sessions = SessionRegistry()
        self.connections = {}
        self.by_session = {}
        self.rooms = RoomManager(bank, self._emit)
        self.listener = None
        self.running = False

    # ========================================================
    # 3. Outgoing Buffers and Events / 发送缓冲区与事件
    # ========================================================

    def _interest(self, connection):
        flags = (0 if connection.closing else selectors.EVENT_READ)
        if connection.outgoing:
            flags |= selectors.EVENT_WRITE
        if flags:
            self.selector.modify(connection.socket, flags, connection)
        else:
            self._drop(connection)

    def _queue(self, connection, message):
        if connection.socket not in self.connections or connection.abort:
            return
        frame = encode_frame(message)
        if len(connection.outgoing) + len(frame) > MAX_OUTGOING:
            # Defer removal: an emit may occur inside an atomic room transition.
            # 房间状态可能正在切换，延后移除连接，避免中途修改成员。
            connection.abort = True
            return
        connection.outgoing.extend(frame)
        self._interest(connection)

    def _emit(self, session, kind, payload):
        connection = self.by_session.get(session.session_id)
        if connection is not None and not connection.closing:
            self._queue(connection, event(kind, session.session_id, payload))

    # ========================================================
    # 4. Connection Management / 连接管理
    # ========================================================

    def _accept(self):
        # Bound work per readiness notification so accept bursts cannot starve timers.
        # 每轮限制接入次数，让房间计时仍有机会执行。
        for _ in range(32):
            try:
                sock, _ = self.listener.accept()
            except BlockingIOError:
                return
            sock.setblocking(False)
            connection = Connection(sock)
            self.connections[sock] = connection
            self.selector.register(sock, selectors.EVENT_READ, connection)

    def _drop(self, connection):
        if self.connections.pop(connection.socket, None) is None:
            return
        try:
            self.selector.unregister(connection.socket)
        except (KeyError, ValueError):
            pass
        connection.socket.close()
        if connection.session is not None:
            self.by_session.pop(connection.session.session_id, None)
            self.sessions.remove(connection.session, self.rooms)

    # ========================================================
    # 5. Socket Reads and Writes / Socket 消息收发
    # ========================================================

    def _write(self, connection):
        try:
            sent = connection.socket.send(connection.outgoing)
        except BlockingIOError:
            return
        except OSError:
            self._drop(connection)
            return
        if sent == 0:
            self._drop(connection)
            return
        # Keep unsent bytes for the next writable notification.
        # 只移除实际发出的字节，剩余部分留待下次可写时继续发送。
        del connection.outgoing[:sent]
        self._interest(connection)

    def _read(self, connection):
        try:
            data = connection.socket.recv(65_536)
        except BlockingIOError:
            return
        except OSError:
            self._drop(connection)
            return
        if not data:
            self._drop(connection)
            return
        try:
            for message in connection.frames.feed(data):
                # Expired questions close before request processing.
                # 在处理请求前先关闭到期题目。
                self.rooms.tick()
                self._dispatch(connection, message)
                # Answer acknowledgement precedes early-close events.
                # 作答响应先排队，再发布提前结题事件。
                self.rooms.tick()
                if connection.closing or connection.abort:
                    break
        except ProtocolError as exc:
            self._queue(connection, error(None, self._session_id(connection), E.INVALID_MESSAGE, str(exc)))
            connection.closing = True
            self._interest(connection)

    @staticmethod
    def _session_id(connection):
        return connection.session.session_id if connection.session else None

    # ========================================================
    # 6. Request Handling / 请求处理
    # ========================================================

    def _dispatch(self, connection, message):
        kind, payload, request_id = message["type"], message["payload"], message["request_id"]
        try:
            if not kind.endswith("_REQUEST"):
                raise ApplicationError(E.INVALID_MESSAGE, "Clients may send requests only")
            if kind == M.LOGIN_REQUEST:
                if connection.session is not None or message["session_id"] is not None:
                    raise ApplicationError(E.INVALID_SESSION, "Login requires an unauthenticated connection")
                session = self.sessions.login(payload.get("user_id"), payload.get("name"))
                connection.session = session
                self.by_session[session.session_id] = connection
                self._queue(connection, response(M.LOGIN_RESPONSE, request_id, session.session_id,
                                                {"success": True, "session_id": session.session_id}))
                return
            session = connection.session
            if session is None or message["session_id"] != session.session_id:
                raise ApplicationError(E.INVALID_SESSION, "Session does not identify this connection")

            def reply(response_type, body):
                self._queue(connection, response(response_type, request_id, session.session_id, body))

            if kind == M.LIST_QUIZZES_REQUEST:
                reply(M.LIST_QUIZZES_RESPONSE, {"quizzes": self.rooms.list_quizzes()})
            elif kind == M.LIST_ROOMS_REQUEST:
                reply(M.LIST_ROOMS_RESPONSE, {"rooms": self.rooms.list_rooms()})
            elif kind == M.CREATE_ROOM_REQUEST:
                room = self.rooms.create(session, payload.get("quiz_id"))
                reply(M.CREATE_ROOM_RESPONSE, {"success": True, "room_code": room.room_code,
                                               "room": room.view()})
                self.rooms.status(room)
            elif kind == M.JOIN_ROOM_REQUEST:
                room = self.rooms.join(session, payload.get("room_code"))
                reply(M.JOIN_ROOM_RESPONSE, {"success": True, "room": room.view()})
                self.rooms.status(room)
            elif kind == M.PLAYER_LIST_REQUEST:
                reply(M.PLAYER_LIST_RESPONSE, {"players": self.rooms.current(session).player_list()})
            elif kind == M.READY_REQUEST:
                self.rooms.ready(session, payload.get("ready"))
            elif kind == M.START_QUIZ_REQUEST:
                self.rooms.start(session)
            elif kind == M.ANSWER_REQUEST:
                result = self.rooms.answer(session, payload.get("question_id"), payload.get("answer"))
                reply(M.ANSWER_RESPONSE, result)
            elif kind == M.LEADERBOARD_REQUEST:
                reply(M.LEADERBOARD_RESPONSE, {"leaderboard": self.rooms.current(session).leaderboard()})
            elif kind == M.LEAVE_ROOM_REQUEST:
                self.rooms.current(session)
                self.rooms.leave(session)
            elif kind == M.LOGOUT_REQUEST:
                # Release identity immediately, then drain already queued responses.
                # 立即释放身份，再发送已排队的响应并关闭连接。
                self.by_session.pop(session.session_id, None)
                self.sessions.remove(session, self.rooms)
                connection.session = None
                connection.closing = True
                self._interest(connection)
        except ApplicationError as exc:
            self._queue(connection, error(request_id, self._session_id(connection), exc.code, str(exc)))

    # ========================================================
    # 7. Selectors Event Loop / 非阻塞事件循环
    # ========================================================

    def serve_forever(self):
        try:
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listener.bind((self.host, self.port))
            self.listener.listen(128)
            self.listener.setblocking(False)
            self.port = self.listener.getsockname()[1]
            self.selector.register(self.listener, selectors.EVENT_READ, None)
            self.running = True
            print(f"SERVER_READY {self.host}:{self.port}", flush=True)
            while self.running:
                self.rooms.tick()
                for key, flags in self.selector.select(self.rooms.next_timeout()):
                    if not self.running:
                        break
                    if key.data is None:
                        self._accept()
                        continue
                    connection = key.data
                    if connection.socket not in self.connections:
                        continue
                    if flags & selectors.EVENT_READ:
                        self._read(connection)
                    if connection.socket in self.connections and flags & selectors.EVENT_WRITE:
                        self._write(connection)
                for connection in list(self.connections.values()):
                    if connection.abort:
                        self._drop(connection)
        finally:
            self.close()

    # ========================================================
    # 8. Graceful Shutdown / 正常关闭与清理
    # ========================================================

    def stop(self):
        self.running = False

    def close(self):
        self.running = False
        for connection in list(self.connections.values()):
            self._drop(connection)
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        self.rooms.clear()
        self.selector.close()


# ============================================================
# 9. Arguments and Program Entry / 参数与程序入口
# ============================================================

def port_number(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("port must be 1-65535")
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=port_number)
    parser.add_argument("--questions", required=True)
    args = parser.parse_args(argv)
    try:
        socket.inet_pton(socket.AF_INET, args.host)
        bank = load_question_bank(args.questions)
    except (OSError, QuizValidationError) as exc:
        print(f"STARTUP_ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    server = QuizServer(args.host, args.port, bank)

    def shutdown(signum, frame):
        server.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"SERVER_ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    print("SERVER_STOPPED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
