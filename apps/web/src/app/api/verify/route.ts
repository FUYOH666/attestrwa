// Runs the reference verifier (attestrwa.verify) on the attester host, with
// that host's chain, policy file and registry file.

import {NextResponse} from "next/server";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const url = process.env.ATTESTER_API_URL;
  if (!url) {
    return NextResponse.json({detail: "No attester is configured for this site."}, {status: 503});
  }
  const body = await request.text();
  if (body.length > 256_000) {
    return NextResponse.json({detail: "record is too large"}, {status: 413});
  }
  try {
    const response = await fetch(`${url}/verify`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body,
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), {status: response.status});
  } catch {
    return NextResponse.json({detail: "The attester is not reachable."}, {status: 502});
  }
}
