"""S9-28: the runbook's "Stage controller (P36, G24)" section names every refusal the controller can raise.

The section said the command line "writes the two records it checks" (it writes three kinds: alerts-proven, gate, ack-rollback),
listed three refusals (preconditions() raises more), never mentioned --build-sha or the go-sentence bound, and said nothing of
the Stage 3 irreversibility notice. This pins the section to the code: every `Refused(...)` token raised by `sha8_of()` and
`preconditions()` (templated ones such as `gate_{gate}_not_recorded` match their expanded spelling), the two reasons
`Records.unresolved()` returns, and `run_in_progress` must appear in that section; the flags and the notice are pinned by name.
Reads two files, no network (pattern: test_runbook_pins_c465.py)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = (ROOT / "docs" / "runbooks" / "v1.2-deploy-rollback.md").read_text(encoding="utf-8")
CONTROLLER = (ROOT / "tools" / "stage_controller.py").read_text(encoding="utf-8")


def section() -> str:
    start = RUNBOOK.index("## Stage controller (P36, G24)")
    end = RUNBOOK.index("\n## ", start + 5)
    return RUNBOOK[start:end]


def refused_tokens(function_name: str) -> list[str]:
    """The text of every `Refused(<str or f-string>)` raised in the named module-level function; `{...}` becomes `*`."""
    tree = ast.parse(CONTROLLER)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
    tokens = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Refused" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                tokens.append(arg.value)
            elif isinstance(arg, ast.JoinedStr):
                tokens.append("".join(v.value if isinstance(v, ast.Constant) else "*" for v in arg.values))
    return tokens


def appears(token: str, text: str) -> bool:
    pattern = re.escape(token).replace(r"\*", r"[A-Za-z0-9<>_]+")
    return re.search(pattern, text) is not None


def test_the_section_is_found_and_bounded():
    s = section()
    assert s.startswith("## Stage controller (P36, G24)") and "## Internal secret" not in s


def test_the_controller_raises_the_refusals_this_pin_expects():
    # guards the pin itself: if these helpers find nothing, the loop below would pass vacuously
    assert {"unknown_stage", "build_sha_invalid", "alerts_not_proven", "go_sentence_missing"} <= set(
        refused_tokens("preconditions") + refused_tokens("sha8_of"))
    assert any("*" in t and "not_recorded" in t for t in refused_tokens("preconditions"))
    assert any("*" in t and "not_clean" in t for t in refused_tokens("preconditions"))


def test_every_refusal_token_of_preconditions_and_sha8_of_is_in_the_section():
    s = section()
    missing = [t for t in refused_tokens("preconditions") + refused_tokens("sha8_of") if not appears(t, s)]
    assert missing == [], f"the runbook section does not name: {missing}"


def test_the_two_unresolved_reasons_and_the_run_lock_are_in_the_section():
    s = section()
    for token in ("rollback_failed_unresolved", "stage_in_progress", "run_in_progress"):
        assert token in CONTROLLER and token in s, token


def test_the_three_record_kinds_the_command_line_writes_are_named():
    s = section()
    for what in ("record alerts-proven", "record gate", "record ack-rollback"):
        assert what in s, what
    assert "write the two records" not in s


def test_the_build_sha_flag_the_go_sentence_bound_and_the_irreversibility_notice_are_documented():
    s = section()
    assert "--build-sha" in s and "--build-sha" in CONTROLLER
    max_go = re.search(r"^MAX_GO_SENTENCE = (\d+)", CONTROLLER, re.M).group(1)
    assert "MAX_GO_SENTENCE" in s and max_go in s
    assert "irreversib" in s.lower() and "irreversibility:" in CONTROLLER
