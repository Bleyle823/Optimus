import type { Decision, TelemetryReading } from "./schemas.js";

function parseTempRange(context: string): { min: number; max: number } | null {
  const m = context.match(/(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)\s*C/i);
  if (!m) return null;
  return { min: Number(m[1]), max: Number(m[2]) };
}

export function decideWithRules(
  reading: TelemetryReading,
  history: TelemetryReading[],
): Decision | null {
  const start = performance.now();
  const metrics = reading.metrics;

  if (reading.kind === "cold_room" || metrics.tempC !== undefined) {
    const temp = metrics.tempC;
    if (temp !== undefined) {
      const range = parseTempRange(reading.context);
      if (range && (temp < range.min || temp > range.max)) {
        return {
          status: temp > range.max ? "critical" : "warning",
          reason:
            temp > range.max
              ? `Temperature ${temp}C exceeds safe range ${range.min}-${range.max}C`
              : `Temperature ${temp}C below safe range`,
          action:
            temp > range.max
              ? "Check compressor, move stock to backup cold room"
              : "Inspect cooling unit and sensors",
          source: "rules",
          latencyMs: performance.now() - start,
        };
      }
    }
    if (metrics.mainsLost === 1 && (metrics.batteryPct ?? 100) < 40) {
      return {
        status: "warning",
        reason: "Mains lost; backup battery draining",
        action: "Confirm backup power, estimate time to threshold",
        source: "rules",
        latencyMs: performance.now() - start,
      };
    }
  }

  if (reading.kind === "forklift" || metrics.batteryPct !== undefined) {
    const battery = metrics.batteryPct;
    if (battery !== undefined && battery <= 25) {
      const sag = metrics.voltageSag ?? 0;
      return {
        status: battery <= 15 ? "critical" : "warning",
        reason: `Battery ${battery}%${sag > 0 ? ", voltage sag under load" : ""}`,
        action: "Return to charging bay",
        source: "rules",
        latencyMs: performance.now() - start,
      };
    }
    const vib = metrics.vibrationMmS;
    if (vib !== undefined && vib >= 8) {
      const prev = history.map((h) => h.metrics.vibrationMmS ?? 0);
      const rising =
        prev.length >= 2 && prev.every((p, i) => i === 0 || p <= (prev[i] ?? 0));
      if (rising || vib >= 12) {
        return {
          status: vib >= 12 ? "critical" : "warning",
          reason: `Vibration ${vib} mm/s elevated over recent readings`,
          action: "Schedule bearing maintenance",
          source: "rules",
          latencyMs: performance.now() - start,
        };
      }
    }
  }

  const range = parseTempRange(reading.context);
  if (range && metrics.tempC !== undefined) {
    const temp = metrics.tempC;
    const nearHigh = temp > range.max - 1;
    if (nearHigh && temp <= range.max) {
      return {
        status: "warning",
        reason: `Temperature ${temp}C approaching upper limit`,
        action: "Monitor closely and prep contingency",
        source: "rules",
        latencyMs: performance.now() - start,
      };
    }
  }

  const allOk =
    (!metrics.tempC ||
      (range &&
        metrics.tempC >= range.min &&
        metrics.tempC <= range.max)) &&
    (metrics.batteryPct === undefined || metrics.batteryPct > 25) &&
    (metrics.vibrationMmS === undefined || metrics.vibrationMmS < 8);

  if (allOk) {
    return {
      status: "ok",
      reason: "Readings within expected operating range",
      action: "Continue normal operation",
      source: "rules",
      latencyMs: performance.now() - start,
    };
  }

  return null;
}
