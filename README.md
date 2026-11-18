# CSI201 CW1: Networked Quiz Tournament

A Python 3.12 command-line quiz tournament using raw TCP sockets and the Standard Library.

- Login with unique active user IDs; create, join and manage quiz rooms.
- Play timed questions with server-controlled scoring and final rankings.
- Run independent rooms concurrently; retrieve large room lists automatically.
- Validate the complete question bank before opening the listening socket.

## Project structure

```text
Codes/          Client, server, shared modules, sample bank and tests
docs/           Implemented application-layer protocol
verification/   Test results, acceptance checklist and retained logs
docker_env/     Unmodified supplied inputs and the existing development compose file
reference/      Original coursework specification and informative protocol appendix
```

## Quick start

Use Python 3.12. From `Codes/`, start the server and each client in separate terminals:

```bash
python3 server.py --host 127.0.0.1 --port 5000 --questions questions.json
python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
python3 client.py --server 127.0.0.1 --port 5000 --id 1002 --name Bob
```

On Windows, the existing workspace environment is `..\.venv\Scripts\python.exe` when running from `Codes/`.
For a new checkout, create `.venv` at the repository root with an installed Python 3.12 interpreter:

```powershell
python -m venv --without-pip .venv
.\.venv\Scripts\python.exe --version
```

Use `/help` for commands. Both players join the same room and use `/ready`; the host then uses `/start`.
Normal editing, debugging and preliminary tests run on Windows without Docker.

## Documentation

- [Source and operating guide](Codes/README.md): files, launch arguments, commands and game rules.
- [Protocol design](docs/protocol-design.md): authoritative description of the implemented wire protocol.
- [Verification record](verification/README.md): environments, full results and acceptance evidence.

The coursework specification defines compulsory requirements; the supplied protocol appendix is informative.
The application does not require a GUI, database, package installation or external service.
Official examiner-image verification remains pending until its published image and tag are confirmed.
The academic PDF, demonstration video and submission ZIP are separate later deliverables.
