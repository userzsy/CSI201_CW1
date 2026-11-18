# Application-layer protocol design

## Design overview

This document specifies the protocol implemented by `Codes/client.py`, `Codes/server.py` and `Codes/quizlib/protocol.py`.
The supplied appendix is an informative baseline; this document records the actual version 1 design and its room-pagination extension.
The coursework specification remains authoritative for compulsory behaviour and the question-bank schema.

Each client uses one persistent raw TCP connection. The server controls identity, room membership, question order, deadlines and scoring.
Messages distinguish requests, direct responses, asynchronous events and recoverable errors. Only the server reads the local bank.

## TCP framing

```text
4-byte unsigned big-endian N | N bytes of UTF-8 JSON
```

- The prefix uses `struct.pack("!I", N)`. N counts payload bytes, excluding the prefix, and must be 1-65,536.
- The payload is one JSON object. Outgoing JSON uses UTF-8 without replacing invalid Unicode; non-JSON numeric constants are rejected.
- Each connection's `FrameBuffer` retains incomplete input and yields complete messages in stream order. One receive can contain part of a frame or several frames.
- Invalid lengths are rejected from the header. Invalid UTF-8 bytes, malformed JSON, non-object payloads or invalid envelopes produce `INVALID_MESSAGE` and close only the offending connection.
- Valid messages preceding a bad frame in the same receive are dispatched first. Partial server sends retain unsent bytes in the connection's output buffer.

`FrameSizeError`, a `ProtocolError` subclass, identifies outbound size overflow. Other encoding failures remain `ProtocolError`.
Room pagination catches size overflow to shrink a page; it reports unexpected serialization failures as `INTERNAL_ERROR` rather than treating them as oversized pages.

## Common envelope

All six fields are mandatory, including fields whose value is null. Additional envelope members are allowed.

```json
{
  "version": 1,
  "type": "LOGIN_REQUEST",
  "request_id": "req-000001",
  "event_id": null,
  "session_id": null,
  "payload": {"user_id": "1001", "name": "Alice"}
}
```

| Field | Type and rule |
| --- | --- |
| `version` | Integer 1; booleans and other versions are rejected. |
| `type` | Known, case-sensitive message name. |
| `request_id` | Null or a 1-128-character string. Requests and normal responses require it; direct responses repeat the request value. |
| `event_id` | Null or a 1-128-character string. Events require a unique value and null `request_id`; requests and responses use null. |
| `session_id` | Null before login; a 1-128-character string identifying the authenticated connection afterward. |
| `payload` | JSON object; may be empty. |

Successful login returns the same session ID in the response envelope and payload. Later requests must use the session bound to that socket.
Events carry the recipient's session ID and have unique IDs even when the same event data is sent to several players.
An `ERROR_RESPONSE` may have null `request_id` when framing or envelope failure prevents safe correlation. Errors never have an event ID.
Request IDs correlate responses; request replay and general deduplication are not implemented.

## Request and response catalogue

Suffixes below are literal message names. All recoverable failures use `ERROR_RESPONSE` instead of a successful response.

| Request | Request payload | Direct response | Response payload |
| --- | --- | --- | --- |
| `LOGIN_REQUEST` | `user_id`, `name` | `LOGIN_RESPONSE` | `success: true`, `session_id` |
| `LIST_QUIZZES_REQUEST` | `{}` | `LIST_QUIZZES_RESPONSE` | `quizzes` |
| `LIST_ROOMS_REQUEST` | Optional `cursor` | `LIST_ROOMS_RESPONSE` | `rooms`, `next_cursor` |
| `CREATE_ROOM_REQUEST` | `quiz_id` | `CREATE_ROOM_RESPONSE` | `success: true`, `room_code`, `room` |
| `JOIN_ROOM_REQUEST` | `room_code` | `JOIN_ROOM_RESPONSE` | `success: true`, `room` |
| `PLAYER_LIST_REQUEST` | `{}` | `PLAYER_LIST_RESPONSE` | `players` |
| `ANSWER_REQUEST` | `question_id`, `answer` | `ANSWER_RESPONSE` | `accepted: true`, `question_id` |
| `LEADERBOARD_REQUEST` | `{}` | `LEADERBOARD_RESPONSE` | `leaderboard` |

| Request without direct success response | Payload | Success indication |
| --- | --- | --- |
| `READY_REQUEST` | Boolean `ready` | `PLAYER_STATUS_EVENT`; the CLI sets true, while the protocol also accepts false. |
| `START_QUIZ_REQUEST` | `{}` | `QUIZ_STARTED_EVENT`, then `QUESTION_EVENT`. |
| `LEAVE_ROOM_REQUEST` | `{}` | Status event also sent to the leaver, or `ROOM_CLOSED_EVENT` if no active players remain. |
| `LOGOUT_REQUEST` | `{}` | Identity release and connection closure; no logout response type. |

Public quiz entries contain `quiz_id`, `title`, `description` and `question_count`, in bank order. They never contain question text, options or answers.
Player entries contain `user_id`, `name`, `ready` and `is_host` for active members.
Full room views returned on create/join contain the metadata below plus `players`; pagination does not remove those participant details.
Leaderboard entries contain `rank`, `user_id`, `name`, `score` and `correct_answers`, including retained scores of departed players.

## Room listing pagination

### Requests and ordering

The first request may use an empty object or a null cursor:

```json
{"cursor": null}
```

Use the previous page's `next_cursor` for each subsequent request, with a fresh request ID:

```json
{"cursor": "R000020"}
```

The server accepts null or a nonempty string of at most 128 characters. Wrong types, empty strings and longer strings return correlated `INVALID_MESSAGE` without closing the connection.
The cursor need not identify an existing room, so deletion of the previous page's last room does not prevent progress.
Rooms are sorted lexically by `room_code`; only codes strictly greater than the cursor are considered. Only LOBBY rooms with fewer than ten active players are joinable.

### Responses and frame size

Each room entry contains exactly the listing metadata:

```json
{
  "rooms": [
    {"room_code": "R000020", "quiz_id": "quiz1", "title": "Networking Basics",
     "host_id": "1001", "player_count": 3, "capacity": 10, "state": "LOBBY"}
  ],
  "next_cursor": "R000020"
}
```

This is a payload example; the complete common envelope surrounds it on the wire. The non-null cursor indicates that later rooms remain.
Public listings omit `players`. Join a room and use `/players` for detailed participants.

- A page contains at most twenty rooms; this is a page limit, not a global room limit.
- The server constructs the complete response with the real request and session IDs, then measures it with `encode_frame()`.
- If it exceeds 65,536 payload bytes, the room count is halved and encoding is retried. No rooms are silently discarded from later pages.
- `next_cursor` is the last code actually returned when more rooms remain; otherwise it is null. A valid individual listing fits the limit; an unexpected single-listing overflow returns `INTERNAL_ERROR`.

The final page may contain rooms with a null cursor. An empty result is:

```json
{"rooms": [], "next_cursor": null}
```

Pages reflect current room state. There is no snapshot or reservation across pages; joinability can change before a user joins. Completeness and no-duplicate acceptance tests use a stable 160-room dataset.

### Client handling

One `/rooms` command initializes an accumulator. The client follows every non-null cursor using a unique request ID and validates each corresponding response and session.
It requires increasing room codes and a non-null cursor that matches the page's last code and advances beyond the previous cursor. Empty pages with a non-null cursor, repeated entries and malformed or non-progressing cursors are protocol errors.
Only the final combined `LIST_ROOMS_RESPONSE` is printed; that terminal output can be larger than a single network frame.

Overlapping `/rooms` commands are rejected locally without replacing the active accumulator. Other responses and room events may interleave normally.
An error for the current page, an uncorrelated fatal error or a disconnect clears partial results. Invalid server protocol data ends the client's receive loop.
Follow-up sends occur after releasing `state_lock`, preserving the `send_lock`-then-`state_lock` order.

## Server events

Events have null `request_id`, a unique `event_id` and the recipient's session ID.

| Event | Payload |
| --- | --- |
| `PLAYER_STATUS_EVENT` | `room_code`, active `players`, `host_id` |
| `ROOM_CLOSED_EVENT` | `room_code`, `reason` |
| `QUIZ_STARTED_EVENT` | `quiz_id`, `title`, `total_questions` |
| `QUESTION_EVENT` | `question_id`, one-based `number`, `text`, `options`, `time_limit`, `points` |
| `QUESTION_RESULT_EVENT` | `question_id`, `correct_answer`, recipient's `your_answer`, `points_awarded`, `leaderboard` |
| `QUIZ_FINISHED_EVENT` | `quiz_id`, `final_leaderboard`, `winner` (the first ranked entry, or null if empty) |

Room events go only to the room's active participants, with the departure acknowledgement also sent to a connected leaver.
`ROOM_CLOSED_EVENT` is used when the final active player leaves in any phase. Open-question events never contain the answer.

## Error model

```json
{"code": "QUESTION_CLOSED", "message": "The current question is closed"}
```

The object above is the payload of `ERROR_RESPONSE`. Recoverable errors repeat the request ID and keep the connection usable.

| Code | Meaning |
| --- | --- |
| `INVALID_MESSAGE` | Invalid envelope, unsupported message or malformed request fields, including cursor type/length. |
| `INVALID_SESSION` | Missing, unknown or incorrectly bound session, or an invalid login state. |
| `DUPLICATE_USER` | User ID already has an active session. |
| `QUIZ_NOT_FOUND` | Requested quiz is absent. |
| `ROOM_NOT_FOUND` | Requested room is absent or its join code is not a string. |
| `ROOM_FULL` | Room has ten players. |
| `ALREADY_IN_ROOM` | User must leave the current room before creating or joining another. |
| `NOT_ROOM_HOST` | A non-host attempts to start. |
| `PLAYERS_NOT_READY` | Fewer than two players or not all players ready. |
| `QUESTION_CLOSED` | Answer targets a closed question or arrives at/after its deadline. |
| `DUPLICATE_ANSWER` | An answer is already accepted for this player and the open question. |
| `INVALID_ANSWER` | Invalid answer value or mismatched question ID. |
| `INVALID_STATE` | Operation is not allowed in the room's current state. |
| `NOT_IN_ROOM` | Operation requires active membership. |
| `INTERNAL_ERROR` | Unexpected room-list encoding failure, including an impossible individual overflow. |

`INVALID_STATE`, `NOT_IN_ROOM` and `INTERNAL_ERROR` extend the informative appendix's error set. Existing error names remain unchanged.
Unsafe input framing/envelopes cannot be recovered and close only that peer after an uncorrelated `INVALID_MESSAGE` when possible.

## Session, room and question behaviour

- Login requires a nonblank printable `user_id` of 1-64 characters and `name` of 1-100 characters. Active IDs are unique and case sensitive; display names need not be unique. Logout or disconnect releases the ID.
- A `Session` stores identity and a room reference, not a separate timer or networking thread. The connection owns framing and output buffers.
- Creators become host. Room codes are a monotonically increasing sequence such as `R000001`; codes are not reused during a server lifetime.
- Rooms transition `LOBBY -> QUESTION_OPEN -> QUESTION_CLOSED -> QUESTION_OPEN/FINISHED`. Result publication is immediate, followed by the next question or final ranking without a blocking pause.
- Each room owns its answers, scores, question index and `time.monotonic()` deadline. The server loop checks all rooms independently.
- Answers require the current question ID and exactly A, B, C or D. Invalid answers do not consume a turn. Each accepted answer is scored once at closure: configured points for correct, zero otherwise.
- Questions close at the deadline or after every active player answers. An answer acknowledgement is queued before early-close result events. Answers at the exact deadline are late.
- Ranking is score descending, correct answers descending, then user ID ascending. Consecutive ranks also determine a single winner in a tie.
- Lobby departures remove membership and transfer host to the earliest remaining member. During play, departed players become inactive but retain scores and accepted answers. They no longer count as unanswered players; host departure does not stop play. Empty rooms are removed.

## Validation and connection handling

The complete bank is validated before the listening socket is created. Required text, including option values, must encode as strict UTF-8.
An escaped unpaired surrogate causes a field-specific `STARTUP_ERROR`, nonzero process exit and no `SERVER_READY` or listening port.
Identifiers and answers have restricted character rules; option values retain the schema's 1-200-character rule without an added printability restriction. Valid Unicode and supplementary characters remain supported. Extra bank members are allowed except extra option keys.

The server uses one non-blocking selectors loop. Each connection has an input decoder and output buffer; a client exceeding the 1 MiB output-buffer cap is disconnected without blocking other rooms.
SIGINT/SIGTERM stop the loop and release listening/client sockets, sessions, rooms and selector resources. No final shutdown event is guaranteed.
There is no TLS, password authentication, persistence or reconnect/resume. See [verification](../verification/README.md) for executed tests and remaining environment limits.
