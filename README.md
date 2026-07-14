# Codex DMX Proxy

**GitLab Project Name:** `Codex DMX Proxy`
**Stable repository Path:** `codex-dmx-proxy`

一个仅绑定 loopback 的本地 *Responses* 兼容适配器。它在 Codex 与任意已验证的第三方
OpenAI Responses 端点之间，净化**可判定不可重放**的历史输入，而不改写 Codex 会话。

它曾首先用于诊断通过 **dmxapi** 使用 **Codex** 时的报错：

> The encrypted content `gAAA...` could not be verified.
> Reason: Encrypted content could not be decrypted or parsed.

以及相关的 `invalid_payload` / `stream disconnected before completion`。

跨平台（macOS / Linux / Windows），纯 Python 标准库，**零第三方依赖**，**包内零密钥**。

---

## 这是什么问题

Codex 使用 OpenAI 的 *Responses* wire API。每一轮，模型可能返回一个 `reasoning` 项，里面带一个
`encrypted_content`（`gAAAAAB...` 开头的 Fernet 加密块）。Codex 把它存下来，并在**之后每一轮
重放**。dmxapi 作为第三方中转，用自己的密钥加密这些块；密钥轮换 / 后端路由后，它无法再验证一个
被递回来的旧块 → 报 `encrypted content could not be verified`。

Codex 是闭源二进制，**没有配置项能关掉这个重放**。因此适配器只在出站边界移除顶层、已重放的
`reasoning` 项和请求的 `reasoning.encrypted_content` include；它保留所有其他有类型的
`encrypted_content`，因为 agent message 中该字段可能是必填 payload。对由早期版本遗留的无 payload
空壳块，只在请求边界剔除该坏块。模型照常推理；本地历史、SQLite、JSONL 和模型元数据保持不变。

这是一类第三方端点的 replay-compatibility 问题；具体根因、可验证范围和上游限制必须以当前端点
的响应与回归测试为准，不能把某个供应商的历史症状外推为通用结论。

---

## 安装

前提：Python 3.12+，且至少跑过一次 Codex（这样 `~/.codex/config.toml` 已存在）。仅 Python
标准库是运行依赖；安装器不会下载依赖、Token 或上游配置。

```bash
# 主通道
git clone ssh://git@192.168.64.101:1122/dig/misc/llm-third-party-api/codex-dmx-proxy.git
cd codex-dmx-proxy
python3 install.py

# 备通道（无 git）：从 GitLab Releases 下载 zip → 解压 → cd 进去 → python3 install.py
```

Windows 上用 `py -3 install.py`。

安装器会：探测平台 + Python 绝对路径 → 定位 `~/.codex/config.toml` → 复制代理+看门狗到
`~/.codex/dmx-proxy/` → 把 provider 的 `base_url` 改指向本地代理（先备份）→ 注册开机自启的看门狗
→ 验证 `/v1/models` 返回 2xx/4xx。

**路由变更后**：Codex 桌面 App 可能缓存配置；按该客户端正常方式重载后，已运行会话才会采用新路由。
Proxy 不会改写会话历史；若历史本身仍包含上游不兼容数据，代理会在出站边界净化可判定的不兼容项。

### 启用 / 停用 Proxy（不卸载）

安装器实际写入过受管路由时，可使用安装目录内的控制程序：

```bash
python3 ~/.codex/dmx-proxy/control.py status
python3 ~/.codex/dmx-proxy/control.py disable  # 改回安装前记录的直连路由；保留 Proxy 与守护进程
python3 ~/.codex/dmx-proxy/control.py enable   # 恢复 loopback Proxy 路由
```

此开关只更改安装器记录的 `base_url`；它不会停止服务、删除文件、改写会话或覆盖后续人工配置。若配置或备份
发生漂移，命令会拒绝写入并提示重新安装/人工检查。

#### AIGW 管理 Codex 路由时

若 Codex 的 `[model_providers.aigw]` 投影由 **AIGW** 管理，`aigw sync` 会以 AIGW 的 canonical
endpoint 覆盖直接写入 `~/.codex/config.toml` 的结果。因此应让 AIGW 保持路由权威，Proxy 只负责数据面与
生命周期。一次性登记当前的 AIGW Account 后，仍使用同一份便捷开关：

```bash
# 当前 endpoint 必须已是代理地址或此处记录的直连地址；否则拒绝接管。
python3 ~/.codex/dmx-proxy/control.py adopt-aigw \
  --aigw-account <account> \
  --direct-url https://gateway.example/v1

python3 ~/.codex/dmx-proxy/control.py status
python3 ~/.codex/dmx-proxy/control.py disable  # 由 aigw account edit + sync 改回直连
python3 ~/.codex/dmx-proxy/control.py enable   # 由 aigw account edit + sync 恢复 loopback Proxy
```

该模式不读取或保存 AIGW Token；仅保存 AIGW 配置路径、Account 名称与两条可验证 endpoint。若 canonical
endpoint 已被其他操作改为第三个值，开关会 fail-closed，绝不覆盖。`control.py` 每次变更后都会复核 canonical
AIGW 配置；已运行的 Codex 仍应按客户端正常方式重载。

### 卸载

```bash
python3 uninstall.py            # 停服务 + 回滚 config 备份
python3 uninstall.py --purge    # 另外删掉 ~/.codex/dmx-proxy/
```

---

## 工作原理（架构）

```
Codex ──HTTP──> loopback Proxy :8791 ──窄化重放兼容转换──> 已验证 Responses endpoint
                     ▲
                看门狗（常驻）每 15s 探活，死了就拉起
                     ▲
        平台原生服务（launchd / systemd / 计划任务）开机启动看门狗一次 + KeepAlive
```

- **代理**（`proxy/dmx_responses_proxy.py`）：透传 method/path/headers（含 Bearer token）；
  只改 `/responses` 的 JSON body——丢弃 `input[]` 里的顶层 replayed reasoning 项、
  从 `include[]` 移除 `reasoning.encrypted_content`；**不会递归删除**其他带类型的
  `encrypted_content` 块（agent message 的该字段是必填）；对早期本地 Proxy 留下的无 payload 空壳块，
  仅在请求边界剔除该坏块；并剔除历史回放中无法被第三方端点远程获取的
  `input_image`（本地路径、Data URL、无 host 或格式非法的 HTTP(S) URL），保留相邻文本和合法 `http(s)` 图片。**fail-open**：任何解析错误
  → 原样转发。
  另含：SSE 断流透明重连（prelude 缓冲，客户端永不见重复 `response.created`）、上游瞬时故障
  retry、并发闸（默认 64）。
- **看门狗**（`watchdog/watchdog.py`）：一份跨平台常驻循环。TCP 探 8791，不通就用安装时记录的
  Python 绝对路径拉起代理。靠端口占用做单实例保护（防 `Address already in use`），失败退避防 fork 风暴。
- **平台层**：只负责"开机启动看门狗一次 + 看门狗挂了重启它"。三个 OS 语法不同，但职责极简。

**为什么自愈逻辑收敛成一份看门狗**：自愈是最容易出错、最难跨平台测的部分。将其收敛为可测的
标准库 Python，平台层则仅负责启动一个进程，能把跨平台差异压缩在薄适配层。各平台的证据强度见
“平台支持说明”，不得以结构化测试代替物理主机验收。

---

## 诊断

按以下顺序定位：先确认 loopback listener 和受管 endpoint，再按响应类型区分 payload、上游和
客户端状态。不要通过改写会话、SQLite、JSONL 或模型元数据绕过错误。

**报 `encrypted content could not be verified` 时，先查两点：**
```bash
# 1. 代理进程活着吗？
lsof -iTCP:8791 -sTCP:LISTEN            # mac/linux；Windows: netstat -ano | findstr 8791
# 2. 受管 endpoint 是否指向代理？
grep base_url ~/.codex/config.toml      # 应为 http://127.0.0.1:8791/v1
```
两者都对才算修好。只要有一个不对，请求就绕过代理裸奔到上游 → 必报此错。

**macOS `bootstrap failed 5: Input/output error`**：十有八九是 launchd 把该 label 标了
`disabled`。用 `launchctl load -w`（`-w` 清 disabled 位）或 `launchctl enable gui/$UID/<label>` 解。

**`invalid_payload` / `does not match the expected schema`**：先保留响应状态、请求边界净化结果和
上游响应证据，再判断是 payload schema 或上游短暂失败。代理只对已定义的短暂失败执行有限重试；
**不要**删除 `custom_tool_call` 等正常字段来“碰运气”修复，否则会破坏工具调用。

**`Invalid 'input[…].output[…].image_url'`**：历史工具输出中可能保存了 `/tmp/example.png` 一类本地
图片路径，第三方 Responses 端点要求可获取的远程 URL，因而会拒绝整个后续请求。代理会仅剔除这类不可远程回放的
`input_image`（包括 Data URL、无 host/非法端口/含空白的伪 HTTP(S) URL）；其余文字和合法远程图片保持不变；无需改写会话历史。

**`stream disconnected before completion`**：这可能来自上游、网络或客户端。代理只在尚未向客户端
写出实质字节时，以 prelude 缓冲和有限重连吸收可重试的连接中断；一旦已开始输出，不会伪造完成状态。

**客户端未采用新路由**：按 Codex 自身的正常配置重载生命周期操作；本项目不提供或要求强制退出、
杀进程、重开客户端或新建会话。原会话恢复仍须在原会话中得到用户可见的成功回复。

---

## 配置（环境变量，均有默认值）

| 变量 | 默认 | 说明 |
|---|---|---|
| `DMX_UPSTREAM` | `https://www.dmxapi.cn` | 默认上游示例；生产安装应显式指定已验证 endpoint |
| `DMX_PROXY_PORT` | `8791` | 代理监听端口 |
| `DMX_RESPONSES_MAX_CONCURRENCY` | `64` | /responses 并发闸（subagents 扇出需要，别调回 3） |
| `DMX_WATCHDOG_INTERVAL` | `15` | 看门狗探活间隔（秒） |

改端口/上游：`python3 install.py --port 8801 --upstream https://your.host`。端口必须是 `1..65535`；上游仅
接受绝对 HTTP(S) URL，且拒绝空 host、空白、控制符、用户凭据、query/fragment 和会进入服务定义的 shell 元字符。

## 运行时完整性与精确重载

安装目录 `~/.codex/dmx-proxy/` 是可再生成的运行时投影，不是源代码真相。安装器会复制声明的可执行 payload，清理旧版遗留的 `tests/` 运行时目录，并写入仅含版本与 SHA-256 的 `payload-manifest.json`；不包含配置、备份、日志、凭据、请求体或会话内容。

```bash
python3 ~/.codex/dmx-proxy/control.py status
python3 ~/.codex/dmx-proxy/control.py reload
```

`reload` 先校验清单，再仅终止“端口与命令行都证明属于本安装目录”的单个 Proxy；随后必须观察到 watchdog 拉起不同 PID 的替代监听进程。AIGW 仍是 endpoint 与配置投影的唯一权威，Proxy 只负责数据面和进程生命周期。

## 发布与验证

发布版本由根目录 `VERSION` 定义。每次发布须先运行：

```bash
python3 scripts/check_release_metadata.py
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q proxy watchdog platform_adapters install.py uninstall.py control.py tests scripts
  "$py" tests/test_package.py
done
```

GitLab CI 对同一 Python 矩阵执行这些检查；发布 tag 必须为 `v$(cat VERSION)`。

---

## 安全

- **包内零密钥**：代理是 Bearer 透传，API key 始终在 Codex 自己的 keychain/config，代理不存、
  git 里也没有。即使 private 仓库也不会泄露任何人的 key。
- 代理**只绑 `127.0.0.1`**。**不要**改成 `0.0.0.0` 把它暴露到网络。

---

## 平台支持说明

| | macOS | Windows | Linux |
|---|---|---|---|
| Codex 桌面 App | ✅ | ✅ | ❌ 官方无（仅 CLI/IDE） |
| 本代理 + 看门狗 | ✅ | ✅ | ✅（服务 CLI 用户） |
| 自启机制 | launchd | 计划任务 | systemd --user（无则 cron 兜底） |

持续集成在 Python 3.12、3.13 与 3.14 上执行编译和包测试。Linux 安装路径有隔离容器验收；
Windows 服务注册具有生成物与结构化回归覆盖，但仍需要受管 Windows runner 的同候选工件验收。
因此，跨平台兼容是明确的产品目标和测试契约，不应将当前 macOS 上的结果夸大为全部物理平台的证明。

## 治理与文档

- [Agent 入口](AGENTS.md)
- [贡献与验证](CONTRIBUTING.md)
- [文档根](docs/README.md)
- [运行时权威边界](docs/architecture/authority-and-runtime-boundary.md)
- [变更与发布政策](docs/governance/release-and-change-policy.md)
- [ADR-0001](docs/decisions/0001-control-plane-data-plane-boundary.md)
- [发布历史](CHANGELOG.md)
