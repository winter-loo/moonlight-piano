from pathlib import Path
import json

root = Path('.')

# Pin SHA-256 alongside Git blob SHA-1.
p = root / 'data/acoustic/registry.json'
data = json.loads(p.read_text())
sha = {
    'c4-mp3': '689eaa4c2fd7f29a2cc0e386eec462156d523a87d701269e5e2458e66056f4f6',
    'license-readme': '04ddba91bcafcb4c53dee7b004479f79af47bb92574f06bbe741b00c3ca64e0e',
}
for asset in data['sources'][0]['assets']:
    asset['integrity']['sha256'] = sha[asset['id']]
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

# Candidate bytes are part of the holdout commitment.
p = root / 'data/acoustic/holdout/protocol.json'
data = json.loads(p.read_text())
data['commitment']['candidateArtifactRequired'] = True
data['commitment']['candidateArtifactAlgorithm'] = 'sha256'
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

p = root / 'scripts/acoustic-data-registry.mjs'
s = p.read_text()
s = s.replace(
'''const SOURCE_STATUSES = new Set(["product-eligible", "research-only", "blocked"]);
const ASSET_ROLES = new Set([''',
'''const SOURCE_STATUSES = new Set(["product-eligible", "research-only", "blocked"]);
const MODEL_PARAMETER_FITTING_POLICIES = new Set([
  "allowed-with-attribution",
  "legal-clearance-required",
  "research-only",
]);
const ASSET_ROLES = new Set([''')
s = s.replace(
'''  if (policy?.schemaVersion !== 1 || !plainObject(policy?.licenses)) {
    errors.push("license policy is missing or unsupported");
  }

  const sourceIds''',
'''  if (policy?.schemaVersion !== 1 || !plainObject(policy?.licenses)) {
    errors.push("license policy is missing or unsupported");
  }
  validateLicensePolicy(policy, errors);

  const sourceIds''')
s = s.replace(
'''      if (!isPinnedHttpsUrl(asset?.url)) errors.push(`${assetPrefix}: URL must be HTTPS and pinned to a 40-character commit`);
      if (!Number.isSafeInteger(asset?.expectedBytes) || asset.expectedBytes <= 0) errors.push(`${assetPrefix}: expectedBytes must be positive`);
      if (asset?.integrity?.algorithm !== "git-sha1" || !/^[0-9a-f]{40}$/.test(asset?.integrity?.value ?? "")) {
        errors.push(`${assetPrefix}: a valid git-sha1 checksum is required`);
      }''',
'''      const pinnedUrlError = validatePinnedAssetUrl(
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
      }''')
needle = '''function validateOrigin(origin, prefix, errors) {
'''
insert = '''function validateLicensePolicy(policy, errors) {
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

'''
assert needle in s
s = s.replace(needle, insert + needle, 1)
s = s.replace(
'''  if (holdout?.commitment?.requiredBeforeFormalEvaluation !== true || holdout?.commitment?.algorithm !== "sha256") errors.push("holdout commitment must be required and use sha256");''',
'''  if (holdout?.commitment?.requiredBeforeFormalEvaluation !== true || holdout?.commitment?.algorithm !== "sha256") errors.push("holdout commitment must be required and use sha256");
  if (holdout?.commitment?.candidateArtifactRequired !== true || holdout?.commitment?.candidateArtifactAlgorithm !== "sha256") errors.push("holdout commitment must bind the frozen candidate artifact with sha256");''')
s = s.replace(
'''export function verifyAssetBuffer(sourceId, asset, buffer) {
  if (buffer.length !== asset.expectedBytes) throw new RegistryError(`${sourceId}:${asset.id} byte length changed: expected ${asset.expectedBytes}, got ${buffer.length}`, "INTEGRITY_MISMATCH");
  const actual = gitBlobSha1(buffer);
  if (actual !== asset.integrity.value) throw new RegistryError(`${sourceId}:${asset.id} checksum changed: expected ${asset.integrity.value}, got ${actual}`, "INTEGRITY_MISMATCH");
}

export async function sealHoldoutManifest({ manifestPath, candidateId, metricPlanPath, outputPath, custodian }) {''',
'''export function verifyAssetBuffer(sourceId, asset, buffer) {
  if (buffer.length !== asset.expectedBytes) throw new RegistryError(`${sourceId}:${asset.id} byte length changed: expected ${asset.expectedBytes}, got ${buffer.length}`, "INTEGRITY_MISMATCH");
  const actualGitSha1 = gitBlobSha1(buffer);
  if (actualGitSha1 !== asset.integrity.value) throw new RegistryError(`${sourceId}:${asset.id} git-sha1 changed: expected ${asset.integrity.value}, got ${actualGitSha1}`, "INTEGRITY_MISMATCH");
  const actualSha256 = sha256(buffer);
  if (actualSha256 !== asset.integrity.sha256) throw new RegistryError(`${sourceId}:${asset.id} sha256 changed: expected ${asset.integrity.sha256}, got ${actualSha256}`, "INTEGRITY_MISMATCH");
}

export async function sealHoldoutManifest({ manifestPath, candidateId, candidateArtifactPath, metricPlanPath, outputPath, custodian }) {''')
s = s.replace(
'''  const [manifest, metricPlan] = await Promise.all([readFile(absoluteManifest), readFile(path.resolve(metricPlanPath))]);
  const receipt = {
    schemaVersion: 1,
    protocolId: "professional-piano-outer-test-v1",
    candidateId,
    custodian,
    manifestSha256: sha256(manifest),
    metricPlanSha256: sha256(metricPlan),''',
'''  const [manifest, candidateArtifact, metricPlan] = await Promise.all([
    readFile(absoluteManifest),
    readFile(path.resolve(candidateArtifactPath)),
    readFile(path.resolve(metricPlanPath)),
  ]);
  const receipt = {
    schemaVersion: 1,
    protocolId: "professional-piano-outer-test-v1",
    candidateId,
    custodian,
    candidateArtifactSha256: sha256(candidateArtifact),
    candidateArtifactBytes: candidateArtifact.length,
    manifestSha256: sha256(manifest),
    metricPlanSha256: sha256(metricPlan),''')
s = s.replace(
'''      || received.gitSha1 !== registered.integrity.value
      || !/^[0-9a-f]{64}$/.test(received.sha256 ?? "")) {''',
'''      || received.gitSha1 !== registered.integrity.value
      || received.sha256 !== registered.integrity.sha256) {''')
s = s.replace(
'''function isPinnedHttpsUrl(value) {
  return typeof value === "string" && value.startsWith("https://") && /\/[0-9a-f]{40}\//.test(value);
}
''',
'''function validatePinnedAssetUrl(value, repository, commit) {
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
''')
s = s.replace(
'''    for (const required of ["manifest", "candidate", "metric-plan", "output", "custodian"]) if (!options[required]) throw new RegistryError(`--${required} is required`, "CLI_INVALID");
    const receipt = await sealHoldoutManifest({
      manifestPath: options.manifest,
      candidateId: options.candidate,
      metricPlanPath: options["metric-plan"],''',
'''    for (const required of ["manifest", "candidate", "candidate-artifact", "metric-plan", "output", "custodian"]) if (!options[required]) throw new RegistryError(`--${required} is required`, "CLI_INVALID");
    const receipt = await sealHoldoutManifest({
      manifestPath: options.manifest,
      candidateId: options.candidate,
      candidateArtifactPath: options["candidate-artifact"],
      metricPlanPath: options["metric-plan"],''')
p.write_text(s)

# Persistent integration branch and index-wide raw guard.
p = root / '.github/workflows/acoustic-data-registry.yml'
s = p.read_text()
s = s.replace('''    branches:
      - feat/acoustic-data-registry
''', '''    branches:
      - main
      - feat/acoustic-data-registry
''', 1)
s = s.replace('''      - name: Confirm raw assets are not tracked
        run: |
          test -z "$(git status --short --untracked-files=all work/acoustic-data/raw)"
          git check-ignore work/acoustic-data/raw/salamander-tonejs-c4/C4.mp3
''', '''      - name: Confirm raw assets are ignored and absent from the Git index
        run: |
          test -z "$(git ls-files -- work/acoustic-data/raw)"
          test -z "$(git status --short --untracked-files=all work/acoustic-data/raw)"
          git check-ignore work/acoustic-data/raw/salamander-tonejs-c4/C4.mp3
''')
p.write_text(s)

# Candidate artifact required by the documented protocol.
p = root / 'docs/audio/acoustic-data-registry.md'
s = p.read_text()
s = s.replace('''  --candidate candidate-001 \\
  --metric-plan''', '''  --candidate candidate-001 \\
  --candidate-artifact /outside-the-repository/candidate-001.mlpiano \\
  --metric-plan''')
s = s.replace('''only SHA-256 commitments and release identifiers, never sample names, URLs,
labels, or per-sample results.''', '''only SHA-256 commitments for the private manifest, frozen candidate artifact,
and metric plan plus release identifiers—never sample names, URLs, labels, or
per-sample results. Rebuilding the candidate changes its commitment and requires
a new sealed evaluation.''')
p.write_text(s)
