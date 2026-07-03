"""共享的 Gerrit 客户端：认证、GET、POST、diff 解析。
所有 scripts 统一 import 本模块。

必需环境变量（不提供将报错退出）：
  GERRIT_BASE           例: https://gerrit.example.com
  GERRIT_USER           Gerrit 用户名
  GERRIT_HTTP_PASSWORD  Gerrit HTTP 密码（Settings → HTTP Credentials）

凭据策略：
  技能包不含任何硬编码账号/密码。未设置环境变量将直接报错退出（exit 2）。
"""
import os, sys, json, re, urllib3, urllib.parse
import requests
from requests.auth import HTTPBasicAuth

urllib3.disable_warnings()


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.stderr.write(
            f"[gerrit-review] 缺少必需环境变量 {name}。\n"
            f"  请先设置：export {name}=<value>\n"
            f"  需要的变量：GERRIT_BASE / GERRIT_USER / GERRIT_HTTP_PASSWORD\n"
            f"  详见 skill README 中 \u201c配置\u201d 章节。\n"
        )
        sys.exit(2)
    return v


BASE = _require_env("GERRIT_BASE").rstrip("/")
USER = _require_env("GERRIT_USER")
PWD = _require_env("GERRIT_HTTP_PASSWORD")
AUTH = HTTPBasicAuth(USER, PWD)

# Jira 前缀：锁定车联项目
# 如需新增前缀，请在此集中维护；避免把 URL 片段、枚举值误识别为 Jira 号。
# 2026-05-03 更新：名单扩展 + 占位规则放宽
#   白名单前缀: CHER*/CHYT1V/BAIC/KP31/CHYT12A/CHYMIFA/CHY/T1V/N80/D01/FL[123] + CHY* / KP* 通配 + CL- / AUDI
#   占位识别:  Jira 合规不要求绝对严格；纯数字占位（000/001 之类后缀或全 0）才算不合规，
#             其他形如 T1V-12345 / CHYT1V-1234 等正常业务号一律视为合规
# 2026-06-06 更新：新增 AUDI- 前缀（奥迪项目正式 Jira 号，如 AUDI-12345）
# 2026-06-16 更新（v2.5.5）：新增 CHER 前缀（奇瑞 Chery 项目 Jira 号，如 CHER-1234 / CHERY-1234）。
#   置于 CHY 分支之前无歧义（CHER 不以 CHY 开头）；CHER[A-Z0-9]* 兼容 CHER / CHERY / CHERxxx。
JIRA_RE = re.compile(
    r"(CHER[A-Z0-9]*-\d+|CHY[A-Z0-9]+-\d+|BAIC-\d+|KP[A-Z0-9]+-\d+|AUDI-\d+|CL-[A-Z0-9\-]+|T1V-\d+|N80-\d+|D01-\d+|FL[1-3]-\d+)"
)

# 占位 Jira 后缀（放宽规则，2026-05-03 统一）：
#   - 数值为 0（如 T1V-0）
#   - 以 ≥2 个连续 0 开头（如 T1V-000 / T1V-001 / T1V-0099）
# 正常业务号（T1V-5 / T1V-10 / T1V-12345 / CHYT1V-1234）不受此规则影响。
def is_placeholder_jira(jira_num_str: str) -> bool:
    """判断一个 Jira 编号的数字部分是否是占位号。"""
    if not jira_num_str:
        return True
    try:
        n = int(jira_num_str)
    except ValueError:
        return True
    if n == 0:
        return True
    if len(jira_num_str) >= 3 and jira_num_str.startswith('00'):
        return True
    return False


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


def get_current_revision(cr):
    """取 CR 当前（最新）revision sha + patch_set 号（实时查 Gerrit）。

    v2.5.4 / v2.7.3 stale-revision 修复：POST 前必须以 Gerrit 实时
    current_revision 为准，避免 review.json / ctx.json 里残留的旧 PS sha
    被贴回到陈旧 patchset（导致 cover revision 标错 + 基于旧代码误判）。

    返回 (sha, patch_set_number)；拿不到返回 (None, None)。
    """
    d = get_cr_detail(cr)
    if not isinstance(d, dict):
        return None, None
    sha = d.get('current_revision', '') or None
    ps = None
    revs = d.get('revisions', {}) if isinstance(d, dict) else {}
    if sha and sha in revs:
        ps = revs[sha].get('_number')
    return sha, ps


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


# ── v2.5.0 新增：inline comments + cover messages 获取 ──────────

def get_change_comments(cr):
    """获取 CR 所有 inline comments（含 reply 链）。
    返回 dict: {file_path: [comment_obj, ...]}
    每个 comment_obj 含：id, author, message, line, in_reply_to, updated, patch_set
    """
    s, data = gget(f"/a/changes/{cr}/comments")
    if not isinstance(data, dict):
        return {}
    return data


def get_change_messages(cr):
    """获取 CR 所有 cover-level messages（含分数变更历史）。
    返回 list: [message_obj, ...]
    每个 message_obj 含：id, author, message, date, tag, _revision_number
    """
    s, data = gget(f"/a/changes/{cr}/messages")
    if not isinstance(data, list):
        return []
    return data


def is_substantive_review_message(msg_text):
    """v2.5.0 修正：判断一条评审消息是否含 AI 评审实质内容。

    实质评审特征：
      - 含「评审结论」/「维度扫描」/P0/P1/并发专项等 AI 评审骨架词
      - 含 inline comments 量 > 0
      - 长度 > 300 字符（净文本）

    非实质评审（需重新发起 AI 评审）：
      - “自动预审未通过”/“未找到 AI 本地预审结果”
      - 纯分数圈改动无说明
      - 纯 CommitMsg-Check / Verified 等 CI 标记
    """
    if not msg_text:
        return False
    text = msg_text.strip()

    # 包含负面关键字（预审未通过 / 需要 owner 提交 AI 预审）→ 非实质
    non_substantive_markers = [
        '自动预审未通过',
        '未找到代码 owner',
        '未找到代码 owner.*提交的 AI',
        '不满足评审前置条件',
        '请先使用 AI 代码评审工具对代码进行本地预审',
        'CommitMsg-Check',
        'Prebuild-Check',
        'StaticCode-Check',
        'DevTest-Check',
        'Verified+',
        'Peer-Review+',
    ]
    for marker in non_substantive_markers:
        import re as _re
        if _re.search(marker, text):
            return False

    # 包含 AI 评审骨架词 → 实质
    substantive_markers = [
        '评审结论',
        '维度扫描',
        '并发专项',
        '隐私合规',
        '必改项',
        '错误处理',
        'P0=',
        'P1=',
        '[P0]',
        '[P1]',
        '[P2]',
        '[P3]',
        '依据：',
        'gerrit-review',
        '识别为 P',
    ]
    for marker in substantive_markers:
        if marker in text:
            return True

    # 备选：净文本足够长且不是分数圈 → 认为实质
    if len(text) > 300:
        return True

    return False


def build_prior_review_context(cr, self_username):
    """v2.5.0 核心：构建 prior review context。

    返回 dict:
      has_prior_review: bool
      prior_score: int|None   (self 上一次给的分数)
      self_prior_comments: [{path, line, message, id, patch_set}, ...]
      owner_replies: [{reply_to_comment_id, path, line, message, author}, ...]
      owner_cover_replies: [{message, date}, ...]   v2.5.0 修正：owner 在 cover 层面的任何回复
      owner_inline_replies_to_others: [{reply_to_comment_id, reply_to_author, path, line, message}, ...]   owner 对其他 reviewer 的回复
      other_reviewer_comments: [{path, line, message, author, score}, ...]
      special_notes: [{author, message, type}, ...]  (owner/reviewer 的备注说明)
      score_history: [{author, score, message_snippet, is_withdrawn}, ...]
      has_withdrawn: bool  (是否有 -Code-Review 撤回记录)
      other_minus_one: bool  (是否有其他人已给 -1)
      other_minus_one_details: [{reviewer, score, is_substantive}, ...]
      has_substantive_other_minus_one: bool   v2.5.0 修正：是否有「含实质 AI 评审」的他人 -1
      has_owner_reply: bool   v2.5.0 修正：owner 是否有任何 reply（cover 或 inline）
    """
    comments = get_change_comments(cr)
    messages = get_change_messages(cr)

    # v2.5.0 修正：获取 owner 身份，用于识别 owner 的任何 reply
    detail = get_cr_detail(cr)
    owner_info = detail.get('owner', {}) if isinstance(detail, dict) else {}
    owner_username = owner_info.get('username') or owner_info.get('name', '')

    # v2.5.0 fix （质强 2026-05-12反馈）：获取当前 patch_set 号，用于严格识别"代码是否有变动"
    # 依赖 _number 字段而非仅 sha：不同 patch_set 都是代码变动
    current_revision_sha = detail.get('current_revision', '') if isinstance(detail, dict) else ''
    revisions = detail.get('revisions', {}) if isinstance(detail, dict) else {}
    current_patch_set = None
    if current_revision_sha and current_revision_sha in revisions:
        current_patch_set = revisions[current_revision_sha].get('_number')

    result = {
        'has_prior_review': False,
        'prior_score': None,
        'prior_review_patch_set': None,
        'current_patch_set': current_patch_set,
        'current_revision_sha': current_revision_sha,
        'code_changed_since_prior_review': False,
        'self_prior_comments': [],
        'owner_replies': [],
        'owner_cover_replies': [],
        'owner_inline_replies_to_others': [],
        'other_reviewer_comments': [],
        'special_notes': [],
        'score_history': [],
        'has_withdrawn': False,
        'other_minus_one': False,
        'other_minus_one_details': [],
        'has_substantive_other_minus_one': False,
        'has_owner_reply': False,
        'owner_username': owner_username,
    }

    # 1. 从 messages 提取分数历史 + 撤回信号 + 特殊备注
    for msg in messages:
        author = msg.get('author', {})
        author_name = author.get('username') or author.get('name', '')
        msg_text = msg.get('message', '')
        tag = msg.get('tag', '')

        # 跳过自动生成消息（jenkins、gerrit 自身）
        if tag and tag.startswith('autogenerated:'):
            continue

        # 解析分数变更："Patch Set N: Code-Review+1" / "Code-Review-1"
        import re as _re
        score_match = _re.search(r'Code-Review([+-]\d)', msg_text)
        withdrawn_match = _re.search(r'-Code-Review\b', msg_text)

        if score_match:
            score_val = int(score_match.group(1))
            is_substantive = is_substantive_review_message(msg_text)
            entry = {
                'author': author_name,
                'score': score_val,
                'message_snippet': msg_text[:200],
                'is_withdrawn': False,
                'is_substantive': is_substantive,
                'patch_set': msg.get('_revision_number'),
            }
            result['score_history'].append(entry)

            if author_name == self_username:
                result['has_prior_review'] = True
                result['prior_score'] = score_val
                # v2.5.0 fix：记录 self 上次评审是哪个 patch_set
                ps = msg.get('_revision_number')
                if ps is not None:
                    # 取最新一次 self 评审的 patch_set
                    if result['prior_review_patch_set'] is None or ps > result['prior_review_patch_set']:
                        result['prior_review_patch_set'] = ps

            # 其他人的 -1/-2
            if author_name != self_username and score_val < 0:
                result['other_minus_one'] = True
                result['other_minus_one_details'].append({
                    'reviewer': author_name,
                    'score': score_val,
                    'is_substantive': is_substantive,
                    'message_snippet': msg_text[:300],
                })
                if is_substantive:
                    result['has_substantive_other_minus_one'] = True

        if withdrawn_match:
            entry = {
                'author': author_name,
                'score': 0,
                'message_snippet': msg_text[:200],
                'is_withdrawn': True,
            }
            result['score_history'].append(entry)
            if author_name != self_username:
                # 别人撤回的不算持续 -1
                pass

        # 检测 self 的 -1 被撤回
        if withdrawn_match and author_name == self_username:
            result['has_withdrawn'] = True

        # 提取特殊备注（owner 或 reviewer 的解释性 reply，不含分数变更）
        if not score_match and not withdrawn_match and msg_text.strip():
            # 非自动消息、非分数变更的 cover-level 消息视为特殊备注
            if len(msg_text.strip()) > 20:  # 过滤太短的
                result['special_notes'].append({
                    'author': author_name,
                    'message': msg_text[:500],
                    'type': 'cover_reply',
                })
                # v2.5.0 修正：识别 owner 的 cover-level 回复
                if author_name and owner_username and author_name == owner_username:
                    result['owner_cover_replies'].append({
                        'message': msg_text[:1000],
                        'date': msg.get('date', ''),
                    })
                    result['has_owner_reply'] = True

        # v2.5.0 修正：owner 在有分数变更的消息里也可能带 reply 文本
        if score_match and author_name and owner_username and author_name == owner_username:
            # owner 自己投 +1 同时可能带解释性文字
            clean_text = msg_text.replace(score_match.group(0), '').strip()
            if len(clean_text) > 30:
                result['owner_cover_replies'].append({
                    'message': clean_text[:1000],
                    'date': msg.get('date', ''),
                })
                result['has_owner_reply'] = True

    # 2. 从 inline comments 提取 self 历史评论 + owner 回复
    # 先建立 comment ID → comment 的索引
    comment_index = {}  # id → comment_obj (with path injected)
    for path, clist in comments.items():
        for c in clist:
            c_with_path = dict(c)
            c_with_path['_path'] = path
            comment_index[c.get('id', '')] = c_with_path

    for path, clist in comments.items():
        for c in clist:
            c_author = c.get('author', {})
            c_username = c_author.get('username') or c_author.get('name', '')
            c_id = c.get('id', '')
            reply_to = c.get('in_reply_to')

            if c_username == self_username:
                # self 的历史评论
                result['self_prior_comments'].append({
                    'path': path,
                    'line': c.get('line'),
                    'message': c.get('message', ''),
                    'id': c_id,
                    'patch_set': c.get('patch_set'),
                })
                result['has_prior_review'] = True
            elif reply_to and reply_to in comment_index:
                # 检查是否是对 self 评论的回复
                parent = comment_index[reply_to]
                parent_author = parent.get('author', {})
                parent_username = parent_author.get('username') or parent_author.get('name', '')
                if parent_username == self_username:
                    result['owner_replies'].append({
                        'reply_to_comment_id': reply_to,
                        'reply_to_message': parent.get('message', '')[:200],
                        'path': path,
                        'line': c.get('line'),
                        'message': c.get('message', ''),
                        'author': c_username,
                    })
                    # v2.5.0 修正：owner 回复 self 也计为 has_owner_reply
                    if c_username == owner_username:
                        result['has_owner_reply'] = True
                # v2.5.0 修正：owner 回复其他 reviewer 的评论也要捕获
                elif c_username == owner_username and parent_username != owner_username:
                    result['owner_inline_replies_to_others'].append({
                        'reply_to_comment_id': reply_to,
                        'reply_to_author': parent_username,
                        'reply_to_message': parent.get('message', '')[:200],
                        'path': path,
                        'line': c.get('line'),
                        'message': c.get('message', ''),
                    })
                    result['has_owner_reply'] = True
            else:
                # 其他 reviewer 的评论
                if c_username != self_username:
                    result['other_reviewer_comments'].append({
                        'path': path,
                        'line': c.get('line'),
                        'message': c.get('message', '')[:300],
                        'author': c_username,
                    })

    # v2.5.0 fix：计算代码是否有变动（以 patch_set 号为准）
    if result['prior_review_patch_set'] is not None and current_patch_set is not None:
        result['code_changed_since_prior_review'] = current_patch_set > result['prior_review_patch_set']
    elif result['has_prior_review'] and current_patch_set is not None:
        # 有历史评审但拿不到 patch_set 号（不应该发生）——保守判为未变为了安全
        result['code_changed_since_prior_review'] = False

    # v2.6.0 CL-5：真修复识别——比对每条 self 历史 inline comment 在新 PS 中的代码变化
    # 输出 code_change_per_comment，供 LLM 判断 owner reply 是否谁不同于“口头修复”
    try:
        result['code_change_per_comment'] = _compute_code_change_per_comment(
            cr, result['self_prior_comments'], result['owner_replies'],
            current_patch_set, result['prior_review_patch_set']
        )
    except Exception as e:
        result['code_change_per_comment'] = []
        result['_cl5_error'] = f'CL-5 计算失败: {e}'

    return result


# v2.6.0 CL-5 辅助函数
def _compute_code_change_per_comment(cr, self_comments, owner_replies, current_ps, prior_ps):
    """对每条 self 历史 inline，比对原 PS vs 当前 PS 代码是否变化。

    返回 [{comment_id, path, line, code_at_orig_ps, code_at_curr_ps,
            actually_changed, owner_reply, claims_fixed, fix_mismatch}, ...]
    """
    if not self_comments or not current_ps:
        return []

    # 构建 owner_replies 查找表：reply_to_comment_id -> reply message
    reply_by_target = {}
    for r in owner_replies:
        target = r.get('reply_to_comment_id', '')
        if target:
            reply_by_target[target] = r.get('message', '')

    # “已修复”关键词集合
    fixed_keywords = ['已修复', '已改', '已处理', '已完成', '已适配', '已调整',
                      'fixed', 'resolved', 'done', 'addressed', 'patched']

    out = []
    for sc in self_comments:
        cid = sc.get('id', '')
        path = sc.get('path', '')
        line = sc.get('line')
        # 获取原 PS 和当前 PS 的该行代码
        orig_ps = sc.get('patch_set') or prior_ps
        code_orig = _get_line_at_ps(cr, orig_ps, path, line) if orig_ps else None
        code_curr = _get_line_at_ps(cr, current_ps, path, line) if current_ps else None
        actually_changed = (code_orig is not None and code_curr is not None
                            and code_orig.strip() != code_curr.strip())

        # 查 owner reply
        owner_reply = reply_by_target.get(cid, '')
        claims_fixed = any(kw.lower() in owner_reply.lower() for kw in fixed_keywords)
        fix_mismatch = claims_fixed and (not actually_changed)

        out.append({
            'comment_id': cid,
            'path': path,
            'line': line,
            'orig_patch_set': orig_ps,
            'curr_patch_set': current_ps,
            'code_at_orig_ps': code_orig,
            'code_at_curr_ps': code_curr,
            'actually_changed': actually_changed,
            'owner_reply': owner_reply[:300] if owner_reply else '',
            'claims_fixed': claims_fixed,
            'fix_mismatch': fix_mismatch,
        })
    return out


def _get_line_at_ps(cr, ps, path, line):
    """从 Gerrit 拉取指定 PS 某文件某行的代码。拿不到返回 None。"""
    if not path or not line or not ps:
        return None
    try:
        from urllib.parse import quote
        encoded = quote(path, safe='')
        code, content = gget(f'/a/changes/{cr}/revisions/{ps}/files/{encoded}/content')
        if code != 200 or not content:
            return None
        # gget 返回的 content 此处可能是 base64；粗略按原始 str 判
        import base64
        if isinstance(content, str) and '\n' not in content[:200]:
            try:
                content = base64.b64decode(content).decode('utf-8', errors='replace')
            except Exception:
                pass
        if not isinstance(content, str):
            return None
        lines = content.split('\n')
        idx = line - 1
        if 0 <= idx < len(lines):
            return lines[idx]
    except Exception:
        return None
    return None


def compute_review_decision(prior, current_revision=None, force=False, build_failure=None):
    """v2.5.0 修正版核心决策函数：根据 prior_review_context 决定评审模式。

    返回 dict：
      mode: 'proceed' | 'skip' | 'incremental' | 'skip_build_failed'   (v2.6.0 新增)
      reason: 可读原因
      should_review: bool
      is_incremental: bool
      details: 诊断详情

    决策优先级：
      0. force=True → 总是 proceed
      0.5. v2.6.0 BUILD-FAIL-1：build_failure 不为空 → skip_build_failed（-2 跳过 LLM）
      1. owner 有任何 reply → incremental（规则 3）
      2. self 有历史评审 + owner 有 reply → incremental（规则 1）
      3. 其他人 -1/-2 但是「非实质 AI 评审」（如纯预审拒绝）→ proceed（规则 2）
      4. 其他人含实质 AI 评审的 -1/-2 + owner 无 reply + 代码未变 → skip
      5. self 有历史评审 + owner 无 reply + 代码未变 → skip
      6. 默认 → proceed
    """
    if force:
        return {
            'mode': 'proceed',
            'reason': '手动强制 (--force)',
            'should_review': True,
            'is_incremental': False,
            'details': {},
        }

    # v2.6.0 BUILD-FAIL-1 质量红线：预编译失败 → 直接 -2 跳过 LLM。
    # 优先级高于 force 以外的所有规则，但低于 force（手动覆盖场景）。
    if build_failure and build_failure.get('failed'):
        return {
            'mode': 'skip_build_failed',
            'reason': f'BUILD-FAIL-1 预编译失败（{build_failure.get("evidence", "")}）：P0 质量红线直接 -2，不走 LLM 评审流程',
            'should_review': False,
            'is_incremental': False,
            'details': {
                'failed_labels': build_failure.get('failed_labels', []),
                'rejected_by': build_failure.get('rejected_by', []),
            },
        }

    has_owner_reply = prior.get('has_owner_reply', False)
    has_prior_self_review = prior.get('has_prior_review', False)
    other_minus_one = prior.get('other_minus_one', False)
    has_substantive_other_minus_one = prior.get('has_substantive_other_minus_one', False)
    other_details = prior.get('other_minus_one_details', [])
    code_changed = prior.get('code_changed_since_prior_review', False)
    current_ps = prior.get('current_patch_set')
    prior_ps = prior.get('prior_review_patch_set')

    # v2.5.0 fix（质强 2026-05-12 反馈）：代码有变动 → 总是进行评审
    # 优先于 "self/他人 已 -1 跳过" 规则，但低于 "force" 和 "owner 有 reply" 设为中间优先级略略合适
    # 如果代码变了但同时 owner 也有 reply → incremental（下面规则 1 优先命中）
    # 如果代码变了但无 owner reply → 这里直接 proceed，owner 推 patchset 本身就是对前次评审的响应

    # 规则 1+3：owner 有 reply → incremental 评审
    if has_owner_reply:
        return {
            'mode': 'incremental',
            'reason': 'owner 有 reply，需增量评审评判 reply 合理性（v2.5.0 规则 1+3）',
            'should_review': True,
            'is_incremental': True,
            'details': {
                'has_prior_self_review': has_prior_self_review,
                'owner_cover_replies_count': len(prior.get('owner_cover_replies', [])),
                'owner_inline_replies_count': len(prior.get('owner_replies', [])) + len(prior.get('owner_inline_replies_to_others', [])),
                'code_changed': code_changed,
                'prior_patch_set': prior_ps,
                'current_patch_set': current_ps,
            },
        }

    # v2.5.0 fix：代码有变动 → 重新评审（重要修复，质强 2026-05-12 反馈）
    # 这个规则必须优先于后面的 skip 规则。owner 推 patchset = 默认育应前次评审（不需仅 reply）
    if has_prior_self_review and code_changed:
        return {
            'mode': 'incremental',
            'reason': f'self 已评审（PS{prior_ps} score={prior.get("prior_score")}），owner 已推新 patchset 到 PS{current_ps}，需增量评审检查旧问题是否修复（v2.5.0 规则 6 · 代码有变动）',
            'should_review': True,
            'is_incremental': True,
            'details': {
                'prior_score': prior.get('prior_score'),
                'prior_patch_set': prior_ps,
                'current_patch_set': current_ps,
                'self_prior_comments_count': len(prior.get('self_prior_comments', [])),
            },
        }

    # v2.5.0 fix：其他人已 -1 但代码有变动 → proceed。owner 推 patchset 表明已响应
    if other_minus_one and code_changed:
        return {
            'mode': 'proceed',
            'reason': f'其他 reviewer 已 -1，但 owner 推新 patchset (PS→{current_ps})，代码有变动，重新评审（v2.5.0 规则 6 · 代码有变动）',
            'should_review': True,
            'is_incremental': False,
            'details': {
                'current_patch_set': current_ps,
            },
        }

    # 规则 2：其他人仅「非实质 AI 评审」的 -1 → 需重新发起完整评审
    if other_minus_one and not has_substantive_other_minus_one and not has_prior_self_review:
        non_substantive_reviewers = [d['reviewer'] for d in other_details if not d.get('is_substantive', False)]
        return {
            'mode': 'proceed',
            'reason': f'其他人 -1/-2 仅为纯标记（无 AI 评审实质内容，如 {non_substantive_reviewers[0] if non_substantive_reviewers else "未知"} 自动预审拒绝），需重新发起完整评审（v2.5.0 规则 2）',
            'should_review': True,
            'is_incremental': False,
            'details': {
                'non_substantive_reviewers': non_substantive_reviewers,
            },
        }

    # 规则 4：其他人含实质 AI 评审的 -1 + 代码未变 + owner 无 reply → skip
    if has_substantive_other_minus_one and not has_owner_reply:
        substantive_reviewers = [d['reviewer'] for d in other_details if d.get('is_substantive', False)]
        return {
            'mode': 'skip',
            'reason': f'其他 reviewer ({substantive_reviewers}) 已给出含实质 AI 评审的 -1，且 owner 无 reply，代码未变，不重复评审（v2.5.0 规则 4）',
            'should_review': False,
            'is_incremental': False,
            'details': {
                'substantive_reviewers': substantive_reviewers,
            },
        }

    # 规则 5：self 有历史评审 + owner 无 reply + 代码未变 → skip
    if has_prior_self_review and not has_owner_reply:
        return {
            'mode': 'skip',
            'reason': f'self 已评审（score={prior.get("prior_score")}）且 owner 无 reply，代码未变，不重复评审（v2.5.0 规则 5）',
            'should_review': False,
            'is_incremental': False,
            'details': {
                'prior_score': prior.get('prior_score'),
                'self_prior_comments_count': len(prior.get('self_prior_comments', [])),
            },
        }

    # 默认：首评 → proceed
    return {
        'mode': 'proceed',
        'reason': '首评 / 代码有变动，进行完整评审',
        'should_review': True,
        'is_incremental': False,
        'details': {},
    }


# ============================================================
# v2.6.0 内部修订 (2026-05-15) · BUILD-FAIL-1 质量红线
# 预编译失败（Verified-1 / Prebuild-Check-1）直接 -2 跳过 LLM 评审
# ============================================================

def detect_build_failure(cr_or_detail):
    """检查 CR 当前 patchset 是否被构建系统标记为预编译失败。

    Args:
        cr_or_detail: CR number (str/int) 或 已拉取的 detail dict

    Returns:
        dict | None:
          {
            'failed': True,
            'failed_labels': ['Verified', 'Prebuild-Check'],   # 触发的 label 列表
            'rejected_by': [{'label': 'Verified', 'reviewer': 'scm_verify'}, ...],
            'evidence': '描述文本'
          }
        None 表示未失败 / 无法判定
    """
    if isinstance(cr_or_detail, dict):
        detail = cr_or_detail
    else:
        detail = get_cr_detail(cr_or_detail)
        if not isinstance(detail, dict):
            return None

    labels = detail.get('labels') or {}
    failed_labels = []
    rejected_by = []

    # 优先检查 Verified 与 Prebuild-Check（预编译/构建相关）
    BUILD_LABELS = ('Verified', 'Prebuild-Check')
    for ln in BUILD_LABELS:
        lab = labels.get(ln)
        if not lab:
            continue
        rej = lab.get('rejected')
        if rej:
            failed_labels.append(ln)
            rejected_by.append({
                'label': ln,
                'reviewer': rej.get('username') or rej.get('name', '<unknown>'),
            })
            continue
        # 兼容性：扫 all 中是否有 -1/-2
        for entry in (lab.get('all') or []):
            v = entry.get('value')
            if v is not None and v < 0:
                failed_labels.append(ln)
                rejected_by.append({
                    'label': ln,
                    'reviewer': entry.get('username') or entry.get('name', '<unknown>'),
                })
                break

    if not failed_labels:
        return None

    # 去重
    seen = set()
    uniq_failed = []
    for x in failed_labels:
        if x in seen:
            continue
        seen.add(x)
        uniq_failed.append(x)

    return {
        'failed': True,
        'failed_labels': uniq_failed,
        'rejected_by': rejected_by,
        'evidence': '、'.join(f'{r["label"]}-1 (by {r["reviewer"]})' for r in rejected_by),
    }


# v2.6.0 BUILD-FAIL-1 cover 模板
BUILD_FAIL_COVER_TEMPLATE = """### 评审结论：-2（质量红线 · 预编译失败）

当前 patchset 已被构建系统标记为 {evidence}（预编译失败）。按 gerrit-review v2.6.0 质量红线 BUILD-FAIL-1，预编译未通过的 CR 不进入代码评审流程，请 owner 自查代码并完成本地预编译验证（make / gradle / m clean install 等）后重新提交 patch。

> 本次未触发 7+1 维度 LLM 评审（节省 token）；预编译通过后再提交即可重新走完整评审。
"""
