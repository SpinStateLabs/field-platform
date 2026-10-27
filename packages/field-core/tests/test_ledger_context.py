"""field_core.ledger_context: only allow-listed, cleaned correlation ids and
notes reach a ledger row (P30 item 5)."""

from field_core.ledger_context import (
    CORRELATION_KEYS,
    MAX_ID_CHARS,
    MAX_NOTE_CHARS,
    correlation_context,
    ledger_note,
)

#: The context the claude-approver sends on every /check (core.py _answer).
APPROVER_CONTEXT = {
    "source": "claude-approver",
    "console_session_id": "sesn_01LYJ1mZ5RtNnD7hmAoyVY6V",
    "console_agent_id": "agent_01abc",
    "tool_name": "bash",
    "event_id": "sevt_01xyz",
    "event_type": "agent.tool_use",
    "session_thread_id": "sthr_01",
    "mcp_server_name": "github",
}


def test_the_allow_list_is_exactly_the_correlation_ids():
    assert CORRELATION_KEYS == ("source", "session_id", "console_session_id",
                                "console_agent_id", "session_thread_id", "event_id")


def test_approver_context_keeps_ids_and_drops_the_rest():
    assert correlation_context(APPROVER_CONTEXT) == {
        "source": "claude-approver",
        "console_session_id": "sesn_01LYJ1mZ5RtNnD7hmAoyVY6V",
        "console_agent_id": "agent_01abc",
        "session_thread_id": "sthr_01",
        "event_id": "sevt_01xyz",
    }


def test_a_generic_session_id_is_kept():
    assert correlation_context({"session_id": "s-1", "source": "my-agent"}) == {
        "source": "my-agent", "session_id": "s-1"}


def test_non_strings_blanks_and_non_mappings_are_dropped():
    assert correlation_context(None) == {}
    assert correlation_context(["source"]) == {}
    assert correlation_context({}) == {}
    assert correlation_context({"source": 7, "session_id": None,
                                "console_session_id": {"x": 1},
                                "event_id": "   ", "console_agent_id": True}) == {}


def test_values_are_whitespace_collapsed_and_truncated():
    got = correlation_context({"source": " a\n\tb  c ", "session_id": "x" * (MAX_ID_CHARS + 50)})
    assert got["source"] == "a b c"
    assert got["session_id"] == "x" * MAX_ID_CHARS


def test_ledger_note_cleans_truncates_and_drops_blank():
    assert ledger_note("console session sesn_01") == "console session sesn_01"
    assert ledger_note("  two\nlines  ") == "two lines"
    assert ledger_note("n" * (MAX_NOTE_CHARS + 1)) == "n" * MAX_NOTE_CHARS
    assert ledger_note("") is None
    assert ledger_note(" \n ") is None
    assert ledger_note(None) is None
