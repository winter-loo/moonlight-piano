import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(import.meta.dirname, "../..");

test("a clean production build ships the playable piano WASM and worklet", async () => {
  // Do not let a previous local audio:wasm or Vite build hide a missing build
  // dependency. These are generated, ignored artifacts; source stays intact.
  await rm(path.join(ROOT, "public/audio/moonlight_wasm.wasm"), { force: true });
  for (const name of ["sound-engine.js", "physical-c4-worklet-engine.js"]) {
    await rm(path.join(ROOT, "public/audio", name), { force: true });
  }
  await rm(path.join(ROOT, "dist"), { recursive: true, force: true });

  const result = spawnSync("npm", ["run", "build"], {
    cwd: ROOT,
    stdio: "inherit",
    shell: process.platform === "win32",
    timeout: 300_000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, "npm run build must succeed from clean audio assets");

  const generatedWasm = await readFile(path.join(ROOT, "public/audio/moonlight_wasm.wasm"));
  const deployedWasm = await readFile(path.join(ROOT, "dist/client/audio/moonlight_wasm.wasm"));
  assert.deepEqual(deployedWasm, generatedWasm, "the deployed WASM must match this build's module");
  const wasmModule = await WebAssembly.compile(deployedWasm);
  const exports = new Map(WebAssembly.Module.exports(wasmModule).map(({ name, kind }) => [name, kind]));
  assert.equal(exports.get("memory"), "memory");
  for (const name of [
    "moonlight_engine_abi_version",
    "moonlight_basic_init",
    "moonlight_engine_init",
    "moonlight_event_buffer_ptr",
    "moonlight_output_buffer_ptr",
    "moonlight_active_voices_ptr",
    "moonlight_hammer_diagnostics_ptr",
    "moonlight_process_block",
  ]) {
    assert.equal(exports.get(name), "function", `missing AudioWorklet ABI export: ${name}`);
  }
  assert.deepEqual(
    await readFile(path.join(ROOT, "dist/client/audio/physical-c4-worklet.js")),
    await readFile(path.join(ROOT, "public/audio/physical-c4-worklet.js")),
    "the deployed worklet must match the current processor",
  );
  for (const name of ["sound-engine.js", "physical-c4-worklet-engine.js", "score-piano-controller.js"]) {
    assert.deepEqual(
      await readFile(path.join(ROOT, "dist/client/audio", name)),
      await readFile(path.join(ROOT, "public/audio", name)),
      `the deployed static-score module must match this build: ${name}`,
    );
  }
});
