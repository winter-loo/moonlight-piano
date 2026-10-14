import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const ROOT = path.resolve(import.meta.dirname, "../..");

async function buildFixture(t, wasmExitCode) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "moonlight-build-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const { scripts } = JSON.parse(await readFile(path.join(ROOT, "package.json"), "utf8"));
  await writeFile(path.join(directory, "package.json"), JSON.stringify({
    private: true,
    type: "module",
    scripts,
  }));
  await mkdir(path.join(directory, "scripts"));
  await writeFile(path.join(directory, "scripts/build-web-audio-wasm.mjs"), `
    import { appendFileSync } from "node:fs";
    appendFileSync("steps.txt", "wasm\\n");
    process.exit(${wasmExitCode});
  `);
  await writeFile(path.join(directory, "scripts/run-vinext.mjs"), `
    import { appendFileSync } from "node:fs";
    appendFileSync("steps.txt", process.argv[2] + "\\n");
  `);

  // Run the real npm build command with cheap compiler/bundler stand-ins. The
  // separate test:build regression exercises the actual Rust and Vite output.
  const result = spawnSync("npm", ["run", "build"], {
    cwd: directory,
    encoding: "utf8",
    shell: process.platform === "win32",
    timeout: 30_000,
  });
  assert.ifError(result.error);
  const steps = await readFile(path.join(directory, "steps.txt"), "utf8");
  return { result, steps };
}

test("production build generates WASM before starting the web bundler", async (t) => {
  const { result, steps } = await buildFixture(t, 0);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(steps, "wasm\nbuild\n");
});

test("production build stops when WASM generation fails", async (t) => {
  const { result, steps } = await buildFixture(t, 7);
  assert.notEqual(result.status, 0);
  assert.equal(steps, "wasm\n");
});
