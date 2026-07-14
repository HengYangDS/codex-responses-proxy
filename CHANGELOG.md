# Changelog

本项目遵循语义化版本。版本史提炼自维护者在生产环境的实际修复轮次。

## [Unreleased]

### 修复
- **历史本地图片回放不再阻断整个会话**：Codex 会把本地工具图片结果（例如
  `/tmp/example.png`）保留在后续 Responses 请求的历史中；第三方端点只接受远程 URL，遂报
  `Invalid 'input[…].image_url'`。代理现只剔除这些不可远程回放的 `input_image`（本地路径与
  Data URL），同时保留相邻文本与合法 `http(s)` 图片，不改写本地会话历史。

### 验证
- 新增代理净化回归用例，覆盖本地路径和 Data URL 的移除、文字保留及 `https` 图片保留。

## [1.0.1] - 2026-07-08

Linux 从"调研+单测"升级为 **Docker 真机端到端验证**,并修复真机测试暴露的一个健壮性问题。

### 修复
- **Linux minimal 环境不再 fail-hard**:无 systemd user bus 且无 crontab 时(minimal 容器 /
  锁定主机),旧版会在文件已放置后直接 ERROR 退出整个安装。现降级为 `ManualStartRequired` 警告:
  文件照装、看门狗本会话启动、并提示手动 boot-persistence 钩子。

### 验证
- Docker 真机(debian/python 3.14)端到端全过:install 优雅降级 → config 改写+备份 →
  代理真转发上游(HTTP 401 证明穿透)→ **看门狗 Linux 自愈实测**(杀代理→自动重启)→ uninstall 回滚。
- 新增降级路径单测,共 17 单测。
- Windows 仍为"调研+单测",待首个真实用户验证。

## [1.0.0] - 2026-07-08

首个可分发版本。把维护者在自己 macOS 上攻克的 dmxapi encrypted-reasoning 方案，打包成跨平台
（macOS / Linux / Windows）的一键安装件。

### 核心能力
- **剥离 encrypted_content**：代理在出站 `/responses` 请求里丢弃重放的 reasoning 项 + 递归删
  encrypted_content + 从 include[] 移除 reasoning.encrypted_content，修复
  `encrypted content could not be verified`。fail-open。
- **上游瞬时故障吸收**：`invalid_payload` / 429 / 5xx 透明重试（invalid_payload 重试 1 次 +
  3s backoff——实测这是 dmxapi 服务端 ~18% 瞬时故障，非请求内容问题，原样重放会成功）。
- **SSE 断流透明重连**：prelude 缓冲策略，客户端永不见重复 `response.created`；修复
  `stream disconnected before completion`。
- **并发闸默认 64**（早期为 3，subagents 扇出时满载丢连，已上调）。

### 打包 / 分发新增
- **跨平台看门狗**（常驻循环）：自愈逻辑收敛成一份可测代码；探 8791 死则重启，单实例保护 + 退避节流。
- **三平台服务适配器**：launchd（`load -w` 清 disabled 位）/ systemd --user（+ enable-linger，
  无 systemd 时 cron @reboot 兜底）/ Windows 计划任务（ONLOGON + RestartOnFailure + PT0S，pythonw，无需管理员）。
- **幂等安装器**：探测平台 + Python 绝对路径（避开 Windows Store 存根陷阱）；TOML 行感知改写
  base_url（非 sed 字符串替换，容错引号/空格）；改前警告 Codex 桌面 App 运行中会回滚 config；装后验证 200。
- **跨平台加固**：urllib 强制禁用系统代理（`ProxyHandler({})`），避免 localhost 被走公司代理。
- **零密钥**：Bearer 透传，包内不含任何 API key。

### 已知限制
- 维护者仅有 macOS 环境；Linux/Windows 服务注册按调研核实的语法编写并有结构化单测，但未真机端到端实测。
- Codex 桌面 App 官方只有 macOS/Windows；Linux 仅 CLI，本包在 Linux 上服务 CLI 用户。
