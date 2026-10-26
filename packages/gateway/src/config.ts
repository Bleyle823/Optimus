import { z } from "zod";

const envSchema = z.object({
  GATEWAY_PORT: z.coerce.number().default(3030),
  GATEWAY_HOST: z.string().default("0.0.0.0"),
  GATEWAY_DID: z.string().default("did:peaq:gateway-local"),
  GATEWAY_PRIVATE_KEY: z.string().optional(),
  GATEWAY_DB_PATH: z.string().default("./data/gateway.json"),
  GATEWAY_PRICE_USDT: z.string().default("0.01"),
  QVAC_MODEL: z.string().optional(),
  QVAC_ENABLED: z
    .string()
    .optional()
    .transform((v) => v !== "0" && v !== "false"),
  GATEWAY_URL: z.string().optional(),
});

export type GatewayConfig = z.infer<typeof envSchema>;

export function loadGatewayConfig(
  env: NodeJS.ProcessEnv = process.env,
): GatewayConfig {
  return envSchema.parse(env);
}
