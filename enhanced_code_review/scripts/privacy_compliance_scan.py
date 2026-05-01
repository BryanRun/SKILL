"""privacy_compliance_scan: 隐私合规候选扫描（P0 维度，强门控，高精确率）。

设计目标（2026-04-21 团队约定）：
- 隐私合规按 P0 计，触发门槛必须**极严**，否则会误杀大量无害代码。
- 本扫描器只负责**门控 A（数据）+ 门控 B（去向）共现候选**，
  不负责最终判定——LLM 在 08-llm-review-prompt.md 的 Step 8 必须再做
  **门控 C（语义 / 目录 / 上下文）** 的二次确认。
- 因此本扫描器的返回字段叫 `candidates`（不叫 hits），每条附带：
  * gate_a：命中的敏感字段/类别
  * gate_b：命中的高风险 sink
  * window：两者共现的行号窗口
  * cs_po：对齐的产品需求号
  * severity_suggested：P0 / P1（LLM 最终定级以 08 为准）

与 gerrit_audit / local_audit 的关系：
- gerrit_audit.py 调用 `scan_diff_lines(added_lines_by_file)` → 产出 CR 粒度的候选
- local_audit.py / local_module_prepare.py 调用 `scan_file(path, lines)` → 产出全文件候选
- 两者都把候选注入 LLM user prompt 的 `privacy_candidates_json` 占位符。

用法（CLI，便于单测）：
  python3 privacy_compliance_scan.py <path/to/file.java>
  python3 privacy_compliance_scan.py --diff CR_NUMBER   # 需要 Gerrit 凭据

兼容性：本模块不使用 PEP 563 / PEP 585 / PEP 604，且不依赖标准库 dataclasses（3.7+），
       可在 Python 3.6.9+ 直接运行（见 SKILL.md「运行时要求」）。
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

# ---------------------------------------------------------------------------
# 门控 A · 敏感数据清单（来自《附录-个人信息定义》POXGWm）
# ---------------------------------------------------------------------------
# 每项：(id, 正则, 说明, 敏感个人信息标记（源表 √）, 默认建议级别)
# 规则："特别敏感" 默认 P0，一般个人信息默认 P1（仅在与 sink 共现时）
GATE_A = [  # type: List[Tuple[str, Pattern, str, bool, str]]
    # 生物识别（源表 √）
    ("A.BIO_FACE",
     re.compile(r"\b(face[_-]?feature|faceVector|face_data|faceEmbedding|facialTemplate)\b", re.I),
     "人脸特征值", True, "P0"),
    ("A.BIO_VOICE",
     re.compile(r"\b(voice[_-]?print|voicePrint|voicePrintFeature|speakerEmbedding)\b", re.I),
     "声纹特征值", True, "P0"),
    ("A.BIO_FINGER",
     re.compile(r"\b(fingerprint(?!Util)|fingerTemplate)\b"),
     "指纹", True, "P0"),
    ("A.BIO_IRIS",
     re.compile(r"\b(iris(?!ColorUtil)|irisTemplate)\b"),
     "虹膜", True, "P0"),

    # 身份证件（源表 √）
    ("A.ID_CARD",
     re.compile(r"\b(idCard(No)?|idNumber|身份证号|passportNo|driverLicenseNo|socialSecurityNo|medicareId)\b"),
     "身份证件号", True, "P0"),

    # 精准位置（源表 √，要求成对或明确字段）
    ("A.LOC_GPS",
     re.compile(r"\b(gpsLocation|locationTrack|trajectory|preciseLocation|locationHistory)\b"),
     "位置轨迹", True, "P0"),
    # 经纬度成对（需后续 _check_pair_gps 辅助确认）
    ("A.LOC_LATLNG",
     re.compile(r"\b(latitude|longitude)\b"),
     "经纬度", True, "P0"),

    # 通信内容（源表 √）
    ("A.COMM_CONTENT",
     re.compile(r"\b(smsBody|smsContent|callRecord|emailContent|messageBody|msgPayload)\b"),
     "通信内容", True, "P0"),

    # 通讯录（源表 √）
    ("A.CONTACT",
     re.compile(r"\b(contactList|phoneBook|addressBook|friendsList)\b"),
     "通讯录", True, "P0"),

    # 财务（源表 √）
    ("A.FIN",
     re.compile(r"\b(bankCard(No)?|creditCard(No)?|accountBalance|transactionRecord)\b"),
     "财产信息", True, "P0"),

    # 浏览历史（源表 √；强上下文，避免误报）
    ("A.BROWSE",
     re.compile(r"\b(browseHistory|browsingHistory|userClickLog|userVisitLog)\b"),
     "浏览/点击历史", True, "P1"),

    # 一般个人信息 / 设备标识（需 + sink 才触发）
    ("A.PII_PHONE",
     re.compile(r"\b(userPhone|mobilePhone(?!Util)|phoneNumber)\b"),
     "手机号", False, "P1"),
    ("A.PII_EMAIL",
     re.compile(r"\b(userEmail|emailAddress(?!Validator)|mailAddress)\b"),
     "邮箱地址", False, "P1"),
    ("A.DEV_IMEI",
     re.compile(r"\b(imei|getDeviceId|imsi)\b"),
     "设备唯一标识（IMEI/IMSI）", False, "P1"),
    ("A.DEV_MAC",
     re.compile(r"\b(wifiMac|btMac|bluetoothMac|hardwareMac)\b"),
     "硬件 MAC", False, "P1"),
    ("A.VEHICLE_VIN",
     re.compile(r"\bvin(?:Code|Number)?\b", re.I),
     "VIN 码", False, "P1"),
    ("A.AUTH_TOKEN",
     re.compile(r"\b(accessToken|refreshToken|sessionToken|bearerToken|apiKey|apiSecret)\b"),
     "认证凭证 / Token", False, "P0"),
    ("A.PASSWORD",
     re.compile(r"\b(wifiPassword|hotspotPassword|userPassword|loginPassword)\b"),
     "密码（WiFi/热点/登录）", True, "P0"),
]

# ---------------------------------------------------------------------------
# 门控 B · 高风险 sink 清单
# ---------------------------------------------------------------------------
GATE_B = [  # type: List[Tuple[str, Pattern, str, str]]
    # 明文网络（CS-PO-017）
    ("B.NET_HTTP",
     re.compile(r'"http://[^"]*"'),
     "明文 HTTP URL", "CS-PO-017"),
    ("B.NET_TLS_OFF",
     re.compile(r"(setHostnameVerifier\s*\(\s*\w*ALLOW_ALL|"
                r"new\s+AllTrustingTrustManager|"
                r"checkServerTrusted\s*\([^)]*\)\s*\{\s*\}|"
                r"SSLContext\.getInstance\s*\(\s*\"SSL\"\s*\))"),
     "TLS 校验被禁用", "CS-PO-017"),
    ("B.NET_MQTT_PLAIN",
     re.compile(r"tcp://[^\"'\s]+:1883|mqtt://[^\"'\s]+"),
     "明文 MQTT（1883）", "CS-PO-017"),

    # 明文落盘（CS-PO-016）
    ("B.STORE_SP",
     re.compile(r"getSharedPreferences\s*\(|\.edit\s*\(\s*\)\s*\.put(String|Int|Long)"),
     "SharedPreferences 写入（非 EncryptedSharedPreferences）", "CS-PO-016"),
    ("B.STORE_FILE",
     re.compile(r"\b(openFileOutput|new\s+FileOutputStream|FileWriter|PrintWriter)\b"),
     "明文文件写入", "CS-PO-016"),
    ("B.STORE_DB_INSERT",
     re.compile(r"(?:db\.insert|execSQL\s*\(\s*\"INSERT|contentValues\.put)\s*"),
     "数据库明文写入", "CS-PO-016"),

    # 明文日志
    ("B.LOG_ANDROID",
     re.compile(r"\bLog\.(v|d|i|w|e)\s*\("),
     "Android Log.*", "CS-PO-017(隐含)"),
    ("B.LOG_ALOG",
     re.compile(r"\bALOG(D|I|W|E|V)\s*\("),
     "ALOG 宏", "CS-PO-017(隐含)"),
    ("B.LOG_PRINTF",
     re.compile(r"\b(printf|fprintf|std::cout|std::cerr)\b"),
     "stdout/stderr/printf", "CS-PO-017(隐含)"),

    # 跨进程 / 跨端（CS-PO-028）
    ("B.IPC_FDBUS",
     re.compile(r"\b(FDBus|fdbusSend|FDB_SEND|sendFdbus)\b"),
     "FDBus 传递", "CS-PO-028"),
    ("B.IPC_BINDER",
     re.compile(r"\b(Parcel\.writeString|aidl|IBinder\.transact)\b"),
     "Binder/AIDL 传递", "CS-PO-028"),

    # 权限使用（CS-PO-022）
    ("B.PERM_CAMERA",
     re.compile(r"\b(Camera\.open|CameraManager\.openCamera|cameraManager\.openCamera)\b"),
     "打开摄像头", "CS-PO-022-003"),
    ("B.PERM_AUDIO",
     re.compile(r"\b(AudioRecord\.startRecording|MediaRecorder\.start)\b"),
     "开始录音", "CS-PO-022-005"),
    ("B.PERM_LOCATION",
     re.compile(r"\b(requestLocationUpdates|getLastKnownLocation|FusedLocationProviderClient)\b"),
     "使用位置", "CS-PO-022-002/004"),
    ("B.PERM_CONTACT",
     re.compile(r"\b(ContactsContract|getContactsList|readBluetoothPhonebook)\b"),
     "读取通讯录", "CS-PO-022-006"),
]

# ---------------------------------------------------------------------------
# 门控 C · 黑名单（命中即 drop）
# ---------------------------------------------------------------------------
DROP_PATH_HINTS = (
    "/test/", "/tests/", "/androidTest/", "/unittest/", "/ut/",
    "/mock/", "/mocks/", "/fixtures/", "/testdata/", "/sample/", "/samples/",
    "/examples/", "/demo/", "/doc/", "/docs/",
)
DROP_LINE_COMMENT = re.compile(r"^\s*(//|\*|#)")
# 字符串字面量 TAG / URL 模式（常见非数据携带）
DROP_XML_NAMESPACE = re.compile(r"http://schemas\.")

# ---------------------------------------------------------------------------
# 默认窗口：同一文件内 ±8 行视为"共现"（车载 Java 常见函数长度）
DEFAULT_WINDOW = 8


class Candidate(object):
    """门控 A + B 共现候选；为兼容 Python 3.6.9 不使用 ``@dataclass``。"""

    __slots__ = (
        "path",
        "gate_a_line",
        "gate_b_line",
        "gate_a_id",
        "gate_a_desc",
        "gate_a_sensitive",
        "gate_b_id",
        "gate_b_desc",
        "gate_b_snippet",
        "gate_a_snippet",
        "cs_po",
        "severity_suggested",
        "rule",
    )

    def __init__(
        self,
        path,
        gate_a_line,
        gate_b_line,
        gate_a_id,
        gate_a_desc,
        gate_a_sensitive,
        gate_b_id,
        gate_b_desc,
        gate_b_snippet,
        gate_a_snippet,
        cs_po,
        severity_suggested,
        rule="PC.CANDIDATE",
    ):
        self.path = path
        self.gate_a_line = gate_a_line
        self.gate_b_line = gate_b_line
        self.gate_a_id = gate_a_id
        self.gate_a_desc = gate_a_desc
        self.gate_a_sensitive = gate_a_sensitive
        self.gate_b_id = gate_b_id
        self.gate_b_desc = gate_b_desc
        self.gate_b_snippet = gate_b_snippet
        self.gate_a_snippet = gate_a_snippet
        self.cs_po = cs_po
        self.severity_suggested = severity_suggested
        self.rule = rule

    def to_dict(self):
        # type: () -> dict
        return {
            "rule": self.rule,
            "path": self.path,
            "gate_a_line": self.gate_a_line,
            "gate_b_line": self.gate_b_line,
            "gate_a_id": self.gate_a_id,
            "gate_a_desc": self.gate_a_desc,
            "gate_a_sensitive": self.gate_a_sensitive,
            "gate_b_id": self.gate_b_id,
            "gate_b_desc": self.gate_b_desc,
            "gate_a_snippet": self.gate_a_snippet,
            "gate_b_snippet": self.gate_b_snippet,
            "cs_po": self.cs_po,
            "severity_suggested": self.severity_suggested,
            "note": "候选仅为 A+B 共现提示；P0 最终裁决须由 LLM 做门控 C（语义/目录/上下文）二次确认。",
        }


def _path_should_drop(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    return any(h in p for h in DROP_PATH_HINTS)


def _scan_gates(lines):
    # type: (List[str]) -> Tuple[List[Tuple[int, str, str]], List[Tuple[int, str, str]]]
    """返回 (a_hits, b_hits), 每条 = (line_no_1based, hit_id, snippet)."""
    a_hits = []  # type: List[Tuple[int, str, str]]
    b_hits = []  # type: List[Tuple[int, str, str]]
    for i, raw in enumerate(lines, start=1):
        # 注释行降权：命中但不作为 A/B 证据
        if DROP_LINE_COMMENT.match(raw):
            continue
        # XML 命名空间不算 http 明文
        stripped_for_b = raw
        if DROP_XML_NAMESPACE.search(raw):
            # 排除 xmlns 行的明文 http 判定，但保留 log 判定
            stripped_for_b = DROP_XML_NAMESPACE.sub("", raw)

        for gid, pat, _desc, _sens, _lvl in GATE_A:
            if pat.search(raw):
                a_hits.append((i, gid, raw.strip()[:200]))
        for gid, pat, _desc, _cs in GATE_B:
            if pat.search(stripped_for_b):
                b_hits.append((i, gid, raw.strip()[:200]))
    return a_hits, b_hits


def _pair(path, lines, a_hits, b_hits, window):
    # type: (str, List[str], List[Tuple[int, str, str]], List[Tuple[int, str, str]], int) -> List[Candidate]
    """A × B 共现配对；同一 A 与同一 B 只报一次；距离优先近的。"""
    # 建索引：gid -> meta
    a_meta = {gid: (desc, sens, lvl) for gid, _pat, desc, sens, lvl in GATE_A}
    b_meta = {gid: (desc, cs) for gid, _pat, desc, cs in GATE_B}

    cands = []  # type: List[Candidate]
    # 同一 (gate_a_id, gate_b_id) 每文件仅保留距离最近的一条，其余压制为噪声
    best_by_pair = {}  # type: Dict[Tuple[str, str], Candidate]

    for (la, aid, asnip) in a_hits:
        for (lb, bid, bsnip) in b_hits:
            if abs(la - lb) > window:
                continue

            a_desc, a_sens, a_lvl = a_meta[aid]
            b_desc, cs = b_meta[bid]

            # 经纬度单点不算敏感，仅当 latitude + longitude 同窗口出现才放行
            if aid == "A.LOC_LATLNG":
                # 需在同 ±2 行内同时出现 latitude/longitude 两个词
                lo = max(1, la - 2)
                hi = min(len(lines), la + 2)
                chunk = "\n".join(lines[lo - 1: hi])
                if not (re.search(r"\blatitude\b", chunk, re.I)
                        and re.search(r"\blongitude\b", chunk, re.I)):
                    continue

            severity = a_lvl
            cand = Candidate(
                path=path,
                gate_a_line=la, gate_b_line=lb,
                gate_a_id=aid, gate_a_desc=a_desc, gate_a_sensitive=a_sens,
                gate_b_id=bid, gate_b_desc=b_desc,
                gate_a_snippet=asnip, gate_b_snippet=bsnip,
                cs_po=cs,
                severity_suggested=severity,
            )
            pair_key = (aid, bid)
            prev = best_by_pair.get(pair_key)
            if prev is None or abs(la - lb) < abs(prev.gate_a_line - prev.gate_b_line):
                best_by_pair[pair_key] = cand

    cands = list(best_by_pair.values())
    return cands


def scan_file(path, lines, window=DEFAULT_WINDOW):
    # type: (str, List[str], int) -> dict
    """扫描单文件（全量）。返回 { path, candidates:[...], dropped_reason? }。"""
    if _path_should_drop(path):
        return {"path": path, "candidates": [], "dropped_reason": "test/mock/doc path"}
    a_hits, b_hits = _scan_gates(lines)
    cands = _pair(path, lines, a_hits, b_hits, window)
    return {"path": path, "candidates": [c.to_dict() for c in cands]}


def scan_diff_added(added_by_file, context_by_file=None, window=DEFAULT_WINDOW):
    # type: (Dict[str, List[Tuple[int, str]]], Optional[Dict[str, List[str]]], int) -> List[dict]
    """扫 CR 粒度：
    - `added_by_file[path]` = [(new_line_no, text), ...]  仅新增行
    - `context_by_file[path]` = 完整新侧文件行数组（用于 A/B 跨行共现）

    策略：以 added 行为锚点（即至少有一侧证据出现在新增行），否则不列入
          （避免把完全未改动的既存问题扫出来刷屏）。
    """
    out = []  # type: List[dict]
    for path, added in added_by_file.items():
        if _path_should_drop(path):
            out.append({"path": path, "candidates": [], "dropped_reason": "test/mock/doc path"})
            continue
        full = context_by_file.get(path) if context_by_file else None
        if full is None:
            # fallback: 仅用 added 行做单行同时命中 A+B（极苛刻）
            pseudo_lines = [""] * (max((ln for ln, _ in added), default=0))
            for ln, txt in added:
                if ln <= len(pseudo_lines):
                    pseudo_lines[ln - 1] = txt
            a_hits, b_hits = _scan_gates(pseudo_lines)
            cands = _pair(path, pseudo_lines, a_hits, b_hits, window=window)
        else:
            a_hits, b_hits = _scan_gates(full)
            added_line_set = {ln for ln, _ in added}
            # 必须至少有一侧证据落在 added 行
            a_hits = [h for h in a_hits if h[0] in added_line_set or any(
                abs(h[0] - lb[0]) <= window and lb[0] in added_line_set for lb in b_hits)]
            b_hits = [h for h in b_hits if h[0] in added_line_set or any(
                abs(h[0] - la[0]) <= window and la[0] in added_line_set for la in a_hits)]
            cands = _pair(path, full, a_hits, b_hits, window=window)
        out.append({"path": path, "candidates": [c.to_dict() for c in cands]})
    return out


# ----------------------------------------------------------------------- CLI
def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="要扫描的本地文件路径")
    ap.add_argument("--diff", dest="cr", help="Gerrit CR 号（扫描该 CR 新增侧）")
    ap.add_argument("-w", "--window", type=int, default=DEFAULT_WINDOW)
    args = ap.parse_args()

    if args.cr:
        # 延迟 import：仅在 --diff 模式需要 gerrit_client
        from gerrit_client import get_cr_detail, get_file_diff, iter_diff_lines
        d = get_cr_detail(args.cr)
        cur = d.get("current_revision")
        files = d["revisions"][cur].get("files") or {}
        added_by_file = {}     # type: Dict[str, List[Tuple[int, str]]]
        context_by_file = {}   # type: Dict[str, List[str]]
        for fn, _meta in files.items():
            if fn == "/COMMIT_MSG":
                continue
            dd = get_file_diff(args.cr, cur, fn)
            if not isinstance(dd, dict):
                continue
            added = []  # type: List[Tuple[int, str]]
            full = []   # type: List[str]
            for old_ln, new_ln, kind, text in iter_diff_lines(dd):
                if kind in ("add", "ctx"):
                    # 无完整 new side 时用 ctx+add 拼接近似全文
                    while len(full) < (new_ln or 0) - 1:
                        full.append("")
                    if new_ln:
                        if len(full) < new_ln:
                            full.extend([""] * (new_ln - len(full)))
                        full[new_ln - 1] = text
                if kind == "add" and new_ln:
                    added.append((new_ln, text))
            if added:
                added_by_file[fn] = added
                context_by_file[fn] = full
        res = scan_diff_added(added_by_file, context_by_file, window=args.window)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if not args.path:
        ap.error("需提供 path 或 --diff CR")
    with open(args.path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    res = scan_file(args.path, lines, window=args.window)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
