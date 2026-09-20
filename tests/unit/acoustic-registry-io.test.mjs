import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  buildProvenanceReport, gitBlobSha1, ingestAllSources, ingestSource,
  loadAndValidateRegistry, sha256,
} from "../../scripts/acoustic-data-registry.mjs";

async function setup(t, sourceCount = 1) {
  const root = await mkdtemp(path.join(os.tmpdir(), "acoustic-io-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const documents = await loadAndValidateRegistry();
  const registry = structuredClone(documents.registry);
  const splits = structuredClone(documents.splits);
  const bytes = Buffer.from("controlled fixture bytes");
  const template = registry.sources[0];
  registry.sources = Array.from({ length: sourceCount }, (_, index) => {
    const source = structuredClone(template);
    source.id = `fixture-${index}`;
    for (const asset of source.assets) {
      asset.expectedBytes = bytes.length;
      asset.integrity = { algorithm: "git-sha1", value: gitBlobSha1(bytes), sha256: sha256(bytes) };
    }
    return source;
  });
  splits.roles.calibration = registry.sources.map((source) => `${source.id}:c4-mp3`);
  const registryOptions = {};
  for (const [key, document] of [
    ["registry", registry], ["policy", documents.policy], ["splits", splits], ["holdout", documents.holdout],
  ]) {
    registryOptions[`${key}Path`] = path.join(root, `${key}.json`);
    await writeFile(registryOptions[`${key}Path`], JSON.stringify(document));
  }
  return { root, bytes, registry, splits, registryOptions, outputRoot: path.join(root, "output") };
}

test("ingestion is repeatable but does not silently repair tampered cached bytes", async (t) => {
  const setupData = await setup(t);
  const options = { ...setupData, fetchImpl: async () => new Response(setupData.bytes) };
  const first = await ingestAllSources(options);
  const second = await ingestAllSources(options);
  assert.deepEqual(first, second);
  const raw = path.join(setupData.outputRoot, "raw/fixture-0/C4.mp3");
  const changed = Buffer.from(setupData.bytes);
  changed[0] ^= 1;
  await writeFile(raw, changed);
  await assert.rejects(() => ingestAllSources(options), /existing ingestion bytes changed/);
  assert.deepEqual(await readFile(raw), changed);
});

test("failed or oversized downloads cannot yield a source receipt", async (t) => {
  const setupData = await setup(t);
  for (const response of [
    () => new Response("missing", { status: 404 }),
    () => new Response(Buffer.alloc(setupData.bytes.length + 1)),
    () => new Response(setupData.bytes.subarray(1)),
  ]) {
    await assert.rejects(() => ingestAllSources({ ...setupData, fetchImpl: async () => response() }),
      /download failed|registered byte count|byte length changed/);
    await assert.rejects(() => readFile(path.join(setupData.outputRoot, "receipts/fixture-0.json")),
      (error) => error.code === "ENOENT");
  }
});

test("blocked sources are not fetched and cannot be explicitly ingested", async (t) => {
  const setupData = await setup(t);
  const source = setupData.registry.sources[0];
  source.status = "blocked";
  source.permittedUse.commercial = false;
  source.permittedUse.modelParameterFitting = false;
  setupData.splits.roles.calibration = [];
  await writeFile(setupData.registryOptions.registryPath, JSON.stringify(setupData.registry));
  await writeFile(setupData.registryOptions.splitsPath, JSON.stringify(setupData.splits));
  let fetches = 0;
  const options = { ...setupData, fetchImpl: async () => { fetches += 1; return new Response(setupData.bytes); } };
  assert.deepEqual(await ingestAllSources(options), []);
  await assert.rejects(() => ingestSource({ ...options, sourceId: source.id }), /blocked source/);
  assert.equal(fetches, 0);
});

test("required provenance covers every applicable source, not just the first", async (t) => {
  const setupData = await setup(t, 2);
  const options = { ...setupData, fetchImpl: async () => new Response(setupData.bytes) };
  await ingestSource({ ...options, sourceId: "fixture-0" });
  const reportOptions = {
    receiptsDirectory: path.join(setupData.outputRoot, "receipts"),
    requireAllReceipts: true, registryOptions: setupData.registryOptions,
  };
  await assert.rejects(() => buildProvenanceReport(reportOptions), /fixture-1.*missing/);
  await ingestSource({ ...options, sourceId: "fixture-1" });
  const report = await buildProvenanceReport(reportOptions);
  assert.equal(report.sources.length, 2);
  assert.ok(report.sources.every((source) => source.ingested));
});
