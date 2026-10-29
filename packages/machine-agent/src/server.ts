import Fastify from "fastify";
import { z } from "zod";
import {
  telemetryReadingSchema,
  decideWithRules,
  type Decision,
  type TelemetryReading,
  type Receipt,
} from "@optimus/shared";
import { createWalletAdapter } from "@optimus/wallet";
import { AgentStore } from "./cache.js";
import { discoverGatewayUrl } from "./discovery.js";
import { checkSpendPolicy, spendPolicySchema } from "./policy.js";

const envSchema = z.object({
  MACHINE_AGENT_PORT: z.coerce.number().default(4040),
  MACHINE_AGENT_HOST: z.string().default("127.0.0.1"),
  MACHINE_ID: z.string().default("peaqos:machine:demo"),
  MACHINE_WALLET_MNEMONIC: z
    .string()
    .default("test test test test test test test test test test test junk"),
  GATEWAY_URL: z.string().default("http://127.0.0.1:3030"),
  AGENT_DB_PATH: z.string().default("./data/agent.json"),
  CHAIN: z.string().default("sepolia"),
});

const config = envSchema.parse(process.env);
const store = new AgentStore(config.AGENT_DB_PATH);
const wallet = createWalletAdapter({
  seedPhrase: config.MACHINE_WALLET_MNEMONIC,
  chain: config.CHAIN,
});

const policy = spendPolicySchema.parse({
  maxPricePerRequestUsdt: Number(process.env.MAX_PRICE_USDT ?? 0.05),
  dailyCapUsdt: Number(process.env.DAILY_CAP_USDT ?? 1),
  allowedGatewayDids: process.env.ALLOWED_GATEWAY_DIDS
    ? process.env.ALLOWED_GATEWAY_DIDS.split(",")
    : [],
});

const history: TelemetryReading[] = [];
let faultOverrides: Record<string, number> = {};

const faultSchema = z.object({
  scenario: z.enum([
    "cold_room_drift",
    "battery_fade",
    "vibration_spike",
    "normal",
  ]),
});

function applyFaults(reading: TelemetryReading): TelemetryReading {
  const m = { ...reading.metrics };
  if (faultOverrides.cold_room_drift) {
    m.tempC = (m.tempC ?? 5) + faultOverrides.cold_room_drift;
  }
  if (faultOverrides.battery_fade) {
    m.batteryPct = 22;
    m.voltageSag = 1;
  }
  if (faultOverrides.vibration_spike) {
    m.vibrationMmS = 10;
  }
  return { ...reading, metrics: m };
}

async function resolveGatewayUrl(): Promise<string> {
  const cached = store.getDiscovery();
  if (cached?.gatewayBaseUrl) return cached.gatewayBaseUrl;
  return discoverGatewayUrl(config.GATEWAY_URL);
}

type QuoteSlice = {
  quoteId?: string;
  gatewayDid: string;
  priceUsdt: string;
  model?: string;
};

type QvacSlice = { ready: boolean; modelAlias: string };

type InferResult = {
  decision: Decision;
  usedGateway: boolean;
  quote?: QuoteSlice;
  receipt?: Receipt;
  qvac: QvacSlice;
};

async function fetchGatewayHealth(baseUrl: string): Promise<QvacSlice> {
  try {
    const res = await fetch(`${baseUrl}/health`);
    if (!res.ok) throw new Error("health failed");
    const health = (await res.json()) as {
      qvacReady?: boolean;
      modelAlias?: string;
    };
    return {
      ready: Boolean(health.qvacReady),
      modelAlias: health.modelAlias ?? "llama-3.2-1b-instruct",
    };
  } catch {
    return { ready: false, modelAlias: "llama-3.2-1b-instruct" };
  }
}

async function inferAtGateway(
  reading: TelemetryReading,
  hist: TelemetryReading[],
): Promise<InferResult> {
  const baseUrl = await resolveGatewayUrl();
  const qvac = await fetchGatewayHealth(baseUrl);
  try {
    const quoteRes = await fetch(
      `${baseUrl}/quote?task=anomaly_judgment`,
    );
    if (!quoteRes.ok) throw new Error("quote failed");
    const quote = (await quoteRes.json()) as QuoteSlice & { nonce: string };

    const policyCheck = checkSpendPolicy(
      policy,
      quote.priceUsdt,
      store.getSpendToday(),
      quote.gatewayDid,
    );
    if (!policyCheck.ok) {
      return {
        decision: {
          status: "warning",
          reason: policyCheck.reason,
          action: "Local rules only until policy allows spend",
          source: "rules",
          latencyMs: 0,
        },
        usedGateway: false,
        quote,
        qvac,
      };
    }

    const payerAddress = await wallet.getAddress();
    const payeeAddress = process.env.GATEWAY_PAYEE_ADDRESS;
    if (!payeeAddress) throw new Error("GATEWAY_PAYEE_ADDRESS not set");

    const inferRes = await fetch(`${baseUrl}/infer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        telemetry: reading,
        history: hist,
        paymentIntent: await wallet.signPaymentIntent({
          quoteId: quote.quoteId ?? "",
          payerAddress,
          payeeAddress,
          amountUsdt: quote.priceUsdt,
          nonce: quote.nonce,
          chain: config.CHAIN,
        }),
      }),
    });

    if (!inferRes.ok) {
      const errText = await inferRes.text();
      throw new Error(errText);
    }
    const body = (await inferRes.json()) as {
      decision: Decision;
      receipt?: Receipt;
    };
    store.addSpend(Number(quote.priceUsdt));
    return {
      decision: body.decision,
      usedGateway: true,
      quote,
      receipt: body.receipt,
      qvac,
    };
  } catch {
    return {
      decision: localFallback(reading, hist),
      usedGateway: false,
      qvac,
    };
  }
}

function localFallback(
  reading: TelemetryReading,
  hist: TelemetryReading[],
): Decision {
  return (
    decideWithRules(reading, hist) ?? {
      status: "ok",
      reason: "Gateway unreachable; readings look nominal",
      action: "Continue with reduced speed",
      source: "rules",
      latencyMs: 0,
    }
  );
}

const app = Fastify({ logger: true });

app.post("/telemetry", async (req, reply) => {
  const parsed = telemetryReadingSchema.safeParse(req.body);
  if (!parsed.success) {
    return reply.code(400).send({ error: parsed.error.flatten() });
  }
  let reading = { ...parsed.data, machineId: config.MACHINE_ID };
  reading = applyFaults(reading);
  store.logTelemetry(JSON.stringify(reading));
  history.push(reading);
  if (history.length > 20) history.shift();

  const decision = localFallback(reading, history.slice(0, -1));
  let qvac: QvacSlice = {
    ready: false,
    modelAlias: "llama-3.2-1b-instruct",
  };
  try {
    qvac = await fetchGatewayHealth(await resolveGatewayUrl());
  } catch {
    /* keep defaults */
  }

  return { decision, telemetry: reading, qvac };
});

/** Paid gateway infer — Webots kiosk only (optimus_robot pay_for_inference). */
app.post("/kiosk/infer", async (req, reply) => {
  const parsed = telemetryReadingSchema.safeParse(req.body);
  if (!parsed.success) {
    return reply.code(400).send({ error: parsed.error.flatten() });
  }
  let reading = { ...parsed.data, machineId: config.MACHINE_ID };
  reading = applyFaults(reading);
  store.logTelemetry(JSON.stringify(reading));
  history.push(reading);
  if (history.length > 20) history.shift();

  const needsModel =
    reading.metrics.tempC !== undefined &&
    reading.context.toLowerCase().includes("cold");
  const suspicious =
    (reading.metrics.tempC ?? 0) > 7 ||
    (reading.metrics.batteryPct ?? 100) < 30 ||
    (reading.metrics.vibrationMmS ?? 0) > 7;

  if (!needsModel && !suspicious) {
    return reply.code(400).send({
      error: "readings not eligible for paid anomaly_judgment at kiosk",
    });
  }

  const result = await inferAtGateway(reading, history.slice(0, -1));
  return {
    decision: result.decision,
    telemetry: reading,
    quote: result.quote,
    receipt: result.receipt,
    qvac: result.qvac,
  };
});

app.post("/fault", async (req, reply) => {
  const parsed = faultSchema.safeParse(req.body);
  if (!parsed.success) {
    return reply.code(400).send({ error: parsed.error.flatten() });
  }
  faultOverrides = {};
  if (parsed.data.scenario === "cold_room_drift") {
    faultOverrides.cold_room_drift = 4;
  } else if (parsed.data.scenario === "battery_fade") {
    faultOverrides.battery_fade = 1;
  } else if (parsed.data.scenario === "vibration_spike") {
    faultOverrides.vibration_spike = 1;
  }
  return { ok: true, scenario: parsed.data.scenario };
});

app.post("/cache/discovery", async (req) => {
  const body = z
    .object({
      gatewayDid: z.string(),
      gatewayBaseUrl: z.string().url(),
      priceUsdt: z.string(),
      mcrScore: z.number().optional(),
    })
    .parse(req.body);
  store.setDiscovery({
    gatewayDid: body.gatewayDid,
    gatewayBaseUrl: body.gatewayBaseUrl,
    priceUsdt: body.priceUsdt,
    mcrScore: body.mcrScore ?? 0,
  });
  return { ok: true };
});

app.get("/health", async () => {
  const qvac = await fetchGatewayHealth(await resolveGatewayUrl());
  return { ok: true, machineId: config.MACHINE_ID, qvac };
});

app.listen({ port: config.MACHINE_AGENT_PORT, host: config.MACHINE_AGENT_HOST });
