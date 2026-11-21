# 「r5 修订」指令（给每个修书 subagent）

先读 `framework/rewrite-brief.md`，它的体例、禁止读的范围全部适用。本次是按修订清单定点修订，不是从零写。

## 可读
- 本领域的 `fix-list-r5.md`（修订清单，只写现象和方向，不含来源内容）
- 本领域收紧后的骨架（r5）、avoid-list、evidence-notes
- 本领域现行的书
- `reference/WCAG-2.3.1-闪烁阈值.md`（闪烁一律以此为准，含换算口径）
- `framework/CHANGELOG.md` 最新一节（用户 2026-11-19 的裁决）

**严格禁止读**：`01-learn\`、任何 `signatures.md`、任何 `check-report*.md`、`framework/drift-check-r4.md`、任何 `archive\skeleton-before-*.md`、`00-sources\`、任何 skills 或原料目录。

## 步骤
1. 先用 Python 按 UTF-8 把现行的书复制到同目录 `archive\`，文件名加 `-before-r5`。
2. 按清单的优先级逐节处理：S 安全 → E 计算 → R 退回或快到线 → D 多样性 → U 只换了说法 → M 小修。
   - **R、U**：从收紧后的骨架和观众一侧重新推导，真正重新决定结构、分类、参数，不要只换说法或只加减一个参数。
   - **E**：需要计算的用 Python 实际复算，结果写进正文或附录。
   - **D**：被删的取向要恢复，或写明删除理由和证据；每章至少三种取向。
3. 同步速查表、交叉引用（用脚本核对）、书末「禁用值自查」附录；书首版本说明改为 r5（2026-11-19）。
4. 书末附一节「r5 修订记录」：清单每条一行，写"已改 / 部分 / 未改（理由）"。

分段写，每次 Edit 一章，每段不超过约 3000 字。UTF-8，禁止 PowerShell Get-Content/Set-Content。回复一句话：各节处理条数、未改的条目及理由。
