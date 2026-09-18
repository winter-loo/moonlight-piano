# Acoustic data registry and immutable holdout protocol

The physical-piano project can use external recordings as **offline evidence**,
but runtime instruments may contain only physical parameters, reduced models,
and other permitted coefficients. Raw note, release, pedal, and resonance audio
must never be committed or embedded in a model pack.

## Registry

`data/acoustic/registry.json` records, for every source:

- origin and immutable distribution commit;
- retrieval date;
- SPDX license and checksummed license evidence;
- explicit commercial, fitting, runtime, redistribution, and research use;
- processing steps;
- byte length and Git blob checksum for every asset;
- whether the source is product-eligible, research-only, or blocked.

`data/acoustic/license-policy.json` is deliberately fail-closed. Unknown licenses
fail validation. Non-commercial sources cannot enter product model fitting.
Share-alike sources require a documented legal clearance before they can be
marked product-eligible.

## Reproducible ingestion

The first registered acoustic probe is the Salamander Grand Piano C4 file and
its source/license README, pinned to commit
`efd8296360f9526e379bfbe5c1698ff54d6a1d34` of `Tonejs/audio`. The source README
identifies Alexander Holm, a Yamaha C5, and CC BY 3.0. The full upstream library
contains 16 velocity layers sampled in minor thirds; this ticket downloads only
the registered C4 probe needed to prove the evidence pipeline.

```bash
npm run acoustic:validate
npm run acoustic:ingest:all
npm run acoustic:report
```

Downloads go under ignored `work/acoustic-data/raw/`. Before a byte is accepted,
the tool checks the expected size, Git blob SHA-1 and registered SHA-256.
The local receipt records those verified values. A changed byte count, checksum, license, attribution, or use
policy fails the command.

The provenance report is written as Markdown and JSON under
`work/acoustic-data/`; those reports and receipts can be attached to a model-pack
or release review. Raw audio remains excluded.

## Development evidence roles

`data/acoustic/development-splits.json` separates:

1. calibration;
2. inspectable development validation;
3. cross-piano validation;
4. the immutable outer test.

An inspectable asset cannot appear in more than one role. The outer test commits
no asset reference at all.

## Immutable outer test

`data/acoustic/holdout/protocol.json` defines an external-custodian protocol:

- neither data nor locators enter the repository;
- developers, tuning agents, and automation agents cannot inspect it;
- the candidate, metric plan, thresholds, and failure policy are frozen first;
- the custodian runs a one-shot gate and returns aggregate pass/fail before the
  release decision;
- inspected data permanently loses outer-test status;
- repartitioning the same inspected corpus cannot restore independence.

A custodian can publish a commitment without disclosing the manifest:

```bash
node scripts/acoustic-data-registry.mjs seal-holdout \
  --manifest /outside-the-repository/private-manifest.json \
  --candidate candidate-001 \
  --candidate-artifact /outside-the-repository/candidate-001.mlpiano \
  --metric-plan /outside-the-repository/frozen-metrics.json \
  --custodian independent-reviewer \
  --output work/acoustic-data/holdout-commitment.json
```

The command refuses a private manifest located inside the repository and writes
only SHA-256 commitments for the private manifest, frozen candidate artifact,
and metric plan plus release identifiers—never sample names, URLs, labels, or
per-sample results. Rebuilding the candidate changes its commitment and requires
a new sealed evaluation.

The metric plan is validated before it can be sealed. It must be JSON with
`schemaVersion: 1`, the exact `candidateId`, at least one metric containing an
`id`, `comparison` (`lte` or `gte`), and finite `threshold`, plus non-empty
`statisticalMethod` and `failureCriteria`. Empty or arbitrary bytes cannot
produce a valid-looking holdout commitment.

CI uses `ingest-all` and requires a valid receipt for every non-blocked source,
so adding a registry entry also adds its URL, byte length, both checksums, and
license evidence to the end-to-end integrity gate.

## Read-only validation workflow

CI no longer reconstructs source files from a compressed payload or commits and
pushes corrections. The fixes are normal, reviewable source. The workflow uses
`contents: read`, does not persist checkout credentials, and verifies the tracked
worktree remains unchanged. Full application tests, lint and build remain in
place alongside acoustic tests. Raw data and final holdout data are not uploaded.

`ingest-all` takes one validated registry snapshot and processes all non-blocked
sources. It never promotes a research-only source to commercial calibration;
source status and permissions remain attached to every receipt. Explicitly
requesting a blocked source fails. The npm report command uses `--require-all true`
to reject missing receipts for any non-blocked source, not only the first C4.

Downloads have a 60-second timeout, a 256 MiB per-asset budget, registered byte
limits and no redirects. Nested symlinks and non-basename asset names are rejected.
An existing cached asset or receipt must match exactly; ingestion never silently
overwrites tampered evidence. Caller-controlled output storage must still be
protected by normal filesystem permissions. These checks are not a substitute
for external-custodian access control or legal review.
