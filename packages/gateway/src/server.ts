import crypto from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import Fastify from "fastify";
import websocket from "@fastify/websocket";
import { Bonjour } from "bonjour-service";
import { Wallet, verifyMessage, getAddress } from "ethers";
import {
  inferRequestSchema,
  quoteTaskSchema,
  type Quote,
} from "@optimus/shared";
import { loadGatewayConfig } from "./config.js";
import { GatewayLedger } from "./ledger.js";
import { decide } from "./decide.js";
import { createQvacAdapter } from "./adapters/qvac-adapter.js";

const config = loadGatewayConfig();
mkdirSync(dirname(config.GATEWAY_DB_PATH), { recursive: true });

const ledger = new GatewayLedger(config.GATEWAY_DB_PATH);
const qvac = createQvacAdapter(config.QVAC_MODEL);
const gatewayWallet = config.GATEWAY_PRIVATE_KEY
  ? new Wallet(config.GATEWAY_PRIVATE_KEY)
  : Wallet.createRandom();

const modelEnabled = config.QVAC_ENABLED !== false;

const clients = new Set<{ send: (data: string) => void }>();

function broadcast(event: unknown) {
  const payload = JSON.stringify(event);
  for (const c of clients) {
    c.send(payload);
  }
}

function hashDecision(decision: unknown): string {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(decision))
    .digest("hex");
}

async function signReceiptPayload(payload: string): Promise<string> {
  return gatewayWallet.signMessage(payload);
}

export async function buildServer() {
  const app = Fastify({ logger: true });
  await app.register(websocket);

  app.get("/health", async () => ({
    ok: true,
    qvacReady: qvac.isReady(),
    modelAlias: qvac.getModelAlias(),
    gatewayAddress: gatewayWallet.address,
    gatewayDid: config.GATEWAY_DID,
  }));

  app.get("/v1/models", async () => ({
    object: "list" as const,
    data: [
      {
        id: qvac.getModelAlias(),
        object: "model" as const,
        created: Math.floor(Date.now() / 1000),
        owned_by: "qvac" as const,
        state: qvac.isReady() ? ("ready" as const) : ("idle" as const),
      },
    ],
  }));

  app.get("/quote", async (req, reply) => {
    const task = (req.query as { task?: string }).task;
    const parsedTask = quoteTaskSchema.safeParse(task);
    if (!parsedTask.success) {
      return reply.code(400).send({ error: "invalid task" });
    }
    const nonce = crypto.randomBytes(16).toString("hex");
    const quote: Quote = {
      quoteId: crypto.randomUUID(),
      gatewayDid: config.GATEWAY_DID,
      task: parsedTask.data,
      model: qvac.getModelAlias(),
      priceUsdt: config.GATEWAY_PRICE_USDT,
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
      nonce,
    };
    ledger.saveQuote(quote);
    return quote;
  });

  app.post("/infer", async (req, reply) => {
    const parsed = inferRequestSchema.safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: parsed.error.flatten() });
    }
    const { telemetry, history, paymentIntent } = parsed.data;

    const quote = ledger.getQuote(paymentIntent.quoteId);
    if (!quote) {
      return reply.code(400).send({ error: "unknown quote" });
    }
    if (new Date(quote.expiresAt) < new Date()) {
      return reply.code(400).send({ error: "quote expired" });
    }
    if (quote.nonce !== paymentIntent.nonce) {
      return reply.code(400).send({ error: "nonce mismatch" });
    }
    if (ledger.isNonceUsed(paymentIntent.nonce)) {
      return reply.code(409).send({ error: "nonce replay" });
    }
    if (paymentIntent.amountUsdt !== quote.priceUsdt) {
      return reply.code(400).send({ error: "amount mismatch" });
    }
    if (
      getAddress(paymentIntent.payeeAddress) !== getAddress(gatewayWallet.address)
    ) {
      return reply.code(400).send({ error: "payee mismatch" });
    }

    const payload = JSON.stringify({
      quoteId: paymentIntent.quoteId,
      payerAddress: paymentIntent.payerAddress.toLowerCase(),
      payeeAddress: paymentIntent.payeeAddress.toLowerCase(),
      amountUsdt: paymentIntent.amountUsdt,
      nonce: paymentIntent.nonce,
      chain: paymentIntent.chain,
    });
    try {
      const recovered = verifyMessage(payload, paymentIntent.signature);
      if (getAddress(recovered) !== getAddress(paymentIntent.payerAddress)) {
        return reply.code(401).send({ error: "invalid signature" });
      }
    } catch {
      return reply.code(401).send({ error: "invalid signature" });
    }

    const decision = await decide(telemetry, history, {
      qvac,
      modelEnabled: modelEnabled && qvac.isReady(),
    });

    const decisionHash = hashDecision(decision);
    const receiptId = crypto.randomUUID();
    const receiptBody = JSON.stringify({
      receiptId,
      quoteId: quote.quoteId,
      machineId: telemetry.machineId,
      decisionHash,
      amountUsdt: quote.priceUsdt,
    });
    const gatewaySignature = await signReceiptPayload(receiptBody);

    const receipt = {
      receiptId,
      quoteId: quote.quoteId,
      machineId: telemetry.machineId,
      gatewayDid: config.GATEWAY_DID,
      decisionHash,
      amountUsdt: quote.priceUsdt,
      settlementStatus: "pending_settlement" as const,
      gatewaySignature,
    };

    ledger.markNonceUsed(paymentIntent.nonce);
    ledger.saveReceipt(receipt);

    broadcast({ type: "infer", telemetry, decision, receipt });
    return { decision, receipt };
  });

  app.get("/ledger", async () => ({ receipts: ledger.listReceipts() }));

  app.get("/ws", { websocket: true }, (socket) => {
    clients.add(socket);
    socket.on("close", () => clients.delete(socket));
  });

  return app;
}

export async function startGateway() {
  if (modelEnabled) {
    await qvac.load();
  }
  const app = await buildServer();
  const bonjour = new Bonjour();
  bonjour.publish({
    name: "optimus-gateway",
    type: "optimus-gateway",
    port: config.GATEWAY_PORT,
  });

  await app.listen({ port: config.GATEWAY_PORT, host: config.GATEWAY_HOST });
  console.info(
    `Gateway listening on ${config.GATEWAY_HOST}:${config.GATEWAY_PORT}; payee ${gatewayWallet.address}`,
  );
}
