#!/usr/bin/env python3
"""Webhook triage for WTD -> Shared Goals PRD update decisions.

Reads a GitHub webhook payload from stdin and returns a strict JSON decision.
"""
from __future__ import annotations

import json
import sys
from typing import Any

TARGET_REPO = "bongiozzo/whattodo"
TARGET_REF = "refs/heads/master"
MEMORY_TAGS = ["project:sg", "mvp", "wtd", "prd"]

RELEVANT_PREFIXES = (
    "text/",
)
RELEVANT_FILES = {
    "mkdocs.yml",
    "README.md",
}

NOISE_PREFIXES = (
    "build/",
    "public/",
    ".github/",
)

PRD_TARGETS = [
    "README.md",
    "BACKLOG.md",
    "HISTORY.md",
    "RESEARCH.md",
    "ACCEPTANCE.md",
    "IMPLEMENTATION.md",
]


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _collect_changed_paths(commits: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for commit in commits:
        for key in ("added", "modified", "removed"):
            for raw in _safe_list(commit.get(key)):
                path = _safe_str(raw).strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                paths.append(path)
    return sorted(paths)


def _is_noise(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in NOISE_PREFIXES)


def _is_relevant(path: str) -> bool:
    if path in RELEVANT_FILES:
        return True
    return any(path.startswith(prefix) for prefix in RELEVANT_PREFIXES)


def _decision_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    repo = _safe_str(payload.get("repository", {}).get("full_name"))
    ref = _safe_str(payload.get("ref"))
    commits = _safe_list(payload.get("commits"))

    if repo != TARGET_REPO:
        return {
            "ignored": True,
            "ignore_reason": f"repo_mismatch:{repo}",
        }

    if ref and ref != TARGET_REF:
        return {
            "ignored": True,
            "ignore_reason": f"branch_mismatch:{ref}",
        }

    changed_paths = _collect_changed_paths([c for c in commits if isinstance(c, dict)])
    relevant_paths = [p for p in changed_paths if _is_relevant(p)]
    material_paths = [p for p in changed_paths if not _is_noise(p)]

    should_update = bool(relevant_paths)
    decision = "UPDATE_PRD" if should_update else "NO_UPDATE"

    if should_update:
        reason = "content_updates_detected"
    elif material_paths:
        reason = "changes_not_mapped_to_prd_scope"
    else:
        reason = "only_noise_paths_changed"

    before = _safe_str(payload.get("before"))
    after = _safe_str(payload.get("after"))
    commit_range = ""
    if before and after:
        commit_range = f"{before[:7]}..{after[:7]}"

    report_lines = [
        f"SG PRD decision: {decision}",
        f"Repo: {repo}",
        f"Branch: {ref or TARGET_REF}",
        f"Commits: {len(commits)}",
    ]
    if commit_range:
        report_lines.append(f"Range: {commit_range}")
    report_lines.append(f"Reason: {reason}")
    if should_update:
        report_lines.append(
            "How to realize: the push touched core content paths, so PRD upkeep is required."
        )
        report_lines.append("PRD to update: " + ", ".join(PRD_TARGETS))
    else:
        report_lines.append(
            "How to realize: the push did not touch PRD-scoped content paths, so defer."
        )
    if relevant_paths:
        report_lines.append("Relevant paths: " + ", ".join(relevant_paths[:8]))
    elif material_paths:
        report_lines.append("Changed paths: " + ", ".join(material_paths[:8]))

    memory_query = (
        "Shared Goals MVP PRD maintenance context for whattodo updates: "
        f"decision={decision}, reason={reason}, paths={','.join(changed_paths[:12])}"
    )
    reflect_query = (
        "Given this whattodo push evidence, should Shared Goals PRD be updated now, "
        "or deferred as no-update? Return concise rationale and target PRD files."
    )

    return {
        "ignored": False,
        "should_update_prd": should_update,
        "decision_hint": decision,
        "decision": decision,
        "reason": reason,
        "commit_count": len(commits),
        "commit_range": commit_range,
        "changed_paths": changed_paths,
        "relevant_paths": relevant_paths,
        "suggested_targets": PRD_TARGETS if should_update else [],
        "memory_tags": MEMORY_TAGS,
        "memory_query": memory_query,
        "reflect_query": reflect_query,
        "requires_memory_review": True,
        "report": "\n".join(report_lines),
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
    except OSError:
        print("[SILENT]")
        return

    if not raw.strip():
        print("[SILENT]")
        return

    try:
        payload = json.loads(raw)
    except ValueError:
        print("[SILENT]")
        return

    if not isinstance(payload, dict):
        print("[SILENT]")
        return

    out = _decision_for_payload(payload)
    if out.get("ignored"):
        print("[SILENT]")
        return

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
