# 01 · SOLID 原则（车载中间件 · Google Style 依据）

## 基础参考

- [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html)
- [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)
- [Effective Java, 3rd Edition](https://www.oreilly.com/library/view/effective-java-3rd/9780134686097/)（Item 15-24 关于类设计）
- [Clean Architecture (Martin, 2017)](https://www.goodreads.com/book/show/18043011-clean-architecture)
- Bob Martin: *Agile Software Development, Principles, Patterns, and Practices* (2002) — SOLID 原始论文

---

## 5 大原则

### SRP · Single Responsibility Principle（单一职责）

> "A class should have only one reason to change." — Bob Martin, APPP (2002)

**何时评审**：
- 类里方法属于**不相关的抽象层**（HTTP + DB + Domain Logic 混在一起）
- 一个方法**既读状态又发事件又持久化**（无法单测）
- 类承担**两个子系统**的职责（如 Power 类里混入诊断逻辑）
- 类名与实际承担职责**严重不符**（`DisplayController` 实际提供整车电源状态）

**如何提**：
```
[P1] <file>:<line> — 类名 XxxController 返回整车 Power 状态
**依据**：SRP（Martin, APPP）+ 最小惊讶原则
**后果**：调用方看到类名会误认为是组件级接口，易错用
**建议**：搬到 PowerImpl 或新建 SystemPowerController
**示例**：
// Before
class DisplayController { PowerState getPowerState() { ... } }
// After
class SystemPowerController { PowerState getPowerState() { ... } }
```

**不发的项**：
- 类 > 300 行 → 只是大，**不一定违反 SRP**
- 方法 > 30 行 → 只是长，**不一定违反 SRP**

---

### OCP · Open/Closed Principle（开闭原则）

> "Software entities should be open for extension, but closed for modification." — Bertrand Meyer, 1988

**何时评审**：
- 加新芯片/新屏幕/新诊断协议需要**改既有 switch/if**（应扩展，不应修改）
- 已存在 ≥ 2 个实现，但代码仍硬编码分支
- 新增分支但**遗漏 default 异常路径**（扩展后原有的 default 处理被绕过）

**如何提**：
```
[P2] <file>:<line> — 加新平台需改既有 switch
**依据**：OCP（Meyer, 1988）
**后果**：每加一个平台都要 revisit 该函数，改动风险高
**建议**：策略模式（HashMap<Platform, Handler> 注册表）
```

**不发的项**：
- 只有 1 个实现 → **YAGNI**，别建议加 interface
- 代码稳定、不会频繁变动 → OCP 不适用

---

### LSP · Liskov Substitution Principle（里氏替换）

> "Functions that use pointers or references to base classes must be able to use objects of derived classes without knowing it." — Barbara Liskov, 1987

**何时评审**：
- 子类**抛父类未声明的异常**（违反契约）
- 子类**静默降级**（返回默认值或 return，父类会处理）
- 子类**强化前置条件**（接受范围更窄的入参）
- 子类**弱化后置条件**（返回更宽泛的结果）
- 子类通过 `instanceof` 识别类型分支 → 违反 LSP

**如何提**：引用 Effective Java Item 17（minimize mutability）+ Item 20（prefer interfaces to abstract classes）

**不发的项**：
- 子类**增加**字段或方法 → OK
- 子类 override 父类方法 → 只要契约一致就 OK

---

### ISP · Interface Segregation Principle（接口隔离）

> "Clients should not be forced to depend on interfaces they do not use." — Bob Martin, APPP

**何时评审**：
- AIDL 接口方法 > 15 个，每类调用方**只用 30% 方法**
- Listener 接口 3 个回调，50% 实现**只 override 1 个**（其他 `{}` 空实现）
- 新加 AIDL 方法后强制**所有老 Client 重新实现**

**如何提**：拆接口（如 `ILegacyPowerCallback` + `IPowerStateCallback`）

**不发的项**：
- 小接口（< 5 方法）不评 ISP
- 有 default method 的 Java interface，空实现本就允许

---

### DIP · Dependency Inversion Principle（依赖倒置）

> "Depend on abstractions, not on concretions." — Bob Martin

**何时评审**：
- 上层直接 `new` 出底层（无法测试 / 无法替换）
- APP 层绕过 Framework 直接拿 binder
- Service 层直接读 sysfs / hardware properties
- Framework 直接依赖具体 HAL 实现类（应依赖 `IPowerHal` interface）

**如何提**：
```
[P1] <file>:<line> — Framework 直接 new HalImpl
**依据**：DIP（Martin）+ Effective Java Item 5（prefer DI）
**后果**：无法 mock，无法替换，UT 跑不起来
**建议**：构造函数注入 IPowerHal，测试替换为 mock
```

**不发的项**：
- 1 个实现不建议加 Factory → **YAGNI**

---

## 常见 Code Smell（Fowler, *Refactoring*）

| Smell | 何时评审 | 不评审的情况 |
|---|---|---|
| **Long Method** | > 50 行且嵌套 > 3 层 **且** 读不懂 | 线性流程、读得懂就 OK |
| **Feature Envy** | 方法访问另一类的字段 > 自己类 | 单次访问不算 |
| **Data Clump** | 3+ 参数总是一起传递 > 3 处 | 偶尔共现不算 |
| **Primitive Obsession** | String/int 表示领域概念且无校验 | 简单值不需要领域类型 |
| **Shotgun Surgery** | 一个改动需改 5+ 文件 | 正常耦合 OK |
| **Divergent Change** | 一个文件因 3+ 无关原因频繁改 | 偶发改动 OK |
| **Dead Code** | 明确未用的代码（grep 确认 0 调用） | 不确定慎提 |
| **Speculative Generality** | 抽象但只有 1 个实现 | 明确规划多实现 OK |
| **Magic Number** | 数字有业务含义且多处使用 | 局部数学/偏移量 OK |

---

## 重构启发式

1. **按职责切，不按大小切** — 小文件也可能违反 SRP
2. **出现第二个用例才抽象** — 不 speculative
3. **重构前先有测试** — 保行为
4. **命名是设计** — 命不出名说明抽象错
5. **组合优于继承** — 继承强耦合
6. **Illegal state → Unrepresentable** — 用类型系统约束

---

## 三问自检（每条 SOLID 评论必过）

1. **有具体的 bug/risk/混淆吗？** — 纯洁癖 → drop
2. **当前已有 ≥ 2 个实现吗？**（针对 OCP/DIP/ISP）— 1 个 → YAGNI → drop
3. **团队/项目里有类似重构先例吗？** — 没有先例 → 从小处开始，不一次推翻
