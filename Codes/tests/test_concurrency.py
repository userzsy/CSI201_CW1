"""Run ten submitted clients across two independently progressing rooms."""


# Imports

import json
import time
import unittest

from tests import RunningSystem, bank_fixture


# Client and Room Setup

class ConcurrencyTests(unittest.TestCase):
    def test_ten_actual_clients_two_independent_rooms(self):
        bank = bank_fixture()
        bank["quizzes"][0]["questions"][0]["time_limit"] = 5
        system = RunningSystem(bank)
        self.addCleanup(system.close)
        clients = [system.client(f"u{i:02d}") for i in range(10)]
        groups = (clients[:5], clients[5:])
        codes = []
        for k, group in enumerate(groups):
            group[0].send(f"/create quiz{k}")
            code = group[0].wait("CREATE_ROOM_RESPONSE")["room_code"]
            codes.append(code)
            for client in group[1:]:
                client.send(f"/join {code}")
                client.wait("JOIN_ROOM_RESPONSE")
            for client in group:
                client.send("/ready")
            group[0].wait("PLAYER_STATUS_EVENT", lambda p: len(p["players"]) == 5 and all(x["ready"] for x in p["players"]))

        # Independent Real Deadlines

        started = time.monotonic()
        for group in groups:
            group[0].send("/start")
        for k, group in enumerate(groups):
            for client in group:
                self.assertEqual(client.wait("QUIZ_STARTED_EVENT")["quiz_id"], f"quiz{k}")
                question = client.wait("QUESTION_EVENT")
                self.assertEqual(question["question_id"], f"Q{k}_0")
                self.assertEqual(question["time_limit"], 5 if k == 0 else 30)
        # A's real five-second timeout must not close B's thirty-second question.
        for client in groups[0]:
            result = client.wait("QUESTION_RESULT_EVENT")
            self.assertEqual(result["question_id"], "Q0_0")
            self.assertIsNone(result["your_answer"])
            self.assertEqual(result["points_awarded"], 0)
            self.assertEqual(client.wait("QUESTION_EVENT")["question_id"], "Q0_1")
        self.assertGreaterEqual(time.monotonic() - started, 4.9)
        for client in groups[1]:
            client.send("/score")
            client.wait("LEADERBOARD_RESPONSE")
            self.assertFalse(any(line.startswith("QUESTION_RESULT_EVENT ") for line in client.transcript))

        # Independent Progress and Scores

        # Room A completes its remaining questions while Room B stays on its first.
        for i in range(1, 5):
            for client in groups[0]:
                client.send("/answer A")
            for client in groups[0]:
                client.wait("ANSWER_RESPONSE")
                result = client.wait("QUESTION_RESULT_EVENT")
                self.assertEqual(result["question_id"], f"Q0_{i}")
                self.assertEqual(len(result["leaderboard"]), 5)
                if i < 4:
                    self.assertEqual(client.wait("QUESTION_EVENT")["question_id"], f"Q0_{i + 1}")
        for client in groups[0]:
            self.assertEqual(client.wait("QUIZ_FINISHED_EVENT")["winner"]["score"], 410)
        for client in clients:
            self.assertIsNone(client.process.poll())
        for client in groups[1]:
            client.send("/score")
            board = client.wait("LEADERBOARD_RESPONSE")["leaderboard"]
            self.assertEqual(len(board), 5)
            self.assertTrue(all(row["score"] == 0 for row in board))

        # Disconnect Recovery and Event Isolation

        # Four answers plus one disconnected unanswered player close Room B early.
        for client in groups[1][:-1]:
            client.send("/answer B")
            client.wait("ANSWER_RESPONSE")
        groups[1][-1].close()
        for client in groups[1][:-1]:
            result = client.wait("QUESTION_RESULT_EVENT")
            self.assertEqual(result["question_id"], "Q1_0")
            self.assertEqual(result["points_awarded"], 0)
            self.assertEqual(client.wait("QUESTION_EVENT")["question_id"], "Q1_1")
        groups[0][0].send("/score")
        self.assertEqual(groups[0][0].wait("LEADERBOARD_RESPONSE")["leaderboard"][0]["score"], 410)
        # Inspect every displayed event, not only the ones consumed by wait().
        for k, group in enumerate(groups):
            for client in group:
                for line in list(client.transcript):
                    if line.startswith(("QUESTION_EVENT ", "QUESTION_RESULT_EVENT ")):
                        payload = json.loads(line.partition(" ")[2])
                        self.assertTrue(payload["question_id"].startswith(f"Q{k}_"))
                    if line.startswith("PLAYER_STATUS_EVENT "):
                        self.assertEqual(json.loads(line.partition(" ")[2])["room_code"], codes[k])
