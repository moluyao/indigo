# 第 1 轮框架效果测试（2026-11-17 起）

## 各组

| 组 | 模型 | 框架 | 状态 |
|---|---|---|---|
| A | Opus 5.5（子 agent） | 无 | 已有（runs/claude-raw，2026-10-31） |
| B | Opus 5.5（子 agent） | 青出 core v1 | 待跑 |
| C | DeepSeek v4-pro | 无 | 已有（runs/deepseek-raw，2026-10-31） |
| D | DeepSeek v4-pro | 青出 core v1 | 待跑 |
| E | Fable（官方子 agent） | 无 | 待跑 |
| F | Fable（官方子 agent） | 青出 core v1 | 待跑 |

"用框架"的定义：模型收到同一份 `indigo-core-v1.md`，在一次生成里自己走完 理解 → 发散 → 收拢 → 简报 → 制作 → 自检。本轮不加外部评审回炉，保证和无框架组一样是一次生成。

## 防泄题

- core v1 不得包含任何壁纸、网页动画、记账 App 的示例。需求理解书里拿这三道题做的演示一律不用。
- 用框架的子 agent 只能读 `tasks.md` 和 `indigo-core-v1.md`，不读 craft-lib 其他文件。

## 评审

- 作品复制到 `eval/blind/`，用随机编号；编号对照表 `eval/blind-key.json`，评审不读。
- 两位评审（Opus、Fable）各自独立打分，只读 `rubric-v1.md`、渲染图和联系表、render.json。评审看不到 core v1。
- 每题：每件作品逐维度定级（L0–L4），再整体排序和两两比较；写出证据。

## 要回答的问题

1. B vs A、F vs E、D vs C：框架对每个模型有没有用。
2. D vs A、D vs E：DeepSeek 加框架能不能追上更强的模型裸做。
3. F vs E：对最强的模型，框架还有没有用。
