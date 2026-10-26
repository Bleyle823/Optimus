import { z } from "zod";

export const spendPolicySchema = z.object({
  maxPricePerRequestUsdt: z.number().default(0.05),
  dailyCapUsdt: z.number().default(1),
  allowedGatewayDids: z.array(z.string()).default([]),
});

export type SpendPolicy = z.infer<typeof spendPolicySchema>;

export function checkSpendPolicy(
  policy: SpendPolicy,
  priceUsdt: string,
  spentToday: number,
  gatewayDid: string,
): { ok: true } | { ok: false; reason: string } {
  const price = Number(priceUsdt);
  if (price > policy.maxPricePerRequestUsdt) {
    return { ok: false, reason: "price exceeds max per request" };
  }
  if (spentToday + price > policy.dailyCapUsdt) {
    return { ok: false, reason: "daily spend cap exceeded" };
  }
  if (
    policy.allowedGatewayDids.length > 0 &&
    !policy.allowedGatewayDids.includes(gatewayDid)
  ) {
    return { ok: false, reason: "gateway DID not allowlisted" };
  }
  return { ok: true };
}
