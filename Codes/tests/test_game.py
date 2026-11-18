"""Test RoomManager and QuizEngine with fixtures and a controlled clock.
使用题库夹具和可控时钟检查房间、状态、计分与隔离；真实计时见集成测试。
"""

# ============================================================
# 1. Imports and Test Setup / 导入与测试初始化
# ============================================================

import unittest

from quizlib.game import GameState, RoomManager
from quizlib.protocol import ApplicationError, MessageType as M
from quizlib.session import SessionRegistry
from tests import bank_fixture


class GameTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.events = []
        self.manager = RoomManager(bank_fixture(), lambda *args: self.events.append(args), lambda: self.now)
        registry = SessionRegistry()
        self.players = [registry.login(str(i), f"Player {i}") for i in range(12)]
        self.a, self.b = self.players[:2]
        self.room = self.manager.create(self.a, "quiz0")
        self.manager.join(self.b, self.room.room_code)

    # ========================================================
    # 2. Reusable Game Actions / 可复用的游戏测试操作
    # ========================================================

    def assert_error(self, code, function, *args):
        with self.assertRaises(ApplicationError) as failure:
            function(*args)
        self.assertEqual(failure.exception.code, code)

    def start(self):
        self.manager.ready(self.a, True)
        self.manager.ready(self.b, True)
        self.manager.start(self.a)

    def answer_both(self, a="A", b="B"):
        qid = self.room.quiz["questions"][self.room.question_index]["question_id"]
        self.manager.answer(self.a, qid, a)
        self.manager.answer(self.b, qid, b)
        self.manager.tick()

    # ========================================================
    # 3. Lobby Rules and State Transitions / 大厅规则与状态转换
    # ========================================================

    def test_room_creation_listing_and_host(self):
        self.assertEqual(self.room.host_id, self.a.user_id)
        self.assertEqual(self.manager.list_rooms()[0]["player_count"], 2)
        self.assertEqual(self.manager.list_quizzes()[0]["quiz_id"], "quiz0")
        self.assert_error("ALREADY_IN_ROOM", self.manager.create, self.a, "quiz0")
        self.assert_error("QUIZ_NOT_FOUND", self.manager.create, self.players[2], "missing")
        self.assert_error("ROOM_NOT_FOUND", self.manager.join, self.players[2], "missing")

    def test_room_capacity_and_unique_codes(self):
        for player in self.players[2:10]:
            self.manager.join(player, self.room.room_code)
        self.assert_error("ROOM_FULL", self.manager.join, self.players[10], self.room.room_code)
        second = self.manager.create(self.players[10], "quiz1")
        self.assertNotEqual(second.room_code, self.room.room_code)
        # Full rooms are not joinable.
        # 已满员的房间不列入可加入列表。
        self.assertEqual(len(self.manager.list_rooms()), 1)

    def test_readiness_start_guards(self):
        self.assert_error("PLAYERS_NOT_READY", self.manager.start, self.a)
        self.manager.ready(self.a, True)
        self.assert_error("PLAYERS_NOT_READY", self.manager.start, self.a)
        self.manager.ready(self.b, True)
        self.assert_error("NOT_ROOM_HOST", self.manager.start, self.b)
        self.manager.ready(self.b, False)
        self.assertFalse(self.room.players[self.b.user_id].ready)
        self.assert_error("INVALID_MESSAGE", self.manager.ready, self.a, 1)
        self.manager.leave(self.b)
        self.assert_error("PLAYERS_NOT_READY", self.manager.start, self.a)

    def test_state_transitions_and_no_answer_leakage(self):
        self.start()
        self.assertEqual(self.room.state, GameState.QUESTION_OPEN)
        self.assertEqual(self.room.deadline, 130.0)
        self.assertFalse(self.manager.list_rooms())
        question = next(payload for _, kind, payload in self.events if kind == M.QUESTION_EVENT)
        self.assertNotIn("answer", question)
        self.assertEqual(question["number"], 1)
        self.assert_error("INVALID_STATE", self.manager.ready, self.a, True)
        self.assert_error("INVALID_STATE", self.manager.start, self.a)
        self.assert_error("INVALID_STATE", self.manager.join, self.players[2], self.room.room_code)

    # ========================================================
    # 4. Answers, Deadlines and Ranking / 作答、截止时间与排名
    # ========================================================

    def test_correct_wrong_and_personalized_results(self):
        self.start()
        self.answer_both()
        self.assertEqual(self.room.players["0"].score, 100)
        self.assertEqual(self.room.players["1"].score, 0)
        self.assertEqual(self.room.players["0"].correct_answers, 1)
        results = {s.user_id: p for s, kind, p in self.events if kind == M.QUESTION_RESULT_EVENT}
        self.assertEqual(results["0"]["your_answer"], "A")
        self.assertEqual(results["1"]["your_answer"], "B")
        self.assertEqual(results["0"]["points_awarded"], 100)
        self.assertEqual(results["1"]["points_awarded"], 0)
        self.assertEqual(results["0"]["correct_answer"], "A")

    def test_invalid_and_duplicate_answer_do_not_corrupt_record(self):
        self.start()
        for qid, answer in (("bad", "A"), ("Q0_0", "a"), ([], "A"), ("Q0_0", [])):
            self.assert_error("INVALID_ANSWER", self.manager.answer, self.a, qid, answer)
        self.assertFalse(self.room.answers)
        self.manager.answer(self.a, "Q0_0", "A")
        self.assert_error("DUPLICATE_ANSWER", self.manager.answer, self.a, "Q0_0", "B")
        self.assertEqual(self.room.answers, {"0": "A"})

    def test_exact_deadline_late_and_missing_answers(self):
        self.start()
        self.manager.answer(self.a, "Q0_0", "A")
        self.now = self.room.deadline
        self.assert_error("QUESTION_CLOSED", self.manager.answer, self.b, "Q0_0", "A")
        self.manager.tick()
        self.assertEqual(self.room.question_index, 1)
        self.assertEqual(self.room.players["0"].score, 100)
        self.assertEqual(self.room.players["1"].score, 0)
        self.assert_error("QUESTION_CLOSED", self.manager.answer, self.b, "Q0_0", "A")

    def test_does_not_close_before_deadline_with_missing_answer(self):
        self.start()
        self.now = 129.999
        self.manager.tick()
        self.assertEqual(self.room.question_index, 0)
        self.assertGreater(self.manager.next_timeout(), 0)

    def test_early_close_and_final_winner(self):
        self.start()
        for _ in range(5):
            self.answer_both()
        self.assertEqual(self.room.state, GameState.FINISHED)
        self.assertIsNone(self.room.deadline)
        self.assertEqual(self.room.leaderboard()[0]["score"], 510)
        final = next(p for _, kind, p in self.events if kind == M.QUIZ_FINISHED_EVENT)
        self.assertEqual(final["winner"]["user_id"], "0")
        self.assertEqual(final["final_leaderboard"], self.room.leaderboard())
        self.manager.tick()
        self.assertEqual(self.room.leaderboard()[0]["score"], 510)

    def test_leaderboard_tie_breaking(self):
        self.room.players["1"].score = 100
        self.room.players["0"].score = 100
        self.room.players["1"].correct_answers = 2
        self.assertEqual(self.room.leaderboard()[0]["user_id"], "1")
        self.room.players["0"].correct_answers = 2
        self.assertEqual(self.room.leaderboard()[0]["user_id"], "0")

    # ========================================================
    # 5. Departure Cleanup and Room Isolation / 离开清理与房间隔离
    # ========================================================

    def test_lobby_host_transfer_and_empty_room_cleanup(self):
        self.manager.leave(self.a)
        self.assertEqual(self.room.host_id, self.b.user_id)
        self.assertIsNone(self.a.room_code)
        self.manager.leave(self.b)
        self.assertFalse(self.manager.rooms)
        self.assertFalse(self.manager.engines)
        self.assertEqual(self.events[-1][1], M.ROOM_CLOSED_EVENT)

    def test_disconnect_during_play_keeps_scores_and_unblocks(self):
        self.start()
        self.answer_both("A", "A")
        self.manager.answer(self.b, "Q0_1", "A")
        self.manager.leave(self.a)
        self.manager.tick()
        self.assertEqual(self.room.question_index, 2)
        self.assertFalse(self.room.players["0"].active)
        self.assertEqual(self.room.players["0"].score, 100)
        self.assertEqual(self.room.players["1"].score, 201)
        self.manager.leave(self.b)
        self.assertFalse(self.manager.rooms)

    def test_two_rooms_have_independent_deadlines_answers_and_events(self):
        self.start()
        c, d = self.players[2:4]
        other = self.manager.create(c, "quiz1")
        self.manager.join(d, other.room_code)
        self.manager.ready(c, True)
        self.manager.ready(d, True)
        self.now += 3
        self.manager.start(c)
        self.assertEqual(other.deadline - self.room.deadline, 3)
        self.assert_error("INVALID_ANSWER", self.manager.answer, c, "Q0_0", "A")
        self.answer_both()
        self.assertEqual(other.question_index, 0)
        self.assertEqual(other.answers, {})
        self.assertEqual(other.players[c.user_id].score, 0)
        for session, kind, payload in self.events:
            if kind == M.QUESTION_EVENT:
                expected = "Q0_" if session in (self.a, self.b) else "Q1_"
                self.assertTrue(payload["question_id"].startswith(expected))
        self.manager.clear()
        self.assertTrue(all(s.room_code is None for s in self.players))
