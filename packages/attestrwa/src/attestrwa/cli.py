"""Command line: ``attestrwa verify | hash | schema-uid | policy-hash``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from attestrwa import __version__
from attestrwa.canonical import CanonicalError, loads_strict
from attestrwa.eas import DECISION_SCHEMA, schema_uid
from attestrwa.hashing import to_hex
from attestrwa.policy import DSLError, load_policy
from attestrwa.record import RecordError, record_hash, validate_record
from attestrwa.registry import RegistryError, parse_registry
from attestrwa.rpc import JsonRpc, RpcError
from attestrwa.verify import FAIL, GROUPS, PASS, Report, verify

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_MARK = {PASS: "✓", FAIL: "✗"}
_MARK_ASCII = {PASS: "ok  ", FAIL: "FAIL"}


class UsageError(Exception):
    """Bad arguments or unreadable input files."""


def _load_json(path: str) -> Any:
    try:
        content = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    try:
        return loads_strict(content)
    except CanonicalError as exc:
        raise UsageError(f"{path}: {exc}") from exc


def _find_policy(directory: str, wanted_sha256: str) -> str | None:
    for candidate in sorted(Path(directory).glob("*.y*ml")):
        try:
            if load_policy(candidate).sha256 == wanted_sha256:
                return str(candidate)
        except DSLError:
            continue
    return None


def _can_encode(text: str) -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _print_report(report: Report, source: str) -> None:
    unicode_ok = _can_encode("✓✗–…")
    marks = _MARK if unicode_ok else _MARK_ASCII
    skip_mark = "–" if unicode_ok else "skip"
    summary = report.summary
    print(f"AttestRWA decision record: {source}")
    if summary:
        print(f"  deal      {summary.get('deal_id')}")
        print(f"  escrow    {summary.get('escrow')} on chain {summary.get('chain_id')}")
        print(
            f"  decision  {str(summary.get('decision', '')).upper()} under {summary.get('policy')}"
        )
        if summary.get("attestation_uid"):
            print(f"  anchor    EAS attestation {summary['attestation_uid']}")
    for group in GROUPS:
        checks = [check for check in report.checks if check.group == group]
        if not checks:
            continue
        print(f"\n{group}")
        width = max(len(check.id) for check in checks)
        for check in checks:
            mark = marks.get(check.status, skip_mark)
            detail = check.detail if unicode_ok else check.detail.replace("…", "...")
            print(f"  {mark} {check.id.ljust(width)}  {detail}")
    passed, failed, skipped = (report.count(s) for s in (PASS, FAIL, "skip"))
    verdict = report.verdict
    note = ""
    if report.ok and skipped:
        note = " (skipped checks were not evaluated; pass --strict to require them)"
    if not report.ok and not failed:
        note = " (strict mode: skipped checks count as failures)"
    print(f"\nResult: {verdict}: {passed} passed, {failed} failed, {skipped} skipped{note}")


def _cmd_verify(args: argparse.Namespace) -> int:
    doc = _load_json(args.record)
    body = doc.get("record") if isinstance(doc, dict) and "record" in doc else doc

    policy = None
    policy_path = args.policy
    if policy_path is None and args.policy_dir and isinstance(body, dict):
        wanted = (body.get("policy") or {}).get("sha256")
        policy_path = _find_policy(args.policy_dir, wanted) if wanted else None
    if policy_path is not None:
        try:
            policy = load_policy(policy_path)
        except DSLError as exc:
            raise UsageError(str(exc)) from exc

    registry = None
    if args.registry:
        try:
            registry = parse_registry(Path(args.registry).read_bytes())
        except (OSError, RegistryError) as exc:
            raise UsageError(f"cannot read registry {args.registry}: {exc}") from exc

    rpc = None if args.offline or not args.rpc else JsonRpc(args.rpc, timeout=args.timeout)
    report = verify(
        doc,
        rpc=rpc,
        uid=args.uid,
        policy=policy,
        registry=registry,
        recheck_inputs=args.recheck_inputs,
        strict=args.strict,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report, args.record)
    return EXIT_OK if report.ok else EXIT_FAILED


def _cmd_hash(args: argparse.Namespace) -> int:
    doc = _load_json(args.record)
    body = doc["record"] if isinstance(doc, dict) and "record" in doc else doc
    try:
        validate_record(body)
    except RecordError as exc:
        raise UsageError(str(exc)) from exc
    print(to_hex(record_hash(body)))
    return EXIT_OK


def _cmd_schema_uid(_args: argparse.Namespace) -> int:
    print(to_hex(schema_uid()))
    return EXIT_OK


def _cmd_schema(_args: argparse.Namespace) -> int:
    print(DECISION_SCHEMA)
    return EXIT_OK


def _cmd_policy_hash(args: argparse.Namespace) -> int:
    try:
        pack = load_policy(args.policy)
    except DSLError as exc:
        raise UsageError(str(exc)) from exc
    print(f"{pack.sha256}  {pack.pack_id}@{pack.version}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="attestrwa",
        description="Verify decision records for compliance-gated settlement.",
    )
    parser.add_argument("--version", action="version", version=f"attestrwa {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    verify_cmd = commands.add_parser(
        "verify",
        help="check a decision record against its on-chain attestation and replay its rules",
    )
    verify_cmd.add_argument("record", help="record file (envelope or bare record), or - for stdin")
    verify_cmd.add_argument("--rpc", help="JSON-RPC endpoint of the chain the record is about")
    verify_cmd.add_argument("--uid", help="EAS attestation UID (default: the one in the file)")
    verify_cmd.add_argument("--policy", help="policy pack file the record claims to apply")
    verify_cmd.add_argument(
        "--policy-dir", help="directory to search for the policy pack by its sha256"
    )
    verify_cmd.add_argument("--registry", help="payee registry file the record refers to")
    verify_cmd.add_argument(
        "--recheck-inputs",
        action="store_true",
        help="re-run recorded on-chain calls at their recorded blocks",
    )
    verify_cmd.add_argument(
        "--offline", action="store_true", help="do not contact any RPC endpoint"
    )
    verify_cmd.add_argument(
        "--strict", action="store_true", help="treat skipped checks as failures"
    )
    verify_cmd.add_argument("--json", action="store_true", help="print the report as JSON")
    verify_cmd.add_argument("--timeout", type=float, default=20.0, help="RPC timeout in seconds")
    verify_cmd.set_defaults(handler=_cmd_verify)

    hash_cmd = commands.add_parser("hash", help="print the hash of a record")
    hash_cmd.add_argument("record")
    hash_cmd.set_defaults(handler=_cmd_hash)

    uid_cmd = commands.add_parser("schema-uid", help="print the SettlementDecision EAS schema UID")
    uid_cmd.set_defaults(handler=_cmd_schema_uid)

    schema_cmd = commands.add_parser("schema", help="print the SettlementDecision EAS schema")
    schema_cmd.set_defaults(handler=_cmd_schema)

    policy_cmd = commands.add_parser("policy-hash", help="print the sha256 of a policy pack")
    policy_cmd.add_argument("policy")
    policy_cmd.set_defaults(handler=_cmd_policy_hash)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except UsageError as exc:
        print(f"attestrwa: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except RpcError as exc:
        print(f"attestrwa: RPC error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
