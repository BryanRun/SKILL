# CHANGELOG

## enhanced_code_review v2.0.0 — 2026-04-20

- **技能名称**：`enhanced_code_review`（与 `gerrit-review` 同源 references + scripts，质量门禁不变）。
- **新增**：本地模块评审 — `scripts/local_module_prepare.py`、`scripts/local_audit.py`、`references/09-local-module-review.md`。
- **分发**：`enhanced-code-review-v2.0.0.zip`；原版单独包 `gerrit-review-v2.0.0.zip`。

## gerrit-review / 融合版 v2.0.0 — 2026-04-19

**里程碑版本：完整融合 code-review-expert + superpowers + Google Style**

### 重大改动

- **完整 6 大评审维度**（每次必全扫，不再砍维度）：
  1. SOLID 原则
  2. 安全性（OWASP + CWE + Android CDD + ISO 21434）
  3. 性能（Effective Java Item 67 + Android Performance）
  4. 错误处理 + 边界（Effective Java 70-77 + Clean Code Ch.7）
  5. 代码质量 + 风格
  6. 车载中间件专项（L1~L10）

- **项目硬规范**：
  - Java 缩进必须 **4 空格**，禁用 tab（P1）
  - C++ 缩进必须 **4 空格**，禁用 tab（P1）
  - C++ 风格不强制 Google Style，必须遵循项目原有风格（P1）
  - commit message 必带 Jira 号（P0 → -1）

- **YAGNI 定位**：作为 P3 建议，不强制，不阻断合入

- **评审方法论**：
  - 对抗式评审（verify-before-comment）
  - 三问 filter（每条必过）
  - 每条评论必有权威依据（不是 AI 常识）
  - 评论 5 要素（问题+依据+原理+建议+Before/After）

- **新增 preflight 保护**：不覆盖人工分数（self 已 +2 时不贴回）

### 新增文件

- `references/01-solid-principles.md`
- `references/02-security.md`
- `references/03-performance.md`
- `references/04-error-handling-boundaries.md`
- `references/05-code-quality-style.md`
- `references/06-automotive-middleware.md`
- `references/07-review-methodology.md`
- `references/08-llm-review-prompt.md`
- `VERSION` / `CHANGELOG.md`

### 已删除

- `references/solid-architecture.md` → 合并到 01
- `references/security-reliability.md` → 合并到 02
- `references/code-quality.md` → 拆分到 03/04/05
- `references/adversarial-review.md` → 合并到 07
- `references/llm-review-prompt.md` → 合并到 08
- `references/automotive-middleware-checklist.md` → 重写为 06
- `references/false-positives.md` → 合并到 07 反例表

---

## v1.0.0 — 2026-04-19（早期版本）

- 初始版本，包含 7 脚本 + 6 references
- code-review-expert + superpowers 初步融合
- CR 993636 首次实战（-1，发现 DisplayController NPE）
- CR 995945 实战（+1，preflight 保护未覆盖志强 +2）
