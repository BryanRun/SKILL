"""同文件内一致性扫描 (Intra-file Consistency Analyzer)

专门解决车载中间件评审里最高发的硬伤：
  "同一个文件里，A 方法做了 null check，B 方法（新加的）没做" → 这是 P0 硬不一致。

用法：
  python3 consistency_scan.py <CR_NUMBER>

输出：每个修改文件，列出新增方法 vs 既有方法的"防御式编程"差异。
"""
import sys, re, json, urllib.parse
from gerrit_client import get_cr_detail, get_file_diff, iter_diff_lines, gget

# 从 Gerrit 拉原文件（new side 完整内容）
def get_file_content(cr, rev, path):
    enc = urllib.parse.quote(path, safe="")
    # Gerrit 的 content API 返回 base64
    s, data = gget(f"/a/changes/{cr}/revisions/{rev}/files/{enc}/content", raw=True)
    if s != 200:
        return None
    import base64
    try:
        return base64.b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return None


# 模式：检测"字段访问前是否有 null check"
NULL_CHECK_METHODS_PAT = re.compile(
    r"(public|protected|private)?\s+\w[\w<>\[\],\s]*\s+(\w+)\s*\([^)]*\)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
    re.DOTALL
)

# 类字段识别（简化版）
FIELD_DECL_PAT = re.compile(r"private\s+(?:volatile\s+)?(\w[\w<>\[\]]*)\s+(\w+)\s*[;=]")


def extract_class_fields(src):
    """返回 {fieldName: type}。"""
    fields = {}
    for m in FIELD_DECL_PAT.finditer(src):
        fields[m.group(2)] = m.group(1)
    return fields


def method_uses_field_without_null_check(method_body, field):
    """方法体内是否无条件使用了某字段（作为方法调用 receiver 或 赋值 target）。"""
    # 有 null check
    null_check_pat = re.compile(rf"if\s*\(\s*{re.escape(field)}\s*(?:!=\s*null|==\s*null)", re.MULTILINE)
    has_check = bool(null_check_pat.search(method_body))
    # 有调用
    call_pat = re.compile(rf"\b{re.escape(field)}\s*\.", re.MULTILINE)
    has_call = bool(call_pat.search(method_body))
    return has_call and not has_check


def analyze_file(cr, rev, path):
    src = get_file_content(cr, rev, path)
    if not src:
        return []

    fields = extract_class_fields(src)
    if not fields:
        return []

    # 找所有方法（非精确，但足够启发）
    methods = []
    for m in NULL_CHECK_METHODS_PAT.finditer(src):
        name = m.group(2)
        body = m.group(3) or ""
        methods.append({"name": name, "body": body, "span": m.span()})

    findings = []
    # 对每个字段，统计方法里"做了 null check 的比例"
    for field, ftype in fields.items():
        if ftype in {"int", "long", "boolean", "float", "double", "short", "byte", "char"}:
            continue  # 基本类型不需要 null check
        checked = []
        unchecked = []
        for mm in methods:
            body = mm["body"]
            call_pat = re.compile(rf"\b{re.escape(field)}\s*\.")
            if not call_pat.search(body):
                continue
            null_pat = re.compile(rf"if\s*\(\s*{re.escape(field)}\s*(?:!=\s*null|==\s*null)")
            if null_pat.search(body):
                checked.append(mm["name"])
            else:
                unchecked.append(mm["name"])
        if checked and unchecked:
            # 硬不一致：同字段有的方法判了 null 有的没判
            findings.append({
                "field": field,
                "type": ftype,
                "checked_methods": checked,
                "unchecked_methods": unchecked,
                "severity": "P0",
                "title": f"同文件内 '{field}' 字段的 null check 不一致",
                "detail": (
                    f"字段 `{field}` 在以下方法中做了 null check: {checked}，"
                    f"但在以下方法中未做: {unchecked}。\n\n"
                    "同一字段在同一类内的访问模式应保持一致。如果原有方法认为需要判空，"
                    "新增/修改的方法也应判空；否则存在 NPE 风险。"
                )
            })

    return findings


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 consistency_scan.py <CR_NUMBER>")
        return
    cr = sys.argv[1]
    d = get_cr_detail(cr)
    if not isinstance(d, dict):
        print("ERR", d)
        return
    rev = d["current_revision"]
    files = d["revisions"][rev].get("files") or {}
    out = {}
    for fn in files:
        if fn == "/COMMIT_MSG" or not fn.endswith(".java"):
            continue
        findings = analyze_file(cr, rev, fn)
        if findings:
            out[fn] = findings
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
