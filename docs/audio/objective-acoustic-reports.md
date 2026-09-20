# Objective acoustic reports (#20)

Built on the licensed acoustic-data registry now present in `main`.
These tools inspect legal development evidence. They never load sealed final
holdouts, fit the product automatically, or execute in the audio callback.

## Integration status

This PR lands the reusable objective-analysis foundation and one registered real
C4 development case. It does **not** complete Issue #20: representative real
bass, treble, controlled velocity/pedal, and synchronized microphone cases are
still required before that issue can close. Synthetic fixtures validate
estimators; they are not substitutes for the missing real-reference matrix.

## Reproduce the estimator validation

```sh
python3 -m pip install -r tools/acoustics/requirements.txt
python3 -m unittest discover -s tests/acoustics -v
python3 -m tools.acoustics.fixtures
python3 -m tools.acoustics.cli \
  --manifest work/acoustic-analysis/fixtures/job.json \
  --output work/acoustic-analysis/synthetic --rendered-rate 48000
```

The generator creates 12 known **synthetic estimator fixtures**, not a cheap
piano engine or a substitute for recordings: bass, middle, treble, soft/strong,
pedal-up/down decay, a synchronized microphone gain/delay pair, unstruck-target
band energy with a baseline, and a source-native 96 kHz treble case. Generation
uses a fixed seed and PCM24 WAV without timestamped floating-point PEAK chunks.
The fixture code and dependency versions establish the scope of reproducibility.

Repeat with `--rendered-rate 96000` to inspect the high-rate source's extra
partials. This does not upsample a lower-rate file. A 48 kHz input still has a
24 kHz Nyquist limit even when a larger rendered rate is requested.

## Analyze an actual registered reference

```sh
node scripts/prepare-acoustic-analysis.mjs \
  --case salamander-c4-reference \
  --output work/acoustic-analysis/reference-job.json
python3 -m tools.acoustics.cli \
  --manifest work/acoustic-analysis/reference-job.json \
  --output work/acoustic-analysis/reference-c4
```

The Node preparation seam calls the existing registry/policy validator, requires
an inspectable split and explicit commercial/fitting permission, rejects unsafe
paths and symlinks, verifies the registered audio **and license evidence** by
byte count, Git blob SHA-1 and SHA-256, and writes a job containing provenance.
Downloads are bounded by registered byte counts and a timeout. Cached data are
revalidated. Source audio stays under ignored `work/acoustic-data/raw/`.

The Python report seam rechecks original recording bytes before decoding them
from memory. Decoded observations are bounded to 16 million scalar values
(128 MB for the initial float64 decode, before analysis scratch buffers). Metadata/job hashes, tool source hash, tool and dependency versions,
parameters, source provenance, recording hash and exact invocation are recorded.
This is an integrity chain, not a substitute for license review or filesystem
access control. The private holdout's custodian must enforce access separately.

`data/acoustic/analysis-cases.json` is the curated selector for known note,
velocity, pedal and microphone conditions. Do not invent those labels by
passing a desired sound into the analyzer. The currently registered C4 MP3 has
unknown exact velocity, release timestamp, pedal trajectory and microphone
placement. Null values are intentional. Additional real bass/treble, controlled
pedal and synchronized multi-position cases must be registered with evidence
before claiming the real-recording matrix is complete.

## What is measured

- Fundamental and partial frequency tracks: windowed FFT peaks with local
  log-parabolic interpolation. MIDI note is a search prior, not measured pitch.
- Equivalent stiff-string inharmonicity: regression of `(f_n/n)^2` against
  `n^2`, with fit residual information. Not a unique length/tension inference.
- Attack: 5 ms RMS-envelope onset and 10–90% rise, with time resolution reported.
- Early/late decay: a separate envelope spanning at least three fundamental
  periods (minimum 25 ms), with the derived resolution recorded; declared fixed segments and amplitude-dB linear fits,
  slope standard error and R-squared. T60 is extrapolated only for a sufficiently
  linear negative slope; a poor or short fit returns unavailable.
- Levels: RMS and peak dBFS. **Not** BS.1770 integrated LUFS or acoustic SPL.
- Spectral centroid: power-weighted within the common guarded bandwidth.
- Beating: a periodic narrowband-envelope **candidate**, not proof of unison
  strings. Room reflections and amplitude modulation are confounders.
- Release: separately fitted only when a real note-off timestamp is supplied.
- Noise: observed pre-onset recording floor only, not isolated hammer mechanics.

The common partial ceiling is `0.98 * min(source_rate, rendered_rate) / 2`.
Zero-padding interpolates spectral peaks but adds neither observation duration
nor physical bandwidth. Near-floor or missing partials are not filled in.

## Paired measurements

A pedal comparison requires matched known instrument, note, velocity and mic,
and explicitly different pedal states. It reports state-specific decay and
level differences, never labels them room reverb.

A microphone comparison reports gain; phase, delay, correlation and cross-spectral
transfer additionally require the same declared synchronized take. A periodic
lag ambiguity is exposed. The measured transfer combines piano, room, microphones
and recording chain; it is not an identified soundboard radiation operator.

An unstruck-target comparison requires an explicit not-struck declaration and
observation interval. Band energy with a controlled baseline is reported, with
the warning that overlapping partials can contaminate the band. It does not
infer performer intent from a waveform.

## Validation and limits

Known signals test pitch tolerance (0.3 Hz), B-fit tolerance (2e-5), exponential
T60, release decay, modulation candidates, source/native bandwidth, anti-phase
stereo, finite-input rejection, 1 ms microphone delay and -6.02 dB gain, pedal
contrasts, byte tampering, final-holdout rejection, deterministic fixture
regeneration, and JSON/Markdown output. These are estimator tests, not a
statistical demonstration of accuracy on every real piano.

## Recorded local verification

On 2026-09-18 the owner tested the unchanged commit
`e4a2759239d5b0661dff25d515686c482ef0992c` on macOS with Python 3.13.7,
NumPy 2.3.5, SciPy 1.17.0, SoundFile 0.13.1 and Node 25.8.1. All 14 acoustic
and 13 then-current registry tests passed. The real registered C4 was downloaded,
checksummed together with its license evidence, decoded and analyzed into JSON
and Markdown. Evidence ZIP SHA-256:
`6e1a69ac1ad993fd6114bbc3a5a1f63c29384c10a0534a37002391174cdf4804`.

That closes the previously unexecuted local C4 end-to-end gate, not the entire
ticket. The measured file still has unknown velocity, pedal, release and
microphone metadata. Both T60 estimates remained unavailable at the chosen
fit-quality threshold; the report does not invent decay constants to fill gaps.
Original report JSON SHA-256:
`b9ff56a83e6670fa2b325c82bb74a22b0717146d86e35228f69ce161bb12b018`.

The analysis and registry workflows are read-only with respect to tracked
source, record the actual checked-out revision, and keep raw audio outside Git.
Historical local measurements above remain provenance for that exact historical
commit; hosted CI on the rebased implementation is the authoritative current
integration gate.

Remaining before full Issue #20 acceptance: sufficiently documented real examples
for the bass/treble/velocity/pedal/microphone matrix. Integrated perceptual
loudness, confidence calibration on real recordings and source-specific
estimator error characterization remain explicit limitations, not fabricated
measurements.

Review the machine-readable JSON for full tracks and uncertainty; Markdown is
an inspection summary. Report generation uses strict JSON (no NaN or Infinity).
Do not commit generated raw audio or load reports into the runtime model pack.
