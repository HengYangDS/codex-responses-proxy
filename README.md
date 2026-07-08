# codex-dmx-proxy

一个本地 HTTP 代理，修复通过 **dmxapi** 使用 **Codex** 时反复出现的报错：

> The encrypted content `gAAA...` could not be verified.
> Reason: Encrypted content could not be decrypted or parsed.

以及相关的 `invalid_payload` / `stream disconnected before completion`。

跨平台（macOS / Linux / Windows），纯 Python 标准库，**零第三方依赖**，**包内零密钥**。

---

## 这是什么问题

Codex 用 OpenAI 的 *Responses* wire API。每一轮，模型返回一个 `reasoning` 项，里面带一个
`encrypted_content`（`gAAAAAB...` 开头的 Fernet 加密块）。Codex 把它存下来，并在**之后每一轮
重放**。dmxapi 作为第三方中转，用自己的密钥加密这些块；密钥轮换 / 后端路由后，它无法再验证一个
被递回来的旧块 → 报 `encrypted content could not be verified`。

Codex 是闭源二进制，**没有配置项能关掉这个重放**。所以我们在 Codex 和 dmxapi 之间放一个本地小代理，
在每个出站请求里**剥掉**这些重放的加密块。模型照常每轮推理，只是不再被递回一个它（代理）验证不了的
旧加密块。这正是 Codex 维护者推荐的修法（发送前 strip encrypted_content），只不过做在网络边缘。

**这是第三方中转商（dmxapi）的架构性固有限制**，在 dmxapi 侧无解——只能本地剥离。

---

## 安装

前提：装了 Python 3.8+，且至少跑过一次 Codex（这样 `~/.codex/config.toml` 已存在）。

```bash
# 主通道
git clone git@192.168.64.101:dig/misc/agentic-third-party-api/codex-dmx-proxy.git
cd codex-dmx-proxy
python3 install.py

# 备通道（无 git）：从 GitLab Releases 下载 zip → 解压 → cd 进去 → python3 install.py
```

Windows 上用 `py -3 install.py`。

安装器会：探测平台 + Python 绝对路径 → 定位 `~/.codex/config.toml` → 复制代理+看门狗到
`~/.codex/dmx-proxy/` → 把 provider 的 `base_url` 改指向本地代理（先备份）→ 注册开机自启的看门狗
→ 验证 `/v1/models` 返回 2xx/4xx。

**装完必做**：完全退出并重开 Codex 桌面 App（`⌘Q` / 关闭），然后**开一个新线程**。
原因：① Codex 桌面版的 app-server 启动时缓存 config，不重开不生效；② 旧线程持久化的历史里可能
仍带旧的加密块，开新线程避开重放。

### 卸载

```bash
python3 uninstall.py            # 停服务 + 回滚 config 备份
python3 uninstall.py --purge    # 另外删掉 ~/.codex/dmx-proxy/
```

---

## 工作原理（架构）

```
Codex ──HTTP──> 本地代理 :8791 ──剥离 encrypted_content──> dmxapi
                     ▲
                看门狗（常驻）每 15s 探活，死了就拉起
                     ▲
        平台原生服务（launchd / systemd / 计划任务）开机启动看门狗一次 + KeepAlive
```

- **代理**（`proxy/dmx_responses_proxy.py`）：透传 method/path/headers（含 Bearer token）；
  只改 `/responses` 的 JSON body——丢弃 `input[]` 里的 reasoning 项、递归删所有 `encrypted_content`、
  从 `include[]` 移除 `reasoning.encrypted_content`。**fail-open**：任何解析错误 → 原样转发。
  另含：SSE 断流透明重连（prelude 缓冲，客户端永不见重复 `response.created`）、上游瞬时故障
  retry、并发闸（默认 64）。
- **看门狗**（`watchdog/watchdog.py`）：一份跨平台常驻循环。TCP 探 8791，不通就用安装时记录的
  Python 绝对路径拉起代理。靠端口占用做单实例保护（防 `Address already in use`），失败退避防 fork 风暴。
- **平台层**：只负责"开机启动看门狗一次 + 看门狗挂了重启它"。三个 OS 语法不同，但职责极简。

**为什么自愈逻辑收敛成一份看门狗**：自愈是最容易出错、最难跨平台测的部分。收敛成一份可测的
Python（在 mac 上完整验证过），平台层退化成研究已验证的薄适配，把"无法在 Linux/Windows 实测"
这个风险从高危的自愈逻辑，转移到低危的"如何启动一个进程"。

---

## 诊断口诀（排查时先看这里）

这套经验来自维护者在自己机器上的大量踩坑，直接可复用：

**报 `encrypted content could not be verified` 时，先查两点：**
```bash
# 1. 代理进程活着吗？
lsof -iTCP:8791 -sTCP:LISTEN            # mac/linux；Windows: netstat -ano | findstr 8791
# 2. config 真的指向代理吗？
grep base_url ~/.codex/config.toml      # 应是 http://127.0.0.1:8791/v1，不是 dmxapi 直连
```
两者都对才算修好。只要有一个不对，请求就绕过代理裸奔到上游 → 必报此错。

**macOS `bootstrap failed 5: Input/output error`**：十有八九是 launchd 把该 label 标了
`disabled`。用 `launchctl load -w`（`-w` 清 disabled 位）或 `launchctl enable gui/$UID/<label>` 解。

**`invalid_payload` / `does not match the expected schema`**（经代理仍偶发）：这是 dmxapi
**服务端瞬时故障**，不是请求内容问题——实测把被拒的请求原样重放会成功。代理已内置"retry 1 次 +
3s backoff"吸收它。**不要**去 strip 请求里的 `custom_tool_call` 等字段（那会破坏正常工具调用）。
判据：reject dump 若全是同一 session 且 item 数递增，那是**重试放大的果，不是因**。

**`stream disconnected before completion`**：dmxapi 在 turn 起步掐断 SSE 流（观测 ~82% 断在
前 4 个事件、零实质内容）。代理已用 prelude 缓冲 + 透明重连处理：只要还没向客户端写出实质字节，
就重新发起同一请求，客户端只见一条干净的 200 流。

**App 突然"打不开" + 内存暴涨**：可能是 GUI 进程活着但 `windows=0` + RSS 膨胀。
`⌘Q` + `pkill -f '/Applications/Codex.app/Contents/MacOS/Codex'` + 重开。

---

## 配置（环境变量，均有默认值）

| 变量 | 默认 | 说明 |
|---|---|---|
| `DMX_UPSTREAM` | `https://www.dmxapi.cn` | 上游中转地址 |
| `DMX_PROXY_PORT` | `8791` | 代理监听端口 |
| `DMX_RESPONSES_MAX_CONCURRENCY` | `64` | /responses 并发闸（subagents 扇出需要，别调回 3） |
| `DMX_WATCHDOG_INTERVAL` | `15` | 看门狗探活间隔（秒） |

改端口/上游：`python3 install.py --port 8801 --upstream https://your.host`。

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

维护者只有 macOS 环境。**Linux 已用 Docker 真机(debian/python 3.14)端到端验证**(install→
看门狗自愈→uninstall 全过)。**Windows 的服务注册按调研核实的语法编写、结构化单测覆盖，但未真机
端到端实测**——若你在 Windows 上跑，欢迎反馈 issue。代理与看门狗主体是纯 stdlib，三平台行为一致。
