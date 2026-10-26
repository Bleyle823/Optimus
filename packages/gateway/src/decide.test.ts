import { describe, expect, it } from "vitest";
import { decideWithRules } from "./decide-rules.js";
import type { TelemetryReading } from "@optimus/shared";

function reading(
  partial: Partial<TelemetryReading> & Pick<TelemetryReading, "metrics">,
): TelemetryReading {
  return {
    machineId: "peaqos:machine:1",
    kind: "cold_room",
    timestamp: new Date().toISOString(),
    context: partial.context ?? "Cold room B, flowers, safe range 2 to 8 C",
    ...partial,
  };
}

describe("decideWithRules — §8 scenarios", () => {
  it("cold room drift → critical", () => {
    const d = decideWithRules(
      reading({ metrics: { tempC: 9, compressorCurrent: 0.2 } }),
      [reading({ metrics: { tempC: 4 } })],
    );
    expect(d?.status).toBe("critical");
  });

  it("power outage → warning", () => {
    const d = decideWithRules(
      reading({
        metrics: { tempC: 5, mainsLost: 1, batteryPct: 30 },
      }),
      [],
    );
    expect(d?.status).toBe("warning");
  });

  it("forklift battery fade → warning", () => {
    const d = decideWithRules(
      reading({
        kind: "forklift",
        context: "Forklift 3",
        metrics: { batteryPct: 22, voltageSag: 1 },
      }),
      [],
    );
    expect(d?.status).toBe("warning");
  });

  it("bearing vibration → warning", () => {
    const h = [
      reading({
        kind: "forklift",
        context: "Forklift 1",
        metrics: { vibrationMmS: 4 },
      }),
      reading({
        kind: "forklift",
        context: "Forklift 1",
        metrics: { vibrationMmS: 6 },
      }),
    ];
    const d = decideWithRules(
      reading({
        kind: "forklift",
        context: "Forklift 1",
        metrics: { vibrationMmS: 9 },
      }),
      h,
    );
    expect(d?.status).toBe("warning");
  });

  it("normal operation → ok", () => {
    const d = decideWithRules(
      reading({ metrics: { tempC: 5, vibrationMmS: 2 } }),
      [],
    );
    expect(d?.status).toBe("ok");
    expect(d!.latencyMs).toBeLessThan(50);
  });
});
