import { loadRepoEnv } from "@optimus/shared";

loadRepoEnv();

import { createQvacAdapter } from "@optimus/gateway";

if (process.env.OPTIMUS_OFFLINE !== "1") {
  console.warn("Set OPTIMUS_OFFLINE=1 and disable network for a strict offline test.");
}

const qvac = createQvacAdapter(process.env.QVAC_MODEL);
await qvac.load();
if (!qvac.isReady()) {
  console.error("Model failed to load — run pnpm download-models online first.");
  process.exit(1);
}

const text = await qvac.complete({
  system: "Reply with one word: ok",
  user: "ping",
});
console.info("Offline inference result:", text.slice(0, 200));
await qvac.unload();
process.exit(0);
