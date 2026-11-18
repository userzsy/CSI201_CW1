# Verification Record / 验证记录

## Documentation Pass / 本次文档检查

2026-11-18：Windows Python 3.12.14 编译检查通过；完整测试 59 项，58 通过、1 项 POSIX SIGINT 测试跳过，用时 32.969 秒，与基线的通过和跳过数量一致。
The documentation pass compiled successfully on Windows Python 3.12.14. The full suite ran 59 tests in 32.969 seconds: 58 passed and the POSIX SIGINT case skipped, matching the baseline counts.

16 个 Python 文件去除说明字符串后的语法树保持一致；题库、Docker 配置和参考文件的哈希未变。Markdown 链接、代码块、表格和 18 个源文件的目录树检查通过。
All 16 executable ASTs match after excluding docstrings. Protected input files are unchanged, and Markdown links, fences, tables and the 18-file source tree passed checks.

本次仅运行本地验证，没有构建或运行 Docker；原日志与哈希清单保留为下面标明的历史基线。
This pass used local verification without a Docker build or run. The original logs and hash manifest remain the historical baseline identified below.

## Recorded Baseline / 已记录的基线

以下日志来自 2026-11-18 的实现基线 `42f7ff5`，不代表本次文档修改重新执行了 Docker 测试。
These logs describe implementation baseline `42f7ff5` from 2026-11-18. They do not claim a new Docker run for this documentation pass.

| 环境 / Environment | 结果 / Result | 证据 / Evidence |
| --- | --- | --- |
| Windows, CPython 3.12.14 | 59 项：58 通过、1 跳过；34.739 s / 58 passed, 1 skipped | [Local log / 本地日志](local-tests.txt) |
| Supplied Docker, Linux, CPython 3.12.16 | 59 项全部通过；19.514 s / All 59 passed | [Docker log / 容器日志](supplied-docker-tests.txt) |
| Official Examiner Docker Image | 镜像标签未确认，尚未验证 / Tag unconfirmed; not verified | 确认发布镜像后复测 / Rerun in the published image |

Windows 跳过的是 POSIX SIGINT 子进程测试；该测试在所供 Linux 容器中通过。本地结果仅用于初步检查。
The Windows skip is the POSIX SIGINT subprocess test, which passed in the supplied Linux container. Host results remain preliminary.

原始 Dockerfile 未修改，构建出的镜像为 `csi201-cw1:latest`：
The unchanged supplied Dockerfile produced this image:

```text
sha256:4e89089fe7c6bee76ee0c43f056b966a00a9c1db3cb0c0e323dba729c160ab3f
```

[构建日志 / Build log](supplied-docker-build.txt)记录了原镜像来源；不能仅凭该 Dockerfile 确认官方考核镜像身份。
The build log records the supplied base image; it does not establish the official examiner image identity.

## Coverage / 测试覆盖

| 任务 / Task | 模块 / Modules | 检查内容 / Checks |
| --- | --- | --- |
| 1 启动与题库 / Startup and bank | `server.py`, `quiz_loader.py` | Schema、边界、全局 ID、先校验后监听 / Schema, bounds, global IDs, validation before listening |
| 2 身份与连接 / Identity | `session.py`, `server.py`, `client.py` | 重复 ID、连接绑定、退出和 ID 复用 / Duplicate IDs, connection binding, cleanup and ID reuse |
| 3 房间 / Rooms | `game.py`, CLI pair | 创建、加入、准备、房主、离开 / Create, join, ready, host and leave |
| 4 答题 / Play | `QuizEngine`, paired tests | 题序、超时、重复和迟答、计分排名 / Order, timeouts, duplicate/late answers and ranking |
| 5 并发 / Concurrency | `test_concurrency.py` | 十个实际客户端、双房间、5 秒与 30 秒独立时限 / Ten actual clients, two rooms, independent 5/30-second deadlines |
| 6 异常 / Failures | Protocol and server tests | 拆包、粘包、坏消息、部分写入、断线和关闭 / Fragmentation, coalescing, malformed input, partial writes, disconnects and shutdown |

集成测试使用提交的两个程序；假时钟仅用于单元测试，集成测试保留真实的最小 5 秒时限。
Integration tests run the submitted entry points. Fake clocks are confined to unit tests; integration timeout checks use the real five-second schema minimum.

## Evidence Files / 证据文件

- [Source checks / 源码检查](source-checks.txt)：基线编译、标准库依赖和原始文件比较 / Baseline compilation, Standard Library imports and supplied-file comparisons.
- [SHA-256 manifest / 哈希清单](source-sha256.json)：记录基线源码字节；本次注释修改后不再作为工作区当前哈希 / Identifies baseline bytes, not the current files after comment edits.

测试命令和模块说明见[代码 README](../Codes/README.md)。See the code guide for commands and module responsibilities.

## Open Findings / 尚未解决的问题

前次代码审查在 Windows 与所供 Docker 环境中复现了以下问题，现有 59 项测试未覆盖；本次仅整理文档和注释，保留原行为。
The previous review reproduced these cases on Windows and in supplied Docker. The 59-test suite does not cover them; this documentation pass leaves behaviour unchanged.

| 问题 / Finding | 影响 / Impact |
| --- | --- |
| P1：题库选项中的孤立 Unicode 代理字符未在加载时拒绝 / Unpaired Unicode surrogate accepted in an option | 自动切题时编码失败，服务器退出并断开其他客户端 / Encoding fails on automatic question transition, terminating the server and disconnecting other clients |
| P2：房间列表超过 65,536 字节 / Room list exceeds the frame limit | 已用 160 个房间复现：正常 `/rooms` 请求导致请求者断线 / Reproduced with 160 rooms: a normal list request disconnects its requester |

其他范围限制：未验证 Windows 原生 Ctrl+C 或持续网络饱和负载；没有 TLS、密码、持久化、重连、全局房间上限或空闲超时。
Other limits: Windows native Ctrl+C and sustained network saturation were not exercised. There is no TLS, password authentication, persistence, resume, global room cap or idle timeout.
