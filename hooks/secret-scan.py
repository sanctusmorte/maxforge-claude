#!/usr/bin/env python3
"""PreToolUse(Bash) secret gate — scans the staged diff before any `git commit`.

Denies the commit when added lines contain credential-looking strings or when a secret-bearing
file is staged (.env, *.pem, id_rsa, *.key, service-account json). Uses gitleaks when installed,
otherwise a built-in regex set. Files named *.example / *.sample / *.md / test fixtures are
skipped for value patterns but still reported for key files. Escape hatch (conscious decision):
prefix the command with `CLAUDE_ALLOW_SECRETS=1 `.
"""
import json
import os
import re
import shutil
import subprocess
import sys

VALUE_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}|gho_[A-Za-z0-9]{36}", "GitHub token"),
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "Anthropic API key"),
    (r"sk-(proj-)?[A-Za-z0-9_\-]{32,}", "OpenAI-style secret key"),
    (r"xox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED)? ?PRIVATE KEY-----", "private key"),
    (r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b", "Telegram bot token"),
    (r"(?i)\b(api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|password|passwd|jwt[_-]?secret|app[_-]?key)\b\s*[=:]\s*['\"]?(?!\$\{)(?!\$[A-Z])(?!<)(?!\{\{)(?!your[_-])(?!changeme)(?!example)(?!secret\b)(?!password\b)(?!null\b)(?!true\b)(?!false\b)[A-Za-z0-9_\-/+=.]{16,}", "credential assignment"),
    (r"(?i)(mysql|postgres(ql)?|redis|amqp|mongodb(\+srv)?)://[^:\s/]+:[^@\s]{6,}@", "connection string with password"),
]
KEY_FILES = re.compile(r"(^|/)(\.env(\.[a-z0-9_-]+)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.pfx|.*\.key|.*service[-_]?account.*\.json|.*credentials\.json)$")
SKIP_VALUE_SCAN = re.compile(r"(\.example|\.sample|\.dist|\.md|\.lock|package-lock\.json|composer\.lock|yarn\.lock|/tests?/|/fixtures?/|/__tests__/|\.min\.js|\.svg|\.map)$")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "secret-scan: " + reason,
    }}))
    sys.exit(0)


def git(args, cwd):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=15)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not re.search(r"(^|[;&|]\s*)git\s+(-c\s+\S+\s+)*(-C\s+(\S+)\s+)?commit\b", cmd):
        return
    if cmd.lstrip().startswith("CLAUDE_ALLOW_SECRETS=1"):
        return
    cwd = data.get("cwd") or os.getcwd()
    m = re.search(r"git\s+(?:-c\s+\S+\s+)*-C\s+(\S+)\s+commit", cmd)
    if m:
        cwd = os.path.expanduser(m.group(1).strip("'\""))
    # commit -a stages tracked changes at commit time: scan working tree of tracked files too
    scan_all = bool(re.search(r"commit\b[^|;&]*\s(-a|--all|-am|-a\s)", cmd))
    if shutil.which("gitleaks"):
        try:
            r = subprocess.run(["gitleaks", "protect", "--staged", "--no-banner", "--redact", "-v"] if not scan_all
                               else ["gitleaks", "protect", "--no-banner", "--redact", "-v"],
                               cwd=cwd, capture_output=True, text=True, timeout=40)
            if r.returncode != 0:
                tail = "\n".join((r.stdout or r.stderr).strip().splitlines()[-8:])
                deny("gitleaks found secrets in the commit:\n" + tail)
            return
        except Exception:
            pass  # fall back to regex
    names = git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd).split()
    if scan_all:
        names += git(["diff", "--name-only", "--diff-filter=ACMR"], cwd).split()
    key_hits = [n for n in dict.fromkeys(names) if KEY_FILES.search(n) and not n.endswith((".example", ".sample", ".dist"))]
    if key_hits:
        deny("secret-bearing file(s) staged: " + ", ".join(key_hits[:5]) + " — add to .gitignore, commit an .example instead")
    diff = git(["diff", "--cached", "-U0", "--no-color"], cwd)
    if scan_all:
        diff += git(["diff", "-U0", "--no-color"], cwd)
    findings = []
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if SKIP_VALUE_SCAN.search(current):
            continue
        for pat, label in VALUE_PATTERNS:
            mm = re.search(pat, line)
            if mm:
                val = mm.group(0)
                masked = val[:6] + "…" + val[-3:] if len(val) > 12 else "***"
                findings.append(f"{current}: {label} ({masked})")
                break
        if len(findings) >= 8:
            break
    if findings:
        deny("possible secrets in added lines:\n  " + "\n  ".join(findings)
             + "\nMove them to env/secret manager; if this is a false positive prefix the command with CLAUDE_ALLOW_SECRETS=1")


if __name__ == "__main__":
    main()
