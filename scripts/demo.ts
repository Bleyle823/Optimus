import { loadRepoEnv } from "@optimus/shared";

loadRepoEnv();

const agentUrl = process.env.MACHINE_AGENT_URL ?? "http://127.0.0.1:4040";

await fetch(`${agentUrl}/fault`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ scenario: "cold_room_drift" }),
});

const telemetry = {
  machineId: "peaqos:machine:demo",
  kind: "cold_room",
  timestamp: new Date().toISOString(),
  metrics: { tempC: 9, compressorCurrent: 0.2 },
  context: "Cold room B, flowers, safe range 2 to 8 C",
};

const res = await fetch(`${agentUrl}/telemetry`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(telemetry),
});

console.info("Demo response:", await res.json());
