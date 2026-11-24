# AGENTS.md — shared-goals/skill

This repository is public: every committed file is published the moment
someone pushes. Agents write here regularly, so read this before writing.

## What must never enter tracked files

- **Personal names and private agreements.** The author is "автор" /
  "the author" — never a person's name. Personal workflow deals (who edits
  what, push approvals) are phrased generically.
- **Private infrastructure:** LAN hostnames, internal IPs, ports of private
  services, absolute machine paths (`/mnt/...`, `/Users/...`), checkout
  layouts.
- **Deployment specifics of a private instance:** systemd units, sudo
  procedures, live DB paths, deploy sequences.
- **Secret values.** Env-var names are fine; values never.

## Where local specifics belong

`references/` inside a skill directory is gitignored by convention — hosts,
ports, paths and personal workflow notes live there, not in tracked files.
Already-public resources (the reference WTD repo, published sites, public
APIs) may be referenced — phrased as examples, e.g. "reference deployment".

## Git policy

- `git pull` — always allowed.
- Commit only files you authored. Before every commit run `git status` and
  leave parallel sessions' uncommitted changes alone.
- The agent never pushes; pushing is the human's step.
- `.githooks/pre-push` audits outgoing commits for the patterns above.
  Enable once per clone: `git config core.hooksPath .githooks`.
  Private extra patterns (real names), if ever needed, go to gitignored
  `.githooks/local-patterns.txt` — never into the repo.

## Writing style

- Generic phrasing over UI snapshots: no weekly leaderboards, default
  filters or model counts hardcoded; give the reader a way to reproduce
  the claim instead.
- Public skills speak of "the author"; author-facing reports are
  «Отчёт автору».
