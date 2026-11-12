"use client";

import {useEffect, useState} from "react";
import {createPublicClient, http} from "viem";

import {CheckList, RecordView} from "@/components/RecordView";
import {type NetworkConfig, chainFor, loadConfig} from "@/lib/config";
import {type Check, type Envelope, cliCommand, verifyInBrowser} from "@/lib/record";

type Example = {network: string; file: string; label: string};
type Reference = {ok: boolean; verdict: string; checks: Check[]};

export default function VerifyPage() {
  const [config, setConfig] = useState<NetworkConfig | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [text, setText] = useState("");
  const [envelope, setEnvelope] = useState<Envelope | null>(null);
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [reference, setReference] = useState<Reference | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [autoRun, setAutoRun] = useState(false);

  useEffect(() => {
    loadConfig().then(setConfig);
    fetch("/data/records/index.json")
      .then((response) => (response.ok ? response.json() : []))
      .then(setExamples)
      .catch(() => setExamples([]));
    const handedOver = sessionStorage.getItem("attestrwa.record");
    if (handedOver) {
      setText(JSON.stringify(JSON.parse(handedOver), null, 2));
      sessionStorage.removeItem("attestrwa.record");
    }
    // /verify?example=<file>&auto=1 opens a published record and checks it at once.
    const params = new URLSearchParams(window.location.search);
    const example = params.get("example");
    if (example && /^[A-Za-z0-9._-]+\.json$/.test(example)) {
      fetch(`/data/records/${example}`)
        .then((response) => (response.ok ? response.text() : ""))
        .then((body) => {
          if (!body) return;
          setText(body);
          if (params.get("auto") === "1") setAutoRun(true);
        })
        .catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    if (autoRun && config && text) {
      setAutoRun(false);
      void verify();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun, config, text]);

  async function loadExample(example: Example) {
    const response = await fetch(`/data/records/${example.file}`);
    setText(await response.text());
    setChecks(null);
    setReference(null);
  }

  async function verify() {
    if (!config) return;
    setBusy(true);
    setError(null);
    setChecks(null);
    setReference(null);
    try {
      const parsed = JSON.parse(text) as Envelope;
      setEnvelope(parsed);
      const client = createPublicClient({chain: chainFor(config), transport: http(config.rpcUrl)});
      setChecks(await verifyInBrowser(parsed, client));
    } catch (cause) {
      setEnvelope(null);
      setError(cause instanceof Error ? cause.message.split("\n")[0] : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function replay() {
    setBusy(true);
    try {
      const response = await fetch("/api/verify", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: text,
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `verifier answered ${response.status}`);
      setReference(body);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const failed = checks?.some((check) => check.status === "fail");
  const anchored = checks?.some((check) => check.id === "attestation.record_hash" && check.status === "pass");
  const verdict = !checks
    ? undefined
    : failed
      ? "NOT VERIFIED"
      : anchored
        ? "VERIFIED against the chain (rules not re-run in the browser)"
        : "CONSISTENT (not checked against the chain)";

  return (
    <>
      <section className="hero hero-small">
        <p className="eyebrow">No server involved: your browser talks to the chain directly</p>
        <h1>Verify a decision record</h1>
        <p className="lead">
          Paste a record file. The page recomputes its hash, reads the EAS attestation and the
          escrow from {config ? <code>{config.rpcUrl}</code> : "the RPC"}, and compares them with
          the record.
        </p>
      </section>

      <section className="card">
        {examples.length ? (
          <div className="examples">
            <span className="muted">Published examples:</span>
            {examples.map((example) => (
              <button key={example.file} className="button" onClick={() => loadExample(example)}>
                {example.label} · {example.network}
              </button>
            ))}
          </div>
        ) : null}
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder='{"record": {…}, "record_hash": "0x…", "attestation": {"uid": "0x…"}}'
          spellCheck={false}
          rows={10}
        />
        <button className="button button-primary" disabled={busy || !text.trim()} onClick={verify}>
          {busy ? "Verifying…" : "Verify"}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </section>

      {checks ? (
        <section className="card">
          <h3>Browser checks</h3>
          <CheckList checks={checks} verdict={verdict} />
          <h4>Replay the rules yourself</h4>
          <p className="muted">
            Re-running the policy rules is done by the reference verifier, from a checkout of the
            repository:
          </p>
          <pre>{cliCommand("record.json", config?.rpcUrl ?? "https://sepolia.base.org")}</pre>
          <button className="button" disabled={busy} onClick={replay}>
            Run the reference verifier on this demo&apos;s attester
          </button>
          {reference ? <CheckList checks={reference.checks} verdict={reference.verdict} /> : null}
        </section>
      ) : null}

      {envelope && checks && checks[0]?.status === "pass" ? (
        <section className="card">
          <h3>What the record says</h3>
          <RecordView envelope={envelope} />
        </section>
      ) : null}
    </>
  );
}
