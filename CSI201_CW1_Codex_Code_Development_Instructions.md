# CSI201 Coursework I --- Complete Code Development Instructions

## 1. Your role and primary objective

You are the lead Python software engineer responsible for implementing
the complete source-code submission for CSI201 Introduction to
Networking Coursework I: Networked Quiz Tournament.

Your task is to READ the provided coursework specification, protocol
appendix and Docker environment, then IMPLEMENT, TEST, DEBUG and
VALIDATE the complete working system.

This is an implementation task, not a planning-only task.

Do not stop after producing an architecture proposal or code skeleton.
You must create the actual source files, integrate all modules, run the
tests and fix implementation defects.

The project must satisfy all six official functional tasks and all
compulsory assessment constraints.

The final deliverable of this stage is the complete `Codes/` directory.

Do NOT start writing the Development_Documentation.pdf or producing the
demonstration video at this stage. Those will be prepared after the
implementation is stable and verified.

------------------------------------------------------------------------

## 2. Source documents and priority

Read these three sources before coding:

1.  `reference/Coursework I Task Sheet.pdf`
    -   This is the normative coursework specification.
    -   All compulsory requirements, question-bank validation rules,
        submission rules and assessment conditions must be followed.
2.  `reference/CAN201_Networked_Quiz_Tournament_Appendix_Application_Layer_Protocol.pdf`
    -   This is the informative Application Layer Protocol Reference.
    -   Adopt its protocol design as the team's implementation baseline.
    -   Use its exact field names, message names, message structure and
        error terminology wherever applicable.
    -   The coursework specification takes precedence if any conflict
        exists.
3.  `docker_env/`
    -   Read the provided Dockerfile, compose.yaml and
        questions_50.json.
    -   Use the supplied environment for Python 3.12 testing.

Do not invent alternative requirements when the source documents already
specify the behaviour.

If any required reference file is missing from the workspace, report
that clearly rather than guessing its contents.

------------------------------------------------------------------------

## 3. Non-negotiable implementation constraints

### Programming environment

-   Python 3.12.
-   Python Standard Library ONLY.
-   No third-party packages.
-   No package installation during execution.
-   No database.
-   No external web services.
-   No GUI.
-   No web application.
-   No browser interface.
-   No desktop application.
-   No high-level networking framework.

### Networking

Use:

-   `socket`
-   `selectors`
-   `struct`
-   `json`
-   `threading` where appropriate for the CLIENT receive thread
-   `time`
-   `argparse`
-   `dataclasses`
-   `enum`
-   `collections`
-   `uuid`
-   `secrets`
-   `signal`
-   `unittest`

The SERVER networking core must directly use raw TCP sockets and
selectors.

Do NOT use:

-   socketserver
-   asyncio high-level server APIs
-   Flask
-   Django
-   FastAPI
-   aiohttp
-   Requests
-   WebSocket frameworks
-   Socket.IO
-   gRPC
-   ZeroMQ
-   Twisted

The entire client-server application must remain usable in a basic
terminal.

### Important architectural decision

Implement the SERVER using a single-threaded selectors event loop.

Use `time.monotonic()` and independent room deadlines for quiz timing.

Do not use `threading.Timer` for room countdowns. This avoids concurrent
modification of room state by timer threads.

The server event loop must be responsible for:

-   Accepting connections.
-   Receiving client messages.
-   Processing requests.
-   Managing session and room state.
-   Checking room deadlines.
-   Closing questions.
-   Updating scores.
-   Broadcasting events.
-   Managing outgoing socket buffers.
-   Handling disconnects and shutdown.

The CLIENT may use a background receiving thread to process asynchronous
server messages while the main thread handles keyboard input.

------------------------------------------------------------------------

## 4. Required project structure

Create the following structure:

``` text
Codes/
├── server.py
├── client.py
├── questions.json
├── README.md
├── quizlib/
│   ├── __init__.py
│   ├── protocol.py
│   ├── quiz_loader.py
│   ├── session.py
│   └── game.py
└── tests/
    ├── __init__.py
    ├── test_quiz_loader.py
    ├── test_protocol.py
    ├── test_session.py
    ├── test_game.py
    ├── test_client.py
    ├── test_server.py
    ├── test_client_server.py
    └── test_concurrency.py
```

Do not unnecessarily split the project into many additional modules.

Each module must have a clear responsibility and stable interfaces.

------------------------------------------------------------------------

## 5. Application-layer protocol --- follow the Appendix exactly

This is a critical requirement.

Use the protocol appendix as the baseline protocol design.

### 5.1 TCP frame format

Each application message must consist of:

1.  A four-byte unsigned integer.
2.  The length prefix uses big-endian network byte order.
3.  The payload is UTF-8 encoded JSON.
4.  The length represents payload bytes, not character count.

Python implementation should use:

-   `struct.pack("!I", payload_length)`
-   `struct.unpack("!I", header)`

Maximum accepted payload:

`65,536 bytes`

Reject:

-   Zero-length frames.
-   Oversized frames.
-   Invalid UTF-8.
-   Invalid JSON.
-   Non-object JSON values.
-   Invalid protocol envelopes.

### 5.2 Exact common envelope

Use the following JSON structure:

``` json
{
  "version": 1,
  "type": "LOGIN_REQUEST",
  "request_id": "req-0001",
  "event_id": null,
  "session_id": null,
  "payload": {
    "user_id": "1234567",
    "name": "Alice"
  }
}
```

The following field names must be preserved exactly:

-   `version`
-   `type`
-   `request_id`
-   `event_id`
-   `session_id`
-   `payload`

Do not rename them to `kind`, `data`, `request`, `event` or other
alternatives.

All messages must follow one consistent envelope.

`request_id` must match the corresponding direct response.

Server-initiated events must have unique `event_id` values.

`session_id` is null before authentication and identifies the
authenticated connection after login.

The LOGIN_RESPONSE must return the session identifier consistently in
accordance with the appendix.

The `payload` field must always be a JSON object.

### 5.3 Required request and response types

Implement the message catalogue from the appendix:

``` text
LOGIN_REQUEST
LOGIN_RESPONSE

LIST_QUIZZES_REQUEST
LIST_QUIZZES_RESPONSE

LIST_ROOMS_REQUEST
LIST_ROOMS_RESPONSE

CREATE_ROOM_REQUEST
CREATE_ROOM_RESPONSE

JOIN_ROOM_REQUEST
JOIN_ROOM_RESPONSE

PLAYER_LIST_REQUEST
PLAYER_LIST_RESPONSE

READY_REQUEST

START_QUIZ_REQUEST

ANSWER_REQUEST
ANSWER_RESPONSE

LEADERBOARD_REQUEST
LEADERBOARD_RESPONSE

LEAVE_ROOM_REQUEST

LOGOUT_REQUEST
```

For READY_REQUEST, START_QUIZ_REQUEST and LEAVE_ROOM_REQUEST, use the
corresponding successful server events to acknowledge state changes.
Errors must always use ERROR_RESPONSE.

LOGOUT_REQUEST should release the session and close the connection
cleanly.

### 5.4 Required asynchronous events

Implement these exact event names:

-   `PLAYER_STATUS_EVENT`
-   `ROOM_CLOSED_EVENT`
-   `QUIZ_STARTED_EVENT`
-   `QUESTION_EVENT`
-   `QUESTION_RESULT_EVENT`
-   `QUIZ_FINISHED_EVENT`

Each event must have:

-   A unique event_id.
-   A null request_id unless the protocol explicitly requires otherwise.
-   The authenticated session_id of the recipient.
-   A payload matching the documented event structure.

Room-specific events must only be delivered to the relevant room
participants.

### 5.5 Required error model

Use:

`ERROR_RESPONSE`

The payload must contain:

-   `code`
-   `message`

Implement at least the error codes in the appendix:

-   INVALID_MESSAGE
-   INVALID_SESSION
-   DUPLICATE_USER
-   QUIZ_NOT_FOUND
-   ROOM_NOT_FOUND
-   ROOM_FULL
-   ALREADY_IN_ROOM
-   NOT_ROOM_HOST
-   PLAYERS_NOT_READY
-   QUESTION_CLOSED
-   DUPLICATE_ANSWER
-   INVALID_ANSWER

You may add clearly documented codes for invalid commands, invalid room
states and users not belonging to a room.

Do not replace the appendix error names with alternative names.

### 5.6 Protocol module

`quizlib/protocol.py` must provide:

-   Frame encoding.
-   Frame decoding.
-   FrameBuffer.
-   ProtocolError.
-   Common envelope validation.
-   Message type definitions.
-   Error code definitions.
-   Request/response/event construction helpers.

FrameBuffer must:

1.  Retain incomplete bytes.
2.  Handle fragmented TCP messages.
3.  Handle multiple complete messages in one receive buffer.
4.  Decode messages in their original order.
5.  Reject invalid lengths before waiting for the payload.
6.  Validate UTF-8 and JSON.
7.  Reject non-object JSON.
8.  Validate message envelope types.

The SERVER must also correctly handle partial socket sends.

Do not assume one recv() equals one message.

Do not assume one send() transmits the entire frame.

Use per-connection outgoing buffers and register EVENT_WRITE when
necessary.

Write comprehensive tests for fragmentation, coalescing and malformed
messages.

------------------------------------------------------------------------

## 6. Question-bank validation --- strict official schema

Implement the complete normative schema in:

`quizlib/quiz_loader.py`

The server must load and validate the entire question bank before
opening its listening socket.

### 6.1 File-level validation

Validate:

-   UTF-8 encoding.
-   Maximum file size of 1 MB.
-   Non-empty file.
-   Valid JSON.
-   Top-level JSON object.
-   Required `schema_version`.
-   Required `quizzes`.

`schema_version` must be integer 1.

`quizzes` must be an array containing 1--20 quiz objects.

Important: The submitted sample file must contain at least two quizzes,
but the validator must accept any otherwise valid file containing 1--20
quizzes. Do not incorrectly require two quizzes in the validator.

### 6.2 Quiz validation

For every quiz:

`quiz_id` - String. - Length 1--32. - Only letters, digits, underscore
and hyphen. - Unique across the file.

`title` - String. - Length 1--100 visible characters.

`description` - String. - Length 0--300 visible characters.

`questions` - Array. - 5--50 questions.

### 6.3 Question validation

For every question:

`question_id` - String. - Length 1--32. - Only letters, digits,
underscore and hyphen. - Globally unique across the entire question
bank, not merely within one quiz.

`text` - String. - Length 1--500 visible characters.

`options` - JSON object. - Exactly four keys: A, B, C and D. - Each
value must be a string of length 1--200. - Missing or additional option
keys invalidate the containing question bank.

`answer` - Exactly A, B, C or D.

`time_limit` - Integer. - 5--60 seconds.

`points` - Integer. - 1--1000 points.

Use strict integer checks. Python booleans must not be accepted as
integers.

Additional object members must be allowed for forward compatibility,
except that options must contain exactly A, B, C and D.

If any required value is missing, invalid, out of range or duplicated,
the complete file must be rejected.

### 6.4 Sample question bank

Use the supplied:

`docker_env/questions_50.json`

Copy it into:

`Codes/questions.json`

Preserve its existing question content.

It contains five quizzes and fifty questions and has already been
checked against the supplied schema.

Do not unnecessarily regenerate or rewrite it.

### 6.5 Confidentiality

Only the SERVER may read questions.json.

The CLIENT must never directly read the question-bank file.

Public quiz listings may contain:

-   quiz_id
-   title
-   description
-   question_count

They must not contain:

-   question text
-   question options
-   correct answers

During a question, QUESTION_EVENT may contain:

-   question_id
-   number
-   text
-   options
-   time_limit
-   points

It must never contain `answer`.

Correct answers may only be revealed after the question closes, using
QUESTION_RESULT_EVENT.

------------------------------------------------------------------------

## 7. Server implementation --- server.py

Implement the compulsory command-line interface:

``` bash
python3 server.py --host <server_IP> --port <port> --questions <json_path>
```

All three arguments must be supported.

The port must not be hard-coded.

### 7.1 Startup sequence

Implement this exact sequence:

1.  Parse arguments.
2.  Validate argument values.
3.  Load the question bank.
4.  Validate the entire question bank.
5.  Initialize application state.
6.  Create the listening socket.
7.  Bind to the selected host and port.
8.  Start listening.
9.  Set the socket to non-blocking mode.
10. Register it with selectors.
11. Print SERVER_READY.
12. Enter the event loop.

SERVER_READY must only appear after successful validation and after the
server begins listening.

If the question bank is invalid:

-   Print a meaningful diagnostic.
-   Exit with a non-zero status.
-   Do not create a listening socket.
-   Do not print SERVER_READY.

### 7.2 Connection management

Use raw TCP sockets and selectors.

Support at least ten simultaneously connected clients.

Each connection must have its own:

-   Socket.
-   FrameBuffer.
-   Receive state.
-   Outgoing buffer.
-   Session reference.

Accept connections without blocking the event loop.

Use non-blocking socket operations.

Handle partial reads and writes.

A slow client must not block other clients or rooms.

### 7.3 Login

Clients send LOGIN_REQUEST containing:

-   user_id
-   name

The server must:

-   Validate both values.
-   Generate a session_id.
-   Maintain active user sessions.
-   Reject duplicate active user IDs using DUPLICATE_USER.
-   Release the user ID after logout or unexpected disconnection.

A disconnected user's ID must become available again.

### 7.4 Graceful shutdown

Ctrl+C must trigger orderly shutdown.

The server must:

-   Stop accepting new connections.
-   Close the listening socket.
-   Close active client sockets.
-   Release selector resources.
-   Clean up session and room resources.
-   Exit cleanly.

Do not leave the process permanently blocked.

Use try/finally and appropriate KeyboardInterrupt handling.

------------------------------------------------------------------------

## 8. Session implementation --- quizlib/session.py

Implement the session and user-connection management.

Suggested data:

-   user_id
-   name
-   session_id
-   socket
-   room_code
-   connection status
-   receive buffer
-   outgoing buffer

Maintain a reliable mapping between active user IDs and authenticated
sessions.

Responsibilities:

1.  Register new authenticated sessions.
2.  Enforce unique active user IDs.
3.  Resolve incoming session_id values.
4.  Maintain room membership references.
5.  Remove disconnected sessions.
6.  Release user IDs after logout.
7.  Notify RoomManager when a player disconnects.

The session registry must remain consistent with the server's active
socket connections.

Coordinate the interface with server.py and game.py rather than
duplicating state.

------------------------------------------------------------------------

## 9. Game implementation --- quizlib/game.py

This module contains the main business logic.

Implement:

-   Room
-   RoomManager
-   QuizEngine
-   Player state
-   Score management
-   Question timing and deadlines
-   Leaderboard generation

### 9.1 Room management

Support:

-   List quizzes.
-   Create room.
-   List joinable rooms.
-   Join room.
-   List participants.
-   Set readiness.
-   Leave room.
-   Start quiz.

Use `room_code` as the protocol field name.

Do not replace it with room_id in protocol messages.

Suggested documented game rules:

-   Minimum two players to start.
-   Maximum ten players per room.
-   The room creator becomes Host.
-   Only Host can start the quiz.
-   All connected players must be Ready.
-   A room cannot accept new players after the quiz starts.
-   Only lobby rooms appear in the joinable-room listing.
-   A player cannot belong to two rooms simultaneously.

Use deterministic room-code generation and prevent collisions.

### 9.2 State management

Follow the state terminology in the protocol appendix:

-   CONNECTED
-   AUTHENTICATED
-   LOBBY
-   QUESTION_OPEN
-   QUESTION_CLOSED
-   FINISHED

Room and session state transitions must be documented in code comments
and implemented consistently.

Prevent illegal transitions.

A room must not start if the player count or readiness requirements are
not satisfied.

### 9.3 Quiz engine

The server controls:

-   Quiz selection.
-   Question order.
-   Question distribution.
-   Question deadlines.
-   Accepted answers.
-   Scoring.
-   Result publication.
-   Final leaderboard.

Preserve question order from questions.json.

Do not introduce random question ordering unless explicitly documented
and justified.

Use the official `time_limit` value as the authoritative question
deadline.

Use `time.monotonic()`.

For each question:

1.  Set the question deadline.
2.  Broadcast QUIZ_STARTED_EVENT when the quiz begins.
3.  Broadcast QUESTION_EVENT.
4.  Accept at most one valid answer per active player.
5.  Validate question_id.
6.  Validate the answer value.
7.  Check the deadline.
8.  Reject duplicate answers.
9.  Close the question when every active player has answered or the
    deadline expires.
10. Calculate points.
11. Broadcast QUESTION_RESULT_EVENT.
12. Start the next question or finish the quiz.

Do not block the selectors loop while waiting for the timer.

### 9.4 Scoring

Correct accepted answer:

Award the question's configured points.

Incorrect answer:

Zero points.

Missing answer:

Zero points.

Late answer:

Zero points and return QUESTION_CLOSED.

Duplicate answer:

Reject it using DUPLICATE_ANSWER. Never award points twice.

An invalid answer must not corrupt the accepted-answer record.

Maintain one authoritative score record per player per room.

### 9.5 Leaderboard

Generate a deterministic ordered leaderboard.

Suggested ordering:

1.  Higher score first.
2.  Higher number of correct answers first.
3.  user_id ascending as the final tie-breaker.

Include:

-   rank
-   user_id
-   name
-   score
-   correct_answers

The final QUIZ_FINISHED_EVENT must contain:

-   quiz_id
-   final_leaderboard
-   winner

Ensure the winner is determined consistently, including tied-score
cases.

### 9.6 Multi-room isolation

At least two rooms must operate independently.

Each Room must own its:

-   players
-   readiness states
-   quiz selection
-   question index
-   current deadline
-   answers
-   scores
-   leaderboard
-   game state

Never use one shared timer or answer dictionary for all rooms.

Events from Room A must never be sent to Room B.

One room finishing must not terminate another room.

### 9.7 Disconnect handling

Define and implement deterministic behaviour.

Recommended rules:

-   Lobby player disconnects: remove the player and update membership.
-   Host disconnects in lobby: transfer Host to the earliest remaining
    connected player.
-   Empty lobby: close the room.
-   Player disconnects during play: mark them inactive, preserve their
    earned score, and exclude them from the active unanswered-player
    count.
-   Host disconnects during play: the game continues; Host privileges
    are no longer needed.
-   All players disconnect: finish or close the room and release
    resources.
-   Client reconnect is not required unless implemented and documented.

The server must never remain blocked waiting for a disconnected player.

------------------------------------------------------------------------

## 10. Client implementation --- client.py

Implement the compulsory command-line interface:

``` bash
python3 client.py --server <server_IP> --port <port> --id <user_id> --name <display_name>
```

The CLIENT must use the shared `quizlib.protocol` module.

### 10.1 Client architecture

Use:

-   Main thread: keyboard input and commands.
-   Background thread: server message receiving and asynchronous event
    handling.

The receive thread must:

-   Read TCP data.
-   Use FrameBuffer.
-   Handle fragmented and coalesced messages.
-   Process direct responses.
-   Process asynchronous events.
-   Display ERROR_RESPONSE messages.
-   Detect server disconnection.

Protect concurrent outgoing writes using a lock.

Do not allow multiple threads to corrupt the same socket frame.

### 10.2 Required commands

Implement the CLI command mapping from the appendix:

``` text
/help
/quizzes
/rooms
/create <quiz_id>
/join <room_code>
/players
/ready
/start
/answer <A|B|C|D>
/score
/leave
/quit
```

The client must maintain the current question_id received through
QUESTION_EVENT.

When a user enters `/answer A`, the client must send ANSWER_REQUEST
containing:

-   question_id
-   answer

Do not ask the user to manually enter question_id.

### 10.3 User interface

Display clearly:

-   Connection status.
-   Login result.
-   Available quizzes.
-   Available rooms.
-   Room code.
-   Host information.
-   Participant list.
-   Readiness.
-   Question number.
-   Question text.
-   Options A/B/C/D.
-   Time limit.
-   Answer submission result.
-   Correct answer after question closure.
-   Points awarded.
-   Current leaderboard.
-   Final leaderboard.
-   Server error messages.

The client must remain usable in a basic terminal.

No GUI, browser, web interface or graphical dashboard.

The client must never open or read questions.json.

------------------------------------------------------------------------

## 11. Testing requirements

Use Python Standard Library unittest only.

No pytest or third-party testing framework.

Every module owner must provide meaningful unit tests, and the complete
system must have integration tests.

### 11.1 test_quiz_loader.py

Test:

-   Valid question bank.
-   One-quiz valid hidden bank.
-   Multiple quizzes.
-   Missing file.
-   Empty file.
-   File exceeding 1 MB.
-   Invalid UTF-8.
-   Invalid JSON.
-   Non-object top-level JSON.
-   Wrong schema_version.
-   Missing required fields.
-   Wrong data types.
-   Invalid quiz count.
-   Invalid question count.
-   Duplicate quiz_id.
-   Duplicate question_id across different quizzes.
-   Invalid identifier characters.
-   Invalid options keys.
-   Missing option.
-   Additional option.
-   Invalid answer.
-   Invalid time_limit.
-   Invalid points.
-   Boolean supplied where integer is required.
-   Additional allowed object members.

### 11.2 test_protocol.py

Test:

-   Correct frame encoding.
-   Correct frame decoding.
-   One message fragmented into multiple TCP receives.
-   Multiple messages coalesced into one receive.
-   Correct message ordering.
-   Zero-length frame.
-   Oversized frame.
-   Invalid UTF-8.
-   Invalid JSON.
-   Non-object JSON.
-   Missing envelope fields.
-   Incorrect field types.
-   Unsupported protocol version.
-   Invalid message type.
-   request_id matching.
-   event_id handling.

### 11.3 test_session.py

Test:

-   Successful login.
-   Duplicate active user ID.
-   Session lookup.
-   Invalid session.
-   Logout.
-   Unexpected disconnect.
-   User ID reuse after disconnect.
-   Room membership cleanup.

### 11.4 test_game.py

Test:

-   Room creation.
-   Room listing.
-   Room joining.
-   Room capacity.
-   Host assignment.
-   Readiness.
-   Invalid start conditions.
-   Host-only start.
-   Room state transitions.
-   Correct scoring.
-   Incorrect scoring.
-   Duplicate answer.
-   Invalid answer.
-   Late answer.
-   Missing answer.
-   Question timeout.
-   Early closure after all active players answer.
-   Leaderboard ordering.
-   Final winner.
-   Host disconnect.
-   Player disconnect.
-   Two-room isolation.

### 11.5 test_client.py

Test:

-   CLI command parsing.
-   Valid commands.
-   Invalid commands.
-   Current question tracking.
-   Answer submission.
-   Server error display.
-   Server disconnection.
-   Asynchronous event handling.

### 11.6 test_server.py

Test:

-   Valid server startup.
-   SERVER_READY only after successful listening.
-   Invalid question bank prevents listening.
-   Non-zero exit on invalid startup.
-   Clean Ctrl+C shutdown.
-   Resource release.

### 11.7 test_client_server.py

This must test the actual submitted client.py and server.py as a pair.

Test the complete workflow:

1.  Start submitted server.
2.  Start submitted client.
3.  Login.
4.  List quizzes.
5.  Create room.
6.  Join room from another client.
7.  View participants.
8.  Ready.
9.  Start quiz.
10. Receive questions.
11. Submit answers.
12. Receive results.
13. View leaderboard.
14. Leave room.
15. Logout.

Do not rely exclusively on a separate test client that bypasses the
submitted client.py.

### 11.8 test_concurrency.py

This is especially important.

Test at least ten simultaneous connected clients across at least two
rooms.

Suggested setup:

Room A: - Five clients. - Quiz A. - Independent questions and answers.

Room B: - Five clients. - Quiz B. - Independent questions and answers.

Verify:

-   All ten clients remain connected.
-   Both rooms can run simultaneously.
-   Both rooms have independent question indexes.
-   Both rooms have independent deadlines.
-   Both rooms have independent scores.
-   Answers never cross room boundaries.
-   Events never cross room boundaries.
-   One room finishing does not interrupt another.
-   Disconnecting one client does not corrupt other sessions.

All tests must be repeatable.

------------------------------------------------------------------------

## 12. Docker development and verification

Use the supplied Docker environment.

Do not replace the supplied Dockerfile or compose.yaml without a
specific technical reason.

Because the supplied compose.yaml mounts its own directory to /code,
create a separate local development file:

`docker_env/compose.dev.yaml`

Suggested configuration:

``` yaml
services:
  python:
    build:
      context: .
      dockerfile: Dockerfile
    image: csi201-cw1:latest
    pull_policy: never
    working_dir: /code
    volumes:
      - ../Codes:/code
    stdin_open: true
    tty: true
```

This is a development-only configuration and must not be included in the
coursework submission.

Build:

``` bash
docker compose -f docker_env/compose.dev.yaml build
```

Run the complete test suite:

``` bash
docker compose -f docker_env/compose.dev.yaml run --rm python -m unittest discover -s tests -v
```

Run syntax checks:

``` bash
docker compose -f docker_env/compose.dev.yaml run --rm python -m compileall -q .
```

All integration-test server and client subprocesses should run inside
the same Docker container using loopback networking where appropriate.

If Docker is unavailable, you may run preliminary local Python 3.12
tests, but clearly label them as local tests, not Docker verification.

If the official examiner image differs from this supplied environment,
repeat the full test suite in that image before claiming final
compliance.

Do not fabricate Docker results or screenshots.

------------------------------------------------------------------------

## 13. README.md

Create a practical README.md containing:

1.  Project description.
2.  Requirements and Python version.
3.  Project directory structure.
4.  Server startup command.
5.  Client startup command.
6.  CLI command reference.
7.  Game rules and Host behaviour.
8.  Protocol overview.
9.  Question-bank format.
10. Testing commands.
11. Docker development commands.
12. Assumptions and known limitations.

Use the exact compulsory launch commands:

Server:

``` bash
python3 server.py --host <server_IP> --port <port> --questions <json_path>
```

Client:

``` bash
python3 client.py --server <server_IP> --port <port> --id <user_id> --name <display_name>
```

Do not write a separate academic report at this stage.

------------------------------------------------------------------------

## 14. Implementation workflow

Work in the following order.

### Phase 1 --- Inspect

-   Inspect all source documents.
-   Inspect the existing workspace.
-   Check Git status.
-   Preserve all existing user modifications.
-   Verify the supplied Docker files.
-   Verify questions_50.json.
-   Confirm the intended directory structure.

Do not overwrite unrelated files.

### Phase 2 --- Protocol first

Implement protocol.py.

Freeze the common envelope, exact message names, error codes and
FrameBuffer interface.

All other modules must use the same protocol definitions.

### Phase 3 --- Server foundations

Implement:

-   quiz_loader.py
-   session.py
-   server.py

Verify Task 1 and Task 2.

### Phase 4 --- Game logic

Implement game.py.

Verify Task 3 and Task 4.

### Phase 5 --- Client

Implement client.py.

Complete the paired client-server workflow.

### Phase 6 --- Integration

Connect all modules.

Resolve interface mismatches.

Test asynchronous events, response matching, disconnect handling and
room isolation.

### Phase 7 --- Full verification

Run all unit and integration tests inside Docker.

Fix all discovered bugs.

Repeat the complete test suite after important fixes.

Do not leave incomplete functions, placeholder implementations, fake
test results or unresolved TODOs in the submitted code.

### Phase 8 --- Final source review

Review every file.

Check:

-   Correct imports.
-   No circular dependencies.
-   No third-party packages.
-   No hard-coded server port.
-   No client access to questions.json.
-   No correct-answer leakage.
-   No blocking server networking operations.
-   No shared room state.
-   No missing cleanup.
-   No unhandled socket errors.
-   No protocol field-name mismatches.
-   No unnecessary files.

------------------------------------------------------------------------

## 15. Final deliverables and completion report

The final implementation must contain:

``` text
Codes/
├── server.py
├── client.py
├── questions.json
├── README.md
├── quizlib/
│   ├── __init__.py
│   ├── protocol.py
│   ├── quiz_loader.py
│   ├── session.py
│   └── game.py
└── tests/
    ├── test_quiz_loader.py
    ├── test_protocol.py
    ├── test_session.py
    ├── test_game.py
    ├── test_client.py
    ├── test_server.py
    ├── test_client_server.py
    └── test_concurrency.py
```

When finished, provide a concise engineering completion report
containing:

1.  Actual files created or modified.
2.  Implemented functionality corresponding to Task 1--Task 6.
3.  Protocol implementation and confirmed field names.
4.  Question-bank validation coverage.
5.  Unit test results.
6.  Paired client-server integration test results.
7.  Ten-client/two-room concurrency test results.
8.  Docker build and verification results.
9.  Known remaining defects or limitations.
10. Exact commands for running the submitted system.

Clearly distinguish:

-   Implemented.
-   Tested locally.
-   Tested in the supplied Docker environment.
-   Tested in the official examiner Docker image.

Do not claim a test passed unless it was actually executed successfully.

Do not create a Git commit without explicit authorization.

Do not create Development_Documentation.pdf, the final ZIP archive or
the demonstration video yet.

The immediate objective is a complete, stable, reproducible and fully
tested Python 3.12 CLI client-server application that satisfies the
official CSI201 Coursework I specification.
