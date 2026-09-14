"""force-gateway test isolation (v1.2 D2c).

Every ``create_app()`` now opens the persistent telemetry store at
``$FIELD_DATA_DIR/gateway/telemetry.sqlite3``: each test gets its own data
dir (never the repo, never another test's counts) and an operator's shell
env cannot leak a secret, a mock flag or a gateway URL into a test. Stores
opened during a test are closed after it (Windows keeps open files locked).
"""

import pytest

from force_gateway.store import GatewayStore

_ISOLATED_VARS = (
    "FIELD_SHARED_SECRET", "FIELD_GOVERNOR_URL", "FIELD_LEDGER_URL",
    "FORCE_GATEWAY_MOCK", "FORCE_GATEWAY_URL", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_KEY", "FORCE_HYGIENE_JUDGE", "FORCE_GATEWAY_SAMPLE_EVERY",
    "FORCE_TELEMETRY_WINDOW", "FORCE_TELEMETRY_RETAIN", "FORCE_HYGIENE_WINDOW",
    "FORCE_HYGIENE_BAND", "FORCE_HYGIENE_BASELINE_WINDOWS",
    "FORCE_GATEWAY_LATENCY_BUDGET_MS", "FORCE_GATEWAY_BYPASS_COOLDOWN",
    # F1: an operator's enforce posture, sentinel URL/timeout or self-agent
    # identity must never leak into a test (enforce=0 is every test's default).
    "FORCE_GATEWAY_ENFORCE", "FORCE_GATEWAY_TOOL_CHECK", "FIELD_SENTINEL_URL",
    "FORCE_GATEWAY_SENTINEL_TIMEOUT", "FIELD_SELF_AGENT_ID", "FIELD_SELF_TOKEN_ID",
)


@pytest.fixture(autouse=True)
def _isolated_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    for var in _ISOLATED_VARS:
        monkeypatch.delenv(var, raising=False)

    opened: list[GatewayStore] = []
    real_init = GatewayStore.__init__

    def tracking_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        opened.append(self)

    monkeypatch.setattr(GatewayStore, "__init__", tracking_init)
    yield
    for store in opened:
        try:
            store.close()
        except Exception:
            pass
