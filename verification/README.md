# Verification record

The tested application baseline is `f30777a584357f016c947bf39ca3b9e7947772ce`: 59 original test methods plus 25 regressions. This documentation release retains those executable files and the raw logs; it does not rerun the complete suite. Recorded source hashes refer to that baseline, including its earlier README bytes.

Use the [operational guide](../docs/verification-and-demonstration-guide.md) to reproduce verification and the [demo runbook](examiner-image/demo-runbook.md) for recording commands. Host results are preliminary; each Docker result below belongs to its stated image and run.

## Windows Python 3.12

| Runtime | Passed | Failed | Skipped | Time | Evidence |
| --- | --- | --- | --- | --- | --- |
| Windows Python 3.12.14 | 83 | 0 | 1 | 36.237 s | [Final acceptance](final-acceptance-windows.txt) |

Compilation passed. The only skip was the POSIX SIGINT test, which passed in both Linux Docker environments. This uses the last complete run in the log, after final comment review. Follow [host test commands](../Codes/README.md#tests) for preliminary checks without Docker.

## Supplied Development Docker Environment

| Runtime | Passed | Failed | Skipped | Time | Evidence |
| --- | --- | --- | --- | --- | --- |
| Linux Python 3.12.16 | 84 | 0 | 0 | 20.090 s | [Final acceptance](final-acceptance-docker.txt) |

Compilation passed. The last complete run reused `csi201-cw1:latest`, ID `sha256:4e89089fe7c6bee76ee0c43f056b966a00a9c1db3cb0c0e323dba729c160ab3f`, without rebuilding or changing supplied inputs. The log also retains the earlier acceptance run.

From the repository root, the existing development Compose file mounts `Codes/` at `/code`:

```powershell
docker compose -f docker_env/compose.dev.yaml run --rm -T python --version
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
```

## Learning Mall Supplied Docker Environment

Completed on 2026-11-19 (Asia/Shanghai) against application baseline `f30777a584357f016c947bf39ca3b9e7947772ce`.
The user identified Learning Mall's `CW1 - Docker Env ZIP` as the official coursework attachment. It provides a Dockerfile, Compose configuration and the 50-question bank; it contains no prebuilt image archive.
This verification used the exact extracted Dockerfile, built with `--pull` under the separate local tag below. It verifies the officially supplied build environment, not a separately distributed prebuilt examiner image.

| Item | Verified value |
| --- | --- |
| Attachment / local archive | `CW1 - Docker Env ZIP` / `CSI201_CW1_Docker_Env.zip` |
| Archive SHA-256 | `dc20f0ed59437c46a91f4b5c04b029be7397a290d8ffb01ec9290e6e31e8c0ab` |
| Build source | Extracted supplied `CSI201_CW1_Docker_Env` directory; original paths retained in metadata |
| Local image | `csi201-cw1:learning-mall-local` |
| Image ID | `sha256:f76ee65c28d414ed11e626694c4508174bbae44a27c48f9db37863b731af6e92` |
| Base | `docker.m.daocloud.io/library/python:3.12-slim` |
| Resolved base digest | `sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b` |
| Runtime | Python 3.12.16; Linux/amd64; Docker engine 29.9.3 |
| Image configuration | Entrypoint `python`, working directory `/code`, no configured default command or volumes; default user, observed UID/GID 0 |

### Results

| Check | Result | Evidence |
| --- | --- | --- |
| Exact supplied Dockerfile build with `--pull` | Pass; separate tag; development image preserved | [Build output](examiner-image/build.txt), [metadata](examiner-image/image-metadata.txt) |
| Python 3.12 and required Standard Library imports | Pass; `STANDARD_LIBRARY_OK` | [Environment check](examiner-image/environment-check.txt) |
| Syntax compilation | Pass | [compileall](examiner-image/compileall.txt) |
| Complete suite | 84 passed, 0 failed, 0 skipped; 18.186 s | [Full output](examiner-image/unittest-full.txt) |
| P1 Unicode/startup regression | Pass | Full suite and invalid-bank CLI startup |
| P2 160-room pagination | 160 unique ordered rooms, 8 pages; maximum payload 15519 bytes | Full suite, including actual submitted CLI pagination |
| Ten clients / two rooms | Pass; actual submitted clients; independent deadlines, scores and events | `test_ten_actual_clients_two_independent_rooms` in full output |
| Official bank and CLI workflow | Pass; catalogue has five quizzes / fifty questions; complete ten-question Geography quiz | [CLI transcript](examiner-image/cli-smoke-test.txt) |
| Identity, error and shutdown checks | Pass; duplicate ID/answer rejection, ID reuse, SIGINT and listening-port release | CLI transcript |

Both compilation and the full suite used `--network none`, a read-only root filesystem and read-only host bind mounts. The 18 submitted source/data files were copied byte-for-byte into the container's writable `/tmp` filesystem before execution. No packages were installed.
The CLI rehearsal used a persistent container from the same image, the official bank at `/examiner-env/questions_50.json`, and only the actual submitted client/server entry points. It was driven through scripted stdin/stdout, not a substitute protocol client or a recorded video.
Alice answered D and Bob answered A throughout the complete Geography quiz; the observed final scores were Alice 200 and Bob 300. Per-question awards and the final leaderboard were checked against actual result events.

The development image `csi201-cw1:latest` retains ID `sha256:4e89089fe7c6bee76ee0c43f056b966a00a9c1db3cb0c0e323dba729c160ab3f`. Application files, supplied inputs, reference PDFs and historical logs were preserved. The temporary smoke container was removed.

Raw `.txt` evidence is retained verbatim, including empty CLI prompts and final blank lines. The directory's [Git attributes](examiner-image/.gitattributes) disable newline conversion and whitespace checks for those logs; Markdown documentation remains checked normally. The original filename `build.txt` is retained.

### Demonstration preparation

[Demo runbook](examiner-image/demo-runbook.md) retains preparation commands, Tasks 1–5 and the single 9:30 schedule. The [main guide](../docs/verification-and-demonstration-guide.md#team-video-responsibilities) assigns the agreed A–E roles. The already-executed [verification runner](examiner-image/container_verify.py) is retained unchanged from its original temporary location so a fresh checkout can reproduce compilation and the suite.
No final video or academic report was produced. Human interactive recording and the optional official-bank 60-second timeout scene remain rehearsal steps; the automated suite exercised real timeout behaviour with its controlled five-second bank.

## Acceptance checklist

All P1/P2 acceptance checks below passed in the recorded Windows, development Docker and Learning Mall full-suite runs. Only POSIX SIGINT skipped on Windows; it passed in Linux.
Test files are under [`Codes/tests/`](../Codes/tests/).

| ID | Result | Check | Executable evidence |
| --- | --- | --- | --- |
| P1-01 | Pass | High surrogate rejected | `test_quiz_loader`: `test_unpaired_surrogates_rejected_in_schema_strings_and_files` |
| P1-02 | Pass | Low surrogate rejected | Same test, low-surrogate subcases |
| P1-03 | Pass | Every option position rejects invalid Unicode | Same test, A-D subcases, in-memory and escaped JSON files |
| P1-04 | Pass | Title, description and question text validated | Same test, other required string subcases |
| P1-05 | Pass | Startup exits before listening | `test_server`: `test_invalid_unicode_bank_is_rejected_before_listening` checks process, error, readiness, port and socket constructor |
| P1-06 | Pass | Valid Chinese, English, Emoji and supplementary characters | `test_quiz_loader`: `test_valid_chinese_supplementary_and_nonprintable_options`; `test_protocol`: `test_chinese_and_supplementary_unicode_round_trip` |
| P1-07 | Pass | Existing framing regression preserved | Complete `test_protocol` suite, including surrogate encoding errors |
| P2-01 | Pass | Deterministic ordering | `test_game`: `test_listing_is_compact_sorted_and_cursor_filtered` |
| P2-02 | Pass | Cursor progress and complete stable dataset | Same test plus the 160-room TCP test |
| P2-03 | Pass | Full/playing rooms excluded | `test_game`: `test_listing_excludes_full_and_playing_rooms` |
| P2-04 | Pass | Compact listing; full create/join views preserved | Game listing tests, 160-room tests and original paired workflow |
| P2-05 | Pass | Exactly 160 unique, ordered rooms over real TCP | `test_server`: `test_160_rooms_over_real_tcp_with_bounded_frames_and_reused_connection` |
| P2-06 | Pass | One CLI command retrieves all pages and prints once | `test_client_server`: `test_submitted_cli_automatically_collects_all_160_rooms`; client accumulation test |
| P2-07 | Pass | Empty/single pages, invalid cursors, errors and disconnects | Complete `ClientPaginationTests`, game cursor validation and TCP invalid-cursor check |
| P2-08 | Pass | Connection reuse after pagination | Both 160-room tests query again on the same connection; CLI also quits normally |

Byte-size fallback tests force smaller temporary bounds to verify shrinking; production `MAX_PAYLOAD` remains 65,536.
Unexpected serialization failures and impossible individual overflows return `INTERNAL_ERROR`. Client tests also cover duplicate entries, overlapping commands, interleaved responses and lock order.

## Coursework regression

| Task | Coverage |
| --- | --- |
| 1: Startup and bank validation | Missing/malformed/schema-invalid banks, field bounds, global IDs, strict integers, Unicode and validation before socket creation |
| 2: Identity and connections | Login, duplicate ID rejection, connection-bound sessions, logout, disconnect and ID reuse |
| 3: Catalogue and rooms | Create/join/list/players/ready/start/leave, capacity, host rules and pagination |
| 4: Tournament play | Question order, real/fake-clock deadlines, scoring, late/duplicate/missing answers and final rankings |
| 5: Concurrency | `test_ten_actual_clients_two_independent_rooms`: ten submitted clients, independent 5/30-second deadlines, scores, events and progress |
| 6: Failure handling | Fragmented/coalesced TCP, malformed peers, partial sends, backpressure, disconnects and graceful shutdown |

The original full CLI pair is exercised as separate subprocesses. The 160-room fixture seeds valid records before starting the real `QuizServer` loop, then tests its TCP path and a submitted CLI client.
The Windows-only skip is POSIX SIGINT; Linux Docker must pass it. Any additional OS-denied networking skips would prevent a full-acceptance claim.

## Resolved findings

- **P1:** Option type/length checks previously admitted unpaired surrogates that failed during publication. `_text()` now checks strict UTF-8 for required bank text before startup. Options retain valid control characters and Unicode without replacements.
- **P2:** One full room list, including participants, could exceed one frame. Compact metadata and cursor pages now keep every response within the unchanged limit; the client merges pages automatically. Pages reflect live state without snapshot consistency.

## Code and documentation review

[Static review](final-review.txt) records the full source and documentation checks. All sixteen application/test files retain the verified P1/P2 executable logic; cleanup changed explanations and removed three unused test imports. The original 59 test methods and all 25 regressions remain intact.

The 160-room TCP acceptance test returned eight pages in all three environments, with a maximum JSON payload of **15,519 bytes**, excluding the four-byte header. Every room was unique and ordered, and the connection remained usable. The submitted CLI printed one complete list and then queried quizzes and quit normally.

The original ten-client/two-room test passed in all three environments, including independent deadlines, scores, events and room progress. Only Unicode fixtures retain Chinese source text; explanatory Markdown, comments and docstrings are English-only. Supplied inputs, reference PDFs and historical logs retain their original hashes.

## Historical evidence

These logs are retained unchanged and are not presented as current source hashes or fresh runs.

| Stage | Windows | Supplied Docker | Evidence |
| --- | --- | --- | --- |
| Initial implementation, `42f7ff5` | 58 passed, 1 skipped; 34.739 s | 59 passed; 19.514 s | [Host](local-tests.txt), [Docker](supplied-docker-tests.txt) |
| Documentation pass, based on `42f7ff5`, later committed as `d496648` | Prior summary: 58 passed, 1 skipped; 32.969 s | Not rerun for comments-only changes | Historical documentation summary only; no separate raw transcript retained |
| P1/P2 fix pass, based on `d496648` | 83 passed, 1 skipped; 36.976 s | 84 passed; 20.132 s | [Host](findings-fix-local-tests.txt), [Docker](findings-fix-docker-tests.txt) |

The P1/P2 socket test returned 160 rooms in eight pages, with a maximum payload of 15,519 bytes in both environments.
Original supporting files remain available: [build log](supplied-docker-build.txt), [source checks](source-checks.txt) and [baseline SHA-256 manifest](source-sha256.json).
The manifest identifies the original baseline bytes; it does not describe the current edited files.
One original PowerShell location diagnostic remains in the build log at line 2. It is retained verbatim as historical machine output, not as a translated project explanation.

## Outstanding limits

- No separate prebuilt examiner image/archive was supplied. This run verified the official Learning Mall Dockerfile; if a different image is later announced, repeat verification in that exact image.
- Windows native Ctrl+C and sustained network saturation have not been exercised. Shutdown is covered by the server API on Windows and SIGINT in Linux.
- There is no TLS, password authentication, persistence, resume, global room cap or idle timeout. Room pages do not provide a snapshot.
- Academic documentation, the demonstration video and the final submission ZIP remain separate deliverables.
