import Link from "next/link";

const STEPS = [
  {
    title: "Decide from sources, not claims",
    text: "The attester reads the deal from the escrow and each input from the kind of source the policy names: chain state, a sanctions oracle, a registry file, or an explicit declaration.",
  },
  {
    title: "Record and anchor",
    text: "Policy version, inputs with their sources, rule results and the outcome go into one canonical record. Its hash and the policy hash are attested on-chain with EAS.",
  },
  {
    title: "Anyone verifies",
    text: "With the record file and a public RPC, a third party recomputes the hash, compares it with the attestation and the escrow, and re-runs the rules.",
  },
];

export default function Home() {
  return (
    <>
      <section className="hero">
        <p className="eyebrow">Decision records for compliance-gated settlement</p>
        <h1>Prove why a settlement was allowed.</h1>
        <p className="lead">
          AttestRWA turns a compliance decision about a stablecoin settlement into a record anyone
          can check afterwards: which policy version was applied, which inputs were used and where
          each came from, and which rules held. The record&apos;s hash is anchored on-chain; an
          escrow releases or refunds on that decision.
        </p>
        <div className="actions">
          <Link className="button button-primary" href="/settle">
            Run a settlement
          </Link>
          <Link className="button" href="/verify">
            Verify a record
          </Link>
        </div>
      </section>

      <section className="grid">
        {STEPS.map((step, index) => (
          <article className="card" key={step.title}>
            <span className="step-number">{index + 1}</span>
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </article>
        ))}
      </section>

      <section className="card">
        <h3>What is in the repository</h3>
        <ul className="plain">
          <li>
            <strong>Decision Record v0.1</strong> — the format, its JSON Schema and test vectors.
          </li>
          <li>
            <strong>Decision Record v0.2</strong> — the same record signed with a key, for
            decisions with no escrow: documents, AI model outputs and sign-offs cited by hash.
            Verified with the command line.
          </li>
          <li>
            <strong>attestrwa verify</strong> — an independent verifier with two dependencies.
          </li>
          <li>
            <strong>SettlementEscrow</strong> — a reference escrow that settles only on an exact,
            live decision by a trusted attester.
          </li>
          <li>
            <strong>Reference attester</strong> — reads the deal from chain and screens against the
            Chainalysis sanctions oracle.
          </li>
        </ul>
      </section>
    </>
  );
}
