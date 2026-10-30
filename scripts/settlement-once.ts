import { spawnSync } from "node:child_process";
import {
  loadRepoEnv,
  prepareLedgerForOnline,
  resolveGatewayLedgerPath,
} from "@optimus/shared";

const repoRoot = loadRepoEnv();
const ledgerPath = resolveGatewayLedgerPath(repoRoot);
prepareLedgerForOnline({
  ledgerPath,
  repoRoot,
  requeueFailed: true,
  resetKiosk: false,
});
const r = spawnSync(
  process.execPath,
  ["packages/settlement/dist/worker.js"],
  {
    cwd: repoRoot ?? process.cwd(),
    env: { ...process.env, SETTLEMENT_ONCE: "1" },
    stdio: "inherit",
  },
);
process.exit(r.status ?? 1);
