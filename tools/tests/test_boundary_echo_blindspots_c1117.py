"""C-1117 (Lane 17 Q-17 on PR 407, report 20261101-1530-reviewer-lane17-q17-pr407-e256e6b.md; C-1055 PWC): corpus cases
for the boundary-echo lint of test_boundary_echo_lint_c505.py.

Three groups, one function each so a failure names the shape:

* `test_flags_*`       a shape that sends outside text to a caller and must be a finding. Some were blind spots (a returned
                       dict literal, `sys.stderr.write`, `typer.secho`, `logging.getLogger(..).error`); the rest were
                       followed but unpinned (a typed `except`, `.strip()`, `.join()`, `logger.exception`, the taint
                       steps: tuple unpack, augmented assignment, walrus).
* `test_clean_*`       a shape that looks close and must stay clean (a fixed text, a status code, a class name, an alias
                       two steps deep inside an expression), so the extension does not over-taint.
* `test_floors_*`      the blindness floors (100 files, 600 sinks) are the numbers the lint file says they are.

The lint is a floor, not a proof; these cases pin what it is meant to see.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("boundary_echo_lint_c505", HERE / "test_boundary_echo_lint_c505.py")
lint = importlib.util.module_from_spec(_spec)
sys.modules["boundary_echo_lint_c505"] = lint
_spec.loader.exec_module(lint)  # type: ignore[union-attr]


def hits(src: str) -> int:
    found, _ = lint.scan_source(src)
    return sum(found.values())


FLAGS = {
    # --- blind spots: the shape had no sink or no taint step ---------------------------------------------------------
    "returned dict literal, detail": 'def f(resp):\n    return {"detail": resp.json()}\n',
    "returned dict literal, error from an exception": 'def f():\n    try:\n        g()\n    except ValueError as exc:\n        return {"error": str(exc)}\n',
    "returned dict literal, message from the environment": 'import os\ndef f():\n    return {"message": os.environ.get("X")}\n',
    "returned dict literal in a conditional": 'def f(resp, ok):\n    return {"ok": True} if ok else {"detail": resp.text}\n',
    "sys.stderr.write": 'import sys\ndef f(resp):\n    sys.stderr.write(resp.text)\n',
    "sys.stdout.write": 'import sys\ndef f(resp):\n    sys.stdout.write(resp.text + "\\n")\n',
    "typer.secho": 'import typer\ndef f(resp):\n    typer.secho(resp.text, fg="red")\n',
    "click.secho": 'import click\ndef f():\n    try:\n        g()\n    except OSError as exc:\n        click.secho(f"failed: {exc}")\n',
    "logging.getLogger(..).error": 'import logging\ndef f(resp):\n    logging.getLogger(__name__).error("x %s", resp.text)\n',
    "logging.getLogger(..).warning with an exception": 'import logging\ndef f():\n    try:\n        g()\n    except OSError as exc:\n        logging.getLogger("a").warning(str(exc))\n',
    # --- followed but unpinned (Lane 17 survivors S1, S4, S5, S6, S7) ------------------------------------------------
    "typed except handler whose type expression holds a sink": 'def f(resp):\n    try:\n        g()\n    except (print(resp.text) or ValueError):\n        pass\n',
    "bare except handler body": 'def f(resp):\n    try:\n        g()\n    except:\n        print(resp.text)\n',
    "str(exc).strip() through a name": 'def f():\n    try:\n        g()\n    except OSError as exc:\n        msg = str(exc).strip()\n        print(msg)\n',
    "sep.join(str(exc)) through a name": 'def f():\n    try:\n        g()\n    except OSError as exc:\n        msg = ", ".join(str(exc))\n        print(msg)\n',
    "logger.exception": 'import logging\nlog = logging.getLogger("a")\ndef f():\n    try:\n        g()\n    except OSError as exc:\n        log.exception(str(exc))\n',
    "UsageError": 'def f():\n    try:\n        g()\n    except OSError as exc:\n        raise UsageError(str(exc))\n',
    # --- taint steps -------------------------------------------------------------------------------------------------
    "tuple unpack": 'def f(resp):\n    a, b = resp.text, 1\n    print(a)\n',
    "nested tuple unpack": 'def f(resp):\n    a, (b, c) = 1, (2, resp.text)\n    print(c)\n',
    "augmented assignment": 'def f(resp):\n    m = "x: "\n    m += resp.text\n    print(m)\n',
    "annotated assignment": 'def f(resp):\n    m: str = resp.text\n    print(m)\n',
    "walrus": 'def f(resp):\n    if (w := resp.text):\n        print(w)\n',
    "walrus inside the sink": 'def f(resp):\n    print(w := resp.text)\n',
}

CLEAN = {
    "fixed text in a returned dict": 'def f():\n    return {"detail": "not found"}\n',
    "status code in a returned dict": 'def f(resp):\n    return {"status": resp.status_code}\n',
    "class name in a returned dict": 'def f():\n    try:\n        g()\n    except OSError as exc:\n        return {"error": type(exc).__name__}\n',
    "a returned dict whose tainted value is under a key that is not a field": 'def f(resp):\n    return {"payload": resp.json()}\n',
    "sys.stderr.write of a fixed text": 'import sys\ndef f():\n    sys.stderr.write("failed\\n")\n',
    "typer.secho of a fixed text": 'import typer\ndef f():\n    typer.secho("failed", fg="red")\n',
    "getLogger(..).error of a class name": 'import logging\ndef f():\n    try:\n        g()\n    except OSError as exc:\n        logging.getLogger(__name__).error("x %s", type(exc).__name__)\n',
    "__class__ of the environment": 'import os\ndef f():\n    print(os.environ.__class__)\n',
    "__name__ of the environment": 'import os\ndef f():\n    print(os.environ.__name__)\n',
    "an alias of an alias inside an expression is not followed": 'def f():\n    try:\n        g()\n    except OSError as exc:\n        y = exc\n        z = f"{y}"\n        print(z)\n',
}


@pytest.mark.parametrize("name", sorted(FLAGS))
def test_flags_(name):
    assert hits(FLAGS[name]) >= 1, f"not flagged: {name}"


@pytest.mark.parametrize("name", sorted(CLEAN))
def test_clean_(name):
    assert hits(CLEAN[name]) == 0, f"flagged: {name}"


def test_one_alias_is_followed_inside_an_expression_but_not_two():
    one = 'def f():\n    try:\n        g()\n    except OSError as exc:\n        y = exc\n        print(y)\n'
    assert hits(one) == 1
    assert hits(CLEAN["an alias of an alias inside an expression is not followed"]) == 0


def test_floors_are_the_numbers_the_lint_names():
    assert lint.MIN_FILES == 100 and lint.MIN_SINKS == 600


def test_a_returned_dict_inside_a_sink_call_is_one_finding_not_two():
    """Q-82 point 4 (measured): `return JSONResponse({"detail": resp.text})` is one echo. The dict inside the sink call
    is the sink's own argument, so only the sink records it; a dict inside any other call is still a reply-field."""
    found, _ = lint.scan_source('def f(resp):\n    return JSONResponse({"detail": resp.text})\n')
    assert dict(found) == {("f", "api-reply"): 1}
    found, _ = lint.scan_source('def f(resp):\n    return wrap({"detail": resp.text})\n')
    assert dict(found) == {("f", "reply-field"): 1}
    found, _ = lint.scan_source('def f(resp):\n    return [{"detail": resp.text}, {"error": resp.text}]\n')
    assert dict(found) == {("f", "reply-field"): 2}


def test_the_real_scan_clears_both_floors():
    _, files, sinks, bad = lint.scan_repo()
    assert not bad and files >= lint.MIN_FILES and sinks >= lint.MIN_SINKS, (files, sinks, bad)
