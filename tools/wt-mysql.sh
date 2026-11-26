#!/usr/bin/env bash
# wt-mysql.sh — own MySQL per worktree (owner 2026-11-23: «зачем на одной все гонять»).
# One shared host mysqld for ~10 parallel sessions = minutes-long schema loads, deadlocks, sessions wiping each
# other's e2e database. Each worktree gets a rootless-docker mysql:8.0 container, datadir on tmpfs (RAM, no fsync),
# published on a random 127.0.0.1 port; the worktree's untracked .env.testing/.env.e2e are pointed at it.
#
# Usage: wt-mysql.sh up <worktree> [db ...]   start/reuse, create DBs, patch env files, print env lines
#        wt-mysql.sh down <worktree>          remove the container (data is in RAM — gone)
#        wt-mysql.sh ls                       containers + their worktrees
#        wt-mysql.sh prune                    remove containers whose worktree dir no longer exists
# Env: WT_MYSQL_IMAGE (mysql:8.0), WT_MYSQL_TMPFS (6g), WT_MYSQL_POOL (1G).
set -euo pipefail
IMAGE=${WT_MYSQL_IMAGE:-mysql:8.0}; TMPFS=${WT_MYSQL_TMPFS:-6g}; POOL=${WT_MYSQL_POOL:-1G}
cmd=${1:-}; shift || true

cname() { echo "wtdb-$(basename "$1" | tr -c 'A-Za-z0-9_.-' '-' | sed 's/-*$//' | cut -c1-60)"; }
envval() { { grep -E "^$2=" "$1" 2>/dev/null || true; } | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }  # missing file/key → "" (pipefail+set -e used to kill `up` when .env.testing is absent, 2026-11-24)
setenv() { # file key value — replace or append
  if grep -qE "^$2=" "$1"; then sed -i -E "s|^$2=.*|$2=$3|" "$1"; else printf '%s=%s\n' "$2" "$3" >> "$1"; fi; }

case "$cmd" in
up)
  WT=$(cd "${1:?worktree}" && pwd); shift
  NAME=$(cname "$WT")
  PW=$(envval "$WT/.env.testing" DB_PASSWORD); [ -n "$PW" ] || PW=$(envval "$WT/.env" DB_PASSWORD)
  if ! docker container inspect "$NAME" >/dev/null 2>&1; then
    if [ -n "$PW" ]; then AUTH=(-e "MYSQL_ROOT_PASSWORD=$PW"); else AUTH=(-e MYSQL_ALLOW_EMPTY_PASSWORD=yes); fi
    docker run -d --name "$NAME" --label "wtdb.worktree=$WT" "${AUTH[@]}" -e MYSQL_ROOT_HOST=% \
      --tmpfs "/var/lib/mysql:rw,size=$TMPFS" -p 127.0.0.1::3306 "$IMAGE" \
      --skip-log-bin --innodb-flush-log-at-trx-commit=0 --innodb-doublewrite=0 --sync-binlog=0 \
      --innodb-buffer-pool-size="$POOL" --max-connections=500 --skip-name-resolve \
      --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci >/dev/null
  elif [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" != true ]; then
    docker start "$NAME" >/dev/null   # tmpfs is empty after a stop → entrypoint re-initialises
  fi
  PORT=$(docker port "$NAME" 3306/tcp | head -1 | sed 's/.*://')
  for i in $(seq 1 90); do
    docker exec -e MYSQL_PWD="$PW" "$NAME" mysql -uroot -h127.0.0.1 -e 'SELECT 1' >/dev/null 2>&1 && break
    [ "$i" = 90 ] && { echo "wt-mysql: $NAME not ready after 90 s" >&2; docker logs --tail 20 "$NAME" >&2; exit 1; }
    sleep 1
  done
  DBS=("$@")
  for f in .env.testing .env.e2e; do [ -f "$WT/$f" ] && DBS+=("$(envval "$WT/$f" DB_DATABASE)"); done
  [ -f "$WT/phpunit.xml" ] && DBS+=($(grep -oE 'name="DB_DATABASE" value="[^"]+"' "$WT/phpunit.xml" | sed 's/.*value="//;s/"$//'))
  for db in $(printf '%s\n' "${DBS[@]}" | grep -v '^$' | sort -u); do
    docker exec -e MYSQL_PWD="$PW" "$NAME" mysql -uroot -h127.0.0.1 \
      -e "CREATE DATABASE IF NOT EXISTS \`$db\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  done
  for f in .env.testing .env.e2e; do   # untracked per-worktree copies (wt-new.sh) — never the main checkout's
    [ -f "$WT/$f" ] || continue
    git -C "$WT" ls-files --error-unmatch "$f" >/dev/null 2>&1 && { echo "wt-mysql: $f is tracked, not patched" >&2; continue; }
    setenv "$WT/$f" DB_HOST 127.0.0.1; setenv "$WT/$f" DB_PORT "$PORT"
  done
  # e2e web port: stable per worktree, away from the shared 8001 (playwright reuses a server already on the port)
  E2E_PORT=$(( 8100 + $(echo -n "$WT" | cksum | cut -d' ' -f1) % 800 ))
  [ -f "$WT/.env.e2e" ] && sed -i -E "s|^(APP_URL=http://127\.0\.0\.1):[0-9]+|\1:$E2E_PORT|" "$WT/.env.e2e"
  echo "mysql=$NAME 127.0.0.1:$PORT dbs=$(printf '%s ' "${DBS[@]}" | xargs -n1 | sort -u | xargs)"
  echo "env=DB_HOST=127.0.0.1 DB_PORT=$PORT"
  echo "e2e=cd $WT && DB_HOST=127.0.0.1 DB_PORT=$PORT E2E_PORT=$E2E_PORT npx playwright test <spec>"
  ;;
down) NAME=$(cname "$(cd "${1:?worktree}" 2>/dev/null && pwd || echo "$1")"); docker rm -f "$NAME" >/dev/null && echo "removed $NAME" ;;
ls) docker ps -a --filter label=wtdb.worktree --format '{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Label "wtdb.worktree"}}' ;;
prune)
  docker ps -a --filter label=wtdb.worktree --format '{{.Names}} {{.Label "wtdb.worktree"}}' | while read -r n wt; do
    [ -d "$wt" ] || { docker rm -f "$n" >/dev/null && echo "pruned $n ($wt gone)"; }
  done ;;
*) sed -n '2,12p' "$0"; exit 2 ;;
esac
