import {parseAbi, parseAbiParameters} from "viem";

export const escrowAbi = parseAbi([
  "function deposit(bytes32 salt, address payee, address token, uint256 amount, uint64 deadline) returns (bytes32)",
  "function release(bytes32 dealId, bytes32 attestationUid)",
  "function refund(bytes32 dealId, bytes32 attestationUid)",
  "function computeDealId(address buyer, bytes32 salt) view returns (bytes32)",
  "function getDeal(bytes32 dealId) view returns ((address buyer, uint64 deadline, uint8 status, address payee, uint64 depositedAt, address token, uint256 amount))",
  "function eas() view returns (address)",
  "function schemaUid() view returns (bytes32)",
  "function trustedAttesters(address attester) view returns (bool)",
]);

export const tokenAbi = parseAbi([
  "function mint(address to, uint256 amount)",
  "function approve(address spender, uint256 amount) returns (bool)",
  "function balanceOf(address owner) view returns (uint256)",
]);

export const easAbi = parseAbi([
  "function getAttestation(bytes32 uid) view returns ((bytes32 uid, bytes32 schema, uint64 time, uint64 expirationTime, uint64 revocationTime, bytes32 refUID, address recipient, address attester, bool revocable, bytes data))",
]);

// spec/eas-schema.txt
export const decisionParameters = parseAbiParameters(
  "bytes32 dealId, address payee, address token, uint256 amount, uint8 decision, bytes32 policyHash, bytes32 recordHash",
);

export const SCHEMA_UID = "0x1a86145e70ac5055683604a56201574b2c9edf0512ad08fc1368a9e7cb565135";
export const DEAL_STATUS = ["none", "open", "released", "refunded"] as const;
