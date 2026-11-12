// Check the browser canonicaliser against the published test vectors.
// Run with: node scripts/check-vectors.mts   (Node >= 22.18 strips the types)
import {readFileSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

import {keccak256, stringToBytes} from "viem";

import {canonicalize} from "../src/lib/canonical.ts";

const vectors = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "spec", "test-vectors");
let failures = 0;
let checked = 0;

const canonical = JSON.parse(readFileSync(join(vectors, "canonical.json"), "utf8"));
for (const vector of canonical.vectors) {
  checked += 1;
  const text = canonicalize(vector.value);
  if (text !== vector.canonical || keccak256(stringToBytes(text)) !== vector.keccak256) {
    failures += 1;
    console.error(`canonical vector failed: ${vector.name}`);
  }
}

for (const file of ["record-approve.json", "record-reject.json"]) {
  checked += 1;
  const envelope = JSON.parse(readFileSync(join(vectors, file), "utf8"));
  const hash = keccak256(stringToBytes(canonicalize(envelope.record)));
  if (hash !== envelope.record_hash) {
    failures += 1;
    console.error(`record vector failed: ${file}`);
  }
}

for (const bad of [1.5, {Upper: 1}, {n: 2 ** 53}, {s: "\ud800"}]) {
  checked += 1;
  try {
    canonicalize(bad);
    failures += 1;
    console.error(`value outside the subset was accepted: ${JSON.stringify(bad)}`);
  } catch {
    // expected
  }
}

if (failures) {
  console.error(`${failures} of ${checked} vector checks failed`);
  process.exit(1);
}
console.log(`${checked} vector checks passed`);
