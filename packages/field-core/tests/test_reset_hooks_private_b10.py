"""B-10: the two test-only reset hooks are not part of the public surface.

`alerts._reset_stats` and `operator_auth._reset_retired_memory` wipe process state that a
real process only loses by restarting. They keep an underscore name so no service can
import them as an API; the old public names must not come back as aliases."""
from field_core import alerts, operator_auth


def test_the_reset_hooks_have_underscore_names_only():
    assert callable(alerts._reset_stats)
    assert callable(operator_auth._reset_retired_memory)
    assert not hasattr(alerts, "reset_stats")
    assert not hasattr(operator_auth, "reset_retired_memory")


def test_the_reset_hooks_still_reset():
    alerts._stats["sent"] = 5
    alerts._reset_stats()
    assert alerts._stats["sent"] == 0
    operator_auth.retired_hash_seen = 3
    operator_auth._reset_retired_memory()
    assert operator_auth.retired_hash_seen == 0
