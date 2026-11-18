import unittest

from quizlib.protocol import ApplicationError
from quizlib.session import SessionRegistry
from quizlib.game import RoomManager
from tests import bank_fixture


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.registry = SessionRegistry()

    def test_login_lookup_logout_and_reuse(self):
        session = self.registry.login("123", "Alice")
        self.assertIs(self.registry.resolve(session.session_id), session)
        with self.assertRaises(ApplicationError) as failure:
            self.registry.login("123", "Bob")
        self.assertEqual(failure.exception.code, "DUPLICATE_USER")
        self.registry.remove(session)
        with self.assertRaises(ApplicationError):
            self.registry.resolve(session.session_id)
        replacement = self.registry.login("123", "Alice")
        self.assertNotEqual(replacement.session_id, session.session_id)
        self.registry.remove(session)  # repeated stale cleanup cannot remove replacement
        self.assertIs(self.registry.by_user["123"], replacement)

    def test_invalid_identity_and_session(self):
        for value in (None, [], 3, "", " ", "x\ny", "x" * 101):
            with self.subTest(value=value), self.assertRaises(ApplicationError):
                self.registry.login(value, "Alice")
            with self.subTest(name=value), self.assertRaises(ApplicationError):
                self.registry.login("id", value)
        with self.assertRaises(ApplicationError):
            self.registry.resolve("unknown")

    def test_disconnect_cleans_room_membership(self):
        manager = RoomManager(bank_fixture(), lambda *args: None)
        a = self.registry.login("a", "Alice")
        b = self.registry.login("b", "Bob")
        room = manager.create(a, "quiz0")
        manager.join(b, room.room_code)
        self.registry.remove(a, manager)
        self.assertIsNone(a.room_code)
        self.assertEqual(room.host_id, "b")
        self.assertNotIn("a", room.players)
        self.registry.remove(b, manager)
        self.assertFalse(manager.rooms)
