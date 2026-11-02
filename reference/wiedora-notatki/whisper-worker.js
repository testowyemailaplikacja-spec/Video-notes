/* Transkrypcja lokalna: model działa w przeglądarce. Dźwięk NIGDY nie jest wysyłany do backendu. */
const LIBRARY = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/transformers.min.js";
const MODELS = {tiny:"onnx-community/whisper-tiny",base:"onnx-community/whisper-base"};
let pipe = null;
let actualModel = null;

function report(event,extra={}) { self.postMessage({type:event,...extra}); }

self.onmessage = async ({data}) => {
  if (!data || typeof data !== "object") return;
  try {
    if (data.type === "init") {
      const choice = MODELS[data.model] ? data.model : "tiny";
      let hasWebGPU = false;
      if (!data.forceCPU && self.navigator?.gpu) {
        try { hasWebGPU = !!(await self.navigator.gpu.requestAdapter()); } catch {}
      }
      const device = hasWebGPU ? "webgpu" : "wasm";
      const model = MODELS[choice];
      report("status",{text:"Ładowanie lokalnego modelu " + choice + " (" + (hasWebGPU ? "WebGPU" : "CPU") + ")…"});
      const {pipeline,env} = await import(LIBRARY);
      env.allowLocalModels = false;
      env.backends.onnx.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/";
      env.backends.onnx.wasm.numThreads = 1;
      env.allowRemoteModels = true;
      env.useBrowserCache = true;
      const callback = data => {
        if (!data || !["progress","download","initiate","done"].includes(data.status)) return;
        report("download",{status:data.status,file:String(data.file||""),progress:Number.isFinite(data.progress)?data.progress:null});
      };
      const config = device === "webgpu"
        ? {device:"webgpu",dtype:{encoder_model:"fp32",decoder_model_merged:"q4"},progress_callback:callback}
        : {device:"wasm",dtype:"q8",progress_callback:callback};
      try {
        pipe = await pipeline("automatic-speech-recognition",model,config);
        actualModel = choice;
        report("ready",{device,model:choice});
      } catch (gpuError) {
        if (device !== "webgpu") throw gpuError;
        // A failed ORT initialization can poison its module-level promise chain.
        // Ask the caller for a fresh worker before trying CPU.
        report("error",{message:"WebGPU nie uruchomiło modelu. Ponawiam na CPU…",retryCPU:true});
      }
      return;
    }
    if (data.type === "transcribe") {
      if (!pipe) throw new Error("Model nie został załadowany.");
      const audio = data.audio;
      if (!(audio instanceof Float32Array) || !audio.length) throw new Error("Brak danych audio.");
      // Whisper otrzymuje próbki mono / 16000 Hz w kawałkach krótszych niż 30 s.
      const result = await pipe(audio, {language:"polish",task:"transcribe"});
      report("result",{index:data.index,text:String(result?.text||"").trim(),model:actualModel});
    }
  } catch (error) {
    report("error",{message:String(error?.message||error||"Nieznany błąd modelu.")});
  }
};