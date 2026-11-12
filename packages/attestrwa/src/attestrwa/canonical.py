"""Canonical JSON for decision records.

A decision record is hashed, so two parties must turn the same record into
the same bytes. This module implements a strict subset of RFC 8785 (JSON
Canonicalization Scheme): every value it accepts is serialised exactly as an
RFC 8785 implementation would serialise it, and everything that could differ
between implementations is rejected up front.

Accepted values:

- objects whose keys match ``[a-z0-9_]+`` (so UTF-16 key ordering equals
  plain byte ordering),
- arrays, strings, booleans, ``null``,
- integers within ``±(2**53 - 1)``.

Rejected: floats, NaN, integers outside the safe range, non-string keys,
strings with unpaired surrogates. Large numbers such as token amounts are
carried as decimal strings.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_SAFE_INTEGER = 2**53 - 1
_KEY_RE = re.compile(r"[a-z0-9_]+")


class CanonicalError(ValueError):
    """The value cannot be canonicalised under the decision-record rules."""


def _check(value: Any, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(
                f"{path}: integer {value} is outside ±(2**53-1); carry it as a decimal string"
            )
        return
    if isinstance(value, float):
        raise CanonicalError(f"{path}: floats are not allowed in a decision record")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CanonicalError(f"{path}: string is not valid Unicode ({exc.reason})") from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
                raise CanonicalError(f"{path}: object key {key!r} must match [a-z0-9_]+")
            _check(item, f"{path}.{key}")
        return
    raise CanonicalError(f"{path}: unsupported type {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """Return the canonical UTF-8 bytes of ``value``.

    Raises :class:`CanonicalError` when the value is outside the accepted subset.
    """
    _check(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_float(text: str) -> Any:
    raise CanonicalError(f"float literal {text!r} is not allowed in a decision record")


def _reject_constant(text: str) -> Any:
    raise CanonicalError(f"JSON constant {text!r} is not allowed in a decision record")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise CanonicalError(f"duplicate object key {key!r}")
        result[key] = item
    return result


def loads_strict(text: str | bytes) -> Any:
    """Parse JSON, refusing duplicate keys, floats and NaN/Infinity.

    A lenient parser would silently keep the last duplicate key, which lets
    two different files hash to the same record. This one fails instead.
    """
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonicalError(f"record is not valid UTF-8: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except CanonicalError:
        raise
    except json.JSONDecodeError as exc:
        raise CanonicalError(f"invalid JSON: {exc}") from exc
    except RecursionError as exc:
        raise CanonicalError("invalid JSON: nested too deeply") from exc
    except ValueError as exc:
        # For example an integer literal of thousands of digits, which the
        # interpreter refuses to convert.
        raise CanonicalError("invalid JSON: a value cannot be represented") from exc
