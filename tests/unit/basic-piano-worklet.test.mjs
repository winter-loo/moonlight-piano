import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

test("analytic 88-key WASM renders chords through the actual AudioWorklet processor", async (t) => {
  const script = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  const wasm = await readFile("public/audio/moonlight_wasm.wasm").catch((error) => {
    if (error.code === "ENOENT") {
      t.skip("Build the browser module with npm run audio:wasm to exercise the WASM path.");
      return null;
    }
    throw error;
  });
  if (!wasm) return;
  const processors = new Map();
  const notices = [];
  const scope = {
    ArrayBuffer, DataView, Float32Array, Float64Array, Uint8Array, WebAssembly,
    performance, sampleRate: 48_000, currentFrame: 0,
    AudioWorkletProcessor: class {
      constructor() {
        this.port = { onmessage: null, postMessage: (message) => notices.push(message) };
      }
    },
    registerProcessor: (name, processor) => processors.set(name, processor),
  };
  runInNewContext(script, scope);
  const Processor = processors.get("moonlight-basic-piano");
  assert.equal(typeof Processor, "function");
  const bytes = wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength);
  const processor = new Processor({ processorOptions: { wasmBytes: bytes, mode: "basic" } });
  const deadline = Date.now() + 2000;
  while (!processor.ready && !processor.failed && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal(processor.ready, true, JSON.stringify(notices));

  for (const note of [21, 60, 108]) {
    processor.port.onmessage({ data: { type: "event", frame: 17, kind: 1, note, value: 0.8 } });
  }
  const channel = new Float32Array(128);
  const right = new Float32Array(128);
  processor.process([], [[channel, right]]);
  assert.ok(channel.subarray(0, 17).every((sample) => sample === 0));
  assert.ok(channel.subarray(17).some((sample) => sample !== 0));
  assert.ok(channel.every(Number.isFinite));
  assert.ok(right.every(Number.isFinite));
  assert.ok(channel.some((sample, index) => sample !== right[index]));

  scope.currentFrame = 128;
  processor.port.onmessage({ data: { type: "reset", frame: 128 } });
  channel.fill(1);
  right.fill(1);
  processor.process([], [[channel, right]]);
  assert.ok(channel.every((sample) => sample === 0));
  assert.ok(right.every((sample) => sample === 0));

  scope.currentFrame = 256;
  processor.port.onmessage({ data: { type: "event", frame: 256, kind: 1, note: 60, value: 0.8 } });
  processor.process([], [[channel, right]]);
  assert.ok(channel.some((sample) => sample !== 0));
  for (let index = 0; index < 256; index++) {
    processor.port.onmessage({ data: { type: "event", frame: 20_000 + index, kind: 1, note: 60, value: 0.8 } });
  }
  // A far-future release must still force a reset on the next quantum.
  processor.port.onmessage({ data: { type: "event", frame: 20_500, kind: 2, note: 60, value: 0.5 } });
  scope.currentFrame = 384;
  processor.process([], [[channel, right]]);
  assert.ok(channel.every((sample) => sample === 0));
  assert.equal(processor.overflowEvents, 1);
});
