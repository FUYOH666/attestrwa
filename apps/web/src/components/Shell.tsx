import Link from "next/link";
import type {ReactNode} from "react";

export function Shell({children}: {children: ReactNode}) {
  return (
    <>
      <header className="top">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden>
            ✓
          </span>
          AttestRWA
        </Link>
        <nav>
          <Link href="/settle">Live settlement</Link>
          <Link href="/verify">Verify a record</Link>
          <a href="https://github.com/FUYOH666/attestrwa">GitHub</a>
        </nav>
      </header>
      <main>{children}</main>
      <footer className="foot">
        Testnet reference implementation. Not audited. The demo policy and payee registry are
        synthetic; nothing here is legal or compliance advice.
      </footer>
    </>
  );
}
