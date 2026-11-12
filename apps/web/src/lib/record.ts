// Decision Record v0.1 types and the checks a browser can make on its own:
// recompute the hash, read the attestation and the escrow, compare. Rule
// replay is left to the reference verifier (`attestrwa verify`).

import {
  type Address,
  type Hex,
  type PublicClient,
  decodeAbiParameters,
  keccak256,
  size,
  stringToBytes,
} from "viem";

import {DEAL_STATUS, SCHEMA_UID, decisionParameters, easAbi, escrowAbi} from "./abi";
import {CanonicalError, canonicalize} from "./canonical";

export const SPEC_ID = "attestrwa.decision-record/0.1";

export type RecordInput = {
  name: string;
  type: "bool" | "int" | "string";
  value: boolean | string;
  source: {kind: string; [key: string]: unknown};
};

export type RecordBody = {
  spec: string;
  nonce: string;
  supersedes: string | null;
  subject: {
    kind: string;
    chain_id: number;
    escrow: Address;
    deal_id: Hex;
    buyer: Address;
    payee: Address;
    token: Address;
    amount: string;
    deadline: number;
    deposited_at: number;
  };
  evaluation: {block_number: number; evaluated_at: number};
  policy: {pack_id: string; version: string; sha256: Hex; uri: string};
  inputs: RecordInput[];
  rules: {id: string; expression: string; result: boolean}[];
  decision: {outcome: "approve" | "reject"; code: number; failed_rules: string[]};
  attester: {address: Address; software: string};
  anchor: {kind: string; chain_id: number; eas: Address; schema_uid: Hex};
};

export type Envelope = {
  record: RecordBody;
  record_hash: Hex;
  network?: string;
  attestation?: {uid: Hex; tx_hash?: Hex} | null;
  links?: Record<string, string>;
};

export type Check = {id: string; group: string; status: "pass" | "fail" | "skip"; detail: string};

export function recordHash(body: RecordBody): Hex {
  return keccak256(stringToBytes(canonicalize(body)));
}

const short = (value: string) => (value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value);
const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

/** The subset of `attestrwa verify` a browser can run without trusting any server. */
export async function verifyInBrowser(envelope: Envelope, client: PublicClient): Promise<Check[]> {
  const checks: Check[] = [];
  const add = (id: string, group: string, ok: boolean, pass: string, fail: string) =>
    checks.push({id, group, status: ok ? "pass" : "fail", detail: ok ? pass : fail});

  const body = envelope?.record;
  if (!body || body.spec !== SPEC_ID || !body.subject || !body.anchor || !body.decision) {
    add("record.structure", "Record", false, "", `not a Decision Record v0.1 (${SPEC_ID})`);
    return checks;
  }
  add("record.structure", "Record", true, "Decision Record v0.1", "");

  let computed: Hex;
  try {
    computed = recordHash(body);
  } catch (error) {
    const reason = error instanceof CanonicalError ? error.message : String(error);
    add("record.hash", "Record", false, "", `cannot canonicalise the record: ${reason}`);
    return checks;
  }
  add(
    "record.hash",
    "Record",
    !envelope.record_hash || same(envelope.record_hash, computed),
    `record hash ${computed}`,
    `the file states ${short(envelope.record_hash ?? "")} but the record hashes to ${short(computed)}`,
  );

  const failed = body.rules.filter((rule) => !rule.result).map((rule) => rule.id);
  const outcome = failed.length ? "reject" : "approve";
  add(
    "record.decision",
    "Record",
    body.decision.outcome === outcome && body.decision.failed_rules.join() === failed.join(),
    `decision ${outcome.toUpperCase()} is consistent with the recorded rule results`,
    `rule results give ${outcome} but the record says ${body.decision.outcome}`,
  );
  checks.push({
    id: "record.replay",
    group: "Record",
    status: "skip",
    detail: "rules are not re-evaluated in the browser; use the command below",
  });

  const uid = envelope.attestation?.uid;
  if (!uid) {
    add("attestation.exists", "On-chain", false, "", "the file names no attestation UID");
    return checks;
  }
  const chainId = await client.getChainId();
  add(
    "chain.network",
    "On-chain",
    chainId === body.subject.chain_id,
    `RPC serves chain ${chainId}`,
    `the RPC serves chain ${chainId}, the record is about chain ${body.subject.chain_id}`,
  );
  if (chainId !== body.subject.chain_id) return checks;

  const attestation = await client.readContract({
    address: body.anchor.eas,
    abi: easAbi,
    functionName: "getAttestation",
    args: [uid],
  });
  const exists = BigInt(attestation.uid) !== 0n;
  add("attestation.exists", "On-chain", exists, `attestation ${short(uid)} found`, `no attestation ${short(uid)} on this chain`);
  if (!exists) return checks;

  add(
    "attestation.schema",
    "On-chain",
    same(attestation.schema, SCHEMA_UID) && same(body.anchor.schema_uid, SCHEMA_UID),
    "schema is SettlementDecision",
    `attestation uses schema ${short(attestation.schema)}`,
  );
  if (size(attestation.data) !== 224) {
    add("attestation.data", "On-chain", false, "", "attestation data is not a SettlementDecision");
    return checks;
  }
  const [dealId, payee, token, amount, decision, policyHash, onchainHash] = decodeAbiParameters(
    decisionParameters,
    attestation.data,
  );
  add(
    "attestation.record_hash",
    "On-chain",
    same(onchainHash, computed),
    "the attestation commits to exactly this record",
    `the attestation commits to ${short(onchainHash)}, this record hashes to ${short(computed)}`,
  );
  add(
    "attestation.policy_hash",
    "On-chain",
    same(policyHash, body.policy.sha256),
    "on-chain policy hash matches the record",
    `on-chain policy hash is ${short(policyHash)}`,
  );
  add(
    "attestation.deal",
    "On-chain",
    same(dealId, body.subject.deal_id) &&
      same(payee, body.subject.payee) &&
      same(token, body.subject.token) &&
      amount.toString() === body.subject.amount,
    "deal id, payee, token and amount match the record",
    "the attestation and the record describe different deals",
  );
  add(
    "attestation.decision",
    "On-chain",
    decision === body.decision.code,
    `on-chain decision is ${body.decision.outcome.toUpperCase()}`,
    `on-chain decision code is ${decision}, the record says ${body.decision.code}`,
  );
  add(
    "attestation.recipient",
    "On-chain",
    same(attestation.recipient, body.subject.escrow),
    "attestation is addressed to this escrow",
    `attestation is addressed to ${attestation.recipient}`,
  );
  add(
    "attestation.attester",
    "On-chain",
    same(attestation.attester, body.attester.address),
    `attested by ${attestation.attester.toLowerCase()}`,
    `attested by ${attestation.attester}, the record names ${body.attester.address}`,
  );
  add(
    "attestation.not_revoked",
    "On-chain",
    attestation.revocationTime === 0n,
    "not revoked",
    `the attester revoked this decision at ${attestation.revocationTime}`,
  );

  const escrow = body.subject.escrow;
  const [deal, escrowEas, escrowSchema, trusted] = await Promise.all([
    client.readContract({address: escrow, abi: escrowAbi, functionName: "getDeal", args: [body.subject.deal_id]}),
    client.readContract({address: escrow, abi: escrowAbi, functionName: "eas"}),
    client.readContract({address: escrow, abi: escrowAbi, functionName: "schemaUid"}),
    client.readContract({address: escrow, abi: escrowAbi, functionName: "trustedAttesters", args: [attestation.attester]}),
  ]);
  add(
    "escrow.config",
    "On-chain",
    same(escrowEas, body.anchor.eas) && same(escrowSchema, body.anchor.schema_uid),
    "escrow reads the same EAS contract and schema",
    "the escrow is wired to another EAS contract or schema",
  );
  add(
    "escrow.deal",
    "On-chain",
    deal.status !== 0 &&
      same(deal.buyer, body.subject.buyer) &&
      same(deal.payee, body.subject.payee) &&
      same(deal.token, body.subject.token) &&
      deal.amount.toString() === body.subject.amount &&
      Number(deal.deadline) === body.subject.deadline &&
      Number(deal.depositedAt) === body.subject.deposited_at,
    `the escrow holds this exact deal (now ${DEAL_STATUS[deal.status] ?? "unknown"})`,
    deal.status === 0 ? "the escrow has no such deal" : "the escrow's deal differs from the record",
  );
  add(
    "escrow.attester_trusted",
    "On-chain",
    trusted,
    "the escrow trusts this attester",
    "the escrow does not (or no longer) trust this attester",
  );
  return checks;
}

export function cliCommand(file: string, rpcUrl: string): string {
  return (
    `uvx --from "git+https://github.com/FUYOH666/attestrwa#subdirectory=packages/attestrwa" \\\n` +
    `  attestrwa verify ${file} --rpc ${rpcUrl} \\\n` +
    `  --policy data/policies/settlement-demo-v2.yaml --registry data/registry/payees.json --recheck-inputs`
  );
}
