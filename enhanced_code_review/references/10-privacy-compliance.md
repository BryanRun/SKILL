# 10 · 隐私合规评审（P0 级，高精确率触发）

> 本维度仅覆盖 **隐私合规**（Privacy Compliance）。
> 信息安全（TLS/签名/权限/密码学等）相关条款按 02-security.md 处理。
> 本维度新增来源：飞书表格《产品功能 信息安全要求-v1.2-20260210》+《附录-个人信息定义》。

## 0. 前置原则：**宁可漏报，不可误报**

隐私合规问题按 **P0（-1）** 算，分数权重极大 → **触发条件必须"确认无误"**。
**三重门控**全部命中才触发，任一不满足 → **不发**。

- **门控 A · 数据信号**：代码出现"确认属于个人信息 / 敏感数据"的**具体标识**（见 §2 清单）
- **门控 B · 去向信号**：该数据流向**高风险 sink**（明文存储 / 明文日志 / 明文网络 / 跨组件传递）
- **门控 C · 语义确认**：不是测试代码 / 不是注释 / 不是文档示例 / 不是 mock / 不是 `@Deprecated` 预删字段 / 变量名非单纯巧合（如只是 `name` 无上下文）

> **评审者须在评论中同时引用「门控 A 证据行」和「门控 B 证据行」**；只命中一端 → 降为 **P3 提示**或直接 drop。

---

## 1. 纳入的需求清单（v1.2-20260210）

| 需求 ID | 主题 | 评审要点 |
|---|---|---|
| CS-PO-014 | 敏感权限图标 | 使用敏感权限时应调用状态栏通知接口（见 CS-PO-022） |
| CS-PO-016-001 | WiFi 密码加密存储 | 系统设置中 wifi 热点密码 / 信号登录密码 **必须**走 keystore 加密，**禁止**明文存档 |
| CS-PO-016-002 | 人脸特征值加密存储 | DMS 人脸特征值加密存储 ≥ AES-128；**密钥与特征值不得同目录** |
| CS-PO-016-003 | 声纹特征值加密存储 | 声纹特征值 keystore 加密存储，**禁止**明文 |
| CS-PO-017 | 安全通信 | 个人信息 / Token / 设备标识 / 认证数据 → 云端**必须加密通道**；**禁止明文 HTTP / 明文 MQTT / 明文 socket** |
| CS-PO-020-003 | 账户/隐私政策选择安全日志 | 账户登录/登出、隐私政策的选择结果须记录安全日志 |
| CS-PO-022-001 | 敏感权限管理总接口 | 敏感权限=定位/麦克风/车内摄像头/通讯录；须走项目权限管理模块 |
| CS-PO-022-002 | 智驾定位权限 | 首次上电弹窗；使用时 `requestLocationUpdates` / 退出时 `removeUpdates`；授权状态经 FDBus `ADAS_USER_LOCATION_SET` 同步至 QNX |
| CS-PO-022-003 | 车内摄像头权限 | 使用前 check 授权；使用开始/退出调用状态栏接口 |
| CS-PO-022-004 | 定位权限 | 同上 |
| CS-PO-022-005 | 麦克风权限 | 同上 |
| CS-PO-022-006 | 通讯录权限 | 读取蓝牙电话缓存联系人前 check 授权 |
| CS-PO-023 | 用户告知与授权 | 处理个人信息前应有隐私政策（涵盖处理者/种类/目的/期限/撤回/第三方/跨境/未成年人/变更机制 等 11 项） |
| CS-PO-024 | 用户数据处理限制 | 仅使用《用户告知》清单内数据；超期必须删除或匿名化 |
| CS-PO-025 | 非必要数据独立协议 | 埋点/画像/模型优化等需**独立协议**，**不得**绑定在主隐私协议内；用户拒绝不得影响核心功能 |
| CS-PO-026 | 撤回同意 | 支持随时撤回；撤回后停止采集并删除本地数据；云端需同步通知 |
| CS-PO-027 | 本地数据删除 | APP 提供主动删除 or 通过恢复出厂设置删除本地个人数据 |
| CS-PO-028 | QNX 侧恢复出厂设置 | Android 侧恢复出厂 → FDBus 信号 → QNX 同步删除（记忆泊车/数据闭环/DMS 人脸特征值等） |

---

## 2. 个人信息 & 敏感个人信息清单（自《附录-个人信息定义》）

> 源文档定义在《LXLlsDkmxhgxOHtwQFqcTDbpnBb` POXGWm`》。以下是映射到代码特征的白名单。

### 2.1 敏感个人信息（命中即高置信度，√ 项）

| 类别 | 典型字段名 / 关键词（代码层） |
|---|---|
| **生物识别** | `faceFeature`, `face_vector`, `voiceprint`, `voicePrint`, `fingerprint`, `iris`, `gene` |
| **身份证件** | `idCard`, `idNumber`, `passport`, `driverLicense`, `socialSecurity`, `medicareId` |
| **精准位置** | `latitude` + `longitude` 成对、`gpsLocation`, `locationTrack`, `trajectory` |
| **通信内容** | `smsBody`, `callRecord`, `emailContent`, `messageBody` |
| **通讯录** | `contactList`, `phoneBook`, `friendsList` |
| **浏览历史** | `browseHistory`, `clickLog`（注：需 + 用户维度） |
| **财产信息** | `bankCard`, `creditCard`, `accountBalance`, `transactionRecord` |
| **健康** | `medicalRecord`, `diagnosis` |

### 2.2 一般个人信息（需结合上下文，不单独触发）

- 基础：`userName`, `birthday`, `gender`, `homeAddress`, `phoneNumber`, `email`
- 设备：`imei`, `imsi`, `macAddress`（WLAN/BT）, `serialNumber`
- 车辆：`vin`, `plateNumber`
- 账号：`account`, `userId`, `token`, `refreshToken`, `sessionId`, `password` 明文变量

### 2.3 典型上下文（凡命中需双重确认）

**不是**个人信息的常见误报：
- 单元测试 / mock 文件里的假数据（目录含 `test/`, `androidTest/`, `mock/`）
- 注释、字符串字面量 TAG、日志级别常量
- 仅变量名巧合：如 `name` / `id` 泛指非人，上下文未关联"用户" / "车主" / "驾驶员"
- 协议/结构体字段**声明**但尚未实际写入数据

---

## 3. 高风险 sink 模式（门控 B）

只有当 §2 数据流向以下 sink 之一，才可能构成 P0：

### 3.1 明文网络传输（对应 CS-PO-017）
- `http://` URL（硬编码或动态拼接）
- `new URL("http:...")` / `OkHttp` builder 未启用 TLS
- `setHostnameVerifier(ALLOW_ALL)` / `X509TrustManager` 接受一切证书
- MQTT broker 明文端口 1883（非 8883）
- Socket 明文 + 无 TLS 包装

### 3.2 明文落盘 / 明文存储（对应 CS-PO-016）
- `SharedPreferences` 未加密（非 `EncryptedSharedPreferences`） + 写入 §2.1 敏感字段
- `FileOutputStream` / `openFileOutput` 写入 §2.1 敏感字段
- 数据库列直接存敏感特征值（未经 AES/keystore）
- 密钥与加密数据**同目录**（CS-PO-016-002 特别禁止）

### 3.3 明文日志
- `Log.d/i/w/e`（Android） / `printf` / `ALOGD` 输出 §2.1 敏感字段的明文值
- `toString()` 泄露敏感字段 + 被日志 / exception 打印

### 3.4 权限使用未声明 / 未告知（CS-PO-022）
- 调用 `android.permission.CAMERA` / `RECORD_AUDIO` / `ACCESS_FINE_LOCATION` / `READ_CONTACTS`
  - **未**在使用前检查权限管理模块状态（自研 PermissionManager，非 ContextCompat 系统层）
  - **未**在开始/退出时调用状态栏显示接口（CS-PO-022-002~006 要求）

### 3.5 跨进程 / 跨端传递（CS-PO-028）
- Android → QNX FDBus 信号名指向 §2.1 敏感字段 **且** 未经加密
- Binder / AIDL 接口在参数中明文携带 §2.1 字段

### 3.6 不支持撤回 / 不支持删除（CS-PO-026 / CS-PO-027）
- 新增采集敏感数据的类 **但** 无对应的 `delete*` / `revoke*` / `clear*` 方法

---

## 4. P0 触发规则表（必须"双命中"）

| 规则 ID | 数据信号（门控 A） | 去向信号（门控 B） | 级别 | 对齐需求 |
|---|---|---|---|---|
| **PC.NET.PLAIN** | §2.1 字段 | `http://` / 非 TLS socket / setHostnameVerifier(ALLOW_ALL) | **P0** | CS-PO-017 |
| **PC.STORE.PLAIN_SENSITIVE** | §2.1 字段 | 未经 keystore / AES 的 SP / File / DB 写入 | **P0** | CS-PO-016-001/002/003 |
| **PC.KEY_COLOC** | §2.1 字段 + 密钥文件 | 落盘目录同源（同 `File.getParent()` 命中） | **P0** | CS-PO-016-002 |
| **PC.LOG.LEAK** | §2.1 字段 **明文** 或 `toString()` 包含 | `Log.*` / `printf` / `ALOGD` | **P0** | CS-PO-017 隐含 |
| **PC.PERM.MISS_CHECK** | 调用敏感权限 API（定位/麦克风/摄像头/通讯录） | 未走项目 PermissionManager check | **P0** | CS-PO-022-001~006 |
| **PC.PERM.MISS_STATUS** | `requestLocationUpdates` / `openCamera` / `AudioRecord.startRecording` | 同类路径中未调用**项目状态栏显示接口** | **P1** | CS-PO-022-002~005 |
| **PC.QNX_WIPE.MISS** | 新增 QNX 侧用户数据存储（记忆泊车/DMS/数据闭环） | 未订阅 FDBus 恢复出厂信号 / 无 `wipe*` handler | **P1** | CS-PO-028 |
| **PC.REVOKE.MISS** | 新增采集敏感数据类 | 无 `revoke*` / `clearUserData*` / `optOut*` 接口 | **P1** | CS-PO-026 / CS-PO-027 |
| **PC.OPTIONAL_BINDING** | 埋点 / 画像 / 模型优化数据上传 | 开关与主隐私协议绑定（同一 checkbox 同意即启用） | **P0** | CS-PO-025 |

**级别裁决**：
- 规则表中 **P0 必须"双命中"**（即需同时引用数据证据行 + 去向证据行）。
- 只命中一端 → 降级为**疑似**，在 cover 中口述，不落 inline 评论。
- 如代码仅为**接口声明 / 字段定义**（无赋值无调用），一律 **drop**（不满足门控 C）。

---

## 5. 典型反例（绝对不发，历史误报）

| 误报场景 | 为什么不发 |
|---|---|
| `String userName = ...;` 变量声明，无落盘/日志/网络 | 未命中门控 B |
| `Log.d(TAG, "user login")` 不含敏感字段值 | 非敏感明文 |
| Test 目录中的 `val mockVin = "LVXXX..."` | 门控 C 排除 |
| 注释里写 "// TODO: support face feature" | 注释排除 |
| `interface IContact { List<String> list(); }` 纯声明 | 无实现无数据流 |
| `http://schemas.android.com/apk/res/android` XML 命名空间 | 非传输 URL |
| `requestPermissions(CAMERA)` 调用 Android 标准 API 但项目未自研 PermissionManager 时 | 规则不适用于无自研权限管理的模块（须先确认 PermissionManager 在该模块范围内） |

---

## 6. 评论 5 要素（继承 07）

```
[P0] <file>:<line> - <一句话标题>（隐私合规）

**依据**: 《产品功能 信息安全要求-v1.2-20260210》CS-PO-XXX + 《附录-个人信息定义》第 N 类
**证据（门控 A 数据）**: <file>:<line_a> - <代码节选>
**证据（门控 B 去向）**: <file>:<line_b> - <代码节选>
**原理**: <为什么这是隐私合规问题 + 法规/需求后果>
**建议**: <具体修法，引用 CS-PO-XXX 中的方案>

**示例**:
// Before
<当前代码>
// After
<修复代码>
```

---

## 7. 与方法论 / 工具链的关系

- **Step 8 · 隐私合规**：评审工作流在 07 步骤后追加 Step 8（见 07-review-methodology.md）。
- **机械扫描**：由 `scripts/privacy_compliance_scan.py` 执行门控 A + B 的**候选命中**；LLM 再做门控 C 语义确认。
- **权威依据**：评论中的"依据"行必须引用 **CS-PO-XXX** 需求号，以及（若涉及个人信息分类）引用《附录-个人信息定义》对应行。
- **与 02-security.md 的边界**：
  - 02 负责 TLS 证书 / 密码学算法强度 / 权限模型（OWASP/CWE 层）
  - 10 负责**数据 × 用途 × 用户告知** 的合规性（GB/T 35273 + 车联 PO 明文层）
  - 有交集时**双重列出**（一条 inline 可同时标记 `security + privacy`）

---

## 8. 源文档索引

- 本技能内的摘录即本节 §1~§2，已满足评审使用。
- 原始需求：飞书表格 `LXLlsDkmxhgxOHtwQFqcTDbpnBb`
  - Sheet `ft1ojh`：产品功能 信息安全要求-v1.2-20260210（本技能只采用**隐私合规**类条目）
  - Sheet `POXGWm`：附录-个人信息定义（敏感个人信息 √ 清单）
- 法规背景参考：GB/T 35273-2020、GB/T 41871-2022（汽车数据安全）、个人信息保护法（PIPL）。
