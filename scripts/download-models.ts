import { createQvacAdapter } from "@optimus/gateway";

const qvac = createQvacAdapter(process.env.QVAC_MODEL);
console.info("Downloading / loading QVAC model (cached for offline use)...");
await qvac.assessFit();
await qvac.load();
console.info("Model ready:", qvac.getModelAlias());
await qvac.unload();
console.info("Done. Weights should be cached locally.");
