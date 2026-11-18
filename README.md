# CSI201 CW1: Networked Quiz Tournament

Python 3.12 命令行 TCP 答题项目。[代码与操作说明](Codes/README.md)介绍目录、模块、运行和测试；[验证记录](verification/README.md)保留实际测试证据。
A Python 3.12 CLI quiz project using raw TCP sockets. The code guide covers structure and operation; the verification record identifies test evidence.

## Windows Development / Windows 开发

日常编码和初测直接在 Windows 上完成，不需要启动 Docker，也不需要第三方包。
Use host Python 3.12 for editing, debugging and preliminary tests. Docker is not required for this workflow.

已安装 Python 3.12 时，可在仓库根目录创建环境；已有 `.venv` 可直接使用。
From the repository root, create an environment with an installed Python 3.12 interpreter, or reuse the existing `.venv`:

```powershell
python3 -m venv --without-pip .venv
.\.venv\Scripts\python.exe --version
Set-Location Codes
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe server.py --host 127.0.0.1 --port 5000 --questions questions.json
```

每个客户端在另一个 `Codes/` 终端中运行 / Run each client in another terminal in `Codes/`:

```powershell
..\.venv\Scripts\python.exe client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
```

## Repository Materials / 仓库材料

| 路径 / Path | 内容 / Contents |
| --- | --- |
| `Codes/` | 源代码、示例题库与测试 / Source, sample bank and tests |
| `docker_env/` | 原始 Docker 配置及单独的开发挂载配置 / Supplied Docker inputs and a separate development mount |
| `reference/` | 课程规范与协议参考 PDF / Coursework specification and informative protocol appendix |
| `verification/` | 测试日志、环境标识和历史源码哈希 / Test logs, environment identities and historical source hashes |

课程规范规定必需行为；协议附录是采用的设计参考。开发顺序遵循用户指定的 Windows 优先策略。
The specification defines compulsory behaviour; the informative appendix is the protocol baseline. Development follows the user's host-first strategy.

## Docker Verification / Docker 验证

`Dockerfile`、`compose.yaml` 和原题库保持不变。`compose.dev.yaml` 将 `Codes/` 挂载到 `/code`。
The supplied configuration and bank are preserved; the separate development compose file mounts the source directory.
在已有镜像的情况下，从仓库根目录运行 / With the image already available, run from the repository root:

```powershell
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
```

本次文档整理无需重建 Docker。本地、所供 Docker 和官方考核镜像的结果必须分别记录；官方镜像标签尚未确认。
This documentation pass does not require a Docker rebuild. Keep host, supplied-container and official examiner results distinct; the official tag is still unconfirmed.

开发文档 PDF、演示视频和最终提交 ZIP 属于后续交付。Documentation, the demonstration video and the submission ZIP remain separate later deliverables.
