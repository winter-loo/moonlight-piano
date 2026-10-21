# Web physical C4 tracer

The engine lab at `/lab/engine` can select **Rust 物理 C4** and compare it with
the accepted Rust basic piano and the legacy Web Audio baselines. The basic
piano remains the production default.

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
  offline host. Its native ABI test calls the exported C interface and requires
  exact PCM and contact-diagnostic equality with the direct core.
- A separate executable conformance test runs the actual production `.wasm`
  against native output at 44.1/48 kHz and 64/128/512-frame blocks. It checks PCM,
  all 15 diagnostics, sample offsets, restrikes and reset, with maximum absolute
  PCM error `2e-6` and relative RMS error `1e-5`. See
  [the measurement guide](c4-hammer-quality.md) for observed results and scope.

## Diagnostics

The developer lab exposes the actual `AudioContext.sampleRate`, current render
block size, latest render-deadline ratio, current WebAssembly memory size,
deadline overruns, and late-event count. WASM fetch/instantiation failures and
AudioWorklet processor failures are reported through `SoundEngineSnapshot.lastError`.
Deadline timing depends on a high-resolution clock being available inside the
worklet. Hosts without that clock currently report zero; that value does not
establish deadline compliance. Native benchmark results and browser audio
correctness are separate checks.

ABI version **5** adds `moonlight_hammer_diagnostics_ptr`. The worklet resolves
this pointer once during initialization. Every ordinary process call updates a
fixed 16-element `f64` buffer; slots 0–14 contain, in order:

1. current and peak contact force (N);
2. current and peak felt compression (m);
3. initial and current hammer velocity (m/s);
4. contact duration (s);
5. hammer, string, total, dissipated and supplied energy (J);
6. maximum absolute cumulative energy-balance residual (J);
7. contact count and contact-active flag.

Slot 15 is reserved and zero. The basic piano reports zero contact diagnostics.
The worklet reads this buffer after rendering and reuses a preallocated telemetry
object at its existing reporting interval, so diagnostics add no per-block
JS/WASM call. The lab shows peak force, compression, initial speed, contact time
and energy accounting for the physical C4 engine.

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

The C4 controls include a continuous velocity slider, seven-step ppp–fff
listening sequence and full MIDI 1–127 sweep. The full sweep has 254 scheduled
note events; its preceding reset also fits the fixed 256-event queue. Starting
or stopping a sweep cancels previously queued events. Live sequences preserve
string history between notes, while the offline measurement sweep starts each
velocity from rest. Note-off does not yet implement a damper in the C4 model;
continuous release and repedal behavior remain issue #8.

## Validate the web path

```sh
npm run build
npx playwright install chromium
npm run test:hammer
npm run test:score-audio
```

`test:hammer` includes native/WASM conformance, a real Chromium AudioWorklet
test at 44.1 and 48 kHz, and a production lab lifecycle test. The worklet test starts audio through a user
gesture, checks nonzero finite output and velocity-dependent contact, then
checks silence and cleared diagnostics after reset. The lab test also verifies
that a full sweep can pause after the eight-beat timing probe completes, resume
without losing sample-frame progress, stop, and switch back to the basic piano.
`test:score-audio` protects
the existing basic piano's standalone practice-player integration. A preinstalled
compatible Chromium can be selected with `PIANO_CHROMIUM_PATH`.
