#!/usr/bin/env bash
# wt-new.sh — bootstrap an isolated task worktree: branch from origin/<base>, env, deps, own test DB.
# Usage: wt-new.sh <repo-path> <task-slug> [--base dev|master|main] [--no-deps] [--no-db]
# Records the creating Claude session (CLAUDE_CODE_SESSION_ID) in <git-dir>/claude-owner for hooks/stop-guard.py.
# Prints the worktree path, branch, and the env lines to use (DB_DATABASE=…) — capture them.
set -euo pipefail
REPO=${1:?repo path}; SLUG=${2:?task slug}; shift 2
BASE=""; DEPS=1; DB=1
while [ $# -gt 0 ]; do case "$1" in
  --base) BASE=$2; shift 2;; --no-deps) DEPS=0; shift;; --no-db) DB=0; shift;; *) echo "unknown arg $1" >&2; exit 2;; esac; done
REPO=$(cd "$REPO" && git rev-parse --show-toplevel)
NAME=$(basename "$REPO")
git -C "$REPO" fetch -q --prune origin
if [ -z "$BASE" ]; then
  if git -C "$REPO" rev-parse --verify -q origin/dev >/dev/null; then BASE=dev
  else BASE=$(git -C "$REPO" symbolic-ref -q --short refs/remotes/origin/HEAD | sed 's#origin/##'); BASE=${BASE:-master}; fi
fi
SAFE=$(echo "$SLUG" | tr -c 'A-Za-z0-9._-' '-' | sed 's/-*$//')
BRANCH="${SAFE}"
# a slug that already ends in a date keeps it (no task/x-2026-09-26-2026-09-26)
if [[ "$BRANCH" != */* ]]; then
  if [[ "$SAFE" =~ -[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then BRANCH="task/${SAFE}"; else BRANCH="task/${SAFE}-$(date +%Y-%m-%d)"; fi
fi
WT="${WORKTREES_DIR:-$HOME/worktrees}/wt-${NAME}-${SAFE}"   # persistent (not /tmp): survives reboots
mkdir -p "$(dirname "$WT")"
if [ -e "$WT" ]; then echo "worktree exists: $WT" >&2; exit 3; fi
if git -C "$REPO" show-ref --verify -q "refs/heads/$BRANCH"; then
  git -C "$REPO" worktree add -q "$WT" "$BRANCH"
else
  git -C "$REPO" worktree add -q -b "$BRANCH" "$WT" "origin/$BASE"
fi
echo "worktree=$WT"; echo "branch=$BRANCH"; echo "base=origin/$BASE"
# Owner marker for hooks/stop-guard.py: only the creating session is asked to finish this worktree. It lives in the
# worktree's git dir (never in `git status`) and goes away with `git worktree remove`. Subagents share the parent's id.
OWNER=${CLAUDE_CODE_SESSION_ID:-${CLAUDE_SESSION_ID:-}}
if [ -n "$OWNER" ]; then
  printf '%s\n' "$OWNER" > "$(git -C "$WT" rev-parse --absolute-git-dir)/claude-owner"; echo "owner=$OWNER"
else echo "owner=none (no CLAUDE_CODE_SESSION_ID: stop-guard will not track this worktree)" >&2; fi

# --- env files ------------------------------------------------------------------------------
for f in .env .env.testing .env.e2e; do
  if [ -f "$REPO/$f" ] && [ ! -f "$WT/$f" ]; then cp "$REPO/$f" "$WT/$f"; fi
done
# gitignored data dirs → symlink to the main checkout (read-only sharing; never copy big data)
for d in storage/app research/data_cache ft_userdata/user_data/data data; do
  if [ -d "$REPO/$d" ] && [ ! -e "$WT/$d" ] && git -C "$REPO" check-ignore -q "$d" 2>/dev/null; then
    mkdir -p "$(dirname "$WT/$d")"; ln -s "$REPO/$d" "$WT/$d"; echo "linked=$d"; fi
done

# --- dependencies (shared caches, fast) ---------------------------------------------------------
if [ $DEPS -eq 1 ]; then
  if [ -f "$WT/composer.json" ]; then
    # NEVER symlink vendor/: composer's PSR-4 autoload maps app/ by absolute path → worktree code would
    # resolve to the main checkout's classes. Copy (reflink when the FS supports it) + regenerate autoload.
    if [ -d "$REPO/vendor" ] && cmp -s "$REPO/composer.lock" "$WT/composer.lock"; then
      cp -a --reflink=auto "$REPO/vendor" "$WT/vendor"
      # The main checkout's vendor/ can lag behind its own lock (e.g. a package added on dev) → package:discover fails.
      if (cd "$WT" && composer dump-autoload -o -q); then echo "vendor=copied(main)+dump-autoload"
      else echo "vendor: copied vendor is stale, running composer install" >&2
        (cd "$WT" && composer install -q --no-interaction --prefer-dist) && echo "vendor=copied(main)+installed"; fi
    else (cd "$WT" && composer install -q --no-interaction --prefer-dist 2>&1 | tail -1); echo "vendor=installed"; fi
  fi
  if [ -f "$WT/package.json" ]; then
    # Copy, never symlink: `npm install <pkg>` inside a symlinked node_modules would mutate the main checkout.
    if [ -d "$REPO/node_modules" ] && cmp -s "$REPO/package-lock.json" "$WT/package-lock.json" 2>/dev/null; then cp -a --reflink=auto "$REPO/node_modules" "$WT/node_modules"; echo "node_modules=copied(main)";
    else (cd "$WT" && npm ci --silent 2>&1 | tail -1); echo "node_modules=installed"; fi
  fi
  if [ -f "$WT/pyproject.toml" ] || [ -f "$WT/requirements.txt" ]; then
    if [ -d "$REPO/.venv" ]; then ln -s "$REPO/.venv" "$WT/.venv"; echo "venv=symlink(main)"; fi
  fi
fi

# --- per-task test database (Laravel) ---------------------------------------------------------
if [ $DB -eq 1 ] && [ -f "$WT/artisan" ]; then
  DBNAME="${NAME//-/_}_testing_${SAFE//-/_}"; DBNAME=${DBNAME:0:60}
  CONN=$(grep -E '^DB_CONNECTION=' "$WT/.env" 2>/dev/null | cut -d= -f2); CONN=${CONN:-mysql}
  if [ "$CONN" = "mysql" ] && command -v docker >/dev/null && [ "${WT_MYSQL_OFF:-0}" != 1 ] \
     && "$(dirname "$0")/wt-mysql.sh" up "$WT" "$DBNAME"; then
    echo "testdb=$DBNAME (own mysql container; .env.testing/.env.e2e point at it; pass DB_HOST/DB_PORT above to ad-hoc commands)"
  elif [ "$CONN" = "mysql" ] && command -v mysql >/dev/null; then
    echo "wt-mysql failed or off — falling back to the SHARED host mysql" >&2
    mysql -e "CREATE DATABASE IF NOT EXISTS \`$DBNAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null && echo "testdb=$DBNAME (mysql)"
  elif [ "$CONN" = "pgsql" ] && command -v psql >/dev/null; then
    PORT=$(grep -E '^DB_PORT=' "$WT/.env" | cut -d= -f2); PORT=${PORT:-5432}
    psql -h 127.0.0.1 -p "$PORT" -tc "SELECT 1 FROM pg_database WHERE datname='$DBNAME'" postgres 2>/dev/null | grep -q 1 || psql -h 127.0.0.1 -p "$PORT" -c "CREATE DATABASE \"$DBNAME\"" postgres >/dev/null 2>&1 && echo "testdb=$DBNAME (pgsql)"
  fi
  echo "env=DB_DATABASE=$DBNAME"
  echo "migrate=cd $WT && DB_DATABASE=$DBNAME php artisan migrate --force --no-interaction"
  echo "test=cd $WT && DB_DATABASE=$DBNAME php artisan test --filter=<Class>"
fi
echo "cleanup=git -C $REPO worktree remove --force $WT && git -C $REPO branch -d $BRANCH"
