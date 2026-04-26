# 06 · 车载中间件专项 checklist（Android + QNX）

## 基础参考

- [Android Automotive OS Developer Guide](https://source.android.com/docs/automotive)
- [Android IPC Best Practices](https://developer.android.com/guide/components/aidl)
- [QCA Platform (QNX) Documentation](https://developer.qnx.com/) — 内部
- ISO 26262 (Functional Safety)
- AUTOSAR Classic / Adaptive Platform

---

## L1 · 功能正确性

### L1.1 状态机 / 回调时序

| 检查项 | 典型场景 | 级别 |
|---|---|---|
| HIDL/AIDL 回调处理"**注册前触发**"场景？ | `registerCallback` 前 `PROPERTY_CHANGE` 已来 | P0 (NPE) |
| CarProperty 回调考虑"**初始化未完成就 PROPERTY_CHANGE**" | | P0 |
| 上下电 / 休眠唤醒 / STR 场景状态机完整？ | 漏状态转换 | P0 |
| PPS 订阅在同线程处理？跨线程加 `volatile`？ | QNX PPS multi-thread | **P0** |
| EventHolder 线程与 Binder 线程共享字段 | | P0 |

### L1.2 跨进程契约

| 检查项 | 级别 |
|---|---|
| AIDL 返回值语义与 IPower/IPowerCallback 契约一致 | P0 |
| 新增 AIDL 方法同步更新 `current.txt` | P1 |
| 新增常量拼写正确 | P1 |
| 命名风格与已有一致 | P2 |

### L1.3 分片 CR（1/N, 2/N）

| 检查项 | 级别 |
|---|---|
| 分片 CR 独立编译通过（避免 1/N 先合 2/N 再合的时序陷阱） | P0 |
| 跨分片 Jira 号一致 | P1 |
| 公开 API 在最后一片合并时一次性 freeze | P1 |

---

## L2 · 线程 / 并发

车载中间件最高发问题，详见 `02-security.md` §4。

额外车载专项：

| 检查项 | 级别 |
|---|---|
| Handler 在 onDestroy removeCallbacks | P1 |
| Looper.quit() 后仍有 post | P1 |
| Binder Thread Pool 耗尽 | **P0** |
| QNX 信号处理函数里做复杂操作 | **P0** |
| EventHolder 多线程共享字段未 volatile | **P0** |

---

## L3 · IPC 可靠性

详见 `02-security.md` §6。

额外车载专项：

| 项 | 级别 |
|---|---|
| QNX PPS 发布频率 > 100Hz 无 throttle | P1 |
| FDBus 调用未配对 connect/disconnect | P1 |
| HIDL 服务未处理 client 死亡 | P1 |
| Android ↔ QNX 跨 VM IPC 未 heartbeat | P2 |
| AIDL Binder 入参 null 校验 | P0/P1 |

---

## L4 · 资源 / 生命周期

详见 `02-security.md` §5。

### 车载专项 WakeLock / Alarm

| 项 | 级别 |
|---|---|
| WakeLock 不配对 release | **P0**（电池） |
| Alarm `ELAPSED_REALTIME_WAKEUP` 频率过高（< 5 min） | **P1** |
| STR 状态下 Alarm 仍在运行 | P0 |
| 定时器 `PowerTimer::startTimer` 不配对 `stopTimer` | P1 |

---

## L5 · 日志 / 规范（项目惯例）

### 硬性项目规范

| 项 | 级别 |
|---|---|
| **commit message 无 Jira 号**（CHYT1V/BAIC/KP31/CL/T1V/D01） | **P0** → -1 |

### 项目允许/不强制（非违规）

- `e.printStackTrace()` — 允许
- commit message 格式错误 / 错别字 — 不管
- Log 封装类（XxxLog vs android.util.Log） — 无明文规范时不强制
- TAG 命名 — 无明文规范时不强制
- JavaDoc 缺失 — 仅 public API 且明显困惑时提 P3

---

## L6 · 电源 / 启动时序（车载核心）

### 评审项

| 项 | 级别 |
|---|---|
| 新增功能未考虑 **STR 快速启动** 场景 | **P0** |
| 冷启动场景依赖的服务未 ready → NPE | P0 |
| 休眠唤醒后内存中状态未刷新 | P1 |
| 上电时序（MCU → SOC → AP → Service → App）哪一层未就绪时调用会出什么问题 | P1 |
| PM_SUSPEND 前的异步任务未 flush | P1 |
| 重启策略 / 防抖 / 限频 缺失 | P1 |

---

## L7 · 诊断（车载专项）

| 项 | 级别 |
|---|---|
| DTC 上报后无**清除路径** → 故障灯常亮 | **P0** |
| DID 编码不符合 UDS 服务规范 | P0 |
| 诊断 session timeout 未 reset | P1 |
| DoCAN 流控未实现（避免总线拥塞） | P1 |
| DoIP 连接心跳缺失 | P1 |

---

## L8 · OTA / 升级

| 项 | 级别 |
|---|---|
| 升级失败无回滚 | **P0** |
| 升级中断后二次启动不可恢复 | P0 |
| A/B partition 切换异常 | P0 |
| 升级过程未校验签名 | **P0** |
| 升级包未校验完整性（hash/checksum） | P0 |
| OTA 流程未考虑磁盘空间预检 | P1 |

---

## L9 · 配置管理

| 项 | 级别 |
|---|---|
| 新平台硬编码到 `if (chip == 8775)` 分支（应走配置） | P1 |
| T1V 专属代码污染公共目录 | **P1** |
| 配置读取未兜底（默认值缺失） | P1 |
| 云配置/本地配置优先级混乱 | P1 |

---

## L10 · 日志管理

| 项 | 级别 |
|---|---|
| 高频回调内 `Log.i`（应 `Log.d` 或降频） | P2 |
| Log 中含敏感信息（VIN/IMEI/GPS/Token） | **P0** |
| Exception 堆栈被截断或缺 | P2 |
| 缺 TAG 分类（定位问题困难） | P3 |

---

## 车载评审特有原则

1. **时序思维**：每个新函数都要问"如果在 STR/休眠/冷启动时被调用，会发生什么？"
2. **多线程思维**：Binder 线程 / Handler 线程 / EventHolder 线程共存，任何字段都要想"谁写谁读"
3. **Treble 分层**：APP → Framework → HAL → Kernel，不允许跨层直达
4. **续航思维**：任何 WakeLock / Alarm / 高频事件都要考虑对续航的影响
5. **诊断闭环**：DTC 必须有"上报 + 清除"两条路径
