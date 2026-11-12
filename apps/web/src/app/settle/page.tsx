"use client";

import Link from "next/link";
import {useCallback, useEffect, useMemo, useState} from "react";
import {type Address, type Hex, createPublicClient, formatUnits, http, keccak256, stringToBytes} from "viem";

import {CheckList, Hash, RecordView} from "@/components/RecordView";
import {escrowAbi, tokenAbi} from "@/lib/abi";
import {
  type NetworkConfig,
  REGISTERED_PAYEE,
  UNREGISTERED_PAYEE,
  chainFor,
  loadConfig,
} from "@/lib/config";
import type {Check, Envelope} from "@/lib/record";
import {type Signer, connectSigner} from "@/lib/signer";

const AMOUNT = 580_000_000n; // 580 mUSDC (6 decimals)

const SCENARIOS = {
  approve: {
    title: "Registered payee",
    payee: REGISTERED_PAYEE,
    note: "The payee is in the registry and nobody is sanctioned. Expect APPROVE, then release.",
  },
  reject: {
    title: "Unregistered payee",
    payee: UNREGISTERED_PAYEE,
    note: "The buyer was given a payee that is not in the registry. Expect REJECT, then refund.",
  },
} as const;

type Scenario = keyof typeof SCENARIOS;
type Phase = "idle" | "depositing" | "deposited" | "deciding" | "decided" | "settling" | "settled";
type Report = {ok: boolean; verdict: string; checks: Check[]};
type LogLine = {text: string; hash?: Hex};

export default function SettlePage() {
  const [config, setConfig] = useState<NetworkConfig | null>(null);
  const [scenario, setScenario] = useState<Scenario>("approve");
  const [phase, setPhase] = useState<Phase>("idle");
  const [signer, setSigner] = useState<Signer | null>(null);
  const [dealId, setDealId] = useState<Hex | null>(null);
  const [envelope, setEnvelope] = useState<Envelope | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [balances, setBalances] = useState<Record<string, bigint>>({});

  useEffect(() => {
    loadConfig().then(setConfig);
  }, []);

  const client = useMemo(
    () => (config ? createPublicClient({chain: chainFor(config), transport: http(config.rpcUrl)}) : null),
    [config],
  );
  const payee = SCENARIOS[scenario].payee;

  const refreshBalances = useCallback(
    async (buyer?: Address) => {
      if (!client || !config?.token || !config.escrow) return;
      const read = (owner: Address) =>
        client.readContract({address: config.token!, abi: tokenAbi, functionName: "balanceOf", args: [owner]});
      const next: Record<string, bigint> = {payee: await read(payee), escrow: await read(config.escrow)};
      if (buyer) next.buyer = await read(buyer);
      setBalances(next);
    },
    [client, config, payee],
  );

  useEffect(() => {
    refreshBalances(signer?.address).catch(() => undefined);
  }, [refreshBalances, signer]);

  const note = (text: string, hash?: Hex) => setLog((lines) => [...lines, {text, hash}]);

  async function run(next: Phase, done: Phase, action: () => Promise<void>) {
    setError(null);
    setPhase(next);
    try {
      await action();
      setPhase(done);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message.split("\n")[0] : String(cause));
      setPhase(next === "depositing" ? "idle" : next === "deciding" ? "deposited" : "decided");
    }
  }

  const deposit = () =>
    run("depositing", "deposited", async () => {
      if (!client || !config?.escrow || !config.token) throw new Error("No deployment configured.");
      const wallet = signer ?? (await connectSigner(config));
      setSigner(wallet);
      const chain = chainFor(config);
      const account = wallet.client.account!;
      const send = async (label: string, request: Parameters<typeof wallet.client.writeContract>[0]) => {
        const hash = await wallet.client.writeContract(request);
        await client.waitForTransactionReceipt({hash});
        note(label, hash);
      };
      await send("Minted 580 mUSDC to the buyer", {
        address: config.token, abi: tokenAbi, functionName: "mint", args: [wallet.address, AMOUNT], chain, account,
      });
      await send("Approved the escrow to pull 580 mUSDC", {
        address: config.token, abi: tokenAbi, functionName: "approve", args: [config.escrow, AMOUNT], chain, account,
      });
      const salt = keccak256(stringToBytes(`${Date.now()}-${Math.random()}`));
      const block = await client.getBlock();
      await send(`Deposited 580 mUSDC for payee ${payee}`, {
        address: config.escrow, abi: escrowAbi, functionName: "deposit",
        args: [salt, payee, config.token, AMOUNT, block.timestamp + 86_400n], chain, account,
      });
      const id = await client.readContract({
        address: config.escrow, abi: escrowAbi, functionName: "computeDealId", args: [wallet.address, salt],
      });
      setDealId(id);
      await refreshBalances(wallet.address);
    });

  const decide = () =>
    run("deciding", "decided", async () => {
      const response = await fetch("/api/attest", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({deal_id: dealId}),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `attester answered ${response.status}`);
      setEnvelope(body.envelope);
      note(`Attester decided ${String(body.decision).toUpperCase()} and anchored the record`, body.tx_hash);
      const verified = await fetch("/api/verify", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body.envelope),
      });
      if (verified.ok) setReport(await verified.json());
    });

  const settle = () =>
    run("settling", "settled", async () => {
      if (!client || !config?.escrow || !signer || !dealId || !envelope?.attestation) return;
      const approve = envelope.record.decision.outcome === "approve";
      const hash = await signer.client.writeContract({
        address: config.escrow,
        abi: escrowAbi,
        functionName: approve ? "release" : "refund",
        args: [dealId, envelope.attestation.uid],
        chain: chainFor(config),
        account: signer.client.account!,
      });
      await client.waitForTransactionReceipt({hash});
      note(approve ? "Escrow released the funds to the payee" : "Escrow refunded the buyer", hash);
      await refreshBalances(signer.address);
    });

  function reset(next: Scenario) {
    setScenario(next);
    setPhase("idle");
    setDealId(null);
    setEnvelope(null);
    setReport(null);
    setLog([]);
    setError(null);
  }

  function openInVerifier() {
    if (envelope) sessionStorage.setItem("attestrwa.record", JSON.stringify(envelope));
  }

  if (!config) return <p className="muted">Loading…</p>;
  if (!config.escrow || !config.token) {
    return (
      <section className="card">
        <h2>No deployment is configured</h2>
        <p>
          Start the local demo from the repository root. It forks Base Sepolia, deploys the
          contracts and runs the attester; no wallet or faucet is needed.
        </p>
        <pre>./scripts/demo-mode.sh</pre>
      </section>
    );
  }

  const busy = phase === "depositing" || phase === "deciding" || phase === "settling";
  const approve = envelope?.record.decision.outcome === "approve";
  const units = (value?: bigint) => (value === undefined ? "–" : formatUnits(value, 6));

  return (
    <>
      <section className="hero hero-small">
        <p className="eyebrow">
          {config.network} · escrow <Hash value={config.escrow} />
        </p>
        <h1>Live settlement</h1>
        <p className="lead">
          Deposit into the escrow, let the attester decide from chain state, the sanctions oracle
          and the payee registry, then settle on that decision. Every step is a real transaction
          {config.devSigner ? " on a local fork of Base Sepolia, signed by the public development account." : "."}
        </p>
      </section>

      <section className="card">
        <h3>1 · Choose the deal</h3>
        <div className="choices">
          {(Object.keys(SCENARIOS) as Scenario[]).map((key) => (
            <button
              key={key}
              className={`choice ${scenario === key ? "choice-on" : ""}`}
              disabled={busy}
              onClick={() => reset(key)}
            >
              <strong>{SCENARIOS[key].title}</strong>
              <span>{SCENARIOS[key].note}</span>
            </button>
          ))}
        </div>
        <button className="button button-primary" disabled={phase !== "idle"} onClick={deposit}>
          {phase === "depositing" ? "Depositing…" : "Deposit 580 mUSDC into the escrow"}
        </button>
        <dl className="facts">
          <dt>Buyer balance</dt>
          <dd>{units(balances.buyer)}</dd>
          <dt>Escrow balance</dt>
          <dd>{units(balances.escrow)}</dd>
          <dt>Payee balance</dt>
          <dd>{units(balances.payee)}</dd>
        </dl>
      </section>

      <section className="card">
        <h3>2 · Ask the attester</h3>
        <p className="muted">
          The request carries only the deal id. Buyer, payee, token and amount are read from the
          escrow; they cannot be supplied by the caller.
        </p>
        <button className="button button-primary" disabled={phase !== "deposited"} onClick={decide}>
          {phase === "deciding" ? "Deciding…" : "Request a decision"}
        </button>
        {dealId ? (
          <p className="muted">
            Deal <Hash value={dealId} />
            {phase === "deciding" && config.devSigner
              ? " · on the local fork this takes about ten seconds: Anvil fetches EAS state from the public RPC"
              : ""}
          </p>
        ) : null}
        {envelope ? <RecordView envelope={envelope} /> : null}
      </section>

      {report ? (
        <section className="card">
          <h3>Independent verification</h3>
          <p className="muted">
            The reference verifier recomputed the hash, compared the record with the attestation and
            the escrow, re-ran the rules and re-queried the on-chain inputs.
          </p>
          <CheckList checks={report.checks} verdict={report.verdict} />
          <Link className="button" href="/verify" onClick={openInVerifier}>
            Check it again in the browser
          </Link>
        </section>
      ) : null}

      <section className="card">
        <h3>3 · Settle</h3>
        <button
          className="button button-primary"
          disabled={phase !== "decided"}
          onClick={settle}
        >
          {phase === "settling"
            ? "Settling…"
            : envelope
              ? approve
                ? "Release to the payee"
                : "Refund the buyer"
              : "Release or refund"}
        </button>
        {phase === "settled" ? (
          <p className={approve ? "verdict verdict-pass" : "verdict verdict-fail"}>
            {approve ? "Released: the payee received 580 mUSDC." : "Refunded: the buyer has the deposit back."}
          </p>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        {log.length ? (
          <ol className="log">
            {log.map((line, index) => (
              <li key={index}>
                {line.text}
                {line.hash ? (
                  <>
                    {" "}
                    {config.explorer ? (
                      <a href={config.explorer.tx + line.hash}>
                        <Hash value={line.hash} />
                      </a>
                    ) : (
                      <Hash value={line.hash} />
                    )}
                  </>
                ) : null}
              </li>
            ))}
          </ol>
        ) : null}
      </section>
    </>
  );
}
