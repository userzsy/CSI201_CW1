import unittest

from tests import RunningSystem, bank_fixture


class PairedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.system = RunningSystem()
        self.addCleanup(self.system.close)

    def test_actual_submitted_cli_pair_complete_workflow(self):
        a, b = self.system.client("a"), self.system.client("b")
        a.send("/help")
        a.wait("/quizzes")
        a.send("/quizzes")
        catalogue = a.wait("LIST_QUIZZES_RESPONSE")["quizzes"]
        self.assertEqual(catalogue[0]["quiz_id"], "quiz0")
        self.assertNotIn("questions", catalogue[0])
        a.send("/create quiz0")
        code = a.wait("CREATE_ROOM_RESPONSE")["room_code"]
        b.send("/rooms")
        self.assertEqual(b.wait("LIST_ROOMS_RESPONSE")["rooms"][0]["room_code"], code)
        b.send(f"/join {code}")
        self.assertEqual(b.wait("JOIN_ROOM_RESPONSE")["room"]["room_code"], code)
        a.send("/players")
        self.assertEqual(len(a.wait("PLAYER_LIST_RESPONSE")["players"]), 2)
        a.send("/start")
        self.assertEqual(a.wait("ERROR_RESPONSE")["code"], "PLAYERS_NOT_READY")
        for client in (a, b):
            client.send("/ready")
        a.wait("PLAYER_STATUS_EVENT", lambda p: len(p["players"]) == 2 and all(x["ready"] for x in p["players"]))
        b.send("/start")
        self.assertEqual(b.wait("ERROR_RESPONSE")["code"], "NOT_ROOM_HOST")
        a.send("/start")
        for client in (a, b):
            self.assertEqual(client.wait("QUIZ_STARTED_EVENT")["total_questions"], 5)
        for i in range(5):
            for client in (a, b):
                question = client.wait("QUESTION_EVENT")
                self.assertEqual(question["question_id"], f"Q0_{i}")
                self.assertNotIn("answer", question)
                self.assertEqual(question["number"], i + 1)
            a.send("/answer A")
            self.assertTrue(a.wait("ANSWER_RESPONSE")["accepted"])
            a.send("/answer B")
            self.assertEqual(a.wait("ERROR_RESPONSE")["code"], "DUPLICATE_ANSWER")
            b.send("/answer B")
            b.wait("ANSWER_RESPONSE")
            ar, br = a.wait("QUESTION_RESULT_EVENT"), b.wait("QUESTION_RESULT_EVENT")
            self.assertEqual(ar["correct_answer"], "A")
            self.assertEqual(ar["points_awarded"], 100 + i)
            self.assertEqual(br["points_awarded"], 0)
        for client in (a, b):
            final = client.wait("QUIZ_FINISHED_EVENT")
            self.assertEqual(final["winner"]["user_id"], "a")
            self.assertEqual(final["final_leaderboard"][0]["score"], 510)
        a.send("/score")
        self.assertEqual(a.wait("LEADERBOARD_RESPONSE")["leaderboard"][0]["score"], 510)
        a.send("/leave")
        a.wait("PLAYER_STATUS_EVENT", lambda p: all(x["user_id"] != "a" for x in p["players"]))
        b.send("/leave")
        b.wait("ROOM_CLOSED_EVENT")
        for client in (a, b):
            client.send("/quit")
            self.assertEqual(client.process.wait(timeout=3), 0)

    def test_unexpected_disconnect_and_id_reuse_with_actual_client(self):
        a = self.system.client("a")
        b = self.system.client("b")
        a.send("/create quiz0")
        code = a.wait("CREATE_ROOM_RESPONSE")["room_code"]
        b.send(f"/join {code}")
        b.wait("JOIN_ROOM_RESPONSE")
        a.close()
        b.wait("PLAYER_STATUS_EVENT", lambda p: len(p["players"]) == 1 and p["players"][0]["is_host"])
        replacement = self.system.client("a")
        replacement.send("/rooms")
        self.assertEqual(replacement.wait("LIST_ROOMS_RESPONSE")["rooms"][0]["host_id"], "b")

    def test_server_disconnect_ends_client_even_with_stdin_open(self):
        client = self.system.client("a")
        self.system.server.close()
        client.wait("DISCONNECTED")
        self.assertEqual(client.process.wait(timeout=3), 0)

    def test_real_monotonic_timeout_and_missing_answer(self):
        # Real 5-second minimum deadline, independent of the fake-clock unit tests.
        self.system.close()
        bank = bank_fixture()
        bank["quizzes"][0]["questions"][0]["time_limit"] = 5
        self.system = RunningSystem(bank)
        self.addCleanup(self.system.close)
        a, b = self.system.client("a"), self.system.client("b")
        a.send("/create quiz0")
        code = a.wait("CREATE_ROOM_RESPONSE")["room_code"]
        b.send(f"/join {code}")
        b.wait("JOIN_ROOM_RESPONSE")
        for client in (a, b):
            client.send("/ready")
        a.wait("PLAYER_STATUS_EVENT", lambda p: all(x["ready"] for x in p["players"]))
        a.send("/start")
        a.wait("QUESTION_EVENT")
        a.send("/answer A")
        a.wait("ANSWER_RESPONSE")
        result = b.wait("QUESTION_RESULT_EVENT", timeout=8)
        self.assertIsNone(result["your_answer"])
        self.assertEqual(result["points_awarded"], 0)
        self.assertEqual(result["leaderboard"][0]["score"], 100)
