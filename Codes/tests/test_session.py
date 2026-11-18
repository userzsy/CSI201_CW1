"""Test SessionRegistry identity rules and its RoomManager cleanup interface.
检查会话注册、身份复用与房间清理的配合，不涉及 Socket 连接。
"""

# ============================================================
# 1. Imports and Registry Setup / 导入与注册表初始化
# ============================================================

import unittest

from quizlib.protocol import ApplicationError
from quizlib.session import SessionRegistry
from quizlib.game import RoomManager
from tests import bank_fixture


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.registry = SessionRegistry()

    # ========================================================
    # 2. Identity Lifecycle and Invalid Input / 身份生命周期与非法输入
    # ========================================================

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
        # Repeated stale cleanup cannot remove a replacement session.
        # 重复清理旧会话不能误删新会话。
        self.registry.remove(session)
        self.assertIs(self.registry.by_user["123"], replacement)

    def test_invalid_identity_and_session(self):
        for value in (None, [], 3, "", " ", "x\ny", "x" * 101):
            with self.subTest(value=value), self.assertRaises(ApplicationError):
                self.registry.login(value, "Alice")
            with self.subTest(name=value), self.assertRaises(ApplicationError):
                self.registry.login("id", value)
        with self.assertRaises(ApplicationError):
            self.registry.resolve("unknown")

    # ========================================================
    # 3. Disconnect and Room Membership / 断线与房间成员清理
    # ========================================================

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
