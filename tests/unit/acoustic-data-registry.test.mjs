import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  RegistryError,
  buildProvenanceReport,
  gitBlobSha1,
  loadAndValidateRegistry,
  provenanceReportMarkdown,
  sealHoldoutManifest,
  validateRegistryDocument,
  verifyAssetBuffer,
} from "../../scripts/acoustic-data-registry.mjs";

const ROOT = path.resolve(import.meta.dirname, "../..");

async function fixtureDocuments() {
  return Promise.all([
    readJson("data/acoustic/registry.json"),
    readJson("data/acoustic/license-policy.json"),
    readJson("data/acoustic/development-splits.json"),
    readJson("data/acoustic/holdout/protocol.json"),
  ]);
}

async function readJson(relativePath) {
  return JSON.parse(await readFile(path.join(ROOT, relativePath), "utf8"));
}

test("the committed registry and sealed-access protocol validate", async () => {
  const result = await loadAndValidateRegistry();
  assert.equal(result.registry.sources[0].id, "salamander-tonejs-c4");
  assert.equal(result.holdout.repositoryContainsData, false);
  assert.equal(result.holdout.access.reveal, "one-shot-after-candidate-freeze");
});

test("Git blob integrity detects byte changes", async () => {
  const [registry] = await fixtureDocuments();
  const asset = registry.sources[0].assets[0];
  const buffer = Buffer.from("fixture");
  assert.equal(gitBlobSha1(buffer), "001f1993905d81b471eeaa840432cf35aedaea61");
  assert.throws(() => verifyAssetBuffer(registry.sources[0].id, asset, buffer), (error) => error instanceof RegistryError && error.code === "INTEGRITY_MISMATCH");
});

test("missing attribution and unknown licenses fail closed", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const missingAttribution = structuredClone(registry);
  missingAttribution.sources[0].license.attribution = "";
  assert.throws(() => validateRegistryDocument(missingAttribution, policy, splits, holdout), /attribution is required/);
  const unknownLicense = structuredClone(registry);
  unknownLicense.sources[0].license.spdx = "Custom-Maybe";
  assert.throws(() => validateRegistryDocument(unknownLicense, policy, splits, holdout), /unknown or ambiguous license/);
});

test("license policy rules validate field types and fitting-policy enums before use", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const malformed = structuredClone(policy);
  malformed.licenses["CC-BY-NC-4.0"].commercialUse = "false";
  delete malformed.licenses["CC-BY-NC-4.0"].modelParameterFitting;
  assert.throws(
    () => validateRegistryDocument(registry, malformed, splits, holdout),
    /commercialUse must be boolean|modelParameterFitting must be a supported policy value/,
  );
});

test("asset URLs must match the declared distribution repository and commit", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const wrongCommit = structuredClone(registry);
  wrongCommit.sources[0].origin.distributionCommit = "0".repeat(40);
  assert.throws(
    () => validateRegistryDocument(wrongCommit, policy, splits, holdout),
    /URL commit .* does not match declared/,
  );
  const wrongRepository = structuredClone(registry);
  wrongRepository.sources[0].origin.distributionRepository = "other/project";
  assert.throws(
    () => validateRegistryDocument(wrongRepository, policy, splits, holdout),
    /URL repository .* does not match declared/,
  );
});

test("non-commercial and uncleared share-alike sources cannot enter product fitting", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const nonCommercial = structuredClone(registry);
  nonCommercial.sources[0].license.spdx = "CC-BY-NC-SA-4.0";
  assert.throws(() => validateRegistryDocument(nonCommercial, policy, splits, holdout), /non-commercial license|isolates this source/);
  const shareAlike = structuredClone(registry);
  shareAlike.sources[0].license.spdx = "CC-BY-SA-4.0";
  assert.throws(() => validateRegistryDocument(shareAlike, policy, splits, holdout), /requires explicit legal clearance/);
});

test("inspectable splits cannot contain unknown, mismatched, or duplicate assets", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const duplicate = structuredClone(splits);
  duplicate.roles.developmentValidation.push("salamander-tonejs-c4:c4-mp3");
  assert.throws(() => validateRegistryDocument(registry, policy, duplicate, holdout), /assigned to developmentValidation|more than one inspectable split/);
});

test("license evidence must be an independently checksummed text asset", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const wrongEvidence = structuredClone(registry);
  wrongEvidence.sources[0].license.evidenceAssetId = "c4-mp3";
  assert.throws(() => validateRegistryDocument(wrongEvidence, policy, splits, holdout), /license evidence must be a text asset/);
});

test("holdout protocol rejects committed locators or developer access", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const exposed = structuredClone(holdout);
  exposed.repositoryContainsLocators = true;
  exposed.access.deniedActors = ["automation-agents"];
  assert.throws(() => validateRegistryDocument(registry, policy, splits, exposed), /locators must remain outside|deny developers/);
});

test("sealing binds candidate bytes and publishes commitments only", async () => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "moonlight-holdout-"));
  const manifestPath = path.join(temp, "private-manifest.json");
  const candidateArtifactPath = path.join(temp, "candidate-001.mlpiano");
  const metricPlanPath = path.join(temp, "metric-plan.json");
  const outputPath = path.join(temp, "commitment.json");
  await writeFile(manifestPath, '{"secretAsset":"never-publish.wav","label":"fail"}\n');
  await writeFile(candidateArtifactPath, "frozen-candidate-bytes-v1\n");
  await writeFile(metricPlanPath, '{"metric":"spectral-distance","threshold":0.1}\n');
  const receipt = await sealHoldoutManifest({
    manifestPath,
    candidateId: "candidate-001",
    candidateArtifactPath,
    metricPlanPath,
    outputPath,
    custodian: "independent-reviewer",
  });
  const published = await readFile(outputPath, "utf8");
  assert.equal(receipt.candidateId, "candidate-001");
  assert.match(published, /candidateArtifactSha256/);
  assert.match(published, /manifestSha256/);
  assert.doesNotMatch(published, /never-publish|spectral-distance|frozen-candidate-bytes|"label"/);

  await writeFile(candidateArtifactPath, "rebuilt-candidate-bytes-v2\n");
  const rebuiltOutput = path.join(temp, "rebuilt-commitment.json");
  const rebuilt = await sealHoldoutManifest({
    manifestPath,
    candidateId: "candidate-001",
    candidateArtifactPath,
    metricPlanPath,
    outputPath: rebuiltOutput,
    custodian: "independent-reviewer",
  });
  assert.notEqual(rebuilt.candidateArtifactSha256, receipt.candidateArtifactSha256);

  const inRepoManifest = path.join(ROOT, "work-would-be-private.json");
  await assert.rejects(
    () => sealHoldoutManifest({
      manifestPath: inRepoManifest,
      candidateId: "candidate-002",
      candidateArtifactPath,
      metricPlanPath,
      outputPath,
      custodian: "reviewer",
    }),
    /must live outside the repository/,
  );
});

test("a tampered ingestion receipt cannot enter a provenance report", async () => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "moonlight-receipt-"));
  const [registry] = await fixtureDocuments();
  const source = registry.sources[0];
  await writeFile(path.join(temp, `${source.id}.json`), `${JSON.stringify({
    schemaVersion: 1,
    sourceId: source.id,
    sourceStatus: source.status,
    distributionCommit: source.origin.distributionCommit,
    license: source.license.spdx,
    attribution: source.license.attribution,
    rawCommitPolicy: "never-commit",
    assets: source.assets.map((asset) => ({
      assetId: asset.id,
      role: asset.role,
      expectedBytes: asset.expectedBytes,
      actualBytes: asset.expectedBytes,
      gitSha1: asset.integrity.value,
      sha256: "0".repeat(64),
    })),
  }, null, 2)}
`);
  await assert.rejects(() => buildProvenanceReport({ receiptsDirectory: temp }), /does not prove the registered bytes/);
});

test("CI guards every indexed raw asset and validates pushes to main", async () => {
  const workflow = await readFile(path.join(ROOT, ".github/workflows/acoustic-data-registry.yml"), "utf8");
  assert.match(workflow, /- main/);
  assert.match(workflow, /git ls-files -- work\/acoustic-data\/raw/);
});

test("the provenance report is attachable without exposing raw data", async () => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "moonlight-report-"));
  const report = await buildProvenanceReport({ receiptsDirectory: temp });
  const markdown = provenanceReportMarkdown(report);
  assert.match(markdown, /Salamander Grand Piano C4 reference probe/);
  assert.match(markdown, /CC-BY-3.0/);
  assert.match(markdown, /external-custodian/);
  assert.doesNotMatch(markdown, /private-manifest|outer.*\.wav/i);
});
