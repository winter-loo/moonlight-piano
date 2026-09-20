#!/usr/bin/env node
// Registry-backed preparation. No sealed outer-test data is read by this tool.
import { createHash } from "node:crypto";
import { mkdir, readFile, realpath, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadAndValidateRegistry, verifyAssetBuffer } from "./acoustic-data-registry.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const hash = (data) => createHash("sha256").update(data).digest("hex");
const inspectable = new Set(["calibration", "development-validation", "cross-piano-validation"]);
const identifier = (value) => typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(value);

export async function prepareAnalysisJob({ caseId, outputPath, fetchImpl = fetch }) {
  const validated = await loadAndValidateRegistry();
  const cataloguePath = path.join(ROOT, "data/acoustic/analysis-cases.json");
  const catalogueBytes = await readFile(cataloguePath);
  const catalogue = JSON.parse(catalogueBytes);
  if (catalogue.schemaVersion !== 1 || !Array.isArray(catalogue.cases)) throw new Error("invalid case catalogue");
  const matches = catalogue.cases.filter((item) => item.id === caseId);
  if (matches.length !== 1) throw new Error("case must identify exactly one curated recording");
  const item = matches[0];
  const entry = validated.assetsByReference.get(item.assetReference);
  if (!entry || entry.asset.kind !== "audio" || !inspectable.has(entry.asset.role)) throw new Error("case must reference inspectable registered audio");
  const { source, asset } = entry;
  const rule = validated.policy.licenses[source.license.spdx];
  // Do not rely on a role label alone to permit model-design use.
  if (source.status !== "product-eligible" || source.permittedUse.commercial !== true ||
      source.permittedUse.modelParameterFitting !== true || rule.commercialUse !== true ||
      rule.modelParameterFitting === "research-only") throw new Error("source is isolated from commercial model design");
  if ((rule.shareAlike || rule.modelParameterFitting === "legal-clearance-required") && !source.license.clearanceId) {
    throw new Error("source requires separate legal clearance");
  }
  const roleField = { calibration: "calibration", "development-validation": "developmentValidation", "cross-piano-validation": "crossPianoValidation" }[asset.role];
  if (!validated.splits.roles[roleField]?.includes(item.assetReference)) throw new Error("case lacks an inspectable split assignment");
  if (!identifier(source.id)) throw new Error("unsafe source directory");
  for (const registered of source.assets) {
    if (!identifier(registered.fileName) || path.basename(registered.fileName) !== registered.fileName) throw new Error("unsafe asset filename");
  }
  if (!Number.isInteger(item.conditions?.note) || item.conditions.note < 0 || item.conditions.note > 127) throw new Error("case needs a known note");
  for (const key of ["velocity", "pedal", "microphone", "instrument", "noteOffSeconds"]) {
    if (!(key in item.conditions)) throw new Error(`missing condition ${key}; use null for genuinely unknown metadata`);
  }
  const rawRoot = path.join(ROOT, "work/acoustic-data/raw");
  const rawDirectory = path.join(rawRoot, source.id);
  await mkdir(rawDirectory, { recursive: true });
  if (await realpath(rawDirectory) !== rawDirectory) throw new Error("raw storage must not traverse symlinks");
  const evidence = [];
  // Verify audio AND license evidence against immutable registered bytes.
  for (const registered of source.assets) {
    if (registered.expectedBytes > 256 * 1024 * 1024) throw new Error("asset exceeds ingestion budget");
    const destination = path.join(rawDirectory, registered.fileName);
    let bytes;
    try {
      if (await realpath(destination) !== destination) throw new Error("asset symlink is forbidden");
      if ((await stat(destination)).size !== registered.expectedBytes) throw new Error("cached asset size changed");
      bytes = await readFile(destination);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      const response = await fetchImpl(registered.url, { redirect: "error", signal: AbortSignal.timeout(60000) });
      if (!response.ok) throw new Error(`download failed: HTTP ${response.status}`);
      // The registry limits the expected object; reject mismatches before analysis.
      const chunks = [];
      let totalBytes = 0;
      for await (const chunk of response.body) {
        totalBytes += chunk.length;
        if (totalBytes > registered.expectedBytes) throw new Error("download exceeds registered byte count");
        chunks.push(chunk);
      }
      bytes = Buffer.concat(chunks, totalBytes);
      verifyAssetBuffer(source.id, registered, bytes);
      await writeFile(destination, bytes, { flag: "wx" });
    }
    verifyAssetBuffer(source.id, registered, bytes);
    evidence.push({ assetId: registered.id, sha256: hash(bytes), bytes: bytes.length });
  }
  const registryBytes = await readFile(path.join(ROOT, "data/acoustic/registry.json"));
  const policyBytes = await readFile(path.join(ROOT, "data/acoustic/license-policy.json"));
  const absoluteOutput = path.resolve(outputPath);
  const job = {
    schemaVersion: 1, evidenceKind: "registered-reference", cases: [{
      id: item.id, role: asset.role, conditions: item.conditions,
      recording: { path: path.relative(path.dirname(absoluteOutput), path.join(rawDirectory, asset.fileName)),
        bytes: asset.expectedBytes, sha256: asset.integrity.sha256 },
      provenance: { sourceId: source.id, assetId: asset.id, origin: source.origin,
        license: source.license.spdx, attribution: source.license.attribution,
        retrievedAt: source.retrievedAt, permittedUse: source.permittedUse,
        processing: source.processing, registrySha256: hash(registryBytes),
        licensePolicySha256: hash(policyBytes), caseCatalogueSha256: hash(catalogueBytes),
        metadataLimitations: item.limitations, verifiedAssets: evidence },
    }], comparisons: [],
  };
  await mkdir(path.dirname(absoluteOutput), { recursive: true });
  await writeFile(absoluteOutput, `${JSON.stringify(job, null, 2)}\n`);
  return job;
}

async function main() {
  const args = process.argv.slice(2);
  const options = {};
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    if (!["--case", "--output"].includes(key) || options[key] || !args[index+1]) throw new Error("usage: --case ID --output JOB.json");
    options[key] = args[index+1];
  }
  if (!options["--case"] || !options["--output"]) throw new Error("--case and --output required");
  await prepareAnalysisJob({ caseId: options["--case"], outputPath: options["--output"] });
  console.log(`prepared ${options["--case"]}: ${options["--output"]}`);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}
