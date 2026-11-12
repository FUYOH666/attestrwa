import {
  type Address,
  type WalletClient,
  createWalletClient,
  custom,
  http,
} from "viem";
import {mnemonicToAccount} from "viem/accounts";

import {DEV_BUYER_INDEX, DEV_MNEMONIC, type NetworkConfig, chainFor} from "./config";

export type Signer = {client: WalletClient; address: Address; label: string};

type InjectedProvider = {request: (args: {method: string; params?: unknown[]}) => Promise<unknown>};

/**
 * On the local fork the buyer is the public development account, so the demo
 * needs no wallet. On a real network the browser wallet signs.
 */
export async function connectSigner(config: NetworkConfig): Promise<Signer> {
  const chain = chainFor(config);
  if (config.devSigner) {
    const account = mnemonicToAccount(DEV_MNEMONIC, {addressIndex: DEV_BUYER_INDEX});
    return {
      client: createWalletClient({account, chain, transport: http(config.rpcUrl)}),
      address: account.address,
      label: "development account (local fork)",
    };
  }
  const provider = (globalThis as {ethereum?: InjectedProvider}).ethereum;
  if (!provider) throw new Error("No browser wallet found. Install one, or run the local demo.");
  const client = createWalletClient({chain, transport: custom(provider)});
  const [address] = await client.requestAddresses();
  if (!address) throw new Error("The wallet did not share an account.");
  if ((await client.getChainId()) !== chain.id) await client.switchChain({id: chain.id});
  return {client: createWalletClient({account: address, chain, transport: custom(provider)}), address, label: "browser wallet"};
}
