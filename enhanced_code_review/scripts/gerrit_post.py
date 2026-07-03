"""post: 把评审草稿 (JSON) POST 到 Gerrit。

v2.7.0: 默认自动用 cover_template.render_from_review_and_ctx 生成统一 cover
（必含 skill 名 + 版本号 + 档位徽章 + 8 大维度矩阵 + 并发汇总）。

v2.5.2（模板强约束）：回帖 cover **必须**经 skill 模板渲染，禁止模型自由写整段 cover。
  - 默认 auto-cover：缺 ctx 无法渲染模板时 **硬失败（exit 4）**，不再静默退回 review.json
    原始 cover；提示用 `--ctx` 传上下文。
  - `--no-auto-cover` / `--cover` / 缺 ctx 等「绕过 skill 模板」的路径，必须显式叠加
    `--allow-raw-cover` 才放行，并在 stderr 打印醒目告警；否则一律拒绝 POST。

用法：
  # 默认：auto-cover + 从 review.json 的 ctx_ref（或同名 .ctx.json）读 ctx 做模板渲染
  python3 gerrit_post.py review.json --ctx ctx.json

  # 缺 ctx 时（不推荐）显式裸 cover：绕过 skill 模板
  python3 gerrit_post.py review.json --no-auto-cover --allow-raw-cover

  # 命令行直接给 score 和 cover（覆盖 review.json 字段，需显式 --allow-raw-cover）
  python3 gerrit_post.py review.json --score -1 --cover cover.md --allow-raw-cover

  # dry run：打印不发
  python3 gerrit_post.py review.json --ctx ctx.json --dry
"""
import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gerrit_client import post_review, get_current_revision
try:
    from cover_template import render_from_review_and_ctx
except Exception:
    render_from_review_and_ctx = None


def _load_ctx(review_path, explicit_ctx):
    """按优先级加载 ctx：显式 --ctx > review.json 的 ctx_ref > 同名 .ctx.json > None."""
    if explicit_ctx:
        return json.loads(open(explicit_ctx, "r", encoding="utf-8").read())
    try:
        review = json.loads(open(review_path, "r", encoding="utf-8").read())
    except Exception:
        return None
    ref = review.get("ctx_ref")
    if ref and os.path.isfile(ref):
        return json.loads(open(ref, "r", encoding="utf-8").read())
    guess = review_path.rsplit(".", 1)[0] + ".ctx.json"
    if os.path.isfile(guess):
        return json.loads(open(guess, "r", encoding="utf-8").read())
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review_json")
    ap.add_argument("--score", type=int, default=None,
                    help="覆盖 suggested_score。-2/-1/+1/+2。")
    ap.add_argument("--cover", default=None,
                    help="cover 文件路径（markdown）；或直接传字符串。给了就禁用 auto-cover。")
    ap.add_argument("--ctx", default=None,
                    help="ctx.json 路径（用于 auto-cover 渲染；默认自动探测同名 .ctx.json）")
    ap.add_argument("--no-auto-cover", action="store_true",
                    help="跳过自动模板渲染，直接用 review.json 的 cover 原值（v2.5.2 起需配 --allow-raw-cover）")
    ap.add_argument("--allow-raw-cover", action="store_true",
                    help="v2.5.2：显式允许绕过 skill 模板使用裸 cover（缺 ctx / --no-auto-cover / --cover 时必须叠加，否则拒绝 POST）")
    ap.add_argument("--dry", action="store_true", help="不真发，仅预览")
    a = ap.parse_args()

    r = json.loads(open(a.review_json, "r", encoding="utf-8").read())

    cr = r["cr"]
    rev = r.get("revision") or "current"
    score = a.score if a.score is not None else r.get("suggested_score", r.get("score", 0))

    # v2.5.4 stale-revision 修复：POST 前以 Gerrit 实时 current_revision 为准，
    # 防止 review.json 残留旧 PS sha 被贴回陈旧 patchset（同 gerrit_review.py --post）。
    try:
        _live_sha, _live_ps = get_current_revision(cr)
    except Exception:
        _live_sha, _live_ps = None, None
    if _live_sha and rev not in (_live_sha, "current"):
        print("[warn] stale-revision: review.json revision={0} ≠ Gerrit current={1}（PS{2}）；已自动改为最新 PS。".format(
              (rev or "")[:12], _live_sha[:12], _live_ps), file=sys.stderr)
        rev = _live_sha
        r["revision"] = _live_sha

    # cover 选择（v2.5.2）：默认必须经 skill 模板渲染；任何「绕过模板」路径都要 --allow-raw-cover。
    def _deny_raw(reason):
        print("[error] {0}".format(reason), file=sys.stderr)
        print("        回帖 cover 必须经 skill 模板渲染（cover_template）。", file=sys.stderr)
        print("        请用 --ctx 传 ctx.json（与 gerrit_review.py --prepare -o 对齐）；", file=sys.stderr)
        print("        如确需裸 cover（不推荐，绕过模板），显式加 --allow-raw-cover。", file=sys.stderr)
        sys.exit(4)

    if a.cover:
        # 命令行直接给 cover：绕过 skill 模板
        if not a.allow_raw_cover:
            _deny_raw("--cover 直接指定 cover 会绕过 skill 模板。")
        print("[warn] --cover + --allow-raw-cover：使用命令行 cover（绕过 skill 模板）。", file=sys.stderr)
        if a.cover.endswith(".md") or a.cover.endswith(".txt"):
            try:
                cover = open(a.cover, "r", encoding="utf-8").read()
            except FileNotFoundError:
                cover = a.cover
        else:
            cover = a.cover
    elif render_from_review_and_ctx is None:
        # 模板模块不可用：仅在显式放行时退回裸 cover
        if not a.allow_raw_cover:
            _deny_raw("cover_template 模块不可用，无法渲染 skill 模板。")
        print("[warn] cover_template 不可用 + --allow-raw-cover：退回 review.json 原 cover。", file=sys.stderr)
        cover = r.get("cover", "")
    elif a.no_auto_cover:
        # 显式禁用 auto-cover：绕过 skill 模板
        if not a.allow_raw_cover:
            _deny_raw("--no-auto-cover 会绕过 skill 模板。")
        print("[warn] --no-auto-cover + --allow-raw-cover：使用 review.json 原始 cover（绕过 skill 模板）。", file=sys.stderr)
        cover = r.get("cover", "")
    else:
        # 默认：用模板自动包装
        ctx = _load_ctx(a.review_json, a.ctx)
        if ctx is None:
            if a.allow_raw_cover:
                print("[warn] 未找到 ctx.json + --allow-raw-cover：使用 review.json 原始 cover（绕过 skill 模板）。", file=sys.stderr)
                cover = r.get("cover", "")
            else:
                _deny_raw("未找到 ctx.json，auto-cover 无法渲染 skill 模板。")
        else:
            if _live_sha and ctx.get("revision") and ctx.get("revision") != _live_sha:
                print("[warn] stale-revision: ctx.revision={0} ≠ current={1}，已同步（cover 元信息以最新 PS 为准）。".format(
                      (ctx.get("revision") or "")[:12], _live_sha[:12]), file=sys.stderr)
                ctx["revision"] = _live_sha
            cover = render_from_review_and_ctx(r, ctx)

    comments = r.get("comments", {})
    # 清洗：跳过 /COMMIT_MSG（Gerrit 对 commit msg 的 comment 要走别的 path）
    clean = {}
    if isinstance(comments, dict):
        for path, items in comments.items():
            if path == "/COMMIT_MSG":
                # 把 commit msg 的问题挪到 cover 里
                extra = "\n\n[commit message]\n" + "\n".join(
                    "- {0}".format(i.get('message', '')) for i in items
                )
                cover = cover + extra
                continue
            clean[path] = items

    body_preview = {
        "cr": cr, "rev": rev, "score": score,
        "cover": cover,
        "comments_count": sum(len(v) for v in clean.values()),
        "paths": list(clean.keys()),
    }
    print("=== POST preview ===")
    print(json.dumps(body_preview, ensure_ascii=False, indent=2))

    if a.dry:
        print("\n[DRY RUN] skipped real POST")
        return

    s, resp = post_review(cr, rev, cover, score, clean)
    print("\nstatus: {0}".format(s))
    print(json.dumps(resp, ensure_ascii=False, indent=2) if isinstance(resp, dict) else (resp[:500] if isinstance(resp, str) else resp))


if __name__ == "__main__":
    main()
