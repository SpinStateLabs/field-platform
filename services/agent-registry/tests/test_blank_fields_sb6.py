"""A whitespace-only name, owner or domain is a 422 on create and on PATCH, and a padded
value is stored stripped (scout S-B6). `min_length=1` let "   " through: an agent with a
blank "human owner" (the registry's one hard rule), and a domain of " finance" that the
kill-switch's exact-match domain halt for "finance" would silently miss. AgentRecord is
left alone on purpose: tightening the READ model would 500 every list over a legacy row."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_registry.api import create_app
from agent_registry.models import AgentCreate, AgentUpdate
from agent_registry.store import RegistryStore

AGENT = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
         "owner": "Controller", "domain": "finance"}
BLANK = ["", " ", "   ", "\t", "\n", " \t\n "]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert c.post("/agents", json=AGENT).status_code == 201
    yield c
    store.close()


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("blank", BLANK)
def test_create_with_a_blank_field_is_refused(field, blank):
    with pytest.raises(ValidationError):
        AgentCreate(**{**AGENT, "agent_id": "x1", field: blank})


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("blank", BLANK)
def test_update_with_a_blank_field_is_refused(field, blank):
    with pytest.raises(ValidationError):
        AgentUpdate(**{field: blank})


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
def test_patch_over_http_with_whitespace_is_422_and_changes_nothing(client, field):
    before = client.get("/agents/invoicing-agent").json()
    r = client.patch("/agents/invoicing-agent", json={field: "   "})
    assert r.status_code == 422, r.text
    assert client.get("/agents/invoicing-agent").json() == before


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
def test_post_over_http_with_whitespace_is_422(client, field):
    r = client.post("/agents", json={**AGENT, "agent_id": "second", field: "  "})
    assert r.status_code == 422, r.text
    assert client.get("/agents/second").status_code == 404


def test_surrounding_whitespace_is_stripped_on_create(client):
    r = client.post("/agents", json={**AGENT, "agent_id": "padded", "domain": " finance ",
                                     "owner": "  Controller ", "name": " N "})
    assert r.status_code == 201
    got = client.get("/agents/padded").json()
    assert (got["domain"], got["owner"], got["name"]) == ("finance", "Controller", "N")
    assert [a["agent_id"] for a in client.get("/agents", params={"domain": "finance"}).json()
            ].count("padded") == 1


def test_surrounding_whitespace_is_stripped_on_patch(client):
    r = client.patch("/agents/invoicing-agent", json={"domain": " hr "})
    assert r.status_code == 200 and r.json()["domain"] == "hr"


def test_omitted_fields_on_patch_stay_allowed_and_unchanged(client):
    r = client.patch("/agents/invoicing-agent", json={"name": "Renamed"})
    assert r.status_code == 200
    got = client.get("/agents/invoicing-agent").json()
    assert (got["name"], got["owner"], got["domain"]) == ("Renamed", "Controller", "finance")


def test_the_default_domain_is_unchanged(client):
    body = {k: v for k, v in AGENT.items() if k != "domain"}
    assert client.post("/agents", json={**body, "agent_id": "dflt"}).status_code == 201
    assert client.get("/agents/dflt").json()["domain"] == "general"


# ---- R-PR511-c42b348 condition C2: invisible characters count as blank, and as padding ---------------------------------

INVISIBLE = [chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)]


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("char", INVISIBLE, ids=lambda c: f"U+{ord(c):04X}")
def test_a_value_of_only_invisible_characters_is_blank(field, char):
    body = {"agent_id": "a", "name": "n", "owner": "o", "domain": "d", field: char * 3}
    with pytest.raises(ValidationError):
        AgentCreate(**body)
    with pytest.raises(ValidationError):
        AgentUpdate(**{field: " " + char + " " + char})


@pytest.mark.parametrize("char", INVISIBLE, ids=lambda c: f"U+{ord(c):04X}")
def test_invisible_padding_is_stripped_and_stored_stripped(char):
    rec = AgentCreate(agent_id="a", name=char + "Name" + char, owner=" " + char + "Owner" + char + " ", domain=char + "finance")
    assert (rec.name, rec.owner, rec.domain) == ("Name", "Owner", "finance")
    assert AgentUpdate(owner=char + " Bob " + char).owner == "Bob"


def test_an_invisible_character_inside_a_value_is_kept():
    inner = "a" + INVISIBLE[0] + "b"
    assert AgentCreate(agent_id="a", name=inner, owner="o").name == inner


# ---- R-PR511-3675644 condition C1: "blank" is a categories rule, one example per class ------------------------------------

#: (label, character): every one of these used to be accepted as a name, owner or domain.
BLANK_CLASSES = [
    ("Cc NUL", 0x0000), ("Cc ESC", 0x001B), ("Cc DEL", 0x007F), ("Cc NEL", 0x0085),
    ("Cf soft hyphen", 0x00AD), ("Cf left-to-right mark", 0x200E), ("Cf right-to-left mark", 0x200F),
    ("Cf embedding", 0x202A), ("Cf override", 0x202E), ("Cf invisible times", 0x2062), ("Cf mongolian vowel sep", 0x180E),
    ("Cf tag character", 0xE0020), ("Zl line separator", 0x2028), ("Zp paragraph separator", 0x2029),
    ("Zs ideographic space", 0x3000), ("Zs em space", 0x2003), ("Zs no-break space", 0x00A0),
    ("Cs lone surrogate", 0xDCFF), ("Co private use", 0xE000),
    ("Hangul choseong filler", 0x115F), ("Hangul jungseong filler", 0x1160), ("Hangul filler", 0x3164),
    ("halfwidth Hangul filler", 0xFFA0), ("braille blank", 0x2800), ("combining grapheme joiner", 0x034F),
    ("variation selector 16", 0xFE0F), ("variation selector 17", 0xE0100),
    ("Khmer inherent vowel AQ", 0x17B4), ("Khmer inherent vowel AA", 0x17B5), ("Mongolian FVS one", 0x180B),
    ("Mongolian FVS two", 0x180C), ("Mongolian FVS three", 0x180D), ("Mongolian FVS four", 0x180F),
    ("Cn default-ignorable 2065", 0x2065), ("Cn default-ignorable FFF0", 0xFFF0), ("Cn default-ignorable FFF8", 0xFFF8),
    ("Cn default-ignorable E0000", 0xE0000), ("Cn default-ignorable E0080", 0xE0080), ("Cn default-ignorable E0FFF", 0xE0FFF),
]


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("label,cp", BLANK_CLASSES, ids=[b[0] for b in BLANK_CLASSES])
def test_a_value_made_only_of_one_ignorable_class_is_blank(field, label, cp):
    body = {"agent_id": "a", "name": "n", "owner": "o", "domain": "d", field: chr(cp) * 3}
    with pytest.raises(ValidationError):
        AgentCreate(**body)
    with pytest.raises(ValidationError):
        AgentUpdate(**{field: " " + chr(cp) + " "})


# a lone surrogate never reaches the validator in a padded value: pydantic itself refuses the string (string_unicode)
PADDABLE = [b for b in BLANK_CLASSES if not b[0].startswith("Cs")]


@pytest.mark.parametrize("label,cp", PADDABLE, ids=[b[0] for b in PADDABLE])
def test_ignorable_padding_around_a_real_value_is_stripped(label, cp):
    padded = chr(cp) + " Controller " + chr(cp)
    assert AgentCreate(agent_id="a", name="n", owner=padded).owner == "Controller"
    assert AgentUpdate(domain=padded).domain == "Controller"


@pytest.mark.parametrize("value", ["José", "Ana María", "می" + chr(0x200C) + "خواهم",
                                    "f" + chr(0x200B) + "inance", "Fin" + chr(0x00AD) + "ance", "山田 太郎"])
def test_real_names_and_inner_ignorable_characters_are_kept_unchanged(value):
    assert AgentCreate(agent_id="a", name=value, owner=value, domain="d").owner == value


# ---- the recorded decision: a TRAILING ignorable character is trimmed even after visible text -------------------------------

@pytest.mark.parametrize("value,stored", [
    ("Team " + chr(0x2764) + chr(0xFE0F), "Team " + chr(0x2764)),          # a trailing emoji variation selector
    (chr(0x05D3) + chr(0x05DF) + chr(0x200F), chr(0x05D3) + chr(0x05DF)),    # a trailing right-to-left mark
])
def test_a_trailing_ignorable_character_after_visible_text_is_trimmed_by_decision(value, stored):
    assert AgentCreate(agent_id="a", name="n", owner=value).owner == stored


def test_the_unassigned_code_points_used_above_are_unassigned_in_every_supported_python():
    """The Cn rows are only meaningful while these are unassigned (Unicode keeps them reserved, so this holds on 3.11 to 3.14)."""
    import unicodedata
    assert all(unicodedata.category(chr(c)) == "Cn" for c in (0x2065, 0xFFF0, 0xFFF8, 0xE0000, 0xE0080, 0xE0FFF))
