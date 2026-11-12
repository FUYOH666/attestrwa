// Server-side bridge to the attester. The API key stays on the server; the
// browser only names a deal id. Chain and escrow come from server settings,
// so a page visitor cannot point the attester at anything else.

import {NextResponse} from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const url = process.env.ATTESTER_API_URL;
  const key = process.env.ATTESTER_API_KEY;
  const escrow = process.env.NEXT_PUBLIC_ESCROW_ADDRESS;
  if (!url || !key || !escrow) {
    return NextResponse.json(
      {detail: "No attester is configured for this site. Run ./scripts/demo-mode.sh for the local demo."},
      {status: 503},
    );
  }
  const body = await request.json().catch(() => null);
  const dealId = body?.deal_id;
  if (typeof dealId !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(dealId)) {
    return NextResponse.json({detail: "deal_id must be 0x followed by 64 hex digits"}, {status: 422});
  }
  try {
    const response = await fetch(`${url}/attest/settlement`, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-API-Key": key},
      body: JSON.stringify({
        chain_id: 84532,
        escrow,
        deal_id: dealId,
        // What this integrator states about the deal. Recorded as declared, not verified.
        declared: {jurisdiction: "TH"},
      }),
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), {status: response.status});
  } catch {
    return NextResponse.json({detail: "The attester is not reachable."}, {status: 502});
  }
}
