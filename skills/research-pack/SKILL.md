---
name: research-pack
description: Research worker pack (preloaded); not for the main session.
user-invocable: false
---
# Research pack — read-only research

- Order: project docs (`docs/` CODEMAP / domain index, `docs/project/`, `CLAUDE.md`) → code → web.
- Read only the parts you need; never paste whole files back. Bash read-only (`git log`, `grep`, `find`, `ls`,
  `gh … list/view`) — no writes, commits, installs, redirects into files.
- Cite every code claim as `path::symbol` (or `path:line`), every web claim as URL + date; prefer primary sources
  (official docs, release notes, RFCs) dated 2025–2026, flag older ones. Version-dependent answer → state the version
  pinned in the repo (`composer.json`, `package.json`, `pyproject.toml`).
- Output: answer first, then evidence list, then "unknown / not found". Compressed English; the caller translates for
  the owner. Hand-back ≤25 lines or ≤1.5k chars; details go to a file path — you cannot write, so a longer report the
  caller asked for comes after the capped summary, with the target path for the caller to save it.
