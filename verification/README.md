# Verification record — 2026-11-18

This is a development evidence index, not the academic Development Documentation.

| Environment | Result | Evidence |
| --- | --- | --- |
| Windows host, CPython 3.12.14 | 59 run: 58 passed, 1 skipped; 34.739 s | [Local test log](local-tests.txt) |
| Supplied Dockerfile build, Linux, CPython 3.12.16 | 59 run: 59 passed, no skips; 19.514 s | [Docker test log](supplied-docker-tests.txt) |
| Official published examiner image/tag | Not independently identified; not claimed as verified | Rerun in the published image before assessment |

The Windows skip is the POSIX SIGINT subprocess test. It passed in Linux Docker.
Local results remain preliminary and must not be presented as official verification.
The supplied Dockerfile was built without modifications. Its resulting image is
`csi201-cw1:latest`, ID
`sha256:4e89089fe7c6bee76ee0c43f056b966a00a9c1db3cb0c0e323dba729c160ab3f`.
The original Dockerfile uses a Python 3.12 slim base through the supplied registry
mirror; the published examiner image identity cannot be inferred from this alone.
The complete [build log](supplied-docker-build.txt) is retained.

## Requirement coverage

| Task | Implementation | Verification |
| --- | --- | --- |
| 1: Startup and bank validation | `server.py`, `quiz_loader.py` | Invalid files and schema fields; one-quiz banks; global IDs; strict integers; bounds; extra fields; validation before socket creation; readiness after listening |
| 2: Identity and connections | `server.py`, `session.py`, `client.py` | Duplicate active ID rejection; connection-bound sessions; logout/disconnect cleanup; ID reuse; real CLI login |
| 3: Catalogue and rooms | `game.py`, `server.py`, `client.py` | Create/join/list/players/ready/start/leave; capacity; host-only start; lobby host transfer |
| 4: Tournament play | `QuizEngine` in `game.py` | Question order; real and deterministic deadlines; correct/wrong/missing/late/duplicate answers; personal awards; tie ordering; final winner; no premature answer disclosure |
| 5: Concurrency | Per-room state and single selectors loop | Ten actual submitted CLI clients in two rooms; real 5-second versus 30-second deadlines; independent progress/scores; event isolation; one room finishes while the other remains active |
| 6: Failure handling | Framing, output buffers, cleanup, CLI validation | Fragmented/coalesced wire input; malformed peers; partial writes; backpressure limit; disconnects during play; client exit on server loss; SIGINT; unrelated sessions continue |

The paired integration tests execute the submitted `client.py` and `server.py` as
separate processes, and cover the complete login-to-logout workflow. The
concurrency test likewise launches ten submitted clients, rather than using only
an alternative wire-level test client. Unit tests additionally inspect deterministic
boundary conditions. The real timeout tests retain the schema minimum of five seconds.

## Source review and preservation

[Source checks](source-checks.txt) record successful host and Docker compile checks,
Standard Library import review, and byte-for-byte comparisons with the original
supplied ZIP. `Dockerfile`, `compose.yaml`, `questions_50.json`, and the submitted
sample question bank are unchanged. [SHA-256 manifest](source-sha256.json) identifies
the tested source, reference files and Docker inputs. The development compose file
mounts `Codes` and is kept outside the source submission directory.

This continuation added operating documentation, a Git ignore file and this evidence
record, and strengthened `test_concurrency.py` to exercise actual independent room
timeouts. The existing application modules passed review and tests without source
changes during this continuation. No defect was observed in the executed suite.

## Remaining limits

- Official examiner-image verification is pending identification of its published tag.
- Windows native Ctrl+C was not exercised; graceful shutdown was tested through
  the server API on Windows and SIGINT in the supplied Linux container.
- Output backpressure and partial writes have focused tests; a sustained real
  network saturation/load soak was not performed.
- No TLS, passwords, persistence, game resume, global room cap or idle timeout.
  Very large room listings are not paginated. This is intended for the coursework
  tournament scope, not public Internet hosting.
- The academic report, demonstration video and final submission ZIP are later
  deliverables and have not been created at this stage.
