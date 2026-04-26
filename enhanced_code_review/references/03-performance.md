# 03 · 性能（车载中间件）

## 基础参考

- [Effective Java Item 67](https://www.oreilly.com/library/view/effective-java-3rd/9780134686097/) — Optimize judiciously
- [Google Android Performance Patterns](https://developer.android.com/topic/performance)
- [Java Performance: The Definitive Guide (Oaks, 2020)](https://www.oreilly.com/library/view/java-performance-the/9781492056102/)
- [ART runtime performance best practices](https://source.android.com/docs/core/runtime)

---

## 1. 时间复杂度 / 算法

### 评审项

| 项 | 依据 | 级别 |
|---|---|---|
| 嵌套循环 O(n²) 在 n > 100 的热路径 | Big-O | P1 |
| 循环内 `Pattern.compile(regex)` | Effective Java Item 67 | P1 |
| 循环内 JSON 解析（Gson/Jackson） | API cost | P1 |
| 循环内 Binder IPC 调用 | Binder transaction 昂贵 | **P0** (≥ 10次) / P1 (<10) |
| for 循环内开关 DB 连接 | N+1 | P1 |

### 常见改法

```java
// Bad: N 次 Binder IPC
for (int id : ids) mService.query(id);

// Good: 批量
List<Result> results = mService.queryBatch(ids);
```

---

## 2. 阻塞主线程 / Binder 线程

### 评审项

| 场景 | 级别 | 依据 |
|---|---|---|
| MainLooper 内 sync I/O | **P0** | Android ANR |
| MainLooper 内 `Thread.sleep()` | **P0** | ANR |
| MainLooper 内同步网络 | **P0** | ANR |
| **Binder 线程内阻塞 I/O（会耗尽 Binder 线程池）** | **P0** | Android Binder doc |
| `SharedPreferences.commit()` 在主线程 | P1 | 应 `apply()` |
| `ContentResolver.query()` 主线程 | P1 | 应 AsyncQueryHandler |

---

## 3. 内存

### 评审项

| 项 | 依据 | 级别 |
|---|---|---|
| 无界集合（`List<Listener>` 只 add 不 remove） | CWE-401 | P0 |
| cache 无 size 上限 → OOM | | P1 |
| 监听器注册无配对反注册 | Android lifecycle | P1 |
| 大对象强引用持有 | `WeakReference` | P1 |
| 循环内 `String +=`（应 StringBuilder） | Effective Java Item 63 | P2 |
| 大文件整体加载进内存（应 stream） | | P1 |

---

## 4. 缓存

### 评审项

| 项 | 级别 |
|---|---|
| 昂贵操作重复计算（无 memoization） | P2 |
| cache 无 TTL → stale data 永久存在 | P1 |
| cache 无 invalidation 策略 | P1 |
| cache key 冲突风险 | P1 |
| 用户数据全局缓存 → 隐私/安全 | P0 |

---

## 5. 数据库 / I/O

### 评审项

| 项 | 级别 |
|---|---|
| N+1 查询 | P1 |
| 未加 index 的查询字段 | P2 |
| `SELECT *` 只用几列 | P3 |
| 无分页加载全表 | P1 |
| SQLite 事务未包裹批量写 | P1 |

---

## 6. CPU 占用

### 评审项

| 项 | 级别 |
|---|---|
| 热路径（> 10Hz）内 crypto（MD5/SHA） | P1 |
| 热路径内 reflection | P1 |
| 热路径内 `Class.forName()` | P1 |
| 定时器未配对 cancel，造成 CPU 持续唤醒 | **P0**（车机续航） |

---

## 7. 车载专项性能

### 7.1 启动性能

- BootCompleteReceiver 里做重活 → 拖慢开机
- Provider onCreate 做 I/O → 拖慢 Zygote
- 未使用 StartupWithTracer 追踪

### 7.2 续航（suspend / STR）

- 持有 WakeLock 未 release
- Alarm 使用 `ELAPSED_REALTIME_WAKEUP` 过于频繁（< 5 min）
- 定时器在 STR 状态下仍运行

### 7.3 IO

- QNX PPS 订阅/发布频率 > 100Hz 直接进 Binder
- 高频事件未做 debounce/throttle

---

## 评审输出模板

```
[P1] <file>:<line> — 热路径内编译正则
**依据**：Effective Java Item 67
**现象**：`onPowerFieldChanged` 回调 50Hz，每次 `Pattern.compile` 耗时 ~200us，CPU 占用持续 1%
**建议**：抽为 `private static final Pattern P = Pattern.compile(...)`
**示例**：
// Before
void onEvent(Event e) { if (Pattern.compile(REGEX).matcher(e.tag).matches()) ... }
// After
private static final Pattern P = Pattern.compile(REGEX);
void onEvent(Event e) { if (P.matcher(e.tag).matches()) ... }
```
