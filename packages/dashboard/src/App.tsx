import { useEffect, useState } from "react";

type Decision = {
  status: string;
  reason: string;
  action: string;
  source: string;
  latencyMs: number;
};

const gatewayWs =
  import.meta.env.VITE_GATEWAY_WS ?? "ws://127.0.0.1:3030/ws";
const agentUrl = import.meta.env.VITE_AGENT_URL ?? "http://127.0.0.1:4040";

export default function App() {
  const [online, setOnline] = useState(navigator.onLine);
  const [events, setEvents] = useState<
    { telemetry?: unknown; decision?: Decision; receipt?: unknown }[]
  >([]);

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  useEffect(() => {
    const ws = new WebSocket(gatewayWs);
    ws.onmessage = (msg) => {
      try {
        setEvents((e) => [JSON.parse(msg.data), ...e].slice(0, 50));
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, []);

  async function trigger(scenario: string) {
    await fetch(`${agentUrl}/fault`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scenario }),
    });
  }

  return (
    <div className="min-h-screen p-6 max-w-5xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Optimus — Nairobi warehouse</h1>
        <span
          className={`px-3 py-1 rounded-full text-sm font-medium ${
            online ? "bg-emerald-900 text-emerald-200" : "bg-amber-900 text-amber-100"
          }`}
        >
          {online ? "ONLINE" : "OFFLINE (LAN inference)"}
        </span>
      </header>

      <section className="flex gap-2 flex-wrap">
        {[
          ["cold_room_drift", "Cold room drift"],
          ["battery_fade", "Forklift battery fade"],
          ["vibration_spike", "Vibration spike"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            className="px-3 py-2 bg-slate-800 rounded hover:bg-slate-700 text-sm"
            onClick={() => trigger(id)}
          >
            {label}
          </button>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Live decisions</h2>
        {events.length === 0 && (
          <p className="text-slate-400 text-sm">Waiting for gateway WebSocket events…</p>
        )}
        {events.map((ev, i) => (
          <article
            key={i}
            className="border border-slate-800 rounded-lg p-4 bg-slate-900/50"
          >
            {ev.decision && (
              <div className="flex gap-2 items-center mb-2">
                <span className="uppercase text-xs tracking-wide text-slate-400">
                  {ev.decision.status}
                </span>
                <span className="text-xs px-2 py-0.5 rounded bg-slate-800">
                  {ev.decision.source}
                </span>
                <span className="text-xs text-slate-500">
                  {ev.decision.latencyMs.toFixed(0)} ms
                </span>
              </div>
            )}
            <p className="text-sm">{ev.decision?.reason}</p>
            <p className="text-sm text-slate-400">{ev.decision?.action}</p>
          </article>
        ))}
      </section>
    </div>
  );
}
