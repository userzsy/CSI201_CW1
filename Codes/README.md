# Networked Quiz Tournament

## 1. Project Overview / 项目简介

Python 3.12 命令行答题系统，使用原始 TCP Socket，支持登录、房间、多人答题、计时和排行榜。
A Python 3.12 CLI quiz system using raw TCP sockets, with login, rooms, timed multiplayer questions and leaderboards. No GUI or third-party packages are used.

## 2. Project Structure / 项目目录结构

以下是源文件目录，不含运行生成的缓存。Source files are shown below; generated caches are omitted.

```text
Codes/
├── server.py                 # 服务器入口与连接管理 / Server entry and connections
├── client.py                 # 终端命令与消息收发 / CLI commands and messaging
├── questions.json            # 仅服务器读取的示例题库 / Server-only sample bank
├── README.md                 # 项目与运行说明 / Project and operating guide
├── quizlib/                  # 共享协议与服务器业务模块 / Protocol and server logic
│   ├── __init__.py           # 标记共享模块包 / Shared package marker
│   ├── protocol.py           # 消息、TCP 帧与错误定义 / Messages, TCP frames and errors
│   ├── quiz_loader.py        # 题库加载与校验 / Bank loading and validation
│   ├── session.py            # 用户身份与会话注册表 / Identity and session registry
│   └── game.py               # 房间、答题计时与评分 / Rooms, timing and scoring
└── tests/                    # unittest 测试 / unittest suite
    ├── __init__.py           # 题库夹具与子进程工具 / Fixtures and subprocess helpers
    ├── test_quiz_loader.py   # 单元：题库格式与边界 / Unit: bank schema and bounds
    ├── test_protocol.py      # 单元：帧、拆包与消息结构 / Unit: frames and envelopes
    ├── test_session.py       # 单元：登录与会话清理 / Unit: login and session cleanup
    ├── test_game.py          # 单元：房间、计时与计分 / Unit: rooms, timing and scores
    ├── test_client.py        # 客户端：命令与事件处理 / Client: commands and events
    ├── test_server.py        # 服务器：启动、TCP 与关闭 / Server: startup, TCP and shutdown
    ├── test_client_server.py # 集成：实际客户端和服务器 / Integration: submitted CLI pair
    └── test_concurrency.py   # 并发：十客户端、双房间 / Concurrency: ten clients, two rooms
```

## 3. Module Responsibilities / 模块职责

| 模块 / Module | 中文 | English |
| --- | --- | --- |
| `server.py` | 解析参数；管理 TCP 连接与缓冲区；分发请求；协调会话、房间和关闭 | Parses arguments, manages TCP buffers, dispatches requests, and coordinates sessions, rooms and shutdown |
| `client.py` | 连接并登录；解析命令；发送请求；接收异步消息并显示结果 | Connects and logs in, parses commands, sends requests, receives events and displays results |
| `protocol.py` | 定义消息、错误码与 Envelope；编码帧；用 `FrameBuffer` 保留未完整接收的字节 | Defines messages, errors and envelopes; encodes frames and buffers incomplete input |
| `quiz_loader.py` | 加载 JSON；校验官方 Schema；生成不含题目与答案的公开目录 | Loads JSON, validates the required schema and builds public quiz metadata |
| `session.py` | 用 `Session`、`SessionRegistry` 管理活跃身份、查询与离线清理 | Uses `Session` and `SessionRegistry` for active identities, lookup and cleanup |
| `game.py` | 用 `Player`、`Room`、`RoomManager`、`QuizEngine` 管理状态、截止时间、答题和排名 | Owns players, rooms, state transitions, independent deadlines, answers and rankings |

## 4. Application Workflow / 程序运行流程

```text
Client / 客户端 ── TCP ── Server / 服务器
  │                         ├── protocol.py     编解码 / Encoding and decoding
  └── protocol.py           ├── session.py      会话身份 / Session identity
      共享帧格式 / Framing   ├── game.py         房间与答题 / Rooms and play
                            └── quiz_loader.py  加载与校验 / Loading and validation
                                  └── questions.json
```

客户端不读取题库；服务器发送当前题目，并在该题关闭后公布答案。
Clients never read the bank. The server sends each question and reveals its answer only after closure.

登录 → 查看题库 → 创建或加入房间 → 全员准备 → 房主开始 → 答题与结果 → 最终排名 → 离开或退出。
Login → list quizzes → create/join → ready → host starts → questions/results → final ranking → leave/quit.

## 5. Running the Program / 程序运行

在 `Codes/` 中运行，每个进程使用独立终端。Run from `Codes/`, with a separate terminal for each process.

```bash
python3 server.py --host <server_IP> --port <port> --questions <json_path>
python3 client.py --server <server_IP> --port <port> --id <user_id> --name <display_name>
```

| 参数 / Argument | 用途 / Purpose |
| --- | --- |
| `--host` | 服务器绑定的 IPv4 地址 / Server bind IPv4 address |
| `--server` | 服务器地址或主机名 / Server address or hostname |
| `--port` | 双方使用的端口，1-65535 / Shared port, 1-65535 |
| `--questions` | 服务器题库路径 / Server question-bank path |
| `--id` | 当前在线用户的唯一 ID / Unique active user ID |
| `--name` | 显示名称，含空格时加引号 / Display name; quote names containing spaces |

```bash
python3 server.py --host 127.0.0.1 --port 5000 --questions questions.json
python3 client.py --server 127.0.0.1 --port 5000 --id 1001 --name Alice
python3 client.py --server 127.0.0.1 --port 5000 --id 1002 --name Bob
```

Windows 下把 `python3` 换成 `..\.venv\Scripts\python.exe`；环境创建见[仓库说明](../README.md)。
On Windows, use the repository's Python 3.12 virtual environment in place of `python3`.

题库校验和监听成功后才打印 `SERVER_READY`；非法题库输出 `STARTUP_ERROR` 并以非零状态退出。Ctrl+C 关闭服务器。
`SERVER_READY` appears only after validation and listening succeed. An invalid bank causes `STARTUP_ERROR` and a nonzero exit. Ctrl+C stops the server.

| 命令 / Command | 操作 / Action |
| --- | --- |
| `/help` | 显示命令 / Show commands |
| `/quizzes` | 查看公开题库目录 / List public quiz metadata |
| `/rooms` | 查看可加入的房间 / List joinable rooms |
| `/create <quiz_id>` | 创建房间并成为房主 / Create a room as host |
| `/join <room_code>` | 加入大厅中的房间 / Join a lobby |
| `/players` | 查看成员、房主与准备状态 / Show players, host and readiness |
| `/ready` | 设置已准备 / Set ready |
| `/start` | 房主请求开始 / Host requests start |
| `/answer <A\|B\|C\|D>` | 回答当前题目，无需输入题号 / Answer the current question without entering its ID |
| `/score` | 查看排名 / Show leaderboard |
| `/leave` | 离开房间 / Leave the room |
| `/quit` | 注销并退出 / Log out and exit |

## 6. Testing / 测试说明

所有测试使用标准库 `unittest`。集成与并发测试会启动实际的 `client.py`、`server.py` 子进程，通过回环 TCP 通信。
All tests use `unittest`. Integration and concurrency tests launch the submitted client and server as separate processes over loopback TCP.

在 `Codes/` 中执行 / From `Codes/`:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```

Windows 下使用 / On Windows:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m compileall -q .
```

从仓库根目录使用现有 Docker 配置 / From the repository root, using the existing Docker configuration:

```bash
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m unittest discover -s tests -v
docker compose -f docker_env/compose.dev.yaml run --rm -T python -m compileall -q .
```

`compose.dev.yaml` 把 `Codes/` 挂载到 `/code`，客户端与服务器子进程都在同一容器内运行。
The development compose file mounts `Codes/` at `/code`; both subprocesses run inside the same container.

| 环境 / Environment | 用途与证据 / Purpose and evidence |
| --- | --- |
| Windows Python 3.12 | 快速开发、初步检查；不能作为官方证据 / Rapid development and preliminary checks; not official evidence |
| Supplied Docker Environment | 完整集成、并发和兼容性检查 / Full integration, concurrency and compatibility checks |
| Official Examiner Docker Image | 正式考核；需确认发布的镜像和标签后复测 / Assessment environment; confirm the published image/tag and rerun |

Windows 会跳过 POSIX SIGINT 子进程测试；若操作系统禁止回环网络，相关集成测试也会明确跳过。
The POSIX SIGINT test skips on Windows; integration tests also report a skip if the OS denies loopback networking.
已有结果与环境标识见[验证记录](../verification/README.md)。See the verification record for actual results and environment identities.

## 7. Development Notes / 开发说明

- **并发 / Concurrency:** 标准库、原始 TCP 和单线程 `selectors` 事件循环；服务器使用非阻塞 I/O。Standard Library, raw TCP and one selectors loop with non-blocking server I/O.
- **计时 / Timing:** 每个 `Room` 保存独立 `deadline`，用 `time.monotonic()` 判断；没有独立 Timer 模块。Each room owns a monotonic deadline; there is no separate timer module.
- **客户端 / Client:** 后台接收事件，主线程处理命令；额外的 stdin 读取线程让服务器断线时能够结束等待。A receiver handles events; the main thread dispatches commands, with a stdin reader allowing exit on server loss.
- **协议 / Protocol:** 4 字节大端长度加 UTF-8 JSON，载荷上限 65,536 字节；字段为 `version`、`type`、`request_id`、`event_id`、`session_id`、`payload`。Frames use a four-byte big-endian length and the listed envelope fields. Responses match request IDs; events have unique event IDs.
- **题库 / Bank:** 示例为 5 套、50 题；校验器接受 1-20 套、每套 5-50 题，检查全局题号、整数、选项、时限和分值。The sample has five quizzes and fifty questions; validation follows the required schema, including global question IDs and strict integers.

### Game Rules / 游戏规则

- 每房间最多 10 人，至少 2 人且全员准备后由房主开始；开始后不再接受加入。Rooms hold up to ten players; at least two, all ready, are required to start. Only the host starts; no joins during play.
- 题目按文件顺序；全员作答或截止时结算。正确答案获得题目分值，错误、缺答和迟答为零；重复答案被拒绝。Questions follow file order and close when all active players answer or time expires. Correct answers earn configured points; wrong, missing and late answers earn zero. Duplicates are rejected.
- 排名按分数降序、答对数降序、用户 ID 字典序；同一顺序决定获胜者。Rank by score, correct-answer count, then user ID; this order also selects the winner.
- 大厅房主离开后转交最早加入的剩余成员；游戏中离线者保留成绩，并退出等待作答人数。空房间被移除。Lobby hosts transfer to the earliest remaining member. Departed players keep scores and no longer delay question closure. Empty rooms are removed.

### Known Limits / 已知限制

系统无 TLS、密码认证、持久化或重连恢复，仅面向课程网络；会话 ID 不证明真实身份。
There is no TLS, password authentication, persistence or game resume; the system targets a coursework network.

前次审查发现两处尚未修复的问题：异常 Unicode 选项可能导致切题时服务器退出；过大的房间列表会使 `/rooms` 请求者断线。
Two findings remain open: an unpaired Unicode surrogate in an option can crash the server on question transition, and an oversized room list disconnects its requester. This documentation pass leaves those behaviours unchanged.

## 8. Team Development / 小组开发

可按协议、服务器、客户端、游戏逻辑和测试分工。修改共享协议、数据结构或接口前，先确认调用方和接收方兼容，并运行相关测试及完整集成测试。
Work can be divided by module. Before changing shared messages, data structures or interfaces, check compatibility with callers and recipients, then run the relevant tests and full integration suite.
