"""C-560 (reviewer C-540): the public repository carries no private-range address, no personal account path and no
personal mailbox in a tracked NON-TEST file, except the sites listed in `public_safety_allowlist.txt`.

Classes (a pattern per class, built from parts so this file itself holds no matchable value):
* `private-ipv4`: an address in 10/8, 172.16/12 or 192.168/16 (documentation ranges, loopback and link-local are not
  in the class);
* `windows-user-path`: a drive letter, `Users` and an account name;
* `unix-home-path`: `/home/<name>` or `/Users/<name>` where the name is not a generic CI/container account (a
  placeholder such as `<home>` or `$USER` is not a name and never matches);
* `personal-mailbox`: ANY mailbox (`name@domain`, also `%40`, an entity at-sign or a spelled "[at]") outside a short
  allowlist: the company's own domains, the reserved example/test/invalid domains, `noreply`-style and `git@` local parts
  (C-793 C2; it was a list of 20 consumer providers, which let every other provider and every corporate domain through);
* `fly-hostname`: a hostname under the Fly.io application domain other than the public sandbox's own (Don's ruling C-561/C-758:
  the sandbox hostname is public by design and allowed in public files; no other estate address is);
* `private-ipv6`: a unique-local (RFC 4193) or link-local (RFC 4291) IPv6 address;
* `userinfo-url`: a URL carrying `name:password@host` (a placeholder password starting `<`, `$`, `{` or `%` is not one).
The allowlist (`path::class = count`, no values) must equal the scan in both directions: a new site fails, and so does
an entry whose site was fixed, so the list only shrinks. What stays on it today are FUNCTIONAL lines (a compose default,
a PowerShell shim default, two manifest endpoints) that need an operator decision, not a placeholder.
TEST FILES ARE SCANNED TOO (C-619 F-C619-1): fixtures that need a private-range address or a path shape are on the allowlist
by count; this file builds its own samples from parts so it holds no matchable value. A candidate that cannot be read
or is over the size limit FAILS the scan (F-C619-5).
Not covered: git history, other branches, images and binaries, secrets (a shape scan finds shapes, not meanings).
Deliberate obfuscation is OUT OF SCOPE (C-726, reviewer C-693 F-C693-3): `~name`, percent-encoded paths, decimal, hex and
zero-padded integer addresses, `.local` hostnames, "at" and "dot" spelled as words, zero-width characters inside an address.
Third-party contact data (reviewer C-619 F-C619-1, an open decision for Don, C-561) is not removed by this guard: the two
lines that hold it are on the allowlist by count so a third one fails. Covered since C-793: any mailbox outside the
allowed domains, IPv6 unique-local and link-local addresses, a URL with `name:password@host` and a WSL UNC home path
(`\\wsl$` and `\\wsl.localhost`). Covered since C-726: `/var/home`,
`/export/home`, `/data/home`, UNC administrative shares, a percent-encoded or entity at-sign and the bracketed "[at]" and
"[dot]" spellings.
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
_DOT = r"(?:\.|\s*[\[({]dot[\])}]\s*)"
_AT = r"(?:@|%40|&#0*64;|&#x0*40;|&commat;|\s*[\[({]at[\])}]\s*)"
# Mailbox rule (C-793 C2): every mailbox is flagged unless its domain is the company's own, a reserved example/test/
# invalid domain (RFC 2606) or a no-reply domain, or its local part is not a person (`noreply`, `git`).
OWN_DOMAINS = ("spinstatelabs.ca", "spinstatelabs.com")
RESERVED_DOMAINS = ("example.com", "example.org", "example.net", "noreply.github.com")
RESERVED_TLDS = ("example", "test", "invalid", "localhost")
NOT_PERSONAL_LOCALS = ("noreply", "no-reply", "git")
# The public sandbox's own application hostname (a public demo by design): assembled from parts, never spelled in one piece.
SANDBOX_HOST = "".join(('force-f', 'ield-sa', 'ndbox')) + ".fly" + ".dev"
CLASSES: dict[str, re.Pattern[str]] = {
    # 10/8, 172.16/12, 192.168/16 and the carrier-grade NAT range 100.64/10 (overlay-network addresses)
    "private-ipv4": re.compile(
        r"(?<![\d.])(?:10\." + _OCT + r"|192\." + "168" + r"|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\."
        + _OCT + r"\." + _OCT + r"(?![\d.]*\d)"),
    # unique-local (RFC 4193) and link-local (RFC 4291) IPv6; loopback and the documentation prefix are not in the class
    "private-ipv6": re.compile(r"(?<![\w:.])(?:f[cd][0-9a-f]{2}|fe[89ab][0-9a-f])(?::[0-9a-f]{0,4}){2,7}(?![\w:])", re.I),
    # a drive letter, the user-profile directory (any case) and a name; the WSL and Git Bash spellings of the same path
    "windows-user-path": re.compile(
        r"(?i:[a-z]:(?:\\\\|\\|/)+" + "users" + r"(?:\\\\|\\|/)+|(?<![\w.])/mnt/[a-z]/" + "users" + r"/|(?<![\w.])/[a-z]/" + "users" + r"/"
        # a UNC administrative share (host, drive share, profile directory, account; either slash direction)
        + r"|(?<![\w.])[\\/]{2}[^\\/\s]+[\\/][a-z]\$[\\/]+" + "users" + r"[\\/]+)(?P<n>[A-Za-z0-9._-]+)"),
    # `/home/<name>`, `/Users/<name>`, the relocated home roots (`/var/home`, `/export/home`, `/data/home`) and a WSL UNC home
    "unix-home-path": re.compile(
        r"(?i:(?<![\w.])/(?:(?:var/|export/|data/)?" + "home" + "|" + "users" + r")/"
        + r"|(?<![\w.])[\\/]{2}wsl(?:\.localhost|\$)[\\/]+[^\\/\s]+[\\/]+(?:" + "home" + "|" + "users" + r")[\\/]+)(?P<n>[A-Za-z0-9._-]+)"),
    # any host under the Fly.io application domain; the sandbox's own hostname alone is allowed (see scan_text)
    "fly-hostname": re.compile(r"(?:[a-z0-9-]+\.)+fly\.dev(?![\w-]|\.[a-z0-9])", re.I),
    # a URL with `name:password@host`; a placeholder password (`<..>`, `$..`, `{..}`, `%..`) is not one
    "userinfo-url": re.compile(r"[a-z][a-z0-9+.-]*://[^\s/@:'\"<>$`]+:(?![<${%])[^\s/@'\"<>`]+@[^\s/'\"<>`]+", re.I),
    # the at-sign may be percent-encoded, an HTML entity or spelled "[at]" / "(at)" / "{at}"; the dot likewise "[dot]" etc.
    "personal-mailbox": re.compile(
        r"(?P<local>[A-Za-z0-9._%+-]+)" + _AT + r"(?P<dom>[A-Za-z0-9-]+(?:" + _DOT + r"[A-Za-z0-9-]+)*" + _DOT + r"[A-Za-z]{2,})\b", re.I),
}


def mailbox_allowed(local: str, dom: str) -> bool:
    dom = re.sub(r"\s*[\[({]dot[\])}]\s*", ".", dom).lower()
    if local.lower() in NOT_PERSONAL_LOCALS or dom.rsplit(".", 1)[-1] in RESERVED_TLDS:
        return True
    return any(dom == d or dom.endswith("." + d) for d in OWN_DOMAINS + RESERVED_DOMAINS)


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
        url_spans = [m.span() for m in CLASSES["userinfo-url"].finditer(line)]
        for cls, rx in CLASSES.items():
            for m in rx.finditer(line):
                name = m.groupdict().get("n")
                if name is not None and name.lower() in GENERIC_ACCOUNTS:
                    continue
                if cls == "fly-hostname" and m.group(0).lower() == SANDBOX_HOST:
                    continue
                if cls == "personal-mailbox" and (mailbox_allowed(m["local"], m["dom"])
                                                  or any(m.start() < b and m.end() > a for a, b in url_spans)):
                    continue   # an allowed domain, or the `password@host` part of a URL already counted as userinfo-url
                found[cls] += 1
    return found


def scan_texts(texts: dict[str, str]) -> Counter[str]:
    out: Counter[str] = Counter()
    for rel, text in texts.items():
        for cls, n in scan_text(text).items():
            out[f"{rel}::{cls}"] += n
    return out


MIN_REASON = 20   # characters: "fixture" alone is not a reason


def parse_allowlist_entries(text: str) -> dict[str, tuple[int, str]]:
    """`path::class = count | reason` -> {key: (count, reason)}. An entry without a reason (or a one-word one) is refused
    (C-726, reviewer C-693 F-C693-4): the list says WHY a site may stay, not only that it may."""
    out: dict[str, tuple[int, str]] = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            head, sep, reason = ln.partition(" | ")
            key, _, n = head.rpartition(" = ")
            assert sep and len(reason.strip()) >= MIN_REASON, f"allowlist entry without a reason: {key or ln}"
            assert key not in out, f"duplicate allowlist entry: {key}"
            out[key] = (int(n), reason.strip())
    return out


def parse_allowlist(text: str) -> Counter[str]:
    return Counter({k: n for k, (n, _reason) in parse_allowlist_entries(text).items()})


def problems(found: Counter[str], allowed: Counter[str], tolerated: frozenset[str] = frozenset()) -> list[str]:
    """`tolerated` keys (entries of kind `decision`) may fall below their count: the owner's ruling removes the data, and the
    guard must not turn red on that edit (C-758). They may never exceed it."""
    out = [f"new public-safety site (use a placeholder, never the value): {k} x{found[k] - allowed.get(k, 0)}"
           for k in sorted(found) if found[k] > allowed.get(k, 0)]
    out += [f"stale allowlist entry (site fixed or moved, remove it): {k}" for k in sorted(allowed)
            if found.get(k, 0) < allowed[k] and k not in tolerated]
    return out


def tolerated_keys(text: str) -> frozenset[str]:
    return frozenset(k for k, (_n, reason) in parse_allowlist_entries(text).items() if reason.startswith("decision:"))


def test_the_repository_matches_the_allowlist():
    text = ALLOWLIST.read_text(encoding="utf-8")
    assert problems(scan_texts(read_scannable()), parse_allowlist(text), tolerated_keys(text)) == []


MIN_FILES = 600   # a floor under the number of files the scan reads; pinned to the repository size below (C-726)


def test_the_scan_is_not_blind():
    texts = read_scannable()
    assert len(texts) >= MIN_FILES, "the repository has hundreds of text files; a scan of fewer is broken"
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
            assert re.fullmatch(r"[\w./-]+::(private-ipv4|private-ipv6|windows-user-path|unix-home-path|userinfo-url|personal-mailbox) = [1-9]\d* \| [^|]{%d,}" % MIN_REASON, ln), ln
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
    "/mnt/c/projects/x",
    "/c/projects/users/x",
    "c:" + "\\" + "windows" + "\\" + "system32",
])
def test_nearby_text_is_not_flagged_by_the_new_spellings(line):
    assert sum(scan_text(line).values()) == 0, line


# ---- C-726 (reviewer C-693 F-C693-3 and the surviving mutants of C-693): more spellings, each built from parts --------
def test_the_blindness_floor_stays_near_the_repository_size():
    """Lowering MIN_FILES (the reviewer's survivor: 600 -> 6) would let a scan that read almost nothing pass."""
    assert MIN_FILES >= len(tracked_files()) // 2


@pytest.mark.parametrize("root", ["var/" + "home", "export/" + "home", "data/" + "home"])
def test_relocated_home_roots_are_flagged(root):
    assert scan_text(f"x=/{root}/someone/work")["unix-home-path"] == 1


@pytest.mark.parametrize("line", [
    "\\\\" + "fileserver" + "\\" + "c$" + "\\" + "Users" + "\\" + "someone" + "\\x",        # UNC admin share
    "//" + "fileserver" + "/" + "d$" + "/" + "users" + "/someone/x",                                  # either slash direction
])
def test_a_unc_admin_share_profile_path_is_flagged(line):
    assert scan_text(line)["windows-user-path"] == 1, line


@pytest.mark.parametrize("line", [
    "/var/lib/someone/x",
    "/var/" + "homepage" + "/x",
    "//fileserver/share/" + "users" + "/someone/x",                                                    # not an administrative share
    "\\\\" + "fileserver" + "\\" + "c$" + "\\" + "Windows" + "\\x",
])
def test_nearby_paths_are_not_flagged_by_the_new_roots(line):
    assert sum(scan_text(line).values()) == 0, line


@pytest.mark.parametrize("line", [
    "owner: someone%40" + "gmail" + ".com",
    "owner: someone&#64;" + "gmail" + ".com",
    "owner: someone&#x40;" + "gmail" + ".com",
    "owner: someone&commat;" + "gmail" + ".com",
    "owner: someone [at] " + "gmail" + ".com",
    "owner: someone (at) " + "gmail" + ".com",
    "owner: someone{at}" + "gmail" + ".com",
    "owner: someone@" + "gmail" + " [dot] com",
    "owner: someone@" + "gmail" + "(dot)com",
    "owner: someone [at] " + "gmail" + " {dot} com",
])
def test_obfuscated_consumer_mailboxes_are_flagged(line):
    assert scan_text(line)["personal-mailbox"] == 1, line


@pytest.mark.parametrize("line", [
    "owner: someone [at] example.com",
    "owner: someone (at) example [dot] com",
    "an (at) sign and a gmail mention",
])
def test_obfuscation_spellings_of_allowed_domains_are_not_flagged(line):
    assert sum(scan_text(line).values()) == 0, line


# Every provider and every TLD, spelled out here (not read from the module), so removing one from the module fails a test.
ALL_PROVIDERS = ["gmail", "googlemail", "hotmail", "outlook", "live", "msn", "yahoo", "aol", "icloud", "me", "mac", "proton",
                 "protonmail", "pm", "gmx", "fastmail", "hey", "zoho", "yandex", "qq"]
ALL_TLDS = ["com", "net", "org", "ca", "co", "de", "fr", "ru", "cn", "me", "io", "uk"]


@pytest.mark.parametrize("provider", ALL_PROVIDERS)
def test_every_listed_provider_is_flagged(provider):
    assert scan_text(f"owner: someone@{provider}.com")["personal-mailbox"] == 1


@pytest.mark.parametrize("tld", ALL_TLDS)
def test_every_listed_top_level_domain_is_flagged(tld):
    assert scan_text("owner: someone@" + "gmail" + f".{tld}")["personal-mailbox"] == 1


# ---- C-726 (reviewer C-693 F-C693-4): every allowlist entry says why ------------------------------------------------
def test_every_allowlist_entry_has_a_reason_that_names_its_kind():
    entries = parse_allowlist_entries(ALLOWLIST.read_text(encoding="utf-8"))
    assert entries
    for key, (_n, reason) in entries.items():
        assert reason.split(":")[0] in ("fixture", "functional", "test pin", "decision"), (key, reason)
        assert not any(rx.search(reason) for rx in CLASSES.values()), f"{key}: the reason must not hold a matchable value"


@pytest.mark.parametrize("line", [
    "a/b.py::private-ipv4 = 2",
    "a/b.py::private-ipv4 = 2 | fixture",
    "a/b.py::private-ipv4 = 2 |  ",
])
def test_an_entry_without_a_real_reason_is_refused(line):
    with pytest.raises(AssertionError, match="without a reason"):
        parse_allowlist_entries(line)


def test_a_duplicate_entry_is_refused_and_a_good_one_parses():
    good = "a/b.py::private-ipv4 = 2 | fixture: a test needs a sample address"
    assert parse_allowlist_entries(good) == {"a/b.py::private-ipv4": (2, "fixture: a test needs a sample address")}
    with pytest.raises(AssertionError, match="duplicate"):
        parse_allowlist_entries(good + "\n" + good)
    assert parse_allowlist(good) == Counter({"a/b.py::private-ipv4": 2})


# ---- C-793 (reviewer C-793 C2 and C3) ------------------------------------------------------------------------------------
def test_max_bytes_is_pinned_by_value():
    """Raising the limit (the reviewer's survivor: 2 MB -> 2 GB) must fail a test, not only a size-relative one."""
    assert MAX_BYTES == 2_000_000


# Public provider and ISP names (no person): the reviewer's probe found 35 of these let through by the old provider list.
PROBE_PROVIDERS = ["mail.com", "inbox.com", "mail.ru", "web.de", "t-online.de", "orange.fr", "free.fr", "libero.it", "naver.com",
                   "163.com", "protonmail.ch", "tutanota.com", "tuta.io", "duck.com", "mailbox.org", "posteo.de", "hushmail.com",
                   "ymail.com", "rocketmail.com", "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "bellsouth.net",
                   "cox.net", "earthlink.net", "bell.ca", "rogers.com", "shaw.ca", "sympatico.ca", "telus.net", "videotron.ca",
                   "sasktel.net", "bell.net"]


@pytest.mark.parametrize("domain", PROBE_PROVIDERS)
def test_any_provider_and_isp_mailbox_is_flagged(domain):
    assert scan_text("owner: someone@" + domain)["personal-mailbox"] == 1


@pytest.mark.parametrize("domain", ["acme-corp.io", "client" + "-name.com", "mecorp.com", "sub.acme-corp.io", "test.com", "invalid.com",
                                    "notexample.com", "example.com.evil.io", "evilspinstatelabs.ca", "spinstatelabs.ca.evil.io",
                                    "github.com", "anthropic.com", "x.internal", "x.local"])
def test_a_corporate_or_lookalike_domain_is_flagged(domain):
    assert scan_text("contact: someone@" + domain)["personal-mailbox"] == 1


@pytest.mark.parametrize("mailbox", [
    "someone@example.com", "someone@example.org", "someone@example.net", "someone@mail.example.com", "someone@a.b.example.org",
    "someone@host.test", "someone@host.invalid", "someone@host.example", "someone@host.localhost",
    "someone@spinstatelabs.ca", "someone@spinstatelabs.com", "someone@mail.spinstatelabs.ca",
    "13129187+someone@users.noreply.github.com", "noreply@anthropic.com", "no-reply@whatever.io", "NoReply@whatever.io",
    "git@github.com", "git@gitlab.com", "someone [at] example [dot] com", "someone%40example.org",
])
def test_company_reserved_and_noreply_mailboxes_are_not_flagged(mailbox):
    assert scan_text("contact: " + mailbox)["personal-mailbox"] == 0, mailbox


@pytest.mark.parametrize("line", [
    "pkg@1.2.3", "actions/checkout@v4", "uses: owner/repo@" + "a" * 40, "@pytest.mark.asyncio", "a @ b.c",
    "user@host", "see (at) the end.", "x [at] y",
])
def test_text_that_only_looks_like_a_mailbox_is_not_flagged(line):
    assert scan_text(line)["personal-mailbox"] == 0, line


def test_a_mailbox_inside_a_userinfo_url_counts_once_as_the_url():
    url = "https://" + "someone" + ":" + "pw" + "@" + "acme-corp.io" + "/x"
    assert dict(scan_text(url)) == {"userinfo-url": 1}


# IPv6: built at run time from parts. Unique-local is the fc and fd blocks (/7), link-local the fe8 to feb blocks (/10).
_V6 = [":".join(["fd12", "3456", "789a", "1", "0", "0", "0", "1"]), "fc00" + "::" + "1", "fd00" + "::", "fe80" + "::" + "1",
       "fe80" + "::" + "a:b:c:d", "feb" + "f::1", "FD12" + "::AB"]
_NOT_V6 = ["::1", "2001" + ":db8::1", "fec0" + "::1", "fe7f" + "::1", "fb00" + "::1", "fe0" + "::1", "fed" + "::", "12:34:56:78:9a:bc",
           ":".join(["fd12"] + ["1"] * 8), "fdd", "ab" + "fd12" + "::1", "1" + "fd12" + "::1", "fd" + "12"]


@pytest.mark.parametrize("addr", _V6)
def test_a_unique_local_or_link_local_ipv6_address_is_flagged(addr):
    assert scan_text(f"host: {addr}")["private-ipv6"] == 1, addr
    assert scan_text(f"http://[{addr}]:8080/x")["private-ipv6"] == 1, addr


@pytest.mark.parametrize("addr", _NOT_V6)
def test_loopback_documentation_and_other_ipv6_text_is_not_flagged(addr):
    assert scan_text(f"host: {addr}")["private-ipv6"] == 0, addr


# URL userinfo: a user, a password, an at-sign and a host.
def _url(user: str, password: str, host: str = "host.example.org") -> str:
    return "https://" + user + ":" + password + "@" + host + "/x"


@pytest.mark.parametrize("url", [_url("svc", "pw"), _url("svc", "p" + "ass" + "word"), "ftp://" + "svc" + ":" + "pw" + "@" + "host.example.org",
                                 _url("svc", "pw", ".".join(["10", "0", "0", "5"]) + ":8080"), _url("svc", "a.b-c_d!")])
def test_a_url_with_userinfo_and_a_password_is_flagged(url):
    assert scan_text(f"endpoint: {url}")["userinfo-url"] == 1, url


@pytest.mark.parametrize("url", [_url("svc", "<password>"), _url("svc", "$PASSWORD"), _url("svc", "${PASSWORD}"), _url("svc", "%(pw)s"),
                                 _url("svc", "{pw}"),
                                 "https://" + "svc" + "@" + "host.example.org/x", "https://host.example.org:8443/x@y", "http://localhost:8080/a",
                                 "mailto:x@example.com"])
def test_a_placeholder_password_or_no_password_is_not_a_userinfo_url(url):
    assert scan_text(f"endpoint: {url}")["userinfo-url"] == 0, url


# WSL UNC: `\\wsl$\<distro>\home\<name>` and `\\wsl.localhost\<distro>\home\<name>`, either slash direction.
@pytest.mark.parametrize("line", [
    "\\\\" + "wsl$" + "\\" + "Ubuntu" + "\\" + "home" + "\\" + "someone" + "\\x",
    "\\\\" + "wsl.localhost" + "\\" + "Debian" + "\\" + "home" + "\\" + "someone",
    "//" + "wsl$" + "/Ubuntu/" + "home" + "/someone/x",
    "//" + "wsl.localhost" + "/Ubuntu/" + "home" + "/someone/x",
    "\\\\" + "WSL$" + "\\" + "Ubuntu" + "\\" + "Home" + "\\" + "someone",
])
def test_a_wsl_unc_home_path_is_flagged(line):
    assert scan_text(line)["unix-home-path"] == 1, line


@pytest.mark.parametrize("line", [
    "\\\\" + "wsl$" + "\\" + "Ubuntu" + "\\" + "etc" + "\\" + "hosts",
    "\\\\" + "wsl$" + "\\" + "Ubuntu" + "\\" + "home" + "\\" + "runner" + "\\x",
    "\\\\" + "otherhost" + "\\" + "Ubuntu" + "\\" + "home" + "\\" + "someone",
    "\\\\" + "wsl$" + "\\" + "home" + "\\" + "someone",
    "x" + "\\\\" + "wsl$" + "\\" + "Ubuntu" + "\\" + "home" + "\\" + "someone",
])
def test_nearby_wsl_text_is_not_flagged(line):
    assert sum(scan_text(line).values()) == 0, line


# ---- C-758 (Don's ruling on C-561): the sandbox's own hostname is allowed, no other Fly.io host is --------------------------
SANDBOX_SPELLED_AGAIN = "".join(['force-fiel', 'd-sandbox']) + ".fly" + ".dev"


def test_the_sandbox_hostname_is_assembled_the_same_way_twice():
    assert SANDBOX_HOST == SANDBOX_SPELLED_AGAIN


@pytest.mark.parametrize("line", [
    "https://" + SANDBOX_SPELLED_AGAIN + "/health",
    SANDBOX_SPELLED_AGAIN.upper(),
    "url: " + SANDBOX_SPELLED_AGAIN + ":443",
    "(" + SANDBOX_SPELLED_AGAIN + ")",
])
def test_the_sandbox_hostname_is_allowed(line):
    assert scan_text(line)["fly-hostname"] == 0, line


@pytest.mark.parametrize("host", [
    "other-app" + ".fly" + ".dev",
    "sandbox-two" + ".fly" + ".dev",
    "www." + SANDBOX_SPELLED_AGAIN,                              # a subdomain of the sandbox is not the sandbox
    "a.b." + "other-app" + ".fly" + ".dev",
    SANDBOX_SPELLED_AGAIN.split(".")[0] + "x" + ".fly" + ".dev",    # a one-character lookalike
    "x" + SANDBOX_SPELLED_AGAIN,
    "OTHER-APP" + ".FLY" + ".DEV",                               # host names are case-insensitive
])
def test_another_fly_hostname_is_still_refused(host):
    assert scan_text("https://" + host + "/x")["fly-hostname"] == 1, host


@pytest.mark.parametrize("line", [
    "fly" + ".dev",
    "https://" + "fly" + ".dev/docs",
    SANDBOX_SPELLED_AGAIN + ".evil.io",
    "other-app" + ".fly" + ".dev.evil.io",
    "other-app" + ".fly" + ".devices",
    "other-app" + ".fly" + "-dev.io",
    "other-app" + ".fly" + ".dev-x.io",
])
def test_text_that_only_looks_like_a_fly_hostname_is_not_flagged(line):
    assert scan_text(line)["fly-hostname"] == 0, line


# A `decision` entry may shrink (the owner's ruling removes the data) but never grow; every other kind must match exactly.
def test_a_decision_entry_may_fall_to_zero_but_not_rise_and_a_fixture_entry_may_not_fall():
    allowed = Counter({"a/b.md::personal-mailbox": 2, "c/d.py::private-ipv4": 1})
    tolerated = frozenset({"a/b.md::personal-mailbox"})
    assert problems(Counter({"c/d.py::private-ipv4": 1}), allowed, tolerated) == []
    assert problems(Counter({"a/b.md::personal-mailbox": 1, "c/d.py::private-ipv4": 1}), allowed, tolerated) == []
    assert problems(Counter({"a/b.md::personal-mailbox": 3, "c/d.py::private-ipv4": 1}), allowed, tolerated)
    assert problems(Counter({"a/b.md::personal-mailbox": 2}), allowed, tolerated)        # the fixture entry went stale


def test_only_decision_entries_are_tolerated():
    text = ("a.py::private-ipv4 = 1 | fixture: a test needs a sample address\n"
            "b.md::personal-mailbox = 2 | decision: third-party data awaiting the owner's ruling\n"
            "c.md::personal-mailbox = 1 | functional: a deploy default that waits on an operator\n")
    assert tolerated_keys(text) == frozenset({"b.md::personal-mailbox"})


def test_the_guard_does_not_depend_on_files_a_ruling_may_remove():
    """C-758 removes a tracked media file and rewrites two lines of a skill file: the scan skips media by suffix and the
    skill-file entry is a `decision` entry, so the guard stays green on a tree without them."""
    assert ".mp4" in SKIP_SUFFIXES
    text = ALLOWLIST.read_text(encoding="utf-8")
    assert "agents/ssl-invoicing-agent/SKILL.md::personal-mailbox" in tolerated_keys(text)
    found = scan_texts(read_scannable())
    found.pop("agents/ssl-invoicing-agent/SKILL.md::personal-mailbox", None)
    assert problems(found, parse_allowlist(text), tolerated_keys(text)) == []
