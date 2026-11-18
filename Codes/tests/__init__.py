"""Share bank fixtures and actual CLI subprocess helpers across the test suite.
提供可重复的题库夹具与子进程工具，集成测试运行项目实际的客户端和服务器入口。
"""

# ============================================================
# 1. Imports and Source Path / 导入与源码路径
# ============================================================

import copy
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ============================================================
# 2. Loopback Preflight and Bank Fixtures / 回环检查与题库夹具
# ============================================================

def require_loopback():
    """Skip only an OS permission denial, never a failed application test.

    Windows managed runners can forbid TCP even on loopback (WSAEACCES 10013).
    All these tests execute normally in an unrestricted Linux Docker container.
    只跳过操作系统明确禁止回环 TCP 的情况；应用自身失败仍应报错。
    允许网络的 Linux 容器会正常执行这些测试。
    """
    with socket.socket() as listener, socket.socket() as client:
        listener.settimeout(1)
        client.settimeout(1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        result = client.connect_ex(listener.getsockname())
        if result in (10013, 13, 1):
            raise unittest.SkipTest(f"Runner denies loopback TCP (OS error {result}); rerun in Docker")
        if result:
            raise RuntimeError(f"Loopback preflight failed with OS error {result}")
        accepted, _ = listener.accept()
        accepted.close()


def bank_fixture():
    return {"schema_version": 1, "quizzes": [
        {"quiz_id": f"quiz{k}", "title": f"Quiz {k}", "description": "Test bank",
         "questions": [{"question_id": f"Q{k}_{i}", "text": f"Question {k}/{i}",
                        "options": {c: f"Option {c}" for c in "ABCD"},
                        "answer": "A", "time_limit": 30, "points": 100 + i}
                       for i in range(5)]} for k in range(2)]}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ============================================================
# 3. CLI Subprocess Input and Output / CLI 子进程输入输出
# ============================================================

class Program:
    def __init__(self, script, args):
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1")
        self.process = subprocess.Popen([sys.executable, str(ROOT / script)] + args,
                                        cwd=ROOT, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", env=env)
        self.lines = queue.Queue()
        self.backlog = []
        self.transcript = []
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            line = line.rstrip("\n")
            self.transcript.append(line)
            self.lines.put(line)
        self.lines.put(None)

    def wait(self, prefix, predicate=lambda payload: True, timeout=8):
        deadline = time.monotonic() + timeout
        while True:
            for i, line in enumerate(self.backlog):
                if line.startswith(prefix):
                    body = self._body(line)
                    if predicate(body):
                        self.backlog.pop(i)
                        return body
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"Timed out waiting for {prefix}: {self.transcript[-12:]}")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise AssertionError(f"Timed out waiting for {prefix}: {self.transcript[-12:]}") from exc
            if line is None:
                raise AssertionError(f"Program exited before {prefix}: {self.transcript}")
            self.backlog.append(line)

    @staticmethod
    def _body(line):
        text = line.partition(" ")[2]
        try:
            return json.loads(text)
        except ValueError:
            return text

    def send(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


# ============================================================
# 4. Server and Client Lifecycle / 服务器与客户端测试生命周期
# ============================================================

class RunningSystem:
    def __init__(self, bank=None):
        require_loopback()
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "questions.json"
        self.bank = copy.deepcopy(bank if bank is not None else bank_fixture())
        self.path.write_text(json.dumps(self.bank), encoding="utf-8")
        self.port = free_port()
        self.programs = []
        self.server = Program("server.py", ["--host", "127.0.0.1", "--port", str(self.port),
                                             "--questions", str(self.path)])
        self.programs.append(self.server)
        try:
            self.server.wait("SERVER_READY")
        except BaseException:
            self.close()
            raise

    def client(self, user_id):
        program = Program("client.py", ["--server", "127.0.0.1", "--port", str(self.port),
                                         "--id", user_id, "--name", "Player " + user_id])
        self.programs.append(program)
        program.wait("LOGIN_RESPONSE")
        return program

    def close(self):
        for program in reversed(self.programs):
            program.close()
        self.directory.cleanup()
