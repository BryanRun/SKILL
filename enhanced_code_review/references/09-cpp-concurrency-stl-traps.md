# 09 · C++ 并发与 STL 容器线程安全陷阱（车载中间件高密度雷区）

> **本文件强制硬扫，等同 `02-security` / `06-automotive` 优先级，每条 CR 必过一遍。**
>
> **权威基线**：ISO/IEC 14882:2020 (C++20)，必要时回退 14882:2017 (C++17) / 14882:2023 (C++23)。
>
> 来源：2026-04-29 CR 1003290 评审复盘——LLM 漏掉 4 P0 + 2 P1 后回灌团队记忆；2026-04-30 整合《C++ 并发与 STL 安全规则集 v1.0》。
> 所有规则均**至少一条**经过真实生产代码或团队 -1 评审验证，不是教科书空谈。
>
> **跨语言对应**：Java → `11-java-concurrency-collection-traps.md`；C → `12-c-concurrency-stdlib-traps.md`。

---

## 适用范围

- 所有 C++ 改动（.h / .hpp / .cpp / .cc / .cxx）
- 所有"并发容器"/"RAII 封装"/"自研锁"/"模板特化标准库类型"代码
- QNX 平台（Resource Manager、Pulse、PPS、消息分发回调链）
- Android Native 平台（HAL / native service）
- **测试代码同样适用**（test 目录里的并发问题会污染 CI 矩阵）

---

## 12 条规则（每条 CR 必扫，扫不到要在 cover 写"已扫，无发现"）

> **前 9 条为硬规则（P0/P1），后 3 条为扩展规则（P1，建议扫但不强制）。**

### **C-CONC-1（P0） · 不可重入互斥的"持锁再加锁"自死锁**

| 项 | 内容 |
|---|---|
| 触发 | 已对 `std::mutex` / `std::shared_mutex` / `std::recursive_mutex` 之外的互斥持锁的函数体内，**直接或间接**再调用任何**会自己加同一把锁**的接口 |
| 典型反例 | `bool operator==(const safe_queue& other) { lock_guard l(m_); return size() == other.size(); }`——`size()` 内部又对同一把 `m_` 加锁 → 必死锁 |
| 证据 | C++ Standard `[thread.mutex.requirements.mutex]` ——`std::mutex` / `std::shared_mutex` 重入 = UB；只有 `std::recursive_mutex` 允许同线程重入 |
| 修复 | ① 提供 `_unlocked` 私有版本供持锁方法复用；② 改 `recursive_mutex`（性能差，慎用）；③ 重新组织调用关系，先 unlock 再调对外接口 |
| 扫描提示 | grep 所有 `lock_guard` / `unique_lock` / `shared_lock` / `lock_(.*?)` 持锁块体内的**方法调用**，对每个调用追踪是否再加同一把锁 |

### **C-CONC-2（P0） · 标准容器 API 当线程安全 API 暴露**

| 项 | 内容 |
|---|---|
| 触发 | 自研"线程安全容器"把 `begin() / end() / find() / lower_bound() / iterator` 等**返回迭代器/引用**的接口直接暴露，且只在函数体内持锁，**返回前已 unlock** |
| 典型反例 | `iterator begin() { lock_guard l(m_); return map_.begin(); }`——调用方 `*it` 时锁已释放，并发写入立刻 UB |
| 证据 | C++ Standard `[container.requirements.dataraces]`——容器迭代器/引用在容器被 modifying operation 后失效；线程安全容器**禁止**返回未锁定的迭代器 |
| 修复 | ① 不暴露迭代器；②  改 `for_each(callback)` 形式，回调在持锁内执行（注意回调里也不能再加锁，见 C-CONC-1）；③ `snapshot()` 返回**值拷贝** |
| 反模式 | TBB / oneAPI / Intel TBB 的 `concurrent_hash_map` 永远返回 `accessor` 持锁对象，不返回裸 iterator——这是正确范式 |

### **C-CONC-3（P0） · `std::map::insert` / `unordered_map::insert` 的"已存在则 no-op"陷阱**

| 项 | 内容 |
|---|---|
| 触发 | 自研 `replace(key, value)` / `set(key, value)` / `update(key, value)` 实现里使用 `m_.insert({key, value})` 或 `m_.insert(value_type(key, value))` 试图替换 |
| 典型反例 | `void replace(K k, V v) { auto it = m_.find(k); if (it != m_.end()) { m_.insert({k, v}); /* ← no-op */ } }`——已存在 key 时 `insert` **不替换、不报错、静默失败** |
| 证据 | `[map.modifiers]`——`insert` 对 equivalent key 是 no-op；`[unord.map.modifiers]` 同；C++17 引入 `insert_or_assign` 才是真正的 upsert |
| 修复 | ① C++17：`m_.insert_or_assign(k, v)`；② C++14：`m_[k] = v` 或 `it->second = v`；③ 显式 `m_.erase(k); m_.insert({k, v})` |
| 衍生 | `emplace` 同样行为；`try_emplace`（C++17）也是 no-op-on-exist |

### **C-CONC-4（P0） · 模板嵌套类型当函数返回 / 参数，无默认构造则 ODR 失败**

| 项 | 内容 |
|---|---|
| 触发 | 实现 `value_compare value_comp() { return map_.value_compare(); }` 之类——`std::map::value_compare` 是**类型**且其构造函数是 **private**（仅 `std::map` 自己可造） |
| 典型反例 | `value_compare value_comp() const { return value_compare(); }`——调用 `value_compare()` 是默认构造，但该类型**没有 public 默认构造函数**，模板实例化触达即 hard error |
| 证据 | `[associative.reqmts]`——`value_compare` 是 exposition-only 嵌套类型，公开接口是 `key_comp()` 返回的 Key 比较器；不是供用户构造的 |
| 修复 | ① 改返回 `key_compare key_comp() const { return m_.key_comp(); }`（这是 public）；② 移除该接口（YAGNI，外部基本用不到）；③ 实在要 value_comp，需要自己构造一个等价 functor |
| 衍生 | `std::set::value_compare`（== `key_compare`）OK；`std::map::value_compare` 不 OK；`std::multimap::value_compare` 不 OK |

### **C-STD-1（P1） · `namespace std` 注入新类型 / 函数 = UB**

| 项 | 内容 |
|---|---|
| 触发 | 在自己头文件中 `namespace std { template<...> class unique_ptr {...}; }` 或 `namespace std { void some_func(...); }` |
| 典型反例 | `namespace std { template<class T> class unique_ptr { ... }; }`——意图给老编译器补 polyfill |
| 证据 | C++ Standard `[namespace.std]/1` 明文：**只允许特化模板**（`template<> struct hash<MyType> {}` 这种），**禁止注入新类**或函数；违反即 UB |
| 修复 | ① 放进自有 namespace（如 `AutoLink::compat::unique_ptr`）；② 用 `using std::unique_ptr;` 别名；③ 升级编译器（C++11 起 `unique_ptr` 已在标准里） |
| 例外 | 用户类型的 `std::hash` / `std::less` 等已知模板的**特化**是允许的（必须 partial/full specialization） |

### **C-STD-2（P1） · 依赖标准库实现内部符号（`__M_xxx` / `_Rb_tree` / libstdc++ 私有 API）**

| 项 | 内容 |
|---|---|
| 触发 | 代码出现 `_M_equal` / `_Rb_tree_node_base` / `__1::` / `__cxx11::` / `_S_xxx` 等**双下划线 / 单下划线开头**的标识符调用 |
| 典型反例 | `bool operator==(const safe_unordered_map& other) { return map_._M_equal(other.map_); }`——`_M_equal` 是 libstdc++ 私有实现 |
| 证据 | C++ Standard `[lex.name]/3.1`——双下划线开头标识符 reserved for the implementation；用户代码引用 = 实现细节耦合，**跨编译器不可移植**（QNX/clang/MSVC 必崩） |
| 修复 | ① 用公开 API（迭代器对比、`std::equal`、`std::unordered_map::operator==` 本身就在 C++11 起）；② 抛弃自研 `operator==`，让 std 容器自己比 |
| 排雷 | 任何 `_<大写>` / `__<任意>` / `_Rb_` / `_M_` / `_S_` / `_Hash_` / `_Vector_` 出现 **必须** flag P1+ |

### **C-CONC-5（P1） · `shared_mutex` / `shared_lock` 不可降级 / 不可升级**

| 项 | 内容 |
|---|---|
| 触发 | 持 `shared_lock`（读锁）时再获取 `unique_lock`（写锁）——许多人以为可以"升级" |
| 典型反例 | `shared_lock l(m_); if (need_write) { unique_lock w(m_); /* 死锁 */ }` |
| 证据 | C++ Standard `[thread.sharedmutex.requirements]`——shared 与 exclusive lock 不可同线程嵌套；行为 UB |
| 修复 | ① 先释放 shared 再取 exclusive（**注意期间状态可能变**，需要 double-check）；② 改用 `upgrade_lock`（boost）/ 自实现 token 切换；③ 直接用 unique_lock（牺牲并发） |

### **C-LIFE-1（P1） · 锁内 delete / 销毁锁所属对象 = UAF**

| 项 | 内容 |
|---|---|
| 触发 | `unique_lock l(this->m_); delete this;` 或 `lock_guard l(obj->m_); container.erase(obj);` |
| 典型反例 | 析构函数里 `lock_guard l(m_); m_.unlock(); delete this;`——锁销毁前对象已 free，l 析构 unlock = UAF |
| 证据 | 团队 2026-04 真实 P0 缺陷（CarPropertyManager 析构 UAF）+ Effective C++ Item 14 |
| 修复 | ① 锁与对象生命周期解耦；② 先 unlock + 拷出关键状态再 delete；③ 改用 `weak_ptr` + `enable_shared_from_this` 控制销毁顺序 |

### **C-LIFE-2（P1） · 容器迭代器/引用在 modifying operation 后失效**
| 项 | 内容 |
|---|---|
| 触发 | `for (auto it = v.begin(); it != v.end(); ++it) { if (cond) { v.push_back(x); /* 迭代器失效 */ } }` 或 `for (auto& kv : map_) { if (cond) map_.erase(kv.first); /* 失效 */ }` |
| 证据 | `[container.requirements.general]`——vector::push_back 可能 reallocate，所有迭代器失效；map::erase(key) 使被删元素的迭代器失效 |
| 修复 | ① `it = v.erase(it)` 模式；② 收集"待删 key"到本地 vector，循环外统一 erase；③ 切到 `std::list`（迭代器稳定）；④ 用 `remove_if` + `erase` |

### **C-CONC-6（P1） · `std::atomic` 默认内存序滥用**

| 项 | 内容 |
|---|---|
| 触发 | `std::atomic<T>` 的 `load()` / `store()` / `fetch_*()` / `compare_exchange_*()` 调用不显式传入内存序参数，默认 `seq_cst` 性能差；或无脑改 `relaxed` 破坏了同步语义 |
| 典型反例 | `running_.store(false);` —— 默认 seq_cst，车载热路径上 ARMv8 每次 store 产生 DMB，性能浪费；反之，状态机标志位 `flag_.store(true, std::memory_order_relaxed);` 在没有 release 配对时其他线程可能永远看不到 |
| 证据 | `[atomics.order]` ——定义 relaxed / consume / acquire / release / acq_rel / seq_cst 6 种内存序；acquire/release 必须成对才能立 happens-before |
| 修复 | ① 状态标志位：写端 `store(v, release)`，读端 `load(acquire)`；② 纯计数器：`relaxed` 即可；③ 跨变量同步：用 `seq_cst`；④ 车载 VIDC 等硬件握手：平衡 DMB 开销与正确性，参考 VideoPlayer 重构 6 条铁律 |
| 扶弝原则 | 不允许`.store(x);` / `.load();` 裸调用（隐式 seq_cst）——**必须显式写内存序并写注释说明为何选该序** |

### **C-CONC-7（P1） · `condition_variable::wait` 必须配 predicate 防伪唤醒**

| 项 | 内容 |
|---|---|
| 触发 | `cv.wait(lock);` 调用不带 predicate（二参数版），或在 `if` 分支内（非 `while`）检查条件 |
| 典型反例 | `if (!ready_) cv.wait(lock); doWork();` ——伪唤醒后 ready_ 仍为 false，doWork 在错误状态执行 |
| 证据 | `[thread.condition.condvar]/wait/3` ——明文规定"the wait is unblocked spuriously"是合法行为，调用方**必须**用谓词防御 |
| 修复 | ① 改为 `cv.wait(lock, [&]{ return ready_; });`；② 或手写 `while (!ready_) cv.wait(lock);`（等价）；**禁用** `if (cond) cv.wait(...)` 模式 |
| 扫描提示 | grep `cv\.wait\(` / `cond_wait\(` / `wait\([a-zA-Z_]+\s*\)` （只一个参数的 wait）均为延续查验点 |

### **C-LIFE-3（P1） · 智能指针所有权混用（双 free 风险）**

| 项 | 内容 |
|---|---|
| 触发 | 同一裸指针被两个独立的 `shared_ptr` 控制块管理；或 `shared_ptr` 与 `unique_ptr` 同时持有同一裸指针；或 `shared_ptr` 管理 this 直接转换而非 `enable_shared_from_this` |
| 典型反例 | `Foo* p = new Foo; std::shared_ptr<Foo> sp1(p); std::shared_ptr<Foo> sp2(p); /* sp2 新建控制块 → double free */` |
| 证据 | `[util.smartptr.shared.const]` ——从裸指针构造 shared_ptr 时每次都新建控制块；双来源 shared_ptr 终析时双 free 为 UB |
| 修复 | ① `auto sp = std::make_shared<Foo>();` 单点创建；② 要从 this 取 shared：继承 `enable_shared_from_this<T>` + `shared_from_this()`；③ 跨函数转交 unique_ptr 后不再维持裸指针 |
| 扫描提示 | grep `std::shared_ptr<.*?>\s*\w+\s*\(\s*\w+\s*\)` 极高风险的"裸指针 → shared_ptr"构造 |

---

## LLM 评审 prompt 接入条款（必须复制进 08）

> 以下条款会被 `08-llm-review-prompt.md` 引用，作为 Step 4.5「C++ 并发与 STL 专项扫」的硬约束。

### Step 4.5 · C++ 并发与 STL 专项（C++ 改动必跑）

按 09 文件 12 条规则**逐条 grep + 上下文确认**：

| 规则 | 主关键词 grep | 必须人工确认 |
|---|---|---|
| C-CONC-1 | `lock_guard\|unique_lock\|shared_lock` 后 5 行内有方法调用 | 是否调用同对象的 public 方法（可能再加锁） |
| C-CONC-2 | `iterator\s+(begin\|end\|find\|lower_bound\|upper_bound)` 在持锁函数体内 | 返回前是否已 unlock |
| C-CONC-3 | `\.insert\(\{|\.insert\(.*?value_type\|\.emplace\(` 出现在 `replace\|update\|set\|put` 类方法体内 | 是否有 find 后 insert 的 if 分支 |
| C-CONC-4 | `value_compare\|value_comp\(\)` | 该模板嵌套类型是否有 public 默认构造 |
| C-STD-1 | `^namespace\s+std\s*\{` 后非 `template<>` | 是否注入了新类/函数 |
| C-STD-2 | `_[A-Z]\w*\|__\w+\|_M_\|_S_\|_Rb_\|_Hash_` | 是否调用了实现私有符号 |
| C-CONC-5 | 同函数内 `shared_lock` + `unique_lock` 同 mutex | 是否锁升级 |
| C-LIFE-1 | `lock_guard.*?` 后 10 行内出现 `delete\|erase(.*?this\|reset\(\)` | 是否锁内销毁锁所属对象 |
| C-LIFE-2 | `for\s*\(.*?:\|\.begin\(\).*?\.end\(\)` 循环体内出现 `push_back\|erase\|insert\|emplace` | 是否未 reassign iterator |
| C-CONC-6 | `\.store\(\|\.load\(\|\.fetch_\|compare_exchange_` 调用 | 是否显式写内存序（`memory_order_*`），默认 seq_cst 在热路径是否过重 |
| C-CONC-7 | `cv\.wait\(\|cond_wait\(` | 是否二参数版（带 predicate）或外套 `while` |
| C-LIFE-3 | `shared_ptr<.*?>\s*\w+\s*\(\s*[a-zA-Z_]\w*\s*\)` | 是否从裸指针重复构造 shared_ptr，或 shared_ptr/unique_ptr 共用同裸指针 |

### 强制 cover 条款

C++ 改动的 cover **必含**以下专项段（即使 0 发现也要写）：

```markdown
### C++ 并发与 STL 专项扫描（references/09）

| 规则 | 扫描结果 |
|---|---|
| C-CONC-1 不可重入锁自死锁 | ✅ 无 / ⚠️ N 处 |
| C-CONC-2 标准容器 API 暴露 | ✅ 无 / ⚠️ N 处 |
| C-CONC-3 insert no-op 替换 | ✅ 无 / ⚠️ N 处 |
| C-CONC-4 模板嵌套类型 | ✅ 无 / ⚠️ N 处 |
| C-STD-1 namespace std 注入 | ✅ 无 / ⚠️ N 处 |
| C-STD-2 私有符号依赖 | ✅ 无 / ⚠️ N 处 |
| C-CONC-5 shared/unique lock | ✅ 无 / ⚠️ N 处 |
| C-LIFE-1 锁内 delete | ✅ 无 / ⚠️ N 处 |
| C-LIFE-2 迭代器失效 | ✅ 无 / ⚠️ N 处 |
| C-CONC-6 atomic 内存序滥用 | ✅ 无 / ⚠️ N 处 |
| C-CONC-7 cv.wait 无 predicate | ✅ 无 / ⚠️ N 处 |
| C-LIFE-3 智能指针所有权混用 | ✅ 无 / ⚠️ N 处 |
```

### 评分映射

- C-CONC-1 / C-CONC-2 / C-CONC-3 / C-CONC-4 / C-LIFE-1（如 lock 内 delete 锁所属对象）→ **P0 → -1**
- C-STD-1 / C-STD-2 / C-CONC-5 / C-LIFE-2 / C-CONC-6 / C-CONC-7 / C-LIFE-3 → **P1 → 0 或 -1**（取决于是否在调用链上真触发）

### 「历史代码也算」例外

本文件 12 条**任一命中即报告**，**不区分**新写代码 vs 历史代码——理由：
- 这些缺陷在调用面扩散后修复成本指数上升
- "本 CR 是新增并发容器" = 调用面正在扩张，必须**收敛后再接入业务路径**
- 与 `gerrit_cron_review.py` 的"历史代码 P0 降级 P2"规则**冲突时本规则优先**

---

## 复盘案例：CR 1003290（KP31 core Linux UT）

| 规则 | 文件 | 命中 | her 漏报 | 志强 LLM 报告 |
|---|---|---|---|---|
| C-CONC-1 | `safe_queue.h::operator==` | ✅ | ❌ 完全漏 | ✅ P0 |
| C-CONC-2 | `safe_map.h::begin/end/find` | ✅ | ❌ 完全漏 | ✅ P0 |
| C-CONC-3 | `safe_map.h::replace`, `safe_unordered_map.h::replace` | ✅ | ⚠️ 报为 P2 | ✅ P0 |
| C-CONC-4 | `safe_map.h::value_comp` | ✅ | ❌ 完全漏 | ✅ P0 |
| C-STD-1 | `unique_ptr.h`, `shared_lock.h` | ✅ | ❌ 完全漏 | ✅ P1 |
| C-STD-2 | `safe_unordered_map.h::_M_equal` | ✅ | ⚠️ 报为 P2 | ✅ P1 |

**her 当时分数**：P0=0 / P1=0 / P2=2 → +1 ✗
**志强 LLM 分数**：P0=4 / P1=2 → -1 ✓

**根因**：LLM 评审 prompt 没有"C++ 并发与 STL 专项"硬扫清单；评审者（claude-opus-4-7）凭直觉评，扫到了零碎现象但没识别为 P0 等级。

**本文件存在的目的**：把这次教训**强制写进每条 CR 的评审清单**，让模型**没有"凭直觉评"的余地**。
