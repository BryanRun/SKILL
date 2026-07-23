#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate and sanitize gerrit-pipeline commit messages."""

import argparse
import os
import re
import subprocess
import sys
import tempfile


REQUIRED_FIELDS = [
    ("【Meego工作项URL】", 1, 300),
    ("【原因分析】", 8, 50),
    ("【解决方案】", 8, 50),
    ("【自测用例】", 20, 50),
    ("【自测方法】", 4, 50),
    ("【影响范围】", 8, 50),
    ("【代码修改量】", 0, 50),
    ("【提交项目/分支】", 0, 50),
    ("【体现版本】", 0, 50),
]

DEV_VIDEO_FIELD = "【开发自测视频】"
DEV_VIDEO_VALUE = "申请豁免，原因：已自测通过，请实车验证"

FIELD_ORDER = [item[0] for item in REQUIRED_FIELDS] + [DEV_VIDEO_FIELD]
FIELD_LIMITS = dict((field, (min_len, max_len)) for field, min_len, max_len in REQUIRED_FIELDS)

TITLE_TYPE_RE = re.compile(r"^【(bug|change|feature)】")
TITLE_FULL_RE = re.compile(r"^【(bug|change|feature)】【([^】\r\n]+)】(.+)$")
LEGACY_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
TOPIC_SEQ_RE = re.compile(r"【([0-9]+)/([0-9]+)】")
VERSION_RE = re.compile(r"^After [0-9]{4}/[0-9]{1,2}/[0-9]{1,2}$")
CHANGE_ID_RE = re.compile(r"^Change-Id:\s+I[0-9a-fA-F]{8,}$")
MEEGO_URL_RE = re.compile(r"^https://project\.feishu\.cn/[^/\s]+/[^/\s]+/detail/[^?\s]+(?:\?\S*)?$")

FORBIDDEN_TRAILER_PATTERNS = [
    re.compile(r"^\s*co-authored-by\s*:", re.IGNORECASE),
    re.compile(r"^\s*signed-off-by\s*:", re.IGNORECASE),
    re.compile(r"^\s*made-with\s*:\s*cursor\b", re.IGNORECASE),
]


def _split_message(message):
    return message.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _trim_trailing_empty(lines):
    lines = list(lines)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def normalize_message(message):
    return "\n".join(_trim_trailing_empty(_split_message(message))) + "\n"


def is_forbidden_trailer(line):
    return any(pattern.search(line) for pattern in FORBIDDEN_TRAILER_PATTERNS)


def sanitize_message(message):
    removed_count = 0
    cleaned_lines = []
    for line in _split_message(message):
        if is_forbidden_trailer(line):
            removed_count += 1
            continue
        cleaned_lines.append(line)
    return normalize_message("\n".join(cleaned_lines)), removed_count


def lint_message(message):
    errors = []
    lines = _trim_trailing_empty(_split_message(message))

    if not lines:
        return ["commit message 为空"]

    title = lines[0]
    if not TITLE_TYPE_RE.search(title):
        errors.append("标题格式不符，必须以【bug】、【change】或【feature】开头")

    title_match = TITLE_FULL_RE.search(title)
    if not title_match:
        errors.append("标题格式不符，必须包含【类型】【Meego工单ID或工作项ID】概要描述")
    else:
        work_item_id = title_match.group(2).strip()
        if not work_item_id:
            errors.append("缺少 Meego 工单 ID/工作项 ID 或未用【】包裹")
        elif LEGACY_JIRA_KEY_RE.search(work_item_id):
            errors.append("旧 Jira ID 已弃用，请填写 Meego 工单 ID/工作项 ID")

        summary_part = title_match.group(3)
        seq_matches = TOPIC_SEQ_RE.findall(title)
        if len(seq_matches) > 1:
            errors.append("标题中只能包含一个【x/y】标识")
        if seq_matches:
            if not re.search(r"【[0-9]+/[0-9]+】$", title):
                errors.append("【x/y】标识必须位于标题末尾")
            x_value, y_value = [int(v) for v in seq_matches[-1]]
            if x_value <= 0 or y_value <= 0:
                errors.append("【x/y】中 x 和 y 必须为正整数")
            if x_value > y_value:
                errors.append("【x/y】中 x 不能大于 y")
            summary_part = re.sub(r"【[0-9]+/[0-9]+】$", "", summary_part)
        if not summary_part.strip():
            errors.append("标题缺少概要描述")

    if len(lines) < 2 or lines[1] != "":
        errors.append("标题与 body 之间必须保留一个空行")

    field_counts = dict((field, 0) for field in FIELD_ORDER)
    field_positions = []
    template_lines = []
    change_id_lines = []
    body_lines = lines[2:] if len(lines) >= 3 else []

    for offset, line in enumerate(body_lines, 3):
        if line == "":
            continue

        if is_forbidden_trailer(line):
            errors.append("commit message 中存在禁止的模板外 trailer: 第 %d 行" % offset)
            continue

        if line.startswith("Change-Id:"):
            if not CHANGE_ID_RE.search(line):
                errors.append("Change-Id 格式错误: 第 %d 行" % offset)
            change_id_lines.append(offset)
            continue

        matched_field = None
        for field in FIELD_ORDER:
            if line.startswith(field):
                matched_field = field
                break

        if matched_field is None:
            errors.append("commit message 中存在模板外的多余行: 第 %d 行" % offset)
            continue

        content = line[len(matched_field):]
        field_counts[matched_field] += 1
        field_positions.append((matched_field, offset))
        template_lines.append(offset)

        if matched_field == DEV_VIDEO_FIELD:
            if content != DEV_VIDEO_VALUE:
                errors.append("%s 内容必须为固定值" % DEV_VIDEO_FIELD)
            continue

        if matched_field == "【Meego工作项URL】" and not MEEGO_URL_RE.search(content):
            errors.append("【Meego工作项URL】格式错误，必须为 https://project.feishu.cn/<project>/<type>/detail/<id>")

        min_len, max_len = FIELD_LIMITS[matched_field]
        content_len = len(content)
        if min_len > 0 and content_len < min_len:
            errors.append("%s 内容不足 %d 字（当前 %d 字）" % (matched_field, min_len, content_len))
        if content_len > max_len:
            errors.append("%s 内容超过 %d 字（当前 %d 字）" % (matched_field, max_len, content_len))
        if matched_field == "【体现版本】" and not VERSION_RE.search(content):
            errors.append("【体现版本】格式错误，必须为 After YYYY/M/D")

    for field, _min_len, _max_len in REQUIRED_FIELDS:
        if field_counts[field] == 0:
            errors.append("缺少 %s" % field)
        if field_counts[field] > 1:
            errors.append("%s 只能出现一次" % field)
    if field_counts[DEV_VIDEO_FIELD] > 1:
        errors.append("%s 只能出现一次" % DEV_VIDEO_FIELD)

    last_order_index = -1
    for field, line_no in field_positions:
        order_index = FIELD_ORDER.index(field)
        if order_index < last_order_index:
            errors.append("字段顺序错误: %s 位于错误位置（第 %d 行）" % (field, line_no))
            break
        last_order_index = order_index

    if len(change_id_lines) > 1:
        errors.append("Change-Id 只能出现一次")
    if change_id_lines and template_lines and min(change_id_lines) < max(template_lines):
        errors.append("Change-Id 必须位于模板字段之后")

    return errors


def _run_git(args, cwd=None, check=True):
    proc = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc


def read_head_message():
    return _run_git(["log", "-1", "--format=%B"]).stdout


def ensure_clean_index():
    proc = _run_git(["diff", "--cached", "--quiet"], check=False)
    if proc.returncode == 1:
        raise RuntimeError("index 中仍有 staged 变更，拒绝执行 message-only amend")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "无法检查 staged 变更")


def amend_head_message(message):
    ensure_clean_index()
    fd, path = tempfile.mkstemp(prefix="gerrit-pipeline-commit-msg-", text=True)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(message)
        _run_git(["commit", "--amend", "-F", path])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def print_errors(errors):
    for error in errors:
        print("ERROR: %s" % error, file=sys.stderr)


def cmd_lint(args):
    if args.message_file:
        with open(args.message_file, "r", encoding="utf-8") as handle:
            message = handle.read()
    else:
        message = read_head_message()

    errors = lint_message(message)
    if errors:
        print_errors(errors)
        return 1
    print("commit message guard: OK")
    return 0


def cmd_sanitize_head(_args):
    original = read_head_message()
    cleaned, removed_count = sanitize_message(original)

    if removed_count:
        amend_head_message(cleaned)
        print("commit message guard: removed %d forbidden trailer line(s)" % removed_count)

    errors = lint_message(read_head_message())
    if errors:
        print_errors(errors)
        return 1
    print("commit message guard: OK")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Validate gerrit-pipeline commit messages.")
    subparsers = parser.add_subparsers(dest="command")

    lint_parser = subparsers.add_parser("lint", help="Validate a message file or HEAD commit message.")
    lint_parser.add_argument("--message-file", help="Validate the given commit message file instead of HEAD.")
    lint_parser.set_defaults(func=cmd_lint)

    sanitize_parser = subparsers.add_parser(
        "sanitize-head",
        help="Remove known forbidden attribution trailers from HEAD, amend, then validate.",
    )
    sanitize_parser.set_defaults(func=cmd_sanitize_head)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
