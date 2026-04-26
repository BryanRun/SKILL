# 05 · 代码质量（项目规范 + Google Style 参考）

> **硬规则 · 项目级（最高优先级）**：
> - **Java 缩进必须 4 个空格，禁止 tab**（项目硬规范，志强 2026-04-19 明确）
> - **C++ 缩进必须 4 个空格，禁止 tab**（项目硬规范，志强 2026-04-19 明确）
> - **C++ 风格**：不强制 Google C++ Style，**但必须遵循项目原有代码的整体风格**，不能自己乱写
>
> **参考规范（仅作建议依据，非强制）**：
> - Java: [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html)（注：Google 官方 +2 spaces，本项目覆盖为 **4 spaces**）
> - C++: 项目现有代码风格优先；Google C++ Style 仅作参考

---

## 1. Java 强制规范

### 1.1 格式 / 缩进（项目硬规则）

| 规则 | 依据 | 级别 |
|---|---|---|
| **缩进必须 4 个空格，禁止 tab** | **项目硬规范（志强 2026-04-19）** | **P1** |
| 大括号 K&R 风格（非空 block 开括号不换行，闭括号换行） | Google §4.1 | P3（建议） |
| 所有 `if/else/for/do/while` 即使单行也**必须带大括号** | Google §4.1.1 | **P1** |
| 一行一语句 | Google §4.3 | P3 |
| 行宽 ≤ 100 字符（项目无明文时建议） | Google §4.4 | P3 |
| UTF-8 编码 | Google §2.2 | P0（若非 UTF-8） |

### 1.2 命名

| 规则 | § | 级别 |
|---|---|---|
| 类名 `UpperCamelCase` | §5.2.2 | P1 |
| 方法名 / 字段名 `lowerCamelCase` | §5.2.3, §5.2.5 | P1 |
| 常量名 `CONSTANT_CASE` | §5.2.4 | P1 |
| 包名全小写 | §5.2.1 | P1 |
| 泛型类型名 `T` / `E` / `K` / `V` 或 `UpperCamelCase` | §5.2.8 | P2 |
| **禁止使用不清晰的缩写**（`cust` → `customer`） | §5.3 | P2 |

### 1.3 注释 / Javadoc

| 规则 | § | 级别 |
|---|---|---|
| 所有 **public class** 必须 Javadoc | §7.3.1 | P2 |
| 所有 **public / protected 方法**必须 Javadoc（除 override / trivial getter） | §7.3.1 | P2 |
| Javadoc **summary fragment** 必须以句号结尾 | §7.2 | P3 |

### 1.4 imports

| 规则 | § | 级别 |
|---|---|---|
| 禁止 wildcard import (`import java.util.*;`) | §3.3.1 | P2 |
| 禁止 module import | §3.3.1.1 | P2 |
| static 和非 static import 各成一组 | §3.3.3 | P3 |

### 1.5 practices

| 规则 | § | 级别 |
|---|---|---|
| `@Override` 必须加在 override 方法 | §6.1 | P2 |
| 空 catch 块**必须注释说明** | §6.2 | **P1** |
| 禁止 finalizer（Java 9+ 已废弃） | §6.4 | P2 |

---

## 2. C++ 强制规范（Google C++ Style）

### 2.1 格式（项目硬规则）

| 规则 | 级别 |
|---|---|
| **缩进必须 4 个空格，禁止 tab**（项目硬规范，志强 2026-04-19） | **P1** |
| 遵循项目原有代码整体风格（不能自己乱写） | **P1** |
| 行宽：参考项目现有代码 | P3 |

### 2.2 命名（不强制 Google C++ Style）

> **原则**：C++ 命名**按项目现有代码风格**，不强制 Google 风格（snake_case_ 等）。
> 新代码命名只要与文件/模块内已有代码保持一致即可，不作为违规提出。

### 2.3 practices（真 bug 才提）

| 规则 | 级别 |
|---|---|
| header 缺失 `#pragma once` 或 include guard（真导致重复定义） | **P1** |
| `using namespace` 在 header（会污染） | **P1** |
| 虚函数 override 未加 `override` 关键字（真隐藏 bug） | P1 |
| 裸 new/delete 明显有泄漏路径 | **P1** |
| 其他 Google 风格项（命名/缩进风格/参数顺序） | **不强制** |

---

## 3. 可读性

### 3.1 命名

| 项 | 级别 |
|---|---|
| 变量名**严重误导**（如 `list` 实际是 `Map`） | P1 |
| 单字母变量在**非短循环**出现（`i,j,k` 在短 for 内 OK） | P2 |
| 业务概念用缩写（`cust` vs `customer`） | P2 |

### 3.2 注释

| 项 | 级别 |
|---|---|
| 复杂算法**缺**解释注释 | P2 |
| 注释与代码**严重不符**（误导） | P1 |
| `// TODO` 无责任人/期限 | P3 |
| dead code 注释掉 > 30 行 | P2（应删） |

### 3.3 方法 / 函数设计

| 项 | 级别 |
|---|---|
| 方法 > 100 行且**嵌套 > 4 层**且**职责不清** | P1 |
| 方法参数 > 7 个 | P2（引入 parameter object） |
| cyclomatic complexity > 15 | P2 |
| 方法命名**不反映行为**（`handle()` 空方法名） | P2 |

### 3.4 可读性典型问题

- 长表达式无换行（> 200 字符一行）
- 深嵌套三元（`a ? b : c ? d : e ? f : g`）
- 魔数（`if (count > 42)` 未命名）
- 多返回值通过 out 参数返回（应返回 struct/tuple）

---

## 4. 团队/项目规范（硬性，项目 > Google Style）

### 4.1 Jira 号（硬性）

| 项 | 级别 |
|---|---|
| **commit message 缺 Jira 号**（CHYT1V / BAIC / KP31 / CL / T1V / D01） | **P0** → -1 |

### 4.2 车联（AutoLink）项目规范

目前已明确的项目规范（以此为准，**不以 Google Style 推翻**）：

- `e.printStackTrace()` — **允许使用**，不按规范违规对待
- commit message 格式（原因分析/解决方案/自测用例/影响范围/代码修改量） — **志强已明确不管**，不评审错别字或格式
- 项目未明文规定的条目 → 不强制，**最多 P3 建议**

### 4.3 当项目规范与 Google Style 冲突

**原则**：
1. 项目有明文规定 → 按项目
2. 项目未规定 → 按 Google Style
3. 项目习惯与 Google Style 不一致 → **提 P3 建议**不强制

---

## 5. Dead Code / 冗余

| 项 | 级别 |
|---|---|
| 未使用的 private 方法（grep 确认 0 调用） | P2 |
| 未使用的 import | P3 |
| 未使用的 local variable | P3 |
| 未使用的字段 | P2 |
| 注释掉的代码 > 10 行 | P2 |
| 重复代码（DRY 违反）10+ 行重复 3+ 处 | P1 |
| 重复代码（5 行内小重复） | **不评审** |

---

## 6. 评审输出模板

```
[P2] src/.../PowerImpl.java:45 — 方法参数过多（10 个）
**依据**：Google Java Style + Clean Code Chapter 3
**现象**：`setPowerConfig(a,b,c,d,e,f,g,h,i,j)` 可读性差，调用方易错传
**建议**：引入 `PowerConfig` parameter object 封装
**示例**：
// Before
public void setPowerConfig(int a, int b, int c, int d, int e, int f, int g, int h, int i, int j);
// After
public void setPowerConfig(PowerConfig config);
```
