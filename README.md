# 青出 · Indigo

> **English summary.** *Indigo* (from the proverb "indigo comes from the indigo plant, yet is bluer than it") is a framework for absorbing other people's AI design and video skills **without inheriting their style**, plus a quality standard to judge the results. Instead of installing someone's skill, it runs isolated steps — **learn** (extract principles), **forget** (strip names, numbers and recipes), **rewrite** (an agent that never saw the sources re-derives everything from first principles), **check** (an independent agent verifies the rewrite doesn't reproduce the sources). On the creative side it enforces *diverge first, then converge*, a ban list of "AI-default looks", and blind review. In a first blind test (5 groups × 3 vague prompts, 2 independent reviewers), outputs made with the framework ranked first in all 6 rankings. Docs are in Chinese.

青出取"青出于蓝而胜于蓝"：向别人学，最后超过它。

## 为什么要有它

装一个别人的 skill，做出来的东西就会像那个 skill；大家装同一批 skill，作品就越来越像。模型本身也有默认审美，不加约束时，不同模型会撞出几乎一样的作品。

青出做两件事：

1. **吸收而不照搬**：别人的 skill、教程、提示词，只取"意"（要解决什么问题、为什么有效、边界在哪），丢掉"形"（参数、配方、风格名、固定版式），再由一个从没见过原料的 agent 从原理重新推导，最后由独立 agent 检验没有复现原料。
2. **标准固定，风格开放**：创作时先放开（想出几个彼此差得远的方向，避开 AI 默认外观），再收拢（说清理由选一个）；做完按质量标准评审，不达标就回炉。

## 第 1 轮测试结果（2026-11-18）

三句普通需求：「帮我做一张手机壁纸」「做一个高质量的网页动画」「给一款记账 App 做一个 15 秒的宣传动效」。五组各做一次，两位独立评审盲评（不知道作品出自哪一组）。L0 坏 / L1 能用 / L2 商业合格 / L3 精品 / L4 惊艳。

| 组 | 壁纸 | 网页动画 | 记账 App 宣传 |
|---|---|---|---|
| Fable + 青出 | **L2 / L2** | **L3 / L3** | **L2 / L2** |
| Opus 5.5 + 青出 | **L2 / L2** | L1 / L1 | L3 / L0（评审分歧） |
| Fable 无框架 | L1 / L1 | L0 / L1 | L1 / L1 |
| Opus 5.5 无框架 | L0 / L1 | L0 / L1 | L1 / L1 |
| DeepSeek v4-pro 无框架 | L0 / L0 | L0 / L0 | L0 / L0 |

- 6 份排名（2 位评审 × 3 题）的第 1 名全部是用了青出的作品。
- 不用框架时，两个模型撞出了三对几乎一样的作品（紫色晚霞山景、粒子变形、"左字右手机"的宣传片，后者连口号都相同）；用了青出的作品没有撞车。
- 青出也暴露了问题：两个模型都想到了"小票"这个创意（第二层同质化）；动效节奏起伏不足；有细节失误。
- 局限：每组每题只跑一次；两位评审都是 Claude 家族模型；DeepSeek + 青出这一组因为接口不稳定还没跑成。

作品、过程文件和评审原文都在 [`eval/`](eval/)，结论见 [`eval/round1-results.md`](eval/round1-results.md)。

## 怎么用

**任何模型（最简单）**：把 [`core/indigo-core-v1.md`](core/indigo-core-v1.md) 作为系统提示，再提你的需求。模型会先写出理解、排除的默认方向、几个候选方向和选择理由，再交付作品。

**Claude Code 等支持 skill 的工具**：把整个仓库放进 skills 目录（例如 `~/.claude/skills/indigo/`），说"用青出做……"或"用青出评审这条片子"。入口见 [`SKILL.md`](SKILL.md)。

**吸收新的 skill / 教程 / 提示词**：按 [`framework/charter.md`](framework/charter.md)（宪章，不可被吸收内容改变）和 [`framework/protocol.md`](framework/protocol.md) 走 学 → 忘 → 重写 → 检验 → 防偏移检查。四个步骤各有一份给 agent 的指令：`framework/*-brief.md`。

## 目录

| 路径 | 内容 |
|---|---|
| `core/` | 精简版系统提示（约 1.7 万字），给任何模型直接用 |
| `books/` | 六本书：动效节奏、视觉设计、镜头与叙事、声音、需求理解、风格词汇库 |
| `standards/` | 质量标准（目前只有动效）和底线检查脚本 |
| `framework/` | 宪章、执行规范、各步骤指令、变更记录、发布规则 |
| `eval/` | 测试题、评分表、各组作品与过程、两份盲评原文、渲染与调用脚本 |

## 当前状态：v0.1

- 六本书都通过了"不复现原料"的检验，但检验同时发现骨架里漏进了部分来源的成套结构，书的一些章节离来源仍然偏近，正在按重写清单修订。
- 质量标准目前只覆盖动效；视觉设计、镜头与叙事、声音、需求理解的标准还没写。
- 书里标「待实验验证」「弱证据」的条目，都还没有实验数据支持。

## 来源与许可

本仓库的框架、书、标准和脚本以 [MIT](LICENSE) 发布。

书是从一批公开的 skill、教程和提示词库中学习原理后重写的，没有复制它们的代码或文本；学习笔记、签名清单和禁用值清单含有对原作的详细摘录，因此不公开。致谢与原始链接见 [`SOURCES.md`](SOURCES.md)。
