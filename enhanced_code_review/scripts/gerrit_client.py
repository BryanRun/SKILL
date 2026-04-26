"""共享的 Gerrit 客户端：认证、GET、POST、diff 解析。
所有 scripts 统一 import 本模块。
"""
import os, json, re, urllib3, urllib.parse
import requests
from requests.auth import HTTPBasicAuth

urllib3.disable_warnings()

BASE = os.environ.get("GERRIT_BASE", "https://gerrit.auto-link.com.cn")
USER = os.environ.get("GERRIT_USER", "hualei")
PWD = os.environ.get("GERRIT_HTTP_PASSWORD", "qZZ26xTRNvQAwgsCb6u6I7cKlNx36G/ppDBksdHKqg")
AUTH = HTTPBasicAuth(USER, PWD)

JIRA_RE = re.compile(r"(CHYT1V-\d+|BAIC-\d+|KP31-\d+|CL-[A-Z0-9\-]+|T1V-\d+|N80-\d+|D01-\d+|FL[13]-\d+)")


def _strip(t):
    if t.startswith(")]}'"):
        t = t[4:]
    return t


def gget(path, raw=False):
    r = requests.get(f"{BASE}{path}", auth=AUTH, verify=False, timeout=30)
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
        auth=AUTH, verify=False, timeout=30,
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
    if not text:
        return []
    return list(set(JIRA_RE.findall(text)))


def find_related_crs(jira):
    """按 Jira 号查同组 CR."""
    q = urllib.parse.quote(f"message:{jira}")
    s, data = gget(f"/a/changes/?q={q}&n=20")
    if not isinstance(data, list):
        return []
    return data
