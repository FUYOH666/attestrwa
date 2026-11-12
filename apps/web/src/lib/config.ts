import type {Address, Chain} from "viem";
import {baseSepolia} from "viem/chains";

export const PUBLIC_BASE_SEPOLIA_RPC = "https://sepolia.base.org";
export const EAS_PREDEPLOY: Address = "0x4200000000000000000000000000000000000021";

// Accounts of the publicly known Foundry development mnemonic. They exist
// only on the local fork; data/registry/payees.json lists the first one.
export const DEV_MNEMONIC = "test test test test test test test test test test test junk";
export const DEV_BUYER_INDEX = 1;
export const REGISTERED_PAYEE: Address = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
export const UNREGISTERED_PAYEE: Address = "0x90F79bf6EB2c4f870365E785982E1f101E93b906";

export type NetworkConfig = {
  network: string;
  chainId: number;
  rpcUrl: string;
  escrow: Address | null;
  token: Address | null;
  /** True on the local fork: the page signs with the development account. */
  devSigner: boolean;
  explorer: {tx: string; address: string; attestation: string} | null;
};

const BASE_SEPOLIA_EXPLORER = {
  tx: "https://sepolia.basescan.org/tx/",
  address: "https://sepolia.basescan.org/address/",
  attestation: "https://base-sepolia.easscan.org/attestation/view/",
};

function address(value: string | undefined): Address | null {
  return value && /^0x[0-9a-fA-F]{40}$/.test(value) ? (value as Address) : null;
}

/** Resolve the network: the local fork from the environment, else the public deployment. */
export async function loadConfig(): Promise<NetworkConfig> {
  const envEscrow = address(process.env.NEXT_PUBLIC_ESCROW_ADDRESS);
  const envNetwork = process.env.NEXT_PUBLIC_NETWORK;
  if (envEscrow && envNetwork) {
    const local = envNetwork === "anvil-fork";
    return {
      network: envNetwork,
      chainId: baseSepolia.id,
      rpcUrl: process.env.NEXT_PUBLIC_RPC_URL ?? "http://127.0.0.1:8545",
      escrow: envEscrow,
      token: address(process.env.NEXT_PUBLIC_TOKEN_ADDRESS),
      devSigner: local,
      explorer: local ? null : BASE_SEPOLIA_EXPLORER,
    };
  }
  try {
    const response = await fetch("/data/base-sepolia.json", {cache: "no-store"});
    if (response.ok) {
      const deployment = await response.json();
      return {
        network: "base-sepolia",
        chainId: baseSepolia.id,
        rpcUrl: PUBLIC_BASE_SEPOLIA_RPC,
        escrow: address(deployment.escrow),
        token: address(deployment.token),
        devSigner: false,
        explorer: BASE_SEPOLIA_EXPLORER,
      };
    }
  } catch {
    // fall through to the unconfigured state
  }
  return {
    network: "unconfigured",
    chainId: baseSepolia.id,
    rpcUrl: process.env.NEXT_PUBLIC_RPC_URL ?? PUBLIC_BASE_SEPOLIA_RPC,
    escrow: null,
    token: null,
    devSigner: false,
    explorer: BASE_SEPOLIA_EXPLORER,
  };
}

export function chainFor(config: NetworkConfig): Chain {
  return {...baseSepolia, rpcUrls: {default: {http: [config.rpcUrl]}}};
}
