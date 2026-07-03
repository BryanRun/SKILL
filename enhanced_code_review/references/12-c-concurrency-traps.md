# 12 · C 语言并发与线程安全陷阱（QNX 底层 / 车载 MCU 固件高密度雷区）

> **本文件强制硬扫，等同 `09-cpp-concurrency-stl-traps` / `11-java-concurrency-collection-traps`，每条 C 改动 CR 必过一遍。**
>
> **权威基线**：ISO/IEC 9899:2018 (C17)，必要时回退 9899:2011 (C11) / 9899:1999 (C99)；POSIX.1-2017 (IEEE Std 1003.1-2017)；QNX Neutrino RTOS System Architecture (QNX 7.1 文档)。

---

## 为什么需要 C 并发专项？

C 语言在车载系统中广泛用于：
- **QNX 底层服务**（resource manager / device driver / PPS provider）
- **MCU 固件**（电源管理 / CAN 通信 / 传感器驱动）
- **跨语言桥接**（JNI / HIDL native 实现）

C 没有 RAII / 智能指针 / 标准容器，**手动内存管理 + 裸指针 + 全局状态** 使并发问题更隐蔽、更致命。

---

## 规则表（15 条，P0 6 条 / P1 9 条）

| 规则 ID | 一句话 | 分级 | 权威依据 |
|---------|--------|------|----------|
| **C-MUTEX-1** | `pthread_mutex_lock` 同一线程重入 → 死锁（非 RECURSIVE） | **P0** | POSIX.1 §2.9.3 |
| **C-MUTEX-2** | `pthread_mutex_unlock` 非持锁线程调用 → UB | **P0** | POSIX.1 §pthread_mutex_unlock |
| **C-RACE-1** | 非原子类型多线程读写无同步 → data race | **P0** | C11 §5.1.2.4 / ISO C17 §3.14 |
| **C-RACE-2** | `volatile` 不保证原子性，不能替代 mutex | **P0** | C11 §6.7.3 / Boehm 2005 |
| **C-LIFE-1** | 持锁期间 `free()` 锁所在结构体 → UAF | **P0** | 常识 + QNX 实战 |
| **C-LIFE-2** | 回调函数内 `free()` 回调注册者 → UAF | **P0** | 常识 + 车载实战 |
| **C-INIT-1** | 静态初始化 `PTHREAD_MUTEX_INITIALIZER` 后再 `pthread_mutex_init` → UB | **P1** | POSIX.1 §pthread_mutex_init |
| **C-INIT-2** | `pthread_mutex_destroy` 后未重新 `init` 就 `lock` → UB | **P1** | POSIX.1 §pthread_mutex_destroy |
| **C-COND-1** | `pthread_cond_wait` 不在循环中检查条件 → spurious wakeup 误判 | **P1** | POSIX.1 §pthread_cond_wait |
| **C-COND-2** | `pthread_cond_signal` / `broadcast` 不持锁调用 → lost wakeup | **P1** | Stevens APUE §11.6 |
| **C-ATOMIC-1** | C11 `_Atomic` 类型与非原子操作混用 → UB | **P1** | C11 §7.17.8 |
| **C-ATOMIC-2** | `stdatomic.h` 原子操作用错内存序（如 `relaxed` 用于锁实现） | **P1** | C11 §7.17.3 |
| **C-GLOBAL-1** | 全局变量无锁保护，多线程修改 → data race | **P1** | C11 §5.1.2.4 |
| **C-ERRNO-1** | 多线程共享 `errno` → race（应用 `errno` 是 TLS） | **P1** | POSIX.1 §2.3 |
| **C-SIGNAL-1** | 信号处理函数调用非 async-signal-safe 函数 → UB | **P1** | POSIX.1 §2.4.3 Table 2-4 |

---

## 详细规则

### C-MUTEX-1 · pthread_mutex_lock 同一线程重入 → 死锁（非 RECURSIVE）【P0】

**问题**：
`pthread_mutex_t` 默认类型是 `PTHREAD_MUTEX_DEFAULT`（QNX / Linux 实现为 `NORMAL`），**不支持递归加锁**。同一线程二次 `lock` 会死锁。

**权威依据**：
- POSIX.1-2017 §2.9.3 Thread Mutexes：
  > "If the mutex type is PTHREAD_MUTEX_NORMAL, deadlock detection shall not be provided. Attempting to relock the mutex causes deadlock."

**常见场景**：
```c
pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

void inner_func() {
    pthread_mutex_lock(&g_lock);  // 第二次加锁 → 死锁
    // ...
    pthread_mutex_unlock(&g_lock);
}

void outer_func() {
    pthread_mutex_lock(&g_lock);  // 第一次加锁
    inner_func();  // 调用链内再次加锁
    pthread_mutex_unlock(&g_lock);
}
```

**修复**：
1. **重构调用链**：拆分 `inner_func` 为 `inner_func_locked`（假设已持锁）+ `inner_func`（外部加锁）
2. **改用 RECURSIVE 锁**（不推荐，性能差且掩盖设计问题）：
   ```c
   pthread_mutexattr_t attr;
   pthread_mutexattr_init(&attr);
   pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE);
   pthread_mutex_init(&g_lock, &attr);
   ```

**检测方法**：
- grep `pthread_mutex_lock` + 人工追踪调用链，看是否有递归路径
- 动态：Helgrind / TSan 可检测

---

### C-MUTEX-2 · pthread_mutex_unlock 非持锁线程调用 → UB【P0】

**问题**：
POSIX 规定 `pthread_mutex_unlock` 必须由**持锁线程**调用。跨线程 unlock 是 UB。

**权威依据**：
- POSIX.1-2017 §pthread_mutex_unlock：
  > "If a thread attempts to unlock a mutex that it has not locked or a mutex which is unlocked, undefined behavior results."

**常见场景**：
```c
// 线程 A
pthread_mutex_lock(&g_lock);
send_message_to_thread_b();  // 期望线程 B 解锁

// 线程 B
pthread_mutex_unlock(&g_lock);  // UB！
```

**修复**：
改用条件变量 `pthread_cond_t` 或信号量 `sem_t` 做跨线程同步。

---

### C-RACE-1 · 非原子类型多线程读写无同步 → data race【P0】

**问题**：
C11 §5.1.2.4 定义 **data race**：两个线程访问同一内存位置，至少一个是写，且无 happens-before 关系 → UB。

**权威依据**：
- ISO/IEC 9899:2018 (C17) §3.14 data race：
  > "The execution of a program contains a data race if it contains two conflicting actions in different threads, at least one of which is not atomic, and neither happens before the other."

**常见场景**：
```c
int g_counter = 0;  // 非原子

// 线程 A
g_counter++;  // read-modify-write，非原子

// 线程 B
g_counter++;  // data race
```

**修复**：
1. **加锁**：
   ```c
   pthread_mutex_lock(&g_lock);
   g_counter++;
   pthread_mutex_unlock(&g_lock);
   ```
2. **C11 原子类型**（需编译器支持 `-std=c11`）：
   ```c
   #include <stdatomic.h>
   _Atomic int g_counter = 0;
   atomic_fetch_add(&g_counter, 1);
   ```

---

### C-RACE-2 · volatile 不保证原子性，不能替代 mutex【P0】

**问题**：
`volatile` 只保证**不优化掉读写**，不保证**原子性**和**内存序**。多线程共享变量用 `volatile` 无法避免 data race。

**权威依据**：
- C11 §6.7.3 Type qualifiers：
  > "`volatile` is a hint to the implementation to avoid aggressive optimization involving the object because the value of the object might be changed by means undetectable by an implementation."
- Hans Boehm, "Threads Cannot be Implemented as a Library" (2005)：
  > "`volatile` does not provide atomicity or memory ordering guarantees required for multithreading."

**常见误用**：
```c
volatile int g_flag = 0;

// 线程 A
g_flag = 1;  // 以为线程 B 能立即看到

// 线程 B
while (g_flag == 0);  // 可能永远循环（编译器/CPU 重排序）
```

**修复**：
```c
#include <stdatomic.h>
_Atomic int g_flag = 0;

// 线程 A
atomic_store(&g_flag, 1);

// 线程 B
while (atomic_load(&g_flag) == 0);
```

---

### C-LIFE-1 · 持锁期间 free() 锁所在结构体 → UAF【P0】

**问题**：
与 C++ 的 `C-LIFE-1` 类似，但 C 没有析构函数，更容易误写。

**常见场景**：
```c
typedef struct {
    pthread_mutex_t lock;
    int data;
} MyStruct;

void destroy(MyStruct *s) {
    pthread_mutex_lock(&s->lock);
    // ... 清理 data
    free(s);  // UAF！unlock 会访问已释放内存
    pthread_mutex_unlock(&s->lock);  // 崩溃
}
```

**修复**：
```c
void destroy(MyStruct *s) {
    pthread_mutex_lock(&s->lock);
    // ... 清理 data
    pthread_mutex_unlock(&s->lock);  // 先解锁
    pthread_mutex_destroy(&s->lock);  // 销毁锁
    free(s);  // 最后释放
}
```

---

### C-LIFE-2 · 回调函数内 free() 回调注册者 → UAF【P0】

**问题**：
回调函数（如定时器回调、事件回调）内释放注册者对象，回调返回后访问该对象 → UAF。

**常见场景**：
```c
typedef struct {
    timer_t timer_id;
    void (*callback)(void*);
} Timer;

void timer_callback(union sigval sv) {
    Timer *t = (Timer*)sv.sival_ptr;
    // ... 处理超时
    free(t);  // 释放 Timer 对象
}  // 返回后，系统可能访问 t->timer_id → UAF

void start_timer(Timer *t) {
    struct sigevent sev = {0};
    sev.sigev_notify = SIGEV_THREAD;
    sev.sigev_notify_function = timer_callback;
    sev.sigev_value.sival_ptr = t;
    timer_create(CLOCK_REALTIME, &sev, &t->timer_id);
}
```

**修复**：
1. **回调内只标记删除**，外部轮询清理：
   ```c
   t->pending_delete = true;
   ```
2. **引用计数**：回调持有引用，返回后减引用，外部也持有引用。

---

### C-INIT-1 · 静态初始化后再 pthread_mutex_init → UB【P1】

**问题**：
`PTHREAD_MUTEX_INITIALIZER` 已完成静态初始化，再调用 `pthread_mutex_init` 是 UB。

**权威依据**：
- POSIX.1-2017 §pthread_mutex_init：
  > "Attempting to initialize an already initialized mutex results in undefined behavior."

**常见误用**：
```c
pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

void init() {
    pthread_mutex_init(&g_lock, NULL);  // UB！
}
```

**修复**：
二选一：
1. 只用静态初始化：`pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;`
2. 只用动态初始化：`pthread_mutex_t g_lock; pthread_mutex_init(&g_lock, NULL);`

---

### C-INIT-2 · pthread_mutex_destroy 后未重新 init 就 lock → UB【P1】

**问题**：
`pthread_mutex_destroy` 后，mutex 处于未初始化状态，必须重新 `init` 才能使用。

**权威依据**：
- POSIX.1-2017 §pthread_mutex_destroy：
  > "A destroyed mutex object can be reinitialized using pthread_mutex_init(); the results of otherwise referencing the object after it has been destroyed are undefined."

---

### C-COND-1 · pthread_cond_wait 不在循环中检查条件 → spurious wakeup 误判【P1】

**问题**：
`pthread_cond_wait` 可能**虚假唤醒**（spurious wakeup），必须在循环中重新检查条件。

**权威依据**：
- POSIX.1-2017 §pthread_cond_wait：
  > "When using condition variables there is always a Boolean predicate involving shared variables associated with each condition wait that is true if the thread should proceed. Spurious wakeups from the pthread_cond_wait() or pthread_cond_timedwait() functions may occur. Since the return from pthread_cond_wait() or pthread_cond_timedwait() does not imply anything about the value of this predicate, the predicate should be re-evaluated upon such return."

**常见误用**：
```c
pthread_mutex_lock(&lock);
if (queue_empty) {
    pthread_cond_wait(&cond, &lock);  // 唤醒后不检查
}
process_queue();  // 可能队列仍为空
pthread_mutex_unlock(&lock);
```

**修复**：
```c
pthread_mutex_lock(&lock);
while (queue_empty) {  // 循环检查
    pthread_cond_wait(&cond, &lock);
}
process_queue();
pthread_mutex_unlock(&lock);
```

---

### C-COND-2 · pthread_cond_signal/broadcast 不持锁调用 → lost wakeup【P1】

**问题**：
虽然 POSIX 允许不持锁调用 `pthread_cond_signal`，但**最佳实践是持锁调用**，避免 lost wakeup。

**权威依据**：
- W. Richard Stevens, *Advanced Programming in the UNIX Environment* (APUE) §11.6：
  > "It is recommended that the mutex be locked when calling pthread_cond_signal or pthread_cond_broadcast to avoid lost wakeup problems."

**场景**：
```c
// 生产者（不持锁）
queue_push(item);
pthread_cond_signal(&cond);  // 可能在消费者检查条件和 wait 之间发出 → lost

// 消费者
pthread_mutex_lock(&lock);
while (queue_empty) {
    pthread_cond_wait(&cond, &lock);  // 可能永远等待
}
pthread_mutex_unlock(&lock);
```

**修复**：
```c
// 生产者
pthread_mutex_lock(&lock);
queue_push(item);
pthread_cond_signal(&cond);
pthread_mutex_unlock(&lock);
```

---

### C-ATOMIC-1 · C11 _Atomic 类型与非原子操作混用 → UB【P1】

**问题**：
`_Atomic` 类型必须用 `<stdatomic.h>` 的原子操作访问，不能直接 `=` 赋值（除初始化）。

**权威依据**：
- C11 §7.17.8 Atomic flag type and operations：
  > "Operations on atomic objects are performed using the functions and macros defined in <stdatomic.h>."

**常见误用**：
```c
#include <stdatomic.h>
_Atomic int counter = 0;

counter = 10;  // UB！应用 atomic_store
int val = counter;  // UB！应用 atomic_load
```

**修复**：
```c
atomic_store(&counter, 10);
int val = atomic_load(&counter);
```

---

### C-ATOMIC-2 · stdatomic.h 原子操作用错内存序【P1】

**问题**：
C11 原子操作支持 6 种内存序（`memory_order_relaxed` / `acquire` / `release` / `acq_rel` / `seq_cst` / `consume`），用错会导致可见性问题。

**权威依据**：
- C11 §7.17.3 Order and consistency：
  > "The enumeration memory_order specifies the detailed regular (non-atomic) memory synchronization order as defined in 5.1.2.4 and may provide for operation ordering."

**常见误用**：
```c
// 自旋锁实现用 relaxed → 错误
while (atomic_exchange_explicit(&lock, 1, memory_order_relaxed) == 1);
```

**修复**：
```c
// 自旋锁必须用 acquire
while (atomic_exchange_explicit(&lock, 1, memory_order_acquire) == 1);
// 解锁用 release
atomic_store_explicit(&lock, 0, memory_order_release);
```

---

### C-GLOBAL-1 · 全局变量无锁保护，多线程修改 → data race【P1】

**问题**：
全局变量默认所有线程可见，多线程修改必须加锁或用原子操作。

**常见误用**：
```c
int g_state = 0;  // 全局

// 线程 A
g_state = 1;

// 线程 B
if (g_state == 1) { ... }  // data race
```

**修复**：
```c
pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
int g_state = 0;

// 线程 A
pthread_mutex_lock(&g_lock);
g_state = 1;
pthread_mutex_unlock(&g_lock);

// 线程 B
pthread_mutex_lock(&g_lock);
if (g_state == 1) { ... }
pthread_mutex_unlock(&g_lock);
```

---

### C-ERRNO-1 · 多线程共享 errno → race【P1】

**问题**：
历史上 `errno` 是全局变量，POSIX 要求现代实现将其改为 **TLS**（Thread-Local Storage）。但仍需注意：
- 跨线程传递 `errno` 值无意义
- 信号处理函数可能修改 `errno`

**权威依据**：
- POSIX.1-2017 §2.3 Error Numbers：
  > "For each thread of execution, the value of errno shall not be affected by function calls or assignments to errno by other threads."

**常见误用**：
```c
// 线程 A
if (read(fd, buf, size) < 0) {
    send_errno_to_thread_b(errno);  // 可能被信号处理函数改写
}
```

**修复**：
```c
int saved_errno = errno;  // 立即保存
send_errno_to_thread_b(saved_errno);
```

---

### C-SIGNAL-1 · 信号处理函数调用非 async-signal-safe 函数 → UB【P1】

**问题**：
信号处理函数只能调用 **async-signal-safe** 函数（POSIX.1 Table 2-4 列出约 120 个）。调用 `malloc` / `printf` / `pthread_mutex_lock` 等 → UB。

**权威依据**：
- POSIX.1-2017 §2.4.3 Signal Actions, Table 2-4：
  > "The following table defines a set of functions that shall be async-signal-safe. Therefore, applications can call them, without restriction, from signal-catching functions."

**常见误用**：
```c
void signal_handler(int sig) {
    printf("Received signal %d\n", sig);  // UB！printf 非 async-signal-safe
    pthread_mutex_lock(&g_lock);  // UB！
}
```

**修复**：
1. **只设置标志位**（原子变量）：
   ```c
   volatile sig_atomic_t g_signal_received = 0;
   void signal_handler(int sig) {
       g_signal_received = 1;  // sig_atomic_t 保证原子写
   }
   ```
2. **主循环轮询标志位**，在安全上下文处理。

---

## 强制 cover 条款（C 改动时）

C 改动的 CR，cover 必须包含以下表格（即使全选"✅无"）：

```markdown
### C 并发与线程安全专项扫描

| 规则 ID | 检查项 | 结果 |
|---------|--------|------|
| C-MUTEX-1 | pthread_mutex_lock 递归加锁 | ✅无 / ⚠️发现 |
| C-MUTEX-2 | pthread_mutex_unlock 跨线程调用 | ✅无 / ⚠️发现 |
| C-RACE-1 | 非原子类型多线程读写无同步 | ✅无 / ⚠️发现 |
| C-RACE-2 | volatile 替代 mutex | ✅无 / ⚠️发现 |
| C-LIFE-1 | 持锁期间 free 锁所在结构体 | ✅无 / ⚠️发现 |
| C-LIFE-2 | 回调内 free 回调注册者 | ✅无 / ⚠️发现 |
| C-INIT-1 | 静态初始化后再 pthread_mutex_init | ✅无 / ⚠️发现 |
| C-INIT-2 | pthread_mutex_destroy 后未 init 就 lock | ✅无 / ⚠️发现 |
| C-COND-1 | pthread_cond_wait 不在循环中检查 | ✅无 / ⚠️发现 |
| C-COND-2 | pthread_cond_signal 不持锁调用 | ✅无 / ⚠️发现 |
| C-ATOMIC-1 | _Atomic 类型与非原子操作混用 | ✅无 / ⚠️发现 |
| C-ATOMIC-2 | stdatomic.h 原子操作用错内存序 | ✅无 / ⚠️发现 |
| C-GLOBAL-1 | 全局变量无锁保护多线程修改 | ✅无 / ⚠️发现 |
| C-ERRNO-1 | 多线程共享 errno | ✅无 / ⚠️发现 |
| C-SIGNAL-1 | 信号处理函数调用非 async-signal-safe 函数 | ✅无 / ⚠️发现 |
```

---

## 检测工具

- **静态分析**：Clang Static Analyzer / Coverity / Cppcheck（部分支持）
- **动态分析**：Helgrind / ThreadSanitizer (TSan) / Valgrind DRD
- **QNX 专用**：QNX Momentics IDE 的 Memory Analysis 工具

---

## 参考文献

1. ISO/IEC 9899:2018 (C17) — C 语言标准
2. POSIX.1-2017 (IEEE Std 1003.1-2017) — POSIX 线程 API
3. W. Richard Stevens, *Advanced Programming in the UNIX Environment* (APUE), 3rd Edition
4. Hans Boehm, "Threads Cannot be Implemented as a Library", PLDI 2005
5. QNX Neutrino RTOS System Architecture, QNX Software Systems, 2021
6. David R. Butenhof, *Programming with POSIX Threads*, Addison-Wesley, 1997

---

**最后更新**：2026-05-01（v2.4.0）
