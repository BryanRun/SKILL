# 11 · Java 并发与集合线程安全陷阱（车载 Android Framework / Service 高密度雷区）

> **本文件强制硬扫，等同 `09-cpp-concurrency-stl-traps`，每条 Java/Kotlin 改动 CR 必过一遍。**
>
> **权威基线**：The Java® Language Specification, Java SE 21 Edition (JLS 21)；The Java® Virtual Machine Specification, Java SE 21；JDK 21 API 文档；JEP 261 / 396 / 403（强封装内部 API）。
>
> 来源：2026-04-30 整理《Java 并发与集合安全规则集 v1.0》；CarPropertyManager / CarService / VehicleHAL 团队真实问题沉淀。
>
> **跨语言对应**：C++ → `09-cpp-concurrency-stl-traps.md`；C → `12-c-concurrency-stdlib-traps.md`。

---

## 适用范围

- 所有 Java / Kotlin 改动（`.java` / `.kt`）
- Android Framework / CarService / Vehicle HAL Java Wrapper / VHAL Manager
- AIDL Stub / Binder Service / 跨进程 Listener
- **测试代码同样适用**（CTS / Robolectric / Mockito 并发测试）

---

## 12 条规则（每条 CR 必扫，扫不到要在 cover 写"已扫，无发现"）

> **前 9 条为硬规则（P0/P1），后 3 条为扩展规则（P1，建议扫但不强制）。**

### **J-CONC-1（P0） · `StampedLock` / 非可重入锁的"持锁再加锁"自死锁**

| 项 | 内容 |
|---|---|
| 触发 | 持有 `StampedLock.writeLock()` 期间调用同一锁的 `writeLock()` / `readLock()`；或 `synchronized(this)` 持有期内通过虚函数/回调反向取同一锁 |
| 典型反例 | `long s = sl.writeLock(); try { update(); /* update() 内部又 sl.writeLock() */ } finally { sl.unlockWrite(s); }` |
| 证据 | `StampedLock` JavaDoc：**"is not reentrant, so locked bodies should not call other unknown methods that may try to re-acquire locks."** |
| 修复 | ① 用 `ReentrantReadWriteLock`（可重入）；② 持锁内禁止调用未知方法/虚函数/回调；③ 分离 "_locked" 私有方法供持锁方调用 |
| 扫描提示 | grep `StampedLock` / `tryOptimisticRead` / `synchronized\s*\(this\)` 后函数体内的方法调用追踪 |

### **J-CONC-2（P0） · 集合视图（keySet/entrySet/values）逃出锁外**

| 项 | 内容 |
|---|---|
| 触发 | `synchronized` 方法返回 `Map.entrySet()` / `keySet()` / `values()` 给外部调用方，且调用方在锁外迭代 |
| 典型反例 | `public synchronized Set<Integer> getKeys() { return cache.keySet(); }`——外部 `for (k : keys)` 时另一线程 `cache.put` → CME |
| 证据 | `HashMap` JavaDoc：**"The iterators returned by all of this class's collection view methods are fail-fast: if the map is structurally modified at any time after the iterator is created ... the iterator will throw a ConcurrentModificationException."** |
| 修复 | ① 返回 `Set.copyOf(cache.keySet())`（不可变拷贝）；② 改用 `ConcurrentHashMap`（weakly consistent iterator）；③ 在锁内执行回调（`forEach((k,v)->...)`） |
| 反模式 | `Collections.synchronizedMap` 返回的视图迭代仍需 `synchronized(map) { for (...) }`，单纯 `synchronizedMap` 不解决迭代竞态 |

### **J-CONC-3（P0） · `containsKey`-then-`put` 非原子模式**

| 项 | 内容 |
|---|---|
| 触发 | `if (!map.containsKey(k)) map.put(k, expensiveCompute());`——两步之间并发 put 导致重复计算或覆盖 |
| 典型反例 | `synchronized (cache) { if (!cache.containsKey(k)) cache.put(k, load(k)); }` 看似有锁，但 `load(k)` 是耗时 IO，其他线程 ConcurrentHashMap 路径已绕过 |
| 证据 | `ConcurrentHashMap.computeIfAbsent` JavaDoc：**"The entire method invocation is performed atomically..."**——只有 `computeIfAbsent` 是原子 upsert |
| 修复 | ① `map.computeIfAbsent(k, x -> expensiveCompute());`；② `Map.putIfAbsent(k, v)`（v 已存在时返）；③ `merge(k, v, BiFunction)` 用于累加场景 |
| 衍生 | `HashMap.computeIfAbsent` **非线程安全**——只有 `ConcurrentHashMap` 的 `computeIfAbsent` 才是原子 |

### **J-CONC-4（P0） · `Comparator` 含可变状态 / 与 `equals` 不一致**

| 项 | 内容 |
|---|---|
| 触发 | `TreeMap` / `TreeSet` / `Collections.sort` 使用的 `Comparator` 含 `static int counter`、随机数、读外部状态；或 `compareTo` 与 `equals` 不一致（`a.compareTo(b)==0` 但 `!a.equals(b)`） |
| 典型反例 | `Comparator<Item> cmp = (a, b) -> { count++; return a.id - b.id; };`——并发排序行为不可预测 |
| 证据 | `TreeMap` JavaDoc：**"The behavior of a sorted map is well-defined even if its ordering is inconsistent with equals; it just fails to obey the general contract of the Map interface."**；`Comparable` JavaDoc：**"It is strongly recommended that natural orderings be consistent with equals."** |
| 修复 | ① 纯函数 Comparator，无状态；② 用 `Comparator.comparing(Item::getId)` 链式；③ 修正 `compareTo` 使其与 `equals` 一致（**`a.compareTo(b)==0` ⇔ `a.equals(b)`**） |

### **J-CONC-5（P0） · `ReadWriteLock` 读锁升级写锁**

| 项 | 内容 |
|---|---|
| 触发 | 同一线程在持有 `ReentrantReadWriteLock.readLock()` 时直接 `writeLock().lock()`——必死锁 |
| 典型反例 | `rwl.readLock().lock(); if (need) rwl.writeLock().lock();` |
| 证据 | `ReentrantReadWriteLock` JavaDoc：**"...upgrading from a read lock to the write lock is not possible."**（写锁可降级为读锁，但读锁不可升级为写锁） |
| 修复 | ① 先 `readLock().unlock()`，再 `writeLock().lock()`，**重新校验前置条件**；② 直接用写锁（如果写很频繁）；③ 用 `StampedLock.tryConvertToWriteLock(stamp)` 配合乐观读 |

### **J-STD-1（P1） · 向 `java.*` / `javax.*` / `sun.*` 包注入类**

| 项 | 内容 |
|---|---|
| 触发 | 用户代码 `package java.util; class MyHack { ... }`；JPMS 强封装下 JDK 16+ 直接 `SecurityException` |
| 证据 | JEP 396（JDK 16）/ JEP 403（JDK 17）：**"Strongly encapsulate all internal elements of the JDK by default..."** |
| 修复 | ① 改用 `com.yourcompany.*` 包；② 不要绕过模块边界访问 JDK 内部 |

### **J-STD-2（P1） · 依赖 `sun.misc.Unsafe` / `com.sun.*` 内部 API**

| 项 | 内容 |
|---|---|
| 触发 | `import sun.misc.Unsafe;` / `Unsafe.compareAndSwapInt(...)` / `com.sun.tools.javac.*`；JDK 17+ 需 `--add-opens` 才可反射访问 |
| 证据 | JEP 260 / 396 / 403——`Unsafe` 之外的内部 API 在 JDK 17 起完全封装，未来版本不保证可用 |
| 修复 | ① `VarHandle`（JEP 193）替代 `Unsafe.compareAndSwap*`；② `MethodHandles.Lookup` 替代深度反射；③ `AtomicReferenceFieldUpdater` 替代字段级 CAS |

### **J-LIFE-1（P1） · `synchronized` 块/锁内关闭锁所属资源**

| 项 | 内容 |
|---|---|
| 触发 | `synchronized (conn) { conn.close(); }`——其他等待 conn 锁的线程进入后访问已关闭对象；或 `lock.lock(); try { ... lock.unlock(); ... } finally { lock.unlock(); /* 再次 unlock UB */ }` |
| 证据 | JLS 21 §17.1 "Synchronization"；`AutoCloseable.close()` JavaDoc：**"Calling close more than once may have visible side effects..."** |
| 修复 | ① 锁外执行 close；② try-with-resources 包外，锁仅保护状态变更；③ 标记关闭位 `closed=true` 让等待者退出 |

### **J-LIFE-2（P1） · 集合迭代时通过容器自身（非 Iterator.remove）修改结构**

| 项 | 内容 |
|---|---|
| 触发 | `for (Item it : list) if (it.expired()) list.remove(it);` 抛 `ConcurrentModificationException`；或多线程并发结构性修改非线程安全集合 |
| 证据 | `AbstractList` 实现 / JLS 21 §14.14.2 "Enhanced for"；`ConcurrentModificationException` JavaDoc：**"...detected by methods that have detected concurrent modification of an object when such modification is not permissible."** |
| 修复 | ① `list.removeIf(Item::expired)` (Java 8+)；② `Iterator.remove()`；③ 切到 `CopyOnWriteArrayList`（写极少读多）；④ 收集待删项到本地 list 循环外删 |

---

### **J-LIFE-3（P1，扩展） · `final` / `volatile` 字段发布安全**

| 项 | 内容 |
|---|---|
| 触发 | DCL（Double-Checked Locking）单例不写 `volatile`；构造器中泄漏 `this` 引用；非 final 字段在构造完成前被其他线程读到（部分构造对象） |
| 典型反例 | `private static Singleton instance; public static Singleton get() { if (instance == null) { synchronized(...) { if (instance == null) instance = new Singleton(); } } return instance; }`——instance 不写 volatile，其他线程可能读到部分构造的对象 |
| 证据 | JLS 21 §17.5 "final Field Semantics"：**"A thread that can only see a reference to an object after that object has been completely initialized is guaranteed to see the correctly initialized values for that object's final fields."**；JLS 21 §17.4.4 "Synchronization Order" |
| 修复 | ① 单例字段加 `volatile`；② 用 holder class 模式（`static class Holder { static final Singleton INST = new Singleton(); }`）；③ 用 `enum` 单例（JVM 保证）；④ 关键不可变字段一律 `final` |

### **J-CONC-6（P1，扩展） · `ThreadLocal` 在线程池/虚拟线程中的内存泄漏**

| 项 | 内容 |
|---|---|
| 触发 | `ExecutorService` / `ThreadPoolExecutor` / 虚拟线程（JEP 444）中使用 `ThreadLocal` 但不在任务结束时 `remove()` |
| 证据 | `ThreadLocal` JavaDoc：**"Code that uses ThreadLocal in a thread pool may leak memory if it doesn't call remove()."**；JEP 425 / 444 Best Practices |
| 修复 | ① `try { tl.set(v); doWork(); } finally { tl.remove(); }`；② 改用 `ScopedValue`（JDK 21+ 预览）；③ 评估是否真需要 ThreadLocal（很多场景可改方法参数） |

### **J-CONC-7（P1，扩展） · `Stream.parallel()` 并行流的副作用与有状态 lambda**

| 项 | 内容 |
|---|---|
| 触发 | `stream.parallel().forEach(x -> sharedList.add(x))`——`sharedList` 非线程安全；或 lambda 含可变状态 / 顺序敏感操作 |
| 证据 | `java.util.stream` Package Summary "Stream operations and parallelism" / "Statelessness" |
| 修复 | ① 用 `Collectors.toConcurrentMap` / `toList` 替代手动累加；② lambda 必须无状态、无副作用；③ 顺序敏感场景禁用 `parallel`，或换用 `forEachOrdered` |

---

## LLM 评审 prompt 接入条款（必须复制进 08）

> 以下条款被 `08-llm-review-prompt.md` 引用，作为 Step 4.5 多语言并发专项扫的 Java 分支硬约束。

### Step 4.5 (Java) · Java 并发与集合专项（Java/Kotlin 改动必跑）

按 11 文件 12 条规则**逐条 grep + 上下文确认**：

| 规则 | 主关键词 grep | 必须人工确认 |
|---|---|---|
| J-CONC-1 | `StampedLock` / `synchronized\s*\(this\)` 后调用方法 | 持锁体内是否调用未知方法/虚函数/回调 |
| J-CONC-2 | `\.keySet\(\)\|\.entrySet\(\)\|\.values\(\)` 在 `synchronized` 方法内返回 | 视图是否逃出锁外被迭代 |
| J-CONC-3 | `containsKey.*?put\|get\(.*?\)\s*==\s*null.*?put` | 是否未用 `computeIfAbsent` / `putIfAbsent` |
| J-CONC-4 | `Comparator\|Comparable\|compareTo` 实现 | 是否含可变状态、与 equals 不一致 |
| J-CONC-5 | `readLock\(\)\.lock` 后 `writeLock\(\)\.lock` 同函数 | 是否同线程读锁升写锁 |
| J-STD-1 | `package\s+(java\|javax\|sun\|com\.sun)\.` | 是否注入受保护包 |
| J-STD-2 | `import\s+(sun\.misc\.Unsafe\|com\.sun\.tools\.)` | 是否使用 JDK 内部 API |
| J-LIFE-1 | `synchronized.*?\{.*?\.close\(\)` | 是否锁内 close 锁所属资源 |
| J-LIFE-2 | `for\s*\(.*?:.*?\)\s*\{.*?\.remove\(` | 是否容器自身 remove 而非 Iterator.remove |
| J-LIFE-3 | DCL pattern：`if\s*\(\s*instance\s*==\s*null\s*\)` 后 `synchronized` | 是否字段未 `volatile` |
| J-CONC-6 | `ThreadLocal<.*?>\s+\w+` | 线程池上下文是否调 `remove()` |
| J-CONC-7 | `\.parallel\(\)` / `parallelStream` | lambda 是否无状态、无副作用 |

### 强制 cover 条款

Java/Kotlin 改动的 cover **必含**以下专项段（即使 0 发现也要写）：

```markdown
### Java 并发与集合专项扫描（references/11）

| 规则 | 扫描结果 |
|---|---|
| J-CONC-1 StampedLock 自死锁 | ✅ 无 / ⚠️ N 处 |
| J-CONC-2 集合视图逃出锁外 | ✅ 无 / ⚠️ N 处 |
| J-CONC-3 containsKey-then-put | ✅ 无 / ⚠️ N 处 |
| J-CONC-4 Comparator 不一致 | ✅ 无 / ⚠️ N 处 |
| J-CONC-5 读锁升写锁 | ✅ 无 / ⚠️ N 处 |
| J-STD-1 java.* 包注入 | ✅ 无 / ⚠️ N 处 |
| J-STD-2 sun.misc/com.sun 依赖 | ✅ 无 / ⚠️ N 处 |
| J-LIFE-1 锁内 close | ✅ 无 / ⚠️ N 处 |
| J-LIFE-2 集合迭代修改 | ✅ 无 / ⚠️ N 处 |
| J-LIFE-3 DCL/final 发布安全 | ✅ 无 / ⚠️ N 处 |
| J-CONC-6 ThreadLocal 泄漏 | ✅ 无 / ⚠️ N 处 |
| J-CONC-7 parallel 副作用 | ✅ 无 / ⚠️ N 处 |
```

### 评分映射

- J-CONC-1 / J-CONC-2 / J-CONC-3 / J-CONC-4 / J-CONC-5 → **P0 → -1**
- J-STD-1 / J-STD-2 / J-LIFE-1 / J-LIFE-2 → **P1 → 0 或 -1**
- J-LIFE-3 / J-CONC-6 / J-CONC-7 → **P1 → 0 或 -1**（取决于是否在调用链上真触发）

### 「历史代码也算」例外

本文件 12 条**任一命中即报告**，**不区分**新写代码 vs 历史代码——理由：
- Java 并发问题（CME / DCL 部分构造 / Stream 副作用）在调用面扩散后修复成本指数上升
- 与 `gerrit_cron_review.py` 的"历史代码 P0 降级 P2"规则**冲突时本规则优先**

---

## 检测工具映射（便于 CI 集成）

| 规则 | SpotBugs | SonarQube | ErrorProne | 自研扫描 |
|---|---|---|---|---|
| J-CONC-1 | JLM_JSR166_LOCK_MONITORENTER | — | LockNotBeforeTry | StampedLock 调用图 |
| J-CONC-2 | IS_FIELD_NOT_GUARDED | S2885 | GuardedBy ✅ | — |
| J-CONC-3 | AT_OPERATION_SEQUENCE_ON_CONCURRENT_ABSTRACTION ✅ | S6213 | JdkObsolete | grep containsKey + put |
| J-CONC-5 | — | — | — | 自研 upgrade detection |
| J-STD-1 | — | S1118 (utility) | — | 包名扫描 |
| J-STD-2 | — | S2974 | Java8ApiChecker | grep sun.misc |
| J-LIFE-1 | OS_OPEN_STREAM ✅ | S2095 | MustBeClosedChecker | — |
| J-LIFE-2 | — | S2250 | CollectionIncompatibleType | — |
| J-LIFE-3 | LI_LAZY_INIT_UPDATE_STATIC ✅ | S2168 (DCL) | DoubleCheckedLocking | — |
| J-CONC-6 | — | S5164 ✅ | ThreadLocalUsage | — |

---

**版本**：v1.0 / 2026-05-01
**整理者**：志强的her（基于《Java 并发与集合安全规则集 v1.0》整合）
**复审周期**：每季度对照 JLS / OpenJDK API 文档更新
