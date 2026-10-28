import {
  assessModelFit,
  completion,
  loadModel,
  unloadModel,
  LLAMA_3_2_1B_INST_Q4_0,
} from "@qvac/sdk";

export interface QvacCompleteOptions {
  system: string;
  user: string;
  jsonObject?: boolean;
}

export interface QvacAdapter {
  load(): Promise<void>;
  unload(): Promise<void>;
  isReady(): boolean;
  getModelAlias(): string;
  assessFit(): Promise<void>;
  complete(opts: QvacCompleteOptions): Promise<string>;
}

export function createQvacAdapter(modelEnv?: string): QvacAdapter {
  let modelId: string | null = null;
  let loadError: string | null = null;
  const modelSrc =
    modelEnv === "LLAMA_3_2_1B_INST_Q4_0" || !modelEnv
      ? LLAMA_3_2_1B_INST_Q4_0
      : LLAMA_3_2_1B_INST_Q4_0;

  return {
    getModelAlias() {
      return "llama-3.2-1b-instruct";
    },

    async assessFit() {
      try {
        const result = await assessModelFit({
          models: [
            {
              modelSrc,
              modelType: "llamacpp-completion",
              modelConfig: { ctx_size: 2048 },
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

    async load() {
      if (modelId) return;
      try {
        await this.assessFit();
        modelId = await loadModel({
          modelSrc,
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
        loadError = null;
      } catch (e) {
        loadError = e instanceof Error ? e.message : String(e);
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
