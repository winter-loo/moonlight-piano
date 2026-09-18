# Web physical C4 tracer

The engine lab can select **Rust 物理 C4** and compare it with the two legacy Web Audio baselines.

## Build

```sh
rustup target add wasm32-unknown-unknown
npm run audio:wasm
npm run dev
```

`npm run audio:wasm` builds `moonlight-wasm` and copies the raw module to
`public/audio/moonlight_wasm.wasm`.

## Realtime boundary

- The AudioWorklet owns the WebAssembly instance.
- Model parsing and Rust engine construction happen once during worklet initialization.
- The normal render path makes exactly one JS/WASM call per render quantum:
  `moonlight_process_block`.
- Events are expressed as absolute sample frames in the application boundary and
  converted to offsets only when their render quantum is reached.
- The worklet render callback uses fixed-capacity typed arrays and performs no JSON
  parsing, model parsing, logging, or array construction.
- The Rust wrapper delegates to the same `PianoEngine::process_block` used by the
  offline host. The wrapper test requires exact `f32` equality for an identical
  C4 note-on block, so the current documented numerical tolerance is **0 ULP** for
  that common-core path.

## Diagnostics

The developer lab exposes the actual `AudioContext.sampleRate`, current render
block size, latest render-deadline ratio, current WebAssembly memory size,
deadline overruns, and late-event count. WASM fetch/instantiation failures and
AudioWorklet processor failures are reported through `SoundEngineSnapshot.lastError`.

`NOW` note events receive a two-quantum scheduling lead so UI/message-port jitter
does not pretend to be sample-accurate. Explicit future sample-frame events retain
their requested absolute frame. Events that arrive after their requested frame are
counted as late and are not silently moved to a different sample.

## A/B scope

The lab registry keeps the physical tracer and both legacy engines side by side.
The descriptor-level `labLevel` calibration is outside the Rust model: changing
A/B listening level therefore cannot alter the physical state or the offline
reference numerics.

This ticket remains deliberately C4-only. Chord controls are disabled while the
physical tracer is selected.
