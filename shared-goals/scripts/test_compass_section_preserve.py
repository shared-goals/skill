#!/usr/bin/env python3
"""Tests for Compass.md section preservation and quick-task planning commits.

Importable standalone: ``uv run pytest test_compass_section_preserve.py -q``
must be green on its own, without the repo-level conftest fixtures.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_script(filename: str):
    """Load a dash-named script module by file path (same trick as test_daily_compass)."""
    path = SCRIPTS_DIR / filename
    name = path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sg = _load_script("shared_goals_platform.py")
compass_update = _load_script("compass-update.py")


PAYLOAD = {
    "dimensions": [
        {
            "dimension": "mind",
            "last_fed_at": "2026-11-20T00:00:00+00:00",
            "goals": [
                {
                    "goal_tag": "#sg-homelab",
                    "goal_title": "Homelab",
                    "next_step_text": "Platform step one\nPlatform step two",
                }
            ],
        }
    ]
}

# Representative Compass.md: preamble, generated sections (stale content), and
# three user-owned sections around/below them.
EXISTING_FILE = "\n".join(
    [
        "# My Compass",
        "",
        "Preamble line one.",
        "Preamble line two.",
        "",
        "## Logos",
        "",
        "- [ ] Stale logo item",
        "",
        "## Journal",
        "",
        "Today I learned that things are preserved.",
        "",
        "## Shared Goals",
        "",
        "### Mind (3d)",
        "",
        "- **Old Goal #sg-oldgoal hunger:9d**",
        "  - [x] Old completed line #sg-oldgoal",
        "",
        "## Quick Tasks",
        "",
        "- [ ] Existing quick task",
        "- [ ] Another existing quick task",
        "",
        "## Logos Archive",
        "",
        "Old logos, kept verbatim.",
        "",
    ]
)


# ---------------------------------------------------------------------------
# Task 1 — section-aware update_compass_markdown
# ---------------------------------------------------------------------------


def test_user_section_survives_byte_identical_while_generated_sections_are_replaced() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(EXISTING_FILE, encoding="utf-8")

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        user_section = "## Quick Tasks\n\n- [ ] Existing quick task\n- [ ] Another existing quick task\n"
        assert user_section in text
        # generated sections really replaced
        assert "- [ ] Stale logo item" not in text
        assert "- **Old Goal #sg-oldgoal hunger:9d**" not in text
        assert "- [ ] Fresh logo item" in text
        assert "- **Homelab #sg-homelab hunger:" in text


def test_preamble_before_first_heading_survives() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(EXISTING_FILE, encoding="utf-8")

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        assert text.startswith("# My Compass\n\nPreamble line one.\nPreamble line two.\n")
        assert text.index("# My Compass") < text.index("## Logos")


def test_several_user_sections_keep_relative_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(EXISTING_FILE, encoding="utf-8")

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        assert text.index("## Journal") < text.index("## Quick Tasks")
        assert text.index("## Quick Tasks") < text.index("## Logos Archive")
        assert "Today I learned that things are preserved." in text
        assert "Old logos, kept verbatim." in text


def test_missing_generated_headings_are_inserted_in_canonical_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(
            "\n".join(
                [
                    "# Preamble",
                    "",
                    "## Journal",
                    "",
                    "Journal body.",
                    "",
                    "## Quick Tasks",
                    "",
                    "- [ ] Quick one",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        # insertion order: preamble, ## Logos, ## Shared Goals, then user sections as-is
        assert text.index("# Preamble") < text.index("## Logos")
        assert text.index("## Logos") < text.index("## Shared Goals")
        assert text.index("## Shared Goals") < text.index("## Journal")
        assert text.index("## Journal") < text.index("## Quick Tasks")
        assert "Journal body." in text
        assert "- [ ] Quick one" in text


def test_missing_shared_goals_heading_only_is_inserted_after_logos() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text("## Logos\n\n- [ ] Keep me logo\n", encoding="utf-8")

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        # Both generated headings are re-emitted, with Logos first.
        assert text.count("## Logos") == 1
        assert "## Shared Goals" in text
        assert text.index("## Logos") < text.index("## Shared Goals")
        # the old Logos body is gone (replaced); this input holds no user
        # section besides Logos, so only the generated sections remain
        assert "- [ ] Keep me logo" not in text
        assert "## Quick Tasks" not in text
        assert text.count("## Shared Goals") == 1


def test_absent_file_bootstraps_with_quick_tasks_seed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        assert not path.exists()

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        assert "## Logos" in text
        assert "## Shared Goals" in text
        assert "## Quick Tasks" in text
        assert text.index("## Logos") < text.index("## Shared Goals")
        assert text.index("## Shared Goals") < text.index("## Quick Tasks")
        # seeded empty section: no checkbox items under it
        quick_tail = text.split("## Quick Tasks", 1)[1]
        assert "- [ ]" not in quick_tail


def test_update_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(EXISTING_FILE, encoding="utf-8")

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        first = path.read_text(encoding="utf-8")
        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        second = path.read_text(encoding="utf-8")

        assert first == second


def test_resembling_user_heading_is_preserved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(EXISTING_FILE, encoding="utf-8")

        sg.update_compass_markdown(PAYLOAD, path, logos_text="- [ ] Fresh logo item")
        text = path.read_text(encoding="utf-8")

        assert "## Logos Archive" in text
        assert "Old logos, kept verbatim." in text


# ---------------------------------------------------------------------------
# Task 2 — parse: incomplete-only goals
# ---------------------------------------------------------------------------


# Platform payload matching SHARED_GOALS_COMPLETED_CLEAN exactly: every file line
# of every goal is a platform step, so detection must report nothing.
COMPLETED_CLEAN_PAYLOAD = {
    "dimensions": [
        {
            "dimension": "mind",
            "last_fed_at": "2026-11-20T00:00:00+00:00",
            "goals": [
                {
                    "goal_tag": "#sg-homelab",
                    "goal_title": "Homelab",
                    "next_step_text": "Platform step one\nPlatform step two",
                },
                {
                    "goal_tag": "#sg-finance",
                    "goal_title": "Finance",
                    "next_step_text": "Platform budget review",
                },
                {
                    "goal_tag": "#sg-music",
                    "goal_title": "Music",
                    "next_step_text": "Organize library",
                },
            ],
        }
    ]
}


SHARED_GOALS_WITH_USER_LINE = "\n".join(
    [
        "## Shared Goals",
        "",
        "### Mind (2d)",
        "",
        "- **Homelab #sg-homelab hunger:2d**",
        "  - [x] Platform step one #sg-homelab",
        "  - [ ] Platform step two #sg-homelab",
        "  - [ ] My extra line #sg-homelab",
        "",
        "### Faith (1d)",
        "",
        "- **Finance #sg-finance hunger:1d**",
        "  - [ ] Plan budget #sg-finance",
        "",
        "### Will (never)",
        "",
        "- **Music #sg-music hunger:0d**",
        "  - [ ] Organize library #sg-music",
        "",
        "### Feeling (never)",
        "",
        "- **Empty #sg-empty hunger:0d**",
        "",
    ]
)

SHARED_GOALS_COMPLETED_CLEAN = "\n".join(
    [
        "## Shared Goals",
        "",
        "### Mind (2d)",
        "",
        "- Homelab #sg-homelab hunger:2d",
        "  - [x] Platform step one #sg-homelab",
        "  - [ ] Platform step two #sg-homelab",
        "",
        "### Faith (1d)",
        "",
        "- Finance #sg-finance hunger:1d",
        "  - [ ] Platform budget review #sg-finance",
        "",
        "### Will (never)",
        "",
        "- Music #sg-music hunger:0d",
        "  - [ ] Organize library #sg-music",
        "",
        "### Feeling (never)",
        "",
        "- Empty #sg-empty hunger:0d",
        "",
    ]
)



def test_parse_returns_incomplete_only_goals_and_drops_empty_goals() -> None:
    goals = sg.parse_completed_goals_from_compass_text(SHARED_GOALS_WITH_USER_LINE)
    by_id = {g["goal_id"]: g for g in goals}

    assert "sg-homelab" in by_id
    assert by_id["sg-homelab"]["completed"] == ["Platform step one"]
    assert by_id["sg-homelab"]["incomplete"] == ["Platform step two", "My extra line"]

    assert "sg-finance" in by_id
    assert by_id["sg-finance"]["completed"] == []
    assert by_id["sg-finance"]["incomplete"] == ["Plan budget"]

    # goal with neither completed nor incomplete items is not returned
    assert "sg-empty" not in by_id

    # output shape unchanged
    assert set(by_id["sg-finance"].keys()) == {"goal_tag", "goal_id", "goal_title", "completed", "incomplete"}


# ---------------------------------------------------------------------------
# Task 2 — detect_user_added_steps
# ---------------------------------------------------------------------------


def test_detect_user_added_steps_is_tag_and_order_insensitive() -> None:
    goals = sg.parse_completed_goals_from_compass_text(SHARED_GOALS_WITH_USER_LINE)
    added = sg.detect_user_added_steps(goals, PAYLOAD)

    # Only the genuinely foreign line is reported: the platform line is
    # recognized despite its appended tag, and goals absent from the payload
    # (finance/music) are not reported as user-added.
    assert added == {"sg-homelab": ["My extra line"]}


def test_detect_user_added_steps_empty_when_all_lines_are_platform_steps() -> None:
    goals = sg.parse_completed_goals_from_compass_text(SHARED_GOALS_WITH_USER_LINE)
    payload = {
        "dimensions": [
            {
                "dimension": "mind",
                "last_fed_at": "2026-11-20T00:00:00+00:00",
                "goals": [
                    {
                        "goal_tag": "#sg-homelab",
                        "goal_title": "Homelab",
                        "next_step_text": "Platform step two\nMy extra line\nPlatform step one",
                    }
                ],
            }
        ]
    }

    added = sg.detect_user_added_steps(goals, payload)

    assert added == {}


# ---------------------------------------------------------------------------
# Task 2 — move_lines_to_quick_tasks
# ---------------------------------------------------------------------------


def test_move_lines_appends_items_under_existing_quick_tasks_section() -> None:
    result = sg.move_lines_to_quick_tasks(EXISTING_FILE, ["My extra line"])

    assert "- [ ] My extra line" in result
    quick = result.split("## Quick Tasks", 1)[1].split("##", 1)[0]
    assert "- [ ] Existing quick task" in quick
    assert "- [ ] Another existing quick task" in quick
    assert "- [ ] My extra line" in quick
    assert quick.index("- [ ] Another existing quick task") < quick.index("- [ ] My extra line")
    # rest of the file untouched
    assert "Today I learned that things are preserved." in result


def test_move_lines_creates_section_at_end_of_file_when_absent() -> None:
    text = "# Preamble\n\n## Journal\n\nJournal body.\n"

    result = sg.move_lines_to_quick_tasks(text, ["Orphan one", "Orphan two"])

    assert result.index("## Journal") < result.index("## Quick Tasks")
    tail = result.split("## Quick Tasks", 1)[1]
    assert "- [ ] Orphan one" in tail
    assert "- [ ] Orphan two" in tail


def test_move_lines_with_empty_lines_leaves_text_unchanged() -> None:
    result = sg.move_lines_to_quick_tasks(EXISTING_FILE, [])
    assert result == EXISTING_FILE


# ---------------------------------------------------------------------------
# Task 2 — compass-update orchestration
# ---------------------------------------------------------------------------


class FakeConsole:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *args, **kwargs) -> None:
        self.lines.append(" ".join(str(a) for a in args))


def _payload_with_contract() -> dict:
    return {
        "dimensions": [
            {
                "dimension": "mind",
                "last_fed_at": "2026-11-20T00:00:00+00:00",
                "goals": [
                    {
                        "goal_tag": "#sg-finance",
                        "goal_title": "Finance",
                        "next_step_text": "Platform budget review",
                    }
                ],
            }
        ]
    }


def test_sync_prompts_and_creates_planning_commit_for_user_added_lines() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(
            "\n".join(
                [
                    "## Shared Goals",
                    "",
                    "### Mind (1d)",
                    "",
                    "- **Finance #sg-finance hunger:1d**",
                    "  - [ ] Platform budget review #sg-finance",
                    "  - [ ] Add quick backup #sg-finance",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        contracts = {"sg-finance": {"contract_id": "c-1"}}

        with mock.patch.object(compass_update, "fetch_active_contracts", return_value=contracts), mock.patch.object(
            compass_update, "create_commit"
        ) as create, mock.patch.object(compass_update, "_prompt_yes_no", return_value=True) as yesno, mock.patch.object(
            compass_update.sys.stdin, "isatty", lambda: True
        ):
            created = compass_update._sync_completed_tasks(FakeConsole(), path, _payload_with_contract())

        assert created == 1
        create.assert_called_once()
        args, kwargs = create.call_args
        assert args[0] == "c-1"
        assert kwargs["done"] is None
        assert kwargs["next_step"] == "Platform budget review\nAdd quick backup"
        assert kwargs["time_minutes"] is None
        assert kwargs["happy_moment"] is None
        assert kwargs["source_ref"] == sg.commit_source_ref("sg-finance", [], ["Platform budget review", "Add quick backup"])
        # exactly one prompt (the planning prompt): no minutes/happy prompts consumed
        assert yesno.call_count == 1
        assert "Add 1 line" in yesno.call_args_list[0][0][1]
        # Accepted planning commit: the line lives on the platform now, it must
        # NOT also be moved into ## Quick Tasks (duplication regression guard).
        final_text = path.read_text(encoding="utf-8")
        assert "## Quick Tasks" not in final_text


def test_sync_declined_lines_move_to_quick_tasks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(
            "\n".join(
                [
                    "## Shared Goals",
                    "",
                    "### Mind (1d)",
                    "",
                    "- **Finance #sg-finance hunger:1d**",
                    "  - [ ] Platform budget review #sg-finance",
                    "  - [ ] Add quick backup #sg-finance",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        contracts = {"sg-finance": {"contract_id": "c-1"}}
        console = FakeConsole()

        with mock.patch.object(compass_update, "fetch_active_contracts", return_value=contracts), mock.patch.object(
            compass_update, "create_commit"
        ) as create, mock.patch.object(compass_update, "_prompt_yes_no", return_value=False), mock.patch.object(
            compass_update.sys.stdin, "isatty", lambda: True
        ):
            created = compass_update._sync_completed_tasks(console, path, _payload_with_contract())

        assert created == 0
        create.assert_not_called()
        text = path.read_text(encoding="utf-8")
        assert "## Quick Tasks" in text
        quick = text.split("## Quick Tasks", 1)[1]
        # exactly ONE copy of the declined line in Quick Tasks (the move list is
        # pre-seeded — a second extend would duplicate it)
        assert quick.count("- [ ] Add quick backup") == 1
        assert any("Add quick backup" in line for line in console.lines)


def test_sync_non_tty_moves_lines_with_notice_and_no_prompts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(
            "\n".join(
                [
                    "## Shared Goals",
                    "",
                    "### Mind (1d)",
                    "",
                    "- **Finance #sg-finance hunger:1d**",
                    "  - [ ] Platform budget review #sg-finance",
                    "  - [ ] Add quick backup #sg-finance",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        contracts = {"sg-finance": {"contract_id": "c-1"}}
        console = FakeConsole()
        stdin_not_tty = types.SimpleNamespace(isatty=lambda: False)

        with mock.patch.object(compass_update, "fetch_active_contracts", return_value=contracts), mock.patch.object(
            compass_update, "create_commit"
        ) as create, mock.patch.object(compass_update, "_prompt_yes_no") as yesno, mock.patch.object(
            compass_update.sys, "stdin", stdin_not_tty
        ):
            created = compass_update._sync_completed_tasks(console, path, _payload_with_contract())

        assert created == 0
        create.assert_not_called()
        yesno.assert_not_called()
        text = path.read_text(encoding="utf-8")
        assert "## Quick Tasks" in text
        assert "- [ ] Add quick backup" in text
        assert any("Add quick backup" in line for line in console.lines)


def test_sync_completed_goal_flow_unchanged_and_does_not_offer_user_added_line() -> None:
    # No line of any goal is foreign to the platform payload, so the existing
    # completed-goal flow runs exactly as before: one commit for homelab, no
    # planning prompt for the planning-only goals, and no file write from the
    # sync step at all.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(SHARED_GOALS_COMPLETED_CLEAN, encoding="utf-8")
        contracts = {
            "sg-homelab": {"contract_id": "c-home"},
            "sg-finance": {"contract_id": "c-fin"},
        }
        # homelab: commit? y, edit done? n, edit next? n
        answers = ["y", "n", "n"]
        prompts: list[str] = []
        contract_ids: list[str] = []

        def fake_create(contract_id, **kwargs):
            contract_ids.append(contract_id)
            return {"ok": True}

        def fake_prompt(_console, prompt, default=True):
            prompts.append(prompt)
            raw = answers.pop(0)
            return default if not raw else raw in {"y", "yes"}

        with mock.patch.object(compass_update, "fetch_active_contracts", return_value=contracts), mock.patch.object(
            compass_update, "create_commit", side_effect=fake_create
        ), mock.patch.object(compass_update, "_prompt_yes_no", side_effect=fake_prompt), mock.patch.object(
            compass_update, "_prompt_optional_minutes", return_value=None
        ), mock.patch.object(
            compass_update, "_prompt_happy_moment", return_value=None
        ), mock.patch.object(
            compass_update.sys.stdin, "isatty", lambda: True
        ):
            created = compass_update._sync_completed_tasks(FakeConsole(), path, COMPLETED_CLEAN_PAYLOAD)

        assert created == 1
        assert contract_ids == ["c-home"]
        assert answers == []
        # the music goal is planning-only but has no contract, so it is skipped
        # before any prompt; nothing was user-added, so nothing was moved.
        assert prompts == ["Create commit for this goal?", "Edit done value?", "Edit next step value?"]
        assert path.read_text(encoding="utf-8") == SHARED_GOALS_COMPLETED_CLEAN


def test_main_fetches_payload_before_syncing() -> None:
    calls: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        path.write_text(SHARED_GOALS_WITH_USER_LINE, encoding="utf-8")
        args = types.SimpleNamespace(
            compass_path=str(path), no_sync_completed=False, logos_context=""
        )

        def fake_sync(console, p, payload):
            calls.append("sync")
            assert isinstance(payload, dict)
            return 0

        with mock.patch.object(compass_update, "parse_args", return_value=args), mock.patch.object(
            compass_update, "fetch_platform_shared_goals",
            side_effect=lambda: calls.append("fetch") or PAYLOAD,
        ), mock.patch.object(compass_update, "_sync_completed_tasks", side_effect=fake_sync), mock.patch.object(
            compass_update, "update_compass_markdown"
        ):
            rc = compass_update.main()

        assert rc == 0
        assert calls == ["fetch", "sync"]


def test_main_keeps_none_payload_error_path() -> None:
    args = types.SimpleNamespace(compass_path="/nonexistent/Compass.md", no_sync_completed=True, logos_context="")
    with mock.patch.object(compass_update, "parse_args", return_value=args), mock.patch.object(
        compass_update, "fetch_platform_shared_goals", return_value=None
    ):
        rc = compass_update.main()
    assert rc == 1


# ---------------------------------------------------------------------------
# Task 2 — daily-shared-goals-status stays completed-only
# ---------------------------------------------------------------------------


def test_status_script_sync_prompts_only_for_goals_with_completed_items() -> None:
    status = _load_script("daily-shared-goals-status.py")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Compass.md"
        # finance is planning-only here (its line set differs from the platform
        # steps) and must never be prompted for in the plain status flow.
        path.write_text(SHARED_GOALS_COMPLETED_CLEAN, encoding="utf-8")
        contracts = {
            "sg-homelab": {"contract_id": "c-home"},
            "sg-finance": {"contract_id": "c-fin"},
        }
        # homelab (completed flow): commit? y, edit done? n, edit next? n.
        # finance is planning-only and must never be prompted for here.
        answers = ["y", "n", "n"]
        prompts: list[str] = []
        contract_ids: list[str] = []

        def fake_create(contract_id, **kwargs):
            contract_ids.append(contract_id)
            return {"ok": True}

        def fake_prompt(prompt, default=True):
            prompts.append(prompt)
            raw = answers.pop(0)
            return default if not raw else raw in {"y", "yes"}

        with mock.patch.object(status, "fetch_active_contracts", return_value=contracts), mock.patch.object(
            status, "create_commit", side_effect=fake_create
        ), mock.patch.object(status, "_prompt_yes_no", side_effect=fake_prompt), mock.patch.object(
            status, "_prompt_optional_minutes", return_value=None
        ), mock.patch.object(
            status, "_prompt_happy_moment", return_value=None
        ), mock.patch.object(
            status.sys.stdin, "isatty", lambda: True
        ):
            created = status.maybe_sync_completed_tasks(path)

        # finance (planning-only) must not be prompted for: only one commit,
        # and the answer list is fully consumed by the homelab flow.
        assert created == 1
        assert contract_ids == ["c-home"]
        assert answers == []
        # no planning offer at all in the plain status flow, and no file write
        # from the sync itself
        assert [p for p in prompts if "next steps?" in p] == []
        assert path.read_text(encoding="utf-8") == SHARED_GOALS_COMPLETED_CLEAN
