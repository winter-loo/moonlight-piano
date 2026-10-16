import assert from "node:assert/strict";
import { readFile, mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { runInNewContext } from "node:vm";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { buildBrowserSoundEngine } from "../../scripts/build-browser-sound-engine.mjs";

const controllerSource = await readFile("public/audio/score-piano-controller.js", "utf8");
function makeController(options) {
  const scope = { URL, document: { currentScript: { src: "https://piano.test/public/audio/score-piano-controller.js" } } };
  runInNewContext(controllerSource, scope);
  return new scope.BasicScorePiano(options);
}
function makeContext() {
  return { state: "suspended", currentTime: 10,
    async resume() { this.state = "running"; },
    async close() { this.state = "closed"; } };
}

test("static score schedules independent hand sources through the shared engine", async () => {
  const context = makeContext();
  const batches = [];
  let created = 0;
  let resets = 0;
  let options;
  class Engine {
    constructor(value) { created++; options = value; }
    async start() {}
    snapshot() { return { ready: true }; }
    clock() { return { currentTimeSeconds: 10 }; }
    dispatch(batch) { batches.push(JSON.parse(JSON.stringify(batch))); }
    stopAll() { resets++; }
    async dispose() { await context.close(); }
  }
  const piano = makeController({ createContext: () => context,
    loadEngine: async () => { assert.equal(context.state, "running"); return { PhysicalC4WorkletEngine: Engine }; } });
  await Promise.all([piano.start(), piano.start()]);
  assert.equal(created, 1);
  assert.equal(options.mode, "basic");
  assert.equal(options.wasmUrl, "https://piano.test/public/audio/moonlight_wasm.wasm");
  assert.equal(options.workletUrl, "https://piano.test/public/audio/physical-c4-worklet.js");
  piano.playNote("C3", 1.8, 0.38, "lh", 11);
  piano.playNote("F4", 1.2, 0.44, "rh", 11);
  assert.deepEqual(batches.map(batch => batch[0].note), [48, 65]);
  assert.notEqual(batches[0][0].sourceId, batches[1][0].sourceId);
  assert.equal(batches[0][1].sourceId, batches[0][0].sourceId);
  assert.deepEqual(batches[0][1].time, { kind: "audio-time", seconds: 12.8 });
  piano.playNote("F4", 0.3);
  assert.deepEqual(batches[2][0].time, { kind: "now" });
  piano.stopAll();
  assert.equal(resets, 1);
  await piano.dispose();
  assert.equal(context.state, "closed");
});

test("stop during module loading cancels startup and cannot revive a stopped score", async () => {
  const context = makeContext();
  let finishImport;
  let created = 0;
  const piano = makeController({ createContext: () => context,
    loadEngine: () => new Promise(resolve => { finishImport = resolve; }) });
  const started = piano.start();
  await new Promise(resolve => setImmediate(resolve));
  piano.stopAll();
  finishImport({ PhysicalC4WorkletEngine: class { constructor() { created++; } } });
  await assert.rejects(started, /cancelled/);
  assert.equal(context.state, "closed");
  assert.equal(created, 0);
  assert.equal(piano.context, null);
});

test("a failed WASM startup closes its context and permits a clean retry", async () => {
  const contexts = [];
  let attempts = 0;
  class Engine {
    constructor(options) { this.context = options.context; }
    async start() { if (++attempts === 1) throw new Error("WASM unavailable"); }
    async dispose() { await this.context.close(); }
  }
  const piano = makeController({ createContext: () => { const context = makeContext(); contexts.push(context); return context; },
    loadEngine: async () => ({ PhysicalC4WorkletEngine: Engine }) });
  await assert.rejects(piano.start(), /WASM unavailable/);
  assert.equal(contexts[0].state, "closed");
  await piano.start();
  assert.equal(contexts.length, 2);
  assert.equal(piano.context, contexts[1]);
  await piano.dispose();
});

test("generated browser adapter imports and uses the configured static asset URLs", async (t) => {
  const output = await mkdtemp(path.join(tmpdir(), "score-audio-"));
  const originalFetch = globalThis.fetch;
  const originalNode = globalThis.AudioWorkletNode;
  t.after(async () => { globalThis.fetch = originalFetch; globalThis.AudioWorkletNode = originalNode; await rm(output, { recursive: true, force: true }); });
  await buildBrowserSoundEngine(output);
  await writeFile(path.join(output, "package.json"), '{"type":"module"}');
  const { PhysicalC4WorkletEngine } = await import(pathToFileURL(path.join(output, "physical-c4-worklet-engine.js")).href);
  let fetched;
  let loaded;
  globalThis.fetch = async url => { fetched = url; return { ok: true, arrayBuffer: async () => new ArrayBuffer(8) }; };
  globalThis.AudioWorkletNode = class {
    constructor() {
      this.port = { onmessage: null, postMessage() {} };
      queueMicrotask(() => this.port.onmessage({ data: { type: "ready", memoryBytes: 0 } }));
    }
    connect() { return this; }
    disconnect() {}
  };
  const context = { ...makeContext(), state: "running", sampleRate: 48000, destination: {},
    audioWorklet: { async addModule(url) { loaded = url; } },
    createGain() { return { gain: { value: 0 }, connect() { return this; }, disconnect() {} }; } };
  const engine = new PhysicalC4WorkletEngine({ context, mode: "basic", wasmUrl: "https://piano.test/assets/piano.wasm", workletUrl: "https://piano.test/assets/piano.js" });
  await engine.start();
  assert.equal(fetched, "https://piano.test/assets/piano.wasm");
  assert.equal(loaded, "https://piano.test/assets/piano.js");
  assert.equal(engine.snapshot().ready, true);
  await engine.dispose();
});

test("the checked-in grand staff page is reproducible from its generator", async () => {
  const result = spawnSync("python3", ["-c", "import runpy; ns=runpy.run_path('scripts/generate-bicycle-grand-staff.py'); print(ns['generate_grand_staff_html'](), end='')"], { encoding: "utf8", maxBuffer: 2 * 1024 * 1024 });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, await readFile("docs/practiced-songs/bicycle-built-for-two-grand-staff.html", "utf8"));
});
