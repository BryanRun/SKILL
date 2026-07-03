#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensure HEAD is based on the latest target branch before Gerrit push."""

import argparse
import re
import subprocess
import sys


DEFAULT_REMOTE = "autolink"
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/@+-]+$")


def run_git(args, check=True):
    proc = subprocess.run(
        ["git"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc


def validate_ref_name(value, label):
    if not value or value.startswith("-") or ".." in value or value.endswith(".lock"):
        raise RuntimeError("%s 非法: %s" % (label, value))
    if not BRANCH_RE.search(value):
        raise RuntimeError("%s 包含非法字符: %s" % (label, value))


def fetch_target(remote, branch):
    run_git(["fetch", "--quiet", remote, branch])


def is_ancestor(ancestor, descendant):
    proc = run_git(["merge-base", "--is-ancestor", ancestor, descendant], check=False)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise RuntimeError(proc.stderr.strip() or "无法判断分支基线关系")


def rev_parse(ref):
    return run_git(["rev-parse", "--short", ref]).stdout.strip()


def guard_head(remote, branch, fetch=True, base_ref=None):
    validate_ref_name(remote, "remote")
    validate_ref_name(branch, "branch")

    if fetch:
        fetch_target(remote, branch)
        target_ref = "FETCH_HEAD"
        target_label = "%s/%s" % (remote, branch)
    else:
        target_ref = base_ref or "%s/%s" % (remote, branch)
        target_label = target_ref

    if not is_ancestor(target_ref, "HEAD"):
        target_short = rev_parse(target_ref)
        head_short = rev_parse("HEAD")
        raise RuntimeError(
            "HEAD(%s) 未基于最新 %s(%s)，请先 rebase/merge 目标分支后再 push"
            % (head_short, target_label, target_short)
        )

    print("base branch guard: OK (%s is ancestor of HEAD)" % target_label)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Block Gerrit push when HEAD is behind target branch.")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help="Git remote name, default: autolink.")
    parser.add_argument("--branch", required=True, help="Target branch name used in refs/for/<branch>.")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip fetching and check the local remote-tracking ref instead.",
    )
    parser.add_argument(
        "--base-ref",
        help="Explicit base ref to check when --no-fetch is used. Defaults to <remote>/<branch>.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return guard_head(
            remote=args.remote,
            branch=args.branch,
            fetch=not args.no_fetch,
            base_ref=args.base_ref,
        )
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
