"""AttestRWA: decision records — why a decision was made, provable afterwards.

Public surface:

- :mod:`attestrwa.canonical` — canonical JSON (strict RFC 8785 subset)
- :mod:`attestrwa.policy`    — policy packs and the rule language
- :mod:`attestrwa.record`    — Decision Record v0.1 and v0.2: build, validate, hash
- :mod:`attestrwa.eas`       — the ``SettlementDecision`` EAS schema (escrowed deals)
- :mod:`attestrwa.signing`   — Ed25519 signatures over record hashes (cases)
- :mod:`attestrwa.verify`    — independent verification of a record
"""

__version__ = "2.1.0"

from attestrwa.canonical import CanonicalError, canonicalize, loads_strict
from attestrwa.eas import (
    DECISION_APPROVE,
    DECISION_REJECT,
    DECISION_SCHEMA,
    DecisionData,
    decode_decision,
    encode_decision,
    schema_uid,
)
from attestrwa.policy import (
    DSLError,
    PolicyEvaluation,
    PolicyPack,
    Rule,
    RuleResult,
    evaluate_all,
    evaluate_rule,
    load_policy,
    parse_policy,
)
from attestrwa.record import (
    SPEC_ID,
    SPEC_V01,
    SPEC_V02,
    RecordError,
    build_case_record,
    build_record,
    cited_files,
    make_envelope,
    record_hash,
    validate_record,
)
from attestrwa.signing import (
    SigningError,
    generate_seed,
    public_key_from_seed,
    sign_hash,
    verify_signature,
)
from attestrwa.verify import Report, verify

__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DECISION_SCHEMA",
    "SPEC_ID",
    "SPEC_V01",
    "SPEC_V02",
    "CanonicalError",
    "DSLError",
    "DecisionData",
    "PolicyEvaluation",
    "PolicyPack",
    "RecordError",
    "Report",
    "Rule",
    "RuleResult",
    "SigningError",
    "__version__",
    "build_case_record",
    "build_record",
    "canonicalize",
    "cited_files",
    "decode_decision",
    "encode_decision",
    "evaluate_all",
    "evaluate_rule",
    "generate_seed",
    "load_policy",
    "loads_strict",
    "make_envelope",
    "parse_policy",
    "public_key_from_seed",
    "record_hash",
    "schema_uid",
    "sign_hash",
    "validate_record",
    "verify",
    "verify_signature",
]
