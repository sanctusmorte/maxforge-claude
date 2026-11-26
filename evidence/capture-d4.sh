#!/usr/bin/env bash
# Run from anywhere: bash evidence/capture-d4.sh (rewrites d4-design-gate-fixture-dead-button.txt).
# Throwaway fixture for the d4 capture: same shape as d1-d3 (branch feat touches src/Dashboard.vue,
# artifacts/ui-qa/dashboard/scorecard.md Verdict: PASS, clean geometry report) + the self-test fixture's dead-clicks report.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
: "${TMPDIR:=/tmp}"
FH=$(mktemp -d "$TMPDIR/d4home.XXXX")
export HOME=$FH CLAUDE_HARNESS_DIR=$REPO CLAUDE_PLUGIN_DATA=$FH/plugin-data
mkdir -p "$CLAUDE_PLUGIN_DATA"
git config --global user.email demo@example.com; git config --global user.name demo; git config --global init.defaultBranch dev
git init -q "$FH/ui-app"; cd "$FH/ui-app"
echo "# ui-app" > README.md; git add README.md; git commit -qm init
git update-ref refs/remotes/origin/dev HEAD  # remote-tracking base ref; no remote needed
git checkout -qb feat; mkdir -p src; echo "<template><button>Export</button></template>" > src/Dashboard.vue
git add src; git commit -qm "feat: dashboard"
D=artifacts/ui-qa/dashboard; mkdir -p $D/dead-clicks $D/geometry
printf '# Scorecard dashboard\n\nVerdict: PASS\n' > $D/scorecard.md
cp "$REPO/evidence/ui/dead-clicks-fixture/report.json" $D/dead-clicks/report.json
printf '{"summary":{"errors":0,"warnings":0},"pages":[]}\n' > $D/geometry/report.json
IN=$(printf '{\n  "hook_event_name": "PreToolUse",\n  "tool_name": "Bash",\n  "session_id": "demo-session",\n  "cwd": "%s",\n  "tool_input": {\n    "command": "gh pr create --base dev --title '"'"'feat: dashboard'"'"' --body '"'"'Adds the dashboard'"'"'"\n  }\n}' "$FH/ui-app")
set +e
OUT=$(printf '%s' "$IN" | python3 "$REPO/hooks/guard-bash.py" 2>"$FH/err"); RC=$?
set -e
red() { sed -e "s#$FH#~#g" -e "s#$REPO#<repo>#g"; }
{
echo "# PASS scorecard while the self-test fixture's controls do nothing or throw (NO_EFFECT, ERROR)"
echo "hook: hooks/guard-bash.py"
echo "event: PreToolUse"
echo "matcher: Bash"
echo "captured: $(date +%F), from this tree, throwaway HOME / CLAUDE_PLUGIN_DATA"
echo 'redaction: local absolute paths replaced by `~` (fixture home) and `<repo>` (this checkout); nothing else edited'
echo "note: same fixture as d1-d3 (branch feat touches src/Dashboard.vue; artifacts/ui-qa/dashboard/scorecard.md says Verdict: PASS; clean geometry/report.json); dead-clicks/report.json = evidence/ui/dead-clicks-fixture/report.json (6 controls: NO_EFFECT «Dead button», ERROR «Throwing button»); reproduce: bash evidence/capture-d4.sh"
echo "--- stdin (JSON) ---"; printf '%s\n' "$IN" | red
echo "--- stdout ---"; printf '%s\n' "$OUT" | red
echo "--- deny/block text (decoded from stdout) ---"
printf '%s' "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['hookSpecificOutput']['permissionDecisionReason'])" | red
echo "--- stderr ---"; red < "$FH/err"; echo
echo "--- exit code ---"; echo $RC
} > "$REPO/evidence/d4-design-gate-fixture-dead-button.txt"
rm -rf "$FH"
