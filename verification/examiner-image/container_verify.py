import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

source = Path("/submission")
work = Path("/tmp/csi201-submission")


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


before = hashes(source)
shutil.copytree(source, work, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
assert hashes(work) == before
print(f"SOURCE_COPY_OK files={len(before)}; host mount is read-only; work copy matches byte-for-byte", flush=True)
os.chdir(work)
mode = sys.argv[1]
command = [sys.executable, "-m", "compileall", "-q", "."] if mode == "compile" else [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
print("CONTAINER_COMMAND " + " ".join(command), flush=True)
result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
print(result.stdout, end="", flush=True)
assert result.returncode == 0, result.returncode
assert hashes(source) == hashes(work) == before
if mode == "test":
    assert re.search(r"Ran 84 tests in [\d.]+s", result.stdout)
    assert re.search(r"(?m)^OK$", result.stdout)
    assert "... skipped " not in result.stdout
    for name in ("test_160_rooms_over_real_tcp_with_bounded_frames_and_reused_connection",
                 "test_ten_actual_clients_two_independent_rooms",
                 "test_submitted_cli_automatically_collects_all_160_rooms"):
        assert name in result.stdout
    print("FULL_SUITE_PASS total=84 passed=84 failed=0 skipped=0", flush=True)
else:
    print("COMPILEALL_PASS", flush=True)
