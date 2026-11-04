"""S6-17: the JSONL parser (1) reduces a uri to path + query only when it STARTS with a scheme, so a relative target that
holds ``://`` in its query keeps its own path and query (they are what ``classify`` scans for hostile tokens), and
(2) refuses a status that is a bool or outside 100..599 (the CLF parser's three-digit rule); a refused line is counted as
unparsed."""

from __future__ import annotations

import json

import pytest

from agent_incident_retro.parsers import resolve_parser

parse = resolve_parser("jsonl", "generic")


def line(uri="/x", status=200, **extra):
    return json.dumps({"ts": "2026-09-01T00:00:00Z", "ip": "203.0.113.5", "uri": uri, "status": status, **extra})


# ---- uri ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("uri", [
    "/login?next=https://evil.example/a",
    "/search?q=1&u=http://x/y",
    "/a/b?redirect=ftp://h/p&z=1",
    "/x#frag://y",
    "/a://b",
    "relative/path?u=http://h/p",
], ids=repr)
def test_a_relative_target_with_a_url_later_is_kept_whole(uri):
    p = parse(line(uri))
    assert p is not None and p.target == uri


@pytest.mark.parametrize("uri,target", [
    ("https://h/x?y=1", "/x?y=1"),
    ("http://h/a/b?c=d&e=f", "/a/b?c=d&e=f"),
    ("HTTPS://H/X", "/X"),
    ("git+ssh://h/p?q=1", "/p?q=1"),
    ("ftp://h", "/"),
    ("h2c.v1://host/p", "/p"),
    ("https://h/login?next=https://evil.example/a", "/login?next=https://evil.example/a"),
], ids=repr)
def test_a_full_url_is_still_reduced_to_its_path_and_query(uri, target):
    p = parse(line(uri))
    assert p is not None and p.target == target


@pytest.mark.parametrize("uri", ["://h/x", "1http://h/x", "-x://h/x", " http://h/x", "//h/x"], ids=repr)
def test_something_that_does_not_start_with_a_scheme_is_not_a_full_url(uri):
    p = parse(line(uri))
    assert p is not None and p.target == uri


def test_the_hostile_token_in_a_kept_query_is_visible_to_the_classifier_path():
    p = parse(line("/search?q=1&u=http://x/y&z=<script>alert(1)</script>"))
    assert p is not None and "<script>" in p.target


# ---- status ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", [True, False, 0, 99, 600, -5, 99999, 10**30, -(10**30), 1, 99.0, 600.5],
                         ids=repr)
def test_a_bool_or_out_of_range_status_is_unparsed(status):
    assert parse(line(status=status)) is None


@pytest.mark.parametrize("status,expect", [(100, 100), (200, 200), (404, 404), (599, 599), ("200", 200), ("503", 503),
                                           (200.0, 200)], ids=repr)
def test_a_real_status_parses(status, expect):
    p = parse(line(status=status))
    assert p is not None and p.status == expect


@pytest.mark.parametrize("status", ["99", "600", "abc", "", None, [], {}, "20x"], ids=repr)
def test_other_bad_statuses_are_unparsed_as_before(status):
    assert parse(line(status=status)) is None


def test_a_refused_status_is_counted_as_unparsed_by_the_reader(tmp_path):
    from agent_incident_retro.parsers import read_input
    log = tmp_path / "a.jsonl"
    log.write_text("\n".join([line(status=200), line(status=True), line(status=600), line(status=404)]) + "\n",
                   encoding="utf-8")
    info, requests = read_input(log, "a.jsonl", "jsonl", parse)
    assert info.parsed == 2 and info.unparsed == 2


@pytest.mark.parametrize("token", ["Infinity", "-Infinity", "NaN"])
def test_a_non_finite_json_status_is_unparsed_not_an_exception(token):
    """json accepts the literals; int(inf) is an OverflowError, int(nan) a ValueError."""
    raw = '{"ts":"2026-09-01T00:00:00Z","ip":"203.0.113.5","uri":"/x","status":%s}' % token
    assert parse(raw) is None
