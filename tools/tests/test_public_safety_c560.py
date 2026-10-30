"""C-560 (reviewer C-540): the public repository carries no private-range address, no personal account path and no
personal mailbox in a tracked NON-TEST file, except the sites listed in `public_safety_allowlist.txt`.

Classes (a pattern per class, built from parts so this file itself holds no matchable value):
* `private-ipv4`: an address in 10/8, 172.16/12 or 192.168/16 (documentation ranges, loopback and link-local are not
  in the class);
* `windows-user-path`: a drive letter, `Users` and an account name;
* `unix-home-path`: `/home/<name>` or `/Users/<name>` where the name is not a generic CI/container account (a
  placeholder such as `<home>` or `$USER` is not a name and never matches);
* `personal-mailbox`: an address at a consumer webmail provider.
The allowlist (`path::class = count`, no values) must equal the scan in both directions: a new site fails, and so does
an entry whose site was fixed, so the list only shrinks. What stays on it today are FUNCTIONAL lines (a compose default,
a PowerShell shim default, two manifest endpoints) that need an operator decision, not a placeholder.
TEST FILES ARE SCANNED TOO (C-619 F-C619-1): fixtures that need a private-range address or a path shape are on the allowlist
by count; this file builds its own samples from parts so it holds no matchable value. A candidate that cannot be read
or is over the size limit FAILS the scan (F-C619-5).
Not covered: git history, other branches, images and binaries, secrets (a shape scan finds shapes, not meanings).
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).with_name("public_safety_allowlist.txt")
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mp3", ".pdf", ".ico", ".gz", ".zip", ".whl", ".pyc",
                 ".woff", ".woff2", ".ttf")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
GENERIC_ACCOUNTS = {"runner", "user", "app", "appuser", "node", "nonroot", "root", "ubuntu", "vscode", "ci", "me"}

_OCT = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
_PROVIDERS = ["gmail", "googlemail", "hotmail", "outlook", "live", "msn", "yahoo", "aol", "icloud", "me", "mac", "proton",
              "protonmail", "pm", "gmx", "fastmail", "hey", "zoho", "yandex", "qq"]
CLASSES: dict[str, re.Pattern[str]] = {
    # 10/8, 172.16/12, 192.168/16 and the carrier-grade NAT range 100.64/10 (overlay-network addresses)
    "private-ipv4": re.compile(
        r"(?<![\d.])(?:10\." + _OCT + r"|192\." + "168" + r"|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\."
        + _OCT + r"\." + _OCT + r"(?![\d.]*\d)"),
    # a drive letter, the user-profile directory (any case) and a name; the WSL and Git Bash spellings of the same path
    "windows-user-path": re.compile(
        r"(?i:[a-z]:(?:\\\\|\\|/)+" + "users" + r"(?:\\\\|\\|/)+|(?<![\w.])/mnt/[a-z]/" + "users" + r"/|(?<![\w.])/[a-z]/" + "users" + r"/)(?P<n>[A-Za-z0-9._-]+)"),
    "unix-home-path": re.compile(r"(?i:(?<![\w.])/(?:" + "home" + "|" + "users" + r")/)(?P<n>[A-Za-z0-9._-]+)"),
    "personal-mailbox": re.compile(r"[A-Za-z0-9._%+-]+@(?:" + "|".join(_PROVIDERS) + r")\.(?:com|net|org|ca|co|de|fr|ru|cn|me|io|uk)\b", re.I),
}


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        return [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                      if p.is_file() and not SKIP_DIRS & set(p.relative_to(ROOT).parts))


MAX_BYTES = 2_000_000


def read_scannable(files: list[str] | None = None, root: Path = ROOT) -> dict[str, str]:
    """Every tracked text file, TEST FILES INCLUDED (C-619 F-C619-1). A candidate that cannot be read, is not UTF-8 or
    is larger than MAX_BYTES FAILS the scan: a file the guard cannot read is a file it cannot vouch for
    (F-C619-5). Only the explicit binary suffixes are skipped."""
    out: dict[str, str] = {}
    unreadable: list[str] = []
    for rel in (tracked_files() if files is None else files):
        if rel.lower().endswith(SKIP_SUFFIXES) or SKIP_DIRS & set(rel.split("/")):
            continue
        p = root / rel
        try:
            if p.stat().st_size > MAX_BYTES:
                unreadable.append(f"{rel} (over {MAX_BYTES} bytes)")
                continue
            out[rel] = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f"{rel} ({type(exc).__name__})")
    assert not unreadable, "the guard cannot read these candidates: " + ", ".join(unreadable)
    return out


def scan_text(text: str) -> Counter[str]:
    found: Counter[str] = Counter()
    for line in text.splitlines():
        for cls, rx in CLASSES.items():
            for m in rx.finditer(line):
                name = m.groupdict().get("n")
                if name is not None and name.lower() in GENERIC_ACCOUNTS:
                    continue
                found[cls] += 1
    return found


def scan_texts(texts: dict[str, str]) -> Counter[str]:
    out: Counter[str] = Counter()
    for rel, text in texts.items():
        for cls, n in scan_text(text).items():
            out[f"{rel}::{cls}"] += n
    return out


def parse_allowlist(text: str) -> Counter[str]:
    out: Counter[str] = Counter()
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            key, _, n = ln.rpartition(" = ")
            out[key] = int(n)
    return out


def problems(found: Counter[str], allowed: Counter[str]) -> list[str]:
    out = [f"new public-safety site (use a placeholder, never the value): {k} x{found[k] - allowed.get(k, 0)}"
           for k in sorted(found) if found[k] > allowed.get(k, 0)]
    out += [f"stale allowlist entry (site fixed or moved, remove it): {k}" for k in sorted(allowed) if found.get(k, 0) < allowed[k]]
    return out


def test_the_repository_matches_the_allowlist():
    assert problems(scan_texts(read_scannable()), parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))) == []


def test_the_scan_is_not_blind():
    texts = read_scannable()
    assert len(texts) >= 600, "the repository has hundreds of text files; a scan of fewer is broken"
    assert "STATE.md" in texts and "docs/runbooks/token-renewal.md" in texts
    assert any(r.startswith("tools/tests/test_") for r in texts), "test files are scanned too"


# Synthetic values are assembled from parts: no matchable value appears in this file.
OCT = ["10", "1", "2", "3"]
PRIVATE = [".".join(OCT), ".".join(["192", "168", "7", "9"]), ".".join(["172", "16", "0", "5"]), ".".join(["172", "31", "255", "1"])]
SAFE_ADDR = [".".join(["192", "0", "2", "1"]), ".".join(["198", "51", "100", "7"]), ".".join(["203", "0", "113", "9"]),
             ".".join(["127", "0", "0", "1"]), ".".join(["169", "254", "1", "1"]), ".".join(["172", "32", "0", "1"]),
             ".".join(["11", "1", "2", "3"]), "1.10.1.2.3", ".".join(["10", "1", "2"])]


@pytest.mark.parametrize("addr", PRIVATE)
def test_a_private_range_address_is_flagged(addr):
    assert scan_text(f"endpoint: http://{addr}:18080/x")["private-ipv4"] == 1


@pytest.mark.parametrize("addr", SAFE_ADDR)
def test_documentation_loopback_linklocal_and_public_addresses_are_not(addr):
    assert scan_text(f"endpoint: http://{addr}:18080/x")["private-ipv4"] == 0


@pytest.mark.parametrize("line,cls", [
    ("C:" + "\\" + "Users" + "\\" + "someone" + "\\" + ".venvs", "windows-user-path"),
    ("c:/" + "Users" + "/someone/x", "windows-user-path"),
    ("C:" + "\\\\" + "Users" + "\\\\" + "someone" + "\\\\" + "x", "windows-user-path"),
    ("cd /" + "home" + "/someone/work && ls", "unix-home-path"),
    ("FIELD_DIR=/" + "Users" + "/someone/x", "unix-home-path"),
    ("${VAR:-/" + "home" + "/someone/keys}", "unix-home-path"),
    ("owner: someone@" + "gmail" + ".com", "personal-mailbox"),
    ("mail someone@" + "Outlook" + ".com", "personal-mailbox"),
])
def test_each_class_is_flagged(line, cls):
    assert scan_text(line)[cls] == 1, line


@pytest.mark.parametrize("line", [
    "C:" + "\\" + "Users" + "\\" + "<home>" + "\\" + "x",
    "cd /" + "home" + "/<home>/work",
    "<home>/.field-local/keys",
    "/" + "home" + "/runner/work/x",
    "/" + "home" + "/$USER/x",
    "/usr/home/x",
    "contact: ops@example.com",
    "https://github.com/someone",
])
def test_placeholders_generic_accounts_and_other_text_are_not_flagged(line):
    assert sum(scan_text(line).values()) == 0


def test_a_new_site_and_a_stale_entry_are_both_caught():
    allowed = parse_allowlist(ALLOWLIST.read_text(encoding="utf-8"))
    found = scan_texts(read_scannable())
    assert problems(found + Counter({"docs/x.md::private-ipv4": 1}), allowed)
    key = sorted(allowed)[0]
    assert problems(found, allowed + Counter({key: 1})) and problems(found, Counter({k: v for k, v in allowed.items() if k != key}))


def test_the_allowlist_lines_are_well_formed_and_hold_no_value():
    for ln in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#"):
            assert re.fullmatch(r"[\w./-]+::(private-ipv4|windows-user-path|unix-home-path|personal-mailbox) = [1-9]\d*", ln), ln
            assert not any(rx.search(ln) for rx in CLASSES.values()), "the allowlist must not hold a matchable value"


def test_test_files_are_scanned_too():
    texts = read_scannable()
    assert "tools/tests/test_public_safety_c560.py" in texts and "tools/tests/public_safety_allowlist.txt" in texts


def test_an_unreadable_or_oversize_candidate_fails_the_scan(tmp_path):
    (tmp_path / "ok.txt").write_text("plain", encoding="utf-8")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(AssertionError, match="bad.txt"):
        read_scannable(["ok.txt", "bad.txt"], tmp_path)
    (tmp_path / "big.txt").write_text("x" * (MAX_BYTES + 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="big.txt"):
        read_scannable(["ok.txt", "big.txt"], tmp_path)
    assert list(read_scannable(["ok.txt", "logo.png"], tmp_path)) == ["ok.txt"]      # a binary suffix is skipped by name
    with pytest.raises(AssertionError, match="gone.txt"):
        read_scannable(["gone.txt"], tmp_path)


# ---- the spellings the C-619 probe found (each built from parts: this file holds no matchable value) ----------------
CGNAT = [".".join(["100", "64", "0", "1"]), ".".join(["100", "101", "2", "3"]), ".".join(["100", "127", "255", "254"])]
NOT_CGNAT = [".".join(["100", "63", "0", "1"]), ".".join(["100", "128", "0", "1"]), ".".join(["100", "200", "1", "1"])]


@pytest.mark.parametrize("addr", CGNAT)
def test_a_cgnat_overlay_address_is_flagged(addr):
    assert scan_text(f"http://{addr}:8080/")["private-ipv4"] == 1


@pytest.mark.parametrize("addr", NOT_CGNAT)
def test_addresses_just_outside_the_cgnat_range_are_not(addr):
    assert scan_text(f"http://{addr}:8080/")["private-ipv4"] == 0


@pytest.mark.parametrize("line", [
    "c:" + "\\" + "users" + "\\" + "someone" + "\\" + "x",                    # lower-case drive and `users`
    "C:/" + "USERS" + "/someone/x",
    "/mnt/c/" + "Users" + "/someone/x",                                       # WSL
    "/mnt/d/" + "users" + "/someone/x",
    "cd /c/" + "Users" + "/someone/x",                                        # Git Bash
])
def test_windows_profile_spellings_are_flagged(line):
    assert scan_text(line)["windows-user-path"] == 1, line


@pytest.mark.parametrize("line", [
    "/" + "USERS" + "/someone/x",
    "/" + "Home" + "/someone/x",
    "x=/" + "home" + "/someone/x",
])
def test_unix_home_spellings_are_flagged_in_any_case(line):
    assert scan_text(line)["unix-home-path"] == 1, line


@pytest.mark.parametrize("provider", ["googlemail", "gmx", "live", "msn", "aol", "me", "mac", "pm", "protonmail", "fastmail",
                                      "hey", "zoho", "yandex", "qq", "icloud", "yahoo"])
def test_more_consumer_mailboxes_are_flagged(provider):
    assert scan_text(f"owner: someone@{provider}.com")["personal-mailbox"] == 1


@pytest.mark.parametrize("line", [
    "owner: someone@example.com",
    "@live decorator usage",
    "someone@mecorp.com",
    "/mnt/c/projects/x",
    "/c/projects/users/x",
    "c:" + "\\" + "windows" + "\\" + "system32",
])
def test_nearby_text_is_not_flagged_by_the_new_spellings(line):
    assert sum(scan_text(line).values()) == 0, line
