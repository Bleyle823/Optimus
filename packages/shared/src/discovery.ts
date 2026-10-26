import { z } from "zod";

export const discoveryCacheSchema = z.object({
  gatewayDid: z.string(),
  gatewayBaseUrl: z.string().url(),
  priceUsdt: z.string(),
  mcrScore: z.number(),
});

export type DiscoveryCache = z.infer<typeof discoveryCacheSchema>;
