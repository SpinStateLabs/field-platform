"""The SHA label a running service's image was built with (v1.2 Phase C).

Every service's ``/health`` reports ``build_sha``, read here from
``FIELD_BUILD_SHA``. The images bake it at build time
(``ARG FIELD_BUILD_SHA`` -> ``ENV`` in both Dockerfiles; compose passes the
build arg from the host environment, Fly from ``--build-arg``), so a deploy
gate can assert that every container REPORTS the SHA string its build was
given (``tools/estate_probe.py health --expect-build-sha``) — which catches a
container left on an image built with another value, not an image whose code
differs from that SHA.

ENFORCED: the value is exactly what the environment says, and a missing or
blank variable reports ``unknown`` — never an empty string that could pass
for a value.

DECLARED only: that the SHA matches the code in the image. It is a label the
builder supplies; nothing here hashes the installed code. A build run with a
stale or wrong ``FIELD_BUILD_SHA`` reports that value faithfully.
"""

from __future__ import annotations

import os

ENV_VAR = "FIELD_BUILD_SHA"
UNKNOWN = "unknown"


def build_sha() -> str:
    """The build SHA from the environment, or ``unknown``.

    Read per call (not at import) so tests and long-lived processes see the
    environment they run in."""
    return os.environ.get(ENV_VAR, "").strip() or UNKNOWN
