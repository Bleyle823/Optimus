import { Bonjour } from "bonjour-service";

export async function discoverGatewayUrl(
  fallbackUrl: string,
  timeoutMs = 3000,
): Promise<string> {
  return new Promise((resolve) => {
    const bonjour = new Bonjour();
    let resolved = false;
    const done = (url: string) => {
      if (resolved) return;
      resolved = true;
      bonjour.destroy();
      resolve(url);
    };
    const browser = bonjour.find({ type: "optimus-gateway" });
    browser.on("up", (service) => {
      const host = service.referer?.address ?? service.host;
      const port = service.port;
      if (host && port) {
        done(`http://${host}:${port}`);
      }
    });
    setTimeout(() => done(fallbackUrl), timeoutMs);
  });
}
