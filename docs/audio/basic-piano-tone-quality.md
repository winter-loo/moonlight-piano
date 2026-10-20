# Basic piano: dirty-tone regression

The user rejected the initial MVP's sound on 2026-10-20. Functional, finite-output
and browser tests did not establish acceptable tone. This patch is a candidate
repair of specific artifacts, with listening acceptance still pending.

## Three identified defects

1. **Modal excitation gain depended on frequency and sample rate.** For
   `y[n] = 2r cos(w)y[n-1] - r²y[n-2]`, adding amplitude A directly to the current
   state with a zero previous state produces amplitude proportional to
   `A / sin(w)`. Bass modes were heavily amplified and drove the output shaping.
   The candidate injects `-A sin(w) / r` into the previous state, producing a
   damped sinusoid with the intended amplitude. Initialization compiles this
   factor; the audio loop adds no transcendental calculations.
2. **Release damping changed pitch.** Multiplying only the new state by d
   changes the pole angle to `acos(sqrt(d) cos(w))`. Scaling both saved states
   multiplies the state-transition matrix by d, changing pole radius while
   preserving angle. The existing 0.25 s release factor now has that meaning.
3. **The master shaped every note and chord.** The previous rational response
   added nonlinear harmonics and intermodulation even at ordinary levels.
   The candidate uses a linear master gain of 0.3 below 0.9 full scale. A
   continuous overload curve operates only above 0.9. It remains nonlinear
   during extreme overload; this is not a transparent 32-note loudness promise.

## Measured comparison

Baseline DSP: `fdcb790`. Candidate DSP source SHA-256:
`1d520b0ed200361c6f30d0dee19fca8bbf8df4d462e17c13838221d172e89fc7`.
Both rendered at 48 kHz with note-off at 1 s. Peak-frequency search uses a Hann
window over 1.005–1.125 s and zero-padded FFT interpolation; these estimates
show large detuning, rather than certifying cent-level tuning.

| Note | Held peak, old (Hz) | Released peak, old (Hz) | Released peak, candidate (Hz) |
| --- | ---: | ---: | ---: |
| A1 | 55.02 | 191.44 | 55.02 |
| A2 | 110.05 | 213.78 | 109.95 |
| C4 | 261.66 | 319.43 | 261.66 |
| A4 | 440.00 | 476.62 | 440.00 |
| C6 | 1046.63 | 1062.47 | 1046.63 |

For a normal C4/E4 chord at velocity 0.8, the relative RMS difference between
the combined render and the sum of the individual renders decreased from
0.5344 to 0.000113 in exported 16-bit PCM. This is a superposition error measure,
not THD. The remaining exported-file floor includes quantization. The Rust
full-precision regression requires a ratio below 0.000001.

The three quality regressions fail against the baseline and pass against the
candidate at 44.1/48 kHz where applicable. An additional repeated 32-key test
checks finite output within full scale. Existing allocation and timing tests
remain separate gates.

## Reproduce and listen

```sh
cargo test -p moonlight-dsp --test basic_tone_quality
python3 -m pip install -r tools/acoustics/requirements.txt
python3 scripts/render-basic-tone-review.py
```

The offline-only `basic_render` example accepts an ordered frame-based CSV
(`frame,on|off|sustain|reset,note,value`) and writes stereo PCM. To compare an
older DSP, build that example against the baseline core in a separate checkout
and pass its executable to:

```sh
python3 scripts/render-basic-tone-review.py \
  --baseline-renderer /path/to/baseline/basic_render \
  --baseline-revision fdcb790
```

The script obtains the song excerpt from the existing score generator. Each
16.5 s segment contains bass, middle-register and chord probes, followed by a
Bicycle excerpt. In `basic-piano-tone-ab.wav`, baseline is at 0–16.5 s and the
candidate at 18–34.5 s. One constant gain per segment matches RMS; this is not
LUFS matching. No EQ, denoising or resampling is applied. Original unnormalized
renders and source/renderer/event hashes are retained in `tone-review.json`.

These are artifact repairs, not measured piano calibration or proof of pleasant,
realistic tone. A real browser, target-device performance and subjective listening
remain independent acceptance requirements.
