"""Command line: ``attestrwa verify | hash | sign | keygen | public-key | …``."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from attestrwa import __version__
from attestrwa.canonical import CanonicalError, loads_strict
from attestrwa.eas import DECISION_SCHEMA, schema_uid
from attestrwa.hashing import sha256, to_hex
from attestrwa.policy import DSLError, load_policy
from attestrwa.record import (
    ANCHOR_SIGNATURE,
    RecordError,
    cited_files,
    make_envelope,
    record_hash,
    validate_record,
)
from attestrwa.registry import RegistryError, parse_registry
from attestrwa.rpc import JsonRpc, RpcError
from attestrwa.signing import generate_seed, public_key_from_seed, sign_hash
from attestrwa.verify import FAIL, GROUPS, PASS, Report, verify

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

SIGNING_KEY_ENV = "ATTESTRWA_SIGNING_KEY"
# A file larger than this is not read as a cited document.
MAX_DOCUMENT_BYTES = 256 * 1024 * 1024

_MARK = {PASS: "✓", FAIL: "✗"}
_MARK_ASCII = {PASS: "ok  ", FAIL: "FAIL"}
_HEX_KEY_RE = re.compile(r"(0x)?[0-9a-fA-F]{64}")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


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


def _read_document(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise UsageError(f"{path}: larger than {MAX_DOCUMENT_BYTES // 2**20} MB")
        return path.read_bytes()
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc


def _collect_documents(args: argparse.Namespace, body: Any) -> list[tuple[str, bytes]] | None:
    """Files named with --document, plus the cited ones found in --document-dir.

    A file named explicitly must be one the record cites. A directory is only
    searched: files in it that the record does not cite are ignored.
    """
    if not args.document and not args.document_dir:
        return None
    documents = [(name, _read_document(Path(name))) for name in args.document or []]
    if args.document_dir:
        try:
            validate_record(body)
            wanted = set(cited_files(body))
        except RecordError:
            wanted = set()  # the report will say what is wrong with the record
        for directory in args.document_dir:
            root = Path(directory)
            try:
                if not root.is_dir():
                    raise UsageError(f"{directory} is not a directory")
                candidates = [
                    path
                    for path in sorted(root.iterdir())
                    if path.is_file() and path.stat().st_size <= MAX_DOCUMENT_BYTES
                ]
            except OSError as exc:
                raise UsageError(f"cannot read the directory {directory}: {exc}") from exc
            for candidate in candidates:
                content = _read_document(candidate)
                if to_hex(sha256(content)) in wanted:
                    documents.append((str(candidate), content))
    return documents


def _parse_public_key(value: str) -> str:
    if not _HEX_KEY_RE.fullmatch(value):
        raise UsageError("--public-key must be 32 bytes of hex")
    value = value.lower()
    return value if value.startswith("0x") else "0x" + value


def _read_seed(args: argparse.Namespace) -> bytes:
    """The signing key from --key-file or the environment. Never echoed."""
    if args.key_file:
        try:
            text = Path(args.key_file).read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as exc:
            raise UsageError(f"cannot read the key file {args.key_file}") from exc
        origin = args.key_file
    else:
        text = os.environ.get(SIGNING_KEY_ENV, "")
        origin = f"${SIGNING_KEY_ENV}"
        if not text:
            raise UsageError(f"give --key-file, or set {SIGNING_KEY_ENV}")
    text = text.strip()
    if not _HEX_KEY_RE.fullmatch(text):
        raise UsageError(f"{origin} does not hold a signing key (32 bytes of hex)")
    return bytes.fromhex(text.removeprefix("0x").removeprefix("0X"))


def _can_encode(text: str) -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def _plain(text: Any) -> str:
    """Text from a record, made safe to print on a terminal."""
    return _CONTROL_RE.sub("?", str(text))


def _print_report(report: Report, source: str) -> None:
    unicode_ok = _can_encode("✓✗–…")
    marks = _MARK if unicode_ok else _MARK_ASCII
    skip_mark = "–" if unicode_ok else "skip"
    summary = report.summary
    print(f"AttestRWA decision record: {source}")
    if summary:
        if "case_id" in summary:
            print(f"  case      {_plain(summary['case_id'])}: {_plain(summary.get('title'))}")
        else:
            print(f"  deal      {summary.get('deal_id')}")
            print(f"  escrow    {summary.get('escrow')} on chain {summary.get('chain_id')}")
        print(
            f"  decision  {str(summary.get('decision', '')).upper()} "
            f"under {_plain(summary.get('policy'))}"
        )
        if summary.get("attestation_uid"):
            print(f"  anchor    EAS attestation {summary['attestation_uid']}")
        if summary.get("signer"):
            print(f"  anchor    Ed25519 signature, key {summary['signer']}")
    for group in GROUPS:
        checks = [check for check in report.checks if check.group == group]
        if not checks:
            continue
        print(f"\n{group}")
        width = max(len(check.id) for check in checks)
        for check in checks:
            mark = marks.get(check.status, skip_mark)
            detail = _plain(check.detail)
            if not unicode_ok:
                detail = detail.replace("…", "...").encode("ascii", "replace").decode("ascii")
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
        policy_member = body.get("policy")
        wanted = policy_member.get("sha256") if isinstance(policy_member, dict) else None
        policy_path = (
            _find_policy(args.policy_dir, wanted) if isinstance(wanted, str) and wanted else None
        )
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
        documents=_collect_documents(args, body),
        public_key=_parse_public_key(args.public_key) if args.public_key else None,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report(report, args.record)
    return EXIT_OK if report.ok else EXIT_FAILED


def _valid_body(path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """A file's record body, validated, and the envelope around it (if any)."""
    doc = _load_json(path)
    envelope = doc if isinstance(doc, dict) and "record" in doc else {}
    body = envelope["record"] if envelope else doc
    try:
        validate_record(body)
    except RecordError as exc:
        raise UsageError(str(exc)) from exc
    return body, envelope


def _cmd_hash(args: argparse.Namespace) -> int:
    body, _ = _valid_body(args.record)
    print(to_hex(record_hash(body)))
    return EXIT_OK


def _cmd_keygen(args: argparse.Namespace) -> int:
    seed = generate_seed()
    try:
        # Created, never overwritten, readable by the owner only.
        descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise UsageError(f"{args.out} already exists; a key file is never overwritten") from exc
    except OSError as exc:
        raise UsageError(f"cannot create {args.out}: {exc}") from exc
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(seed.hex() + "\n")
    print(to_hex(public_key_from_seed(seed)))
    print(
        f"The signing key is in {args.out} (owner-only). Keep it out of version control. "
        "What was printed on standard output is the public key: publish it, and put it "
        "into the records this key signs.",
        file=sys.stderr,
    )
    return EXIT_OK


def _cmd_public_key(args: argparse.Namespace) -> int:
    print(to_hex(public_key_from_seed(_read_seed(args))))
    return EXIT_OK


def _cmd_sign(args: argparse.Namespace) -> int:
    body, envelope = _valid_body(args.record)
    if body["anchor"]["kind"] != ANCHOR_SIGNATURE:
        raise UsageError(
            "this record is anchored by an EAS attestation, not by a signature; "
            "only a case record is signed"
        )
    # A signature is a commitment: refuse to commit to a record that would not verify.
    defects = [check for check in verify(body).checks if check.status == FAIL]
    if defects:
        raise UsageError(
            "refusing to sign a record that does not verify: "
            + "; ".join(f"{check.id}: {_plain(check.detail)}" for check in defects)
        )
    seed = _read_seed(args)
    if to_hex(public_key_from_seed(seed)) != body["attester"]["public_key"]:
        raise UsageError("the signing key is not the one this record names as its attester")
    links = envelope.get("links")
    signed = make_envelope(
        body,
        links=links if isinstance(links, dict) else None,
        signature=to_hex(sign_hash(seed, record_hash(body))),
    )
    text = json.dumps(signed, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        if args.key_file and _same_file(args.out, args.key_file):
            raise UsageError("--out names the key file; the signed record would replace the key")
        try:
            Path(args.out).write_text(text, encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"cannot write {args.out}: {exc}") from exc
        print(f"signed {signed['record_hash']} -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return EXIT_OK


def _same_file(first: str, second: str) -> bool:
    """Do two paths name one file, by any spelling, link or symlink?"""
    try:
        if os.path.exists(first) and os.path.exists(second):
            return os.path.samefile(first, second)
        return Path(first).resolve() == Path(second).resolve()
    except OSError:
        return True  # cannot tell: do not risk the key


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


def _add_key_source(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--key-file",
        help=f"file holding the signing key (default: the {SIGNING_KEY_ENV} environment variable)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="attestrwa",
        description="Decision records: verify why a decision was made, and sign your own.",
    )
    parser.add_argument("--version", action="version", version=f"attestrwa {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    verify_cmd = commands.add_parser(
        "verify",
        help="check a decision record against its anchor and replay its rules",
    )
    verify_cmd.add_argument("record", help="record file (envelope or bare record), or - for stdin")
    verify_cmd.add_argument("--policy", help="policy pack file the record claims to apply")
    verify_cmd.add_argument(
        "--policy-dir", help="directory to search for the policy pack by its sha256"
    )
    verify_cmd.add_argument(
        "--strict", action="store_true", help="treat skipped checks as failures"
    )
    verify_cmd.add_argument("--json", action="store_true", help="print the report as JSON")

    onchain = verify_cmd.add_argument_group("escrowed deals (EAS attestation)")
    onchain.add_argument("--rpc", help="JSON-RPC endpoint of the chain the record is about")
    onchain.add_argument("--uid", help="EAS attestation UID (default: the one in the file)")
    onchain.add_argument("--registry", help="payee registry file the record refers to")
    onchain.add_argument(
        "--recheck-inputs",
        action="store_true",
        help="re-run recorded on-chain calls at their recorded blocks",
    )
    onchain.add_argument("--offline", action="store_true", help="do not contact any RPC endpoint")
    onchain.add_argument("--timeout", type=float, default=20.0, help="RPC timeout in seconds")

    signed = verify_cmd.add_argument_group("cases (signature, format 0.2)")
    signed.add_argument(
        "--public-key", help="the Ed25519 public key you trust to have signed the record"
    )
    signed.add_argument(
        "--document",
        action="append",
        metavar="FILE",
        help="a file the record must cite by hash: a document, a prompt, a model output "
        "(repeatable)",
    )
    signed.add_argument(
        "--document-dir",
        action="append",
        metavar="DIR",
        help="directory to search for the files the record cites (repeatable, not recursive)",
    )
    verify_cmd.set_defaults(handler=_cmd_verify)

    hash_cmd = commands.add_parser("hash", help="print the hash of a record")
    hash_cmd.add_argument("record")
    hash_cmd.set_defaults(handler=_cmd_hash)

    sign_cmd = commands.add_parser("sign", help="sign a case record (format 0.2) with Ed25519")
    sign_cmd.add_argument("record", help="record file (envelope or bare record), or - for stdin")
    _add_key_source(sign_cmd)
    sign_cmd.add_argument("--out", help="write the signed record here (default: stdout)")
    sign_cmd.set_defaults(handler=_cmd_sign)

    keygen_cmd = commands.add_parser("keygen", help="create an Ed25519 signing key")
    keygen_cmd.add_argument("--out", required=True, help="file to create for the signing key")
    keygen_cmd.set_defaults(handler=_cmd_keygen)

    public_cmd = commands.add_parser("public-key", help="print the public key of a signing key")
    _add_key_source(public_cmd)
    public_cmd.set_defaults(handler=_cmd_public_key)

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
