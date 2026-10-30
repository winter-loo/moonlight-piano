# C4 hammer performance evidence — absolute gate not passed

These are the original JSON reports from the 2026-10-21 local smoke measurements.
They are copied byte-for-byte from their measured outputs. No failed case was
removed, replaced by a later result, or used to relax a threshold.

## Reports

| File | Measurement | Absolute budget result |
| --- | --- | --- |
| [hammer-baseline-performance.json](hammer-baseline-performance.json) | Original impulse-tracer baseline, unpinned shared container | Zero observed deadline misses; raw baseline retained |
| [hammer-candidate-performance.json](hammer-candidate-performance.json) | First nonlinear-hammer candidate, unpinned shared container | **Failed**: five misses across 44.1 kHz / 64- and 128-frame cases |
| [hammer-baseline-performance-quiet.json](hammer-baseline-performance-quiet.json) | Follow-up baseline, fixed CPU 0, first in sequential pair | Passed absolute smoke checks; zero observed misses |
| [hammer-candidate-performance-quiet.json](hammer-candidate-performance-quiet.json) | Follow-up candidate, same CPU 0, second in sequential pair | **Failed**: three misses at 48 kHz / 64 frames, maximum `R=3.04902225` |

The pair ran while local builds and other coordinated heavy work were paused.
The container and underlying host were still shared; unrelated work and hardware
scheduling were not controlled. There was exactly one follow-up pair, not a
repeat-until-passing procedure. Each report contains the same eight rate/block
cases, 256 warmup blocks and 2,048 measured calls per case.

`R` means render-call wall time divided by the block's audio duration. The
absolute limits remain p50 ≤ 0.25, p99 ≤ 0.45, p99.99 ≤ 0.70, and zero observed
deadline misses. With this observation count p99.99 is the maximum, so
`tailResolutionSufficient=false`. No dedicated or thermal certification is
claimed. The checker intentionally refuses to compare smoke runs as formal
dedicated baselines; numerical cost comparisons in the
[quality report](../../c4-hammer-quality.md) are informational.

## Source and binary identity

The clean baseline is commit
`86638cef0a3d6f86e7620d441b70092767ecf42f`.

The candidate's `sourceRevision` is:

```text
86638cef0a3d6f86e7620d441b70092767ecf42f+worktree-patch-sha256:3517f9fc75056bc304d0daddee71521b691c23c30eec06ce32be29a386b676f4
```

This identifies the complete tracked source closure used to build
`moonlight-bench`; unrelated UI, host, test and documentation edits are outside
that build closure. The candidate source itself is committed with this evidence.
Candidate `localEvidence.sourceClosureSha256` records each input file separately,
and the files were checked again after measurement. The quiet reports also record
the executed binary hash. The frozen DSP hashes are:

| File | SHA-256 |
| --- | --- |
| `crates/moonlight-dsp/src/lib.rs` | `120fe9db15d9291a2a2ecf4d08e74c364639a0e1efe2788435a94bb2e5bc4039` |
| `crates/moonlight-dsp/src/realtime.rs` | `65c7bd3622c9379279b17b99f41276df9e975976d4643f0bd207d658d14f1b27` |
| Unchanged `crates/moonlight-dsp/src/basic.rs` | `1d520b0ed200361c6f30d0dee19fca8bbf8df4d462e17c13838221d172e89fc7` |

Some `localEvidence.command` values retain absolute temporary paths from the
original host. They are raw measurement metadata, not required installation paths
or reproduction instructions. Relative links in this bundle identify the durable
evidence. The raw reports were not rewritten to make their hashes look cleaner.

## Verify the evidence

Run from the repository root:

```sh
python3 scripts/check-realtime-report.py \
  docs/audio/evidence/c4-hammer-performance/hammer-candidate-performance.json
python3 scripts/check-realtime-report.py \
  docs/audio/evidence/c4-hammer-performance/hammer-candidate-performance.json \
  --enforce-budget
python3 scripts/check-realtime-report.py \
  docs/audio/evidence/c4-hammer-performance/hammer-candidate-performance-quiet.json \
  --enforce-budget
```

The first command validates schema and finite observations. The second and third
commands are **expected to fail** on the preserved measurements. A successful
schema check must not be presented as passed timing budgets.

## Reproduce a new smoke observation

For a clean checkout of the revision being measured:

```sh
cargo build --release -p moonlight-bench
MOONLIGHT_SOURCE_REVISION=$(git rev-parse HEAD) \
  target/release/moonlight-bench --mode smoke --blocks 2048 \
  --device-id local-development --output work/realtime/new-observation.json
python3 scripts/check-realtime-report.py work/realtime/new-observation.json \
  --enforce-budget
```

To reconstruct and verify the original measured source patch from this checkout:

```sh
python3 - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
report = json.loads(Path('docs/audio/evidence/c4-hammer-performance/hammer-candidate-performance.json').read_text())
files = list(report['localEvidence']['sourceClosureSha256'])
patch = subprocess.check_output(['git', 'diff', '--binary', '86638cef0a3d6f86e7620d441b70092767ecf42f', '--', *files])
assert hashlib.sha256(patch).hexdigest() == report['sourceRevision'].split(':')[-1]
Path('work').mkdir(exist_ok=True)
Path('work/hammer-candidate-source.patch').write_bytes(patch)
PY
```

Apply that verified patch to a separate clean baseline checkout to rebuild the
original experiment. Record the commit-plus-patch identity above rather than a
bare baseline commit ID. For an affinity diagnostic, choose
an allowed CPU on that host and prefix each already-built binary invocation with
`taskset -c CPU`. Run baseline then candidate on the same CPU, preserve both
reports, and record competing-work conditions. No reproduction command changes
the frozen reports in this directory.

## File hashes

| File | SHA-256 |
| --- | --- |
| `hammer-baseline-performance.json` | `b3cb4b839fdb504d801699444330bcccf05789f25c016bbb9afd6e6e2d0dd282` |
| `hammer-candidate-performance.json` | `b8a5b43a12046fe1652a5427b018776d453f88728fd844bc2ccfb86e7126734e` |
| `hammer-baseline-performance-quiet.json` | `7af60432d326e2cbcdddda2a4921bffad455b192d363e813c26aad6596b4cd17` |
| `hammer-candidate-performance-quiet.json` | `96ab7e8e97ce8b50decef8182cbcad20691cfda08650bf9b05cf0f9665fd5d5f` |
