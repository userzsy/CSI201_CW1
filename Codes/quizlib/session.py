"""Track active identities and sessions for the server's event loop."""


# Imports

from dataclasses import dataclass
import secrets

from .protocol import ApplicationError, ErrorCode


# Session Data

@dataclass
class Session:
    user_id: str
    name: str
    session_id: str
    room_code: str | None = None


# Registry and Login Validation

class SessionRegistry:
    def __init__(self):
        self.by_user = {}
        self.by_session = {}

    def login(self, user_id, name):
        for key, value, limit in (("user_id", user_id, 64), ("name", name, 100)):
            if not isinstance(value, str) or not 1 <= len(value) <= limit or not value.strip() or not value.isprintable():
                raise ApplicationError(ErrorCode.INVALID_MESSAGE, f"{key} must be a nonblank printable string (1-{limit})")
        if user_id in self.by_user:
            raise ApplicationError(ErrorCode.DUPLICATE_USER, "User ID already has an active session")
        session_id = "s-" + secrets.token_hex(16)
        while session_id in self.by_session:
            session_id = "s-" + secrets.token_hex(16)
        session = Session(user_id, name, session_id)
        self.by_user[user_id] = session
        self.by_session[session_id] = session
        return session

    # Session Lookup

    def resolve(self, session_id):
        session = self.by_session.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.INVALID_SESSION, "Unknown session")
        return session

    # Logout and Membership Cleanup

    def remove(self, session, room_manager=None):
        if self.by_session.get(session.session_id) is not session:
            return
        if room_manager is not None:
            room_manager.leave(session)
        self.by_user.pop(session.user_id, None)
        self.by_session.pop(session.session_id, None)
        session.room_code = None
