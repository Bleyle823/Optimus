// NETWORK: WDK broadcast and balance — requires internet.

import { WalletAccountEvm } from "@tetherto/wdk-wallet-evm";
import type { WalletAdapterConfig } from "./wallet-adapter.js";

export interface BroadcastUsdtParams {
  seedPhrase: string;
  providerUrl: string;
  usdtContract: string;
  to: string;
  amountUnits: bigint;
}

export async function broadcastUsdtTransfer(
  params: BroadcastUsdtParams,
): Promise<{ hash: string }> {
  const account = new WalletAccountEvm(params.seedPhrase, {
    provider: params.providerUrl,
  });
  const result = await account.transfer({
    token: params.usdtContract,
    recipient: params.to,
    amount: params.amountUnits,
  });
  return { hash: result.hash };
}

export async function getUsdtBalance(
  config: WalletAdapterConfig & { usdtContract: string },
): Promise<bigint> {
  const account = new WalletAccountEvm(config.seedPhrase, {
    provider: config.providerUrl ?? "https://sepolia.gateway.tenderly.co",
  });
  const readOnly = await account.toReadOnlyAccount();
  return readOnly.getTokenBalance(config.usdtContract);
}
