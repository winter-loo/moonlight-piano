// This runs the actual production WASM in Node's WebAssembly runtime. Browser
// routing/UI coverage is separate; no fake DSP can satisfy this conformance test.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let temporary;
let wasm;

before(async () => {
  temporary = await mkdtemp(path.join(tmpdir(), "moonlight-hammer-parity-"));
  const build = spawnSync("cargo", ["build", "--release", "-p", "moonlight-dsp", "--example", "hammer_sweep"], {
    cwd: root, encoding: "utf8",
  });
  assert.equal(build.error, undefined, build.error?.message);
  assert.equal(build.status, 0, build.stderr);
  wasm = await readFile(path.join(root, "public/audio/moonlight_wasm.wasm"));
});

after(async () => { if (temporary) await rm(temporary, { recursive: true, force: true }); });

function readFloatPcm(buffer) {
  const samples = new Float32Array(buffer.length / 4);
  for (let index = 0; index < samples.length; index += 1) samples[index] = buffer.readFloatLE(index * 4);
  return samples;
}

for (const rate of [44_100, 48_000]) {
  test(`actual C4 WASM matches native PCM and contact state at ${rate} Hz`, async () => {
    let reference;
    for (const block of [64, 128, 512]) {
      const fixture = path.join(temporary, `${rate}-${block}.f32le`);
      const renderer = path.join(root, "target/release/examples/hammer_sweep");
      const result = spawnSync(renderer, ["--parity", fixture, String(rate), String(block)], {
        cwd: root, encoding: "utf8",
      });
      assert.equal(result.error, undefined, result.error?.message);
      assert.equal(result.status, 0, result.stderr);
      const native = readFloatPcm(await readFile(fixture));
      const events = (await readFile(fixture.replace(/\.f32le$/, ".events.csv"), "utf8"))
        .split("\n").filter(line => line && !line.startsWith("#"))
        .map(line => line.split(",").map(Number));
      const expectedDiagnostics = (await readFile(fixture.replace(/\.f32le$/, ".diagnostics.csv"), "utf8"))
        .trim().split("\n").map(line => line.split(",").map(Number));
      assert.equal(events.length, 9);
      assert.equal(native.length, Math.floor(rate / 2));
      if (reference) assert.deepEqual(native, reference, "block partitioning must not change native PCM");
      else reference = native;

      const { instance } = await WebAssembly.instantiate(wasm, {});
      const api = instance.exports;
      assert.equal(api.moonlight_engine_abi_version(), 5);
      assert.equal(api.moonlight_engine_init(rate, 0x243f6a88, 0x85a308d3), 0);
      const eventPtr = api.moonlight_event_buffer_ptr();
      const outputPtr = api.moonlight_output_buffer_ptr();
      const diagnosticPtr = api.moonlight_hammer_diagnostics_ptr();
      const memory = api.memory.buffer;
      const view = new DataView(memory);
      const rendered = new Float32Array(native.length);
      let diagnosticIndex = 0;
      let maxError = 0;
      let energy = 0;
      let errorEnergy = 0;
      let maximumForce = 0;
      for (let start = 0; start < native.length; start += block) {
        const end = Math.min(native.length, start + block);
        const due = events.filter(event => event[0] >= start && event[0] < end);
        for (const [index, [frame, kind, note, value]] of due.entries()) {
          const offset = eventPtr + index * 16;
          view.setUint32(offset, frame - start, true);
          view.setUint32(offset + 4, kind, true);
          view.setUint32(offset + 8, note, true);
          view.setFloat32(offset + 12, value, true);
        }
        assert.equal(api.moonlight_process_block(start, 0, end - start, due.length), 0);
        assert.equal(api.memory.buffer, memory, "render must not grow WASM memory");
        for (let index = start; index < end; index += 1) {
          const sample = view.getFloat32(outputPtr + (index - start) * 4, true);
          assert.ok(Number.isFinite(sample));
          rendered[index] = sample;
          const error = sample - native[index];
          maxError = Math.max(maxError, Math.abs(error));
          errorEnergy += error * error;
          energy += native[index] * native[index];
        }
        const expected = expectedDiagnostics[diagnosticIndex++];
        assert.equal(expected[0], end);
        for (let index = 0; index < 15; index += 1) {
          const value = view.getFloat64(diagnosticPtr + index * 8, true);
          const tolerance = 1e-9 + Math.abs(expected[index + 1]) * 1e-6;
          assert.ok(Number.isFinite(value));
          assert.ok(Math.abs(value - expected[index + 1]) <= tolerance,
            `diagnostic ${index} frame ${end}: native ${expected[index + 1]}, WASM ${value}`);
          if (index === 1) maximumForce = Math.max(maximumForce, value);
        }
      }
      assert.equal(diagnosticIndex, expectedDiagnostics.length);
      assert.ok(energy > 1e-10, "conformance cannot pass on silence");
      assert.ok(maximumForce > 0, "contact diagnostics must report a physical strike");
      assert.ok(rendered.subarray(0, 17).every(sample => sample === 0), "event timing must preserve leading silence");
      assert.ok(rendered.subarray(Math.floor(rate * 9 / 20)).every(sample => sample === 0), "reset must silence the exact scheduled frame");
      assert.ok(maxError <= 2e-6, `maximum sample error ${maxError}`);
      const relativeRmsError = Math.sqrt(errorEnergy / energy);
      assert.ok(relativeRmsError <= 1e-5, `relative RMS error ${relativeRmsError}`);
      console.log(JSON.stringify({ sampleRate: rate, blockSize: block, maxSampleError: maxError,
        relativeRmsError, maximumForceNewtons: maximumForce }));
    }
  });
}
