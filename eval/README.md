# eval 对照实验工具

题目与统一技术要求见 `tasks.md`。两个脚本都在本目录运行（路径也可写绝对路径）。

## ds_run.py — 调 DeepSeek 跑一道题

```
python ds_run.py --task T1|T2|T3 --out runs/<组名> [--system <系统提示文件>] [--model deepseek-v4-pro|deepseek-flash]
                 [--max-tokens 32000] [--timeout 1200]
```

- key 从 `eval/.secrets/deepseek.env（自己建，不要提交）` 的 `DEEPSEEK_API_KEY` 读取；所有输出和报错都会把 key 替换为 `***`。
- 用户消息 = tasks.md 中该题的需求原话 + 「统一技术要求」全文。`--system` 不给时不带系统提示。
- 失败最多重试 1 次（4xx 鉴权/余额类错误不重试）。
- 输出到 `--out`：
  - `T?.md` 原始回复；`T?.reasoning.md` 思考内容（接口返回时）
  - `T?.html` 回复中最后一个完整 html 代码块
  - `T?.meta.json` 模型、用时、token 用量、finish_reason、调用前后余额及差值估算费用（`cost_cny_by_balance_delta`，余额更新可能有延迟，仅供参考）

## render.py — 无头浏览器渲染

```
python render.py runs/<组名> [--only T1 T2 T3]
```

- 自动在目录里找 `T1.html` / `T2.html` / `T3.html`（或以 T1_/T1- 开头的 html），缺的跳过。
- 依赖：Python Playwright + Chromium、ffmpeg（PATH 中）。当前 Python 不能启动 Playwright 时，自动在 `eval/.venv` 安装并改用它运行。
- T1：1080×2340 视口截图 → `T1.png`。
- T2/T3：1920×1080，逐帧调用 `window.__seek(ms)`（30fps，T2 10s / T3 15s），帧存临时目录后用 ffmpeg 合成 `T?.mp4`，并出联系表 `T?.sheet.jpg`（每秒 1 帧，5 列）。
- 页面没有 `__seek` 或逐帧渲染报错时，退回按真实时间录制 10/15 秒（`mode: realtime_fallback`）。
- `render.json` 记录每题：渲染模式、是否有 `__seek`、`seek_repeatable`（同一时刻 seek 两次画面是否一致）、`seek_frozen_after_600ms`（seek 后画面是否保持静止）、seek 报错、页面 JS 错误、console 错误、外部网络请求、文档实际尺寸、耗时。这些都是评审信息。
