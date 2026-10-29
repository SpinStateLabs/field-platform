"""C-253 (reviewer C-232 P2): pins for the evidence-pack and regwatch details the mutation round found unasserted,
and for the lock helpers of the stale-flags store. Each test names the branch it pins."""

from __future__ import annotations

import errno
import hashlib
import os
import sys

import pytest

from compliance_crosswalk import evidence_pack, regwatch, staleness
from compliance_crosswalk.evidence_pack import StalePackError, generate_pack
from compliance_crosswalk.staleness import StaleStore, StoreLockTimeout
from field_core.templates_api import template_data


def manifest():
    data = template_data("default")
    data["agent"]["name"] = "pins-agent"
    data["agent"]["description"] = "x"
    data["identity"]["principal"] = "Controller"
    data["identity"]["org"] = "Org"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/x"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["kill_switch"]["authorized_operators"] = ["Controller"]
    data["ledger"]["store"] = "sealed-ledger service"
    data["delegation"]["granted_by"] = "Controller"
    data["delegation"]["scope"] = ["x"]
    data["delegation"]["revocation"] = {"method": "HTTP POST", "endpoint": "http://x"}
    return data


class Store:
    """active() and status() are independent so a test can make them disagree."""

    corpus_version = "corpus-pins"

    def __init__(self, flags=(), status_active=None):
        self._flags = list(flags)
        self._status_active = list(status_active if status_active is not None else flags)

    def active(self):
        return list(self._flags)

    def status(self):
        return {"corpus_version": self.corpus_version, "active": list(self._status_active), "history": []}


def pack_text(store, **kw):
    return generate_pack(manifest(), signer="Ann Lee", stale_store=store, **kw)[0]


# --- evidence_pack: the stale block ---------------------------------------------------------------------


def test_two_flags_on_one_framework_compute_its_affected_controls_once(monkeypatch):
    calls = []
    monkeypatch.setattr(evidence_pack, "_affected_controls", lambda fw: calls.append(fw) or ["C-1"])
    flags = [{"framework": "osfi-e23", "reason": "a"}, {"framework": "osfi-e23", "reason": "b"},
             {"framework": "nist-ai-rmf", "reason": "c"}]
    with pytest.raises(StalePackError) as exc:
        generate_pack(manifest(), signer="Ann Lee", stale_store=Store(flags))
    assert calls == ["osfi-e23", "nist-ai-rmf"]
    assert exc.value.affected == {"osfi-e23": ["C-1"], "nist-ai-rmf": ["C-1"]}


@pytest.mark.parametrize("flag", [{"reason": "no framework key"}, {"framework": None}, {"framework": ""}])
def test_a_flag_without_a_framework_blocks_but_names_no_affected_framework(monkeypatch, flag):
    calls = []
    monkeypatch.setattr(evidence_pack, "_affected_controls", lambda fw: calls.append(fw) or ["C-1"])
    with pytest.raises(StalePackError) as exc:
        generate_pack(manifest(), signer="Ann Lee", stale_store=Store([flag]))
    assert exc.value.affected == {} and calls == []
    assert exc.value.flags == [flag]


# --- evidence_pack: the staleness section ---------------------------------------------------------------


def test_with_no_active_flags_anywhere_the_pack_says_so():
    md = pack_text(Store())
    assert "No active stale flags." in md and "WARNING: status() reports active flags" not in md


def test_when_status_and_active_disagree_the_pack_warns_and_does_not_say_no_flags():
    flag = {"framework": "osfi-e23", "flagged_at": "2026-10-01T00:00:00+00:00", "reason": "r1",
            "stale_window_seconds": 42}
    md = pack_text(Store(flags=[], status_active=[flag]))
    assert "WARNING: status() reports active flags although active() returned none" in md
    assert "No active stale flags." not in md
    line = next(ln for ln in md.splitlines() if ln.startswith("- framework: osfi-e23"))
    assert line == ("- framework: osfi-e23 — flagged_at: 2026-10-01T00:00:00+00:00 — reason: r1 — "
                    "stale window (seconds): 42")


@pytest.mark.parametrize("entry,expected", [
    ({"framework": "osfi-e23"}, "- framework: osfi-e23"),
    ({}, "- framework: unknown"),
    ({"framework": "osfi-e23", "flagged_at": "T"}, "- framework: osfi-e23 — flagged_at: T"),
    ({"framework": "osfi-e23", "reason": "why"}, "- framework: osfi-e23 — reason: why"),
    ({"framework": "osfi-e23", "stale_window_seconds": 0}, "- framework: osfi-e23 — stale window (seconds): 0"),
    ({"framework": "osfi-e23", "flagged_at": "", "reason": "", "stale_window_seconds": None},
     "- framework: osfi-e23"),
])
def test_each_optional_fragment_of_the_staleness_line_appears_only_when_present(entry, expected):
    md = pack_text(Store(flags=[], status_active=[entry]))
    lines = [ln for ln in md.splitlines() if ln.startswith("- framework:")]
    assert lines == [expected]


# --- evidence_pack: the ingestion log -------------------------------------------------------------------


@pytest.mark.parametrize("entry,expected", [
    ({"framework": "f", "what": "w"}, "f: w"),
    ({"framework": "f", "what": "w", "source": "S"}, "f: w — source: S"),
    ({"framework": "f", "what": "w", "retrieved": "R"}, "f: w — retrieved: R"),
    ({"framework": "f", "what": "w", "note": "N"}, "f: w — note: N"),
    ({"framework": "f", "what": "w", "source": "S", "retrieved": "R", "note": "N"},
     "f: w — source: S — retrieved: R — note: N"),
    ({"framework": "f", "what": "w", "source": "", "retrieved": None, "note": ""}, "f: w"),
])
def test_each_optional_fragment_of_the_ingestion_log_line_appears_only_when_present(monkeypatch, entry, expected):
    monkeypatch.setattr(evidence_pack, "INGESTION_LOG", [entry])
    md = pack_text(Store())
    section = md.split("## Ingestion log", 1)[1]
    first = next(ln for ln in section.splitlines() if ln.strip())
    assert first == "- " + expected


# --- regwatch: the non-bytes guard and the stored-hash prefix ---------------------------------------------


@pytest.mark.parametrize("raw", ["a str body", None, 12, ["list"], object()])
def test_a_fetcher_returning_something_other_than_bytes_is_unreachable(raw):
    obs = regwatch._observe("osfi-e23", "official", "https://example.test/x", lambda url: raw, ("Principle 1.1",))
    assert obs["ok"] is False and "not bytes" in obs["error"] and type(raw).__name__ in obs["error"]


def test_a_bytearray_is_accepted_like_bytes():
    body = bytearray(b"<html><body>Principle 1.1 text</body></html>")
    obs = regwatch._observe("osfi-e23", "official", "https://example.test/x", lambda url: body, ("Principle 1.1",))
    assert obs["ok"] is True and obs["raw_bytes"] == len(body)


def test_the_status_view_shows_a_twelve_character_hash_prefix(tmp_path):
    store = StaleStore(tmp_path / "flags.json")
    refs = " · ".join(sorted({a for e in regwatch.inventory().values() for _u, anchors in e.anchors for a in anchors}))
    page = f"<html><body><p>{refs}</p></body></html>".encode()
    regwatch.run_check(store, lambda url: page)
    report = regwatch.inventory_report(store)
    osfi = next(r for r in report["frameworks"] if r["framework"] == "osfi-e23") if "frameworks" in report else \
        next(r for r in report if r["framework"] == "osfi-e23")
    cand = osfi["candidates"][0]
    text = regwatch.normalise(page)
    assert cand["stored_sha256_prefix"] == hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    assert len(cand["stored_sha256_prefix"]) == 12


def test_a_url_never_read_has_no_stored_prefix(tmp_path):
    report = regwatch.inventory_report(StaleStore(tmp_path / "flags.json"))
    rows = report["frameworks"] if isinstance(report, dict) and "frameworks" in report else report
    osfi = next(r for r in rows if r["framework"] == "osfi-e23")
    assert osfi["candidates"][0]["stored_sha256_prefix"] is None


# --- staleness: the lock helpers --------------------------------------------------------------------------

POSIX = os.name != "nt"


@pytest.fixture
def lock_fds(tmp_path):
    p = tmp_path / "x.lock"
    a = os.open(p, os.O_RDWR | os.O_CREAT, 0o644)
    b = os.open(p, os.O_RDWR | os.O_CREAT, 0o644)
    yield a, b
    for fd in (a, b):
        try:
            os.close(fd)
        except OSError:
            pass


def test_try_lock_is_true_when_free_and_false_when_another_descriptor_holds_it(lock_fds):
    a, b = lock_fds
    assert staleness._try_lock(a) is True
    assert staleness._try_lock(b) is False
    staleness._unlock(a)
    assert staleness._try_lock(b) is True
    staleness._unlock(b)


def test_unlock_actually_releases_so_the_other_descriptor_can_lock(lock_fds):
    a, b = lock_fds
    assert staleness._try_lock(a) is True
    assert staleness._unlock(a) is None
    assert staleness._try_lock(b) is True
    staleness._unlock(b)


@pytest.mark.skipif(not POSIX, reason="fcntl branch")
@pytest.mark.parametrize("code", [errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES])
def test_posix_try_lock_reads_the_held_errnos_as_not_acquired(monkeypatch, code):
    import fcntl

    def boom(fd, op):
        raise OSError(code, "held")

    monkeypatch.setattr(fcntl, "flock", boom)
    assert staleness._try_lock(0) is False


@pytest.mark.skipif(not POSIX, reason="fcntl branch")
@pytest.mark.parametrize("code", [errno.EIO, errno.EBADF, errno.ENOLCK])
def test_posix_try_lock_does_not_swallow_other_errors(monkeypatch, code):
    import fcntl

    def boom(fd, op):
        raise OSError(code, "other")

    monkeypatch.setattr(fcntl, "flock", boom)
    with pytest.raises(OSError):
        staleness._try_lock(0)


@pytest.mark.skipif(os.name != "nt", reason="msvcrt branch")
@pytest.mark.parametrize("code", [errno.EACCES, errno.EDEADLK])
def test_windows_try_lock_reads_the_held_errnos_as_not_acquired(monkeypatch, code):
    import msvcrt

    def boom(fd, mode, n):
        raise OSError(code, "held")

    monkeypatch.setattr(msvcrt, "locking", boom)
    monkeypatch.setattr(os, "lseek", lambda fd, pos, how: 0)
    assert staleness._try_lock(0) is False


@pytest.mark.skipif(os.name != "nt", reason="msvcrt branch")
@pytest.mark.parametrize("code", [errno.EIO, errno.EBADF])
def test_windows_try_lock_does_not_swallow_other_errors(monkeypatch, code):
    import msvcrt

    def boom(fd, mode, n):
        raise OSError(code, "other")

    monkeypatch.setattr(msvcrt, "locking", boom)
    monkeypatch.setattr(os, "lseek", lambda fd, pos, how: 0)
    with pytest.raises(OSError):
        staleness._try_lock(0)


class _Clock:
    """monotonic() only moves when sleep() is called; counts the lock attempts."""

    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def test_the_wait_gives_up_exactly_at_the_deadline_not_one_poll_later(tmp_path, monkeypatch):
    clock = _Clock()
    attempts = []
    monkeypatch.setattr(staleness, "time", clock)
    monkeypatch.setattr(staleness, "_try_lock", lambda fd: attempts.append(clock.now) or False)
    with pytest.raises(StoreLockTimeout):
        with staleness._file_lock(tmp_path / "w.lock", 0.0):
            pass
    assert len(attempts) == 1 and clock.sleeps == []                       # timeout 0: gives up at once


def test_the_wait_polls_until_the_deadline_then_raises(tmp_path, monkeypatch):
    clock = _Clock()
    attempts = []
    monkeypatch.setattr(staleness, "time", clock)
    monkeypatch.setattr(staleness, "_try_lock", lambda fd: attempts.append(clock.now) or False)
    with pytest.raises(StoreLockTimeout) as exc:
        with staleness._file_lock(tmp_path / "w.lock", 0.2):
            pass
    assert clock.sleeps and all(s == staleness._LOCK_POLL_SECONDS for s in clock.sleeps)
    assert 100.2 <= clock.now < 100.2 + staleness._LOCK_POLL_SECONDS + 1e-9
    assert "0.2 s" in str(exc.value) and "nothing was written" in str(exc.value)


def test_a_lock_acquired_on_the_third_try_runs_the_body_and_releases(tmp_path, monkeypatch):
    clock = _Clock()
    tries = iter([False, False, True])
    released = []
    monkeypatch.setattr(staleness, "time", clock)
    monkeypatch.setattr(staleness, "_try_lock", lambda fd: next(tries))
    monkeypatch.setattr(staleness, "_unlock", lambda fd: released.append(fd))
    ran = []
    with staleness._file_lock(tmp_path / "w.lock", 5.0):
        ran.append(1)
    assert ran == [1] and len(released) == 1 and len(clock.sleeps) == 2
