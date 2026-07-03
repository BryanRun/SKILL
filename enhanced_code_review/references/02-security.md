# 02 · 安全性（车载中间件适用范围）

> **SELinux/MAC 强制访问控制**专项独立成篇，见 `references/18-selinux-policy.md`（v2.5.5）。
> CR 改动命中 `*.te`/`*.cil`/`*_contexts`/`te_macros`/`/sepolicy/` 时由 `selinux_policy` 维度承接，
> 本篇仅覆盖应用层安全（OWASP/CWE/输入校验/密钥/权限等）。

## 基础参考

- [OWASP Top 10 - 2024](https://owasp.org/www-project-top-ten/)
- [CWE/SANS Top 25 (2023)](https://cwe.mitre.org/top25/)
- [Android Security Best Practices](https://developer.android.com/privacy-and-security/security-tips)
- [Google C++ Secure Coding Guide](https://google.github.io/styleguide/cppguide.html#Security)
- ISO/SAE 21434 (Road vehicles — Cybersecurity engineering)
- AUTOSAR C++14 Guidelines

---

## 1. 权限与身份（AuthN/AuthZ）

### 评审项

| 项 | 依据 | 级别 |
|---|---|---|
| AIDL 接口未 `checkCallingPermission()` | Android Framework 规范 | P0 (sensitive) / P1 (non-sensitive) |
| CarProperty 未声明 READ/WRITE 权限 | Android Automotive API | P0 |
| 跨进程调用未校验 caller UID（如只允许 system/vendor） | Android CDD | P1 |
| SELinux neverallow 规则缺失 | AOSP SELinux policy | P0 |
| 客户端传入的 UID/RoleFlag 被直接信任 | OWASP A01:2021 Broken Access Control | P0 |
| 新增 vendor API 可被 3rd party 绕过 vendor-interface 调用 | Android Treble | P1 |

---

## 2. 数据安全（敏感信息）

### 评审项

| 项 | 依据 | 级别 |
|---|---|---|
| 日志输出 VIN / IMEI / GPS / 电话号 / Token | ISO 21434 + GB/T 41871-2022 | P0 |
| dumpsys 含用户隐私 | Android Privacy | P1 |
| 持久化明文密码/凭证（应 Keystore） | Android Keystore System | P0 |
| 车身数据未隔离可被非车主进程读 | GB/T 37964-2019 | P1 |
| 错误信息返回给 UI 时含 stack trace / 内部路径 | OWASP A04:2021 | P1 |

### 不评审的项

- HTTPS 证书固定（车机内部 IPC 不需要）
- JWT/Session（非 Web 接口）
- XSS/CSRF（非 Web）

---

## 3. 注入攻击

### 评审项（车载相关）

| 项 | 依据 | 级别 |
|---|---|---|
| 命令注入：字符串拼接到 `Runtime.exec`() / `ProcessBuilder` / `popen`() | CWE-78 | P0 |
| 路径遍历：用户输入进入文件路径无白名单校验 | CWE-22 | P0 |
| SQL 注入：字符串拼接 SQL（Room/ContentProvider） | OWASP A03:2021 | P0 |
| Intent hijacking：隐式 Intent 未声明 package | Android Security | P1 |

---

## 4. 并发与线程安全（车载重点）

> 车载中间件最高发 P0/P1。Binder 线程池、HAL 回调、Handler、EventHolder 多线程混合。

### 4.1 共享状态访问

| 项 | 依据 | 级别 |
|---|---|---|
| 跨线程字段未 `volatile` / 未 synchronized | JMM + Effective Java Item 78 | P0 |
| 单例懒初始化未用 double-check 或 static holder | Effective Java Item 83 | P1 |
| 非线程安全集合（HashMap）用于多线程 | Java Concurrency in Practice | P0 |
| 全局单例在多线程并发修改 | JCIP | P0 |

### 4.2 Check-Then-Act (TOCTOU, CWE-367)

典型模式：

```java
if (!cache.contains(key)) cache.put(key, v);  // P0 TOCTOU
if (balance >= amount) balance -= amount;      // P0 金融类错误
```

### 4.3 Race Condition

| 项 | 检查方式 |
|---|---|
| 多线程访问共享状态 | grep 字段的写点，看是否都在一个 lock 下 |
| Lazy initialization 无 lock | 检查 `if (instance == null) instance = new` |
| Counter 自增未原子化 | 应使用 `AtomicInteger` |
| 锁顺序不一致导致死锁 | 检查多个 synchronized 块的加锁顺序 |

### 4.4 TOCTOU 典型场景

```java
// Dangerous
if (!file.exists()) file.createNewFile();   // P0
if (!list.contains(x)) list.add(x);         // P0

// Safe
Files.createFile(path);                      // throws if exists
ConcurrentHashMap.putIfAbsent(key, value);
```

---

## 5. 资源管理（CWE-664, CWE-772）

### 评审项

| 资源 | 关闭方式 |
|---|---|
| `Cursor` / `InputStream` / `OutputStream` | try-with-resources |
| `BroadcastReceiver` / `ContentObserver` | 成对 register/unregister |
| `Handler.postDelayed` | `onDestroy` 中 `removeCallbacks` |
| 线程池 | `shutdown()` |
| `AssetManager` / `FileDescriptor` | close |
| `linkToDeath` 设置后 | 死亡时 unregister callback |
| `RemoteCallbackList` | `beginBroadcast()` / `finishBroadcast()` 成对 |

### 典型 P0

```java
// P0: 未 close
Cursor c = db.query(...);
c.moveToFirst();  // 若抛异常，c 泄漏

// P1: ListenerList 无 remove 路径
private static List<Listener> listeners = new ArrayList<>();  // 无界
```

---

## 6. IPC 可靠性

### 评审项

| 项 | 依据 | 级别 |
|---|---|---|
| 多客户端回调未用 `RemoteCallbackList` | Android IPC Best Practice | P1 |
| `beginBroadcast()` / `finishBroadcast()` 不配对 | Android API contract | P0 |
| **广播循环内单个 RemoteException 抛出中断整个广播** | Android IPC | **P1** |
| `linkToDeath` 缺失 | Android Binder | P1 |
| 入参未校验（null / 越界） | OWASP A03 | P0/P1 |
| AIDL 方法新增未更新 `current.txt` | Android API Council | P1 |

---

## 7. 无限循环 / CPU 占用 (DoS, CWE-835)

### 评审项

| 项 | 级别 |
|---|---|
| `for/while` 无退出条件 | P0 |
| 递归无栈深度限制 | P0 |
| `Handler.postDelayed` 自循环（onX → post → onX） | P1 |
| 高频回调（> 10Hz）内 `Log.i` | P2（降 Log.d 或降频） |
| Binder 线程内阻塞 I/O | **P0**（耗尽 Binder 线程池 → AIDL 挂死） |
| MainLooper 里 `Thread.sleep()` / 同步网络 | P0 |

---

## 8. 弱加密 / 加密误用

### 评审项

| 项 | 依据 | 级别 |
|---|---|---|
| MD5/SHA1 用于 security 用途 | NIST SP 800-131A | P0 |
| 硬编码密钥/IV/salt | CWE-798 | P0 |
| AES ECB 模式 | CWE-327 | P0 |
| 密钥长度不足（RSA < 2048 / AES < 128） | NIST SP 800-57 | P1 |
| 缺 HMAC（无认证加密） | FIPS 198-1 | P1 |

---

## 9. 车载专项

### 9.1 电源时序（车机特有）

- 新增功能未考虑 STR（Suspend To RAM）快速启动场景
- 冷启动场景下，依赖的服务未 ready
- 休眠唤醒后，内存状态未刷新
- 上电时序（MCU → SOC → AP → Service → App）哪一层未就绪的 NPE？

### 9.2 诊断

- DTC 上报后**缺清除路径**（故障灯常亮）
- DID 编码不符合 UDS 服务规范
- 诊断 session timeout 未 reset

### 9.3 OTA / 升级

- 升级失败无回滚
- 升级中断后二次启动不可恢复
- A/B partition 切换异常
