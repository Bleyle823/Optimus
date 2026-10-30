/**
 * Print paid infer decisions (model vs rules) from the machine-agent kiosk path.
 *
 * One-shot (gateway + machine-agent must be running):
 *   pnpm show-infer
 *
 * Live feed while Webots or smoke tests run:
 *   pnpm show-infer --watch
 */
import { writeFileSync } from "node:fs";
import { loadRepoEnv, resolveFromRepo } from "@optimus/shared";

const repoRoot = loadRepoEnv();

const watch = process.argv.includes("--watch");
const gatewayUrl = process.env.GATEWAY_URL ?? "http://127.0.0.1:3030";
const agentUrl = process.env.MACHINE_AGENT_URL ?? "http://127.0.0.1:4040";
const outPath = resolveFromRepo(
  repoRoot,
  process.env.SHOW_INFER_OUT ?? "./data/last-infer.json",
);

type Decision = {
  status: string;
  reason: string;
  action: string;
  source: "rules" | "model";
  latencyMs: number;
};

function banner(title: string) {
  console.info("");
  console.info("═".repeat(60));
  console.info(title);
  console.info("═".repeat(60));
}

function printDecision(
  decision: Decision,
  extra?: { receiptId?: string; model?: string; qvacReady?: boolean },
) {
  const fromModel = decision.source === "model";
  banner(fromModel ? "QVAC local model judgment" : "Rules-only judgment (model skipped)");
  console.info("  status     ", decision.status);
  console.info("  source     ", decision.source, fromModel ? "← Llama via QVAC" : "← thresholds, not GGUF");
  console.info("  latencyMs  ", decision.latencyMs.toFixed(1));
  if (extra?.model) console.info("  model      ", extra.model);
  if (extra?.qvacReady !== undefined) {
    console.info("  qvacReady  ", extra.qvacReady);
  }
  console.info("  reason     ", decision.reason);
  console.info("  action     ", decision.action);
  if (extra?.receiptId) console.info("  receiptId  ", extra.receiptId);
  console.info("");
  if (!fromModel) {
    console.warn(
      "[show-infer] Tip: rules fired first. Bench telemetry avoids a parsed temp range in context.",
    );
  }
}

async function printGatewayHealth() {
  const res = await fetch(`${gatewayUrl}/health`);
  if (!res.ok) {
    console.error("[show-infer] Gateway /health failed:", res.status);
    process.exit(1);
  }
  const h = (await res.json()) as {
    qvacReady?: boolean;
    modelAlias?: string;
  };
  console.info("[show-infer] gateway", gatewayUrl);
  console.info("[show-infer] qvacReady", h.qvacReady, "model", h.modelAlias ?? "?");
  if (!h.qvacReady) {
    console.error("[show-infer] QVAC not ready — start `pnpm gateway` and wait for offline GGUF load.");
    process.exit(1);
  }
  return h;
}

function benchTelemetry() {
  const now = new Date().toISOString();
  return {
    machineId: process.env.MACHINE_ID ?? "peaqos:machine:demo",
    kind: "cold_room" as const,
    timestamp: now,
    metrics: {
      tempC: Number(process.env.SHOW_INFER_TEMP ?? 7.2),
      vibrationMmS: Number(process.env.SHOW_INFER_VIB ?? 8.5),
    },
    context:
      process.env.SHOW_INFER_CONTEXT ??
      "Cold room B — bench show-infer (no rule range in context)",
  };
}

async function runOnce() {
  await printGatewayHealth();
  console.info("[show-infer] agent", agentUrl);
  console.info("[show-infer] POST /kiosk/infer …");

  const telemetry = benchTelemetry();
  const res = await fetch(`${agentUrl}/kiosk/infer`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(telemetry),
  });
  const body = (await res.json()) as {
    error?: string;
    decision?: Decision;
    receipt?: { receiptId?: string };
    qvac?: { modelAlias?: string; ready?: boolean };
    quote?: { model?: string };
  };

  if (!res.ok) {
    console.error("[show-infer] FAIL", res.status, body);
    process.exit(1);
  }

  const decision = body.decision;
  if (!decision) {
    console.error("[show-infer] No decision in response:", body);
    process.exit(1);
  }

  const payload = {
    at: new Date().toISOString(),
    telemetry,
    decision,
    receipt: body.receipt,
    quote: body.quote,
    qvac: body.qvac,
  };
  writeFileSync(outPath, JSON.stringify(payload, null, 2), "utf8");

  printDecision(decision, {
    receiptId: body.receipt?.receiptId,
    model: body.qvac?.modelAlias ?? body.quote?.model,
    qvacReady: body.qvac?.ready,
  });
  console.info("[show-infer] Full JSON saved to", outPath);
}

function runWatch() {
  const wsUrl = `${gatewayUrl.replace(/^http/, "ws")}/ws`;
  console.info("[show-infer] Watching", wsUrl);
  console.info("[show-infer] Start Webots or run `pnpm show-infer` in another terminal.");
  console.info("[show-infer] Ctrl+C to stop.\n");

  const ws = new WebSocket(wsUrl);
  ws.addEventListener("open", () => {
    console.info("[show-infer] connected\n");
  });
  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(String(ev.data)) as {
        type?: string;
        decision?: Decision;
        receipt?: { receiptId?: string };
      };
      if (msg.type !== "infer" || !msg.decision) return;
      printDecision(msg.decision, { receiptId: msg.receipt?.receiptId });
    } catch {
      /* ignore */
    }
  });
  ws.addEventListener("error", () => {
    console.error("[show-infer] WebSocket error — is `pnpm gateway` running?");
    process.exit(1);
  });
  ws.addEventListener("close", () => {
    console.info("[show-infer] disconnected");
    process.exit(0);
  });
}

if (watch) {
  runWatch();
} else {
  await runOnce();
}
