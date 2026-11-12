import type {Metadata} from "next";

import {Shell} from "@/components/Shell";

import "./globals.css";

export const metadata: Metadata = {
  title: "AttestRWA — prove why a settlement was allowed",
  description:
    "Decision records for compliance-gated stablecoin settlement: the policy version, every input and its source, the rules that held, anchored on-chain and verifiable by anyone.",
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
