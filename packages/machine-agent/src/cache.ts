import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { DiscoveryCache } from "@optimus/shared";

interface AgentFile {
  discovery: DiscoveryCache | null;
  spend: Record<string, number>;
  telemetryLog: string[];
}

export class AgentStore {
  private path: string;
  private data: AgentFile;

  constructor(path: string) {
    this.path = path.endsWith(".json") ? path : `${path}.json`;
    mkdirSync(dirname(this.path), { recursive: true });
    try {
      this.data = JSON.parse(readFileSync(this.path, "utf8")) as AgentFile;
    } catch {
      this.data = { discovery: null, spend: {}, telemetryLog: [] };
      this.flush();
    }
  }

  private flush() {
    writeFileSync(this.path, JSON.stringify(this.data, null, 2), "utf8");
  }

  setDiscovery(cache: DiscoveryCache) {
    this.data.discovery = cache;
    this.flush();
  }

  getDiscovery(): DiscoveryCache | null {
    return this.data.discovery;
  }

  addSpend(amount: number) {
    const day = new Date().toISOString().slice(0, 10);
    this.data.spend[day] = (this.data.spend[day] ?? 0) + amount;
    this.flush();
  }

  getSpendToday(): number {
    const day = new Date().toISOString().slice(0, 10);
    return this.data.spend[day] ?? 0;
  }

  logTelemetry(payload: string) {
    this.data.telemetryLog.push(payload);
    if (this.data.telemetryLog.length > 500) {
      this.data.telemetryLog = this.data.telemetryLog.slice(-500);
    }
    this.flush();
  }
}
