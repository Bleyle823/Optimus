import { WalletAccountEvm } from "@tetherto/wdk-wallet-evm";
import { verifyMessage, getAddress } from "ethers";
import {
  type PaymentIntent,
  paymentIntentPayload,
  paymentIntentSchema,
} from "@optimus/shared";

export interface WalletAdapterConfig {
  seedPhrase: string;
  chain: string;
  /** NETWORK: RPC URL — only required for broadcast/getBalance */
  providerUrl?: string;
}

export interface WalletAdapter {
  getAddress(): Promise<string>;
  signPaymentIntent(
    intent: Omit<PaymentIntent, "signature">,
  ): Promise<PaymentIntent>;
  verifyPaymentIntent(intent: PaymentIntent): boolean;
}

export function createWalletAdapter(config: WalletAdapterConfig): WalletAdapter {
  const account = new WalletAccountEvm(
    config.seedPhrase,
    config.providerUrl ? { provider: config.providerUrl } : undefined,
  );

  return {
    async getAddress() {
      return account.getAddress();
    },

    async signPaymentIntent(intent) {
      const payload = paymentIntentPayload(intent);
      const signature = await account.sign(payload);
      return paymentIntentSchema.parse({ ...intent, signature });
    },

    verifyPaymentIntent(intent) {
      try {
        const payload = paymentIntentPayload({
          quoteId: intent.quoteId,
          payerAddress: intent.payerAddress,
          payeeAddress: intent.payeeAddress,
          amountUsdt: intent.amountUsdt,
          nonce: intent.nonce,
          chain: intent.chain,
        });
        const recovered = verifyMessage(payload, intent.signature);
        return getAddress(recovered) === getAddress(intent.payerAddress);
      } catch {
        return false;
      }
    },
  };
}
