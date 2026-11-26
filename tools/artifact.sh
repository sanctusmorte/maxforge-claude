#!/usr/bin/env bash
# Toggle the heavy built-in tools (Artifact ≈18.7k, Workflow ≈2.4k, ScheduleWakeup ≈2.1k tokens) in
# ~/.claude/settings.json permissions.deny. Takes effect for the NEXT session.
#   artifact.sh on      → remove from deny (mockups / shareable pages / workflows)
#   artifact.sh off     → add to deny (default, saves ≈23k tokens per session start)
#   artifact.sh status  → show current state
set -euo pipefail
# USER config (permissions.deny), deliberately home-based, not plugin-relative
S="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
TOOLS='("Artifact","Workflow","ScheduleWakeup")'
case "${1:-status}" in
  on)  python3 -c "import json;p='$S';s=json.load(open(p));d=s['permissions']['deny'];s['permissions']['deny']=[t for t in d if t not in $TOOLS];json.dump(s,open(p,'w'),indent=2,ensure_ascii=False);open(p,'a').write('\n');print('Artifact/Workflow/ScheduleWakeup: ON for the next session')" ;;
  off) python3 -c "import json;p='$S';s=json.load(open(p));d=s['permissions']['deny'];[d.append(t) for t in $TOOLS if t not in d];json.dump(s,open(p,'w'),indent=2,ensure_ascii=False);open(p,'a').write('\n');print('Artifact/Workflow/ScheduleWakeup: OFF (denied) for the next session')" ;;
  status) python3 -c "import json;d=json.load(open('$S'))['permissions']['deny'];print('OFF (denied)' if 'Artifact' in d else 'ON')" ;;
  *) echo "usage: artifact.sh on|off|status"; exit 1 ;;
esac
