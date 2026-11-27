"""The redaction reads a token id as a dashed UUID. These pins fail if the platform starts writing it another way: the
mint changes shape, or a service re-encodes an id. A shortened prefix of 8 characters is
allowed.

Limit: a source scan sees only code that names ``token_id`` on the same line.
"""
import re
from pathlib import Path

from field_core.delegation import DelegationToken
from field_mcp import client as cl

REPO = Path(__file__).resolve().parents[3]
SOURCES = sorted([*REPO.glob("services/*/src/**/*.py"), *REPO.glob("packages/*/src/**/*.py")])
OTHER_FORM = re.compile(
    r"token_id[^\n]{0,60}?\.(?:replace|hex|bytes|int|translate|split)\b"
    r"|(?:b64encode|urlsafe_b64encode|b32encode|b85encode|hexlify|UUID)\([^\n]*token_id")
SLICE = re.compile(r"token_id[^\[\n]{0,6}\[([^\]\n'\"]*:[^\]\n'\"]*)\]")


def test_a_minted_token_id_is_the_shape_the_redaction_reads():
    mint = DelegationToken.model_fields["token_id"].default_factory
    for _ in range(50):
        assert cl.UUID_SHAPED.fullmatch(mint())


def test_the_scan_sees_the_forms_it_names():
    for line in ('x = token_id.replace("-", "")', "uuid.UUID(token.token_id).hex", "b64encode(token_id.encode())"):
        assert OTHER_FORM.search(line), line
    assert SLICE.search("token.token_id[:32]").group(1) == ":32"
    assert not OTHER_FORM.search('"token_ref": hashlib.sha256(token_id.encode()).hexdigest()[:12]')


def test_no_service_writes_a_token_id_in_another_form():
    assert len(SOURCES) > 50, "the scan found too few files: it is not reading the repository"
    found = []
    for path in SOURCES:
        for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
            if OTHER_FORM.search(line) or any(m.group(1) != ":8" for m in SLICE.finditer(line)):
                found.append(f"{path.relative_to(REPO).as_posix()}:{number}")
    assert not found, found
