import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("AudioWorklet process crosses JS/WASM exactly once per quantum", async () => {
  const source = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  const processBody = source.slice(source.indexOf("  process(_inputs, outputs)"), source.indexOf("  fail(message)"));
  const calls = processBody.match(/moonlight_process_block\(/g) ?? [];
  assert.equal(calls.length, 1);
});

test("AudioWorklet render path avoids parsing, allocation syntax, and logging", async () => {
  const source = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  const processBody = source.slice(source.indexOf("  process(_inputs, outputs)"), source.indexOf("  fail(message)"));
  for (const forbidden of ["JSON.parse", "console.", "new Array", "new Float32Array", "new Uint8Array", "new DataView"]) {
    assert.equal(processBody.includes(forbidden), false, forbidden);
  }
});

test("worklet exposes deadline, memory, block-size and underrun telemetry", async () => {
  const source = await readFile("public/audio/physical-c4-worklet.js", "utf8");
  for (const field of ["blockSize", "deadlineRatio", "memoryBytes", "underruns", "lateEvents"]) {
    assert.equal(source.includes(field), true, field);
  }
});
