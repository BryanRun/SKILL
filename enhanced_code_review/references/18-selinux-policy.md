# 18 · Android SELinux 策略评审专项（仅在 SELinux 相关代码上下文开启）

> **本文件为「上下文门控」专项**：与 C++/Java/C 并发专项的「按语言分派」不同，SELinux 维度
> **只在 CR 改动命中 SELinux 相关文件时才强制开启**（见下文「触发条件」）。普通业务 CR
> （无 sepolicy 改动）该维度 `scanned=false`，不产生噪声，也不影响打分。
>
> **权威基线**：
> - Android Open Source Project — *Security-Enhanced Linux in Android*（source.android.com/docs/security/features/selinux）
> - AOSP *Implementing SELinux* / *Customizing SELinux* / *Validating SELinux*
> - Android CDD（Compatibility Definition Document）§9.7 Kernel Security Features（SELinux 强制 enforcing、禁 permissive 域）
> - NSA SELinux Policy Language / CIL（Common Intermediate Language）Reference
> - 工程实践文档《Android SELinux策略平台化配置指导文档》（vendor/autolink，维护者 @李根，v1.0 2026-02-27）

---

## 触发条件（上下文门控，硬约束）

CR 的 diff 命中以下**任一**特征即判定为「SELinux 上下文」，`gerrit_review.py::build_context`
会向 `ctx['languages']` 追加一个伪语言条目 `lang="SELinux"`，从而强制 `selinux_policy`
维度 `scanned=true` 并要求 `rule_check_table["SELinux"]` 逐条填写：

| 维度 | 命中特征 |
|------|---------|
| 文件后缀 | `*.te`、`*.cil`（含 `*.compat.cil` / `*.ignore.cil`） |
| 无后缀策略文件名 | `file_contexts`、`property_contexts`、`service_contexts`、`seapp_contexts`、`hwservice_contexts`、`vndservice_contexts`、`genfs_contexts`、`keys.conf`、`mac_permissions.xml`、`te_macros` |
| 路径片段 | 路径中含 `/sepolicy/` 或 `/selinux/` |
| 构建脚本 | `*.mk` / `*.bp` 中出现 `SEPOLICY_DIRS` / `BOARD_*_SEPOLICY` / `SYSTEM_EXT_*_SEPOLICY_DIRS` / `PRODUCT_*_SEPOLICY_DIRS` 等 sepolicy 编译宏 |

**不命中**上述任一特征的 CR：`selinux_policy` 维度允许 `scanned=false`（`DIMS_ALLOW_NOT_SCANNED`
白名单），**禁止**对非 SELinux 代码强行套用本专项产生评论。

---

## 规则表（14 条：P0 4 条 / P1 6 条 / P2 3 条 / P3 1 条）

| 规则 ID | 一句话 | 分级 | 权威依据 |
|---------|--------|------|----------|
| **SEL-PERM-1** | 生产策略里出现 `permissive` 域 / `permissive_or_unconfined` → 关闭强制、提权面 | **P0** | Android CDD §9.7；AOSP *Validating SELinux*（user 版禁 permissive） |
| **SEL-WILD-1** | 通配符过度授权（`allow X Y:class *` / `self:capability *` / `*:*`）→ 违反最小权限 | **P0** | AOSP *Writing policy*；指导文档 §7.2「避免过度授权」 |
| **SEL-WX-1** | W^X 违规：`execmem` / `execmod` / `execstack` / `execheap` / 从 data 分区可执行 | **P0** | AOSP *Security features*（W^X）；CWE-732 |
| **SEL-NEVERALLOW-1** | 削弱 / 绕过 `neverallow`（含触发 CTS neverallow 的新 `allow`） | **P0** | AOSP *Implementing SELinux*；CTS `neverallow` 强制 |
| **SEL-CAP-1** | 危险 capability 授予（`sys_admin`/`dac_override`/`setuid`/`sys_module`/`mac_admin` 等）无理由 | **P1**（授予 untrusted 域→P0） | AOSP *Writing policy*；最小权限原则 |
| **SEL-VIOLATOR-1** | 挂接 `*_violators` 临时豁免属性，作为永久方案、无清退计划 | **P1** | AOSP Treble neverallow 白名单（临时性） |
| **SEL-DONTAUDIT-1** | 用 `dontaudit` 掩盖真实 denial，而非定位根因 | **P1** | 指导文档 §7.2「不要用 dontaudit 掩盖真正的问题」 |
| **SEL-LABEL-1** | 上下文标签错误：正则未 `(/.*)?` 锚定 / 类型未定义 / label 错配 / 写死设备名 | **P1** | AOSP *Customizing SELinux*（file_contexts 语法） |
| **SEL-VER-1** | 新增 versioned type 但缺版本兼容（`.cil` / `.compat.cil` / `.ignore.cil` / mapping）→ 跨版本编译/加载失败 | **P1** | 指导文档 §3.3 跨版本策略兼容；AOSP *Compatibility* |
| **SEL-CTX-1** | service/seapp/property context 注册与 `.te` 域/类型不匹配（注册无对应 allow / 域未定义） | **P1** | AOSP *Implementing SELinux*（contexts 一致性） |
| **SEL-MIN-1** | 轻度过宽：授予整组权限但实际只需子集（`{ open read write }` 而仅需 `read`） | **P2** | 指导文档 §7.1 最小权限原则 |
| **SEL-MACRO-1** | 重复 allow 模式未用 `te_macros` / 未用 attribute 归并 → 可维护性差、规则膨胀 | **P2** | 指导文档 §7.1/§7.3；AOSP *te_macros* |
| **SEL-COMMENT-1** | 敏感授权（capability / 跨域 binder / prop set / 跨分区访问）缺 why 注释 | **P2** | 指导文档 §7.1「使用宏和注释提高可读性」 |
| **SEL-NAME-1** | 命名 / 目录结构不符规范（`.te` 须小写下划线、描述性；目录按推荐布局；规则分组排序） | **P3** | 指导文档 §2.2 命名规则、§1.1 推荐目录结构 |

> **定级说明**：SELinux 维度**不设 P2/P3 上限**（区别于 platform_design 软规则）。
> 安全相关问题（SEL-PERM / SEL-WILD / SEL-WX / SEL-NEVERALLOW / SEL-CAP）可直接决定 -1/-2。
> 命中 P0 → score ≤ -1（受 SEV-GATE G1 约束）。

---

## 详细规则

### SEL-PERM-1 · 生产策略里出现 permissive 域 【P0】

**问题**：
`permissive <domain>;` 让该域所有违例只记录 AVC 不拦截，等同对该域**关闭 SELinux 强制**。
`permissive_or_unconfined` 宏在 user 版同理。这是攻击者绕过 MAC 的首选目标。

**权威依据**：
- Android CDD §9.7：设备**必须**在 enforcing 模式启动，**不得**在 user 构建包含 permissive 域；
  CTS / VTS 会校验 `getenforce == Enforcing` 且无 permissive 域。
- AOSP *Validating SELinux*：permissive 仅限本地调试，禁止进入提交。

**反面（禁止合入 user 版）**：
```te
permissive allog;            # ❌ 关闭 allog 域强制
```

**正确做法**：
- 调试期可临时 permissive，但**提交前必须移除**，改为补齐精确 `allow` 规则。
- 通过 `adb shell dmesg | grep avc` 收集 denial → 在 `.te` 补最小权限。

**评论模板**：`[P0][SEL-PERM-1] allog 域被设为 permissive，违反 CDD §9.7（user 版禁 permissive 域）。请移除 permissive，按 AVC 日志补齐精确 allow 规则。`

---

### SEL-WILD-1 · 通配符过度授权 【P0】

**问题**：
`allow domain type:class *;` 或 `allow domain self:capability *;` 一次性授予某类**全部**权限/能力，
极大扩张攻击面，违反最小权限原则；且常常掩盖真实需求。

**权威依据**：
- AOSP *Writing SELinux policy*：规则应精确到具体权限位，禁止 `*`。
- 指导文档 §7.2「避免过度授权：不要使用通配符 `*` 授予所有权限」。

**反面**：
```te
allow allog allog_service:binder *;          # ❌ 授予 binder 全部权限
allow allog self:capability *;               # ❌ 授予全部 capability
```

**正确做法**：
```te
allow allog allog_service:binder { call transfer };
allow allog self:capability { fowner sys_nice };   # 只列实际需要的位
```

**评论模板**：`[P0][SEL-WILD-1] allow 规则使用通配符 * 授予整类权限，违反最小权限。请精确列举实际需要的权限位（如 { call transfer }）。`

---

### SEL-WX-1 · W^X 违规（可写可执行内存 / data 分区执行）【P0】

**问题**：
`execmem` / `execmod` / `execstack` / `execheap` 允许「可写且可执行」内存，破坏 W^X，
是代码注入提权的经典前提；从 `*_data_file` 等可写分区 `execute` 同理危险。

**权威依据**：
- AOSP *Security features*：Android 强制 W^X，普通域不应持有 execmem 系列权限。
- CWE-732 Incorrect Permission Assignment for Critical Resource。

**反面**：
```te
allow allog self:process execmem;                       # ❌ 可写可执行内存
allow allog app_data_file:file { execute execute_no_trans };  # ❌ 从 data 执行
```

**正确做法**：移除 execmem 系列；可执行文件统一标 `*_exec` 类型，从只读分区加载。
确有 JIT 等需求须单列域 + 充分注释 + 安全评审。

**评论模板**：`[P0][SEL-WX-1] 授予 execmem/从 data 分区 execute，违反 W^X（AOSP Security features）。请移除并改用只读 *_exec 类型加载可执行文件。`

---

### SEL-NEVERALLOW-1 · 削弱 / 绕过 neverallow 【P0】

**问题**：
修改或删除 `neverallow` 规则、或新增会触发既有 `neverallow` 的 `allow`，会破坏平台安全不变量；
CTS / 编译期 `neverallow` 检查会失败，掩盖式提交（如改 `.ignore.cil` 绕过）尤其危险。

**权威依据**：
- AOSP *Implementing SELinux*：`neverallow` 是编译期 + CTS 双重强制的安全断言。
- 指导文档 §7.2「避免忽略错误」、§3.2.3 版本差异处理（`.ignore.cil` 仅用于版本兼容，非绕安全）。

**正确做法**：
- 遇到 neverallow 冲突应**重新设计权限**（拆域 / 收窄类型），而非削弱断言。
- `.ignore.cil` 只用于跨版本 neverallow 兼容，**不得**用于规避当前版本的安全断言。

**评论模板**：`[P0][SEL-NEVERALLOW-1] 该改动削弱/绕过 neverallow 安全断言（编译期+CTS 强制）。请改为收窄域/类型重新设计，不要修改或 ignore 掉 neverallow。`

---

### SEL-CAP-1 · 危险 capability 授予 【P1，授予 untrusted 域 → P0】

**问题**：
`sys_admin` / `dac_override` / `dac_read_search` / `setuid` / `setgid` / `sys_ptrace` /
`sys_module` / `mac_admin` / `mac_override` / `sys_rawio` 等是高危能力；授予普通服务域即提权，
授予 `untrusted_app` / `isolated_app` 等不可信域属严重越权（P0）。

**权威依据**：AOSP *Writing policy* + Linux capabilities(7) + 最小权限原则。

**反面**：
```te
allow allog self:capability { sys_admin dac_override };   # ⚠️ 高危能力，需充分理由
allow untrusted_app self:capability sys_ptrace;           # ❌ 授予不可信域 → P0
```

**正确做法**：删除非必需高危能力；确需保留必须注释说明用途 + 关联评审。

**评论模板**：`[P1][SEL-CAP-1] 授予 sys_admin/dac_override 等高危 capability 缺乏理由说明。请确认必要性，删除非必需项并对保留项补注释。`

---

### SEL-VIOLATOR-1 · 挂接 *_violators 临时豁免属性 【P1】

**问题**：
`data_between_core_and_vendor_violators` / `system_executes_vendor_violators` /
`system_writes_vendor_properties_violators` 等是 Treble `neverallow` 的**临时白名单**，
表示「本应禁止但暂允」。作为永久方案、无清退计划即埋雷。

**权威依据**：AOSP Treble — violator 属性是过渡豁免，目标是逐步清空。

**正确做法**：作为临时策略须关联 Jira（CHYT1V/CHYKP31/CHER/D01 等）并写入 `unresolved_issues`，
按 CL-1/CL-2 闭环跟踪量产前清退。

**评论模板**：`[P1][SEL-VIOLATOR-1] 挂接 *_violators 临时豁免属性，属 Treble neverallow 过渡白名单。请关联 Jira 跟踪并制定清退计划，不要作为永久方案。`

---

### SEL-DONTAUDIT-1 · dontaudit 掩盖真实 denial 【P1】

**问题**：
`dontaudit` 只是不打印 AVC 日志，**不授予也不拒绝**权限。用它「消除」denial 日志而不分析根因，
会掩盖真实的访问失败，导致功能时灵时坏、问题难定位。

**权威依据**：指导文档 §7.2「避免忽略错误：不要使用 dontaudit 掩盖真正的问题」；AOSP 建议 dontaudit 仅用于已知良性噪声。

**正确做法**：先判定该 denial 是否为真实需求 → 是则补 `allow`，否则修业务逻辑；
仅对**确认良性**的噪声用 dontaudit 且加注释。

**评论模板**：`[P1][SEL-DONTAUDIT-1] 用 dontaudit 抑制 denial 但未分析根因。请确认该访问是否真实需要：需要则补精确 allow，良性噪声才 dontaudit 并注释原因。`

---

### SEL-LABEL-1 · 上下文标签错误 【P1】

**问题**：`file_contexts` / `service_contexts` / `seapp_contexts` 标签错误会导致文件/服务落到错误安全上下文：
- 目录正则未用 `(/.*)?` 锚定 → 子文件漏标 / 误标；
- 引用未定义的 type；
- 可执行文件标成数据类型（或反之）；
- 路径写死 `out/target/product/<设备名>/...` 等不可移植片段。

**权威依据**：AOSP *Customizing SELinux*（file_contexts 正则与 label 规则）。

**反面 / 正确**：
```
# ❌ 未锚定子路径
/data/misc/allog_logs           u:object_r:autolink_log_data_file:s0
# ✅ 正确锚定目录及其下所有文件
/data/misc/allog_logs(/.*)?     u:object_r:autolink_log_data_file:s0
```

**评论模板**：`[P1][SEL-LABEL-1] file_contexts 目录未用 (/.*)? 锚定子路径，子文件将漏标安全上下文。请补全正则。`

---

### SEL-VER-1 · 缺版本兼容处理 【P1】

**问题**：新增/重命名 versioned type（如 `logservice_app_34_0`）但未在 `private/compat/<ver>/`
补 `.cil` / `.compat.cil` / `.ignore.cil`，或未更新 mapping，会导致高版本系统兼容低版本 vendor 时
**类型未定义编译失败 / 策略加载失败**。

**权威依据**：指导文档 §3.3 跨版本策略兼容（CIL 类型映射三要素 / compat 文件 / ignore.cil）；AOSP *Compatibility with previous platform versions*。

**正确做法**：新增 versioned type 时同步在受支持旧版本目录补映射 / 忽略规则（§3.3.1~3.3.3）。

**评论模板**：`[P1][SEL-VER-1] 新增 versioned type 但缺 compat/<ver> 映射或 ignore.cil，跨版本兼容会编译/加载失败。请按指导文档 §3.3 补齐类型映射。`

---

### SEL-CTX-1 · contexts 与 .te 不一致 【P1】

**问题**：
- `service_contexts` 注册了服务但 `.te` 无 `add_service(domain, svc_type)` / 无对应类型定义；
- `seapp_contexts` 引用的 `domain=` / `type=` 在 `.te` 未定义；
- `property_contexts` 标了属性但缺 `set_prop` / `get_prop` 配套。

**权威依据**：AOSP *Implementing SELinux*（contexts 文件与 type/domain 定义必须自洽）。

**评论模板**：`[P1][SEL-CTX-1] service_contexts 注册 allog_service，但 .te 未见对应类型定义 / add_service 授权。请补齐类型与服务注册规则保持一致。`

---

### SEL-MIN-1 · 权限集合过宽（轻度）【P2】

**问题**：授予整组权限但实际只用子集（如 `{ open read write getattr }` 而功能仅需 `{ open read getattr }`）。
非致命，但偏离最小权限，建议收敛。

**权威依据**：指导文档 §7.1 最小权限原则。

**评论模板**：`[P2][SEL-MIN-1] allow 授予 write 但该路径仅需读取，建议收敛权限集到实际所需（最小权限）。`

---

### SEL-MACRO-1 · 重复模式未用宏 / attribute 【P2】

**问题**：多处重复同样的 allow 组合而不用 `te_macros` 宏或 `typeattribute` 归并，导致规则膨胀、
难维护、易漏改。

**权威依据**：指导文档 §7.1 模块化设计 / §7.3 性能优化（合并相似规则、用属性组织类型）；AOSP *te_macros*。

**评论模板**：`[P2][SEL-MACRO-1] 多个域重复同一组 dumpsys allow，建议抽到 te_macros 宏或用 attribute 归并，提升可维护性。`

---

### SEL-COMMENT-1 · 敏感授权缺 why 注释 【P2】

**问题**：高危/跨域/跨分区授权（capability、跨域 binder、`set_prop`、访问他模块数据）缺少注释说明用途，
评审与后续维护无法判断其合理性。

**权威依据**：指导文档 §7.1「使用宏和注释提高可读性」。

**评论模板**：`[P2][SEL-COMMENT-1] 该跨域 binder 授权缺少用途注释，建议补一行 // <原因/约束> 说明为何需要。`

---

### SEL-NAME-1 · 命名 / 目录结构不规范 【P3】

**问题**：`.te` 文件名未用小写下划线 / 不具描述性；目录未按推荐布局（`sepolicy/<ver>/{public,private}`、
`projects/<项目>/sepolicy/{private,vendor}`）；规则未按功能分组、未排序。

**权威依据**：指导文档 §2.2 命名规则、§2.2.3 命名注意事项、§1.1 推荐目录结构。

**评论模板**：`[P3][SEL-NAME-1] 策略文件名 / 目录结构未按指导文档 §1.1/§2.2 规范，建议按 sepolicy/<ver>/{public,private} 布局并使用小写下划线命名。`

---

## SELinux 评审方法论补充

1. **先判上下文，再开维度**：只有命中「触发条件」才扫；非 SELinux CR 不强行套用。
2. **AVC 驱动最小授权**：所有 `allow` 应可回溯到真实 AVC denial（`dmesg | grep avc`），
   不凭空加宽；评审时优先质疑「该权限来源于哪条 denial」。
3. **安全 > 便利**：permissive / 通配符 / 高危 capability / W^X 一律视为安全红线，宁可拒绝合入。
4. **临时即闭环**：violator 属性 / 调试 permissive / TODO 收紧，都要关联 Jira（CHYT1V/CHYKP31/CHER/D01/...）
   并写入 `unresolved_issues`（CL-1/CL-2）。
5. **跨版本必兼容**：新增 versioned type 必须同步 compat / mapping / ignore.cil（§3.3）。
6. **三问 filter 仍适用**：每条 SELinux 评论须过「真问题？/ 有依据？/ 可操作？」三问，避免风格洁癖噪声。
