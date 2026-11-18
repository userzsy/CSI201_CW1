# Networked Quiz Tournament

A basic terminal application for CSI201 Coursework I. The server owns question
loading, sessions, rooms, monotonic deadlines, accepted answers and scores. Clients
obtain all quiz data over TCP. Python 3.12 and its Standard Library are sufficient;
there is no installation step or runtime dependency on Docker, a database or an
external service.

## Start the system

The compulsory interfaces are:

```text
python3 server.py --host <server_IP> --port <port> --questions <json_path>
python3 client.py --server <server_IP> --port <port> --id <user_id> --name <display_name>
```

Run commands from `Codes` (or the directory mounted as `/code` in Docker).
For example, start one server and a client in each of two other terminals:

```sh
python3 server.py --host 127.0.0.1 --port 5000 --questions questions.json
python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
python3 client.py --server 127.0.0.1 --port 5000 --id 1002 --name Bob
```

On the Windows host, replace `python3` with `..\.venv\Scripts\python.exe`
after creating the Python 3.12 environment described in the repository README.
The example port is user selected; ports 1-65535 are accepted. `--host` expects an
IPv4 address; `--server` accepts an address or hostname. Bind to `0.0.0.0` when
clients must reach the server through another interface. Invalid banks produce
`STARTUP_ERROR` and a nonzero exit before any listening socket is opened.
`SERVER_READY <host>:<port>` means validation and listening have both succeeded.
Ctrl+C stops the server and releases its sockets, sessions, rooms and selector.

## Commands

| Command | Action |
| --- | --- |
| `/help` | Display available commands |
| `/quizzes` | List public quiz metadata in bank order |
| `/rooms` | List lobby rooms with space available |
| `/create <quiz_id>` | Create a room and become host |
| `/join <room_code>` | Join a lobby room |
| `/players` | View participants, host and readiness |
| `/ready` | Set your readiness to true |
| `/start` | Ask to start the selected quiz |
| `/answer <A\|B\|C\|D>` | Submit an answer for the question currently displayed |
| `/score` | Display the current ordered leaderboard |
| `/leave` | Leave the current room |
| `/quit` | Log out and exit |

For a first game, Alice uses `/quizzes`, `/create <quiz_id>`, and shares the returned
room code. Bob uses `/rooms` and `/join <room_code>`. Both use `/ready`, and Alice
uses `/start`. Each player answers with `/answer A` (or B, C, D). Question and
result events are printed automatically. After the final results, use `/score`,
`/leave`, and `/quit`. EOF also logs out. The receiver remains active while the
user types, and a server disconnect ends the client even with stdin still open.
Messages are displayed as a message name followed by a JSON payload on one line;
these include the question, choices, time limit, awards and rankings.

## Game rules and lifecycle

- A room holds 2-10 players for play; its creator is host. All players, including
  the host, must be ready. Only the host may start. Joining and readiness changes
  are permitted only in the lobby. A player can belong to one room at a time.
- Room codes are sequential `R000001`, `R000002`, etc., without reuse during the
  server lifetime. Quiz and question order follow the input file.
- `CONNECTED -> AUTHENTICATED -> LOBBY -> QUESTION_OPEN -> QUESTION_CLOSED`
  describes entry and play. Each result is followed immediately by the next
  question, or `FINISHED` after the last question. Leaving returns a connected
  player to `AUTHENTICATED`. A new game requires leaving and creating/joining a room.
- Each question uses its configured time limit measured with `time.monotonic()`.
  It closes at its deadline or after every active player has answered. The exact
  deadline is exclusive: answers at or after it are late. The server then reveals
  the correct answer and each player's points. Invalid answers do not use a turn.
- A correct accepted answer earns the configured points once. Incorrect, missing
  or late answers earn zero. Duplicate answers are rejected; the first accepted
  answer remains authoritative. Closed-question answers return `QUESTION_CLOSED`.
- Rank by score descending, correct-answer count descending, then user ID in
  ascending lexical order. Ranks are consecutive; this same order determines the
  single winner when scores tie.
- Lobby departures remove membership; a departing host transfers to the earliest
  remaining player. During play, departing players become inactive and retain
  their scores and accepted answers. They no longer count as unanswered players.
  The quiz continues when the host disconnects. An empty room is removed.
- Active user IDs are unique, case sensitive printable strings of 1-64 characters;
  display names are nonblank printable strings of 1-100 characters. A disconnect
  or logout releases the ID. A new connection starts a new session, without resuming
  an earlier game. Duplicate display names are allowed.

## Protocol

The design adopts the supplied informative appendix. Each frame is a 4-byte
unsigned big-endian payload byte count followed by UTF-8 JSON. Payload lengths
1-65,536 are accepted. Fragmented reads and several frames per read are supported;
the server retains partial outgoing writes. Every envelope contains:

```json
{"version":1,"type":"LIST_ROOMS_REQUEST","request_id":"req-0001","event_id":null,"session_id":"s-example","payload":{}}
```

`version` is integer 1, `type` is a known case-sensitive message name, and `payload`
is an object. `request_id`, `event_id`, and `session_id` are null or strings of
1-128 characters. Requests and direct responses use matching `request_id` and
null `event_id`. Events use unique `event_id` and null `request_id`, with the
recipient's authenticated session ID. Login requests have a null session ID;
successful `LOGIN_RESPONSE` carries the same session ID in envelope and payload.
Subsequent requests must identify the session bound to that socket.

Direct request/response pairs are `LOGIN`, `LIST_QUIZZES`, `LIST_ROOMS`,
`CREATE_ROOM`, `JOIN_ROOM`, `PLAYER_LIST`, `ANSWER`, and `LEADERBOARD`, each with
`_REQUEST` / `_RESPONSE` suffixes. Other requests are `READY_REQUEST`,
`START_QUIZ_REQUEST`, `LEAVE_ROOM_REQUEST`, and `LOGOUT_REQUEST`. The first three
are acknowledged by the resulting events; logout closes the connection.

Events are `PLAYER_STATUS_EVENT`, `ROOM_CLOSED_EVENT`, `QUIZ_STARTED_EVENT`,
`QUESTION_EVENT`, `QUESTION_RESULT_EVENT`, and `QUIZ_FINISHED_EVENT`. Payload
fields follow the appendix. `PLAYER_STATUS_EVENT` additionally carries `host_id`;
create responses additionally carry `room`. Successful leave sends a player-status
event to the leaver too, or a room-closed event when no players remain. Empty rooms
are closed in any phase. All six envelope fields, including null `event_id` on
requests/responses, are mandatory in this implementation.

Errors use `ERROR_RESPONSE` with `payload.code` and `payload.message`. Codes:
`INVALID_MESSAGE`, `INVALID_SESSION`, `DUPLICATE_USER`, `QUIZ_NOT_FOUND`,
`ROOM_NOT_FOUND`, `ROOM_FULL`, `ALREADY_IN_ROOM`, `NOT_ROOM_HOST`,
`PLAYERS_NOT_READY`, `QUESTION_CLOSED`, `DUPLICATE_ANSWER`, `INVALID_ANSWER`.
Extensions are `INVALID_STATE` for disallowed room transitions and `NOT_IN_ROOM`
for commands requiring membership. Recoverable errors repeat the request ID.
Unsafe framing/envelope errors use a null request ID and close only that connection.
Request IDs correlate responses; they do not implement request replay or deduplication.

Public quiz metadata includes only ID, title, description and question count.
Open-question events never include the answer; answers appear only after closure.
Room events go only to that room's active participants (and the leaver's departure
acknowledgement). Every room owns its own state, deadline, answers and scores.

## Question bank

`questions.json` is an unchanged copy of the supplied five-quiz, fifty-question bank.
Only the server opens it. A replacement bank is fully validated before listening:

- Nonempty UTF-8 JSON object, at most 1,000,000 bytes (decimal MB).
- Integer `schema_version` equal to 1; `quizzes` array with 1-20 entries. The
  submitted sample has at least two quizzes; a valid one-quiz examiner bank works.
- Quiz: unique `quiz_id` of 1-32 ASCII letters/digits/underscore/hyphen;
  `title` of 1-100 visible characters; `description` of 0-300 visible characters;
  `questions` array of 5-50 entries.
- Question: globally unique `question_id` using the same ID rules; `text` of
  1-500 visible characters; `options` with exactly keys A, B, C, D and string
  values of 1-200 characters; `answer` exactly A, B, C or D; integer `time_limit`
  of 5-60 seconds and integer `points` of 1-1000.
- Booleans are rejected for integer fields. Visible text must be printable, and
  required nonempty text must not be whitespace only. Extra members are allowed
  everywhere except `options`; invalid required values invalidate the entire file.

## Source layout and ownership

```text
Codes/
  server.py                 Raw TCP selectors event loop and CLI
  client.py                 Terminal CLI, receive thread, synchronized writes
  questions.json            Server-only sample data
  README.md
  quizlib/
    __init__.py
    protocol.py             Framing, envelopes, messages and errors
    quiz_loader.py          Complete bank validation and public metadata
    session.py              Active identity/session registry
    game.py                 Rooms, quiz state, deadlines and scoring
  tests/
    __init__.py             Fixtures and real program subprocess helpers
    test_protocol.py
    test_quiz_loader.py
    test_session.py
    test_game.py
    test_client.py
    test_server.py
    test_client_server.py
    test_concurrency.py
```

The server's single event-loop thread owns all mutable game/session state. No
timer threads modify rooms, and socket writes never block it. Each connection has
a frame decoder and output buffer, capped at 1 MiB; a client exceeding that buffer
is disconnected without interrupting other rooms. The client uses a receive thread
and a daemon stdin reader so server loss can interrupt an otherwise idle terminal.
The main thread parses commands, while locks protect shared state and frame writes.

## Verification

From `Codes` with Python 3.12:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```

On Windows use `..\.venv\Scripts\python.exe` in place of `python3`. These are
preliminary host results, never official Docker evidence. Tests use Standard Library
`unittest`, including actual `client.py` and `server.py` subprocesses communicating
over loopback TCP. They cover invalid startup/banks, framing, sessions, game rules,
real five-second timeouts, full paired workflow, ten simultaneous clients in two
rooms, isolation of timers/events/scores and disconnect recovery. Fake clocks are
used only for deterministic unit tests. The POSIX SIGINT subprocess test skips on
Windows and must run in the Linux verification environment. If the OS denies
loopback access, affected integration tests explicitly skip and require a rerun.

From the parent development repository, the supplied Docker environment is used as:

```sh
docker compose -f docker_env/compose.dev.yaml build
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
```

Both subprocesses run inside the same container. The original `compose.yaml`
mounts its own directory, so the separate development override mounts `Codes`.
The Docker files are development material outside the source submission. An actual
published examiner image/tag must be confirmed separately; run the commands below
from `Codes` after setting `EXAMINER_IMAGE` to that exact image:

```sh
docker run --rm --entrypoint python3 -v "$PWD:/code" -w /code "$EXAMINER_IMAGE" -m unittest discover -s tests -v
docker run --rm --entrypoint python3 -v "$PWD:/code" -w /code "$EXAMINER_IMAGE" -m compileall -q .
```

## Assumptions and limits

This is a trusted coursework-network application: there is no TLS, password
authentication, persistence or reconnect/resume. Session IDs bind connections but
do not prove a person's identity. Finished rooms remain while a participant is
present. There is no global cap on connected users/rooms, idle timeout, or pagination
of very large room lists; operation is intended for the assessed small tournament.
Server addresses are IPv4. Terminal event output may appear while entering a command.
The published official examiner image is not identified by the supplied Dockerfile
alone; results must name the actual environment in which they were produced.
