"""Command line for signed case records: keygen, public-key, sign, verify."""

import json
import os
import stat

import pytest

from attestrwa.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, SIGNING_KEY_ENV, main

from .conftest import (
    CASE_POLICY,
    CASE_PUBLIC_KEY,
    CASE_SEED,
    OTHER_PUBLIC_KEY,
    OTHER_SEED,
    case_files,
    sign_case,
)


@pytest.fixture(autouse=True)
def no_key_in_the_environment(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)


@pytest.fixture
def workdir(tmp_path, case_body):
    """A record, its policy, its files and its signing key, on disk."""
    (tmp_path / "policy.yaml").write_bytes(CASE_POLICY)
    (tmp_path / "unsigned.json").write_text(json.dumps(case_body), encoding="utf-8")
    (tmp_path / "signed.json").write_text(json.dumps(sign_case(case_body)), encoding="utf-8")
    (tmp_path / "key").write_text(CASE_SEED.hex() + "\n", encoding="ascii")
    (tmp_path / "other-key").write_text("0x" + OTHER_SEED.hex(), encoding="ascii")
    files = tmp_path / "files"
    files.mkdir()
    for name, content in case_files().items():
        (files / name).write_bytes(content)
    return tmp_path


def verify_args(workdir, record="signed.json"):
    return [
        "verify",
        str(workdir / record),
        "--policy",
        str(workdir / "policy.yaml"),
        "--public-key",
        CASE_PUBLIC_KEY,
        "--strict",
    ]


def test_keygen_writes_an_owner_only_key_and_prints_only_the_public_half(tmp_path, capsys):
    path = tmp_path / "signing.key"
    assert main(["keygen", "--out", str(path)]) == EXIT_OK
    captured = capsys.readouterr()
    seed = path.read_text(encoding="ascii").strip()
    assert len(seed) == 64
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert captured.out.strip().startswith("0x") and len(captured.out.strip()) == 66
    assert seed not in captured.out and seed not in captured.err

    assert main(["public-key", "--key-file", str(path)]) == EXIT_OK
    assert capsys.readouterr().out == captured.out


def test_keygen_never_overwrites_a_key(tmp_path, capsys) -> None:
    path = tmp_path / "signing.key"
    path.write_text("precious\n", encoding="ascii")
    assert main(["keygen", "--out", str(path)]) == EXIT_USAGE
    assert path.read_text(encoding="ascii") == "precious\n"
    assert "never overwritten" in capsys.readouterr().err


def test_public_key_reads_the_key_from_the_environment(monkeypatch, capsys) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, CASE_SEED.hex())
    assert main(["public-key"]) == EXIT_OK
    assert capsys.readouterr().out.strip() == CASE_PUBLIC_KEY


def test_sign_then_verify(workdir, capsys) -> None:
    out = workdir / "out.json"
    code = main(
        ["sign", str(workdir / "unsigned.json"), "--key-file", str(workdir / "key"), "--out"]
        + [str(out)]
    )
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert CASE_SEED.hex() not in captured.out + captured.err
    signed = json.loads(out.read_text(encoding="utf-8"))
    assert signed == json.loads((workdir / "signed.json").read_text(encoding="utf-8"))

    arguments = verify_args(workdir, "out.json") + ["--document-dir", str(workdir / "files")]
    assert main(arguments) == EXIT_OK
    report = capsys.readouterr().out
    assert "case      CASE-0001: Classification of a vacuum bottle" in report
    assert "anchor    Ed25519 signature, key " + CASE_PUBLIC_KEY in report
    assert "Result: VERIFIED: 10 passed, 0 failed, 0 skipped" in report


def test_sign_prints_to_stdout_and_keeps_the_links_of_an_envelope(workdir, capsys) -> None:
    envelope = json.loads((workdir / "signed.json").read_text(encoding="utf-8"))
    envelope["signature"] = None
    envelope["links"] = {"policy": "policy.yaml"}
    (workdir / "draft.json").write_text(json.dumps(envelope), encoding="utf-8")
    assert main(["sign", str(workdir / "draft.json"), "--key-file", str(workdir / "key")]) == 0
    signed = json.loads(capsys.readouterr().out)
    assert signed["links"] == {"policy": "policy.yaml"}
    assert signed["signature"]["scheme"] == "ed25519"


def test_sign_refuses_a_key_the_record_does_not_name(workdir, capsys) -> None:
    code = main(["sign", str(workdir / "unsigned.json"), "--key-file", str(workdir / "other-key")])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "not the one this record names" in captured.err
    assert OTHER_SEED.hex() not in captured.out + captured.err
    assert captured.out == ""


def test_sign_needs_a_key(workdir, capsys) -> None:
    assert main(["sign", str(workdir / "unsigned.json")]) == EXIT_USAGE
    assert SIGNING_KEY_ENV in capsys.readouterr().err


@pytest.mark.parametrize("content", ["", "hello", "0x1234", "zz" * 32, "ab" * 33])
def test_a_file_that_is_not_a_key_is_refused_without_being_echoed(workdir, capsys, content):
    (workdir / "bad-key").write_text(content, encoding="ascii")
    code = main(["sign", str(workdir / "unsigned.json"), "--key-file", str(workdir / "bad-key")])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "does not hold a signing key" in captured.err
    if content:
        assert content not in captured.err


def test_sign_refuses_an_escrowed_deal(tmp_path, approve_envelope, capsys) -> None:
    record = tmp_path / "deal.json"
    record.write_text(json.dumps(approve_envelope), encoding="utf-8")
    (tmp_path / "key").write_text(CASE_SEED.hex(), encoding="ascii")
    assert main(["sign", str(record), "--key-file", str(tmp_path / "key")]) == EXIT_USAGE
    assert "EAS attestation" in capsys.readouterr().err


def test_sign_refuses_an_invalid_record(workdir, capsys) -> None:
    (workdir / "broken.json").write_text('{"spec": "attestrwa.decision-record/0.2"}')
    code = main(["sign", str(workdir / "broken.json"), "--key-file", str(workdir / "key")])
    assert code == EXIT_USAGE


def test_verify_with_files_named_one_by_one(workdir, capsys) -> None:
    arguments = verify_args(workdir)
    for name in case_files():
        arguments += ["--document", str(workdir / "files" / name)]
    assert main(arguments) == EXIT_OK
    assert "all 5 cited file(s) supplied" in capsys.readouterr().out


def test_verify_fails_on_an_altered_file_named_explicitly(workdir, capsys) -> None:
    invoice = workdir / "files" / "invoice.txt"
    invoice.write_bytes(invoice.read_bytes().replace(b"18,400", b"8,400"))
    assert main(verify_args(workdir) + ["--document", str(invoice)]) == EXIT_FAILED
    out = capsys.readouterr().out
    assert "not cited by this record, or altered" in out
    assert "Result: NOT VERIFIED" in out


def test_a_directory_is_searched_and_other_files_in_it_are_ignored(workdir, capsys) -> None:
    (workdir / "files" / "README.md").write_text("not cited", encoding="utf-8")
    (workdir / "files" / "nested").mkdir()
    assert main(verify_args(workdir) + ["--document-dir", str(workdir / "files")]) == EXIT_OK
    assert "all 5 cited file(s) supplied" in capsys.readouterr().out


def test_a_file_missing_from_the_directory_fails_strict_verification(workdir, capsys) -> None:
    (workdir / "files" / "packing.txt").unlink()
    arguments = verify_args(workdir) + ["--document-dir", str(workdir / "files")]
    assert main(arguments) == EXIT_FAILED
    assert "not supplied: document packing.txt" in capsys.readouterr().out
    arguments.remove("--strict")
    assert main(arguments) == EXIT_OK


def test_verify_without_a_trusted_key_says_what_is_missing(workdir, capsys) -> None:
    assert main(["verify", str(workdir / "signed.json")]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Result: CONSISTENT AND SIGNED (signer not checked against a trusted key)" in out
    assert "--public-key" in out


def test_verify_with_another_trusted_key_fails(workdir, capsys) -> None:
    arguments = ["verify", str(workdir / "signed.json"), "--public-key", OTHER_PUBLIC_KEY[2:]]
    assert main(arguments) == EXIT_FAILED
    assert "signature.signer" in capsys.readouterr().out


def test_an_unsigned_record_verifies_as_unsigned(workdir, capsys) -> None:
    assert main(["verify", str(workdir / "unsigned.json")]) == EXIT_OK
    assert "Result: CONSISTENT (unsigned)" in capsys.readouterr().out


@pytest.mark.parametrize("key", ["0x1234", "not-a-key", "0x" + "zz" * 32])
def test_a_malformed_public_key_is_a_usage_error(workdir, capsys, key) -> None:
    assert main(["verify", str(workdir / "signed.json"), "--public-key", key]) == EXIT_USAGE


def test_unreadable_documents_are_usage_errors(workdir, capsys) -> None:
    record = str(workdir / "signed.json")
    assert main(["verify", record, "--document", str(workdir / "absent.txt")]) == EXIT_USAGE
    assert main(["verify", record, "--document-dir", str(workdir / "absent")]) == EXIT_USAGE


def test_json_report_of_a_case(workdir, capsys) -> None:
    arguments = verify_args(workdir) + ["--document-dir", str(workdir / "files"), "--json"]
    assert main(arguments) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "VERIFIED" and report["anchored"] is True
    assert report["summary"]["signer"] == CASE_PUBLIC_KEY


def test_hash_of_a_case_record(workdir, capsys) -> None:
    assert main(["hash", str(workdir / "unsigned.json")]) == EXIT_OK
    envelope = json.loads((workdir / "signed.json").read_text(encoding="utf-8"))
    assert capsys.readouterr().out.strip() == envelope["record_hash"]


def test_sign_refuses_a_record_whose_decision_does_not_follow(workdir, case_body, capsys) -> None:
    body = json.loads(json.dumps(case_body))
    body["rules"][0]["result"] = False
    (workdir / "inconsistent.json").write_text(json.dumps(body), encoding="utf-8")
    code = main(["sign", str(workdir / "inconsistent.json"), "--key-file", str(workdir / "key")])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "refusing to sign" in captured.err and "record.replay" in captured.err
    assert captured.out == ""


def test_a_directory_without_any_cited_file_is_reported_as_nothing_supplied(workdir, capsys):
    empty = workdir / "empty"
    empty.mkdir()
    (empty / "unrelated.txt").write_text("x", encoding="utf-8")
    arguments = ["verify", str(workdir / "signed.json"), "--document-dir", str(empty)]
    assert main(arguments) == EXIT_OK
    assert "none of the 5 cited file(s) was supplied" in capsys.readouterr().out


def test_sign_refuses_to_write_the_record_over_the_key(workdir, capsys) -> None:
    key = workdir / "key"
    before = key.read_text(encoding="ascii")
    link = workdir / "innocent-name.json"
    link.symlink_to(key)
    for out in (key, workdir / "." / "key", link):
        code = main(
            ["sign", str(workdir / "unsigned.json"), "--key-file", str(key), "--out"] + [str(out)]
        )
        assert code == EXIT_USAGE
        assert key.read_text(encoding="ascii") == before
    assert "would replace the key" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs file permissions")
def test_a_directory_that_cannot_be_listed_is_a_usage_error(workdir, capsys) -> None:
    locked = workdir / "locked"
    locked.mkdir()
    locked.chmod(0o300)
    try:
        code = main(["verify", str(workdir / "signed.json"), "--document-dir", str(locked)])
    finally:
        locked.chmod(0o700)
    assert code == EXIT_USAGE
    assert "cannot read the directory" in capsys.readouterr().err


def test_a_deeply_nested_file_is_a_usage_error_not_a_crash(tmp_path, capsys) -> None:
    path = tmp_path / "deep.json"
    path.write_text("[" * 100_000 + "0" + "]" * 100_000, encoding="ascii")
    for command in (["verify", str(path)], ["hash", str(path)], ["sign", str(path)]):
        assert main(command) == EXIT_USAGE
    assert "nested too deeply" in capsys.readouterr().err
