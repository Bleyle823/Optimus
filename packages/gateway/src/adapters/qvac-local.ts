import { existsSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/** True when QVAC must not use registry or HTTP fallback (default). */
export function isQvacOfflineMode(): boolean {
  if (process.env.QVAC_ALLOW_NETWORK === "1") return false;
  if (process.env.QVAC_OFFLINE === "0") return false;
  return true;
}

/** Pick the largest matching GGUF under ~/.qvac/models (avoids partial downloads). */
export function resolveCachedGgufPath(): string | null {
  const explicit = process.env.QVAC_LOCAL_GGUF_PATH?.trim();
  if (explicit && existsSync(explicit)) return explicit;

  const dir = join(homedir(), ".qvac", "models");
  if (!existsSync(dir)) return null;

  let best: { path: string; size: number } | null = null;
  for (const name of readdirSync(dir)) {
    if (!name.endsWith(".gguf")) continue;
    if (!name.includes("Llama-3.2-1B-Instruct-Q4_0")) continue;
    const path = join(dir, name);
    try {
      const size = statSync(path).size;
      if (!best || size > best.size) best = { path, size };
    } catch {
      /* skip */
    }
  }
  return best?.path ?? null;
}

export function offlineLoadHint(): string {
  return (
    "Run `pnpm download-models` once with QVAC_ALLOW_NETWORK=1 (or set QVAC_LOCAL_GGUF_PATH to a full GGUF file)."
  );
}
