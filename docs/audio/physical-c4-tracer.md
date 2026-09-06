# Deterministic physical C4 tracer

This tracer is the first audible path through the intended final architecture:

```text
timestamped event -> validated model pack -> Rust DSP state -> offline host
                  -> PCM WAV + deterministic metrics + energy/timing reports
```

It is deliberately narrow, but it is not a throwaway JavaScript synthesizer. The
same `moonlight-dsp` state and event types are exported by the WASM and native FFI
boundaries for later hosts.

## Render

```bash
scripts/render-physical-c4.sh
```

The repository pins Rust 1.82.0 so local and CI builds use the same compiler. The command accepts an optional output directory. Environment variables can
override `SAMPLE_RATE`, `BLOCK_SIZE`, `DURATION_SECONDS`, and `SEED`.

The output contains:

- `c4-reference.wav`: mono 16-bit PCM generated from damped modal state;
- `c4-report.json`: deterministic peak, RMS, frame count, and PCM checksum;
- `c4-energy.csv`: 100 ms RMS/energy-decay windows;
- `c4-timing.json`: wall-clock render time and realtime ratio.

The timing file is intentionally excluded from byte-for-byte reproducibility
checks. The WAV, deterministic report, and energy CSV must be identical for the
same target, inputs, and seed.

## Model boundary

`fixtures/physical-c4/minimal-c4.mlpiano` contains only modal frequencies,
60 dB decay times, amplitudes, note identity, and output gain. Unknown fields are
rejected, so a `sample=` or waveform path cannot silently enter the runtime model.
The validator rejects non-finite values, invalid decay, unstable poles, and modes
outside the guarded Nyquist bandwidth.

## Scope

This ticket proves persistent passive string state and sample-accurate event
application. It does not pretend to complete the piano:

- nonlinear hammer contact belongs to ticket #7;
- damper/repedal behavior belongs to ticket #8;
- multiple keys, unisons, soundboard, pedals, and radiation retain their later
  tickets and must extend this same core rather than introduce another engine.
