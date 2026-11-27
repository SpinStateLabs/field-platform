"""The stdlib client's note is cut like ``field_core.textcut.cut`` cuts: never inside an id."""
import pytest

from field_agent import field_client as fc
from field_core.textcut import cut

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"


@pytest.mark.parametrize("kept", range(1, len(TID)))
def test_the_usage_note_is_never_cut_inside_an_id(monkeypatch, kept):
    client = fc.FieldClient("http://127.0.0.1:1", "agent-x", "token-x")
    sent = {}

    def call(method, service, path, body=None):
        sent.update(body)
        return 201, {}

    monkeypatch.setattr(client, "_call", call)
    client.report_usage("m", 1, 1, note="z" * (200 - kept) + TID + " end")
    assert sent["note"] == "z" * (200 - kept)


@pytest.mark.parametrize("text", ["", "short", "z" * 300, "z" * 180 + TID, TID * 8,
                                  "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"])
def test_the_copy_matches_field_core(text):
    for limit in range(0, 240, 7):
        assert fc._cut(text, limit) == cut(text, limit)
