"""Policy packs and the rule language.

A policy pack is a YAML file::

    pack_id: settlement-demo
    version: 2.0.0
    inputs:
      payee_registered: {type: bool, source: registry, provider: payee_registry, of: payee}
      amount:           {type: int,  source: subject,  field: amount}
    rules:
      - id: payee-is-registered
        require: payee_registered == true

``inputs`` declares every name a rule may use, its type and the *kind of
source* it must come from. ``rules`` is an ordered list of boolean
expressions; a settlement is approved if and only if every rule holds.

The rule language is deliberately tiny so it can be re-implemented in any
language from the grammar in ``spec/DECISION_RECORD_v0.1.md``:

    expr       := or_expr
    or_expr    := and_expr ("or" and_expr)*
    and_expr   := not_expr ("and" not_expr)*
    not_expr   := "not" not_expr | comparison
    comparison := operand (("==" | "!=" | "<" | "<=" | ">" | ">=") operand)?
    operand    := NAME | INT | STRING | "true" | "false" | "(" expr ")"

Python's ``ast`` module is used only as a parser. Expressions are checked
against a whitelist and then run by the small interpreter below; nothing is
ever passed to ``eval``.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from attestrwa.hashing import sha256, to_hex

INPUT_TYPES = ("bool", "int", "string")
SOURCE_KINDS = ("subject", "onchain", "registry", "provider", "declared")

MAX_POLICY_BYTES = 256 * 1024
MAX_RULES = 200
MAX_EXPRESSION_CHARS = 500

Value = bool | int | str

_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Constant,
    ast.Name,
    ast.Load,
)

_LITERAL_NAMES: dict[str, bool] = {"true": True, "false": False}


class DSLError(ValueError):
    """A policy file or a rule expression is malformed, or cannot be evaluated."""


@dataclass(slots=True, frozen=True)
class InputSpec:
    """Declaration of one input a policy needs."""

    name: str
    type: str
    source: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class Rule:
    """A single declarative rule."""

    id: str
    expression: str


@dataclass(slots=True, frozen=True)
class RuleResult:
    """Outcome of evaluating one rule."""

    rule_id: str
    expression: str
    passed: bool


@dataclass(slots=True, frozen=True)
class PolicyEvaluation:
    """Outcome of evaluating every rule of a policy."""

    rule_results: tuple[RuleResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.rule_results)

    @property
    def decision(self) -> str:
        return "approve" if self.passed else "reject"

    @property
    def failed_rules(self) -> list[str]:
        return [r.rule_id for r in self.rule_results if not r.passed]


@dataclass(slots=True, frozen=True)
class PolicyPack:
    """A parsed policy file together with the hash of its exact bytes."""

    pack_id: str
    version: str
    sha256: str
    inputs: tuple[InputSpec, ...]
    rules: tuple[Rule, ...]
    description: str = ""

    def input(self, name: str) -> InputSpec | None:
        for spec in self.inputs:
            if spec.name == name:
                return spec
        return None


# ---- Expression parsing ----------------------------------------------------


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise DSLError(f"expression contains disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | str):
                raise DSLError(
                    f"literal {node.value!r} is not allowed; use integers, strings, true or false"
                )
        if isinstance(node, ast.Compare) and len(node.ops) != 1:
            raise DSLError("chained comparisons are not allowed; combine them with 'and'")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            operand = node.operand
            if not (isinstance(operand, ast.Constant) and type(operand.value) is int):
                raise DSLError("unary minus is only allowed on integer literals")


def parse_expression(expression: str) -> ast.Expression:
    """Parse and whitelist one rule expression."""
    if not isinstance(expression, str) or not expression.strip():
        raise DSLError("rule expression must be a non-empty string")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise DSLError(f"rule expression is longer than {MAX_EXPRESSION_CHARS} characters")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise DSLError(f"cannot parse rule expression {expression!r}: {exc}") from exc
    _validate_ast(tree)
    return tree


def names_in(expression: str) -> set[str]:
    """Input names an expression refers to (``true`` and ``false`` excluded)."""
    tree = parse_expression(expression)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id not in _LITERAL_NAMES
    }


# ---- Evaluation ------------------------------------------------------------


def _type_name(value: Value) -> str:
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "int"
    return "string"


def _eval(node: ast.AST, context: Mapping[str, Value]) -> Value:
    if isinstance(node, ast.Expression):
        return _eval(node.body, context)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _LITERAL_NAMES:
            return _LITERAL_NAMES[node.id]
        if node.id not in context:
            raise DSLError(f"unknown input {node.id!r}")
        value = context[node.id]
        if type(value) not in (bool, int, str):
            raise DSLError(f"input {node.id!r} has unsupported type {type(value).__name__}")
        return value
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand, context)  # operand is an int literal (validated)
        operand = _eval(node.operand, context)
        if type(operand) is not bool:
            raise DSLError(f"'not' needs a bool, got {_type_name(operand)}")
        return not operand
    if isinstance(node, ast.BoolOp):
        # Every operand is evaluated (no short-circuit) so that a type error is
        # reported the same way regardless of operand order.
        values = [_eval(item, context) for item in node.values]
        for value in values:
            if type(value) is not bool:
                word = "and" if isinstance(node.op, ast.And) else "or"
                raise DSLError(f"'{word}' needs bools, got {_type_name(value)}")
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, context)
        right = _eval(node.comparators[0], context)
        op = node.ops[0]
        if type(left) is not type(right):
            raise DSLError(f"cannot compare {_type_name(left)} with {_type_name(right)}")
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if type(left) is not int:
            raise DSLError(f"ordering comparison needs ints, got {_type_name(left)}")
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        return left >= right
    raise DSLError(f"unsupported syntax: {type(node).__name__}")  # pragma: no cover


def evaluate_rule(rule: Rule, context: Mapping[str, Value]) -> bool:
    """Evaluate one rule. The expression is re-validated on every call."""
    result = _eval(parse_expression(rule.expression), context)
    if type(result) is not bool:
        raise DSLError(f"rule {rule.id!r} must evaluate to a bool, got {_type_name(result)}")
    return result


def evaluate_all(rules: Sequence[Rule], context: Mapping[str, Value]) -> PolicyEvaluation:
    """Evaluate every rule, in order, without stopping at the first failure."""
    results = tuple(
        RuleResult(rule_id=rule.id, expression=rule.expression, passed=evaluate_rule(rule, context))
        for rule in rules
    )
    return PolicyEvaluation(rule_results=results)


# ---- Policy files ----------------------------------------------------------


def _parse_inputs(raw: Any) -> tuple[InputSpec, ...]:
    if not isinstance(raw, dict) or not raw:
        raise DSLError("'inputs' must be a non-empty mapping of input name to declaration")
    specs: list[InputSpec] = []
    for name, decl in raw.items():
        if not isinstance(name, str) or not name.isidentifier() or name in _LITERAL_NAMES:
            raise DSLError(f"invalid input name {name!r}")
        if not isinstance(decl, dict):
            raise DSLError(f"input {name!r} must be a mapping with 'type' and 'source'")
        type_ = decl.get("type")
        source = decl.get("source")
        if type_ not in INPUT_TYPES:
            raise DSLError(f"input {name!r}: type must be one of {', '.join(INPUT_TYPES)}")
        if source not in SOURCE_KINDS:
            raise DSLError(f"input {name!r}: source must be one of {', '.join(SOURCE_KINDS)}")
        params = {k: v for k, v in decl.items() if k not in ("type", "source")}
        specs.append(InputSpec(name=name, type=type_, source=source, params=params))
    return tuple(specs)


def _parse_rules(raw: Any, declared: set[str]) -> tuple[Rule, ...]:
    if not isinstance(raw, list) or not raw:
        raise DSLError("'rules' must be a non-empty list")
    if len(raw) > MAX_RULES:
        raise DSLError(f"a policy may hold at most {MAX_RULES} rules")
    rules: list[Rule] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise DSLError(f"each rule must be a mapping, got {entry!r}")
        rule_id = entry.get("id")
        expression = entry.get("require")
        if not isinstance(rule_id, str) or not rule_id:
            raise DSLError(f"each rule needs a string 'id', got {entry!r}")
        if rule_id in seen:
            raise DSLError(f"duplicate rule id {rule_id!r}")
        seen.add(rule_id)
        if not isinstance(expression, str):
            raise DSLError(f"rule {rule_id!r} needs a string 'require'")
        unknown = names_in(expression) - declared
        if unknown:
            raise DSLError(
                f"rule {rule_id!r} uses undeclared input(s): {', '.join(sorted(unknown))}"
            )
        rules.append(Rule(id=rule_id, expression=expression.strip()))
    return tuple(rules)


def parse_policy(content: bytes) -> PolicyPack:
    """Parse the exact bytes of a policy file. The pack hash covers those bytes."""
    if len(content) > MAX_POLICY_BYTES:
        raise DSLError(f"policy file is larger than {MAX_POLICY_BYTES} bytes")
    try:
        doc = yaml.safe_load(content.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise DSLError(f"cannot read policy file: {exc}") from exc
    if not isinstance(doc, dict):
        raise DSLError("policy file must be a YAML mapping")
    pack_id = doc.get("pack_id")
    version = doc.get("version")
    if not isinstance(pack_id, str) or not pack_id:
        raise DSLError("policy file needs a string 'pack_id'")
    if not isinstance(version, str) or not version:
        raise DSLError("policy file needs a string 'version' (quote it, e.g. \"2.0.0\")")
    inputs = _parse_inputs(doc.get("inputs"))
    rules = _parse_rules(doc.get("rules"), {spec.name for spec in inputs})
    description = doc.get("description") or ""
    if not isinstance(description, str):
        raise DSLError("'description' must be a string")
    return PolicyPack(
        pack_id=pack_id,
        version=version,
        sha256=to_hex(sha256(content)),
        inputs=inputs,
        rules=rules,
        description=description.strip(),
    )


def load_policy(path: str | Path) -> PolicyPack:
    """Read and parse a policy file from disk."""
    file = Path(path)
    try:
        content = file.read_bytes()
    except OSError as exc:
        raise DSLError(f"cannot read policy file {file}: {exc}") from exc
    return parse_policy(content)
