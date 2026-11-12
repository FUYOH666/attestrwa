import json

import pytest
import rfc8785

from attestrwa.canonical import MAX_SAFE_INTEGER, CanonicalError, canonicalize, loads_strict

from .conftest import REPO_ROOT

VECTORS_FILE = REPO_ROOT / "spec" / "test-vectors" / "canonical.json"

ACCEPTED_VALUES = [
    {},
    [],
    {"b": 1, "a": 2},
    {"z": {"y": [3, 2, 1], "x": None}, "a": True},
    {"amount": "115792089237316195423570985008687907853269984665640564039457584007913129639935"},
    {"n": 0, "m": -1, "max": MAX_SAFE_INTEGER, "min": -MAX_SAFE_INTEGER},
    {"text": 'quote " backslash \\ slash / tab \t newline \n'},
    {"control": "\u0000\u0001\u001f\u007f"},
    {"unicode": "Siam ริเวอร์ไซด์ — Öl € 😀"},
    {"separators": "  "},
    {"empty": "", "nested": [[], {}, [{}]]},
    [True, False, None, "x", 7],
]


@pytest.mark.parametrize("value", ACCEPTED_VALUES)
def test_canonical_bytes_equal_rfc8785(value) -> None:
    assert canonicalize(value) == rfc8785.dumps(value)


def test_keys_are_sorted_and_output_has_no_whitespace() -> None:
    assert canonicalize({"b": 1, "a": [1, 2], "c": {"e": None, "d": True}}) == (
        b'{"a":[1,2],"b":1,"c":{"d":true,"e":null}}'
    )


def test_key_order_in_the_source_does_not_change_the_bytes() -> None:
    assert canonicalize({"a": 1, "b": 2}) == canonicalize({"b": 2, "a": 1})


@pytest.mark.parametrize(
    "value",
    [
        1.5,
        {"x": 1.0},
        float("nan"),
        {"n": MAX_SAFE_INTEGER + 1},
        {"n": -MAX_SAFE_INTEGER - 1},
        {"Upper": 1},
        {"with-dash": 1},
        {"ключ": 1},
        {"": 1},
        {1: "non-string key"},
        {"s": "lone surrogate \ud800"},
        {"t": (1, 2)},
        {"b": b"bytes"},
    ],
)
def test_values_outside_the_subset_are_rejected(value) -> None:
    with pytest.raises(CanonicalError):
        canonicalize(value)


def test_loads_strict_reads_plain_json() -> None:
    assert loads_strict('{"a": [1, "2", true, null]}') == {"a": [1, "2", True, None]}
    assert loads_strict(b'{"a": 1}') == {"a": 1}


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1, "a": 2}',
        '{"outer": {"k": 1, "k": 1}}',
        '{"a": 1.0}',
        '{"a": 1e3}',
        '{"a": NaN}',
        '{"a": Infinity}',
        "{not json",
        b"\xff\xfe",
    ],
)
def test_loads_strict_rejects_ambiguous_or_invalid_json(text) -> None:
    with pytest.raises(CanonicalError):
        loads_strict(text)


def test_published_vectors_match_this_implementation_and_rfc8785() -> None:
    vectors = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))["vectors"]
    assert len(vectors) >= 8
    for vector in vectors:
        expected = vector["canonical"].encode("utf-8")
        assert canonicalize(vector["value"]) == expected, vector["name"]
        assert rfc8785.dumps(vector["value"]) == expected, vector["name"]
