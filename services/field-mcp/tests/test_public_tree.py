"""Public repo: no estate addresses, flag values, build SHAs or credentials in the shipped tree. Mutant: add a
documentation example with a private address, a 40-hex string, or ``FIELD_SHARED_SECRET=<value>``."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = [p for p in [*ROOT.joinpath("src").rglob("*"), ROOT / "README.md", *ROOT.joinpath("scripts").rglob("*")]
         if p.is_file() and p.suffix in (".py", ".md", ".json", ".toml")]
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b(?!/\d)")   # a CIDR range (a network rule) is not an address
ALLOWED_IPS = {"127.0.0.1", "0.0.0.0"}


def test_no_address_hash_or_secret_in_the_shipped_tree():
    assert FILES
    for p in FILES:
        text = p.read_text()
        for ip in IPV4.findall(text):
            assert ip in ALLOWED_IPS, (p.name, ip)
        assert not re.search(r"\b[0-9a-f]{40}\b", text), p.name
        assert not re.search(r"(SHARED_SECRET|OPERATOR_KEY|_KEY)=[^<\s\"'$]", text), p.name
