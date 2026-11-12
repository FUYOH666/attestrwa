import json

import pytest

from attestrwa import __version__
from attestrwa.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main

from .conftest import POLICY_FILE, REGISTRY_FILE, clone


@pytest.fixture
def record_file(tmp_path, approve_envelope):
    path = tmp_path / "record.json"
    path.write_text(json.dumps(approve_envelope), encoding="utf-8")
    return path


def test_verify_offline_exits_zero_and_prints_a_report(record_file, capsys) -> None:
    code = main(
        [
            "verify",
            str(record_file),
            "--offline",
            "--policy",
            str(POLICY_FILE),
            "--registry",
            str(REGISTRY_FILE),
        ]
    )
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "Result: CONSISTENT (not checked against the chain)" in out
    assert "record.replay" in out and "policy.match" in out and "registry.match" in out
    assert "APPROVE under settlement-demo@2.0.0" in out


def test_verify_finds_the_policy_by_hash_in_a_directory(record_file, capsys) -> None:
    code = main(["verify", str(record_file), "--policy-dir", str(POLICY_FILE.parent), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    statuses = {check["id"]: check["status"] for check in report["checks"]}
    assert statuses["policy.match"] == "pass"


def test_verify_exits_one_on_a_tampered_record(tmp_path, approve_envelope, capsys) -> None:
    tampered = clone(approve_envelope)
    tampered["record"]["subject"]["amount"] = "1"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    assert main(["verify", str(path), "--offline"]) == EXIT_FAILED
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_strict_offline_verification_fails_because_checks_were_skipped(record_file, capsys):
    assert main(["verify", str(record_file), "--offline", "--strict"]) == EXIT_FAILED
    assert "strict mode" in capsys.readouterr().out


def test_json_report_is_machine_readable(record_file, capsys) -> None:
    assert main(["verify", str(record_file), "--offline", "--json"]) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True and report["record_hash"].startswith("0x")


@pytest.mark.parametrize(
    "content",
    ["{not json", '{"record": {"a": 1, "a": 2}}', '{"record": {"amount": 1.5}}'],
)
def test_unreadable_record_is_a_usage_error(tmp_path, content, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    assert main(["verify", str(path), "--offline"]) == EXIT_USAGE
    assert "attestrwa:" in capsys.readouterr().err


def test_missing_files_are_usage_errors(record_file, tmp_path) -> None:
    missing = str(tmp_path / "nope")
    assert main(["verify", missing, "--offline"]) == EXIT_USAGE
    assert main(["verify", str(record_file), "--offline", "--policy", missing]) == EXIT_USAGE
    assert main(["verify", str(record_file), "--offline", "--registry", missing]) == EXIT_USAGE


def test_unreachable_rpc_is_reported_not_raised(record_file, capsys) -> None:
    code = main(["verify", str(record_file), "--rpc", "http://127.0.0.1:9", "--timeout", "1"])
    assert code == EXIT_USAGE
    assert "RPC error" in capsys.readouterr().err


def test_non_http_rpc_url_is_refused(record_file, capsys) -> None:
    assert main(["verify", str(record_file), "--rpc", "file:///etc/passwd"]) == EXIT_USAGE


def test_hash_prints_the_record_hash(record_file, approve_envelope, capsys) -> None:
    assert main(["hash", str(record_file)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == approve_envelope["record_hash"]


def test_schema_commands(capsys) -> None:
    assert main(["schema-uid"]) == EXIT_OK
    uid = capsys.readouterr().out.strip()
    assert uid == "0x1a86145e70ac5055683604a56201574b2c9edf0512ad08fc1368a9e7cb565135"
    assert main(["schema"]) == EXIT_OK
    assert capsys.readouterr().out.startswith("bytes32 dealId, address payee")


def test_policy_hash_command(capsys) -> None:
    assert main(["policy-hash", str(POLICY_FILE)]) == EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("0x") and "settlement-demo@2.0.0" in out


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out
