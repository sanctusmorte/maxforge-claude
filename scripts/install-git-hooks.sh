#!/usr/bin/env bash
# Install a local pre-push hook that runs the leak check (private patterns included) before any push.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
hooks="$(git rev-parse --git-path hooks)"
mkdir -p "$hooks"
cat > "$hooks/pre-push" <<'HOOK'
#!/usr/bin/env bash
root="$(git rev-parse --show-toplevel)"
exec python3 "$root/scripts/leak-check.py" "$root"
HOOK
chmod +x "$hooks/pre-push"
echo "pre-push leak-check installed in $hooks"
