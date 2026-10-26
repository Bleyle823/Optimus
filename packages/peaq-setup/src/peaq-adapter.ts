// NETWORK: peaq Machine Markets + peaqOS onboarding — requires internet.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { DiscoveryCache } from "@optimus/shared";

export interface PeaqSetupConfig {
  dbPath: string;
  marketsBaseUrl: string;
  mcrApiUrl: string;
}

export class PeaqAdapter {
  private path: string;

  constructor(private config: PeaqSetupConfig) {
    this.path = config.dbPath.endsWith(".json")
      ? config.dbPath
      : `${config.dbPath}.json`;
    mkdirSync(dirname(this.path), { recursive: true });
    if (!this.read()) {
      writeFileSync(this.path, JSON.stringify({ discovery: null }, null, 2));
    }
  }

  private read(): { discovery: DiscoveryCache | null } | null {
    try {
      return JSON.parse(readFileSync(this.path, "utf8")) as {
        discovery: DiscoveryCache | null;
      };
    } catch {
      return null;
    }
  }

  /** // TODO(verify-docs): wire to Machine Markets pairing + provider registration APIs */
  async cacheDiscovery(entry: DiscoveryCache): Promise<void> {
    writeFileSync(
      this.path,
      JSON.stringify({ discovery: entry }, null, 2),
      "utf8",
    );
  }

  async fetchMcrScore(machineDid: string): Promise<number> {
    const res = await fetch(
      `${this.config.mcrApiUrl}/machines/${encodeURIComponent(machineDid)}`,
    );
    if (!res.ok) return 0;
    const body = (await res.json()) as { score?: number; mcr?: number };
    return body.score ?? body.mcr ?? 0;
  }
}
