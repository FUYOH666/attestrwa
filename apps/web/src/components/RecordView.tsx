import type {Check, Envelope, RecordInput} from "@/lib/record";

function sourceText(input: RecordInput): string {
  const source = input.source;
  switch (source.kind) {
    case "subject":
      return `escrow state · ${String(source.field)}`;
    case "onchain":
      return `call ${String(source.call)} at block ${String(source.block_number)}`;
    case "registry":
      return `file ${String(source.ref)}`;
    case "provider":
      return String(source.name);
    case "declared":
      return `by ${String(source.by)} · not verified`;
    default:
      return source.kind;
  }
}

export function Hash({value}: {value: string}) {
  return (
    <code className="hash" title={value}>
      {value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value}
    </code>
  );
}

export function RecordView({envelope}: {envelope: Envelope}) {
  const record = envelope.record;
  const approve = record.decision.outcome === "approve";
  return (
    <div className="record">
      <div className="record-head">
        <span className={`badge ${approve ? "badge-pass" : "badge-fail"}`}>
          {record.decision.outcome.toUpperCase()}
        </span>
        <span>
          under policy <strong>{record.policy.pack_id}</strong> {record.policy.version}{" "}
          <Hash value={record.policy.sha256} />
        </span>
      </div>

      <h4>Inputs and where each came from</h4>
      <table>
        <thead>
          <tr>
            <th>Input</th>
            <th>Value</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {record.inputs.map((input) => (
            <tr key={input.name}>
              <td>
                <code>{input.name}</code>
              </td>
              <td>
                <code>{String(input.value)}</code>
              </td>
              <td className={input.source.kind === "declared" ? "muted" : undefined}>
                <span className={`kind kind-${input.source.kind}`}>{input.source.kind}</span>{" "}
                {sourceText(input)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>Rules</h4>
      <table>
        <tbody>
          {record.rules.map((rule) => (
            <tr key={rule.id}>
              <td className={rule.result ? "mark-pass" : "mark-fail"}>{rule.result ? "✓" : "✗"}</td>
              <td>{rule.id}</td>
              <td>
                <code>{rule.expression}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="facts">
        <dt>Record hash</dt>
        <dd>
          <Hash value={envelope.record_hash} />
        </dd>
        <dt>Attestation</dt>
        <dd>{envelope.attestation ? <Hash value={envelope.attestation.uid} /> : "none"}</dd>
        <dt>Attester</dt>
        <dd>
          <Hash value={record.attester.address} />
        </dd>
        <dt>Evaluated at block</dt>
        <dd>{record.evaluation.block_number}</dd>
      </dl>
    </div>
  );
}

export function CheckList({checks, verdict}: {checks: Check[]; verdict?: string}) {
  const groups = [...new Set(checks.map((check) => check.group))];
  const failed = checks.some((check) => check.status === "fail");
  return (
    <div className="checks">
      {verdict ? (
        <p className={`verdict ${failed ? "verdict-fail" : "verdict-pass"}`}>{verdict}</p>
      ) : null}
      {groups.map((group) => (
        <div key={group}>
          <h4>{group}</h4>
          <ul>
            {checks
              .filter((check) => check.group === group)
              .map((check) => (
                <li key={check.id} className={`check check-${check.status}`}>
                  <span className="check-mark">
                    {check.status === "pass" ? "✓" : check.status === "fail" ? "✗" : "–"}
                  </span>
                  <code>{check.id}</code>
                  <span>{check.detail}</span>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
