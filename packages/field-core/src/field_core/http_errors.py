"""A 422 that does not repeat what the caller sent (C-1018; reviewer C-841 F-C841-1, C-986, C-1004).

FastAPI's default validation reply carries each error's ``input`` (for a missing field, the WHOLE body) and, for an
unexpected field, that field's NAME in ``loc``. A caller who pasted a credential into the wrong field gets it back,
and any proxy or log that keeps response bodies keeps it. ``install_validation_handler`` replies 422 with only the
error ``type``, ``loc`` and ``msg``: the name of an unexpected field is replaced by ``REDACTED_NAME``, and the message
of a value or assertion error (which a validator may build from the value) by a fixed phrase.

Limits (Declared): a dict KEY chosen by the caller can still appear in ``loc`` for an error inside a free-form dict
(for example a model with ``dict[str, int]``); a service whose models take such a dict needs its own handling.
Only the crosswalk service installs this so far; the other services still use FastAPI's default reply.
"""
from __future__ import annotations

from typing import Any

#: Shown in ``loc`` in place of the name of a field the caller sent that the model does not have.
REDACTED_NAME = "(field)"
#: Shown for an error raised by a validator, whose own message may contain the value.
VALUE_ERROR_MESSAGE = "Value error"


def install_validation_handler(app: Any) -> None:
    """Replace FastAPI's request-validation reply on ``app`` with one that never repeats the caller's input."""
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Any, exc: RequestValidationError) -> Any:
        errors = []
        for err in exc.errors():
            kind = str(err.get("type", ""))
            loc = list(err.get("loc", ()))
            if kind == "extra_forbidden" and loc:
                loc[-1] = REDACTED_NAME
            if kind == "value_error" or kind.startswith("assertion"):
                msg = VALUE_ERROR_MESSAGE
            else:
                msg = str(err.get("msg", ""))
            errors.append({"type": kind, "loc": loc, "msg": msg})
        return JSONResponse({"detail": errors}, status_code=422)
