#!/usr/bin/env python3
"""Remove finished worktrees under ~/worktrees (owner 2026-10-17: 234 worktrees, disk 91 %).

A worktree is removed only when ALL hold:
  1. clean — `git status --porcelain` (untracked included) is empty;
  2. finished — its HEAD is an ancestor of origin/<base> (dev › main › master), OR the branch is gone on origin and
     either HEAD is reachable from some origin/* ref or `gh pr list --head <branch> --state merged` finds a PR;
  3. not fresh — created more than 24 h ago (a new wt-new worktree is clean at the base tip until its first commit).
Then `git worktree remove` + `git branch -d` (safe delete; a squash-merged branch stays and is reported).
Dirty, open-PR or unpushed worktrees are listed, never touched. Test DBs are not dropped (reported as a count).
`--report` (list-only, deletes nothing): directories under the root that no repo's `git worktree list` knows (size via
`du -s`, last mtime) and exited `wtdb*` containers → logs/wt-prune-candidates.md (`--out` overrides). Deleting them
is the owner's decision.
Usage: wt-prune.py [--dry-run] [--quiet] [--root DIR] [--report [--out FILE] [--repo DIR ...]]. SessionStart runs it in the background (hooks/main-sync.py).
"""
import argparse
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _paths  # noqa: E402  (hooks/_paths.py)

ROOT = os.path.expanduser("~/worktrees")


def git(cwd, *args, timeout=30):
    try:
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return 1, ""


FRESH_SECONDS = 24 * 3600


def is_fresh(wt):
    """2026-11-23: wt-new makes a clean worktree whose HEAD is the base tip, so it looks «merged» until the first commit;
    another session's SessionStart pruned 4 just-created task worktrees under a working agent. Age = claude-owner
    marker (written by wt-new) or the worktree git dir."""
    rc, gitdir = git(wt, "rev-parse", "--absolute-git-dir")
    if rc or not gitdir:
        return False
    marker = os.path.join(gitdir, "claude-owner")
    path = marker if os.path.exists(marker) else gitdir
    return time.time() - os.path.getmtime(path) < FRESH_SECONDS


def main_repo(wt):
    rc, common = git(wt, "rev-parse", "--git-common-dir")
    if rc or not common:
        return ""
    common = common if os.path.isabs(common) else os.path.join(wt, common)
    return os.path.dirname(os.path.abspath(common))


def base_ref(repo):
    for b in ("dev", "main", "master"):
        if git(repo, "rev-parse", "--verify", "-q", f"origin/{b}")[0] == 0:
            return f"origin/{b}"
    return ""


def pr_merged(repo, branch):
    try:
        p = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number", "-q", "length"],
                           cwd=repo, capture_output=True, text=True, timeout=30)
        return p.returncode == 0 and p.stdout.strip() not in ("", "0")
    except (subprocess.TimeoutExpired, OSError):
        return False


def classify(wt, repo, base):
    _, dirty = git(wt, "status", "--porcelain")
    if dirty:
        return "dirty", ""
    rc, branch = git(wt, "symbolic-ref", "--short", "-q", "HEAD")
    branch = branch if rc == 0 else ""
    _, head = git(wt, "rev-parse", "HEAD")
    if base and git(wt, "merge-base", "--is-ancestor", head, base)[0] == 0:
        return "merged", branch
    if branch and git(repo, "rev-parse", "--verify", "-q", f"origin/{branch}")[0] == 0:
        return "open", branch          # remote branch still exists → PR open or unmerged work
    _, on_origin = git(repo, "branch", "-r", "--contains", head)
    if on_origin.strip():
        return "merged", branch        # reachable from another origin ref (integration branch)
    if branch and pr_merged(repo, branch):
        return "merged", branch        # squash/rebase merge: PR merged, commits not reachable
    return "unpushed", branch


def registered_worktrees(repos):
    paths = set()
    for repo in repos:
        rc, out = git(repo, "worktree", "list", "--porcelain")
        paths.update(os.path.realpath(l[9:]) for l in out.splitlines() if rc == 0 and l.startswith("worktree "))
    return paths


def known_repos(root, extra):
    """Repos seen from worktrees under root + this harness + owner checkout globs (private/wt-prune.json) + explicit --repo."""
    repos = {_paths.harness_dir(), *extra}
    for pat in _paths.private("wt-prune", {}).get("repo_globs", []):   # owner-only checkout globs, e.g. <dir>/*/.git
        repos.update(os.path.dirname(g) for g in glob.glob(pat))
    for name in sorted(os.listdir(root)):
        wt = os.path.join(root, name)
        if os.path.exists(os.path.join(wt, ".git")) and (r := main_repo(wt)):
            repos.add(r)
    return {r for r in repos if os.path.isdir(r)}


def dir_size_kb(path):
    try:
        p = subprocess.run(["du", "-sk", path], capture_output=True, text=True, timeout=60)
        return int(p.stdout.split()[0]) if p.returncode == 0 and p.stdout.split() else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def last_mtime(path):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    except OSError:
        return "?"


def exited_containers():
    try:
        p = subprocess.run(["docker", "ps", "-a", "--filter", "name=wtdb", "--filter", "status=exited",
                            "--format", "{{.Names}}\t{{.Status}}"], capture_output=True, text=True, timeout=20)
        return [l.split("\t") for l in p.stdout.splitlines() if l.strip()] if p.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        return []


def report(root, out, extra_repos):
    """List-only. Orphan = a directory under root that no known repo lists as a worktree."""
    reg = registered_worktrees(known_repos(root, extra_repos))
    rows = []
    for name in sorted(os.listdir(root)):
        wt = os.path.join(root, name)
        if os.path.isdir(wt) and os.path.realpath(wt) not in reg:
            rows.append((name, dir_size_kb(wt), last_mtime(wt)))
    lines = [f"# wt-prune candidates ({time.strftime('%Y-%m-%d %H:%M')}) — list only, nothing deleted", "",
             f"## Unregistered directories in {root} ({len(rows)})", "", "| dir | size MB | last mtime |", "|---|---|---|"]
    lines += [f"| {n} | {'?' if kb is None else kb // 1024} | {m} |" for n, kb, m in rows]
    cont = exited_containers()
    lines += ["", f"## Exited wtdb* containers ({len(cont)})", "", "| name | status |", "|---|---|"]
    lines += [f"| {c[0]} | {c[1] if len(c) > 1 else ''} |" for c in cont]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wt-prune --report: {len(rows)} unregistered dirs, {len(cont)} exited containers -> {out}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", default=_paths.data_dir("logs", "wt-prune-candidates.md"))
    ap.add_argument("--repo", action="append", default=[])
    a = ap.parse_args()
    if not os.path.isdir(a.root):
        return 0
    if a.report:
        return report(a.root, a.out, a.repo)
    fetched, stats, kept = set(), {"removed": 0, "dirty": 0, "open": 0, "unpushed": 0, "fresh": 0, "foreign": 0, "branch_kept": 0}, []
    for name in sorted(os.listdir(a.root)):
        wt = os.path.join(a.root, name)
        if not os.path.isdir(os.path.join(wt, ".git")) and not os.path.isfile(os.path.join(wt, ".git")):
            continue
        repo = main_repo(wt)
        if not repo or os.path.abspath(repo) == os.path.abspath(wt):
            stats["foreign"] += 1
            continue
        if repo not in fetched:
            git(repo, "fetch", "--prune", "--quiet", "origin", timeout=90)
            fetched.add(repo)
        kind, branch = classify(wt, repo, base_ref(repo))
        if kind == "merged" and is_fresh(wt):
            kind = "fresh"
        if kind != "merged":
            stats[kind] += 1
            kept.append(f"{kind}: {name} ({branch or 'detached'})")
            continue
        if a.dry_run:
            stats["removed"] += 1
            kept.append(f"would remove: {name} ({branch})")
            continue
        if git(repo, "worktree", "remove", wt, timeout=120)[0]:
            kept.append(f"remove failed: {name}")
            continue
        stats["removed"] += 1
        if branch and git(repo, "branch", "-d", branch)[0]:
            stats["branch_kept"] += 1
    for repo in fetched:
        git(repo, "worktree", "prune")
    if not a.dry_run:  # per-worktree MySQL containers (tools/wt-mysql.sh) whose worktree is gone
        try:
            p = subprocess.run([os.path.join(os.path.dirname(os.path.abspath(__file__)), "wt-mysql.sh"), "prune"],
                               capture_output=True, text=True, timeout=120)
            kept.extend(l for l in p.stdout.splitlines() if l)
        except (OSError, subprocess.TimeoutExpired):
            pass
    summary = ", ".join(f"{k}={v}" for k, v in stats.items() if v)
    print(f"wt-prune: {summary or 'nothing to do'}")
    if not a.quiet:
        print("\n".join(kept))
    return 0


if __name__ == "__main__":
    sys.exit(main())
