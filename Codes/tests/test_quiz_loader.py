"""Check the bank loader against required fields, bounds and file failures."""


# Imports and Bank Setup

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests import ROOT, bank_fixture
from quizlib.quiz_loader import (MAX_FILE_BYTES, QuizValidationError,
                                 load_question_bank, public_quizzes, validate_bank)


class QuizLoaderTests(unittest.TestCase):
    def setUp(self):
        self.bank = bank_fixture()

    # Accepted Banks and File Errors

    def test_valid_one_and_multiple_quizzes(self):
        self.assertIs(validate_bank(self.bank), self.bank)
        self.bank["quizzes"] = self.bank["quizzes"][:1]
        validate_bank(self.bank)

    def test_original_bank_is_five_quizzes_fifty_questions(self):
        bank = load_question_bank(ROOT / "questions.json")
        self.assertEqual(len(bank["quizzes"]), 5)
        self.assertEqual(sum(len(q["questions"]) for q in bank["quizzes"]), 50)

    def test_file_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bank.json"
            with self.assertRaises(QuizValidationError):
                load_question_bank(path)
            for value in (b"", b"\xff", b"{", b"[]", b" " * (MAX_FILE_BYTES + 1)):
                path.write_bytes(value)
                with self.subTest(value=value[:10]), self.assertRaises(QuizValidationError):
                    load_question_bank(path)

    # Required Fields, Types and Ranges

    def test_missing_every_required_field(self):
        for target, keys in (("bank", ("schema_version", "quizzes")),
                             ("quiz", ("quiz_id", "title", "description", "questions")),
                             ("question", ("question_id", "text", "options", "answer", "time_limit", "points"))):
            for key in keys:
                bank = copy.deepcopy(self.bank)
                obj = bank if target == "bank" else bank["quizzes"][0]
                if target == "question":
                    obj = obj["questions"][0]
                del obj[key]
                with self.subTest(target=target, key=key), self.assertRaises(QuizValidationError):
                    validate_bank(bank)

    def test_top_level_and_quiz_count(self):
        for value in (None, [], "x"):
            with self.assertRaises(QuizValidationError):
                validate_bank(value)
        for quizzes in (None, {}, [], self.bank["quizzes"] * 11):
            with self.assertRaises(QuizValidationError):
                validate_bank(dict(self.bank, quizzes=quizzes))
        for version in (True, 1.0, "1", 0, 2):
            with self.assertRaises(QuizValidationError):
                validate_bank(dict(self.bank, schema_version=version))

    def test_quiz_fields_wrong_types_and_bounds(self):
        values = {"quiz_id": [None, [], "", "a b", "x" * 33],
                  "title": [None, "", " " * 5, "x" * 101, "a\nb"],
                  "description": [None, "x" * 301, "a\tb"],
                  "questions": [None, {}, [], self.bank["quizzes"][0]["questions"][:4],
                                self.bank["quizzes"][0]["questions"] * 11]}
        for key, invalid in values.items():
            for value in invalid:
                bank = copy.deepcopy(self.bank)
                bank["quizzes"][0][key] = value
                with self.subTest(key=key, value=str(value)[:40]), self.assertRaises(QuizValidationError):
                    validate_bank(bank)

    def test_question_fields_wrong_types_and_bounds(self):
        values = {"question_id": [False, {}, "", "x y", "x" * 33],
                  "text": [False, "", " ", "x" * 501, "a\nb"],
                  "options": [[], {}, {"A": "x", "B": "x", "C": "x"},
                              dict.fromkeys("ABCDE", "x"), dict.fromkeys("ABCD", ""),
                              dict.fromkeys("ABCD", 1), dict.fromkeys("ABCD", "x" * 201)],
                  "answer": [None, [], "", "a", "E", "AB"],
                  "time_limit": [True, 5.0, "5", 4, 61],
                  "points": [False, 1.0, "1", 0, 1001]}
        for key, invalid in values.items():
            for value in invalid:
                bank = copy.deepcopy(self.bank)
                bank["quizzes"][0]["questions"][0][key] = value
                with self.subTest(key=key, value=str(value)[:30]), self.assertRaises(QuizValidationError):
                    validate_bank(bank)

    # Global IDs, Extra Fields and Boundaries

    def test_duplicates_are_global(self):
        self.bank["quizzes"][1]["quiz_id"] = self.bank["quizzes"][0]["quiz_id"]
        with self.assertRaisesRegex(QuizValidationError, "duplicate"):
            validate_bank(self.bank)
        self.bank = bank_fixture()
        self.bank["quizzes"][1]["questions"][0]["question_id"] = "Q0_0"
        with self.assertRaisesRegex(QuizValidationError, "duplicate"):
            validate_bank(self.bank)

    def test_extra_members_allowed_except_options(self):
        self.bank["future"] = {}
        self.bank["quizzes"][0]["future"] = []
        self.bank["quizzes"][0]["questions"][0]["future"] = True
        validate_bank(self.bank)

    def test_public_metadata_never_contains_question_data(self):
        for quiz in public_quizzes(self.bank):
            self.assertEqual(set(quiz), {"quiz_id", "title", "description", "question_count"})

    def test_boundary_values(self):
        for quiz in self.bank["quizzes"]:
            quiz["description"] = ""
            for question in quiz["questions"]:
                question["time_limit"] = 5
                question["points"] = 1
        validate_bank(self.bank)
        for quiz in self.bank["quizzes"]:
            for question in quiz["questions"]:
                question["time_limit"] = 60
                question["points"] = 1000
        validate_bank(self.bank)

    # UTF-8 Regression Cases

    def test_unpaired_surrogates_rejected_in_schema_strings_and_files(self):
        cases = [("title", None), ("description", None), ("text", None)]
        cases += [("options", key) for key in "ABCD"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bank.json"
            for field, option in cases:
                for surrogate in ("\ud800", "\udfff"):
                    bank = copy.deepcopy(self.bank)
                    quiz = bank["quizzes"][0]
                    target = quiz if field in ("title", "description") else quiz["questions"][1]
                    if option is None:
                        target[field] = "before" + surrogate + "after"
                    else:
                        target[field][option] = surrogate
                    with self.subTest(field=field, option=option, surrogate=ascii(surrogate)):
                        with self.assertRaisesRegex(QuizValidationError, "valid UTF-8 text"):
                            validate_bank(bank)
                        # Escapes keep the file itself valid UTF-8 while its decoded value is invalid.
                        path.write_bytes(json.dumps(bank, ensure_ascii=True).encode("utf-8"))
                        with self.assertRaisesRegex(QuizValidationError, "valid UTF-8 text"):
                            load_question_bank(path)

    def test_valid_chinese_supplementary_and_nonprintable_options(self):
        quiz = self.bank["quizzes"][0]
        quiz["title"] = "中文与 English 😀"
        quiz["description"] = "Supplementary: \U00010437"
        question = quiz["questions"][0]
        question["text"] = "请选择 😀 / \U00010437"
        question["options"] = {"A": "中文", "B": "English", "C": "😀\U00010437", "D": "\t\n"}
        validate_bank(self.bank)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bank.json"
            for escaped in (True, False):
                path.write_bytes(json.dumps(self.bank, ensure_ascii=escaped).encode("utf-8"))
                self.assertEqual(load_question_bank(path), self.bank)
