import { z } from "zod";

export const machineKindSchema = z.enum(["cold_room", "forklift", "scanner"]);

export const telemetryReadingSchema = z.object({
  machineId: z.string().min(1),
  kind: machineKindSchema,
  timestamp: z.string().datetime(),
  metrics: z.record(z.string(), z.number()),
  context: z.string().min(1),
  /** Deprecated: paid infer uses POST /kiosk/infer on the machine-agent, not /telemetry. */
  requestPaidInfer: z.boolean().optional(),
});

export const quoteTaskSchema = z.literal("anomaly_judgment");

export const quoteSchema = z.object({
  quoteId: z.string().uuid(),
  gatewayDid: z.string().min(1),
  task: quoteTaskSchema,
  model: z.string().min(1),
  priceUsdt: z.string().min(1),
  expiresAt: z.string().datetime(),
  nonce: z.string().min(8),
});

export const paymentIntentSchema = z.object({
  quoteId: z.string().uuid(),
  payerAddress: z.string().regex(/^0x[a-fA-F0-9]{40}$/),
  payeeAddress: z.string().regex(/^0x[a-fA-F0-9]{40}$/),
  amountUsdt: z.string().min(1),
  nonce: z.string().min(8),
  chain: z.string().min(1),
  signature: z.string().min(1),
});

export const decisionStatusSchema = z.enum(["ok", "warning", "critical"]);

export const decisionSchema = z.object({
  status: decisionStatusSchema,
  reason: z.string().min(1),
  action: z.string().min(1),
  source: z.enum(["rules", "model"]),
  latencyMs: z.number().nonnegative(),
});

export const settlementStatusSchema = z.enum([
  "pending_settlement",
  "settled",
  "failed",
]);

export const receiptSchema = z.object({
  receiptId: z.string().uuid(),
  quoteId: z.string().uuid(),
  machineId: z.string().min(1),
  gatewayDid: z.string().min(1),
  decisionHash: z.string().min(1),
  amountUsdt: z.string().min(1),
  settlementStatus: settlementStatusSchema,
  txHash: z.string().optional(),
  gatewaySignature: z.string().min(1),
});

export const inferRequestSchema = z.object({
  telemetry: telemetryReadingSchema,
  history: z.array(telemetryReadingSchema).default([]),
  paymentIntent: paymentIntentSchema,
});

export const inferResponseSchema = z.object({
  decision: decisionSchema,
  receipt: receiptSchema,
});

export const modelListResponseSchema = z.object({
  object: z.literal("list"),
  data: z.array(
    z.object({
      id: z.string(),
      object: z.literal("model"),
      created: z.number(),
      owned_by: z.literal("qvac"),
      state: z.enum(["idle", "loading", "ready", "error"]),
    }),
  ),
});

export type TelemetryReading = z.infer<typeof telemetryReadingSchema>;
export type Quote = z.infer<typeof quoteSchema>;
export type PaymentIntent = z.infer<typeof paymentIntentSchema>;
export type Decision = z.infer<typeof decisionSchema>;
export type Receipt = z.infer<typeof receiptSchema>;
export type InferRequest = z.infer<typeof inferRequestSchema>;
export type InferResponse = z.infer<typeof inferResponseSchema>;

/** Canonical JSON for EIP-191 payment intent signing (excludes signature). */
export function paymentIntentPayload(intent: Omit<PaymentIntent, "signature">) {
  return JSON.stringify({
    quoteId: intent.quoteId,
    payerAddress: intent.payerAddress.toLowerCase(),
    payeeAddress: intent.payeeAddress.toLowerCase(),
    amountUsdt: intent.amountUsdt,
    nonce: intent.nonce,
    chain: intent.chain,
  });
}
