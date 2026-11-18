# Verification record

## Final acceptance

The final checks cover the P1/P2 implementation, English-only explanations and the [implemented protocol](../docs/protocol-design.md).
All 59 original test methods are retained, with 25 additional regressions: 84 tests in total. Unicode fixtures and question-bank data are preserved.

| Environment | Passed | Failed | Skipped | Time | Evidence |
| --- | --- | --- | --- | --- | --- |
| Windows Python 3.12.14 | 83 | 0 | 1 | 36.237 s | [Complete output](final-acceptance-windows.txt) |
| Supplied Docker, Linux Python 3.12.16 | 84 | 0 | 0 | 20.090 s | [Complete output](final-acceptance-docker.txt) |
| Official examiner image | Not run | — | — | — | Published image and tag not confirmed |

Host results are preliminary; supplied-container results are identified separately. No official examiner-image success is claimed.
The result table uses the last complete run after final comment review; the logs also retain the earlier acceptance run.
The supplied image is reused without changing Docker inputs or rebuilding:

```text
csi201-cw1:latest
sha256:4e89089fe7c6bee76ee0c43f056b966a00a9c1db3cb0c0e323dba729c160ab3f
```

## Commands

Windows, from `Codes/`:

```powershell
..\.venv\Scripts\python.exe --version
..\.venv\Scripts\python.exe -m compileall -q .
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Supplied Docker, from the repository root:

```powershell
docker compose -f docker_env/compose.dev.yaml run --rm -T python --version
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
```

## Acceptance checklist

All P1/P2 acceptance checks below passed in both full-suite runs. Compilation passed in both environments; only POSIX SIGINT skipped on Windows and it passed in Linux.
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

The 160-room TCP acceptance test returned eight pages in both environments, with a maximum JSON payload of **15,519 bytes**, excluding the four-byte header. Every room was unique and ordered, and the connection remained usable. The submitted CLI printed one complete list and then queried quizzes and quit normally.

The original ten-client/two-room test passed in both full runs, including independent deadlines, scores, events and room progress. Only Unicode fixtures retain Chinese source text; explanatory Markdown, comments and docstrings are English-only. Supplied inputs, reference PDFs and historical logs retain their original hashes.

## Historical evidence

These logs are retained unchanged and are not presented as current source hashes or fresh runs.

| Stage | Windows | Supplied Docker | Evidence |
| --- | --- | --- | --- |
| Initial implementation, `42f7ff5` | 58 passed, 1 skipped; 34.739 s | 59 passed; 19.514 s | [Host](local-tests.txt), [Docker](supplied-docker-tests.txt) |
| Documentation pass, based on `42f7ff5`, later committed as `d496648` | 58 passed, 1 skipped; 32.969 s | Not rerun for comments-only changes | Prior recorded documentation check; original executable ASTs unchanged |
| P1/P2 fix pass, based on `d496648` | 83 passed, 1 skipped; 36.976 s | 84 passed; 20.132 s | [Host](findings-fix-local-tests.txt), [Docker](findings-fix-docker-tests.txt) |

The P1/P2 socket test returned 160 rooms in eight pages, with a maximum payload of 15,519 bytes in both environments.
Original supporting files remain available: [build log](supplied-docker-build.txt), [source checks](source-checks.txt) and [baseline SHA-256 manifest](source-sha256.json).
The manifest identifies the original baseline bytes; it does not describe the current edited files.
One original PowerShell location diagnostic remains in the build log at line 2. It is retained verbatim as historical machine output, not as a translated project explanation.

## Outstanding limits

- The actual official examiner image/tag has not been confirmed or tested.
- Windows native Ctrl+C and sustained network saturation have not been exercised. Shutdown is covered by the server API on Windows and SIGINT in Linux.
- There is no TLS, password authentication, persistence, resume, global room cap or idle timeout. Room pages do not provide a snapshot.
- Academic documentation, the demonstration video and the final submission ZIP remain separate deliverables.
