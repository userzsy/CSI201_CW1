# CSI201 CW1: Networked Quiz Tournament

## Project Overview

A Python 3.12 command-line quiz tournament using raw TCP sockets and the Standard Library. The coursework specification defines compulsory requirements; the supplied protocol appendix is informative.

## Main Features

- Login with unique active user IDs; create, join and manage quiz rooms.
- Play timed questions with server-controlled scoring and final rankings.
- Run independent rooms concurrently; retrieve large room lists automatically.
- Validate the complete question bank before opening the listening socket.

## Project Structure

```text
Codes/          Submitted client, server, shared modules, sample bank and tests
docs/           Protocol specification and verification/demonstration guide
verification/   Results, retained evidence and recording runbook
docker_env/     Unmodified supplied inputs and the existing development compose file
reference/      Original coursework specification and informative protocol appendix
```

## Development and Verification Status

Implementation and P1/P2 fixes are complete. Normal coding and preliminary tests use Windows Python 3.12 without Docker.

| Environment | Latest recorded suite |
| --- | --- |
| Windows Python 3.12.14 | 83 passed, 0 failed, 1 POSIX-only skip |
| Supplied development Docker environment | 84 passed, 0 failed, 0 skipped |
| Learning Mall Supplied Docker Environment | 84 passed, 0 failed, 0 skipped |

The Learning Mall image was built locally from the supplied Dockerfile. Its verification also completed an official-bank, two-client CLI workflow and Linux SIGINT shutdown. See the evidence below for image identity and test scope. The report, final demonstration video and submission ZIP remain separate deliverables.

## Documentation

| Document | Purpose |
| --- | --- |
| [Codes/README.md](Codes/README.md) | Source structure and usage |
| [Protocol design](docs/protocol-design.md) | Application-layer protocol |
| [Verification and demonstration guide](docs/verification-and-demonstration-guide.md) | Docker, testing and video preparation |
| [Verification record](verification/README.md) | Verification results and evidence |
| [Demo runbook](verification/examiner-image/demo-runbook.md) | Practical recording sequence |

## Quick Links

[Host setup and launch](Codes/README.md#requirements-and-launch-commands) · [CLI commands](Codes/README.md#commands) · [Docker preparation](docs/verification-and-demonstration-guide.md#environment-preparation) · [Recorded results](verification/README.md)
