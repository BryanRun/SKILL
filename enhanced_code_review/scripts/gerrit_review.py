"""gerrit_review.py — 主入口，全自动化评审 + 贴回

用法：
  python3 gerrit_review.py <CR_NUMBER>              # 全自动（拉取→扫描→让 LLM 评 → 贴回）
  python3 gerrit_review.py <CR_NUMBER> --dry        # 只拉数据 + 机械扫描，不贴
  python3 gerrit_review.py <CR_NUMBER> --prepare    # 准备好 LLM 输入（stdout），LLM 产出 review.json 后可用 --post
  python3 gerrit_review.py <CR_NUMBER> --post review.json [--score N]

本脚本不包含 LLM 调用。LLM 侧由 her 本体在对话里完成：
  1. her 跑 prepare，拿到上下文
  2. her 按 references/llm-review-prompt.md 的 system+user prompt 产出 review.json
  3. her 跑 --post review.json 贴回
"""
import sys, os, json, argparse, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gerrit_client import (
    get_cr_detail, get_file_diff, iter_diff_lines,
    extract_jira, find_related_crs, post_review, BASE,
    build_prior_review_context, compute_review_decision, USER,
    detect_build_failure, BUILD_FAIL_COVER_TEMPLATE,
    get_current_revision,
)

try:
    from consistency_scan import analyze_file as scan_consistency
except ImportError:
    scan_consistency = None

from gerrit_audit import analyse_cr

# v2.7.0：复杂度评级 + cherry-pick 复用识别
try:
    from complexity_assess import assess as _complexity_assess
except ImportError:
    _complexity_assess = None
try:
    from cherry_pick_detect import detect as _cherry_pick_detect
except ImportError:
    _cherry_pick_detect = None

# v2.5.2：回帖 cover 统一经 skill 模板渲染（与 gerrit_post.py 同源）
try:
    from cover_template import render_from_review_and_ctx as _render_from_review_and_ctx
except ImportError:
    _render_from_review_and_ctx = None


# v2.5.5 SELinux 上下文门控 ----------------------------------------------------
# 命中以下任一特征即判定 CR 含 SELinux 策略改动（见 references/18-selinux-policy.md）。
_SELINUX_BASENAMES = (
    'file_contexts', 'property_contexts', 'service_contexts', 'seapp_contexts',
    'hwservice_contexts', 'vndservice_contexts', 'genfs_contexts',
    'mac_permissions.xml', 'keys.conf', 'te_macros',
)
_SELINUX_BUILD_MACRO_RE = re.compile(
    r'(SEPOLICY_DIRS|BOARD_[A-Z_]*SEPOLICY|SYSTEM_EXT_[A-Z_]*SEPOLICY_DIRS|PRODUCT_[A-Z_]*SEPOLICY_DIRS|BOARD_VENDOR_SEPOLICY_DIRS|BOARD_ODM_SEPOLICY_DIRS)'
)


def _is_selinux_path(fn):
    """单个文件路径是否属于 SELinux 策略上下文（仅靠路径/文件名判断）。"""
    if not fn or fn == "/COMMIT_MSG":
        return False
    low = fn.lower()
    base = low.rsplit('/', 1)[-1]
    if low.endswith('.te') or low.endswith('.cil'):
        return True
    if base in _SELINUX_BASENAMES:
        return True
    if '/sepolicy/' in low or '/selinux/' in low:
        return True
    return False


def detect_selinux_context(file_names):
    """diff 文件集合是否命中 SELinux 上下文。

    .mk / .bp 仅当含 sepolicy 编译宏时才算（避免任意 Makefile 误触发）。
    本函数只看路径/文件名，对 .mk/.bp 的宏检查留给调用方按需补充内容判断；
    这里对 .mk/.bp 采取「路径含 sepolicy/selinux 即算」的保守策略。
    """
    for fn in (file_names or []):
        if _is_selinux_path(fn):
            return True
    return False


def _selinux_lang_entry():
    """构造 ctx['languages'] 的 SELinux 伪语言条目（含 14 条规则 + scan_hints）。"""
    return {
        'lang': 'SELinux',
        'extensions': ['.te', '.cil', 'file_contexts', 'service_contexts',
                       'seapp_contexts', 'property_contexts', 'te_macros'],
        'rules_file': 'references/18-selinux-policy.md',
        'rules_count': 14,
        'rule_ids': ['SEL-PERM-1', 'SEL-WILD-1', 'SEL-WX-1', 'SEL-NEVERALLOW-1',
                     'SEL-CAP-1', 'SEL-VIOLATOR-1', 'SEL-DONTAUDIT-1', 'SEL-LABEL-1',
                     'SEL-VER-1', 'SEL-CTX-1', 'SEL-MIN-1', 'SEL-MACRO-1',
                     'SEL-COMMENT-1', 'SEL-NAME-1'],
        'scan_hints': [
            {'rule': 'SEL-PERM-1', 'level': 'P0', 'title': 'permissive 域关闭强制',
             'grep': r'^\s*permissive\s+\w+|permissive_or_unconfined',
             'check': '生产策略是否存在 permissive 域（CDD §9.7 user 版禁止）'},
            {'rule': 'SEL-WILD-1', 'level': 'P0', 'title': '通配符过度授权',
             'grep': r'allow\s+\S+\s+\S+:\S+\s+\*|self:capability\s+\*|:\s*\*\s+\*',
             'check': 'allow 是否用 * 授予整类权限/能力'},
            {'rule': 'SEL-WX-1', 'level': 'P0', 'title': 'W^X 违规',
             'grep': r'execmem|execmod|execstack|execheap',
             'check': '是否授予可写可执行内存或从 data 分区 execute'},
            {'rule': 'SEL-NEVERALLOW-1', 'level': 'P0', 'title': '削弱/绕过 neverallow',
             'grep': r'neverallow|\.ignore\.cil',
             'check': '是否修改/删除 neverallow 或用 ignore.cil 规避当前版本安全断言'},
            {'rule': 'SEL-CAP-1', 'level': 'P1', 'title': '危险 capability 授予',
             'grep': r'self:capability\d?\s.*(sys_admin|dac_override|dac_read_search|setuid|setgid|sys_module|sys_ptrace|mac_admin|mac_override|sys_rawio)',
             'check': '高危 capability 是否有理由；授予 untrusted/isolated 域→P0'},
            {'rule': 'SEL-VIOLATOR-1', 'level': 'P1', 'title': '挂接 *_violators 临时豁免',
             'grep': r'_violators\b',
             'check': '是否挂接 Treble violator 属性且无清退计划/Jira'},
            {'rule': 'SEL-DONTAUDIT-1', 'level': 'P1', 'title': 'dontaudit 掩盖真实 denial',
             'grep': r'^\s*dontaudit\b',
             'check': 'dontaudit 是否用于抑制真实需求而非良性噪声'},
            {'rule': 'SEL-LABEL-1', 'level': 'P1', 'title': '上下文标签错误',
             'grep': r'u:object_r:\w+:s0',
             'check': 'file_contexts 目录是否 (/.*)? 锚定 / type 是否已定义 / label 是否错配'},
            {'rule': 'SEL-VER-1', 'level': 'P1', 'title': '缺版本兼容处理',
             'grep': r'_\d+_\d+\b|expandtypeattribute|typeattributeset',
             'check': '新增 versioned type 是否同步 compat/mapping/ignore.cil'},
            {'rule': 'SEL-CTX-1', 'level': 'P1', 'title': 'contexts 与 .te 不一致',
             'grep': r'add_service|set_prop|get_prop|domain=|seinfo=',
             'check': 'service/seapp/property 注册是否有对应 .te 类型与授权'},
            {'rule': 'SEL-MIN-1', 'level': 'P2', 'title': '权限集合过宽（轻度）',
             'grep': r'\{[^}]*\b(write|create|setattr|unlink)\b[^}]*\}',
             'check': '授予的权限集合是否超过实际所需'},
            {'rule': 'SEL-MACRO-1', 'level': 'P2', 'title': '重复模式未用宏/属性',
             'grep': r'^\s*allow\s+',
             'check': '重复 allow 组合是否应抽 te_macros / 用 attribute 归并'},
            {'rule': 'SEL-COMMENT-1', 'level': 'P2', 'title': '敏感授权缺 why 注释',
             'grep': r'binder|capability|set_prop',
             'check': '高危/跨域/跨分区授权是否缺用途注释'},
            {'rule': 'SEL-NAME-1', 'level': 'P3', 'title': '命名/目录结构不规范',
             'grep': r'\.te$',
             'check': '.te 命名是否小写下划线 / 目录是否按推荐布局'},
        ],
    }


def prepare_context(cr_num):
    """拉齐 LLM 评审需要的所有上下文，一个 JSON 返回。"""
    d = get_cr_detail(cr_num)
    if not isinstance(d, dict):
        return {"error": str(d)}

    cur = d["current_revision"]
    subj = d.get("subject", "")
    commit_msg = d["revisions"][cur]["commit"]["message"]
    owner = d.get("owner", {})
    files = d["revisions"][cur].get("files") or {}
    project = d.get("project", "")
    branch = d.get("branch", "")

    ctx = {
        "cr": cr_num,
        "revision": cur,
        "subject": subj,
        "owner": owner.get("username") or owner.get("name"),
        "owner_email": owner.get("email"),
        "project": project,
        "branch": branch,
        "url": f"{BASE}/c/{project}/+/{cr_num}",
        "status": d.get("status"),
        "wip": bool(d.get("work_in_progress")),
        "insertions": d.get("insertions"),
        "deletions": d.get("deletions"),
        "jira": extract_jira(subj + "\n" + commit_msg),
        "commit_message": commit_msg,
        "files": [],
        "related_crs": [],
        "audit": {},
        "consistency": {},
    }


    # 自动检测语言（按文件扩展名）
    detected_langs = set()
    for fn in files.keys():
        if fn == "/COMMIT_MSG":
            continue
        fn_lower = fn.lower()
        if fn_lower.endswith(('.cpp', '.cc', '.cxx', '.hpp', '.h')):
            # .h 可能是 C 或 C++，优先判定为 C++（车载项目多为 C++）
            detected_langs.add('cpp')
        elif fn_lower.endswith(('.java', '.kt')):
            detected_langs.add('java')
        elif fn_lower.endswith('.c'):
            # 纯 .c 文件判定为 C（除非上下文有 C++ 文件）
            detected_langs.add('c')

    # 如果同时有 .c 和 .cpp，优先 C++（混合项目）
    if 'cpp' in detected_langs and 'c' in detected_langs:
        detected_langs.discard('c')

    # 映射到规则文件 (v2.4.2: 加 scan_hints + 修正 rule_ids 与 09/11 文件实际一致)
    lang_rules = []
    if 'cpp' in detected_langs:
        lang_rules.append({
            'lang': 'C++',
            'extensions': ['.cpp', '.cc', '.cxx', '.hpp', '.h'],
            'rules_file': 'references/09-cpp-concurrency-stl-traps.md',
            'rules_count': 12,
            'rule_ids': ['C-CONC-1', 'C-CONC-2', 'C-CONC-3', 'C-CONC-4', 'C-STD-1', 'C-STD-2',
                        'C-CONC-5', 'C-LIFE-1', 'C-LIFE-2', 'C-CONC-6', 'C-CONC-7', 'C-LIFE-3'],
            'scan_hints': [
                {'rule': 'C-CONC-1', 'level': 'P0', 'title': '不可重入锁持锁再加锁自死锁',
                 'grep': r'lock_guard|unique_lock|shared_lock',
                 'check': '持锁块体内的方法调用是否再加同一把锁'},
                {'rule': 'C-CONC-2', 'level': 'P0', 'title': '标准容器迭代器/引用 API 暴露到锁外',
                 'grep': r'\b(begin|end|find|lower_bound|upper_bound)\s*\(',
                 'check': '是否在持锁函数体内返回迭代器/引用，调用者拿到后无锁'},
                {'rule': 'C-CONC-3', 'level': 'P0', 'title': 'std::map::insert 已存在 key 是 no-op',
                 'grep': r'\.insert\s*\(|\.emplace\s*\(',
                 'check': '是否在 replace/update/set/put 方法体内用 insert，期望覆盖却静默失败'},
                {'rule': 'C-CONC-4', 'level': 'P0', 'title': '模板嵌套类型无 public 默认构造',
                 'grep': r'value_compare|value_comp\s*\(\s*\)',
                 'check': '模板嵌套类型是否有 public 默认构造'},
                {'rule': 'C-STD-1', 'level': 'P1', 'title': 'namespace std 注入新类/函数 = UB',
                 'grep': r'^\s*namespace\s+std\s*\{',
                 'check': '是否注入新类/函数（仅模板特化合法）'},
                {'rule': 'C-STD-2', 'level': 'P1', 'title': '依赖标准库实现私有符号',
                 'grep': r'\b(_M_|_S_|_Rb_|_Hash_|_M_equal|__1::)',
                 'check': '是否调用 libstdc++/libc++ 私有符号'},
                {'rule': 'C-CONC-5', 'level': 'P1', 'title': 'shared_lock 与 unique_lock 同 mutex 嵌套',
                 'grep': r'shared_lock|unique_lock',
                 'check': '同函数内是否同 mutex 出现升级/降级'},
                {'rule': 'C-LIFE-1', 'level': 'P1', 'title': '锁内 delete 锁所属对象 = UAF',
                 'grep': r'lock_guard|unique_lock',
                 'check': '持锁后 N 行内是否 delete this/erase 锁所属对象/reset() 锁所属智能指针'},
                {'rule': 'C-LIFE-2', 'level': 'P1', 'title': '迭代器/引用在 modifying op 后失效',
                 'grep': r'for\s*\(.*?:|\.begin\(\).*?\.end\(\)',
                 'check': '循环体内是否 push_back/erase/insert/emplace 后未 reassign iterator'},
                {'rule': 'C-CONC-6', 'level': 'P1', 'title': 'std::atomic 默认内存序滥用',
                 'grep': r'\.store\s*\(|\.load\s*\(|\.fetch_|compare_exchange_',
                 'check': '是否未显式写 memory_order_*，热路径默认 seq_cst 是否过重'},
                {'rule': 'C-CONC-7', 'level': 'P1', 'title': 'condition_variable::wait 必须配 predicate',
                 'grep': r'cv\.wait\s*\(|cond_wait\s*\(',
                 'check': '是否使用二参数版（带 predicate）或外套 while 检查条件'},
                {'rule': 'C-LIFE-3', 'level': 'P1', 'title': '智能指针所有权混用（双 free 风险）',
                 'grep': r'shared_ptr<.*?>\s*\w+\s*\(\s*[a-zA-Z_]\w*\s*\)',
                 'check': '同一裸指针是否被两个 shared_ptr 控制块管理；shared_ptr 与 unique_ptr 共持裸指针'},
            ]
        })
    if 'java' in detected_langs:
        lang_rules.append({
            'lang': 'Java/Kotlin',
            'extensions': ['.java', '.kt'],
            'rules_file': 'references/11-java-concurrency-collection-traps.md',
            'rules_count': 12,
            'rule_ids': ['J-CONC-1', 'J-CONC-2', 'J-CONC-3', 'J-CONC-4', 'J-CONC-5',
                        'J-STD-1', 'J-STD-2', 'J-LIFE-1', 'J-LIFE-2', 'J-LIFE-3',
                        'J-CONC-6', 'J-CONC-7'],
            'scan_hints': [
                {'rule': 'J-CONC-1', 'level': 'P0', 'title': 'StampedLock/synchronized(this) 持锁再加锁自死锁',
                 'grep': r'StampedLock|synchronized\s*\(\s*this\s*\)',
                 'check': '持锁体内是否调用未知方法/虚函数/回调'},
                {'rule': 'J-CONC-2', 'level': 'P0', 'title': '集合视图（keySet/entrySet/values）逃出锁外',
                 'grep': r'\.keySet\(\)|\.entrySet\(\)|\.values\(\)',
                 'check': '视图是否返回到 synchronized 块外被迭代'},
                {'rule': 'J-CONC-3', 'level': 'P0', 'title': 'containsKey-then-put 非原子',
                 'grep': r'containsKey.*?put|get\s*\([^)]*\)\s*==\s*null.*?put',
                 'check': '是否未用 computeIfAbsent / putIfAbsent'},
                {'rule': 'J-CONC-4', 'level': 'P0', 'title': 'Comparator 含可变状态/与 equals 不一致',
                 'grep': r'implements\s+Comparator|implements\s+Comparable|compareTo\s*\(',
                 'check': '是否含可变状态、与 equals 不一致'},
                {'rule': 'J-CONC-5', 'level': 'P0', 'title': 'ReadWriteLock 读锁升级写锁',
                 'grep': r'readLock\(\)\.lock|writeLock\(\)\.lock',
                 'check': '同函数内是否同线程读锁升写锁（必死锁）'},
                {'rule': 'J-STD-1', 'level': 'P1', 'title': 'java.* / javax.* / sun.* 包注入类',
                 'grep': r'^\s*package\s+(java|javax|sun|com\.sun)\.',
                 'check': '是否在受保护包注入类'},
                {'rule': 'J-STD-2', 'level': 'P1', 'title': '依赖 sun.misc.Unsafe / com.sun.* 内部 API',
                 'grep': r'import\s+(sun\.misc\.Unsafe|com\.sun\.tools\.)',
                 'check': '是否使用 JDK 内部 API'},
                {'rule': 'J-LIFE-1', 'level': 'P1', 'title': 'synchronized 块内关闭锁所属资源',
                 'grep': r'synchronized.*?\{.*?\.close\s*\(',
                 'check': '是否锁内 close 锁所属资源'},
                {'rule': 'J-LIFE-2', 'level': 'P1', 'title': '集合迭代时通过容器 remove',
                 'grep': r'for\s*\([^)]*:[^)]*\)\s*\{[^}]*\.remove\s*\(',
                 'check': '是否容器自身 remove 而非 Iterator.remove'},
                {'rule': 'J-LIFE-3', 'level': 'P1', 'title': 'final/volatile 字段发布安全（DCL）',
                 'grep': r'if\s*\(\s*instance\s*==\s*null\s*\)|if\s*\(\s*\w+\s*==\s*null\s*\).*?synchronized',
                 'check': '字段是否未 volatile 导致发布未初始化对象'},
                {'rule': 'J-CONC-6', 'level': 'P1', 'title': 'ThreadLocal 在线程池泄漏',
                 'grep': r'ThreadLocal<',
                 'check': '线程池上下文是否调 remove() 清理'},
                {'rule': 'J-CONC-7', 'level': 'P1', 'title': 'parallelStream 副作用与有状态 lambda',
                 'grep': r'\.parallel\(\)|parallelStream\s*\(\)',
                 'check': 'lambda 是否无状态、无副作用'},
            ]
        })
    if 'c' in detected_langs:
        lang_rules.append({
            'lang': 'C',
            'extensions': ['.c', '.h'],
            'rules_file': 'references/12-c-concurrency-traps.md',
            'rules_count': 15,
            'rule_ids': ['C-MUTEX-1', 'C-MUTEX-2', 'C-RACE-1', 'C-RACE-2', 'C-LIFE-1', 'C-LIFE-2',
                        'C-INIT-1', 'C-INIT-2', 'C-COND-1', 'C-COND-2', 'C-ATOMIC-1', 'C-ATOMIC-2',
                        'C-GLOBAL-1', 'C-ERRNO-1', 'C-SIGNAL-1'],
            'scan_hints': [
                {'rule': 'C-MUTEX-1', 'level': 'P0', 'title': 'pthread_mutex_lock 同一线程重入',
                 'grep': r'pthread_mutex_lock\s*\(',
                 'check': '是否非 PTHREAD_MUTEX_RECURSIVE 同一线程重入加锁'},
                {'rule': 'C-MUTEX-2', 'level': 'P0', 'title': 'pthread_mutex_unlock 非持锁线程调用',
                 'grep': r'pthread_mutex_unlock\s*\(',
                 'check': '是否在不同线程 unlock 已被 lock 的 mutex'},
                {'rule': 'C-RACE-1', 'level': 'P0', 'title': '非原子类型多线程读写无同步',
                 'grep': r'(int|long|bool|char)\s+\w+\s*=|=\s*[a-zA-Z_]\w*',
                 'check': '是否多线程访问的全局/共享变量无 mutex / atomic 保护'},
                {'rule': 'C-RACE-2', 'level': 'P0', 'title': 'volatile 不保证原子性，不能替代 mutex',
                 'grep': r'\bvolatile\s+',
                 'check': '是否用 volatile 做线程同步（应用 atomic 或 mutex）'},
                {'rule': 'C-LIFE-1', 'level': 'P0', 'title': '持锁期间 free() 锁所在结构体',
                 'grep': r'pthread_mutex_lock|pthread_mutex_trylock',
                 'check': '持锁后是否 free 锁所属 struct（lock 字段先于 free 是 UAF）'},
                {'rule': 'C-LIFE-2', 'level': 'P0', 'title': '回调函数内 free() 回调注册者',
                 'grep': r'callback|cb\s*\(|->.*?\(',
                 'check': '回调内是否 free 回调注册者（PPS / FDBus 高发）'},
                {'rule': 'C-INIT-1', 'level': 'P1', 'title': 'PTHREAD_MUTEX_INITIALIZER 后再 pthread_mutex_init',
                 'grep': r'PTHREAD_MUTEX_INITIALIZER|pthread_mutex_init\s*\(',
                 'check': '是否先静态初始化后又调用 init（UB）'},
                {'rule': 'C-INIT-2', 'level': 'P1', 'title': 'pthread_mutex_destroy 后未重新 init 就 lock',
                 'grep': r'pthread_mutex_destroy\s*\(',
                 'check': 'destroy 后是否未 init 就再次 lock（UB）'},
                {'rule': 'C-COND-1', 'level': 'P1', 'title': 'pthread_cond_wait 不在循环中检查条件',
                 'grep': r'pthread_cond_wait\s*\(|pthread_cond_timedwait\s*\(',
                 'check': '是否外套 while 防伪唤醒（spurious wakeup）'},
                {'rule': 'C-COND-2', 'level': 'P1', 'title': 'pthread_cond_signal/broadcast 不持锁调用',
                 'grep': r'pthread_cond_signal\s*\(|pthread_cond_broadcast\s*\(',
                 'check': '是否不持锁调用 signal/broadcast（lost wakeup）'},
                {'rule': 'C-ATOMIC-1', 'level': 'P1', 'title': 'C11 _Atomic 类型与非原子操作混用',
                 'grep': r'_Atomic\s+|\batomic_\w+\s*\(',
                 'check': '是否同一变量混用原子和非原子操作'},
                {'rule': 'C-ATOMIC-2', 'level': 'P1', 'title': 'stdatomic.h 原子操作用错内存序',
                 'grep': r'memory_order_(relaxed|acquire|release|acq_rel|consume|seq_cst)',
                 'check': '是否在锁实现/同步中用了 relaxed'},
                {'rule': 'C-GLOBAL-1', 'level': 'P1', 'title': '全局变量无锁保护多线程修改',
                 'grep': r'^\s*(static\s+)?(int|long|bool|char|struct\s+\w+)\s+\w+\s*[=;]',
                 'check': '全局变量是否有 mutex / atomic 保护'},
                {'rule': 'C-ERRNO-1', 'level': 'P1', 'title': '多线程共享 errno → race',
                 'grep': r'\berrno\b',
                 'check': '是否假定多线程共享 errno（应用 thread-local）'},
                {'rule': 'C-SIGNAL-1', 'level': 'P1', 'title': '信号处理函数调用非 async-signal-safe 函数',
                 'grep': r'sigaction\s*\(|signal\s*\(',
                 'check': '信号处理函数是否调用非 async-signal-safe 函数（如 printf/malloc）'},
            ]
        })

    # v2.5.5 SELinux 上下文门控：命中 sepolicy 相关文件才追加 SELinux 伪语言条目，
    # 从而强制 selinux_policy 维度 scanned=true + rule_check_table["SELinux"]。
    # 非 SELinux CR 不命中 → selinux_policy 允许 scanned=false（DIMS_ALLOW_NOT_SCANNED）。
    if detect_selinux_context(files.keys()):
        lang_rules.append(_selinux_lang_entry())

    ctx['languages'] = lang_rules

    # Jira 关联 CR
    for j in ctx["jira"]:
        peers = find_related_crs(j)
        for r in peers:
            if r.get("_number") == int(cr_num):
                continue
            ctx["related_crs"].append({
                "cr": r.get("_number"),
                "subject": r.get("subject"),
                "status": r.get("status"),
            })

    # files + diff
    for fn, meta in files.items():
        if fn == "/COMMIT_MSG":
            continue
        item = {
            "path": fn,
            "status": meta.get("status", "M"),
            "inserted": meta.get("lines_inserted", 0),
            "deleted": meta.get("lines_deleted", 0),
            "diff_lines": [],
        }
        dd = get_file_diff(cr_num, cur, fn)
        if isinstance(dd, dict):
            for old_l, new_l, kind, text in iter_diff_lines(dd):
                if kind == "ctx":
                    continue
                item["diff_lines"].append({
                    "old": old_l, "new": new_l, "kind": kind, "text": text,
                })
        ctx["files"].append(item)

    # audit: 机械规则
    audit = analyse_cr(cr_num)
    ctx["audit"] = {
        "summary": audit.get("summary", {}),
        "comments": audit.get("comments", {}),
        "suggested_score": audit.get("suggested_score"),
    }

    # consistency scan
    if scan_consistency:
        for fn in files:
            if fn == "/COMMIT_MSG" or not fn.endswith((".java", ".kt")):
                continue
            try:
                findings = scan_consistency(cr_num, cur, fn)
                if findings:
                    ctx["consistency"][fn] = findings
            except Exception as e:
                ctx["consistency"][f"{fn}_error"] = str(e)

    # v2.6.0 BUILD-FAIL-1: 预编译失败红线检查（优先于 LLM 评审）
    try:
        build_failure = detect_build_failure(d)
    except Exception as e:
        build_failure = None
        ctx['build_failure_scan_error'] = str(e)
    if build_failure:
        ctx['build_failure'] = build_failure

    # v2.5.0: prior review context（读取 inline comments 回复链 + 分数历史）
    try:
        prior = build_prior_review_context(cr_num, USER)
        ctx['prior_review_context'] = prior
        # v2.5.0 修正版：计算评审决策（v2.6.0 叠加 BUILD-FAIL-1）
        decision = compute_review_decision(prior, build_failure=ctx.get('build_failure'))
        ctx['review_decision'] = decision
    except Exception as e:
        ctx['prior_review_context'] = {'error': str(e), 'has_prior_review': False, 'has_owner_reply': False, 'other_minus_one': False, 'has_substantive_other_minus_one': False, 'other_minus_one_details': []}
        ctx['review_decision'] = {'mode': 'proceed', 'reason': f'prior_review_context 构建失败，默认 proceed: {e}', 'should_review': True, 'is_incremental': False, 'details': {}}

    # v2.6.0 CL-6 + CL-3：契约变更扫 + 上下文感知一致性扫
    try:
        from gerrit_audit import contract_change_scan, contract_consistency_scan
        from gerrit_client import gget as _gget
        # 收集 diff 文本（按文件拼接）
        diff_lines = []
        for fn in files:
            fdata = cr_info.get('revisions', {}).get(cur, {}).get('files', {}).get(fn, {}) if isinstance(cr_info.get('revisions', {}).get(cur, {}), dict) else {}
            # diff 这里粗略用 audit 已收集的 diff_text；如无则跳过
        # 从 ctx['files'] 累积 diff_lines 字符串
        for f in ctx.get('files', []):
            path = f.get('path')
            if path in ('/COMMIT_MSG', '/PATCHSET_LEVEL'): continue
            diff_lines.append(f'--- {path}')
            for dl in f.get('diff_lines', []):
                kind = dl.get('kind')
                text = dl.get('text', '')
                if kind == 'add':
                    diff_lines.append(f'+{text}')
                elif kind == 'delete':
                    diff_lines.append(f'-{text}')
        diff_text = '\n'.join(diff_lines)
        candidates = contract_change_scan(diff_text, ctx.get('files', []))
        if candidates:
            ctx['contract_change_candidates'] = candidates
            # 进一步做上下文感知扫描
            jira_list = ctx.get('jira') or []
            jira_first = jira_list[0] if isinstance(jira_list, list) and jira_list else (jira_list if isinstance(jira_list, str) else None)
            consistency = contract_consistency_scan(cr_num, jira_first, candidates, _gget, current_owner=ctx.get('owner'))
            if consistency:
                ctx['contract_consistency'] = consistency
    except Exception as e:
        ctx['contract_change_scan_error'] = str(e)

    # v2.7.0 cherry-pick 复用识别（优先于复杂度分档，有 reuse 的覆盖 level）
    if _cherry_pick_detect is not None:
        try:
            cp_info = _cherry_pick_detect(cr_num)
            ctx['cherry_pick'] = cp_info
        except Exception as e:
            ctx['cherry_pick_scan_error'] = str(e)
            cp_info = None
    else:
        cp_info = None

    # v2.7.0 复杂度评级（三档 + cherry_pick_reuse 覆盖）
    if _complexity_assess is not None:
        try:
            comp = _complexity_assess(ctx)
            if cp_info and cp_info.get('reuse'):
                comp['level'] = 'cherry_pick_reuse'
                comp.setdefault('signals', []).append('cherry_pick_reuse')
                comp['reason'] = '识别为 CR {0} 的 cherry-pick ，diff 全等，复用基线评审'.format(cp_info.get('base_cr'))
            ctx['complexity'] = comp
            # 启动 banner
            badge_map = {'lite': '\U0001f7e2', 'standard': '\U0001f7e1', 'deep': '\U0001f534', 'cherry_pick_reuse': '\U0001f501'}
            print('[gerrit-review v2.7.0] complexity={0} {1}  signals={2}  reason={3}'.format(
                badge_map.get(comp.get('level'), '?'), comp.get('level'),
                comp.get('signals'), comp.get('reason')
            ), file=sys.stderr)
        except Exception as e:
            ctx['complexity_scan_error'] = str(e)

    return ctx


REQUIRED_DIMS = [
    'solid', 'security', 'performance',
    'cpp_concurrency_stl',  # 可 scanned=false 但必须有 key
    'error_handling', 'code_quality_style', 'automotive', 'privacy_compliance',
    'platform_design',  # v2.5.1 新增：允许 scanned=false（同 cpp_concurrency_stl），但必须有 key
    'selinux_policy',   # v2.5.5 新增：上下文门控维度，允许 scanned=false，命中 sepolicy 文件时强制 scanned=true
]
COVER_REQUIRED_KEYWORDS = ['SOLID', '安全', '性能', '错误处理', '代码质量', '车载', '隐私合规']
# v2.5.1 新增：platform_design 不强制出现在 cover（避免老 LLM 输出被拒），但推荐出现
# v2.5.5 新增：selinux_policy 同属「key 必填但允许 scanned=false」（仅 SELinux 上下文才强制扫）
DIMS_ALLOW_NOT_SCANNED = {'cpp_concurrency_stl', 'platform_design', 'selinux_policy'}

# 本地定制（与 gerrit-review 同源）：严重度↔分数一致性门禁关键词，命中即视为「不可合入」级阻断问题，强制 -2。
_BLOCKER_KEYWORDS = (
    'MERGE-CONFLICT', 'MERGE_CONFLICT', '合并冲突', '冲突标记',
    '<<<<<<<', '>>>>>>>', '=======',
    'BUILD-FAIL', 'BUILD_FAIL', '预编译失败', '编译失败', '构建失败',
)


def _comment_text_blob(c):
    """把一条 comment 的可读字段拼成大字符串，供关键词匹配。"""
    if not isinstance(c, dict):
        return ''
    parts = []
    for k in ('rule', 'title', 'message', 'detail', 'dimension'):
        v = c.get(k)
        if isinstance(v, str):
            parts.append(v)
    return ' '.join(parts)


def check_score_severity_gate(review):
    """本地定制硬门禁：严重度与最终 score 必须自洽。

    任何档位通用，杜绝「识别出 P0 / 合并冲突 / 编译失败，却给 +1/+2」这种自相矛盾投票。
    返回 errors 列表（空表示通过）。

    规则：
      G1. comments 或 unresolved_issues 中存在 P0 级问题 → score 必须 ≤ -1（禁止正分）。
      G2. comments 中命中合并冲突标记 / 编译失败等阻断关键词 → score 必须 == -2。
      G3. comments 或 unresolved_issues 中存在 P1 级问题 → score 必须 ≤ -1（禁止正分）。
    """
    errs = []
    score = review.get('score')
    if not isinstance(score, int):
        return errs  # score 本身非法由其它校验负责

    comments = [c for c in (review.get('comments') or []) if isinstance(c, dict)]
    unresolved = [u for u in (review.get('unresolved_issues') or []) if isinstance(u, dict)]

    has_p0 = any(c.get('level') == 'P0' for c in comments) or \
             any(u.get('level') == 'P0' for u in unresolved)
    has_p1 = any(c.get('level') == 'P1' for c in comments) or \
             any(u.get('level') == 'P1' for u in unresolved)

    # G2: 阻断关键词（合并冲突 / 编译失败）→ 必须 -2
    blocker_hit = None
    for c in comments:
        blob = _comment_text_blob(c).upper()
        for kw in _BLOCKER_KEYWORDS:
            if kw.upper() in blob:
                blocker_hit = (c.get('rule') or c.get('title') or kw, kw)
                break
        if blocker_hit:
            break
    if blocker_hit and score != -2:
        errs.append(
            'SEV-GATE G2：检测到阻断级问题（{0} / 命中关键词「{1}」，如合并冲突标记/编译失败），'
            'score 必须为 -2，实际 {2}。源码含未解决冲突标记或构建失败时绝不允许 +1/+2。'.format(
                blocker_hit[0], blocker_hit[1], score))

    # G1: 有 P0 → 必须 ≤ -1
    if has_p0 and score > -1:
        errs.append(
            'SEV-GATE G1：评审含 P0 级问题，score 必须 ≤ -1（-1 或 -2），实际 {0}。'
            '识别出 P0 却给正分属自相矛盾投票。'.format(score))

    # G3: 有 P1 → 必须 ≤ -1
    if has_p1 and score > -1:
        errs.append(
            'SEV-GATE G3：评审含 P1 级问题，score 必须 ≤ -1，实际 {0}。'
            'P1 未闭环不允许 +1/+2 放行。'.format(score))

    return errs


class ReviewQualityError(Exception):
    pass

def validate_review_json(review, ctx=None):
    """硬校验：LLM 产出 review.json 必须含 8 大维度扫描记录 + cover 含关键词。
    v2.7.0 按复杂度档位分叉：
      - lite：dimensions_scanned / rule_check_table 可为空，cover ≥ 80 字
      - standard：完整 8 维校验（同 v2.6.0）
      - deep：追加 P0/P1 三问 + cover ≥ 400 字
      - cherry_pick_reuse：仅要求 cherry_pick_info.reuse=true + base_cr 非空
    否则拒绝 POST，避免 cron 不调 LLM 裸投票。"""
    errors = []
    cover_text = review.get('cover', '') or ''
    score = review.get('score')

    # v2.5.2：cover 字段只能写「纯结论散文」，禁止模型自带整段 skill 模板结构
    # （抬头/徽章/顶部结论 H3/8 大维度矩阵/Preflight/落款由 cover_template 统一渲染）。
    # 命中任一模板结构标记即拒绝 POST，杜绝「模型自己写模板」。
    _TEMPLATE_SIGNS = (
        '## 🤖 enhanced_code_review', '## 🤖 gerrit-review',
        '### 评审结论：', '### 8 大维度扫描', '### 7 大维度扫描',
        '### 📊 Preflight', '*🤖 由 enhanced_code_review', '*🤖 由 gerrit-review',
    )
    _sign_hit = [m for m in _TEMPLATE_SIGNS if m in cover_text]
    if _sign_hit:
        raise ReviewQualityError(
            'v2.5.2：cover 字段只能写纯结论散文，禁止自带 skill 模板结构（命中 {0}）。'
            '抬头/徽章/8 大维度矩阵/Preflight/落款由 cover_template 自动渲染，'
            'LLM 只需写「### 📝 LLM 评审结论」之下的散文内容。'.format(_sign_hit)
        )

    level = (
        review.get('complexity_level')
        or (ctx.get('complexity', {}).get('level') if ctx else None)
        or 'standard'
    )
    # cherry_pick_reuse 检查（review.json 显式声明优先）
    if isinstance(review.get('cherry_pick_info'), dict) and review['cherry_pick_info'].get('reuse'):
        level = 'cherry_pick_reuse'

    # --- 档位分叉起点 ---
    if level == 'cherry_pick_reuse':
        cpi = review.get('cherry_pick_info') or {}
        if not cpi.get('reuse'):
            errors.append('cherry_pick_reuse 档要求 cherry_pick_info.reuse=true')
        if not cpi.get('base_cr'):
            errors.append('cherry_pick_reuse 档要求 cherry_pick_info.base_cr 非空')
        if score not in (-2, -1, 1, 2):
            errors.append('score 必须是 -2/-1/+1/+2，实际: {0}'.format(score))
        if not cover_text:
            errors.append('cover 为空')
        if errors:
            raise ReviewQualityError('\n  - '.join(['review.json 质量校验失败（cherry_pick_reuse 档）：'] + errors))
        return

    if level == 'lite':
        # Lite 放宽：不强制 dimensions_scanned / rule_check_table；cover ≥ 80 字
        if score not in (-2, -1, 1, 2):
            errors.append('score 必须是 -2/-1/+1/+2，实际: {0}'.format(score))
        if not cover_text:
            errors.append('cover 为空')
        elif len(cover_text) < 80:
            errors.append('Lite 档 cover 长度不足 80 字符（实际 {0}）'.format(len(cover_text)))
        # 本地定制：严重度↔分数一致性硬门禁（lite 档也适用）
        errors.extend(check_score_severity_gate(review))
        if errors:
            raise ReviewQualityError('\n  - '.join(['review.json 质量校验失败（lite 档）：'] + errors))
        return

    # standard / deep 走原本完整校验
    dims = review.get('dimensions_scanned')
    if not isinstance(dims, dict):
        errors.append('缺少 dimensions_scanned 字段（LLM 8 大维度扫描记录）')
    else:
        for d in REQUIRED_DIMS:
            if d not in dims:
                errors.append(f'dimensions_scanned 缺少维度: {d}')
            elif d not in DIMS_ALLOW_NOT_SCANNED:
                if not dims[d].get('scanned'):
                    errors.append(f'维度 {d} 必须 scanned=true（实际：{dims[d].get("scanned")}）')
        # v2.4.0 多语言分派检查：按 ctx['languages'] 动态判断
        if ctx and 'languages' in ctx:
            for lang_info in ctx['languages']:
                lang = lang_info.get('lang', '')
                if lang == 'C++':
                    cpp = dims.get('cpp_concurrency_stl', {}) if isinstance(dims, dict) else {}
                    if not cpp.get('scanned'):
                        errors.append('C++ 改动 CR 必须 scanned cpp_concurrency_stl（v2.4.0 硬规则）')
                elif lang == 'Java/Kotlin':
                    java = dims.get('java_concurrency_collection', {}) if isinstance(dims, dict) else {}
                    if not java.get('scanned'):
                        errors.append('Java/Kotlin 改动 CR 必须 scanned java_concurrency_collection（v2.4.0 硬规则）')
                elif lang == 'C':
                    c = dims.get('c_concurrency', {}) if isinstance(dims, dict) else {}
                    if not c.get('scanned'):
                        errors.append('C 改动 CR 必须 scanned c_concurrency（v2.4.0 硬规则）')
                elif lang == 'SELinux':
                    sel = dims.get('selinux_policy', {}) if isinstance(dims, dict) else {}
                    if not sel.get('scanned'):
                        errors.append('SELinux 策略改动 CR 必须 scanned selinux_policy（v2.5.5 上下文门控硬规则）')

    # v2.4.2 rule_check_table 强制检查（逐条规则扫描结果）
    if ctx and 'languages' in ctx and ctx['languages']:
        rule_table = review.get('rule_check_table')
        if not isinstance(rule_table, dict):
            errors.append('rule_check_table 字段缺失或格式错误（v2.4.2 强制要求）')
        else:
            for lang_info in ctx['languages']:
                lang = lang_info.get('lang', '')
                rule_ids = lang_info.get('rule_ids', [])
                lang_table = rule_table.get(lang, {})
                if not lang_table:
                    errors.append(f'{lang} 改动 CR 必须在 rule_check_table 中列出逐条扫描结果（v2.4.2）')
                else:
                    for rid in rule_ids:
                        if rid not in lang_table:
                            errors.append(f'rule_check_table[{lang}] 缺少规则 {rid}')
                        else:
                            entry = lang_table[rid]
                            if not isinstance(entry, dict):
                                errors.append(f'rule_check_table[{lang}][{rid}] 必须是 dict（含 scanned/findings）')
                            elif 'scanned' not in entry:
                                errors.append(f'rule_check_table[{lang}][{rid}] 缺少 scanned 字段')

    # v2.5.0: reply_disposition 校验（增量评审模式）
    if ctx and ctx.get('prior_review_context', {}).get('has_prior_review'):
        reply_disp = review.get('reply_disposition')
        if not isinstance(reply_disp, list) and not isinstance(reply_disp, dict):
            # 有 prior review 时必须有 reply_disposition
            errors.append('有历史评审记录但缺少 reply_disposition 字段（v2.5.0 增量评审要求）')

    # v2.5.1: platform_design 维度定级守卫——软规则仅 P2/P3
    for c in (review.get('comments') or []):
        if (c.get('dimension') == 'platform_design') and (c.get('level') in ('P0', 'P1')):
            errors.append(f'platform_design 维度不允许 {c.get("level")}，仅允许 P2/P3（v2.5.1 软规则）。如果是真的 P0/P1 问题请归类到其他维度（SOLID/安全/错误处理等）。')

    # v2.6.0 闭环增强机制（CL-1 ~ CL-6）

    # CL-1 + CL-2: reply_disposition 中 temporary_with_jira 类别必须有 unresolved_issues 配对
    if ctx and ctx.get('prior_review_context', {}).get('has_prior_review'):
        reply_disp = review.get('reply_disposition') or []
        unresolved = review.get('unresolved_issues') or []
        if isinstance(reply_disp, list):
            for rd in reply_disp:
                classification = rd.get('reply_classification', '')
                disposition = rd.get('disposition', '')
                if classification == 'temporary_with_jira' or disposition == 'downgraded_by_temporary':
                    if not unresolved:
                        errors.append('CL-2: 存在 temporary_with_jira / downgraded_by_temporary 处置但 unresolved_issues 为空（v2.6.0 闭环增强）')
                        break
                if classification == 'temporary_no_jira':
                    # 此类禁止豁免；如果 disposition 仍为 dropped/downgraded，提示错误
                    if disposition in ('dropped_by_reply', 'downgraded_by_note', 'downgraded_by_temporary'):
                        errors.append(f"CL-1: reply_classification=temporary_no_jira 不可豁免，但 disposition={disposition}（v2.6.0）")
                if classification == 'tradeoff_no_data':
                    if disposition in ('dropped_by_reply', 'downgraded_by_note', 'downgraded_by_temporary'):
                        errors.append(f"CL-1: reply_classification=tradeoff_no_data 不可豁免（取舍式无量化依据），但 disposition={disposition}（v2.6.0）")

    # CL-2: unresolved_issues schema 校验
    unresolved = review.get('unresolved_issues')
    if unresolved is not None:
        if not isinstance(unresolved, list):
            errors.append('CL-2: unresolved_issues 必须是数组（v2.6.0）')
        else:
            required_fields = ['level', 'path', 'title', 'rationale_accepted', 'tracking_jira', 'risk_summary']
            for i, u in enumerate(unresolved):
                if not isinstance(u, dict):
                    errors.append(f'CL-2: unresolved_issues[{i}] 必须是 object')
                    continue
                for f in required_fields:
                    if not u.get(f):
                        errors.append(f'CL-2: unresolved_issues[{i}] 缺少字段 {f}（v2.6.0）')
                # tracking_jira 必须像 Jira 编号
                jira = u.get('tracking_jira', '')
                if jira and not re.match(r'^[A-Z]+[0-9A-Z]*-\d+$', jira):
                    errors.append(f'CL-2: unresolved_issues[{i}].tracking_jira={jira!r} 不像合法 Jira 编号')

    # CL-3 + CL-6 上下文感知：契约变更但 contract_consistency 缺失时提示
    contract_changes = (ctx or {}).get('contract_change_candidates') or []
    if contract_changes:
        cc = (ctx or {}).get('contract_consistency') or {}
        if not cc.get('assessment'):
            # 不阻断 POST，但记录警告（让 LLM 在 cover 中说明）
            pass  # context_aware_ok / single_side_p2 / mismatch_p0 由 LLM 在 review 中体现

    cover_text = review.get('cover', '')
    if not cover_text:
        errors.append('cover 为空')
    else:
        missing = [k for k in COVER_REQUIRED_KEYWORDS if k not in cover_text]
        if missing:
            errors.append(f'cover 缺少维度关键词: {missing}')

    # CL-4: 带病合入 cover 段强制（依赖 cover_text，放在后面）
    if unresolved:
        if '带病合入说明' not in cover_text and '⚠️ 带病合入' not in cover_text:
            errors.append('CL-4: 含未闭环问题但 cover 缺少「带病合入说明」段（v2.6.0）')

    score = review.get('score')
    if score not in (-2, -1, 1):
        errors.append(f'score 必须是 -2/-1/+1，实际: {score}（禁止 0/None 裸投）')
    if cover_text and len(cover_text) < 200:
        errors.append(f'cover 长度不足 200 字符（实际 {len(cover_text)}），拒绝裸评审')

    # v2.7.0 Deep 档追加校验：每 P0/P1 必须有三问 + cover ≥ 400 字
    if level == 'deep':
        if cover_text and len(cover_text) < 400:
            errors.append('Deep 档 cover 长度不足 400 字符（实际 {0}）'.format(len(cover_text)))
        # 每 P0/P1 comment 必须有 adversarial_qa
        p_high = [c for c in (review.get('comments') or [])
                  if isinstance(c, dict) and c.get('level') in ('P0', 'P1')]
        qa_list = review.get('adversarial_qa') or []
        if p_high and not isinstance(qa_list, list):
            errors.append('Deep 档：P0/P1 项需 adversarial_qa（三问自检）但字段缺失')
        elif p_high and len(qa_list) < len(p_high):
            errors.append('Deep 档：P0/P1 项三问不全（{0} 项 P0/P1 / {1} 项 QA）'.format(
                len(p_high), len(qa_list)
            ))

    # 本地定制：严重度↔分数一致性硬门禁（standard / deep 通用）
    errors.extend(check_score_severity_gate(review))

    if errors:
        raise ReviewQualityError('\n  - '.join(['review.json 质量校验失败：'] + errors))

def post_build_failed(cr_num, build_failure, revision='current', dry=False):
    """v2.6.0 BUILD-FAIL-1：预编译失败快通道——直接 POST -2 + 固定文案，不走 LLM。"""
    cover = BUILD_FAIL_COVER_TEMPLATE.format(evidence=build_failure.get('evidence', '预编译失败'))
    preview = {
        'cr': cr_num,
        'rev': revision,
        'score': -2,
        'mode': 'skip_build_failed (BUILD-FAIL-1)',
        'failed_labels': build_failure.get('failed_labels', []),
        'cover_len': len(cover),
    }
    print('=== BUILD-FAIL-1 fast-track POST preview ===')
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if dry:
        print('\n[DRY] skipped real POST')
        return preview
    s, resp = post_review(cr_num, revision, cover, -2, {})
    print(f'\nstatus: {s}')
    print(json.dumps(resp, ensure_ascii=False, indent=2) if isinstance(resp, dict) else (resp[:500] if isinstance(resp, str) else resp))
    return {'status': s, 'resp': resp}


def post_from_review_json(cr_num, review_json_path, score_override=None, dry=False,
                          ctx_path=None, auto_cover=True, allow_raw_cover=False):
    """把 LLM 产出的 review.json POST 回 Gerrit。post 前强制质量校验。

    v2.5.2：回帖 cover **必须**经 skill 模板渲染（与 gerrit_post.py 同源），
    禁止裸贴模型自由 cover。缺 ctx 或 --no-auto-cover 时必须显式 --allow-raw-cover。
    """
    review = json.load(open(review_json_path, "r", encoding="utf-8"))

    cr = str(review.get("cr") or cr_num)
    rev = review.get("revision") or "current"
    score = score_override if score_override is not None else review.get("score", 0)
    cover = review.get("cover", "")

    # 加载 ctx（v2.4.0 多语言分派需要 + v2.5.2 模板渲染需要）
    ctx = None
    if ctx_path and os.path.exists(ctx_path):
        try:
            ctx = json.load(open(ctx_path))
        except Exception:
            pass

    # v2.5.4 stale-revision 修复：POST 前以 Gerrit 实时 current_revision 为准，
    # 防止 review.json / ctx.json 残留旧 PS sha 导致贴回陈旧 patchset（cover revision
    # 标错 + 基于旧代码误判，如 1049671 PS2 被按 PS1 评成 -1）。
    try:
        live_sha, live_ps = get_current_revision(cr)
    except Exception:
        live_sha, live_ps = None, None
    if live_sha and rev not in (live_sha, "current"):
        print("[warn] stale-revision: review.json revision={0} ≠ Gerrit 当前 current_revision={1}（PS{2}）；"
              "已自动改为贴回最新 PS。".format((rev or "")[:12], live_sha[:12], live_ps), file=sys.stderr)
        rev = live_sha
        review["revision"] = live_sha
        if ctx is not None and ctx.get("revision") != live_sha:
            print("[warn] stale-revision: ctx.revision={0} 也已同步为 {1}（cover 元信息以最新 PS 为准）。".format(
                  (ctx.get("revision") or "")[:12], live_sha[:12]), file=sys.stderr)
            ctx["revision"] = live_sha
    elif live_sha and ctx is not None and ctx.get("revision") and ctx.get("revision") != live_sha:
        # rev 本身没问题（=current 或已对齐），但 ctx 残留旧 sha，仍同步 cover 元信息
        print("[warn] stale-revision: ctx.revision={0} ≠ current={1}，已同步。".format(
              (ctx.get("revision") or "")[:12], live_sha[:12]), file=sys.stderr)
        ctx["revision"] = live_sha

    # 硬校验
    try:
        validate_review_json(review, ctx=ctx)
    except ReviewQualityError as e:
        print(f"\n❌ REVIEW QUALITY VALIDATION FAILED:\n{e}\n", file=sys.stderr)
        print('该 review.json 不符合评审质量要求，POST 已拒绝。', file=sys.stderr)
        print('原因：Gerrit cron 必须调用 LLM 多维度评审，禁止裸投票。', file=sys.stderr)
        sys.exit(3)

    # v2.5.2：cover 统一经 skill 模板渲染（抬头/徽章/8 大维度矩阵/Preflight/落款由模板生成，
    # cherry-pick 自动走 cherry-pick 模板）；缺 ctx / 显式 --no-auto-cover 时必须 --allow-raw-cover。
    if not auto_cover:
        if not allow_raw_cover:
            print("[error] --no-auto-cover 会绕过 skill 模板；如确需裸 cover 请显式加 --allow-raw-cover。", file=sys.stderr)
            sys.exit(4)
        print("[warn] --no-auto-cover + --allow-raw-cover：使用 review.json 原始 cover（绕过 skill 模板）。", file=sys.stderr)
    elif _render_from_review_and_ctx is None:
        if not allow_raw_cover:
            print("[error] cover_template 模块不可用，无法渲染 skill 模板；如确需裸 cover 请加 --allow-raw-cover。", file=sys.stderr)
            sys.exit(4)
        print("[warn] cover_template 不可用 + --allow-raw-cover：退回 review.json 原 cover。", file=sys.stderr)
    elif ctx is None:
        if not allow_raw_cover:
            print("[error] post 模式未传 --ctx，auto-cover 无法渲染 skill 模板。", file=sys.stderr)
            print("        请用 --ctx 传 ctx.json（与 --prepare -o 输出对齐）；如确需裸 cover 加 --allow-raw-cover。", file=sys.stderr)
            sys.exit(4)
        print("[warn] 未传 --ctx + --allow-raw-cover：使用 review.json 原始 cover（绕过 skill 模板）。", file=sys.stderr)
    else:
        cover = _render_from_review_and_ctx(review, ctx)

    # comments：transform LLM 输出到 Gerrit 格式
    comments = {}
    for c in review.get("comments", []):
        path = c["path"]
        if path == "/COMMIT_MSG":
            # 挪到 cover 里
            cover += f"\n\n[commit message] {c.get('message', '')}"
            continue
        comments.setdefault(path, []).append({
            "line": c["line"],
            "message": c.get("message", c.get("title", "")),
            "unresolved": c.get("unresolved", True),
            "level": c.get("level"),
        })

    count = sum(len(v) for v in comments.values())
    preview = {
        "cr": cr, "rev": rev, "score": score,
        "inline_count": count, "cover_len": len(cover),
        "paths": list(comments.keys()),
    }
    print("=== POST preview ===")
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    if dry:
        print("\n[DRY] skipped real POST")
        return preview

    s, resp = post_review(cr, rev, cover, score, comments)
    print(f"\nstatus: {s}")
    print(json.dumps(resp, ensure_ascii=False, indent=2) if isinstance(resp, dict) else resp[:500])
    return {"status": s, "resp": resp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cr", help="CR number")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--prepare", action="store_true", help="只输出 LLM 评审所需上下文（JSON 到 stdout）")
    g.add_argument("--post", metavar="REVIEW_JSON", help="从 LLM 产出的 review.json POST 回 Gerrit")
    g.add_argument("--build-fail-fast", action="store_true", help="v2.6.0 BUILD-FAIL-1：检测到预编译失败直接快通道 POST -2（不走 LLM）")
    ap.add_argument("--dry", action="store_true", help="不真发，仅预览")
    ap.add_argument("--score", type=int, default=None, help="覆盖 review.json 中的 score")
    ap.add_argument("-o", "--output", help="prepare 模式输出到文件")
    ap.add_argument("--ctx", default=None, help="post 模式：传 ctx.json（质量校验 + v2.5.2 cover 模板渲染）")
    ap.add_argument("--no-auto-cover", action="store_true",
                    help="v2.5.2：post 模式跳过 skill 模板渲染，直接用 review.json 原 cover（需配 --allow-raw-cover）")
    ap.add_argument("--allow-raw-cover", action="store_true",
                    help="v2.5.2：显式允许绕过 skill 模板使用裸 cover（缺 --ctx / --no-auto-cover 时必须叠加）")
    ap.add_argument("--force-level", default=None,
                    choices=['lite', 'standard', 'deep'],
                    help="v2.7.0：强制指定复杂度档位（覆盖 complexity_assess 结果）")
    a = ap.parse_args()

    if a.post:
        post_from_review_json(a.cr, a.post, a.score, a.dry, ctx_path=a.ctx,
                              auto_cover=not a.no_auto_cover, allow_raw_cover=a.allow_raw_cover)
    elif a.build_fail_fast:
        # v2.6.0 BUILD-FAIL-1 快通道
        d = get_cr_detail(a.cr)
        if not isinstance(d, dict):
            print(f'拉 CR 失败: {d}', file=sys.stderr); sys.exit(2)
        bf = detect_build_failure(d)
        if not bf:
            print(f'CR {a.cr} 未检测到预编译失败 (Verified-1 / Prebuild-Check-1)，不适用 BUILD-FAIL-1 快通道。', file=sys.stderr)
            sys.exit(4)
        post_build_failed(a.cr, bf, revision=d.get('current_revision', 'current'), dry=a.dry)
    else:
        ctx = prepare_context(a.cr)
        # v2.7.0 --force-level：覆盖复杂度评级
        if a.force_level and isinstance(ctx, dict):
            ctx.setdefault('complexity', {})
            ctx['complexity']['level'] = a.force_level
            ctx['complexity'].setdefault('signals', []).append('force_level:' + a.force_level)
            ctx['complexity']['reason'] = '用户 --force-level {0} 强制覆盖'.format(a.force_level)
            print('[gerrit-review v2.7.0] --force-level {0} 生效'.format(a.force_level), file=sys.stderr)
        out = json.dumps(ctx, ensure_ascii=False, indent=2)
        if a.output:
            open(a.output, "w", encoding="utf-8").write(out)
            print(f"prepared -> {a.output}")
            print(f"  P0={ctx['audit']['summary'].get('P0',0)} "
                  f"P1={ctx['audit']['summary'].get('P1',0)} "
                  f"P2={ctx['audit']['summary'].get('P2',0)} "
                  f"P3={ctx['audit']['summary'].get('P3',0)}")
            print(f"  consistency findings: {sum(len(v) for v in ctx['consistency'].values() if isinstance(v, list))}")
            # v2.5.0: 输出评审决策
            decision = ctx.get('review_decision', {})
            if decision:
                print(f"  v2.5.1 decision: mode={decision.get('mode')} should_review={decision.get('should_review')} incremental={decision.get('is_incremental')}")
                print(f"  reason: {decision.get('reason','')}")
        else:
            print(out)


if __name__ == "__main__":
    main()
