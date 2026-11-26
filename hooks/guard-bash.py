#!/usr/bin/env python3
"""PreToolUse(Bash) gate — deterministic denies for the things the rules forbid.

Denies (JSON permissionDecision=deny) when the command:
  * pushes directly to a protected branch (master/main/dev) or force-pushes anywhere protected;
  * opens a PR into master/main while the local repo has origin/dev (unless --head dev = release);
  * bypasses git hooks (`git commit --no-verify` / `-n` inside the commit segment);
  * runs destructive DB commands outside a test database (migrate:fresh, migrate:reset, db:wipe,
    DROP DATABASE/TABLE) — locally or over ssh;
  * `rm -rf` outside scratch/build/dependency paths;
  * `git reset --hard` / `git clean -f` / `git checkout -- .` inside a user's main checkout
    (not an agent worktree);
  * opens a non-draft PR into dev/master/main (or marks one ready) whose diff touches UI files while no
    `artifacts/ui-qa/*/scorecard.md` says `Verdict: PASS` newer than the last UI commit — unless the body
    says `design-panel: n/a — <reason>` (design gate, 2026-09-26: panels were skipped on 4 products); a scorecard
    dated 2026-11-25 or later must also have a `## State matrix` with no empty row (screenshot or n/a reason);
  * writes to the GitHub copy of a repo moved to another forge (FORGE_MOVED: gh pr/issue/run/workflow/release, writing
    `gh api`, `git push` to the configured GitHub org) — the push mirror would erase it. Owner-only: private/forge-moved.json.
Everything else passes silently. Escape hatch for a conscious human decision: prefix the
command with `CLAUDE_GUARD_OFF=1 `.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402  (hooks/_paths.py)

PROTECTED = ("master", "main", "dev")
SAFE_RM_HINTS = ("/tmp/", "scratchpad", "node_modules", "vendor/", "/dist", "/build", ".venv", "venv-", "/worktrees/",
                 "__pycache__", ".cache", "storage/framework", ".claude/worktrees", "/artifacts",
                 ".pytest_cache", ".next", ".nuxt", ".output", "coverage")
TEST_DB_HINTS = ("testing", "_test", "test_", "sqlite", ":memory:",
                 *_paths.private("test-db-hints", []))   # owner-only extra test-DB names (private/test-db-hints.json)


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "guard-bash: " + reason,
    }}))
    sys.exit(0)


def segments(cmd: str):
    # split a shell line into pipeline/sequence segments; good enough for guarding
    return [s.strip() for s in re.split(r"&&|\|\||;|\|(?!\|)|\n", cmd) if s.strip()]


def has_origin_dev(cwd: str) -> bool:
    try:
        r = subprocess.run(["git", "rev-parse", "--verify", "-q", "origin/dev"], cwd=cwd,
                           capture_output=True, text=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def remote_has_dev(repo: str) -> bool:
    """`gh api` check for a dev branch on GitHub; unknown/offline → treat as no dev (allow)."""
    try:
        r = subprocess.run(["gh", "api", f"repos/{repo}/branches/dev", "--silent"], capture_output=True,
                           text=True, timeout=4)
        return r.returncode == 0
    except Exception:
        return False


UI_FILE = re.compile(r"\.(vue|tsx|jsx|svelte|astro|html|css|scss|sass|less|postcss)$|\.blade\.php$")
UI_EXEMPT = re.compile(r"(^|/)(tests?|e2e|__tests__|docs|fixtures|stories|storybook|mail|emails?)/|\.(spec|test|stories)\.")


def git(repo: str, *args: str) -> str:
    if time.monotonic() - START > DEADLINE_S:
        return ""
    try:
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=3)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


START = time.monotonic()
DEADLINE_S = 7.0  # the hook has 10 s; past this every git/gh call returns "" and the gate fails open

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
WRAPPERS = {"sudo", "command", "exec", "time", "env", "nohup"}
GH_LONG = {"--base": "base", "--head": "head", "--body-file": "body_file", "--body": "body", "--title": "title",
           "--repo": "repo"}
GH_SHORT = {"-B": "base", "-H": "head", "-F": "body_file", "-b": "body", "-t": "title", "-R": "repo"}


def strip_heredocs(cmd: str) -> str:
    """Drop heredoc BODIES (text, not commands); the `<<EOF` opener line stays."""
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        delims = [m.group(2) for m in HEREDOC.finditer(lines[i])]
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1
    return "\n".join(out)


def newlines_to_separators(s: str) -> str:
    """Unquoted newline → `;`, unquoted `# comment` dropped; quoted text untouched."""
    out, q, i = [], None, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and q != "'" and i + 1 < len(s):
            out.append(s[i:i + 2]); i += 2; continue
        if q:
            if c == q:
                q = None
        elif c in ("'", '"'):
            q = c
        elif c == "\n":
            c = ";"
        elif c == "#" and (i == 0 or s[i - 1] in " \t;&|("):
            j = s.find("\n", i)
            i = len(s) if j < 0 else j
            continue
        out.append(c); i += 1
    return "".join(out)


def shell_commands(cmd: str):
    """Simple commands as token lists (shell-aware: quotes, heredocs, ; && || | ( )); None if unparsable."""
    lex = shlex.shlex(newlines_to_separators(strip_heredocs(cmd)), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        toks = list(lex)
    except ValueError:
        return None
    cmds = [[]]
    for t in toks:
        if t and all(ch in ";&|()" for ch in t):
            cmds.append([])
        else:
            cmds[-1].append(t)
    out = []
    for c in cmds:
        while c and (re.match(r"^\w+=", c[0]) or c[0] in WRAPPERS):
            c = c[1:]
        if c:
            out.append(c)
    return out


def parse_gh_tokens(toks) -> dict:
    """Flags of `gh pr <sub> …` tokens (after `gh pr <sub>`)."""
    out: dict = {"args": []}
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if t.startswith("--"):
            name, eq, val = t.partition("=")
            if name in GH_LONG:
                out[GH_LONG[name]] = val if eq else nxt
                i += 0 if eq else 1
            elif name == "--draft":
                out["draft"] = val.lower() not in ("false", "0") if eq else True
            elif name in ("--undo", "--dry-run", "--web", "--fill-verbose"):
                out[name[2:]] = True
        elif t.startswith("-") and len(t) >= 2:
            key = GH_SHORT.get(t[:2])
            if key:
                attached = t[2:].lstrip("=")
                out[key] = attached or nxt
                i += 0 if attached else 1
            elif t == "-d":
                out["draft"] = True
            elif t == "-w":
                out["web"] = True
        else:
            out["args"].append(t)
        i += 1
    return out


def repo_matches_origin(cwd: str, repo: str) -> bool:
    url = git(cwd, "remote", "get-url", "origin").strip().lower()
    return bool(url) and re.sub(r"\.git$", "", url).endswith("/" + repo.lower().removesuffix(".git"))


def resolve_dir(cur: str, arg: str) -> str:
    path = os.path.expanduser(arg)
    path = path if os.path.isabs(path) else os.path.normpath(os.path.join(cur, path))
    return path if os.path.isdir(path) else cur


def gh_invocations(cmd: str, cwd: str):
    """(sub, flags, dir) for every real `gh pr create|ready|edit` in the command line, with the cd-tracked dir."""
    cmds = shell_commands(cmd)
    if cmds is None:
        return []
    cur, found = cwd, []
    for c in cmds:
        if c[0] in ("cd", "pushd") and len(c) > 1:
            cur = resolve_dir(cur, c[1])
        elif c[0] == "git" and len(c) > 2 and c[1] == "-C":
            pass  # git -C does not change the shell's dir
        elif c[0] == "gh" and len(c) >= 3 and c[1] == "pr" and c[2] in ("create", "ready", "edit"):
            found.append((c[2], parse_gh_tokens(c[3:]), cur))
    return found


def default_base(repo: str) -> str:
    ref = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD").strip()
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    return "dev" if has_origin_dev(repo) else ""


def gh_pr_refs(repo: str, number: str):
    if time.monotonic() - START > DEADLINE_S:
        return "", ""
    try:
        r = subprocess.run(["gh", "pr", "view", *( [number] if number else [] ), "--json", "baseRefName,headRefName"],
                           cwd=repo, capture_output=True, text=True, timeout=4)
        d = json.loads(r.stdout) if r.returncode == 0 else {}
        return d.get("baseRefName", ""), d.get("headRefName", "")
    except Exception:
        return "", ""


def scorecard_roots(repo: str):
    roots = []
    top = git(repo, "rev-parse", "--show-toplevel").strip()
    if top:
        roots.append(top)
    main = git(repo, "worktree", "list", "--porcelain").splitlines()
    if main and main[0].startswith("worktree "):
        roots.append(main[0][len("worktree "):])
    return list(dict.fromkeys(roots or [repo]))


MATRIX_FROM = "2026-11-25"  # scorecards dated on/after this need a complete `## State matrix` (I11); older keep the old rule
MATRIX_STATES = ("loading", "first-use empty", "no results", "error", "partial data", "no permission",
                 "disabled+reason", "long text", "1000 rows")


def _filled(cell: str) -> bool:
    c = cell.strip().strip("`").strip()
    return bool(c) and c not in ("-", "—", "–") and not re.fullmatch(r"<[^>]*>", c)


def scorecard_date(text: str) -> str:
    m = re.search(r"^#[^\n]*?(\d{4}-\d{2}-\d{2})", text[:400], re.M)
    return m.group(1) if m else ""


def matrix_empty_rows(text: str):
    """None = legacy scorecard (not subject to the matrix rule); else the state names whose row is missing or empty
    (no screenshot and no n/a reason)."""
    if scorecard_date(text) < MATRIX_FROM:
        return None
    sec = re.search(r"^##\s+State matrix\b.*?(?=^##\s|\Z)", text, re.M | re.S)
    rows = {}
    for line in (sec.group(0).splitlines() if sec else []):
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if len(cells) < 4 or re.fullmatch(r"[-: ]*", cells[0]):
            continue
        rows[re.sub(r"\s+", " ", cells[0].lower().replace("\\", ""))] = cells
    empty = []
    for st in MATRIX_STATES:
        cells = next((v for k, v in rows.items() if k.startswith(st)), None)
        if not cells or not (_filled(cells[1]) or _filled(cells[3])):
            empty.append(st)
    return empty


# Every PASS scorecard needs a clean dead-click report (owner 2026-11-26: "половина кнопок не работает" on a dashboard
# that passed screenshots + judge — nothing clicked the controls). No date grace: in-flight UI PRs are gated too.
DEAD_VERDICTS = ("NO_EFFECT", "ERROR")


def interaction_problem(card_dir: str, text: str, since: int):
    """None = ok or `Interaction: n/a — <reason>`; else why `<card_dir>/dead-clicks/report.json`
    (tools/dead-clicks.mjs) fails: missing, older than the last UI commit, empty, or unallowlisted dead controls."""
    if re.search(r"^Interaction:\s*n/?a\s*[—–-]+\s*\S", text, re.M | re.I):
        return None
    rep = os.path.join(card_dir, "dead-clicks", "report.json")
    try:
        with open(rep, encoding="utf-8") as fh:
            rows = json.load(fh)
        fresh = os.path.getmtime(rep) >= since
    except (OSError, ValueError):
        return "no dead-clicks/report.json next to it (node ~/.claude/tools/dead-clicks.mjs --out <slug dir>/dead-clicks)"
    if not fresh:
        return "dead-clicks/report.json is older than the last UI commit"
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    dead = [r for r in rows if r.get("verdict") in DEAD_VERDICTS and not r.get("allowed")]
    if not rows:
        return "dead-clicks/report.json probed 0 controls"
    shown = ", ".join(f"{r.get('verdict')} «{str(r.get('text', ''))[:30]}»" for r in dead[:3])
    return f"dead-clicks: {len(dead)} control(s) without effect or with an error: {shown}" if dead else None


def geometry_problem(card_dir: str, text: str, since: int):
    """None = ok or `Geometry: n/a — <reason>`; else why `<card_dir>/geometry/report.json` (tools/ui-geometry.mjs)
    fails: missing, older than the last UI commit, unreadable, or summary.errors != 0. No date grace."""
    if re.search(r"^Geometry:\s*n/?a\s*[—–-]+\s*\S", text, re.M | re.I):
        return None
    rep = os.path.join(card_dir, "geometry", "report.json")
    try:
        with open(rep, encoding="utf-8") as fh:
            data = json.load(fh)
        fresh = os.path.getmtime(rep) >= since
    except (OSError, ValueError):
        return "no geometry/report.json next to it (node ~/.claude/tools/ui-geometry.mjs --out <slug dir>/geometry)"
    if not fresh:
        return "geometry/report.json is older than the last UI commit"
    errors = (data.get("summary") or {}).get("errors") if isinstance(data, dict) else None
    if not isinstance(errors, int):
        return "geometry/report.json has no summary.errors"
    return f"geometry: {errors} error(s) in geometry/report.json (fix the layout or mark intent with [data-geometry-ignore])" if errors else None


def card_problems(card_dir: str, since: int):
    """None = not a fresh PASS scorecard; [] = complete PASS; else the list of reasons it is incomplete."""
    sc = os.path.join(card_dir, "scorecard.md")
    with open(sc, encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    if not (re.search(r"^Verdict:\s*PASS\s*$", text[:2000], re.M) and os.path.getmtime(sc) >= since):
        return None
    name, out = os.path.basename(card_dir), []
    empty = matrix_empty_rows(text)
    if empty:
        out.append(f"{name}/scorecard.md: State matrix has empty rows: {', '.join(empty)}")
    for why in (interaction_problem(card_dir, text, since), geometry_problem(card_dir, text, since)):
        if why:
            out.append(f"{name}/scorecard.md: {why}")
    return out


def fresh_pass(roots, since: int, problems=None) -> bool:
    for root in roots:
        art = os.path.join(root, "artifacts", "ui-qa")
        try:
            slugs = os.listdir(art)
        except OSError:
            continue
        for d in slugs:
            try:
                found = card_problems(os.path.join(art, d), since)
            except OSError:
                continue
            if found == []:
                return True
            if found and problems is not None:
                problems.extend(found)
    return False


def design_gate(cmd: str, sub: str, f: dict, repo: str) -> None:
    """Non-draft PR into an integration base with UI files changed → needs a fresh PASS scorecard."""
    if sub == "edit" or f.get("draft") or f.get("undo") or f.get("dry-run"):
        return
    if f.get("repo") and not repo_matches_origin(repo, f["repo"]):
        return  # another repo we cannot inspect locally → not gated
    if sub == "ready":
        base, head = gh_pr_refs(repo, (f["args"] or [""])[0])
        if not base:
            return  # cannot resolve → fail open
    else:
        base, head = f.get("base") or default_base(repo), f.get("head", "")
    if base not in PROTECTED or head == "dev":  # subtask PRs into task/<slug>; release merge dev → master
        return
    body = cmd + "\n" + f.get("body", "")
    if f.get("body_file"):
        bf = os.path.expanduser(f["body_file"])
        bf = bf if os.path.isabs(bf) else os.path.join(repo, bf)
        try:
            body += open(bf, encoding="utf-8", errors="ignore").read()
        except (OSError, ValueError):
            pass
    if re.search(r"design-panel:\s*n/?a\b", body, re.I):
        return
    head_ref = "HEAD"
    if head:
        head_ref = next((c for c in (head, f"origin/{head}")
                         if git(repo, "rev-parse", "--verify", "-q", c).strip()), "")
        if not head_ref:
            return  # named head not available locally → fail open
    if not git(repo, "rev-parse", "--verify", "-q", f"origin/{base}").strip():
        return  # no remote base ref locally → fail open
    files = [x for x in git(repo, "diff", "--name-only", f"origin/{base}...{head_ref}").splitlines()
             if UI_FILE.search(x) and not UI_EXEMPT.search(x)]
    if not files:
        return
    last_ui = git(repo, "log", "-1", "--format=%ct", f"origin/{base}..{head_ref}", "--", *files).strip()
    problems: list = []
    if fresh_pass(scorecard_roots(repo), int(last_ui) if last_ui.isdigit() else 0, problems):
        return
    if problems:
        deny("design gate: a PASS scorecard exists but is not complete — " + "; ".join(problems[:3]) +
             " — every State matrix row needs a screenshot or an 'n/a reason'; every control needs an effect in "
             "dead-clicks/report.json (allowlist only with a reason) or the scorecard says 'Interaction: n/a — <reason>'; "
             "geometry/report.json (tools/ui-geometry.mjs) with 0 errors or 'Geometry: n/a — <reason>' "
             "(templates/project/design-scorecard.md § State matrix, § Interaction, § Geometry)")
    shown = ", ".join(files[:4]) + (f" (+{len(files) - 4})" if len(files) > 4 else "")
    deny(f"design gate: UI files changed ({shown}) and no artifacts/ui-qa/*/scorecard.md with a line "
         "'Verdict: PASS' newer than the last UI commit (PR worktree or main checkout) — run the design panel "
         "(/qa-verify UI gate, /ui-task step 6) or, for a non-visual/tiny change, put "
         "'design-panel: n/a — <reason>' in the PR body")


def rule1_gate(sub: str, f: dict, repo: str) -> None:
    """PR (or base change) into master/main while a dev branch exists — only the release merge dev → master."""
    if sub not in ("create", "edit") or f.get("base") not in ("master", "main") or f.get("head") == "dev":
        return
    if f.get("repo") and not repo_matches_origin(repo, f["repo"]):
        has_dev = remote_has_dev(f["repo"])
    else:
        has_dev = has_origin_dev(repo)
    if has_dev:
        deny(f"PR into {f['base']!r} while a dev branch exists — base must be dev (core rule 1)")


# Repos moved to another git forge: their GitHub copies are push mirrors, anything written there directly (PR, merge,
# push) is lost on the next mirror sync. Owner-only data: private/forge-moved.json (absent = gate silently off).
FORGE = _paths.private("forge-moved", {})
FORGE_MOVED = tuple(FORGE.get("repos") or ())
GH_ORG = FORGE.get("github_org") or ""
RM_PROTECTED = ("/", "/*", "~", "~/", "$HOME", *_paths.private("rm-protect", []))   # + owner web roots
GH_WRITE_SUBS = ("pr", "issue", "run", "workflow", "release")


def moved_repo_name(cwd: str, explicit: str) -> str:
    """Name of a moved repo the command targets (explicit -R value or the dir's origin), else ''."""
    target = explicit.lower() if explicit else git(cwd, "remote", "get-url", "origin").strip().lower()
    host, org = re.escape(FORGE["forge_host"]), re.escape(FORGE["forge_org"])
    for name in FORGE_MOVED:
        if re.search(rf"({re.escape(GH_ORG)}/|{host}[:/]{org}/){name}(\.git)?/?$", target):
            return name
    return ""


def gh_targets_moved_repo(c: list, cur: str) -> str:
    if c[1] == "api":
        write = any(t in ("-f", "-F", "--field", "--raw-field", "--input") for t in c) or re.search(
            r"(-X|--method)\s*(POST|PATCH|PUT|DELETE)", " ".join(c), re.I)
        m = re.search(rf"repos/{re.escape(GH_ORG)}/([a-z0-9_.-]+)", " ".join(c), re.I)
        return m.group(1).lower() if write and m and m.group(1).lower() in FORGE_MOVED else ""
    if c[1] not in GH_WRITE_SUBS:
        return ""
    explicit = next((c[i + 1] for i, t in enumerate(c[:-1]) if t in ("-R", "--repo")), "")
    return moved_repo_name(cur, explicit)


def forge_moved_gate(cmd: str, cwd: str) -> None:
    if not FORGE_MOVED:
        return
    cmds = shell_commands(cmd)
    cur = cwd
    for c in cmds or []:
        if c[0] in ("cd", "pushd") and len(c) > 1:
            cur = resolve_dir(cur, c[1])
            continue
        name = gh_targets_moved_repo(c, cur) if c[0] == "gh" and len(c) >= 2 else ""
        if not name and c[0] == "git" and "push" in c and any(
                re.search(rf"github\.com[:/]{re.escape(GH_ORG)}/", t, re.I) for t in c):
            name = next((n for n in FORGE_MOVED if any(n in t.lower() for t in c)), "")
        if name:
            host, org = FORGE["forge_host"], FORGE["forge_org"]
            deny(f"{name} moved to {FORGE.get("forge_name", "another forge")} https://{host}/{org}/{name} ({FORGE.get('moved_on', '')}); GitHub "
                 f"{GH_ORG}/{name} is a push mirror — writes there are lost. Use `tea` "
                 f"(tea pr create --repo {org}/{name} --base dev --head <branch> …) and `git push origin`.")


def is_agent_worktree(cwd: str) -> bool:
    return (f"/tmp/claude-{os.getuid()}/" in cwd or "/.claude/worktrees/" in cwd or "/scratchpad/" in cwd
            or "/worktrees/wt-" in cwd)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd or cmd.lstrip().startswith("CLAUDE_GUARD_OFF=1"):
        return
    cwd = data.get("cwd") or os.getcwd()
    low = cmd.lower()

    forge_moved_gate(cmd, cwd)
    for sub, flags, repo in gh_invocations(cmd, cwd):  # shell-aware: text in quotes/heredocs is not a command
        rule1_gate(sub, flags, repo)
        design_gate(cmd, sub, flags, repo)

    for seg in segments(cmd):
        toks = seg.split()
        # --- git push -------------------------------------------------------------------------
        if re.match(r"^git\s+(-C\s+\S+\s+)?push\b", seg):
            force = bool(re.search(r"\s(--force|-f|--force-with-lease)(\s|$)", seg))
            refspecs = [t for t in toks[2:] if not t.startswith("-")]
            targets = []
            for t in refspecs:
                t2 = t.split(":")[-1]
                targets.append(t2)
            hits = [t for t in targets if t in PROTECTED]
            if force and (hits or len(refspecs) <= 1):
                deny(f"force-push to a protected or unspecified branch is forbidden ({seg[:80]})")
            if hits:
                deny(f"direct push to protected branch {hits[0]!r} — use a PR (core rule 1)")
        # --- git commit --no-verify ---------------------------------------------------------
        if re.match(r"^git\s+(-c\s+\S+\s+)*(-C\s+\S+\s+)?commit\b", seg):
            if re.search(r"\s(--no-verify|-n)(\s|$)", seg):
                deny("git commit --no-verify / -n bypasses hooks — forbidden")
        # --- destructive git in the user's main checkout ------------------------------------
        if re.match(r"^git\s+(-C\s+\S+\s+)?(reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s+\.)", seg):
            if not is_agent_worktree(cwd) and not re.search(rf"-C\s+/tmp/claude-{os.getuid()}", seg):
                deny("destructive git command in the user's checkout — work in a worktree (core rule 1)")
    # --- destructive DB ---------------------------------------------------------------------
    if re.search(r"(migrate:fresh|migrate:reset|db:wipe|drop\s+database|drop\s+table)", low):
        if not any(h in low for h in TEST_DB_HINTS):
            deny("destructive DB command without a test-DB hint (testing/_test/sqlite) — forbidden on dev/prod data")
    # --- rm -rf ------------------------------------------------------------------------------
    for m in re.finditer(r"(?:^|[;&|]\s*|\bsudo\s+)rm\s+(-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*|-r\s+-f|-f\s+-r)\s+(.+?)(?=(&&|\|\||;|$))", cmd):
        targets = [t for t in m.group(2).split() if not t.startswith("-")]
        for t in targets:
            if t in RM_PROTECTED:
                deny(f"rm -rf on {t!r}")
            if not any(h in t for h in SAFE_RM_HINTS):
                deny(f"rm -rf outside scratch/build/dependency paths: {t!r} — delete explicitly with a plain rm or move to trash")


if __name__ == "__main__":
    main()
