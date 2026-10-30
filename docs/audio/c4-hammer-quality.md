# C4 nonlinear hammer: measurements and listening

This is the next physical-engine milestone after the accepted basic piano in
[PR #46](https://github.com/winter-loo/moonlight-piano/pull/46), implementing the
continuous C4 hammer work in [issue #7](https://github.com/winter-loo/moonlight-piano/issues/7).
The accepted `BasicPianoEngine` remains the production default. The experimental
`physical-c4` engine in `/lab/engine` now drives persistent string modes with a
moving hammer and nonlinear felt contact instead of an instantaneous scaled
impulse. It is an **uncalibrated single-C4 candidate**, with listening acceptance
pending. It is not a complete or professionally certified piano.

## What the evidence establishes

The contact tests exercise nonnegative force, separation, mechanical energy,
extreme inputs, repeated strikes, event timing, deterministic state and velocity
response. The offline measurement path calls the same `PianoEngine` that the
WASM host uses. It does not implement a second renderer or read any recordings.

The measurement sweep starts each of the 127 MIDI velocities from silence and
holds C4 for 0.5 seconds. It runs at both 44.1 and 48 kHz. The first velocity
curve revealed a 25.31 dB change between MIDI velocities 1 and 2, even though it
was mathematically continuous. That was a useful failure: continuous equations
alone did not provide a usable soft dynamic range. The revised, continuously
differentiable input curve interpolates geometrically from 0.12 m/s at MIDI
velocity 1 to 5 m/s at velocity 127, with a smooth extension to zero. It changes the
hammer's initial motion; it does not compensate the output with a velocity EQ
or a per-note gain.

Current candidate measurements are:

| Measurement | 44.1 kHz | 48 kHz |
| --- | ---: | ---: |
| RMS increases at every MIDI velocity | Yes | Yes |
| RMS span, MIDI 1–127 | 37.4005 dB | 37.4005 dB |
| Largest adjacent MIDI RMS change | 0.441621 dB | 0.441621 dB |
| Largest adjacent centroid change | 0.630284% | 0.630385% |
| Spectral centroid at MIDI 1 | 270.99 Hz | 270.99 Hz |
| Spectral centroid at MIDI 127 | 487.94 Hz | 487.95 Hz |
| Best scalar-fit residual, MIDI 24 versus 104 | 0.949022 | 0.949022 |
| Maximum absolute single-note PCM sample | 0.076790 | 0.076767 |

The scalar-fit residual is `RMS(strong − g × weak) / RMS(strong)`, where `g`
minimizes squared error over the same 0.5-second window, even allowing a polarity
change. Its nonzero result,
together with different partial-energy distributions, demonstrates that strong
and weak notes are not one fixed waveform multiplied by different gains. It is
not a distortion metric and it is not a measure of piano realism.

The report rejects silence, nonfinite PCM, non-increasing level, single-C4
clipping, missing contact force, an unchanged weak/strong waveform, and a loud
spectrum that is no brighter than the soft spectrum. It also enforces the
specification's 0.5 dB adjacent-velocity level and 3% adjacent-centroid bounds
against this synthetic sweep. Passing those numeric bounds does not establish
real-piano calibration or perceptual uniformity on every controller.

### Exact feature definitions

- **RMS / dBFS:** signal RMS over the entire 0.5-second note. This is signal level,
  not LUFS or psychoacoustic loudness.
- **Spectral centroid:** magnitude-weighted FFT-bin frequency using a Hann window
  over 20–400 ms, with a 65,536-point FFT.
- **Partial energy:** squared spectrum integrated within ±8 Hz of each configured
  modal frequency below Nyquist, normalized by the sum of those bands.
- **Attack:** the first 10–90% rise of a 1 ms causal RMS envelope relative to its
  maximum in the first 50 ms. This acoustic measure is distinct from physical
  hammer contact time, which is reported independently.
- **Decay excitation:** late (300–500 ms) versus early (30–130 ms) RMS and the
  partial-energy distribution. A half-second sweep cannot certify multi-stage
  T60 decay or a measured real-piano envelope.

These windows and definitions stay fixed across velocities. Full per-velocity
features, contact duration, force, compression and energy diagnostics are in the
generated JSON and CSV, along with tool versions, source/renderer/model hashes
and exact PCM hashes.

## Numerical reference and WASM conformance

Two different checks are deliberately kept separate:

1. `tests/browser/physical-hammer-parity.test.mjs` runs the actual production
   `.wasm` in Node's WebAssembly runtime. Native and WASM render identical events
   at 44.1/48 kHz with 64/128/512-frame blocks, including sample offsets, a
   restrike during contact, releases and exact-frame resets. It compares PCM and
   all 15 contact diagnostics. PCM tolerances are maximum absolute error
   `2e-6` and relative RMS error `1e-5`; observed PCM error is zero on the current
   validation machine. It also checks that native output is independent of
   block partitioning and that WASM memory does not grow while rendering. This
   validates the shared executable path, independently of browser UI routing.
2. A strong isolated C4 strike is rendered at 176.4 and 192 kHz. A Kaiser-window
   lowpass (`scipy.signal.resample_poly`, beta 8.6) precedes downsampling to
   44.1/48 kHz. End-of-sample timestamps are aligned by including the exact rest
   state at time zero. The direct render is compared over 0–400 ms, avoiding the
   final resampling boundary. Relative RMS waveform differences are about
   `1.23e-4` and `1.03e-4`; the first 20 ms differ by about `1.49e-4` and
   `1.26e-4`. Contact-time differences are approximately 0.0014 ms and zero.

The higher-rate comparison measures combined integration and output-sampling
convergence for one strong C4 strike. It does **not** prove alias-free output,
inaudibility of every difference, or accuracy over every parameter setting. The
current output samples the internal modal state; no general nonlinear
anti-aliasing certification is claimed. The source model itself is synthetic.
Native/WASM agreement cannot establish that its physics matches a real piano.

## Performance status: absolute gate not passed

The existing scalar C4 benchmark ran the eight 44.1/48 kHz ×
64/128/256/512-frame cases on 2026-10-21 in a shared AMD EPYC 9V74 Linux
container, using Rust 1.82.0. Each case contains 256 warmup blocks and 2,048
measured render calls. The first candidate run recorded **five deadline misses**.
A single follow-up diagnostic pinned both binaries to CPU 0 and ran the baseline
then candidate sequentially while local build work was paused. The paired
baseline passed the absolute smoke budget, but the candidate recorded **three
deadline misses**. Both candidate runs failed `check-realtime-report.py
--enforce-budget`. These failures are retained in the
[immutable local evidence bundle](evidence/c4-hammer-performance/README.md).

The table reports render time divided by block duration, `R`, not CPU percent.
With only 2,048 observations, p99.99 equals the observed maximum; it is an
under-resolved tail, not a confidence guarantee.

| Rate / frames | Initial candidate p50 | Initial p99 | Initial p99.99 | Initial misses | Paired candidate p50 | Paired p99 | Paired p99.99 | Paired misses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 44100 / 64 | 0.006563 | 0.114192 | 2.198315 | 1 | 0.007702 | 0.110203 | 0.302570 | 0 |
| 44100 / 128 | 0.006553 | 0.112819 | 2.932719 | 4 | 0.007743 | 0.101480 | 0.151516 | 0 |
| 44100 / 256 | 0.008659 | 0.058188 | 0.260598 | 0 | 0.007658 | 0.059808 | 0.250291 | 0 |
| 44100 / 512 | 0.007709 | 0.032248 | 0.220824 | 0 | 0.007740 | 0.035905 | 0.359729 | 0 |
| 48000 / 64 | 0.007136 | 0.133846 | 0.411137 | 0 | 0.008458 | 0.149762 | 3.049022 | 3 |
| 48000 / 128 | 0.008428 | 0.114792 | 0.155204 | 0 | 0.008375 | 0.103001 | 0.132838 | 0 |
| 48000 / 256 | 0.008430 | 0.062969 | 0.102238 | 0 | 0.008424 | 0.060455 | 0.300438 | 0 |
| 48000 / 512 | 0.008099 | 0.036899 | 0.148316 | 0 | 0.008431 | 0.052989 | 0.401550 | 0 |

Candidate medians in the paired run occupy about 0.766%–0.846% of the deadline;
p99 occupies about 3.59%–14.98%. Relative to that run's impulse-tracer baseline,
median cost increased approximately **15.6–20.3 times**. The added cost buys the
coupled hammer/string solve, four internal substeps and mechanical diagnostics;
the measured acoustic benefit is the continuous contact/velocity response
described above. That benefit does not waive the absolute deadline contract.

| Size measurement | Impulse baseline | Hammer candidate | Change |
| --- | ---: | ---: | ---: |
| Fixed engine state | 680 B | 1,648 B | +968 B (+142.35%) |
| Native benchmark executable | 611,512 B | 615,784 B | +4,272 B (+0.70%) |
| Model pack | 380 B | 380 B | Unchanged |

The executable figure is for the native benchmark, not the Web WASM download.
Output and timing-observation buffer sizes are unchanged. These smoke reports
are informational local comparisons; the benchmark policy does not treat them
as equivalent dedicated-device baselines.

The outlier cases moved between runs. Scheduling interference is possible, but
there is no per-callback CPU-time or scheduler trace proving that explanation.
The paired candidate recorded 18 involuntary process context switches and no
increase in cgroup throttled time. It remains incorrect to attribute every miss
to the host or to claim a passed performance gate. Hosted CI's schema/finite-data
checks are separate from `--enforce-budget`. Dedicated-device callback timing,
Web/device performance and thermal certification remain outstanding.

## Reproduce

```sh
cargo test -p moonlight-dsp --test hammer_contact
cargo test -p moonlight-dsp --test realtime_contract
python3 -m pip install -r tools/acoustics/requirements.txt
python3 scripts/render-hammer-review.py
npm run audio:wasm
node --test tests/browser/physical-hammer-parity.test.mjs
```

The report is written under `work/c4-hammer-review/`. `--rate 48000` selects one
rate, and `--output PATH` writes to another directory. The `--skip-render`
option re-analyzes existing raw files after checking their render manifest
against the current Rust/model/example sources and executable. A full run also
rejects source or binary changes during measurement. Reports record whether the working tree is dirty,
so a commit identifier alone is never presented as the identity of an uncommitted
candidate.

The `hammer_sweep` example additionally supports:

```sh
cargo run --release -p moonlight-dsp --example hammer_sweep -- \
  --parity work/c4-parity/native.f32le 48000 128
cargo run --release -p moonlight-dsp --example hammer_sweep -- \
  --reference work/c4-reference/strong.f32le 192000
```

## Listen

Each sample-rate folder contains:

| File | Contents |
| --- | --- |
| `c4-hammer-rms-matched-ab.wav` | Basic at 0–16 s, silence at 16–17 s, hammer candidate at 17–33 s; one RMS-matching gain for each entire segment |
| `c4-hammer-raw-comparison.wav` | The same order, with one common gain for both engines |
| `c4-hammer-candidate.wav` | Candidate alone, using the same constant comparison gain |
| `basic-raw-float.wav`, `hammer-raw-float.wav` | Unnormalized float output for inspection |
| `listen.events.csv` | The exact sample-frame event sequence |

Both engines play C4 at MIDI velocities 8, 24, 40, 56, 72, 88, 104 and 127. Each
single note is held until the next reset, so the different release implementations
do not obscure that part of the comparison. Three release/repeat probes follow
at 13, 13⅓ and 13⅔ seconds within each segment. Their differences include the
current release limitations. Basic stereo output is averaged to mono to compare
with the C4 path. There is no EQ, denoising, limiter, resampling or per-note
normalization in the listening export.

The separation between single-note probes is an exact DSP reset. It can cut a
still-sounding tail abruptly; this is an intentional test separator, not the
finished key-release behavior. Judge the contact/attack and held tone separately
from that boundary. Continuous, click-free damper release remains issue #8.

The two engines also differ in string/voice topology. This is an A/B against the
existing MVP, not an isolated causal measurement of the hammer alone. Listening
acceptance should evaluate dynamics and attack, while recognizing that continuous
damper trajectories, calibrated full-keyboard models, shared bridge/soundboard
coupling and professional instrument calibration are later issues.
