# codex-dmx-proxy — 跨平台分发包设计

- 日期: 2026-07-08
- 状态: 设计已批准, 待 review → writing-plans
- 发布目标: `http://192.168.64.101:18086/dig/misc/agentic-third-party-api/codex-dmx-proxy` (private)

## 1. 问题与目标

Codex(CLI + 桌面 App)通过 dmxapi 这类第三方 OpenAI Responses 中转商时,每轮重放
`reasoning.encrypted_content`(OpenAI 会话密钥加密的 Fernet blob)。dmxapi 无法重新验证这些
blob → 反复报 `The encrypted content gAAA... could not be verified`。这是中转商的**架构性
固有限制**,在 dmxapi 侧无解,只能在本地出站前剥离这些字段。

维护者(hengyang)已在自己 mac 上完整攻克该问题:一个本地 HTTP stripping 代理 + launchd 守护。
本包的目标是**把该方案打包成"填 key 即用"(实际零 key)的分发件,让内网其他 dmxapi 用户
在 macOS / Linux / Windows 上复用**。

### 非目标
- 不解决 dmxapi 上游本身的瞬时故障(代理已有 retry/重连吸收,随包带上,但不在本设计新增)。
- 不做 PyPI 库 / Homebrew / 二进制打包(见 §6 排除方案)。
- Linux 不提供桌面 App 支持(官方无 Linux 桌面版, 仅 CLI)。

## 2. 关键事实(2026-07 研究确认)

驱动本设计的、经调研核实的跨平台事实:

1. **Codex 桌面 App 只在 macOS + Windows 存在**(Windows 2026-03 起),**Linux 仅 CLI**。
   本 bug 的完整形态(app-server 缓存 config、需 ⌘Q 重启)是桌面 App 特有;CLI 每次重读 config。
2. **config 路径三平台统一**: `~/.codex/config.toml`(Windows = `%USERPROFILE%\.codex\config.toml`)。
   Codex **不用** XDG / AppData;唯一可迁移点是 `CODEX_HOME` 环境变量。
3. **proxy 主体纯 stdlib、零 POSIX-only 调用**(仅 `json/os/sys/time/socket/threading/urllib/http.server`),
   三平台可跑。已设 `daemon_threads=True`、`allow_reuse_address=True`、默认绑 `127.0.0.1`(非 `localhost`,避 IPv6 歧义)。
4. **proxy 是 Bearer 透传**:API key 在 Codex keychain/config,proxy 不存 key。
   → **安装器无需收集 key,包内零密钥,可安全提交进 private git**。
5. **服务上下文 `PATH` 为空**:launchd/systemd/计划任务都不继承 shell PATH。
   必须在安装时解析 python **绝对路径**(`sys.executable`)存入服务定义。Windows 要避开
   WindowsApps 的 0 字节 Store 存根(`python.exe`/`python3.exe` 假可执行)。
6. **非 root 自启三平台均可**:mac=launchd LaunchAgent;Linux=systemd `--user` + `loginctl enable-linger`;
   Windows=计划任务 `<LogonTrigger>` + `<RestartOnFailure>`(标准用户无需管理员)。
7. **跨平台 socket 加固点**:`SO_REUSEADDR` 在 Windows 语义不同、`SO_REUSEPORT` Windows 无、
   urllib 会读系统代理(需 `ProxyHandler({})` 禁用,避免 `127.0.0.1` 被走公司代理)。

## 3. 架构

**路线**:自愈逻辑收敛成一份跨平台 Python 看门狗(常驻循环);仅"如何启动看门狗一次"按平台分叉。
**安装器用 Python 写**(非 shell):三平台 shell 差异巨大(bash/PowerShell/cmd),Python 三平台一致。

```
codex-dmx-proxy/
├── proxy/dmx_responses_proxy.py   # 现有 730 行主体 + 跨平台加固(禁用 urllib 系统代理)
├── watchdog/watchdog.py           # 新:常驻循环,探 8791→死则重启 proxy(三平台一份)
├── install.py                     # 跨平台安装器(探测平台/python/config,幂等)
├── uninstall.py                   # 停服务 + 回滚 config + 可选清日志
├── platform_adapters/
│   ├── macos.py                   # launchd plist(RunAtLoad+KeepAlive+ThrottleInterval)+ load -w
│   ├── windows.py                 # 计划任务 XML(ONLOGON+RestartOnFailure+PT0S, pythonw)
│   └── linux.py                   # systemd --user unit + enable-linger(+cron @reboot 兜底)
├── README.md                      # 原理 + 安装 + 诊断口诀(源自维护者 memory)
├── CHANGELOG.md                   # 版本史(提炼修复轮次)
└── config.example                 # 预置 dmxapi 默认值(base_url/port 等)
```

安装目录(用户机):`~/.codex/dmx-proxy/`(独立于 Codex 自身的 `bin/`,归属清晰、卸载干净)。

### 双层守护
- **平台原生服务**:开机把看门狗拉起一次 + 看门狗挂了 KeepAlive 拉回。职责极简,三平台语法不同但研究已给全。
- **看门狗(常驻循环)**:proxy 死了立刻重启。三平台**完全一致**,可在 mac 上完整验证,逻辑跨平台等价。

## 4. 组件设计

### 4.1 proxy(改动最小)
沿用现有 `dmx-responses-proxy.py` 全部逻辑(剥 encrypted_content、SSE prelude 缓冲重连、
retry 1x+3s backoff、并发 64、fail-open)。**唯一新增**:用
`urllib.request.build_opener(urllib.request.ProxyHandler({}))` 禁用系统代理,避免 localhost 被走公司代理。
全部配置继续走 env(`DMX_UPSTREAM/DMX_PROXY_HOST/PORT/...`),默认值预置 dmxapi。

### 4.2 watchdog.py(新,单一职责)
```
每 15s:
  TCP 探 127.0.0.1:8791 (轻量,不发 HTTP)
  连不上 → Popen 启动 proxy(安装时存的 python 绝对路径, start_new_session/DETACHED_PROCESS)
           记日志(时间戳+原因)
  连得上 → 静默
单实例保护:靠端口占用探测(避免多份 proxy 撞端口 = 今天 Address already in use 的预防)。
重启节流:连续失败则退避拉长间隔,不疯狂 fork。
```

### 4.3 install.py(幂等,全程 fail-loud)
```
1. 探测平台 + python 绝对路径(sys.executable;Windows 优先 py -3,检测 WindowsApps 存根陷阱)
2. 定位 ~/.codex/config.toml(不存在→提示先跑过 Codex)
3. 读现有 base_url:已是代理→跳过;dmxapi 直连→备份后 TOML 感知改写(非 sed 字符串替换)
   识别 [model_providers.*] 段(不硬编码 provider 名)
4. 放 proxy + watchdog 到 ~/.codex/dmx-proxy/
5. 调平台适配器 install():启动 watchdog
6. 验证:探 8791 → /v1/models 是否 200 → 打印结果
桌面 App(mac/win)运行中则警告"请先 ⌘Q,否则 app-server 回滚 config"。
```

### 4.4 平台适配器(统一接口 install()/uninstall()/status())
- **macos.py**:plist(python 绝对路径)+ `launchctl load -w`(`-w` 清 disabled 位=bootstrap I/O error 的解药)。
- **windows.py**:计划任务 XML(`<ExecutionTimeLimit>PT0S` 否则 72h 被杀;`pythonw` 无闪窗)+ `schtasks /create /xml`。
- **linux.py**:systemd `--user` unit(`Restart=always/RestartSec=3/WantedBy=default.target`)+ `enable --now` + `enable-linger`;
  无 systemd user bus 时降级 `cron @reboot + 重启循环`。

## 5. 错误处理原则(源自维护者踩坑史)
- **fail-loud, not silent**:今天的 bug 就是 bootstrap 静默失败没人发现。每步验证并显式报成败,绝不 `|| true` 吞错。
- **幂等**:重复 install 安全(先卸后装/检测已存在)。
- **可回滚**:uninstall 恢复 config 备份、移除服务、可选保留/删日志。
- **proxy fail-open**:解析出错转发原始字节(现有设计,保留)——宁可不剥离也不阻断。

## 6. 分发与发布

**目标**:`dig/misc/agentic-third-party-api`(id=657, private)下新建 project `codex-dmx-proxy`。
维护者 `glab` 已鉴权为 hengyang,ssh 协议已配。

```
发布(glab 全自动):
  1. glab api 创建 project(parent namespace id=657)
  2. git init + 提交(零密钥)
  3. git push 到新 project SSH remote
  4. (可选) glab release create v1.0.0 + 传 zip 附件
同事获取(README 双通道):
  主:git clone git@192.168.64.101:dig/misc/agentic-third-party-api/codex-dmx-proxy.git
     → python3 install.py
  备:GitLab Releases → 下载 zip → 解压 → python3 install.py
```

- 版本化:GitLab Release + CHANGELOG(提炼 memory 修复史)。
- CI:首版手动 `glab release create`;有迭代频率再上 `.gitlab-ci.yml`(如非必要勿增实体)。
- 安全:即使 private 也坚持包内零密钥(Bearer 透传);README 警示"代理只绑 127.0.0.1,勿改 0.0.0.0"。

### 排除的方案(YAGNI)
- ❌ PyPI `pip install`:这是系统集成工具(带守护+改 config),非库,语义不符。
- ❌ Homebrew / mac 专属安装器:与三平台目标冲突。
- ❌ 单文件二进制打包:纯 stdlib 不需要,反牺牲可读/可审计性。

## 7. 测试策略
- **watchdog**:mac 上完整验证(杀 proxy→看门狗拉起;杀看门狗→平台服务拉起;单实例;节流)。逻辑跨平台等价。
- **install/uninstall**:mac 上端到端(装→验证 200→卸→回滚 config);Linux/Windows 适配器靠研究核实的语法 + 结构化单测(生成的 plist/XML/unit 内容断言),无法在 mac 实测的部分在 README 标注"社区验证求反馈"。
- **proxy 跨平台加固**:socket 绑定 / 禁代理 的单测。
- 诚实边界:维护者只有 mac,Linux/Windows 的服务注册无法本地实测——设计上已把最高危的自愈逻辑收敛到可测的看门狗,平台层退化为研究已验证的薄适配。
