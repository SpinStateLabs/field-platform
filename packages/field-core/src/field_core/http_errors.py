"""A 422 that does not repeat what the caller sent (C-1018; reviewer C-841 F-C841-1, C-986, C-1004).

FastAPI's default validation reply carries each error's ``input`` (for a missing field, the WHOLE body) and, for an
unexpected field, that field's NAME in ``loc``. A caller who pasted a credential into the wrong field gets it back,
and any proxy or log that keeps response bodies keeps it. ``install_validation_handler`` replies 422 with only the
error ``type``, ``loc`` and ``msg``: the name of an unexpected field is replaced by ``REDACTED_NAME``, and the message
of a value or assertion error (which a validator may build from the value), and of any kind not on an allow-list of kinds with a fixed message (uuid_parsing names the character it found), by a fixed phrase.

Any string in ``loc`` that is not a root (body, query, ...), a declared parameter, or a field name or alias of a model the
app's routes take is replaced too: that is what keeps a caller-chosen dict key out (C-1034). A key that happens to equal a field name stays.
Only the crosswalk service installs this so far; the other services still use FastAPI's default reply.
"""
from __future__ import annotations

from typing import Any

#: Shown in ``loc`` in place of the name of a field the caller sent that the model does not have.
REDACTED_NAME = "(field)"
#: Shown for an error raised by a validator, whose own message may contain the value.
VALUE_ERROR_MESSAGE = "Value error"
#: Shown for any error kind not in ``FIXED_MESSAGE_KINDS``: pydantic's message for some kinds names part of the input
#: (``uuid_parsing`` says which character it found), so only kinds whose message is a fixed phrase keep it (C-1058).
UNLISTED_KIND_MESSAGE = "Invalid value"
#: Pydantic v2 error kinds whose message never contains the caller's text: it names the expected type, a bound, a
#: pattern or the model's own allowed values. A kind not here gets ``UNLISTED_KIND_MESSAGE``.
FIXED_MESSAGE_KINDS = frozenset({
    "missing", "extra_forbidden", "none_required", "string_type", "int_type", "int_parsing", "int_from_float",
    "float_type", "float_parsing", "bool_type", "bool_parsing", "dict_type", "list_type", "tuple_type", "set_type",
    "frozen_set_type", "model_type", "model_attributes_type", "string_too_short", "string_too_long", "too_short",
    "too_long", "greater_than", "greater_than_equal", "less_than", "less_than_equal", "multiple_of", "finite_number",
    "json_invalid", "json_type", "string_pattern_mismatch", "literal_error", "enum", "bytes_type",
})


_LOC_ROOTS = frozenset({"body", "query", "path", "header", "cookie"})


def _model_names(tp: Any, seen: set, names: set) -> None:
    """Add the field names and aliases of every pydantic model reachable from the annotation ``tp``."""
    import typing

    from pydantic import BaseModel

    for arg in typing.get_args(tp):
        _model_names(arg, seen, names)
    if isinstance(tp, type) and issubclass(tp, BaseModel) and tp not in seen:
        seen.add(tp)
        for fname, finfo in tp.model_fields.items():
            names.add(fname)
            for alias in (finfo.alias, finfo.validation_alias):
                if isinstance(alias, str):
                    names.add(alias)
            _model_names(finfo.annotation, seen, names)


def _known_names(app: Any) -> set:
    """Every name a ``loc`` may carry for this app: the roots, the declared parameters and the field names and
    aliases of every model its routes take. A string in ``loc`` that is none of these came from the caller (a dict
    key), so it is replaced."""
    names: set = set(_LOC_ROOTS)
    seen: set = set()
    for route in getattr(app, "routes", ()):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for group in (dependant.query_params, dependant.path_params, dependant.header_params,
                      dependant.cookie_params, dependant.body_params):
            for param in group:
                names.add(param.name)
                alias = getattr(param, "alias", None) or getattr(getattr(param, "field_info", None), "alias", None)
                if isinstance(alias, str):
                    names.add(alias)
                annotation = getattr(getattr(param, "field_info", None), "annotation", None)
                _model_names(annotation if annotation is not None else getattr(param, "type_", None), seen, names)
        body_field = getattr(route, "body_field", None)
        if body_field is not None:
            _model_names(getattr(body_field, "type_", None), seen, names)
            _model_names(getattr(getattr(body_field, "field_info", None), "annotation", None), seen, names)
    return names


def install_validation_handler(app: Any) -> None:
    """Replace FastAPI's request-validation reply on ``app`` with one that never repeats the caller's input."""
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Any, exc: RequestValidationError) -> Any:
        known = _known_names(request.app)
        errors = []
        for err in exc.errors():
            kind = str(err.get("type", ""))
            loc = [part if (not isinstance(part, str) or part in known) else REDACTED_NAME
                   for part in err.get("loc", ())]
            if kind == "extra_forbidden" and loc:
                loc[-1] = REDACTED_NAME
            if kind == "value_error" or kind.startswith("assertion"):
                msg = VALUE_ERROR_MESSAGE
            elif kind in FIXED_MESSAGE_KINDS:
                msg = str(err.get("msg", ""))
            else:
                msg = UNLISTED_KIND_MESSAGE
            errors.append({"type": kind, "loc": loc, "msg": msg})
        return JSONResponse({"detail": errors}, status_code=422)
