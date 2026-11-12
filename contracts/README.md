# Contracts

A [Foundry](https://book.getfoundry.sh) project.

| File | What |
|---|---|
| `src/SettlementEscrow.sol` | Reference consumer of decision records: holds a deposit and settles it on a `SettlementDecision` attestation. |
| `src/MockUSDC.sol` | A 6-decimal demo token anyone can mint. For local and testnet use only. |
| `script/Deploy.s.sol` | Registers the schema if needed, deploys the token (unless one is given) and the escrow. |
| `test/SettlementEscrow.t.sol` | Unit and fuzz tests against the real EAS and SchemaRegistry contracts. |
| `test/SettlementEscrow.invariants.t.sol` | Invariants under random deposits, decisions, settlements and time jumps. |
| `test/EscrowFixture.sol` | Shared setup: deploys EAS, registers the schema from `spec/eas-schema.txt`. |

Dependencies are not vendored. Install them at pinned versions:

```bash
./scripts/install-contract-deps.sh      # from the repository root
cd contracts
forge fmt --check && forge build && forge test
```

Static analysis, as in CI:

```bash
slither src/SettlementEscrow.sol \
  --solc-remaps "@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/ @eas/=lib/eas-contracts/contracts/ forge-std/=lib/forge-std/src/" \
  --filter-paths "lib/" --exclude-low --exclude-informational --fail-medium
```

What the escrow checks is described in [docs/ATTESTATION_SCHEMA.md](../docs/ATTESTATION_SCHEMA.md); what it guarantees and what it does not, in [docs/THREAT_MODEL.md](../docs/THREAT_MODEL.md).

The contracts have not been audited and must not be deployed to mainnet as they are.
