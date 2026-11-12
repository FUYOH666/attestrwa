"""AttestRWA: decision records for compliance-gated settlement.

Public surface:

- :mod:`attestrwa.canonical` — canonical JSON (strict RFC 8785 subset)
- :mod:`attestrwa.policy`    — policy packs and the rule language
- :mod:`attestrwa.record`    — Decision Record v0.1: build, validate, hash
- :mod:`attestrwa.eas`       — the ``SettlementDecision`` EAS schema
- :mod:`attestrwa.verify`    — independent verification of a record
"""

__version__ = "2.0.0"

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
    RecordError,
    build_record,
    make_envelope,
    record_hash,
    validate_record,
)
from attestrwa.verify import Report, verify

__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DECISION_SCHEMA",
    "SPEC_ID",
    "CanonicalError",
    "DSLError",
    "DecisionData",
    "PolicyEvaluation",
    "PolicyPack",
    "RecordError",
    "Report",
    "Rule",
    "RuleResult",
    "__version__",
    "build_record",
    "canonicalize",
    "decode_decision",
    "encode_decision",
    "evaluate_all",
    "evaluate_rule",
    "load_policy",
    "loads_strict",
    "make_envelope",
    "parse_policy",
    "record_hash",
    "schema_uid",
    "validate_record",
    "verify",
]
