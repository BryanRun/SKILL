"""共享的 Gerrit 客户端：认证、GET、POST、diff 解析。
所有 scripts 统一 import 本模块。

凭据：必须通过环境变量提供，**不得**在代码或技能包中内置任何账号或 HTTP 密码。
"""
import os, json, re, urllib3, urllib.parse
import requests
from requests.auth import HTTPBasicAuth

urllib3.disable_warnings()

BASE = os.environ.get("GERRIT_BASE", "https://gerrit.auto-link.com.cn")

# 合法 Jira 前缀（10 个项目）；CL 保留但 CL-<数字> 单独处理
_JIRA_PREFIXES = ("CHYT1V", "BAIC", "KP31", "FL1", "FL2", "FL3", "T1V", "D01", "CHYT12A", "CHYMIFA")
# 匹配所有可能的前缀-数字组合（含不合规形式；后续 extract_jira 做二次过滤）
JIRA_RE = re.compile(
    r"(" + "|".join(re.escape(p) for p in _JIRA_PREFIXES) + r")-(\d+)"
    r"|"
    r"(CL-[A-Z0-9\-]+)"   # CL 前缀格式特殊
    r"|"
    r"(N80-\d+)"           # 历史前缀保留
)

# 占位号判定：数字部分全为 0（如 000）或以 0 开头后跟更多数字（如 0001、007）
_PLACEHOLDER_RE = re.compile(r"^0+$|^0\d+$")


def _get_auth():
    """从环境变量读取 Gerrit HTTP 凭证；未配置则立即失败并提示。"""
    user = os.environ.get("GERRIT_USER", "").strip()
    pwd = os.environ.get("GERRIT_HTTP_PASSWORD", "").strip()
    if not user or not pwd:
        raise RuntimeError(
            "Gerrit 凭据未配置：请设置环境变量 GERRIT_USER 与 GERRIT_HTTP_PASSWORD "
            "（Gerrit 个人设置中的 HTTP 密码）。技能包不含任何默认账号或密钥，"
            "须由使用方自行配置。"
        )
    return HTTPBasicAuth(user, pwd)


def _strip(t):
    if t.startswith(")]}'"):
        t = t[4:]
    return t


def gget(path, raw=False):
    r = requests.get(f"{BASE}{path}", auth=_get_auth(), verify=False, timeout=30)
    t = _strip(r.text)
    if raw:
        return r.status_code, t
    try:
        return r.status_code, json.loads(t)
    except Exception:
        return r.status_code, t


def gpost(path, body):
    r = requests.post(
        f"{BASE}{path}",
        auth=_get_auth(),
        verify=False,
        timeout=30,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )
    t = _strip(r.text)
    try:
        return r.status_code, json.loads(t)
    except Exception:
        return r.status_code, t


def get_cr_detail(cr):
    """取 CR 详情，含 current_revision, files, commit message."""
    s, d = gget(
        f"/a/changes/{cr}/detail"
        "?o=CURRENT_REVISION&o=CURRENT_COMMIT&o=CURRENT_FILES"
        "&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS"
    )
    return d


def get_file_diff(cr, rev, path):
    """取单文件结构化 diff (intraline=true)."""
    enc = urllib.parse.quote(path, safe="")
    s, d = gget(f"/a/changes/{cr}/revisions/{rev}/files/{enc}/diff?intraline=true")
    return d


def iter_diff_lines(diff):
    """把 diff content[] 拉平为 (old_line, new_line, kind, text) 序列。
    kind: 'ctx' 不变 / 'del' 删除 / 'add' 新增。
    """
    old_line, new_line = 1, 1
    for chunk in diff.get("content", []):
        if "ab" in chunk:
            for ln in chunk["ab"]:
                yield (old_line, new_line, "ctx", ln)
                old_line += 1
                new_line += 1
        if "a" in chunk:
            for ln in chunk["a"]:
                yield (old_line, None, "del", ln)
                old_line += 1
        if "b" in chunk:
            for ln in chunk["b"]:
                yield (None, new_line, "add", ln)
                new_line += 1


def post_review(cr, rev, message, score, comments):
    """
    comments: {path: [{line: N, message: str, level: P0|P1|P2|P3}]}
    """
    body_comments = {}
    for path, items in comments.items():
        body_comments[path] = []
        for c in items:
            msg = c["message"]
            if "level" in c and not msg.startswith("["):
                msg = f"[{c['level']}] {msg}"
            body_comments[path].append({
                "line": c["line"],
                "message": msg,
                "unresolved": c.get("unresolved", True),
            })

    body = {
        "message": message,
        "labels": {"Code-Review": score},
        "comments": body_comments,
        "notify": "OWNER_REVIEWERS",
    }
    return gpost(f"/a/changes/{cr}/revisions/{rev}/review", body)


def extract_jira(text):
    """提取合规的 Jira 号列表。

    合规条件：前缀属 _JIRA_PREFIXES / CL / N80，且数字部分非占位（非全 0、非 0 开头）。
    返回 list[str]，如 ['CHYT1V-1234', 'FL2-56']。
    """
    if not text:
        return []
    valid = set()
    for m in JIRA_RE.finditer(text):
        prefix_num = m.group(1)  # 主前缀（10 个项目之一）
        num_part = m.group(2)    # 数字部分
        cl_full = m.group(3)     # CL-xxx
        n80_full = m.group(4)    # N80-xxx
        if prefix_num and num_part:
            if _PLACEHOLDER_RE.match(num_part):
                continue
            valid.add(f"{prefix_num}-{num_part}")
        elif cl_full:
            valid.add(cl_full)
        elif n80_full:
            valid.add(n80_full)
    return list(valid)


# bare_number 误报豁免（v2.1.2）：
# 1) commit message 中以下「明确指向链接资源」的中文段标题，整段（从段标题到下一个【...】段标题或文末）跳过 bare_number 检测；
#    占位号（合法前缀 + 占位数字）仍在所有段落生效。
# 2) 任意段落里被 URL（http(s)://... / ftp://... / file:// / www....）覆盖的字符位置一律剔除后再扫 bare_number。
# 触发动机：奇瑞规范九段中【开发自测视频】等链接段经常含 10~14 位时间戳与文件 ID，旧版会误标为「缺前缀的 Jira」。
_VIDEO_LINK_HEADERS = (
    "开发自测视频", "测试自测视频", "验收视频", "录屏", "录像", "录制视频",
    "关联视频", "关联链接", "关联文档", "下载链接", "评审视频",
)
_SECTION_HEAD_RE = re.compile(r"【([^】]+)】")
_URL_STRIP_RE = re.compile(r"(?:https?|ftp|file)://\S+|\bwww\.\S+", re.IGNORECASE)


def _bare_number_exempt_ranges(text):
    """返回需跳过 bare_number 检测的字符 [start, end) 范围列表（半开区间）。

    范围来自两类：
      - 链接段整段（从段标题行开始到下一个【...】段标题或文末）
      - URL 字面量（http(s)://、ftp://、file://、www. 前缀）
    """
    spans = []
    if not text:
        return spans
    # 链接段：以段标题行的起始为段头；下一个【...】行视为下一段
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)
    line_starts.append(len(text) + 1)

    head_iter = list(_SECTION_HEAD_RE.finditer(text))
    line_starts_arr = line_starts
    # 仅识别「行首附近」的段头（允许前置空格、引导符），避免把行内的【...】误判为段头
    line_head_positions = []  # (head_start, head_name)
    for m in head_iter:
        head_pos = m.start()
        # 找到 head_pos 所在行起点，校验从行首到 head_pos 之间只有空白
        # 二分会更快；这里 commit message 段头数量很少，线性即可
        for ls in line_starts_arr:
            if ls > head_pos:
                break
            line_start_for_head = ls
        prefix = text[line_start_for_head:head_pos]
        if prefix.strip() == "":
            line_head_positions.append((line_start_for_head, m.group(1)))

    for idx, (start, name) in enumerate(line_head_positions):
        if name in _VIDEO_LINK_HEADERS:
            end = line_head_positions[idx + 1][0] if idx + 1 < len(line_head_positions) else len(text)
            spans.append((start, end))

    # URL 字面量：在所有段落里都豁免
    for u in _URL_STRIP_RE.finditer(text):
        spans.append((u.start(), u.end()))
    return spans


def _pos_in_spans(pos, spans):
    for s, e in spans:
        if s <= pos < e:
            return True
    return False


def extract_jira_violations(text):
    """检测 Jira 号不合规情况，返回 list[dict]。

    两类不合规：
    1. 占位号：前缀合法但数字部分为占位（000 / 0001 等）
    2. 纯数字：形如独立的 5+ 位纯数字串（疑似缺少项目前缀）
       —— v2.1.2 起跳过【开发自测视频】等链接段及行内 URL 中的纯数字，避免对时间戳/文件 ID 误报。
    """
    if not text:
        return []
    violations = []
    for m in JIRA_RE.finditer(text):
        prefix_num = m.group(1)
        num_part = m.group(2)
        if prefix_num and num_part and _PLACEHOLDER_RE.match(num_part):
            violations.append({
                "type": "placeholder",
                "raw": "{0}-{1}".format(prefix_num, num_part),
                "detail": "Jira 号 {0}-{1} 为占位号（数字部分 {1} 不合规），请替换为真实 Jira 工单编号。".format(
                    prefix_num, num_part
                ),
            })
    # 纯数字串检测（5+ 位独立数字，排除已被合法前缀匹配的位置 + 链接段 / URL 内位置）
    covered = set()
    for m in JIRA_RE.finditer(text):
        covered.update(range(m.start(), m.end()))
    exempt_spans = _bare_number_exempt_ranges(text)
    for m in re.finditer(r"\b(\d{5,})\b", text):
        if m.start() in covered:
            continue
        if _pos_in_spans(m.start(), exempt_spans):
            continue
        violations.append({
            "type": "bare_number",
            "raw": m.group(1),
            "detail": "发现纯数字 {0}（疑似缺少项目前缀），请补充为 CHYT1V-xxx / FL2-xxx 等合规格式。".format(
                m.group(1)
            ),
        })
    return violations


def find_related_crs(jira):
    """按 Jira 号查同组 CR."""
    q = urllib.parse.quote(f"message:{jira}")
    s, data = gget(f"/a/changes/?q={q}&n=20")
    if not isinstance(data, list):
        return []
    return data
