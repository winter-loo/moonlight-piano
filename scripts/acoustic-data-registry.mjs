#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_REGISTRY = path.join(ROOT, "data/acoustic/registry.json");
const DEFAULT_POLICY = path.join(ROOT, "data/acoustic/license-policy.json");
const DEFAULT_SPLITS = path.join(ROOT, "data/acoustic/development-splits.json");
const DEFAULT_HOLDOUT = path.join(ROOT, "data/acoustic/holdout/protocol.json");
const SOURCE_STATUSES = new Set(["product-eligible", "research-only", "blocked"]);
const ASSET_ROLES = new Set([
  "calibration",
  "development-validation",
  "cross-piano-validation",
  "license-evidence",
]);

export class RegistryError extends Error {
  constructor(message, code = "REGISTRY_INVALID") {
    super(message);
    this.name = "RegistryError";
    this.code = code;
  }
}

export function gitBlobSha1(buffer) {
  return createHash("sha1")
    .update(Buffer.from(`blob ${buffer.length}\0`, "utf8"))
    .update(buffer)
    .digest("hex");
}

export function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

export function validateRegistryDocument(registry, policy, splits, holdout) {
  const errors = [];
  if (registry?.schemaVersion !== 1) errors.push("registry.schemaVersion must be 1");
  if (!nonEmpty(registry?.registryId)) errors.push("registryId is required");
  if (!isoDate(registry?.updatedAt)) errors.push("updatedAt must be YYYY-MM-DD");
  if (!Array.isArray(registry?.sources) || registry.sources.length === 0) {
    errors.push("at least one source is required");
  }
  if (policy?.schemaVersion !== 1 || !plainObject(policy?.licenses)) {
    errors.push("license policy is missing or unsupported");
  }

  const sourceIds = new Set();
  const assetsByReference = new Map();
  for (const source of registry?.sources ?? []) {
    const prefix = `source ${source?.id ?? "<missing>"}`;
    if (!nonEmpty(source?.id)) errors.push(`${prefix}: id is required`);
    else if (sourceIds.has(source.id)) errors.push(`${prefix}: duplicate source id`);
    else sourceIds.add(source.id);
    if (!nonEmpty(source?.title)) errors.push(`${prefix}: title is required`);
    if (!SOURCE_STATUSES.has(source?.status)) errors.push(`${prefix}: invalid status`);
    if (!isoDate(source?.retrievedAt)) errors.push(`${prefix}: retrievedAt must be YYYY-MM-DD`);
    validateOrigin(source?.origin, prefix, errors);

    const spdx = source?.license?.spdx;
    const rule = policy?.licenses?.[spdx];
    if (!nonEmpty(spdx) || !rule) errors.push(`${prefix}: unknown or ambiguous license ${spdx ?? "<missing>"}`);
    if (rule?.attributionRequired && !nonEmpty(source?.license?.attribution)) {
      errors.push(`${prefix}: attribution is required by ${spdx}`);
    }
    if (!plainObject(source?.permittedUse)) errors.push(`${prefix}: permittedUse is required`);
    for (const key of ["commercial", "modelParameterFitting", "runtimeDistribution", "rawRedistribution", "researchEvaluation"]) {
      if (typeof source?.permittedUse?.[key] !== "boolean") errors.push(`${prefix}: permittedUse.${key} must be boolean`);
    }
    if (rule && source?.permittedUse) {
      if (!rule.commercialUse && source.permittedUse.commercial) {
        errors.push(`${prefix}: non-commercial license cannot be marked commercially usable`);
      }
      if (rule.modelParameterFitting === "research-only" && source.permittedUse.modelParameterFitting) {
        errors.push(`${prefix}: license policy isolates this source from product model fitting`);
      }
      if (rule.shareAlike && source.status === "product-eligible" && !nonEmpty(source?.license?.clearanceId)) {
        errors.push(`${prefix}: share-alike source requires explicit legal clearance before product use`);
      }
      if (source.status === "product-eligible" && (!source.permittedUse.commercial || !source.permittedUse.modelParameterFitting)) {
        errors.push(`${prefix}: product-eligible status contradicts permittedUse`);
      }
      if (source.status !== "product-eligible" && source.permittedUse.modelParameterFitting) {
        errors.push(`${prefix}: research-only/blocked source cannot enter product model fitting`);
      }
    }
    if (!Array.isArray(source?.processing) || source.processing.length === 0 || source.processing.some((step) => !nonEmpty(step))) {
      errors.push(`${prefix}: processing must contain explicit steps`);
    }
    if (!Array.isArray(source?.assets) || source.assets.length === 0) {
      errors.push(`${prefix}: at least one checksummed asset is required`);
      continue;
    }
    const assetIds = new Set();
    for (const asset of source.assets) {
      const assetPrefix = `${prefix} asset ${asset?.id ?? "<missing>"}`;
      if (!nonEmpty(asset?.id)) errors.push(`${assetPrefix}: id is required`);
      else if (assetIds.has(asset.id)) errors.push(`${assetPrefix}: duplicate asset id`);
      else assetIds.add(asset.id);
      if (!ASSET_ROLES.has(asset?.role)) errors.push(`${assetPrefix}: invalid role`);
      if (!nonEmpty(asset?.kind) || !nonEmpty(asset?.fileName)) errors.push(`${assetPrefix}: kind and fileName are required`);
      if (!isPinnedHttpsUrl(asset?.url)) errors.push(`${assetPrefix}: URL must be HTTPS and pinned to a 40-character commit`);
      if (!Number.isSafeInteger(asset?.expectedBytes) || asset.expectedBytes <= 0) errors.push(`${assetPrefix}: expectedBytes must be positive`);
      if (asset?.integrity?.algorithm !== "git-sha1" || !/^[0-9a-f]{40}$/.test(asset?.integrity?.value ?? "")) {
        errors.push(`${assetPrefix}: a valid git-sha1 checksum is required`);
      }
      if (asset?.commitPolicy !== "never-commit") errors.push(`${assetPrefix}: raw assets must use never-commit policy`);
      const reference = `${source.id}:${asset.id}`;
      assetsByReference.set(reference, { source, asset });
    }
    const evidenceAsset = source.assets.find((asset) => asset.id === source?.license?.evidenceAssetId);
    if (!evidenceAsset) {
      errors.push(`${prefix}: license evidenceAssetId must reference a checksummed asset`);
    } else if (evidenceAsset.role !== "license-evidence" || evidenceAsset.kind !== "text") {
      errors.push(`${prefix}: license evidence must be a text asset with role license-evidence`);
    }
  }

  validateSplits(splits, assetsByReference, errors);
  validateHoldoutProtocol(holdout, errors);
  if (errors.length > 0) throw new RegistryError(errors.join("\n"));
  return { registry, policy, splits, holdout, assetsByReference };
}

function validateOrigin(origin, prefix, errors) {
  for (const key of ["creator", "instrument", "canonicalUrl", "distributionRepository", "distributionCommit"]) {
    if (!nonEmpty(origin?.[key])) errors.push(`${prefix}: origin.${key} is required`);
  }
  if (origin?.canonicalUrl && !origin.canonicalUrl.startsWith("https://")) errors.push(`${prefix}: canonicalUrl must use HTTPS`);
  if (origin?.distributionCommit && !/^[0-9a-f]{40}$/.test(origin.distributionCommit)) errors.push(`${prefix}: distributionCommit must be immutable`);
}

function validateSplits(splits, assetsByReference, errors) {
  if (splits?.schemaVersion !== 1 || !plainObject(splits?.roles)) {
    errors.push("development-splits is missing or unsupported");
    return;
  }
  const assigned = new Map();
  for (const [roleName, expectedAssetRole] of [
    ["calibration", "calibration"],
    ["developmentValidation", "development-validation"],
    ["crossPianoValidation", "cross-piano-validation"],
  ]) {
    const references = splits.roles[roleName];
    if (!Array.isArray(references)) {
      errors.push(`development-splits.roles.${roleName} must be an array`);
      continue;
    }
    for (const reference of references) {
      const entry = assetsByReference.get(reference);
      if (!entry) errors.push(`development split references unknown asset ${reference}`);
      else if (entry.asset.role !== expectedAssetRole) errors.push(`${reference} is assigned to ${roleName} but declares ${entry.asset.role}`);
      if (assigned.has(reference)) errors.push(`${reference} is assigned to more than one inspectable split`);
      assigned.set(reference, roleName);
    }
  }
  const outer = splits.roles.immutableOuterTest;
  if (outer?.assetReferencesCommitted !== false) errors.push("outer-test asset references must not be committed");
  if (outer?.protocolRef !== "data/acoustic/holdout/protocol.json") errors.push("outer-test protocolRef is invalid");
}

function validateHoldoutProtocol(holdout, errors) {
  if (holdout?.schemaVersion !== 1 || holdout?.role !== "immutable-outer-test") errors.push("holdout protocol is missing or unsupported");
  if (holdout?.status !== "protocol-ready" || holdout?.storage !== "external-custodian") errors.push("holdout must be protocol-ready and externally custodied");
  if (holdout?.repositoryContainsData !== false || holdout?.repositoryContainsLocators !== false) errors.push("holdout data and locators must remain outside the repository");
  if (holdout?.candidateFreezeRequired !== true) errors.push("holdout requires a frozen candidate");
  for (const actor of ["developers", "tuning-agents", "automation-agents"]) {
    if (!holdout?.access?.deniedActors?.includes(actor)) errors.push(`holdout must deny ${actor}`);
  }
  if (holdout?.access?.reveal !== "one-shot-after-candidate-freeze") errors.push("holdout reveal must be one-shot after candidate freeze");
  if (holdout?.access?.preDecisionOutput !== "aggregate-pass-fail-only") errors.push("holdout may reveal only aggregate pass/fail before the release decision");
  if (holdout?.commitment?.requiredBeforeFormalEvaluation !== true || holdout?.commitment?.algorithm !== "sha256") errors.push("holdout commitment must be required and use sha256");
  if (holdout?.failurePolicy?.inspectedDataPermanentlyLeavesOuterTest !== true) errors.push("inspected data must permanently leave the outer test");
  if (holdout?.failurePolicy?.repartitionDoesNotRestoreIndependence !== true) errors.push("holdout policy must forbid independence by repartitioning");
  if (!nonEmpty(holdout?.failurePolicy?.nextCandidateRequires)) errors.push("holdout must define evidence requirements for the next candidate after failure");
}

export async function loadAndValidateRegistry(options = {}) {
  const [registry, policy, splits, holdout] = await Promise.all([
    readJson(options.registryPath ?? DEFAULT_REGISTRY),
    readJson(options.policyPath ?? DEFAULT_POLICY),
    readJson(options.splitsPath ?? DEFAULT_SPLITS),
    readJson(options.holdoutPath ?? DEFAULT_HOLDOUT),
  ]);
  return validateRegistryDocument(registry, policy, splits, holdout);
}

export async function ingestSource({ sourceId, outputRoot, fetchImpl = fetch }) {
  const validated = await loadAndValidateRegistry();
  const source = validated.registry.sources.find((candidate) => candidate.id === sourceId);
  if (!source) throw new RegistryError(`unknown source: ${sourceId}`, "SOURCE_NOT_FOUND");
  const rawDirectory = path.join(outputRoot, "raw", source.id);
  const receiptDirectory = path.join(outputRoot, "receipts");
  await mkdir(rawDirectory, { recursive: true });
  await mkdir(receiptDirectory, { recursive: true });
  const receipts = [];
  for (const asset of source.assets) {
    const response = await fetchImpl(asset.url, { redirect: "follow" });
    if (!response.ok) throw new RegistryError(`${source.id}:${asset.id} download failed with HTTP ${response.status}`, "DOWNLOAD_FAILED");
    const buffer = Buffer.from(await response.arrayBuffer());
    verifyAssetBuffer(source.id, asset, buffer);
    const localPath = path.join(rawDirectory, asset.fileName);
    await writeFile(localPath, buffer);
    receipts.push({
      assetId: asset.id,
      role: asset.role,
      expectedBytes: asset.expectedBytes,
      actualBytes: buffer.length,
      gitSha1: gitBlobSha1(buffer),
      sha256: sha256(buffer),
      localPath: path.relative(ROOT, localPath),
    });
  }
  const receipt = {
    schemaVersion: 1,
    sourceId: source.id,
    sourceStatus: source.status,
    distributionCommit: source.origin.distributionCommit,
    license: source.license.spdx,
    attribution: source.license.attribution,
    rawCommitPolicy: "never-commit",
    assets: receipts,
  };
  const receiptPath = path.join(receiptDirectory, `${source.id}.json`);
  await writeFile(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`);
  return { receipt, receiptPath };
}

export function verifyAssetBuffer(sourceId, asset, buffer) {
  if (buffer.length !== asset.expectedBytes) throw new RegistryError(`${sourceId}:${asset.id} byte length changed: expected ${asset.expectedBytes}, got ${buffer.length}`, "INTEGRITY_MISMATCH");
  const actual = gitBlobSha1(buffer);
  if (actual !== asset.integrity.value) throw new RegistryError(`${sourceId}:${asset.id} checksum changed: expected ${asset.integrity.value}, got ${actual}`, "INTEGRITY_MISMATCH");
}

export async function sealHoldoutManifest({ manifestPath, candidateId, metricPlanPath, outputPath, custodian }) {
  const absoluteManifest = path.resolve(manifestPath);
  const relativeToRoot = path.relative(ROOT, absoluteManifest);
  if (!relativeToRoot.startsWith("..") && !path.isAbsolute(relativeToRoot)) {
    throw new RegistryError("private holdout manifest must live outside the repository", "HOLDOUT_EXPOSURE_RISK");
  }
  if (!nonEmpty(candidateId) || !nonEmpty(custodian)) throw new RegistryError("candidateId and custodian are required", "HOLDOUT_INVALID");
  const [manifest, metricPlan] = await Promise.all([readFile(absoluteManifest), readFile(path.resolve(metricPlanPath))]);
  const receipt = {
    schemaVersion: 1,
    protocolId: "professional-piano-outer-test-v1",
    candidateId,
    custodian,
    manifestSha256: sha256(manifest),
    metricPlanSha256: sha256(metricPlan),
    disclosure: "commitments only; no asset identifiers, locators, labels, or per-sample results",
  };
  await mkdir(path.dirname(path.resolve(outputPath)), { recursive: true });
  await writeFile(path.resolve(outputPath), `${JSON.stringify(receipt, null, 2)}\n`);
  return receipt;
}

export async function buildProvenanceReport({ receiptsDirectory }) {
  const validated = await loadAndValidateRegistry();
  const sources = [];
  for (const source of validated.registry.sources) {
    let receipt = null;
    try {
      receipt = await readJson(path.join(receiptsDirectory, `${source.id}.json`));
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    if (receipt) validateReceipt(source, receipt);
    sources.push({
      id: source.id,
      title: source.title,
      status: source.status,
      creator: source.origin.creator,
      instrument: source.origin.instrument,
      license: source.license.spdx,
      attribution: source.license.attribution,
      productModelFitting: source.permittedUse.modelParameterFitting,
      distributionCommit: source.origin.distributionCommit,
      registeredAssets: source.assets.map((asset) => ({ id: asset.id, role: asset.role, integrity: asset.integrity })),
      ingested: Boolean(receipt),
      receiptAssets: receipt?.assets?.map((asset) => ({ assetId: asset.assetId, sha256: asset.sha256, actualBytes: asset.actualBytes })) ?? [],
    });
  }
  return {
    schemaVersion: 1,
    registryId: validated.registry.registryId,
    outerTest: {
      protocolId: validated.holdout.id,
      status: validated.holdout.status,
      storage: validated.holdout.storage,
      repositoryContainsData: false,
      candidateFreezeRequired: true,
    },
    sources,
  };
}

function validateReceipt(source, receipt) {
  if (receipt?.schemaVersion !== 1) throw new RegistryError(`${source.id}: ingestion receipt schema is unsupported`, "RECEIPT_INVALID");
  for (const [field, expected] of [
    ["sourceId", source.id],
    ["sourceStatus", source.status],
    ["distributionCommit", source.origin.distributionCommit],
    ["license", source.license.spdx],
    ["attribution", source.license.attribution],
    ["rawCommitPolicy", "never-commit"],
  ]) {
    if (receipt[field] !== expected) throw new RegistryError(`${source.id}: ingestion receipt ${field} does not match the registry`, "RECEIPT_INVALID");
  }
  if (!Array.isArray(receipt.assets) || receipt.assets.length !== source.assets.length) {
    throw new RegistryError(`${source.id}: ingestion receipt asset set is incomplete`, "RECEIPT_INVALID");
  }
  const byId = new Map(receipt.assets.map((asset) => [asset.assetId, asset]));
  for (const registered of source.assets) {
    const received = byId.get(registered.id);
    if (!received
      || received.role !== registered.role
      || received.expectedBytes !== registered.expectedBytes
      || received.actualBytes !== registered.expectedBytes
      || received.gitSha1 !== registered.integrity.value
      || !/^[0-9a-f]{64}$/.test(received.sha256 ?? "")) {
      throw new RegistryError(`${source.id}:${registered.id}: ingestion receipt does not prove the registered bytes`, "RECEIPT_INVALID");
    }
  }
}

export function provenanceReportMarkdown(report) {
  const lines = [
    "# Acoustic evidence provenance report",
    "",
    `Registry: \`${report.registryId}\``,
    "",
    "## Immutable outer test",
    "",
    `- Protocol: \`${report.outerTest.protocolId}\``,
    `- Status: ${report.outerTest.status}`,
    `- Storage: ${report.outerTest.storage}`,
    `- Repository contains data: ${report.outerTest.repositoryContainsData ? "yes" : "no"}`,
    `- Candidate freeze required: ${report.outerTest.candidateFreezeRequired ? "yes" : "no"}`,
    "",
    "## Registered sources",
    "",
  ];
  for (const source of report.sources) {
    lines.push(
      `### ${source.title}`,
      "",
      `- ID: \`${source.id}\``,
      `- Status: ${source.status}`,
      `- Creator / instrument: ${source.creator} / ${source.instrument}`,
      `- License: ${source.license}`,
      `- Attribution: ${source.attribution}`,
      `- Product model fitting: ${source.productModelFitting ? "allowed by registered policy" : "isolated"}`,
      `- Pinned distribution commit: \`${source.distributionCommit}\``,
      `- Ingestion receipt present: ${source.ingested ? "yes" : "no"}`,
      "",
    );
    for (const asset of source.registeredAssets) lines.push(`  - ${asset.id} (${asset.role}): ${asset.integrity.algorithm}:${asset.integrity.value}`);
    if (source.receiptAssets.length > 0) {
      lines.push("");
      for (const asset of source.receiptAssets) lines.push(`  - receipt ${asset.assetId}: sha256:${asset.sha256}, ${asset.actualBytes} bytes`);
    }
    lines.push("");
  }
  return `${lines.join("\n")}\n`;
}

function nonEmpty(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isoDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

function isPinnedHttpsUrl(value) {
  return typeof value === "string" && value.startsWith("https://") && /\/[0-9a-f]{40}\//.test(value);
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

function parseCli(argumentsList) {
  const [command, ...rest] = argumentsList;
  const options = {};
  for (let index = 0; index < rest.length; index += 2) {
    const key = rest[index];
    const value = rest[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new RegistryError(`invalid CLI argument near ${key ?? "<end>"}`, "CLI_INVALID");
    options[key.slice(2)] = value;
  }
  return { command, options };
}

async function cli() {
  const { command, options } = parseCli(process.argv.slice(2));
  if (command === "validate") {
    const result = await loadAndValidateRegistry();
    console.log(`validated ${result.registry.sources.length} acoustic source(s)`);
    return;
  }
  if (command === "ingest") {
    if (!options.source) throw new RegistryError("--source is required", "CLI_INVALID");
    const outputRoot = path.resolve(options.output ?? path.join(ROOT, "work/acoustic-data"));
    const { receiptPath } = await ingestSource({ sourceId: options.source, outputRoot });
    console.log(`ingested ${options.source}; receipt=${receiptPath}`);
    return;
  }
  if (command === "report") {
    const outputBase = path.resolve(options.output ?? path.join(ROOT, "work/acoustic-data/provenance-report"));
    const receiptsDirectory = path.resolve(options.receipts ?? path.join(ROOT, "work/acoustic-data/receipts"));
    const report = await buildProvenanceReport({ receiptsDirectory });
    await mkdir(path.dirname(outputBase), { recursive: true });
    await writeFile(`${outputBase}.json`, `${JSON.stringify(report, null, 2)}\n`);
    await writeFile(`${outputBase}.md`, provenanceReportMarkdown(report));
    console.log(`wrote ${outputBase}.json and ${outputBase}.md`);
    return;
  }
  if (command === "seal-holdout") {
    for (const required of ["manifest", "candidate", "metric-plan", "output", "custodian"]) if (!options[required]) throw new RegistryError(`--${required} is required`, "CLI_INVALID");
    const receipt = await sealHoldoutManifest({
      manifestPath: options.manifest,
      candidateId: options.candidate,
      metricPlanPath: options["metric-plan"],
      outputPath: options.output,
      custodian: options.custodian,
    });
    console.log(`sealed holdout commitment ${receipt.manifestSha256}`);
    return;
  }
  throw new RegistryError("usage: acoustic-data-registry.mjs <validate|ingest|report|seal-holdout> [options]", "CLI_INVALID");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  cli().catch((error) => {
    console.error(`${error.name ?? "Error"}: ${error.message}`);
    process.exitCode = 1;
  });
}
