import {
  decisionSchema,
  type Decision,
  type TelemetryReading,
} from "@optimus/shared";
import { decideWithRules } from "./decide-rules.js";
import type { QvacAdapter } from "./adapters/qvac-adapter.js";

const SYSTEM_PROMPT = `You are a warehouse machine-monitoring assistant running locally.
Respond with ONLY a JSON object, no prose, no markdown:
{"status":"ok|warning|critical","reason":"<max 25 words>","action":"<max 20 words>"}
Be conservative: if readings approach or exceed safe limits, escalate.`;

function formatHistory(readings: TelemetryReading[]): string {
  const rows = readings.map((r) => {
    const m = Object.entries(r.metrics)
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    return `${r.timestamp} | ${m}`;
  });
  return rows.join("\n");
}

export interface DecideDeps {
  qvac: QvacAdapter | null;
  modelEnabled: boolean;
}

export async function decide(
  reading: TelemetryReading,
  history: TelemetryReading[],
  deps: DecideDeps,
): Promise<Decision> {
  const rules = decideWithRules(reading, history);
  if (rules && rules.status !== "ok") {
    return rules;
  }

  if (!deps.modelEnabled || !deps.qvac?.isReady()) {
    return (
      rules ?? {
        status: "ok",
        reason: "Readings within expected operating range",
        action: "Continue normal operation",
        source: "rules",
        latencyMs: 0,
      }
    );
  }

  const lastN = [...history, reading].slice(-5);
  const userContent = [
    `kind: ${reading.kind}`,
    `context: ${reading.context}`,
    "recent readings:",
    formatHistory(lastN),
  ].join("\n");

  const start = performance.now();
  try {
    const raw = await deps.qvac.complete({
      system: SYSTEM_PROMPT,
      user: userContent,
      jsonObject: true,
    });
    const parsed = decisionSchema
      .pick({ status: true, reason: true, action: true })
      .safeParse(JSON.parse(raw));
    if (parsed.success) {
      return {
        ...parsed.data,
        source: "model",
        latencyMs: performance.now() - start,
      };
    }
  } catch {
    /* fall through */
  }

  try {
    const raw = await deps.qvac.complete({
      system: SYSTEM_PROMPT,
      user: userContent,
      jsonObject: true,
    });
    const parsed = decisionSchema
      .pick({ status: true, reason: true, action: true })
      .safeParse(JSON.parse(raw));
    if (parsed.success) {
      return {
        ...parsed.data,
        source: "model",
        latencyMs: performance.now() - start,
      };
    }
  } catch {
    /* fall through */
  }

  return (
    rules ?? {
      status: "warning",
      reason: "Model output invalid; conservative hold",
      action: "Use local rules and re-check sensors",
      source: "rules",
      latencyMs: performance.now() - start,
    }
  );
}
