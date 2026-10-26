import type { TelemetryReading } from "@optimus/shared";

export function coldRoomDriftSequence(
  machineId: string,
): TelemetryReading[] {
  const context = "Cold room B, flowers, safe range 2 to 8 C";
  const temps = [4, 5, 6, 7, 8, 9];
  return temps.map((tempC, i) => ({
    machineId,
    kind: "cold_room" as const,
    timestamp: new Date(Date.now() + i * 60_000).toISOString(),
    metrics: { tempC, compressorCurrent: 1.2 - i * 0.15 },
    context,
  }));
}
