"""C-504: an unreachable upstream reaches the browser as a class name, never as the exception's text.

A transport error's message can carry a URL, a proxy or an address. The console's client wrapper, its non-JSON
handler and every route that shows a failed call (a section's error text, a write's 502 body) show the name of
the failure and nothing else. The canary is a made-up marker put into the exception; no slice of it may be in
anything the page receives. Stubs only."""

from __future__ import annotations

import json

from test_ops_console_c184 import Stub, console, sc

# Built from parts so the marker is not a literal in the tree.
CANARY = "tkv-" + "c504" + "-canary" + "-" + "proxy" + "-91ac3e.invalid"
SLICES = sorted({CANARY[i:i + 8] for i in range(0, len(CANARY) - 7, 4)} | {CANARY})


def _boom() -> Exception:
    return ConnectionError(f"proxy {CANARY}:3128 refused the connection")


def _clean(text: str) -> None:
    for marker in SLICES:
        assert marker not in text, f"transport text reached the page: slice of length {len(marker)}"


class NotJson(Stub):
    def _answer(self, path, kw):
        self.calls.append((path, kw))

        class R:
            status_code = 200

            def json(_):  # noqa: N805
                raise json.JSONDecodeError(f"Expecting value {CANARY}", "x", 0)

        return R()


def test_the_client_wrapper_returns_the_class_name_on_get_and_post():
    for method in ("get", "post"):
        st, data = getattr(sc(Stub(exc=_boom())), method)("/p")
        assert (st, data) == (0, "ConnectionError")


def test_a_2xx_that_is_not_json_is_status_0_with_the_parse_error_class_name():
    for method in ("get", "post"):
        st, data = getattr(sc(NotJson()), method)("/p")
        assert (st, data) == (0, "JSONDecodeError")


def test_a_section_error_on_the_overview_shows_the_class_name_only():
    dead = sc(Stub(exc=_boom()))
    c = console(registry=dead, killswitch=dead, ledger=dead)
    r = c.get("/api/overview")
    assert r.status_code == 200
    assert "ConnectionError" in r.text
    _clean(r.text)


def test_a_write_to_an_unreachable_service_shows_no_transport_text():
    c = console(killswitch=sc(Stub(exc=_boom())))
    r = c.post("/api/agents/a1/kill", json={"operator": "Don Hagell", "reason": "r"})
    assert r.status_code >= 400
    _clean(r.text)
