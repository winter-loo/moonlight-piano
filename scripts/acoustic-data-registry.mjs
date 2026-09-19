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
const DEFAULT_CLEARANCES = path.join(ROOT, "data/acoustic/legal-clearances.json");
const SOURCE_STATUSES = new Set(["product-eligible", "research-only", "blocked"]);
const MODEL_PARAMETER_FITTING_POLICIES = new Set([
  "allowed-with-attribution",
  "legal-clearance-required",
  "research-only",
]);
const SAFE_ID = /^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$/;
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

export function validateRegistryDocument(registry, policy, splits, holdout, clearances = { schemaVersion: 1, clearances: [] }) {
  const errors = [];
  const clearanceById = validateLegalClearances(clearances, errors);
  if (registry?.schemaVersion !== 1) errors.push("registry.schemaVersion must be 1");
  if (!nonEmpty(registry?.registryId)) errors.push("registryId is required");
  if (!isoDate(registry?.updatedAt)) errors.push("updatedAt must be YYYY-MM-DD");
  if (!Array.isArray(registry?.sources) || registry.sources.length === 0) {
    errors.push("at least one source is required");
  }
  if (policy?.schemaVersion !== 1 || !plainObject(policy?.licenses)) {
    errors.push("license policy is missing or unsupported");
  }
  validateLicensePolicy(policy, errors);

  const sourceIds = new Set();
  const assetsByReference = new Map();
  for (const source of registry?.sources ?? []) {
    const prefix = `source ${source?.id ?? "<missing>"}`;
    if (!nonEmpty(source?.id)) errors.push(`${prefix}: id is required`);
    else if (!SAFE_ID.test(source.id)) errors.push(`${prefix}: id must be a safe single path segment`);
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
      if (rule.shareAlike && source.status === "product-eligible") {
        const clearanceId = source?.license?.clearanceId;
        const clearance = nonEmpty(clearanceId) ? clearanceById.get(clearanceId) : null;
        if (!clearance) {
          errors.push(`${prefix}: share-alike source requires registered legal clearance before product use`);
        } else if (
          clearance.sourceId !== source.id
          || clearance.licenseSpdx !== spdx
          || clearance.status !== "approved-for-product-model-fitting"
        ) {
          errors.push(`${prefix}: legal clearance does not match this source/license/product-fitting use`);
        }
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
      else if (asset.fileName !== path.basename(asset.fileName) || asset.fileName === "." || asset.fileName === "..") {
        errors.push(`${assetPrefix}: fileName must be a basename confined to the source raw directory`);
      }
      const pinnedUrlError = validatePinnedAssetUrl(
        asset?.url,
        source?.origin?.distributionRepository,
        source?.origin?.distributionCommit,
      );
      if (pinnedUrlError) errors.push(`${assetPrefix}: ${pinnedUrlError}`);
      if (!Number.isSafeInteger(asset?.expectedBytes) || asset.expectedBytes <= 0) errors.push(`${assetPrefix}: expectedBytes must be positive`);
      if (asset?.integrity?.algorithm !== "git-sha1" || !/^[0-9a-f]{40}$/.test(asset?.integrity?.value ?? "")) {
        errors.push(`${assetPrefix}: a valid git-sha1 checksum is required`);
      }
      if (!/^[0-9a-f]{64}$/.test(asset?.integrity?.sha256 ?? "")) {
        errors.push(`${assetPrefix}: a registered sha256 checksum is required`);
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

function validateLicensePolicy(policy, errors) {
  if (!plainObject(policy?.licenses)) return;
  const entries = Object.entries(policy.licenses);
  if (entries.length === 0) errors.push("license policy must define at least one license");
  for (const [spdx, rule] of entries) {
    const prefix = `license policy ${spdx}`;
    if (!nonEmpty(spdx) || !plainObject(rule)) {
      errors.push(`${prefix}: rule must be an object`);
      continue;
    }
    for (const key of ["commercialUse", "attributionRequired", "shareAlike"]) {
      if (typeof rule[key] !== "boolean") errors.push(`${prefix}: ${key} must be boolean`);
    }
    if (!MODEL_PARAMETER_FITTING_POLICIES.has(rule.modelParameterFitting)) {
      errors.push(`${prefix}: modelParameterFitting must be a supported policy value`);
    }
  }
}

function validateLegalClearances(document, errors) {
  const byId = new Map();
  if (document?.schemaVersion !== 1 || !Array.isArray(document?.clearances)) {
    errors.push("legal-clearances registry is missing or unsupported");
    return byId;
  }
  for (const clearance of document.clearances) {
    const prefix = `legal clearance ${clearance?.id ?? "<missing>"}`;
    if (!nonEmpty(clearance?.id) || !SAFE_ID.test(clearance.id)) {
      errors.push(`${prefix}: id must be a safe identifier`);
      continue;
    }
    if (byId.has(clearance.id)) errors.push(`${prefix}: duplicate clearance id`);
    if (!nonEmpty(clearance?.sourceId) || !SAFE_ID.test(clearance.sourceId)) errors.push(`${prefix}: sourceId is required`);
    if (!nonEmpty(clearance?.licenseSpdx)) errors.push(`${prefix}: licenseSpdx is required`);
    if (clearance?.status !== "approved-for-product-model-fitting") errors.push(`${prefix}: status must explicitly approve product model fitting`);
    if (!nonEmpty(clearance?.reviewer)) errors.push(`${prefix}: reviewer is required`);
    if (!isoDate(clearance?.decidedAt)) errors.push(`${prefix}: decidedAt must be YYYY-MM-DD`);
    if (!/^[0-9a-f]{64}$/.test(clearance?.evidenceSha256 ?? "")) errors.push(`${prefix}: evidenceSha256 must identify the reviewed legal evidence`);
    byId.set(clearance.id, clearance);
  }
  return byId;
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
      else {
        if (entry.asset.role !== expectedAssetRole) errors.push(`${reference} is assigned to ${roleName} but declares ${entry.asset.role}`);
        if (
          roleName === "calibration"
          && (
            entry.source.status !== "product-eligible"
            || entry.source.permittedUse?.commercial !== true
            || entry.source.permittedUse?.modelParameterFitting !== true
          )
        ) {
          errors.push(`${reference} cannot enter calibration without product-eligible commercial fitting permission`);
        }
      }
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
  const permittedActors = holdout?.access?.permittedActors;
  const deniedActors = holdout?.access?.deniedActors;
  if (!Array.isArray(permittedActors) || permittedActors.length !== 1 || permittedActors[0] !== "release-gate-custodian") {
    errors.push("holdout permittedActors must contain only release-gate-custodian");
  }
  for (const actor of ["developers", "tuning-agents", "automation-agents"]) {
    if (!deniedActors?.includes(actor)) errors.push(`holdout must deny ${actor}`);
  }
  if (Array.isArray(permittedActors) && Array.isArray(deniedActors) && permittedActors.some((actor) => deniedActors.includes(actor))) {
    errors.push("holdout permittedActors and deniedActors must be disjoint");
  }
  if (holdout?.access?.reveal !== "one-shot-after-candidate-freeze") errors.push("holdout reveal must be one-shot after candidate freeze");
  if (holdout?.access?.preDecisionOutput !== "aggregate-pass-fail-only") errors.push("holdout may reveal only aggregate pass/fail before the release decision");
  if (holdout?.commitment?.requiredBeforeFormalEvaluation !== true || holdout?.commitment?.algorithm !== "sha256") errors.push("holdout commitment must be required and use sha256");
  if (holdout?.commitment?.candidateArtifactRequired !== true || holdout?.commitment?.candidateArtifactAlgorithm !== "sha256") errors.push("holdout commitment must bind the frozen candidate artifact with sha256");
  if (holdout?.commitment?.manifestNonceRequired !== true || !Number.isSafeInteger(holdout?.commitment?.manifestNonceMinimumBytes) || holdout.commitment.manifestNonceMinimumBytes < 32) errors.push("holdout commitment must require a private high-entropy manifest nonce of at least 32 bytes");
  if (holdout?.commitment?.metricPlanValidationRequired !== true) errors.push("holdout commitment must require a validated metric plan");
  if (holdout?.failurePolicy?.inspectedDataPermanentlyLeavesOuterTest !== true) errors.push("inspected data must permanently leave the outer test");
  if (holdout?.failurePolicy?.repartitionDoesNotRestoreIndependence !== true) errors.push("holdout policy must forbid independence by repartitioning");
  if (!nonEmpty(holdout?.failurePolicy?.nextCandidateRequires)) errors.push("holdout must define evidence requirements for the next candidate after failure");
}

export async function loadAndValidateRegistry(options = {}) {
  const [registry, policy, splits, holdout, clearances] = await Promise.all([
    readJson(options.registryPath ?? DEFAULT_REGISTRY),
    readJson(options.policyPath ?? DEFAULT_POLICY),
    readJson(options.splitsPath ?? DEFAULT_SPLITS),
    readJson(options.holdoutPath ?? DEFAULT_HOLDOUT),
    readJson(options.clearancesPath ?? DEFAULT_CLEARANCES),
  ]);
  return validateRegistryDocument(registry, policy, splits, holdout, clearances);
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
    const localPath = confinedPath(rawDirectory, asset.fileName);
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

export async function ingestAllSources({ outputRoot, fetchImpl = fetch }) {
  const validated = await loadAndValidateRegistry();
  const results = [];
  for (const source of validated.registry.sources) {
    if (source.status === "blocked") continue;
    results.push(await ingestSource({ sourceId: source.id, outputRoot, fetchImpl }));
  }
  return results;
}

export function verifyAssetBuffer(sourceId, asset, buffer) {
  if (buffer.length !== asset.expectedBytes) throw new RegistryError(`${sourceId}:${asset.id} byte length changed: expected ${asset.expectedBytes}, got ${buffer.length}`, "INTEGRITY_MISMATCH");
  const actualGitSha1 = gitBlobSha1(buffer);
  if (actualGitSha1 !== asset.integrity.value) throw new RegistryError(`${sourceId}:${asset.id} git-sha1 changed: expected ${asset.integrity.value}, got ${actualGitSha1}`, "INTEGRITY_MISMATCH");
  const actualSha256 = sha256(buffer);
  if (actualSha256 !== asset.integrity.sha256) throw new RegistryError(`${sourceId}:${asset.id} sha256 changed: expected ${asset.integrity.sha256}, got ${actualSha256}`, "INTEGRITY_MISMATCH");
}

export async function sealHoldoutManifest({
  manifestPath,
  manifestNoncePath,
  candidateId,
  candidateArtifactPath,
  metricPlanPath,
  outputPath,
  custodian,
}) {
  const absoluteManifest = path.resolve(manifestPath);
  const absoluteNonce = path.resolve(manifestNoncePath);
  assertOutsideRepository(absoluteManifest, "private holdout manifest");
  assertOutsideRepository(absoluteNonce, "private holdout manifest nonce");
  if (!nonEmpty(candidateId) || !nonEmpty(custodian)) throw new RegistryError("candidateId and custodian are required", "HOLDOUT_INVALID");

  const [manifest, manifestNonce, candidateArtifact, metricPlanBytes] = await Promise.all([
    readFile(absoluteManifest),
    readFile(absoluteNonce),
    readFile(path.resolve(candidateArtifactPath)),
    readFile(path.resolve(metricPlanPath)),
  ]);
  if (manifestNonce.length < 32) {
    throw new RegistryError("private holdout manifest nonce must contain at least 32 bytes of custodian entropy", "HOLDOUT_INVALID");
  }
  const metricPlan = validateMetricPlan(metricPlanBytes);
  const manifestCommitment = sha256(Buffer.concat([
    Buffer.from("moonlight-holdout-manifest-v1\0", "utf8"),
    manifestNonce,
    Buffer.from("\0", "utf8"),
    manifest,
  ]));
  const receipt = {
    schemaVersion: 1,
    protocolId: "professional-piano-outer-test-v1",
    candidateId,
    custodian,
    candidateArtifactSha256: sha256(candidateArtifact),
    candidateArtifactBytes: candidateArtifact.length,
    manifestCommitmentSha256: manifestCommitment,
    metricPlanSha256: sha256(metricPlanBytes),
    metricPlanSchemaVersion: metricPlan.schemaVersion,
    disclosure: "commitments only; private manifest nonce and holdout locators remain with the custodian",
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
      || received.sha256 !== registered.integrity.sha256) {
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

function confinedPath(directory, fileName) {
  const base = path.resolve(directory);
  const target = path.resolve(base, fileName);
  const relative = path.relative(base, target);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative) || path.basename(fileName) !== fileName) {
    throw new RegistryError(`asset fileName escapes raw directory: ${fileName}`, "PATH_INVALID");
  }
  return target;
}

function assertOutsideRepository(absolutePath, label) {
  const relativeToRoot = path.relative(ROOT, absolutePath);
  if (!relativeToRoot.startsWith("..") && !path.isAbsolute(relativeToRoot)) {
    throw new RegistryError(`${label} must live outside the repository`, "HOLDOUT_EXPOSURE_RISK");
  }
}

function validateMetricPlan(bytes) {
  let plan;
  try {
    plan = JSON.parse(Buffer.from(bytes).toString("utf8"));
  } catch {
    throw new RegistryError("metric plan must be valid JSON", "HOLDOUT_INVALID");
  }
  if (
    plan?.schemaVersion !== 1
    || !Array.isArray(plan?.metrics)
    || plan.metrics.length === 0
    || plan.metrics.some((metric) => !nonEmpty(metric?.id) || !Number.isFinite(metric?.threshold))
    || !nonEmpty(plan?.statisticalMethod)
    || !nonEmpty(plan?.failureCriteria)
  ) {
    throw new RegistryError("metric plan must freeze metrics, thresholds, statisticalMethod, and failureCriteria", "HOLDOUT_INVALID");
  }
  return plan;
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

function validatePinnedAssetUrl(value, repository, commit) {
  if (typeof value !== "string" || !nonEmpty(repository) || !/^[0-9a-f]{40}$/.test(commit ?? "")) {
    return "URL, repository, and immutable commit are required";
  }
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return "URL must be valid";
  }
  if (parsed.protocol !== "https:" || parsed.hostname !== "raw.githubusercontent.com") {
    return "URL must use HTTPS raw.githubusercontent.com distribution";
  }
  const segments = parsed.pathname.split("/").filter(Boolean);
  if (segments.length < 4) return "URL must contain owner, repository, commit, and asset path";
  const urlRepository = `${segments[0]}/${segments[1]}`;
  if (urlRepository !== repository) return `URL repository ${urlRepository} does not match declared ${repository}`;
  if (segments[2] !== commit) return `URL commit ${segments[2]} does not match declared ${commit}`;
  return null;
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
  if (command === "ingest-all") {
    const outputRoot = path.resolve(options.output ?? path.join(ROOT, "work/acoustic-data"));
    const results = await ingestAllSources({ outputRoot });
    console.log(`ingested ${results.length} registered acoustic source(s)`);
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
    for (const required of ["manifest", "manifest-nonce", "candidate", "candidate-artifact", "metric-plan", "output", "custodian"]) if (!options[required]) throw new RegistryError(`--${required} is required`, "CLI_INVALID");
    const receipt = await sealHoldoutManifest({
      manifestPath: options.manifest,
      manifestNoncePath: options["manifest-nonce"],
      candidateId: options.candidate,
      candidateArtifactPath: options["candidate-artifact"],
      metricPlanPath: options["metric-plan"],
      outputPath: options.output,
      custodian: options.custodian,
    });
    console.log(`sealed holdout commitment ${receipt.manifestSha256}`);
    return;
  }
  throw new RegistryError("usage: acoustic-data-registry.mjs <validate|ingest|ingest-all|report|seal-holdout> [options]", "CLI_INVALID");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  cli().catch((error) => {
    console.error(`${error.name ?? "Error"}: ${error.message}`);
    process.exitCode = 1;
  });
}
