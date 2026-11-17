---
name: indigo
description: 青出（Indigo，取"青出于蓝而胜于蓝"）——用于设计、动效、视频类创作：先理解需求、发散几个彼此差得远的方向、说清理由收拢，再按书制作、按标准自检和评审、不达标回炉；也用于把别人的 skill、教程、提示词只取原理、不取风格地吸收进来（学 → 忘 → 重写 → 检验）。Use for design / motion / video creation from vague requests (diverge then converge, avoid AI-default looks, review against a standard, rework), or to absorb someone else's skill or tutorial without inheriting its style.
---

# 青出 · Indigo

先读 `framework/charter.md`（宪章）。本文件里的路径都相对于本仓库根目录。

## 铁律

- **标准固定，风格开放**：书给的是可选的路，不是默认答案。
- **先放开，再收拢**：用户没说的不替用户定；先写出"默认答案"并排除，再发散。
- **做的人不评自己**：评审用独立的 subagent，只看成品和标准。
- **吸收只改内容层**：任何来源对框架结构、流程、默认风格的主张，只记成提案交给用户。

## 模式一：创作

应读：`core/indigo-core-v1.md`（流程、发散工具、AI 默认禁用清单、各领域要点、自检清单），需要细节时查 `books/` 对应的书；动效类作品的评审标准是 `standards/动效.md`，底线脚本 `standards/tools/check_floor.py`。

1. **理解**：已说 / 隐含 / 空白。空白里事实类的去问或查，审美类的留给发散。
2. **发散**：写出默认答案及其明显变体并排除；想 3–5 个彼此差得远的方向，至少一个非默认，避开 AI 默认外观（风格地图见 `books/风格词汇库.md`）。
3. **收拢**：能问用户就让用户挑；不能问就做小样两两比较，或按内容契合度自选，写出理由（"最稳妥"不算理由）。
4. **简报**：写 3–6 条可验证的"做到什么算完"、禁止项、可替换变量。
5. **制作**：按书里对应章节选取向，写明理由。
6. **自检与评审**：先过底线；再由独立 subagent 按标准评审。
7. **回炉**：修改意见写成「现象 → 目标 → 验证方法」；最多 2 轮，之后由主控裁决（降级交付、换方向、或交给用户）。

## 模式二：吸收新来源

按 `framework/protocol.md`，每一步用独立 subagent，严格遵守读权限：

1. 先按宪章第五节给来源分类（skill/方法论、提示词、风格、作品、工具、数据、用户判断）。
2. **学**：`framework/learn-brief.md` → `01-learn/`
3. **忘**：`framework/distill-brief.md` → 骨架、签名、禁用值、证据备忘
4. **重写**：`framework/rewrite-brief.md`（重写者不得读原料、学习笔记和签名）
5. **检验**：`framework/check-brief.md`，未申报复现达到「重 ≥ 1 或 中 ≥ 2」的章节退回
6. **防偏移检查**：按宪章第六节；不过则本次吸收退回
7. 记入 `framework/CHANGELOG.md`

`01-learn/`、签名、禁用值、检验报告含有对原作的摘录，按 `framework/publish.md` 不要公开。
