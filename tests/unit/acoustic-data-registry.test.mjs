import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  RegistryError,
  buildProvenanceReport,
  gitBlobSha1,
  ingestAllSources,
  loadAndValidateRegistry,
  provenanceReportMarkdown,
  sealHoldoutManifest,
  sha256,
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

function validMetricPlan(candidateId) {
  return {
    schemaVersion: 1,
    candidateId,
    metrics: [
      { id: "spectral-distance", comparison: "lte", threshold: 0.1 },
      { id: "pedal-continuity", comparison: "gte", threshold: 0.9 },
    ],
    statisticalMethod: "Evaluate frozen aggregate metrics once on the sealed outer test.",
    failureCriteria: "Fail if any registered metric crosses its declared threshold.",
  };
}

function registeredAsset({ id, role, fileName, url, bytes }) {
  return {
    id,
    role,
    kind: role === "license-evidence" ? "text" : "audio",
    fileName,
    url,
    expectedBytes: bytes.length,
    integrity: {
      algorithm: "git-sha1",
      value: gitBlobSha1(bytes),
      sha256: sha256(bytes),
    },
    commitPolicy: "never-commit",
  };
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

test("calibration splits require product-eligible commercial fitting permission", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const restricted = structuredClone(registry);
  restricted.sources[0].status = "research-only";
  restricted.sources[0].license.spdx = "CC-BY-NC-4.0";
  restricted.sources[0].permittedUse.commercial = false;
  restricted.sources[0].permittedUse.modelParameterFitting = false;
  assert.throws(
    () => validateRegistryDocument(restricted, policy, splits, holdout),
    /cannot enter calibration without product-eligible commercial fitting permission/,
  );
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

test("asset filenames cannot escape the ignored raw directory", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const traversal = structuredClone(registry);
  traversal.sources[0].assets[0].fileName = "../../../../package.json";
  assert.throws(
    () => validateRegistryDocument(traversal, policy, splits, holdout),
    /fileName must be a safe basename/,
  );
});

test("holdout protocol rejects committed locators, prohibited access, and actor overlap", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const exposed = structuredClone(holdout);
  exposed.repositoryContainsLocators = true;
  exposed.access.deniedActors = ["automation-agents"];
  assert.throws(() => validateRegistryDocument(registry, policy, splits, exposed), /locators must remain outside|deny developers/);

  const contradictory = structuredClone(holdout);
  contradictory.access.permittedActors.push("developers");
  assert.throws(
    () => validateRegistryDocument(registry, policy, splits, contradictory),
    /permitted actors must contain only release-gate-custodian|both permitted and denied/,
  );
});

test("sealing validates the metric plan, binds candidate bytes, and publishes commitments only", async () => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "moonlight-holdout-"));
  const manifestPath = path.join(temp, "private-manifest.json");
  const candidateArtifactPath = path.join(temp, "candidate-001.mlpiano");
  const metricPlanPath = path.join(temp, "metric-plan.json");
  const outputPath = path.join(temp, "commitment.json");
  await writeFile(manifestPath, '{"secretAsset":"never-publish.wav","label":"fail"}\n');
  await writeFile(candidateArtifactPath, "frozen-candidate-bytes-v1\n");
  await writeFile(metricPlanPath, `${JSON.stringify(validMetricPlan("candidate-001"))}\n`);
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

  await writeFile(metricPlanPath, "{}\n");
  await assert.rejects(
    () => sealHoldoutManifest({
      manifestPath,
      candidateId: "candidate-001",
      candidateArtifactPath,
      metricPlanPath,
      outputPath,
      custodian: "independent-reviewer",
    }),
    /metric plan schemaVersion|at least one metric|statisticalMethod|failureCriteria/,
  );

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

test("ingest-all downloads every non-blocked registered source", async () => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "moonlight-ingest-all-"));
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const commit = "a".repeat(40);
  const repository = "moonlight/test-assets";
  const buffers = new Map();

  function makeSource(id, role) {
    const audio = Buffer.from(`audio-${id}`);
    const license = Buffer.from(`license-${id}`);
    const audioUrl = `https://raw.githubusercontent.com/${repository}/${commit}/${id}.bin`;
    const licenseUrl = `https://raw.githubusercontent.com/${repository}/${commit}/${id}.txt`;
    buffers.set(audioUrl, audio);
    buffers.set(licenseUrl, license);
    return {
      id,
      title: id,
      status: "product-eligible",
      origin: {
        creator: "Fixture",
        instrument: "Fixture piano",
        canonicalUrl: "https://example.com/fixture",
        distributionRepository: repository,
        distributionCommit: commit,
      },
      retrievedAt: "2026-09-07",
      license: {
        spdx: "CC-BY-3.0",
        evidenceAssetId: "license",
        attribution: "Fixture attribution",
      },
      permittedUse: {
        commercial: true,
        modelParameterFitting: true,
        runtimeDistribution: false,
        rawRedistribution: false,
        researchEvaluation: true,
      },
      processing: ["fixture ingestion"],
      assets: [
        registeredAsset({ id: "audio", role, fileName: `${id}.bin`, url: audioUrl, bytes: audio }),
        registeredAsset({ id: "license", role: "license-evidence", fileName: `${id}.txt`, url: licenseUrl, bytes: license }),
      ],
    };
  }

  const customRegistry = structuredClone(registry);
  customRegistry.sources = [
    makeSource("source-a", "calibration"),
    makeSource("source-b", "development-validation"),
  ];
  const customSplits = structuredClone(splits);
  customSplits.roles.calibration = ["source-a:audio"];
  customSplits.roles.developmentValidation = ["source-b:audio"];
  customSplits.roles.crossPianoValidation = [];

  const paths = {
    registryPath: path.join(temp, "registry.json"),
    policyPath: path.join(temp, "policy.json"),
    splitsPath: path.join(temp, "splits.json"),
    holdoutPath: path.join(temp, "holdout.json"),
  };
  await Promise.all([
    writeFile(paths.registryPath, JSON.stringify(customRegistry)),
    writeFile(paths.policyPath, JSON.stringify(policy)),
    writeFile(paths.splitsPath, JSON.stringify(customSplits)),
    writeFile(paths.holdoutPath, JSON.stringify(holdout)),
  ]);

  const requested = [];
  const fetchImpl = async (url) => {
    requested.push(url);
    const bytes = buffers.get(url);
    return new Response(bytes ?? "missing", { status: bytes ? 200 : 404 });
  };
  const results = await ingestAllSources({
    outputRoot: path.join(temp, "output"),
    fetchImpl,
    registryOptions: paths,
  });
  assert.equal(results.length, 2);
  assert.equal(requested.length, 4);
  assert.equal(JSON.parse(await readFile(path.join(temp, "output/receipts/source-a.json"))).sourceId, "source-a");
  assert.equal(JSON.parse(await readFile(path.join(temp, "output/receipts/source-b.json"))).sourceId, "source-b");
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

test("a required provenance report rejects missing non-blocked receipts", async () => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "moonlight-required-receipt-"));
  await assert.rejects(
    () => buildProvenanceReport({ receiptsDirectory: temp, requireAllReceipts: true }),
    /required ingestion receipt is missing/,
  );
});

test("CI guards indexed raw assets, ingests all sources, and validates pushes to main", async () => {
  const workflow = await readFile(path.join(ROOT, ".github/workflows/acoustic-data-registry.yml"), "utf8");
  const packageJson = JSON.parse(await readFile(path.join(ROOT, "package.json"), "utf8"));
  assert.match(workflow, /- main/);
  assert.match(workflow, /git ls-files -- work\/acoustic-data\/raw/);
  assert.match(workflow, /npm run acoustic:ingest:all/);
  assert.match(packageJson.scripts["acoustic:ingest:all"], /ingest-all/);
  assert.match(packageJson.scripts["acoustic:report"], /--require-all true/);
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

test("source directory identifiers and duplicate filenames fail before ingestion", async () => {
  const [registry, policy, splits, holdout] = await fixtureDocuments();
  const unsafe = structuredClone(registry);
  unsafe.sources[0].id = "../../outside";
  assert.throws(() => validateRegistryDocument(unsafe, policy, splits, holdout), /safe source id/);
  const duplicate = structuredClone(registry);
  duplicate.sources[0].assets[1].fileName = "c4.MP3";
  assert.throws(() => validateRegistryDocument(duplicate, policy, splits, holdout), /duplicate fileName/);
});

test("CLI rejects misspelled required-receipt flags instead of failing open", async () => {
  const { spawnSync } = await import("node:child_process");
  for (const args of [
    ["report", "--require-all", "ture"],
    ["report", "--require-al", "true"],
    ["report", "--require-all", "true", "--require-all", "false"],
  ]) {
    const result = spawnSync(process.execPath, [path.join(ROOT, "scripts/acoustic-data-registry.mjs"), ...args], {
      encoding: "utf8", timeout: 5000,
    });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /CLI_INVALID|invalid|unknown|duplicate|true or false/);
  }
});

test("registry workflow remains read-only and keeps full application verification", async () => {
  const workflow = await readFile(path.join(ROOT, ".github/workflows/acoustic-data-registry.yml"), "utf8");
  assert.match(workflow, /contents: read/);
  assert.match(workflow, /persist-credentials: false/);
  for (const command of ["npm test", "npm run lint", "npm run build"]) {
    assert.ok(workflow.includes(command), `missing ${command}`);
  }
  assert.doesNotMatch(workflow, /contents: write|git push|git commit|git add -A|apply-acoustic-round2|acoustic-round2\.part/);
});
