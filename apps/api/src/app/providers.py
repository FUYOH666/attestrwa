"""Turn a policy's input declarations into recorded inputs.

Each input is fetched from the kind of source the policy names, and the
source is written into the record next to the value. A value the policy
expects from the chain or a registry can never be taken from the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from attestrwa.hashing import to_hex
from attestrwa.policy import InputSpec, PolicyPack
from attestrwa.record import RecordError, expected_onchain_value, expected_subject_value
from attestrwa.registry import Registry
from attestrwa.rpc import RpcError, calldata

from app.chain import Rpc
from app.errors import ConfigError, InputError, UpstreamError

_PARTIES = ("buyer", "payee")


def _party(spec: InputSpec, subject: Mapping[str, Any]) -> str:
    party = spec.params.get("of")
    if party not in _PARTIES:
        raise ConfigError(f"policy input {spec.name!r}: 'of' must be one of {', '.join(_PARTIES)}")
    return subject[party]


def _subject_input(spec: InputSpec, subject: Mapping[str, Any]) -> dict[str, Any]:
    field = spec.params.get("field")
    if field not in subject:
        raise ConfigError(f"policy input {spec.name!r}: unknown subject field {field!r}")
    try:
        value = expected_subject_value(subject, field, spec.type)
    except RecordError as exc:
        raise ConfigError(f"policy input {spec.name!r}: {exc}") from exc
    return {
        "name": spec.name,
        "type": spec.type,
        "value": value,
        "source": {"kind": "subject", "field": field},
    }


def _sanctions_input(
    spec: InputSpec,
    subject: Mapping[str, Any],
    rpc: Rpc,
    oracle: str,
    block_number: int,
) -> dict[str, Any]:
    if spec.type != "bool":
        raise ConfigError(f"policy input {spec.name!r}: the sanctions oracle returns a bool")
    address = _party(spec, subject)
    data = calldata("isSanctioned(address)", address)
    try:
        result = rpc.eth_call(oracle, data, block_number)
        value = expected_onchain_value(to_hex(result), spec.type)
    except (RpcError, RecordError) as exc:
        # Fail closed: an unreadable screening source never becomes "not sanctioned".
        raise UpstreamError(f"sanctions oracle read failed for {spec.name!r}: {exc}") from exc
    return {
        "name": spec.name,
        "type": spec.type,
        "value": value,
        "source": {
            "kind": "onchain",
            "chain_id": subject["chain_id"],
            "to": oracle,
            "call": "isSanctioned(address)",
            "data": to_hex(data),
            "block_number": block_number,
            "result": to_hex(result),
        },
    }


def _registry_input(
    spec: InputSpec, subject: Mapping[str, Any], registry: Registry, registry_ref: str
) -> dict[str, Any]:
    if spec.type != "bool":
        raise ConfigError(f"policy input {spec.name!r}: registry membership is a bool")
    key = _party(spec, subject)
    return {
        "name": spec.name,
        "type": spec.type,
        "value": registry.contains(key),
        "source": {"kind": "registry", "ref": registry_ref, "sha256": registry.sha256, "key": key},
    }


def _declared_input(spec: InputSpec, declared: Mapping[str, Any], by: str) -> dict[str, Any]:
    if spec.name not in declared:
        raise InputError(f"the policy needs a declared value for {spec.name!r}")
    raw = declared[spec.name]
    if spec.type == "bool" and type(raw) is bool:
        value: Any = raw
    elif spec.type == "int" and type(raw) is int:
        value = str(raw)
    elif spec.type == "string" and isinstance(raw, str) and raw:
        value = raw
    else:
        raise InputError(f"declared value for {spec.name!r} must be a {spec.type}")
    return {
        "name": spec.name,
        "type": spec.type,
        "value": value,
        "source": {"kind": "declared", "by": by},
    }


def resolve_inputs(
    *,
    pack: PolicyPack,
    subject: Mapping[str, Any],
    block_number: int,
    declared: Mapping[str, Any],
    declared_by: str,
    rpc: Rpc,
    oracle: str,
    registry: Registry,
    registry_ref: str,
) -> list[dict[str, Any]]:
    """Fetch every input the policy declares, in policy order."""
    declarable = {spec.name for spec in pack.inputs if spec.source == "declared"}
    refused = sorted(set(declared) - declarable)
    if refused:
        raise InputError(
            f"{', '.join(refused)} cannot be declared by the caller under policy "
            f"{pack.pack_id}@{pack.version}"
        )

    inputs: list[dict[str, Any]] = []
    for spec in pack.inputs:
        provider = spec.params.get("provider")
        if spec.source == "subject":
            inputs.append(_subject_input(spec, subject))
        elif spec.source == "onchain" and provider == "sanctions_oracle":
            inputs.append(_sanctions_input(spec, subject, rpc, oracle, block_number))
        elif spec.source == "registry" and provider == "payee_registry":
            inputs.append(_registry_input(spec, subject, registry, registry_ref))
        elif spec.source == "declared":
            inputs.append(_declared_input(spec, declared, declared_by))
        else:
            raise ConfigError(
                f"policy input {spec.name!r}: this attester has no "
                f"{spec.source} provider named {provider!r}"
            )
    return inputs
