import {
  assessModelFit,
  completion,
  loadModel,
  unloadModel,
  LLAMA_3_2_1B_INST_Q4_0,
} from "@qvac/sdk";
import {
  isQvacOfflineMode,
  offlineLoadHint,
  resolveCachedGgufPath,
} from "./qvac-local.js";

export interface QvacCompleteOptions {
  system: string;
  user: string;
  jsonObject?: boolean;
}

export interface QvacLoadSummary {
  ready: boolean;
  offline: boolean;
  localPath: string | null;
  error: string | null;
  loadMs: number;
}

export interface QvacAdapter {
  load(): Promise<void>;
  unload(): Promise<void>;
  isReady(): boolean;
  getModelAlias(): string;
  getLoadSummary(): QvacLoadSummary | null;
  assessFit(): Promise<void>;
  complete(opts: QvacCompleteOptions): Promise<string>;
}

const LOCAL_MODEL_TYPE = "llamacpp-completion" as const;
const LOCAL_MODEL_CONFIG = { ctx_size: 2048 };

export function createQvacAdapter(modelEnv?: string): QvacAdapter {
  let modelId: string | null = null;
  let loadError: string | null = null;
  let loadSummary: QvacLoadSummary | null = null;
  const registryModelSrc =
    modelEnv === "LLAMA_3_2_1B_INST_Q4_0" || !modelEnv
      ? LLAMA_3_2_1B_INST_Q4_0
      : LLAMA_3_2_1B_INST_Q4_0;

  return {
    getModelAlias() {
      return "llama-3.2-1b-instruct";
    },

    async assessFit() {
      try {
        const offline = isQvacOfflineMode();
        const localPath = offline ? resolveCachedGgufPath() : null;
        const modelSrc = localPath ?? registryModelSrc;
        const result = await assessModelFit({
          models: [
            {
              modelSrc,
              modelType: LOCAL_MODEL_TYPE,
              modelConfig: LOCAL_MODEL_CONFIG,
            },
          ],
        });
        console.info("[QvacAdapter] assessModelFit:", JSON.stringify(result));
      } catch (e) {
        console.warn("[QvacAdapter] assessModelFit skipped:", e);
      }
    },

    isReady() {
      return modelId !== null && loadError === null;
    },

    getLoadSummary() {
      return loadSummary;
    },

    async load() {
      if (modelId) return;
      const started = performance.now();
      const offline = isQvacOfflineMode();
      let localPath: string | null = null;
      try {
        console.info(
          `[QvacAdapter] loading ${offline ? "offline (local GGUF)" : "network (registry allowed)"}…`,
        );
        await this.assessFit();

        if (offline) {
          localPath = resolveCachedGgufPath();
          if (!localPath) {
            throw new Error(
              `No local GGUF found for offline QVAC. ${offlineLoadHint()}`,
            );
          }
          console.info("[QvacAdapter] offline load from", localPath);
          modelId = await loadModel({
            modelSrc: localPath,
            modelType: LOCAL_MODEL_TYPE,
            modelConfig: LOCAL_MODEL_CONFIG,
          });
        } else {
          console.info("[QvacAdapter] network load (registry / fallback allowed)");
          modelId = await loadModel({
            modelSrc: registryModelSrc,
            fallbackSrc:
              process.env.QVAC_FALLBACK_SRC ??
              "https://huggingface.co/unsloth/Llama-3.2-1B-Instruct-GGUF/resolve/b69aef112e9f895e6f98d7ae0949f72ff09aa401/Llama-3.2-1B-Instruct-Q4_0.gguf",
            onProgress: (p) => {
              if (p.percentage >= 100 || Math.floor(p.percentage) % 25 === 0) {
                console.info(
                  `[QvacAdapter] download ${p.percentage.toFixed(0)}%`,
                );
              }
            },
          });
        }
        loadError = null;
        loadSummary = {
          ready: true,
          offline,
          localPath,
          error: null,
          loadMs: performance.now() - started,
        };
        console.info(
          `[QvacAdapter] ready (${loadSummary.loadMs.toFixed(0)} ms) alias=${this.getModelAlias()}`,
        );
      } catch (e) {
        loadError = e instanceof Error ? e.message : String(e);
        loadSummary = {
          ready: false,
          offline,
          localPath,
          error: loadError,
          loadMs: performance.now() - started,
        };
        console.error("[QvacAdapter] load failed:", loadError);
        modelId = null;
      }
    },

    async unload() {
      if (modelId) {
        await unloadModel({ modelId });
        modelId = null;
      }
    },

    async complete(opts) {
      if (!modelId) {
        throw new Error("QVAC model not loaded");
      }
      const run = completion({
        modelId,
        history: [
          { role: "system", content: opts.system },
          { role: "user", content: opts.user },
        ],
        stream: false,
        ...(opts.jsonObject
          ? { responseFormat: { type: "json_object" as const } }
          : {}),
      });
      const final = await run.final;
      const raw = final as {
        raw?: { fullText?: string };
        text?: string;
        assistantMessage?: { content?: string };
      };
      const text =
        raw.assistantMessage?.content ??
        raw.raw?.fullText ??
        raw.text ??
        "";
      return text.trim();
    },
  };
}
