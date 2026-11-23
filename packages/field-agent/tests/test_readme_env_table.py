"""The README Environment table names every *_URL variable the SDK reads, with the source's default port (S12-6)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "field_agent"
README = (ROOT / "README.md").read_text(encoding="utf-8")
URL_VARS = sorted({m for p in SRC.glob("*.py") for m in re.findall(r'"(FIELD_[A-Z_]+_URL)"', p.read_text(encoding="utf-8"))})


def _source_port(var):
    for p in SRC.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        m = re.search(r'"%s",\s*("http[^"]*"|[A-Z_]+)\s*\)' % var, text)
        if m:
            arg = m.group(1).strip()
            if arg.startswith('"'):
                return re.search(r":(\d+)", arg).group(1)
            const = re.search(r'^%s\s*=\s*"[^"]*:(\d+)"' % arg, text, re.M)
            if const:
                return const.group(1)
    return None


def _row(var):
    for line in README.splitlines():
        if line.startswith("| `%s`" % var):
            return line
    return None


def test_every_url_variable_is_in_the_readme():
    assert URL_VARS, "no FIELD_*_URL literal found: the scan is broken"
    for var in URL_VARS:
        assert var in README, var


def test_documented_default_port_equals_the_source():
    for var in URL_VARS:
        row = _row(var)
        port = _source_port(var)
        if port is None:          # no default in field_agent (FIELD_LEDGER_URL: canary x3-check requires it set)
            continue
        assert row is not None, var
        assert re.search(r":%s`" % port, row), var


def test_table_lists_only_variables_the_code_reads():
    code = "".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.py"))
    for line in README.splitlines():
        m = re.match(r"\| `(FIELD_[A-Z_]+)` \|", line)
        if m:
            assert '"%s"' % m.group(1) in code or m.group(1) in code, m.group(1)
