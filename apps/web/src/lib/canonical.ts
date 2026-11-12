// Canonical JSON for decision records: the strict RFC 8785 subset defined in
// spec/DECISION_RECORD_v0.1.md. Byte-for-byte equal to the Python reference
// (packages/attestrwa) for every value it accepts; scripts/check-vectors.ts
// proves that against the published test vectors.

const KEY = /^[a-z0-9_]+$/;

export class CanonicalError extends Error {}

export function canonicalize(value: unknown, path = "$"): string {
  if (value === null || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new CanonicalError(`${path}: only integers within ±(2^53−1) are allowed`);
    }
    return String(value);
  }
  if (typeof value === "string") {
    if (!value.isWellFormed()) throw new CanonicalError(`${path}: string is not valid Unicode`);
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return "[" + value.map((item, i) => canonicalize(item, `${path}[${i}]`)).join(",") + "]";
  }
  if (typeof value === "object") {
    const entries = Object.keys(value as object).sort();
    return (
      "{" +
      entries
        .map((key) => {
          if (!KEY.test(key)) throw new CanonicalError(`${path}: key ${key} must match [a-z0-9_]+`);
          const item = (value as Record<string, unknown>)[key];
          return JSON.stringify(key) + ":" + canonicalize(item, `${path}.${key}`);
        })
        .join(",") +
      "}"
    );
  }
  throw new CanonicalError(`${path}: unsupported value`);
}
