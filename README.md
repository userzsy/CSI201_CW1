# CSI201 CW1: Networked Quiz Tournament

Python 3.12 command-line client/server coursework project. Source code, the
question bank, operating instructions and repeatable tests are in [Codes](Codes/README.md).
The application uses only the Python Standard Library and raw TCP sockets.
Actual environment identities, test results and retained logs are indexed in
[the verification record](verification/README.md).

## Windows development

Work directly in this Windows directory with Python 3.12. Docker is required only
for integration and compatibility verification after local development is stable.
No packages need to be installed. A local `.venv` is excluded from Git.

With an installed Python 3.12 interpreter, create the host environment once:

```powershell
python3 -m venv --without-pip .venv
.\.venv\Scripts\python.exe --version
Set-Location Codes
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe server.py --host 127.0.0.1 --port 5000 --questions questions.json
```

Use another terminal in `Codes` for each client:

```powershell
..\.venv\Scripts\python.exe client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
```

## Supplied Docker verification environment

`docker_env/Dockerfile`, `docker_env/compose.yaml`, and
`docker_env/questions_50.json` are preserved from the supplied archive.
`compose.dev.yaml` only changes the mount to the project `Codes` directory.
From the repository root:

```powershell
docker compose -f docker_env/compose.dev.yaml build
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
```

The source PDFs are under `reference`. The development instructions are project
reference material; the user's host-development strategy takes precedence over
their workflow suggestions. The coursework specification defines the compulsory
requirements; the protocol appendix is informative and is adopted as the design
baseline, with the choices described in `Codes/README.md`.

Local test results are preliminary. Supplied-environment Docker results and
official examiner-image results must be identified separately. The actual
examiner image/tag has not been independently established from these materials.
Repeat the suite in that published image before using results as assessment evidence.

This repository is the source development stage. Academic documentation, the
demonstration video and the final submission ZIP are separate later deliverables.
