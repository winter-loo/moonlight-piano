# Analytic keyboard tracer (first basic-piano slice)

Select **Rust 基础全键盘** in `/lab/engine`, after `npm run audio:wasm`.
The A0–C8 button schedules note-on/off at absolute sample frames; the chord
buttons exercise simultaneous notes through the existing SoundEngine and
AudioWorklet. The previous physical C4 tracer remains selectable unchanged.

This is an **analytic/empirical model**, not measured piano calibration.
At initialization, Rust generates MIDI 21–108 fundamentals from equal
temperament at A4=440 Hz, rigid-string partials with a simple register-dependent
inharmonicity prior, register-dependent decays and at most 12 valid partials per
key. Partials beyond 0.98 Nyquist are omitted. Velocity varies the excitation
spectrum continuously. Each note retains one persistent modal state; repeating
that note injects more energy into that state. Release applies a simple damping
envelope. A bounded master response keeps large chords within output range.
No audio samples enter the runtime.

The current capacity is **32 sounding key states**, not 32 strings or 32
independent same-pitch instances. A new note first reuses a released tail;
otherwise it replaces the oldest held key. The browser tracks source IDs so
one source releasing a shared key does not release the other source. When the
Worklet event queue overflows, new note-ons are dropped; a release forces a
safe reset rather than leaving an indefinitely held note. Queue overflows are
counted separately from late events. Stop-all clears queued future events.

This slice is mono. Sustain, half-pedal, sostenuto, una corda, shared soundboard,
stereo radiation, and production lesson integration remain forthcoming. The
engine rejects unsupported pedal controls explicitly. The lab disables them
for physical engines.

## Checks

```sh
cargo test --workspace
sh scripts/check-realtime-boundary.sh
npm run audio:wasm
node --test tests/unit/basic-piano-worklet.test.mjs
npx tsc -p tsconfig.audio-worklet.json --noEmit
cargo run --release -p moonlight-dsp --example basic_smoke -- 2048
```

The source policy now scans the analytic path, and the allocation observer
exercises a 32-key render and release. The compiled no_std object audit remains
scoped to the older C4 renderer; the analytic renderer still needs its own
compiled-object audit and dedicated-device performance baseline before a
real-time certification claim. The example is a shared-host smoke measurement,
not a release gate. It reports the actual 32-key load and deadline misses;
2048 observations cannot resolve p99.99 reliably.
