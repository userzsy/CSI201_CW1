"""Load and validate the server's bank, then expose only public quiz metadata.
在服务器监听前校验完整题库；公开目录仅提供元数据，不包含题目或答案。
"""

# ============================================================
# 1. Imports and Schema Limits / 导入与格式限制
# ============================================================

import json
from pathlib import Path
import re

MAX_FILE_BYTES = 1_000_000  # decimal MB / 按十进制 MB 计算
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")


# ============================================================
# 2. Shared Validation Helpers / 通用校验工具
# ============================================================

class QuizValidationError(ValueError):
    pass


def _check(condition, path, rule):
    if not condition:
        raise QuizValidationError(f"{path}: {rule}")


def _object(value, path):
    _check(isinstance(value, dict), path, "must be an object")


def _text(value, path, minimum, maximum, visible=False):
    _check(isinstance(value, str), path, "must be a string")
    _check(minimum <= len(value) <= maximum, path, f"length must be {minimum}-{maximum}")
    if visible:
        _check(all(c.isprintable() for c in value), path, "must contain printable characters")
        _check(minimum == 0 or bool(value.strip()), path, "must not be blank")


def _identifier(value, path, seen):
    _check(isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None,
           path, "must be 1-32 letters, digits, underscores or hyphens")
    _check(value not in seen, path, "duplicate identifier")
    seen.add(value)


def _integer(value, path, minimum, maximum):
    _check(type(value) is int and minimum <= value <= maximum, path,
           f"must be an integer in {minimum}-{maximum} (not boolean)")


# ============================================================
# 3. Bank, Quiz and Question Validation / 文件、题库与题目校验
# ============================================================

def validate_bank(bank):
    _object(bank, "bank")
    _integer(bank.get("schema_version"), "schema_version", 1, 1)
    quizzes = bank.get("quizzes")
    _check(isinstance(quizzes, list) and 1 <= len(quizzes) <= 20, "quizzes", "must contain 1-20 quizzes")
    # Question IDs are unique across quizzes, not just within one quiz.
    # 题号必须在整个文件中唯一，因此所有题库共用同一个题号集合。
    quiz_ids, question_ids = set(), set()
    for i, quiz in enumerate(quizzes):
        path = f"quizzes[{i}]"
        _object(quiz, path)
        _identifier(quiz.get("quiz_id"), path + ".quiz_id", quiz_ids)
        _text(quiz.get("title"), path + ".title", 1, 100, True)
        _text(quiz.get("description"), path + ".description", 0, 300, True)
        questions = quiz.get("questions")
        _check(isinstance(questions, list) and 5 <= len(questions) <= 50,
               path + ".questions", "must contain 5-50 questions")
        for j, question in enumerate(questions):
            qp = f"{path}.questions[{j}]"
            _object(question, qp)
            _identifier(question.get("question_id"), qp + ".question_id", question_ids)
            _text(question.get("text"), qp + ".text", 1, 500, True)
            options = question.get("options")
            _check(isinstance(options, dict) and set(options) == set("ABCD"),
                   qp + ".options", "must contain exactly A, B, C, D")
            for key, value in options.items():
                _text(value, qp + ".options." + key, 1, 200)
            _check(isinstance(question.get("answer"), str) and question["answer"] in ("A", "B", "C", "D"),
                   qp + ".answer", "must be A, B, C or D")
            _integer(question.get("time_limit"), qp + ".time_limit", 5, 60)
            _integer(question.get("points"), qp + ".points", 1, 1000)
    return bank


# ============================================================
# 4. File Loading / 文件加载
# ============================================================

def load_question_bank(path):
    try:
        # Read at most one extra byte: no unbounded allocation for oversized files.
        # 最多多读一个字节来判断超限，避免把过大文件完整读入内存。
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        _check(0 < len(data) <= MAX_FILE_BYTES, "file", "must contain 1-1000000 bytes")
        bank = json.loads(data.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, QuizValidationError):
            raise
        raise QuizValidationError(f"Cannot load question bank: {exc}") from exc
    return validate_bank(bank)


# ============================================================
# 5. Public Quiz Information / 对外题库信息
# ============================================================

def public_quizzes(bank):
    return [{"quiz_id": q["quiz_id"], "title": q["title"], "description": q["description"],
             "question_count": len(q["questions"])} for q in bank["quizzes"]]
