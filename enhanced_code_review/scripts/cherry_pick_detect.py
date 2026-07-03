"""cherry_pick_detect.py — v2.3.1 新增.

识别 CR 是否为 cherry-pick，以及基线 CR 是否已有评审；若 diff 全等则直接
在 gerrit_review.prepare_context 中跳过 LLM 扫描，用基线结果复用。

用户意图（v2.3.1 发布需求原文）：
  「关于同一个 topic 的不同提交需要每一笔提交都 review，但是不需要关联
   topic，对于 cherry-pick 的提交可以按照最早提交的 CR 进行 review，
   然后其他的 cherry-pick 提交直接贴结果」

三级识别（由强到弱，任一失败降级为独立 review）：
  1) Gerrit 原生 `cherry_pick_of_change` 字段
  2) 同 `Change-Id` 在更早 CR 存在
  3) diff new-side 哈希全等

Python 3.6.9 兼容。
"""
import hashlib
import sys
import json
import os
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gerrit_client import gget, get_cr_detail, get_file_diff, iter_diff_lines, BASE


def _cur_rev(detail):
    return detail.get("current_revision")


def _change_id(detail):
    cur = _cur_rev(detail) or ""
    rev = detail.get("revisions", {}).get(cur, {})
    return rev.get("commit", {}).get("message", "").split("Change-Id:", 1)[-1].strip().split("\n", 1)[0].strip() or detail.get("change_id")


def _diff_fingerprint(cr, detail):
    """对 CR 当前 revision 的所有文件 new-side 行做 sha256."""
    cur = _cur_rev(detail)
    files = detail.get("revisions", {}).get(cur, {}).get("files") or {}
    parts = []
    for fn in sorted(files.keys()):
        if fn == "/COMMIT_MSG":
            continue
        dd = get_file_diff(cr, cur, fn)
        if not isinstance(dd, dict):
            continue
        new_lines = []
        for _old, new_l, kind, text in iter_diff_lines(dd):
            if kind in ("add", "ctx") and new_l:
                new_lines.append("{0}\t{1}".format(new_l, text))
        parts.append(fn + "\n" + "\n".join(new_lines))
    blob = "\n---FILE---\n".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest() if parts else ""


def _find_by_change_id(change_id, exclude_cr):
    """按 Change-Id 查同组 CR（跨分支/cherry-pick 常见）。"""
    if not change_id:
        return []
    q = urllib.parse.quote("change:{0}".format(change_id))
    s, data = gget("/a/changes/?q={0}&n=20&o=CURRENT_REVISION".format(q))
    if not isinstance(data, list):
        return []
    return [
        r for r in data
        if r.get("_number") and int(r["_number"]) != int(exclude_cr)
    ]


def _fetch_prior_review(base_cr):
    """拉基线 CR 评审历史；找最后一条 Code-Review label 变化。"""
    s, data = gget("/a/changes/{0}/detail?o=MESSAGES&o=DETAILED_LABELS".format(base_cr))
    if not isinstance(data, dict):
        return None, None

    # score 从 labels.Code-Review.all 取最后一条非零
    score = None
    lbl = data.get("labels", {}).get("Code-Review", {})
    for entry in lbl.get("all") or []:
        val = entry.get("value")
        if val in (-2, -1, 1, 2):
            score = val

    # 评审摘要：取最后一条含"enhanced_code_review"字串的 message
    summary = None
    for msg in reversed(data.get("messages") or []):
        text = msg.get("message", "")
        if "enhanced_code_review" in text or "Code-Review" in text:
            # 截取首段 200 字符
            summary = text.strip().splitlines()[0][:200]
            break
    return score, summary


def detect(cr):
    """返回识别结果字典.

    keys:
      is_cherry_pick : bool     三级信号任一命中
      base_cr        : str|None 最早提交的 CR 号
      base_review_exists : bool 基线 CR 是否已有评分
      base_score     : int|None 基线评分
      base_summary   : str|None 基线摘要
      base_url       : str|None 基线 URL
      diff_identical : bool     new-side diff 指纹全等
      signals        : dict     {api, change_id_match, diff_identical}
      reuse          : bool     最终结论：是否应该走复用
    """
    out = {
        "is_cherry_pick": False,
        "base_cr": None,
        "base_review_exists": False,
        "base_score": None,
        "base_summary": None,
        "base_url": None,
        "diff_identical": False,
        "signals": {"api": None, "change_id_match": None, "diff_identical": None},
        "reuse": False,
    }

    detail = get_cr_detail(cr)
    if not isinstance(detail, dict):
        return out

    # 一级：Gerrit 原生 cherry_pick_of_change
    cp_of = detail.get("cherry_pick_of_change")
    if cp_of:
        out["is_cherry_pick"] = True
        out["base_cr"] = str(cp_of)
        out["signals"]["api"] = True

    # 二级：同 Change-Id
    cid = _change_id(detail)
    peers = _find_by_change_id(cid, cr)
    if peers:
        # 取 _number 最小（时间上最早）为基线
        peers_sorted = sorted(peers, key=lambda r: int(r.get("_number") or 0))
        first = peers_sorted[0]
        if not out["base_cr"]:
            out["base_cr"] = str(first["_number"])
        out["signals"]["change_id_match"] = True
        out["is_cherry_pick"] = True

    if not out["base_cr"]:
        return out

    # 三级：diff 指纹比对
    base_detail = get_cr_detail(out["base_cr"])
    if isinstance(base_detail, dict):
        try:
            fp_a = _diff_fingerprint(cr, detail)
            fp_b = _diff_fingerprint(out["base_cr"], base_detail)
            out["diff_identical"] = bool(fp_a and fp_b and fp_a == fp_b)
            out["signals"]["diff_identical"] = out["diff_identical"]
            out["base_url"] = "{0}/c/{1}/+/{2}".format(
                BASE, base_detail.get("project"), out["base_cr"]
            )
        except Exception as e:
            out["diff_identical"] = False
            out["signals"]["diff_identical"] = "error:{0}".format(e)

    # 基线是否有评审
    score, summary = _fetch_prior_review(out["base_cr"])
    if score is not None:
        out["base_review_exists"] = True
        out["base_score"] = score
        out["base_summary"] = summary

    # 最终复用判定
    out["reuse"] = bool(
        out["is_cherry_pick"]
        and out["diff_identical"]
        and out["base_review_exists"]
    )
    return out


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 cherry_pick_detect.py <CR_NUMBER>")
        sys.exit(1)
    r = detect(sys.argv[1])
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
