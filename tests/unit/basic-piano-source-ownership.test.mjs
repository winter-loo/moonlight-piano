import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";
import { PhysicalC4WorkletEngine } from "../../lib/audio/physical-c4-worklet-engine.ts";
import { scheduleMidiTone } from "../../lib/audio/scheduler.ts";

// Execute the real processor, capturing its ABI events instead of requiring a
// compiled WASM artifact. The separate basic-piano-worklet test renders real WASM.
async function makeProcessor() {
  const script = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  const memory = { buffer: new ArrayBuffer(262_144) };
  const view = new DataView(memory.buffer);
  const rendered = [];
  const processors = new Map();
  const scope = {
    ArrayBuffer, DataView, Float32Array, Float64Array, Uint8Array,
    sampleRate: 48_000, currentFrame: 0,
    AudioWorkletProcessor: class {
      constructor() { this.port = { onmessage: null, postMessage() {} }; }
    },
    registerProcessor: (name, processor) => processors.set(name, processor),
    WebAssembly: {
      async instantiate() {
        return { instance: { exports: {
          memory,
          moonlight_engine_abi_version: () => 5,
          moonlight_basic_init: () => 0,
          moonlight_event_buffer_ptr: () => 0,
          moonlight_output_buffer_ptr: () => 8192,
          moonlight_active_voices_ptr: () => 4096,
          moonlight_hammer_diagnostics_ptr: () => 4104,
          moonlight_process_block(lo, hi, frames, count) {
            for (let index = 0; index < count; index++) {
              const base = index * 16;
              rendered.push({
                frame: lo + hi * 4294967296 + view.getUint32(base, true),
                kind: view.getUint32(base + 4, true),
                note: view.getUint32(base + 8, true),
                value: view.getFloat32(base + 12, true),
              });
            }
            return 0;
          },
        } } };
      },
    },
  };
  runInNewContext(script, scope);
  const Processor = processors.get("moonlight-basic-piano");
  const processor = new Processor({ processorOptions: { wasmBytes: new ArrayBuffer(8), mode: "basic" } });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(processor.ready, true);
  return {
    processor, rendered,
    send: (message) => processor.port.onmessage({ data: message }),
    render(frame, frames = 128) {
      scope.currentFrame = frame;
      assert.equal(processor.process([], [[new Float32Array(frames), new Float32Array(frames)]]), true);
    },
  };
}

function note(sourceId, kind, frame, pitch = 60, immediate = false) {
  return { type: "event", sourceId, kind, frame, note: pitch, value: 0.75, immediate };
}

async function attachEngine(t, harness) {
  const originalNode = globalThis.AudioWorkletNode;
  const originalFetch = globalThis.fetch;
  const context = {
    state: "running", sampleRate: 48_000, currentTime: 0, destination: {},
    audioWorklet: { async addModule() {} },
    createGain: () => ({ gain: {}, connect() { return this; }, disconnect() {} }),
  };
  globalThis.AudioWorkletNode = class {
    constructor() {
      this.port = { postMessage: harness.send, onmessage: null };
      setImmediate(() => this.port.onmessage?.({ data: { type: "ready", memoryBytes: 262_144 } }));
    }
    connect() { return this; }
    disconnect() {}
  };
  globalThis.fetch = async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) });
  t.after(() => {
    if (originalNode === undefined) delete globalThis.AudioWorkletNode;
    else globalThis.AudioWorkletNode = originalNode;
    globalThis.fetch = originalFetch;
  });
  const engine = new PhysicalC4WorkletEngine({ context, ownsContext: false, mode: "basic" });
  await engine.start();
  return { engine, context };
}

function timings(rendered) {
  return rendered.map(({ frame, kind, note: pitch }) => [frame, kind, pitch]);
}

test("scheduled overlapping same-pitch tones release only at the final source's event time", async (t) => {
  const harness = await makeProcessor();
  const { engine } = await attachEngine(t, harness);
  // Reverse temporal submission order, just as independently scheduled voices
  // can do: each scheduler submits its note-on and future note-off together.
  scheduleMidiTone(engine, 60, 0.02, 0.04, 0.16, "later");
  scheduleMidiTone(engine, 60, 0.01, 0.03, 0.16, "earlier");
  for (let frame = 0; frame < 3072; frame += 128) harness.render(frame);
  assert.deepEqual(timings(harness.rendered), [[480, 1, 60], [960, 1, 60], [2880, 2, 60]]);
});

test("a scheduled source cannot release a live same-pitch key", async (t) => {
  const harness = await makeProcessor();
  const { engine, context } = await attachEngine(t, harness);
  engine.dispatch({ type: "note-on", sourceId: "live", note: 60, velocity: 0.75 });
  scheduleMidiTone(engine, 60, 0.01, 0.01, 0.16, "scheduled");
  for (let frame = 0; frame < 1280; frame += 128) harness.render(frame);
  assert.deepEqual(timings(harness.rendered), [[256, 1, 60], [480, 1, 60]]);
  context.currentTime = 1280 / 48_000;
  engine.dispatch({ type: "note-off", sourceId: "live", note: 60, releaseVelocity: 0.75 });
  harness.render(1280); harness.render(1408); harness.render(1536);
  assert.deepEqual(timings(harness.rendered).at(-1), [1536, 2, 60]);
});

test("duplicate, mismatched and missing source events do not corrupt another hold", async () => {
  const harness = await makeProcessor();
  harness.send(note("a", 1, 10));
  harness.send(note("b", 1, 20));
  harness.send(note("a", 1, 30));
  harness.send(note("missing", 2, 40));
  harness.send(note("a", 2, 50, 61));
  harness.send(note("a", 2, 60));
  harness.send(note("a", 2, 70));
  harness.send(note("b", 2, 80));
  harness.send(note("a", 1, 90));
  harness.send(note("a", 2, 100));
  harness.render(0);
  assert.deepEqual(timings(harness.rendered), [[10, 1, 60], [20, 1, 60], [80, 2, 60], [90, 1, 60], [100, 2, 60]]);
});

test("expired absolute onsets acquire no hold and their release cannot stop a live source", async () => {
  const harness = await makeProcessor();
  harness.send(note("live", 1, 10));
  harness.render(0);
  harness.send(note("expired", 1, 20));
  harness.send(note("expired", 2, 140));
  harness.send(note("now", 1, 20, 60, true));
  harness.send(note("live", 2, 160));
  harness.send(note("now", 2, 170));
  harness.render(128);
  assert.deepEqual(timings(harness.rendered), [[10, 1, 60], [128, 1, 60], [170, 2, 60]]);
});

test("reset cancels future notes and clears ownership at its scheduled frame", async () => {
  const harness = await makeProcessor();
  harness.send(note("a", 1, 10));
  harness.send(note("cancelled", 1, 800));
  harness.render(0);
  harness.send({ type: "reset", frame: 150 });
  harness.send(note("a", 1, 140)); // Duplicate until the reset executes.
  harness.send(note("a", 1, 160)); // Same source is available after reset.
  harness.send(note("a", 2, 170));
  for (let frame = 128; frame < 1024; frame += 128) harness.render(frame);
  assert.deepEqual(timings(harness.rendered), [[10, 1, 60], [150, 3, 60], [160, 1, 60], [170, 2, 60]]);
});

test("queue-overflow safety reset clears holds so sources can be used again", async () => {
  const harness = await makeProcessor();
  harness.send(note("a", 1, 10));
  harness.render(0);
  for (let index = 0; index < 256; index++) harness.send(note(`future-${index}`, 1, 10_000 + index));
  harness.send(note("a", 2, 20_000));
  harness.render(128);
  harness.send(note("a", 1, 260));
  harness.send(note("a", 2, 270));
  harness.render(256);
  assert.deepEqual(timings(harness.rendered), [[10, 1, 60], [128, 3, 60], [260, 1, 60], [270, 2, 60]]);
});

test("source ownership is bounded and a rejected extra source cannot release held keys", async () => {
  const harness = await makeProcessor();
  for (let index = 0; index < 256; index++) harness.send(note(`held-${index}`, 1, 10));
  harness.render(0);
  harness.send(note("extra", 1, 140));
  harness.send(note("extra", 2, 150));
  harness.render(128);
  assert.equal(harness.processor.overflowEvents, 1);
  assert.equal(harness.rendered.length, 256);
  for (let index = 0; index < 256; index++) harness.send(note(`held-${index}`, 2, 270));
  harness.render(256);
  assert.deepEqual(timings(harness.rendered).at(-1), [270, 2, 60]);
  assert.equal(harness.rendered.length, 257);
  harness.send(note("extra", 1, 390));
  harness.send(note("extra", 2, 400));
  harness.render(384);
  assert.deepEqual(timings(harness.rendered).slice(-2), [[390, 1, 60], [400, 2, 60]]);
});

test("same-frame release and retrigger preserve stable submission order", async () => {
  const harness = await makeProcessor();
  harness.send(note("a", 1, 10));
  harness.send(note("a", 2, 128));
  harness.send(note("a", 1, 128));
  harness.send(note("a", 2, 140));
  harness.render(0);
  harness.render(128);
  assert.deepEqual(timings(harness.rendered), [[10, 1, 60], [128, 2, 60], [128, 1, 60], [140, 2, 60]]);
});
