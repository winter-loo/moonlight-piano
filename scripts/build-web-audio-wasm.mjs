import { cp, mkdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const result = spawnSync("cargo", [
  "build",
  "--release",
  "-p", "moonlight-wasm",
  "--target", "wasm32-unknown-unknown",
], { cwd: root, stdio: "inherit" });

if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);

const source = path.join(root, "target/wasm32-unknown-unknown/release/moonlight_wasm.wasm");
const outputDir = path.join(root, "public/audio");
await mkdir(outputDir, { recursive: true });
await cp(source, path.join(outputDir, "moonlight_wasm.wasm"));
console.log("Wrote public/audio/moonlight_wasm.wasm");
