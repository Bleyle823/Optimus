import { afterAll, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "optimus-gw-"));
process.env.QVAC_ENABLED = "0";
process.env.GATEWAY_DB_PATH = join(dir, "gateway.json");
process.env.GATEWAY_PRIVATE_KEY =
  "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d";

const { buildServer } = await import("./server.js");

describe("POST /v1/chat/completions", () => {
  it("returns 503 when QVAC is not loaded", async () => {
    const app = await buildServer();
    const res = await app.inject({
      method: "POST",
      url: "/v1/chat/completions",
      payload: {
        messages: [{ role: "user", content: "hello" }],
      },
    });
    expect(res.statusCode).toBe(503);
    expect(res.json()).toEqual({ error: "qvac not ready" });
    await app.close();
  });
});

afterAll(() => {
  rmSync(dir, { recursive: true, force: true });
});
