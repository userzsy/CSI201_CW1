# Learning Mall Docker demonstration runbook

Use the [main guide](verification-and-demonstration-guide.md) for environment preparation, automated verification, CLI reference and A–E responsibilities. This runbook keeps the recording commands and sequence. [Verification records](../verification/README.md#learning-mall-supplied-docker-environment) contain the image metadata and results.

The verified local Learning Mall build is `csi201-cw1:learning-mall-local`, ID `sha256:f76ee65c28d414ed11e626694c4508174bbae44a27c48f9db37863b731af6e92`. The recorded application baseline is `f30777a`. No final video has been recorded.

## Preparation before recording

Run from the repository root in PowerShell. Use the existing verified image; rebuilding is not part of the recording.

```powershell
$RepoRoot = (git rev-parse --show-toplevel).Trim()
$CodesPath = Join-Path $RepoRoot 'Codes'
$OfficialEnv = (Resolve-Path -LiteralPath (Read-Host 'Extracted Docker environment folder')).Path
$Image = 'csi201-cw1:learning-mall-local'
$DemoName = 'csi201-cw1-demo'
git status --short --branch
docker image inspect $Image --format '{{.Id}}'
docker run --rm --network none --entrypoint python $Image --version
```

Confirm the image ID matches the value above. Record the actual Git commit and rerun verification if application source has changed. Do not reset user changes.
Choose another container name if `csi201-cw1-demo` already belongs to another session.

If the image is unavailable, follow the [build and verification procedure](verification-and-demonstration-guide.md#environment-preparation) before rehearsal. Keep the existing evidence and development image.

Create a persistent rehearsal container. Both host mounts are read-only; the exact source is copied into its temporary writable filesystem, excluding bytecode caches. No port is published and no external network is available.

```powershell
$Prepare = "import shutil,time; shutil.copytree('/submission','/tmp/csi201-demo',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo')); print('DEMO_READY',flush=True); time.sleep(86400)"
docker run -d --name $DemoName --network none --read-only --tmpfs /tmp:rw,exec,nosuid,size=256m --mount "type=bind,source=$CodesPath,target=/submission,readonly" --mount "type=bind,source=$OfficialEnv,target=/examiner-env,readonly" --workdir /tmp --entrypoint python $Image -c $Prepare
docker logs $DemoName
```

Expected readiness is `DEMO_READY`. The copy/preparation path was exercised in the CLI smoke test. The commands below use the fixed name `csi201-cw1-demo`; substitute another name consistently if needed.
Prepare separate terminal windows for the server and clients. All application processes run inside this same container and image.

## Task 1: invalid and valid startup

In the preparation terminal, create an invalid test bank only inside `/tmp`. The original 50-question bank remains untouched.

```powershell
$BadBank = "import json; from pathlib import Path; from tests import bank_fixture; bank=bank_fixture(); bank['quizzes'][0]['questions'][0]['options']['A']=chr(0xd800); Path('/tmp/invalid-bank.json').write_text(json.dumps(bank),encoding='utf-8')"
docker exec --workdir /tmp/csi201-demo csi201-cw1-demo python -c $BadBank
docker exec --workdir /tmp/csi201-demo csi201-cw1-demo python3 server.py --host 127.0.0.1 --port 5001 --questions /tmp/invalid-bank.json
```

Expected: field-specific `STARTUP_ERROR`, nonzero exit, no `SERVER_READY` and no listener on port 5001. The nonzero exit is intentional for this negative case.

In the server terminal, start the actual submitted server using the official bank:

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 server.py --host 127.0.0.1 --port 5000 --questions /examiner-env/questions_50.json
```

Expected: `SERVER_READY 127.0.0.1:5000`, with the server staying active. Leave this terminal running.

## Task 2: identity and connections

Use two separate client terminals:

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 1002 --name Bob
```

Run only one client command per terminal. Expected: `CONNECTED`, then `LOGIN_RESPONSE` with success.
In a third terminal, try the active ID again:

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name DuplicateAlice
```

Expected: `ERROR_RESPONSE` with `DUPLICATE_USER`, then client exit. Alice and Bob remain connected.

## Task 3: catalogue, rooms and readiness

1. Alice: `/quizzes`, then `/create geography`.
2. Bob: `/rooms`, then `/join <returned_room_code>`.
3. Alice: `/players`; confirm both members and the host.
4. Alice: `/start` before readiness to show `PLAYERS_NOT_READY`.
5. Both clients: `/ready`; confirm both readiness values are true.
6. Alice: `/start`; both clients receive `QUIZ_STARTED_EVENT` and `QUESTION_EVENT`.

Always use the actual returned room code. The official catalogue has `geography`, `history`, `natural-science`, `literature-arts` and `math-logic`, each with ten questions. Room listings omit participant arrays; `/players` supplies the details.

## Task 4: timed quiz, scoring and final ranking

- For each of the ten Geography questions, Alice uses `/answer D`, Bob uses `/answer A`.
- Before Bob answers the first question, Alice can repeat `/answer A` to show `DUPLICATE_ANSWER`; her accepted D remains unchanged.
- Show each question's configured time limit, `ANSWER_RESPONSE`, `QUESTION_RESULT_EVENT`, points and leaderboard. The official bank uses a 60-second limit, and both answers close a question early.
- Continue through all ten questions, then show `QUIZ_FINISHED_EVENT` and `/score`.
- The observed fixed-answer rehearsal ended with Bob on 300 points and Alice on 200; full actual output is in [cli-smoke-test.txt](../verification/examiner-image/cli-smoke-test.txt).
- Both use `/leave`, then `/quit`. The final leaver receives `ROOM_CLOSED_EVENT`.

After Alice has quit, check ID reuse in her terminal, then use `/quit` again:

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name AliceAgain
```

For a visible real-bank timeout, Alice may answer D on the first question while Bob withholds his answer for the full 60 seconds. Bob should receive `your_answer: null` and zero points at closure. This optional interactive 60-second scene was not executed in the scripted smoke test; real timeout handling was executed by the complete suite. Allow for the minute in the schedule below.

## Task 5: ten clients and two isolated rooms

Open ten separate sessions, one command per terminal:

```powershell
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2001 --name A1
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2002 --name A2
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2003 --name A3
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2004 --name A4
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2005 --name A5
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2006 --name B1
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2007 --name B2
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2008 --name B3
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2009 --name B4
docker exec -it --workdir /tmp/csi201-demo csi201-cw1-demo python3 client.py --server 127.0.0.1 --port 5000 --id 2010 --name B5
```

1. A1 creates `geography`; A2-A5 join that returned room code.
2. B1 creates `history`; B2-B5 join the other returned code.
3. All ten use `/ready`; A1 and B1 each use `/start`.
4. Keep Room B's first question unanswered. All five A clients answer their first question promptly, so Room A advances while B remains on its first question.
5. Use `/score` in each room and show distinct question IDs, participants and scores. Do this before B's 60-second deadline; after it expires, B progresses independently.
6. Quit one A participant and confirm B stays usable. Then `/quit` from all clients.

The complete suite executed ten real submitted clients in two rooms, including independent 5/30-second test-bank deadlines, event/score isolation and disconnect recovery. The ten-window interactive recording procedure above uses the official bank; it has not been recorded as a video.

## Shutdown and cleanup

Press Ctrl+C in the server terminal. Expected: `SERVER_STOPPED`; the scripted rehearsal verified the equivalent SIGINT and confirmed the listening port was released.
After applications have exited, remove only this rehearsal container:

```powershell
docker rm --force csi201-cw1-demo
docker ps --filter name=csi201-cw1-demo
```

Keep both images. No host source, supplied configuration or question data needs changing. The verification smoke container was already removed after its successful run.

## Suggested recording schedule

Perform the build and container preparation before recording. Follow the agreed [five-person allocation](verification-and-demonstration-guide.md#team-video-responsibilities): A handles Task 1/server startup; B handles Task 2/protocol; C handles Tasks 3–4; D operates the paired client; E coordinates Task 5/concurrency. All five participate; insert actual names before recording. Total duration is 9:30, below the ten-minute limit.

| Time | Segment |
| --- | --- |
| 0:00-0:50 | Task 1: image identity, invalid bank and valid startup |
| 0:50-1:40 | Task 2: two logins and duplicate ID |
| 1:40-2:40 | Task 3: catalogue, rooms, participants and readiness |
| 2:40-5:40 | Task 4: full quiz, optional 60-second timeout and final ranking |
| 5:40-8:50 | Task 5: ten clients, two rooms and independent progress |
| 8:50-9:30 | Graceful shutdown, evidence recap and cleanup |

Use actual live terminal behaviour. Do not substitute screenshots, generated output or another client implementation. The academic report and final video are not part of this verification task.
