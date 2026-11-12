import pytest

from attestrwa.policy import (
    MAX_EXPRESSION_CHARS,
    MAX_POLICY_BYTES,
    DSLError,
    Rule,
    evaluate_all,
    evaluate_rule,
    names_in,
    parse_policy,
)

from .conftest import POLICY_FILE, STRICT_POLICY_FILE

GOOD_POLICY = b"""
pack_id: test-pack
version: "1.0.0"
inputs:
  payee_verified: {type: bool, source: registry, registry_id: payees, of: payee}
  capital_class:  {type: int,  source: provider, name: screening}
rules:
  - id: payee-must-match
    require: payee_verified == true
  - id: capital-not-red
    require: capital_class < 2
"""


def _policy(rules: str, inputs: str = "x: {type: int, source: declared}") -> bytes:
    return f'pack_id: p\nversion: "1"\ninputs:\n  {inputs}\nrules:\n{rules}'.encode()


def _rule(expression: str) -> Rule:
    return Rule(id="r", expression=expression)


# ---- Policy files ----------------------------------------------------------


def test_parse_policy_happy_path() -> None:
    pack = parse_policy(GOOD_POLICY)
    assert (pack.pack_id, pack.version) == ("test-pack", "1.0.0")
    assert [rule.id for rule in pack.rules] == ["payee-must-match", "capital-not-red"]
    assert pack.input("capital_class").type == "int"
    assert pack.sha256.startswith("0x") and len(pack.sha256) == 66


def test_policy_hash_covers_the_exact_bytes() -> None:
    assert parse_policy(GOOD_POLICY).sha256 != parse_policy(GOOD_POLICY + b"\n").sha256


def test_shipped_packs_parse_and_differ() -> None:
    demo = parse_policy(POLICY_FILE.read_bytes())
    strict = parse_policy(STRICT_POLICY_FILE.read_bytes())
    assert demo.pack_id == strict.pack_id == "settlement-demo"
    assert demo.version != strict.version
    assert demo.sha256 != strict.sha256
    assert {spec.name: spec.source for spec in demo.inputs} == {
        "payee_registered": "registry",
        "payee_sanctioned": "onchain",
        "buyer_sanctioned": "onchain",
        "amount": "subject",
        "jurisdiction": "declared",
    }


@pytest.mark.parametrize(
    "content",
    [
        b"- just\n- a list\n",
        b'version: "1"\ninputs: {x: {type: int, source: declared}}\n'
        b"rules: [{id: a, require: x == 1}]",
        b"pack_id: p\nversion: 1.0\ninputs: {x: {type: int, source: declared}}\n"
        b"rules: [{id: a, require: x == 1}]",
        b'pack_id: p\nversion: "1"\nrules: [{id: a, require: x == 1}]',
        b'pack_id: p\nversion: "1"\ninputs: {x: {type: float, source: declared}}\n'
        b"rules: [{id: a, require: x == 1}]",
        b'pack_id: p\nversion: "1"\ninputs: {x: {type: int, source: rumour}}\n'
        b"rules: [{id: a, require: x == 1}]",
        b'pack_id: p\nversion: "1"\ninputs: {x: {type: int, source: declared}}\nrules: []',
        b'pack_id: p\nversion: "1"\ninputs: {true: {type: int, source: declared}}\n'
        b"rules: [{id: a, require: x == 1}]",
        b"\xff\xfe not utf-8",
        b"pack_id: [unclosed",
    ],
)
def test_malformed_policy_files_are_rejected(content: bytes) -> None:
    with pytest.raises(DSLError):
        parse_policy(content)


def test_rule_using_an_undeclared_input_is_rejected() -> None:
    with pytest.raises(DSLError, match="undeclared"):
        parse_policy(_policy("  - id: a\n    require: y == 1\n"))


def test_duplicate_rule_ids_are_rejected() -> None:
    with pytest.raises(DSLError, match="duplicate"):
        parse_policy(_policy("  - id: a\n    require: x == 1\n  - id: a\n    require: x == 2\n"))


def test_oversized_policy_is_rejected() -> None:
    with pytest.raises(DSLError, match="larger"):
        parse_policy(b"#" * (MAX_POLICY_BYTES + 1))


# ---- Evaluation ------------------------------------------------------------


def test_evaluate_approves_when_every_rule_holds() -> None:
    pack = parse_policy(GOOD_POLICY)
    out = evaluate_all(pack.rules, {"payee_verified": True, "capital_class": 0})
    assert out.decision == "approve"
    assert out.passed and out.failed_rules == []


def test_evaluate_reports_every_rule_even_after_a_failure() -> None:
    pack = parse_policy(GOOD_POLICY)
    out = evaluate_all(pack.rules, {"payee_verified": False, "capital_class": 3})
    assert out.decision == "reject"
    assert [r.passed for r in out.rule_results] == [False, False]
    assert out.failed_rules == ["payee-must-match", "capital-not-red"]


def test_evaluate_rejects_when_one_rule_fails() -> None:
    pack = parse_policy(GOOD_POLICY)
    out = evaluate_all(pack.rules, {"payee_verified": True, "capital_class": 2})
    assert out.decision == "reject"
    assert out.failed_rules == ["capital-not-red"]


@pytest.mark.parametrize(
    ("expression", "context", "expected"),
    [
        ("a == 1", {"a": 1}, True),
        ("a != 1", {"a": 1}, False),
        ("a < 2 and b >= 2", {"a": 1, "b": 2}, True),
        ("a > 5 or b <= 2", {"a": 1, "b": 2}, True),
        ("not flag", {"flag": False}, True),
        ("not (a == 1 or a == 2)", {"a": 3}, True),
        ("flag", {"flag": True}, True),
        ("flag == false", {"flag": False}, True),
        ('country == "TH" or country == "SG"', {"country": "SG"}, True),
        ('country != "TH"', {"country": "TH"}, False),
        ("a >= -5", {"a": -5}, True),
        ("a == 1 or a == 2 and b == 9", {"a": 1, "b": 0}, True),
        ("amount <= 1000000000000", {"amount": 10**12}, True),
        ("amount <= 1000000000000", {"amount": 10**12 + 1}, False),
        (
            "big == 115792089237316195423570985008687907853269984665640564039457584007913129639935",
            {"big": 2**256 - 1},
            True,
        ),
    ],
)
def test_expression_semantics(expression: str, context: dict, expected: bool) -> None:
    assert evaluate_rule(_rule(expression), context) is expected


@pytest.mark.parametrize(
    "expression",
    [
        'print("hi")',
        "payee.attr == true",
        "__import__('os').system('echo pwned')",
        "values[0] == 1",
        "(lambda: True)()",
        "(x := 1) == 1",
        'f"{x}" == "1"',
        "[1, 2] == [1, 2]",
        "x + 1 == 2",
        "x if x else x",
        "1 < x < 3",
        "x == 1.5",
        "x == True",
        "x == None",
        "x is 1",
        "x in y",
        "-x == 1",
        "x ==",
        "",
        "   ",
        "x == 1; y == 2",
    ],
)
def test_disallowed_or_malformed_expressions_raise(expression: str) -> None:
    with pytest.raises(DSLError):
        evaluate_rule(_rule(expression), {"x": 1, "y": 2})


@pytest.mark.parametrize(
    "expression",
    [
        "0x10 == 16",
        "0o7 == 7",
        "0b1 == 1",
        "1_000 == 1000",
        "01 == 1",
        "1e3 == 1000",
        "x == 1.",
        '"a" "b" == "ab"',
        "x == 'a'",
        'x == "a\\x41"',
        'x == r"a"',
        'x == b"a"',
        'x == """a"""',
        "x == 1 # comment",
        "x == 1\nor x == 2",
        "x == 1 if x else 2",
        "x == None",
        "x == True",
        "x == 1 in y",
        "x == 1 & 1",
        "x == 1 | 1",
        "x == ~1",
        "x == 1 ; 2",
        "x == $y",
        "x == 1\x00",
    ],
)
def test_python_syntax_outside_the_published_grammar_is_rejected(expression: str) -> None:
    """The language is its grammar, not 'whatever Python parses'."""
    with pytest.raises(DSLError):
        evaluate_rule(_rule(expression), {"x": 1, "y": 2})


@pytest.mark.parametrize(
    "declaration",
    [
        "x: {type: int, source: subject}",
        "x: {type: int, source: subject, field: nonsense}",
        "x: {type: bool, source: subject, field: amount}",
        "x: {type: int, source: subject, field: amount, extra: 1}",
        "x: {type: bool, source: onchain}",
        "x: {type: bool, source: onchain, call: 'f(uint256)', args: [payee], contracts: {'1': '0x"
        + "ab" * 20
        + "'}}",
        "x: {type: bool, source: onchain, call: 'f(address)', args: [], contracts: {'1': '0x"
        + "ab" * 20
        + "'}}",
        "x: {type: bool, source: onchain, call: 'f(address)', args: [amount], contracts: {'1': '0x"
        + "ab" * 20
        + "'}}",
        "x: {type: bool, source: onchain, call: 'f(address)', args: [payee]}",
        "x: {type: bool, source: onchain, call: 'f(address)', args: [payee], contracts: {'1': '0x"
        + "AB" * 20
        + "'}}",
        "x: {type: bool, source: onchain, call: 'f(address)', args: [payee], contracts: {1: '0x"
        + "ab" * 20
        + "'}}",
        "x: {type: string, source: onchain, call: 'f(address)', args: [payee], contracts: {'1': '0x"
        + "ab" * 20
        + "'}}",
        "x: {type: bool, source: registry, of: payee}",
        "x: {type: bool, source: registry, registry_id: r, of: amount}",
        "x: {type: int, source: registry, registry_id: r, of: payee}",
        "x: {type: int, source: provider}",
        "x: {type: int, source: declared, by: someone}",
    ],
)
def test_input_declarations_must_say_exactly_what_the_source_is(declaration: str) -> None:
    with pytest.raises(DSLError):
        parse_policy(_policy("  - id: a\n    require: x == 1\n", inputs=declaration))


def test_a_hand_built_rule_cannot_reach_python() -> None:
    """A Rule constructed directly (bypassing the policy parser) is still validated."""
    marker = {"ran": False}

    class Trap:
        def __eq__(self, other):  # pragma: no cover - must never run
            marker["ran"] = True
            return True

    with pytest.raises(DSLError):
        evaluate_rule(_rule("().__class__.__mro__[1].__subclasses__()"), {})
    with pytest.raises(DSLError):
        evaluate_rule(_rule("x == 1"), {"x": Trap()})
    assert marker["ran"] is False


@pytest.mark.parametrize(
    ("expression", "context"),
    [
        ("a == true", {"a": 1}),
        ('a == "1"', {"a": 1}),
        ("a < b", {"a": "x", "b": "y"}),
        ("a < true", {"a": 1}),
        ("a and b", {"a": 1, "b": True}),
        ("a or b", {"a": True, "b": "yes"}),
        ("not a", {"a": 0}),
        ("a", {"a": 1}),
        ('"text"', {}),
        ("missing == 1", {}),
    ],
)
def test_type_errors_and_unknown_names_raise(expression: str, context: dict) -> None:
    with pytest.raises(DSLError):
        evaluate_rule(_rule(expression), context)


def test_bool_operands_are_not_short_circuited() -> None:
    """A type error on the right is reported even when the left already decides."""
    with pytest.raises(DSLError):
        evaluate_rule(_rule("a or b"), {"a": True, "b": 7})


def test_overlong_expression_is_rejected() -> None:
    with pytest.raises(DSLError, match="longer"):
        evaluate_rule(_rule("x == 1 or " * MAX_EXPRESSION_CHARS + "x == 2"), {"x": 1})


def test_deeply_nested_expression_does_not_crash_the_interpreter() -> None:
    with pytest.raises(DSLError):
        evaluate_rule(_rule("(" * 400 + "x == 1" + ")" * 400), {"x": 1})


def test_names_in_ignores_literals() -> None:
    assert names_in('a == true and (b < 3 or c == "x") and not false') == {"a", "b", "c"}
