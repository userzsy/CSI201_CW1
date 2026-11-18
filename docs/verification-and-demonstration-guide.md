# CSI201 CW1 — Verification and Demonstration Guide

## Overview

Use this guide to prepare the Learning Mall Supplied Docker Environment, verify the submitted application and prepare the five-person demonstration. The attachment supplies a Dockerfile, `compose.yaml` and `questions_50.json`; the verified image was built locally from that Dockerfile.

Source and tests are in [`Codes/`](../Codes/). [Verification records](../verification/README.md) identify the tested baseline, image and retained outputs. The [protocol design](protocol-design.md) explains messages; the [demo runbook](../verification/examiner-image/demo-runbook.md) supplies the exact Tasks 1–5 recording sequence.

## Environment Preparation

1. Download **CW1 - Docker Env ZIP** from Learning Mall. Extract it with Windows **Extract All**.
2. Find the extracted folder containing `Dockerfile`, `compose.yaml` and `questions_50.json`. Select that folder below, including any nested folder created during extraction.
3. Open PowerShell in this repository. Start Docker Desktop using Linux containers and check the engine before building.

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$CodesPath = Join-Path $RepoRoot 'Codes'
$OfficialEnv = (Resolve-Path -LiteralPath (Read-Host 'Extracted Docker environment folder')).Path
$Image = 'csi201-cw1:learning-mall-local'
docker version
Get-ChildItem -LiteralPath $OfficialEnv
```

The supplied three files match those retained in [`docker_env/`](../docker_env/). Its original Compose file mounts its own directory at `/code`; the existing `compose.dev.yaml` mounts `Codes/`. Preserve both files. The commands here use a separate image tag, leaving the development tag `csi201-cw1:latest` intact.

On the verified machine, the development image ID is `sha256:4e89089fe7c6bee76ee0c43f056b966a00a9c1db3cb0c0e323dba729c160ab3f`. If that tag exists on your machine, record its ID before and after building:

```powershell
docker image inspect csi201-cw1:latest --format '{{.Id}}'
```

Build once before verification or rehearsal, using the extracted supplied directory as context:

```powershell
docker build --pull --progress plain -t $Image $OfficialEnv
docker image inspect $Image
docker run --rm --network none --read-only --entrypoint python $Image --version
```

The recorded image ID is `sha256:f76ee65c28d414ed11e626694c4508174bbae44a27c48f9db37863b731af6e92`, with Python 3.12.16 on Linux/amd64. Its base resolved to `sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`; see [image metadata](../verification/examiner-image/image-metadata.txt). A later build can resolve a newer base digest. Record its actual identity and fresh results separately; retain the existing evidence and development image.

## Running the Application

Use the [runbook preparation](../verification/examiner-image/demo-runbook.md#preparation-before-recording) to start `csi201-cw1-demo`. It mounts `Codes/` at `/submission` and the supplied directory at `/examiner-env`, both read-only, then copies source into `/tmp/csi201-demo`. The root filesystem is read-only; `/tmp` is writable. All processes share this container's loopback network with `--network none`; no host port is published.

After `DEMO_READY`, use separate PowerShell terminals for the server and each client:

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 server.py --host 127.0.0.1 --port 5000 --questions /examiner-env/questions_50.json
```

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
```

Launch Bob in another terminal with `--id 1002 --name Bob`. Wait for `SERVER_READY` before connecting. Alice creates a quiz room; Bob joins its returned code; both use `/ready`, then Alice uses `/start`.

Clients exit with `/quit`. Press Ctrl+C in the server terminal and wait for `SERVER_STOPPED`, then follow [shutdown and cleanup](../verification/examiner-image/demo-runbook.md#shutdown-and-cleanup). Host-only development commands are in the [source README](../Codes/README.md#requirements-and-launch-commands).

## CLI Command Reference

| Command | Action |
| --- | --- |
| `/help` | Show commands. |
| `/quizzes` | List quiz IDs and public metadata. |
| `/rooms` | Fetch all joinable rooms automatically across pages. |
| `/create <quiz_id>` | Create a room and become host. |
| `/join <room_code>` | Join a lobby using its returned code. |
| `/players` | Show participants and readiness. |
| `/ready` | Set ready. |
| `/start` | Start as host, with at least two players and everyone ready. |
| `/answer <A\|B\|C\|D>` | Submit one answer for the current question. |
| `/score` | Show the ordered leaderboard. |
| `/leave` | Leave the current room. |
| `/quit` | Log out and exit. |

## Verification Procedure

### Automated checks

Keep the variables from environment preparation in this PowerShell session. Check Python 3.12 and required Standard Library imports with the recorded command:

```powershell
docker run --rm --network none --read-only --entrypoint python $Image -c "import socket,selectors,struct,json,threading,time,argparse,unittest,sys,platform,shutil; print(sys.version); print(platform.platform()); print('python3='+str(shutil.which('python3'))); print('STANDARD_LIBRARY_OK'); assert sys.version_info[:2] == (3,12)"
```

The retained [verification runner](../verification/examiner-image/container_verify.py) is the same script used for the recorded compilation and full suite. Its original temporary host location appears in the raw logs; mount its published location below. It checks the source copy's hashes, compiles or runs all tests, and requires 84 passes with no skips in test mode.

```powershell
$EvidencePath = Join-Path $RepoRoot 'verification/examiner-image'
$VerifyArgs = @(
    'run', '--rm', '--network', 'none', '--read-only',
    '--tmpfs', '/tmp:rw,exec,nosuid,size=256m',
    '--mount', "type=bind,source=$CodesPath,target=/submission,readonly",
    '--mount', "type=bind,source=$OfficialEnv,target=/examiner-env,readonly",
    '--mount', "type=bind,source=$EvidencePath,target=/verification-tools,readonly",
    '--workdir', '/tmp', '--entrypoint', 'python', $Image
)
docker @VerifyArgs /verification-tools/container_verify.py compile
docker @VerifyArgs /verification-tools/container_verify.py test
```

Each invocation gets a fresh temporary source copy. No packages or external network are required. Keep fresh command output with its actual commit and image identity; do not overwrite earlier logs. Compilation must print `COMPILEALL_PASS`; the suite must finish with `FULL_SUITE_PASS total=84 passed=84 failed=0 skipped=0`.

| Check within the full suite | Test evidence |
| --- | --- |
| P1 invalid/valid Unicode, including option strings | `test_quiz_loader` surrogate and valid-Unicode cases; `test_protocol` Unicode round trips |
| Invalid-bank startup before listening | `test_invalid_unicode_bank_is_rejected_before_listening` |
| P2 160-room TCP pagination | `test_160_rooms_over_real_tcp_with_bounded_frames_and_reused_connection` |
| CLI follows pages and prints once | `test_submitted_cli_automatically_collects_all_160_rooms` |
| Frame-size protection and error handling | `ServerPageSizingTests` and `ClientPaginationTests` |
| Ten clients in two rooms | `test_ten_actual_clients_two_independent_rooms` |
| Real timeout and missing answer | `test_real_monotonic_timeout_and_missing_answer` |
| Linux SIGINT and port release | `test_ctrl_c_shutdown_subprocess` |

These are automated checks using fixtures, real TCP and submitted CLI subprocesses where indicated. The concurrency fixture uses independent 5/30-second room deadlines. Detailed P1/P2 checks are in the [acceptance checklist](../verification/README.md#acceptance-checklist).

### Official-bank CLI smoke test and rehearsal

Follow [runbook Tasks 1–4](../verification/examiner-image/demo-runbook.md#task-1-invalid-and-valid-startup) to reproduce invalid-bank rejection, two logins, duplicate-ID rejection, catalogue, room, readiness, answers, scoring and exit. `/quizzes` must show five quizzes with ten questions each. Complete Geography with Alice answering D and Bob answering A; the recorded final scores are Alice 200 and Bob 300. After logout, reconnect ID 1001 to confirm reuse, then `/quit` again. Stop the server with Ctrl+C, check `SERVER_STOPPED`, and remove the demo container.

The existing [CLI transcript](../verification/examiner-image/cli-smoke-test.txt) was generated by scripted stdin/stdout driving the actual submitted server and clients. It verified a full ten-question quiz, per-question awards, ID reuse, SIGINT and port release. Human interactive rehearsal and video recording remain to be performed. The optional official-bank 60-second timeout scene is a rehearsal step; the suite already tested real timeout handling with a shorter fixture.

### Recorded Learning Mall results

These results belong to the recorded `f30777a` application baseline and image above. This documentation update does not rerun the full suite. Windows and development Docker results remain [separate](../verification/README.md).

| Verification | Recorded result | Evidence |
| --- | --- | --- |
| Build | Passed; development image preserved | [Build](../verification/examiner-image/build.txt), [metadata](../verification/examiner-image/image-metadata.txt) |
| Python / Standard Library | Python 3.12.16; passed | [Environment](../verification/examiner-image/environment-check.txt) |
| Compilation | Passed | [compileall](../verification/examiner-image/compileall.txt) |
| Full suite, including P1/P2 and ten-client concurrency | 84 passed, 0 failed, 0 skipped; 18.186 s | [Full output](../verification/examiner-image/unittest-full.txt) |
| Pagination | 160 rooms, 8 pages, maximum payload 15,519 bytes excluding the four-byte header | [Full output](../verification/examiner-image/unittest-full.txt) |
| Official bank and two-client workflow | 5 quizzes / 50 questions; completed 10-question quiz | [CLI transcript](../verification/examiner-image/cli-smoke-test.txt) |
| Shutdown and cleanup | SIGINT, port release and temporary container removal passed | [CLI transcript](../verification/examiner-image/cli-smoke-test.txt), [metadata](../verification/examiner-image/image-metadata.txt) |

## Coursework Task Demonstration

| Task | Main feature | Demonstration |
| --- | --- | --- |
| Task 1 | Server startup | Invalid-bank rejection, then valid official-bank startup. |
| Task 2 | Client connections | Two logins and duplicate active user ID rejection. |
| Task 3 | Room management | Catalogue, create, join, participants, ready and guarded start. |
| Task 4 | Quiz tournament | Timed questions, accepted/duplicate answers, scoring and final leaderboard. |
| Task 5 | Concurrency | Ten submitted clients across two isolated rooms with independent progress. |

Task 6 remains covered by automated failure-handling tests and verification records. The required video focuses on Tasks 1–5.

## Team Video Responsibilities

| Member | Responsibility | Recording contribution |
| --- | --- | --- |
| A | Task 1 and server startup | Show environment identity, invalid bank, valid startup and server shutdown. |
| B | Task 2 and network protocol | Show connections and duplicate ID; explain framing and request/event handling briefly. |
| C | Task 3 and Task 4 | Demonstrate room lifecycle, timed quiz, scores and ranking. |
| D | Client operation and interaction | Operate the paired client and answer/ready/leave sequence with C. |
| E | Task 5, concurrency and demonstration coordination | Coordinate ten clients, two-room isolation, timing and cleanup. |

All five members must participate. Replace A–E with actual names before recording and rehearse terminal handoffs together.

## Recording Preparation

- Build and verify before recording. Use the existing [9:30 schedule](../verification/examiner-image/demo-runbook.md#suggested-recording-schedule) as the single timing reference, below the ten-minute limit.
- Keep the server terminal visible. Prepare Alice/Bob terminals and a separate duplicate-ID terminal; label the ten later client sessions A1–A5 and B1–B5.
- Keep `questions_50.json` read-only. Generate the invalid bank only inside container `/tmp`, as shown in the runbook.
- Pre-open ten terminal tabs and paste the launch commands before recording; launch them during Task 5. Capture the actual returned room codes for Geography and History.
- Rehearse A's room advancing while B's first question remains open, within B's 60-second deadline. Show distinct question IDs, participants and scores, then disconnect one A client while B remains usable.
- Make output readable: `SERVER_READY`, `LOGIN_RESPONSE`, `QUESTION_EVENT`, `QUESTION_RESULT_EVENT`, `QUIZ_FINISHED_EVENT` and `SERVER_STOPPED` are the main checkpoints.
- Reserve the runbook's optional timeout minute within Task 4. End with all clients quitting, graceful server shutdown and removal of only the demo container.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Docker engine unavailable | Start Docker Desktop in Linux-container mode; retry `docker version` until the server section responds. |
| Image tag missing or incorrect | Inspect `$Image`; use `csi201-cw1:learning-mall-local` and the supplied Dockerfile build above. Record the identity of a rebuilt image. |
| Port already occupied | Stop your earlier server in the demo container, or select the same free `--port` for server and clients. No host port is published. |
| Incorrect mount or missing bank | Check `$CodesPath` contains `server.py` and `$OfficialEnv` contains `questions_50.json`. Correct the variables and recreate only your demo container. |
| Client cannot connect | Wait for `SERVER_READY`; run every demo process in the same container with `127.0.0.1` and matching ports. Use unique active IDs. |
| Stale demo container | Confirm it belongs to this rehearsal, exit its applications and follow runbook cleanup. Use another consistent name for a separate session. |

## Related Documents

- [Project README](../README.md)
- [Source usage and modules](../Codes/README.md)
- [Protocol design](protocol-design.md)
- [Verification records and evidence](../verification/README.md)
- [Practical demo runbook](../verification/examiner-image/demo-runbook.md)
