# 04 · 错误处理 + 边界条件

## 基础参考

- [Effective Java Item 70-77](https://www.oreilly.com/library/view/effective-java-3rd/9780134686097/)
- [Google Java Style Guide §6](https://google.github.io/styleguide/javaguide.html#s6-programming-practices)
- [Clean Code, Chapter 7: Error Handling](https://www.oreilly.com/library/view/clean-code/9780136083238/)

---

## 1. 错误处理

### 1.1 Anti-patterns（必评审）

| 模式 | 级别 | 依据 |
|---|---|---|
| 空 catch 块（`catch(E e) {}`） | **P1** | Effective Java Item 77 "Don't ignore exceptions" |
| catch 只 Log（log & forget） | **P1** | 服务状态不一致但无告警 |
| 过宽 catch（`catch(Throwable)`）掩盖 OOM/VerifyError | P1 | Effective Java Item 73 |
| 错误信息泄露内部细节（stack trace 给 UI） | P1 | OWASP A04:2021 |
| 缺失 error handling（I/O / 网络 / 解析） | P1 | |
| Async 异常未处理（无 `.catch()` / 无 `exceptionally()`） | P1 | |
| Handler 内抛异常未 catch → 整条消息队列崩溃 | **P0** | Android Handler contract |
| 线程池 task 异常静默 die | P1 | |

### 1.2 Best Practices（必检）

- [ ] 错误在**合适的边界**捕获（不在最深处）
- [ ] 给用户的错误消息**去敏感**
- [ ] 日志含**足够上下文**（request_id / user_id / params）
- [ ] Async 错误**正确传播或处理**
- [ ] 可恢复错误有**fallback 行为**
- [ ] 致命错误**触发告警/监控**（mWatchdog / bugreport）

### 1.3 三问

> 1. 这个操作失败时会发生什么？
> 2. 调用方会知道出错了吗？
> 3. 日志有足够上下文排查吗？

### 1.4 车载专项

| 项 | 级别 |
|---|---|
| AIDL Binder 调用未 catch `RemoteException` | **P1**（会让进程 crash） |
| HIDL HAL 调用未 catch `RemoteException` | P1 |
| **`RemoteCallbackList` 广播循环内单客户端抛异常中断整个广播** | **P1** |
| Callback 回调里抛异常传到系统进程 | **P0** |

---

## 2. 边界条件（Boundary Conditions）

### 2.1 Null / Empty

| 项 | 检查 | 级别 |
|---|---|---|
| 对象属性访问前未判 null | `a.b.c` → P0 if a/b 可能 null | P0/P1 |
| 数组/List `get(0)` 不判空 | `items[0]` without length check | P1 |
| Optional 滥用（`a?.b?.c?.d`）掩盖结构问题 | Effective Java Item 55 | P2 |
| null vs empty 混用 | | P2 |

### 2.2 数值边界

| 项 | 依据 | 级别 |
|---|---|---|
| 除零 | CWE-369 | P0 |
| int 溢出（`timestamp * 1000`） | CWE-190 | P1 |
| 负数未处理（容量为负） | | P1 |
| 浮点数 `==` 比较 | | P2 |
| off-by-one（`< length` vs `<= length`） | Effective Java Item 64 | P1 |

### 2.3 字符串边界

| 项 | 级别 |
|---|---|
| 空字符串未作边界处理 | P2 |
| 只含空白的 string 被 truthy 判定 | P2 |
| 长字符串无 length limit → 内存/显示问题 | P2 |
| Unicode 边界（emoji / RTL / combining） | P2 |

### 2.4 集合边界

| 项 | 级别 |
|---|---|
| `for...in` / `keys()` 于空对象 | P3 |
| 空集合下 `head()` / `first()` | P1 |
| 删除边界（`size-1` / `size`） | P1 |
| 并发修改异常（`ConcurrentModificationException`） | P1 |

### 2.5 状态机边界

- enum 加了 case，switch 未同步
- 初始状态 / 终止状态未处理
- 状态跳转非法路径未兜底

---

## 3. 典型 dangerous patterns（必 grep）

```java
// 危险：无 null check
String name = user.profile.name;

// 危险：数组访问无边界
String first = items[0];

// 危险：除零
int avg = total / count;

// 危险：truthy 检查排除合法值
if (value) { ... }  // 对 0 / "" / false 都失败

// 危险：并发修改
for (Item i : list) { if (i.expired) list.remove(i); }
```

---

## 4. 评审输出模板

```
[P1] src/.../PowerImpl.java:213 — 广播循环单个 RemoteException 中断整个广播
**依据**：Android IPC Best Practice + Effective Java Item 77
**现象**：单个 callback 死亡时，后续所有 callback 都收不到本次广播
**原理**：RemoteException 从 lambda 内抛出，贯穿 forEach，外层 try-catch 只记一条日志就结束
**建议**：把 try-catch 移到 forEach 内部，保证"一个客户端挂不影响全链"
**示例**：
// Before
try {
  listeners.forEach(l -> l.onChange(val));   // 挂一个全挂
} catch (RemoteException e) {
  Log.e(TAG, "broadcast failed", e);
}
// After
listeners.forEach(l -> {
  try { l.onChange(val); }
  catch (RemoteException e) { Log.w(TAG, "callback dead", e); /* 考虑 remove */ }
});
```
