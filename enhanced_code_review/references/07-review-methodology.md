# 07 · 评审方法论(对抗式 + YAGNI + verify-before-comment)

## 来源

- [obra/superpowers · requesting-code-review](https://github.com/obra/superpowers)
- [obra/superpowers · receiving-code-review](https://github.com/obra/superpowers)
- Bob Martin: *Clean Code* Chapter 1 (YAGNI)
- Martin Fowler: [YAGNI](https://martinfowler.com/bliki/Yagni.html)
- Google Engineering Practices: [Code Review Developer Guide](https://google.github.io/eng-practices/review/)

---

## 核心理念

> Reviewer 和 Developer 都服务于业务。评审的目的是**降低线上风险 + 帮开发避免返工**,不是挑错、展示知识或追求"完美"。

---

## 评审工作流(7 步)

### Step 1 · Preflight

- `gerrit_show.py <CR>` 拉 detail / commit / diff / 同组 CR
- `gerrit_audit.py` 机械扫描(Jira / 空 catch / System.out / TODO 无主)
- `consistency_scan.py` 同文件内一致性扫描
- 识别 entry points / ownership / critical paths(电源 / 诊断 / OTA)

### Step 2 · SOLID + 架构

按 `01-solid-principles.md` 扫:SRP / OCP / LSP / ISP / DIP。
每条违反项 → 必须说**具体 bug/risk/混淆**,空话不发。

### Step 3 · 安全

按 `02-security.md` 扫:权限 / 注入 / 并发 / 资源 / IPC / 密码学。
**车载最高发**:线程安全(volatile / synchronized / TOCTOU)+ Binder 线程阻塞。

### Step 4 · 性能

按 `03-performance.md` 扫:时间复杂度 / 主线程阻塞 / 内存 / 缓存 / IO。
**车载重点**:续航(WakeLock / Alarm / 定时器不配对)。

### Step 5 · 错误处理 + 边界

按 `04-error-handling-boundaries.md` 扫:空 catch / 过宽 catch / RemoteException / null / 溢出 / off-by-one。

### Step 6 · 代码质量 + 风格

按 `05-code-quality-style.md` 扫:Google Style(缩进/命名/imports/braces)+ 命名 + 可读性 + dead code。
**Java 统一 Google Java Style / C++ 统一 Google C++ Style**。

### Step 7 · 车载专项

按 `06-automotive-middleware.md` 扫:L1~L10 车载场景(状态机 / QNX / 电源 / OTA / 诊断)。

### Step 8 · 隐私合规（P0，高精确率）

按 `10-privacy-compliance.md` 扫:个人信息 / 敏感数据 × 传输/存储/日志/权限/跨端/撤回。
依据:《产品功能 信息安全要求-v1.2-20260210》隐私合规条目 + 《附录-个人信息定义》。

> **本步骤的特殊触发约束**（由团队于 2026-04-21 明确):
> - 隐私合规问题按 **P0** 级别计分。
> - **触发条件必须"确认无误"**,不能随意触发。
> - 必须同时命中"数据信号(门控 A)+ 去向信号(门控 B)+ 语义确认(门控 C)",三者齐备 才允许作为 P0 评论贴回。
> - 只命中一端 → 降级为疑似(仅 cover 口述)或 drop。
> - 详细触发规则见 `10-privacy-compliance.md` §4 P0 触发规则表。

---

## 三问 Filter(每条评论必过,任一 NO → drop)

每条评论输出前,依次自问:

### 问 1:**不提会真的出问题吗?**

- 会 → 继续下一问
- 不会 / 只是"不优雅" → **drop**

### 问 2:**本条是否有权威依据支撑?**

必须引用至少一项:
- Google Java/C++ Style Guide(§ 章节号)
- Effective Java(Item 编号)
- Clean Code(Chapter 编号)
- OWASP / CWE / ISO / AUTOSAR
- 团队/项目明文规范
- 真实观察(同文件内已一致、本条违反)

**无权威依据 + 只是 AI 常识** → **drop**

### 问 3:**项目里其他代码是否也这么写?**

如果**大家都这么写** → 这是项目风格 → **drop** 或降级到 P3 建议(不强制)。
例外:项目规范明文禁止时,即使现状不符也要提(告知需要修正)。

---

## YAGNI 过滤（仅针对“抽象建议”类评论）

> **项目级规则**：YAGNI 作为 **P3 建议**，不强制。
> 提了也不阻断合入，作为向后演进的治理建议。

来自 Martin Fowler *YAGNI* 和 Clean Code。

评审前 grep **实际使用**：

| 建议类型 | YAGNI 自检 | 级别 |
|---|---|---|
| "应该加 interface" | 当前几个实现？1 个 → P3 建议 | P3 |
| "应该加 Factory" | 当前构造方式是否复杂？简单 → P3 | P3 |
| "应该加 Strategy" | 当前几个策略？1 个 → P3 | P3 |
| "应该加 Builder" | 构造参数 ≤ 5 → P3 | P3 |
| "应该加 DI 容器" | 项目里用 DI 吗？不用 → P3 | P3 |
| "应该拆成多个类" | 当前类有多个 caller 混淆吗？没有 → P3 | P3 |

**核心**：grep 项目内**真实 caller 数量**。≥ 2 才建议抽象，且最高仅 P3。

---

## 不说空话原则

来自 Google Engineering Practices 和 Clean Code Chapter 1。

| ❌ 空话 | ✅ Specific |
|---|---|
| "改进错误处理" | "L213 `catch(RemoteException)` 吞了异常,建议 `Log.w(TAG, \"broadcast item \" + i + \" failed\", e);`" |
| "考虑性能" | "L45 `Pattern.compile(regex)` 在 onPowerFieldChanged 回调内(50Hz),每次 ~200us,建议抽为 `static final Pattern P`" |
| "架构需要优化" | "L260 `DisplayController.getPowerState()` 返回整车状态,但类名是 Display,调用方会误用;建议搬到 PowerImpl 暴露" |
| "遵循 SOLID" | "具体是哪条?本例是 SRP 问题:L260 一个类承担 Display + 整车 Power 两个职责" |
| "命名不好" | "`a` 变量在 L45 外层作用域 50 行,含义不明,建议 `elapsedMs`" |

---

## 三级裁决(对标 Gerrit 分数)

| 级别 | 特征 | Gerrit 分 |
|---|---|---|
| **P0 / Critical** | 真崩溃 / 数据丢失 / 安全 / 隐私合规双命中 / API 契约破坏 / 缺 Jira | **-1** |
| **P1 / Important** | 真 risk(同类其他已防,本方法没防)/ 架构混淆 / 线程安全 / IPC 挂死 | **0** 或 -1 |
| **P2 / Medium** | code smell / 维护性 / Google Style 违反 | **+1** |
| **P3 / Low** | 可选改进 / 风格建议 | **+1** |
| 无问题 | - | **+1**(+2 保留给人工评审) |

### 分数决策规则

- 任何 P0 → **-1**
- 只 P1 + 无 P0 → **0**(建议改,不阻断)
- 无 P0/P1 有 P2/P3 → **+1**
- 纯净 → **+1**(不抢 +2)

---

## 评论 5 要素(每条必含)

```
[P<级别>] <file>:<line> - <一句话标题>

**依据**:<权威文档 + 章节>
**现象**:<具体代码在做什么 + 什么场景会出什么问题>
**原理**:<为什么这是问题>
**建议**:<具体修法>

**示例**:
// Before
<当前代码>
// After
<修复代码>
```

---

## 评审规模建议

来自 Google Engineering Practices:

| 评审等级 | 建议条数 | 说明 |
|---|---|---|
| 小 CR(< 50 行改动) | 0-3 条 | 快评快合 |
| 中 CR(50-300 行) | 3-8 条 | 聚焦重点 |
| 大 CR(> 300 行) | 5-12 条 | 分模块整理 |

**超过 12 条 inline** 说明:
1. CR 过大(建议拆分)
2. 或 reviewer 过滤不够(应聚焦 top 问题)

---

## 对开发友好

1. **排序**:P0 > P1 > P2 > P3,先写重要的
2. **分组**:按 file 聚合,不散乱
3. **语气**:客观陈述 + 给建议,不说教
4. **鼓励**:修复重要 bug 时加一句"这处修复很关键"
5. **可操作**:Before/After 代码直接能贴

---

## 成功指标

- 开发拿到评论:**90%+ 直接能改**,不用再问
- 每条评论都有**后果说明**(why)
- **P0 零漏报**(核心价值)
- **P3 噪音**趋近于零(开发不烦)
- **每条评论有权威依据**(不是 AI 常识)

---

## 反例 / 历史伪阳性

| 日期 | CR | 评论 | 判定 | 原因 |
|---|---|---|---|---|
| 2026-04-19 | 993636 | `e.printStackTrace()` 不规范 | ❌ | 项目允许 |
| 2026-04-19 | 993636 | commit message 错别字 | ❌ | 团队约定不评 commit msg 格式 |
| 2026-04-19 | 993636 | "代码修改量<10 行实际 49 行" | ❌ | 团队约定不评 commit msg 格式 |
| 2026-04-19 | 993636 | DisplayController NPE 缺 null check | ✅ 真 P0 | 同类其他回调都判了 null |
| 2026-04-19 | 993636 | 广播 try-catch 外置 | ✅ 真 P1 | 真实会丢事件 |
| 2026-04-19 | 993636 | DisplayController 违反 SRP | ✅ 真 P1 | 调用方真会混淆 |
