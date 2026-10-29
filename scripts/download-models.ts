import { createQvacAdapter } from "@optimus/gateway";

process.env.QVAC_ALLOW_NETWORK = "1";
const qvac = createQvacAdapter(process.env.QVAC_MODEL);
console.info("Downloading / loading QVAC model (cached for offline use)...");
await qvac.assessFit();
await qvac.load();
if (!qvac.isReady()) {
  console.error("Model failed to load. Check network and retry pnpm download-models.");
  process.exit(1);
}
console.info("Model ready:", qvac.getModelAlias());
await qvac.unload();
console.info("Done. Weights should be cached locally.");
