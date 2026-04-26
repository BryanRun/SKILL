# 本地模块评审（Local Module Review）

本文件定义 **enhanced_code_review** 相对原生 gerrit-review 的增量能力：**不依赖 Gerrit Change Number**，在本地 Git 仓库内对指定目录做与 `--prepare` 类似的结构化上下文输出，供 LLM 按 `08-llm-review-prompt.md` 产出评审结论。

## 触发语义（与 SKILL 一致）

- 用户说 **`review <模块路径>`**（例如 `review frameworks/cm/videoplayer`）→ Agent 应优先识别为**本地模块评审**（当前仓库为真源时）。
- 用户说 **`enhanced_code_review review <模块路径>`** → 显式指定本技能。
- 若 `<模块路径>` 无法解析为目录，再回退到 gerrit 语义（`review CR <数字>` / `review <姓名>`）。

## 工作流

1. `cd` 到仓库根（或 `git rev-parse --show-toplevel`）。
2. 运行：
   ```bash
   python3 scripts/local_module_prepare.py <模块相对路径> [--base origin/main] -o /tmp/local_ctx.json
   ```
3. Agent 读取 `local_ctx.json`，合并 **references/01～08** 的六维 checklist，输出与 Gerrit 评审同构的 **review JSON**（或等价结构正文）。
4. **不执行** `gerrit_post.py`（无 CR 可贴）；结论留在仓库内 Markdown / 会话 / 如需可再手动建 CR。

## 与 Gerrit 流程的对齐

| 环节 | Gerrit | 本地模块 |
|------|--------|----------|
| 上下文 | `gerrit_review.py --prepare` | `local_module_prepare.py` |
| 机械规则 | `gerrit_audit.py` | `local_audit.py`（规则集同源） |
| 一致性扫描 | `consistency_scan.py`（需 CR/Revision） | 可选：仅对 Java/Kotlin 未来扩展；当前以 diff + LLM 为主 |
| 贴回 | `gerrit_post.py` | 不适用 |

## 质量门禁

- 六维必扫、三问 filter、YAGNI、项目明文规范（与 `SKILL.md` 完全一致）**不得因本地模式而删减**。
