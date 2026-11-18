# Source and operating guide

## Source structure

Generated caches are omitted.

```text
Codes/
├── server.py                 # Server entry point and connection management
├── client.py                 # CLI commands, requests and asynchronous output
├── questions.json            # Unchanged server-only sample bank
├── README.md                 # Source and operating guide
├── quizlib/
│   ├── __init__.py           # Shared package marker
│   ├── protocol.py           # Framing, envelopes, message types and errors
│   ├── quiz_loader.py        # Bank loading, validation and public metadata
│   ├── session.py            # Session data and active identity registry
│   └── game.py               # Players, rooms, deadlines, scoring and ranking
└── tests/
    ├── __init__.py           # Bank, subprocess and seeded-server fixtures
    ├── test_quiz_loader.py   # Unit: bank schema, file errors and Unicode
    ├── test_protocol.py      # Unit: frames, envelopes and Unicode round-trips
    ├── test_session.py       # Unit: login, lookup, ID reuse and cleanup
    ├── test_game.py          # Unit: rooms, timing, scoring and cursor filtering
    ├── test_client.py        # Client: commands, events and automatic pagination
    ├── test_server.py        # Server: startup, TCP, page size and shutdown
    ├── test_client_server.py # Integration: submitted CLI workflow and 160 rooms
    └── test_concurrency.py   # Concurrency: ten clients in two independent rooms
```

## Implementation

| Module | Responsibility |
| --- | --- |
| `server.py` | Parses arguments, owns the non-blocking selectors loop, dispatches requests and coordinates cleanup. |
| `client.py` | Logs in, parses commands, serializes writes and receives asynchronous server messages. |
| `quizlib/protocol.py` | Defines the shared envelope, frame buffer, encoder, message types and errors. |
| `quizlib/quiz_loader.py` | Validates the complete bank before listening; exposes public quiz metadata without questions or answers. |
| `quizlib/session.py` | Uses `Session` and `SessionRegistry` for active user identities and membership cleanup. |
| `quizlib/game.py` | Uses `Player`, `Room`, `RoomManager` and `QuizEngine` for state, independent monotonic deadlines and scores. |

Only the server reads the bank. The server event loop owns mutable session and room state; no timer threads modify rooms.
The client has a receiver thread and an stdin reader so server loss can end an idle CLI. Locks protect shared state and frame writes.

## Requirements and launch commands

Python 3.12 and the Standard Library are sufficient. Run from `Codes/`; use a separate terminal for every process.

```bash
python3 server.py --host <server_IP> --port <port> --questions <json_path>
python3 client.py --server <server_IP> --port <port> --id <user_id> --name <display_name>
```

| Argument | Meaning |
| --- | --- |
| `--host` | Server bind IPv4 address; `0.0.0.0` listens on all IPv4 interfaces. |
| `--server` | Server address or hostname. |
| `--port` | User-selected port from 1 to 65535; both sides must use the same value. |
| `--questions` | Relative or supplied path to the server's JSON bank. |
| `--id` | Unique active, case-sensitive user ID. |
| `--name` | Display name; quote names containing spaces. |

On Windows, replace `python3` with `..\.venv\Scripts\python.exe` after following the [environment setup](../README.md#quick-start).
`SERVER_READY` appears only after bank validation and listening succeed. Invalid banks cause `STARTUP_ERROR` and a nonzero exit.
Ctrl+C stops the server and releases its resources; `/quit` or stdin EOF logs out a client.

## Commands

| Command | Action |
| --- | --- |
| `/help` | Show available commands. |
| `/quizzes` | List public quiz metadata in file order. |
| `/rooms` | Retrieve all joinable rooms automatically and display one complete list. |
| `/create <quiz_id>` | Create a lobby and become its host. |
| `/join <room_code>` | Join a lobby. |
| `/players` | Show the current room's participants, host and readiness. |
| `/ready` | Set ready. |
| `/start` | Ask to start; host only. |
| `/answer <A\|B\|C\|D>` | Answer the current question; its ID is supplied automatically. |
| `/score` | Show the ordered leaderboard. |
| `/leave` | Leave the room. |
| `/quit` | Log out and exit. |

## Game rules

- Rooms hold up to ten players. At least two players, including the host, must all be ready before the host starts.
- Joining and readiness changes are allowed only in the lobby. Each player belongs to at most one room.
- Questions follow bank order and close when all active players have answered or the monotonic deadline expires.
- One valid answer is accepted per player per question. Correct answers earn configured points; wrong, missing and late answers earn zero. Results reveal the answer only after closure.
- Rank by score descending, correct-answer count descending, then user ID in ascending lexical order. This order also determines the winner.
- A departing lobby host transfers to the earliest remaining player. During play, departed players retain scores and accepted answers but no longer delay closure. Empty rooms are removed.
- Leave a finished room before creating or joining another game. A reconnect creates a new session and does not resume play.

## Protocol and resolved findings

[Protocol design](../docs/protocol-design.md) specifies the shared envelope and every message payload.
Room-list requests accept `cursor`; responses retain `rooms` and add `next_cursor`. Listings contain compact metadata, with participants available after joining or through `/players`.
The client follows cursors automatically, checks progress and discards incomplete results on page failure or disconnect.

P1 is resolved by strict UTF-8 checks on required bank text before startup. Valid Chinese, English, Emoji and option control characters remain supported.
P2 is resolved by byte-measured pages of at most twenty rooms. The four-byte frame header and 65,536-byte payload limit are unchanged.
See the [acceptance record](../verification/README.md#acceptance-checklist) for executable evidence.

## Tests

From `Codes/`:

```bash
python3 --version
python3 -m compileall -q .
python3 -m unittest discover -s tests -v
```

Use `..\.venv\Scripts\python.exe` in place of `python3` on Windows. Docker is not needed for host development.
From the repository root, use the existing supplied environment for full integration and compatibility checks:

```bash
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
```

`compose.dev.yaml` mounts `Codes/` at `/code`. Client and server integration subprocesses run in the same container.
The POSIX SIGINT test skips on Windows. OS-denied loopback tests also report a skip; those skips do not prove integration success.
Host, supplied Docker and official examiner results are recorded separately in the [verification record](../verification/README.md).

## Limits and team changes

There is no TLS, password authentication, persistence, resume, global room cap or idle timeout. Session IDs identify connections rather than proving a person's identity.
Room pages are a live view, not a cross-page snapshot. Terminal events may appear while entering commands.
Before changing shared messages, data structures or interfaces, check callers and recipients and rerun the full suite.
