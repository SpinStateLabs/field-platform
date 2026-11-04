"""S8-7: the http_errors docstring names exactly the services whose api.py calls install_validation_handler.

The docstring once said "Only the crosswalk service installs this so far" while eleven services did. It now lists the
adopters; this test reads the docstring and the source tree (no network, no app is built) and fails when the two differ,
so the sentence cannot go stale again. A service that adopts the handler, or drops it, must change the docstring."""

import re
from pathlib import Path

from field_core import http_errors

ROOT = Path(__file__).resolve().parents[3]


def adopters_in_the_source():
    names = set()
    for api in sorted((ROOT / "services").glob("*/src/*/api.py")):
        text = api.read_text(encoding="utf-8")
        if re.search(r"^\s*install_validation_handler\(", text, re.M):
            names.add(api.parents[2].name)
    return names


def adopters_in_the_docstring():
    flat = " ".join((http_errors.__doc__ or "").split())
    m = re.search(r"Installed .{0,80}? by ((?:[a-z]+-[a-z-]+,? ?(?:and )?)+)\.", flat)
    assert m, "the docstring no longer has an 'Installed (...) by <services>.' sentence"
    return {name for name in re.split(r",\s*|\s+and\s+", m.group(1)) if name}


def test_the_source_tree_is_found():
    assert (ROOT / "services").is_dir() and len(list((ROOT / "services").glob("*/src/*/api.py"))) >= 10


def test_the_docstring_lists_exactly_the_services_that_call_the_function():
    assert adopters_in_the_docstring() == adopters_in_the_source()


def test_every_adopter_the_docstring_names_is_a_real_service_directory():
    for name in adopters_in_the_docstring():
        assert (ROOT / "services" / name).is_dir(), name


def test_the_stale_sentence_is_gone():
    assert "so far" not in (http_errors.__doc__ or "")


def test_the_non_adopters_the_docstring_mentions_really_do_not_call_it():
    for name in ("federation-broker", "attestation-reporter", "claude-approver"):
        assert name not in adopters_in_the_source()
