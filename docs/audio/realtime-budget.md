# Realtime contract and performance evidence (#5)

Baseline: PR #37, `4e552d261bade72b3dfb60a54f591b709ba37c77`.
The audible C4 recurrence and event order are retained. This does **not** certify
88-key polyphony, a browser AudioWorklet, SIMD, mobile latency, or thermal behavior.

## Audited render boundary

`PianoEngine::new` is non-realtime and compiles a validated model. Audio starts
only after model, host buffers and observer storage exist. `process_block`,
`reset`, and `state_counts` do not allocate or retain events. The realtime module
is private, uses only core, forbids unsafe, and is separately compiled without
std. There is no OS, allocator, file, socket, log, thread, mutex, or async API in
that closure. The tiny host wrapper maps static errors and silences valid-size
buffers on error. Initialization/error formatting is outside the render closure.

Events are borrowed sorted absolute sample frames. There is no internal queue.
The published limits are 256 events/block and 16384 frames/block; oversize inputs
are rejected before state mutation. Work is O(frames * configured_modes + events),
bounded by these limits and the validated fixed mode capacity. A future host
must expose overflow, not silently drop pedal/note-off events or allocate a queue.

## Evidence, and its limits

- `cargo test -p moonlight-dsp --test realtime_contract`: TLS-scoped global
  allocator observation of alloc/alloc_zeroed/realloc/dealloc. A real allocation
  negative control proves the observer runs. It never panics inside GlobalAlloc.
- `sh scripts/check-realtime-boundary.sh`: compile actual production realtime
  source as no_std, require a retained render symbol, inspect external symbols,
  and reject unreviewed source sets,
  unsafe/FFI, dynamic containers, panic/unwrap, includes and open-ended loops.
- Workspace tests plus partition tests exercise event flood, invalid input,
  tails, reset and callback boundaries. Existing model validation remains tested.
- Release profile is panic=abort. This alone is **not** a no-panic proof: compiler
  symbol inspection rejects panic runtime edges from the audited render object.
- Static and dynamic checks complement one another. They are not a theorem about
  arbitrary future code or OS scheduling. Dependencies, wrappers and new modules
  require another render-closure audit. Hardware stalls cannot be ruled out by CI.

GlobalAlloc observations are evidence for the executed build, not proof that an
optimizer preserves every source allocation. The standalone no_std/link check rejects external allocator/system-API edges in
the compiled inner renderer. It is scoped to that object, not the whole host.

## Reproduce

```sh
cargo test --workspace
sh scripts/check-realtime-boundary.sh
MOONLIGHT_SOURCE_REVISION=$(git rev-parse HEAD) cargo run --release -p moonlight-bench -- \
  --mode smoke --blocks 2048 --device-id local-development --output work/realtime/current.json
python3 scripts/check-realtime-report.py work/realtime/current.json
python3 -m unittest discover -s tests/realtime -v
```

The eight cases cover 44100/48000 Hz and 64/128/256/512 frames. Each has 256
warmup blocks, individual render-call timings including clock overhead, nearest-rank
p50/p99/p99.99/max, deadline misses, and measured active state counts. A 2048-block
p99.99 is essentially the maximum: `tailResolutionSufficient=false` explicitly
marks the tail as under-resolved; it is not a confidence guarantee. The benchmark keeps the same C4
state active via bounded repeated excitation; it is not a full-piano load claim.

Every report records CPU, architecture, OS, compiler/host target, source revision,
scalar-f64 path, executable/model size, model fingerprint, fixed engine memory,
output memory, and separately allocated timing observation memory. Timings are
not included in deterministic audio checksum comparisons. A dirty worktree must
be identified as `COMMIT+worktree-patch-sha256:PATCH_DIGEST`; a bare commit ID must
not claim evidence produced by modified code. The workflow records the actual
checkout revision, including the merge revision on pull-request runs.

Without a comparison baseline, the checker returns `regressions: null`, not an
empty list that might suggest a completed comparison. For a local smoke run,
`--enforce-budget` additionally checks the absolute thresholds and every observed
deadline miss. Dedicated runs always enforce these thresholds. Hosted smoke
runs keep timing observations distinct from release certification; none of these
measurements proves real-device callback timing or absence of device underruns.

## Dedicated baselines and regressions

Run on a reserved device with fixed power/thermal settings, idle competing work,
and a recorded device ID. Use `--mode dedicated --blocks 100000 --device-id ID`.
Do not run arbitrary PR code on a self-hosted runner holding secrets. This PR
intentionally does not auto-schedule self-hosted jobs or invent reference devices.
Archive the immutable JSON and environment/power/thermal notes together.

```sh
python3 scripts/check-realtime-report.py work/realtime/current.json \
  --baseline evidence/previous.json --change-report evidence/change.json
```

Only equivalent dedicated device/toolchain/kernel/scene/count runs are compared.
Absolute budgets are p50 <= .25, p99 <= .45, p99.99 <= .70, zero deadline misses.
An acoustic-benefit explanation cannot waive them. A >10% relative increase in
CPU percentiles, engine/output memory, executable or model size requires a report
bound to SHA-256 of both JSON files, `acousticBenefit`, `reviewReference`, and
`errorMetrics` entries with measured `name`, `unit`, `before`, `after`. Numeric
CPU/memory/size deltas come from the reports, not handwritten claims. A compiler
or device change requires a new comparable baseline, not a misleading ratio.

No dedicated or mobile baseline exists merely because CI artifacts exist.
30-minute thermal gates and full-model loads remain the release certification
work. Ordinary CI gates only deterministic conformance, observer self-tests,
static/link audit, complete benchmark schema and finite observations.

References: Rust GlobalAlloc safety contract
<https://doc.rust-lang.org/core/alloc/trait.GlobalAlloc.html>;
project professional spec sections 14, 16, 19 and 20.

## Recorded local evidence and cleanup status

On 2026-09-18 the owner validated commit
`fac994528d69c4129f13e650a1f7c9656a0e3c77` plus the Rust 1.82 formatting patch
`1ae93efff47ebe8b51869fe04babee6b1d9b477253ad99037d369caa3bf3777b`
on macOS 15.7.8 / x86_64 / Intel i5-8259U. That exact formatting change is
included in this cleanup; the DSP equations and event behavior are unchanged.

The recorded run passed Clippy, 20 workspace tests, the five realtime contract
tests in both debug and release, WASM compilation, source/object audit, and two
byte-identical WAV/metrics/energy renders. It also measured 100,000 calls for each
of eight rate/block combinations with zero observed `R >= 1`. The scene contains
one string and eight modes, not a complete piano. Performance JSON SHA-256:
`3054888af01f219ff01c0cbccc1d320149b5e98c7f88d23dc981ba1bd5b5de8b`.
The immutable original report retains its commit-plus-patch identity.

This is historical local evidence, not a fresh execution of every cleanup
script or a dedicated-device baseline. The cleanup adds policy tests, makes the
compiled-object check reject a missing renderer, updates the reviewed wrapper
digest for the formatting change, invokes the Bash render script with Bash,
and compares the energy CSV as well as WAV/metrics. New revisions require their
own validation logs. GitHub-hosted jobs were blocked before startup by account
billing limits; no synthetic passing status replaces them.

The public wrapper has an explicit reviewed-source digest as a conservative
change guard; this is not a general Rust static analyzer. Future wrapper changes
require renewed render-closure review before updating that digest. On Mach-O,
one C-symbol underscore is normalized for the fixed-size memory-operation
allow-list; no arbitrary runtime helper or prefix is allowed.
