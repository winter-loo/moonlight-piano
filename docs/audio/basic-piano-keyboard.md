# Analytic basic piano

Listening status: the initial MVP was rejected for dirty sound. The current
candidate repairs specific synthesis artifacts; subjective tone acceptance is
still pending. See [tone-quality regression](basic-piano-tone-quality.md).

Select **Rust 基础全键盘** in `/lab/engine`, after `npm run audio:wasm`.
The A0–C8 button schedules note-on/off at absolute sample frames; the chord
buttons exercise simultaneous notes through the existing SoundEngine and
AudioWorklet. The previous physical C4 tracer remains selectable unchanged.
The home screen keyboard and B1-01 listening/echo lesson expose a basic-piano
choice through the same SoundEngine contract. They wait for WASM readiness
before the first note and return visibly to the legacy sound if startup fails.

The standalone `docs/practiced-songs/bicycle-built-for-two-grand-staff.html`
also defaults to **Rust 基础钢琴**, for both-hand playback and clicked-note previews.
`npm run audio:wasm` builds the WASM and the shared browser host modules;
`npm run audio:browser` refreshes only the host modules after TypeScript changes.
Serve the repository root, for example with `python3 -m http.server 8000`, then
open `http://localhost:8000/docs/practiced-songs/bicycle-built-for-two-grand-staff.html`.
AudioWorklet requires localhost or HTTPS. Opening the HTML as a standalone
`file://` document is not a supported Rust playback path. Missing assets produce
an explicit error; the other sound choices remain available for manual selection.
The reverb slider belongs to those older sounds and is disabled for the Rust
engine. Stop, pause, reset and timbre switching cancel queued notes and pending
startup. The Python generator uses the repository font and preserves the wiring.

This is an **analytic/empirical model**, not measured piano calibration.
At initialization, Rust generates MIDI 21–108 fundamentals from equal
temperament at A4=440 Hz, rigid-string partials with a simple register-dependent
inharmonicity prior, register-dependent decays and at most 12 valid partials per
key. Partials beyond 0.98 Nyquist are omitted. Velocity varies the excitation
spectrum continuously. Each note retains one persistent modal state; repeating
that note injects more energy into that state. Release applies a simple damping
envelope without detuning the oscillator. Modal kicks are normalized for
frequency and sample rate. The master is linear below 0.9 full scale; overload
protection above that level keeps extreme/repeated chords within output range.
No audio samples enter the runtime.

The current capacity is **32 sounding key states**, not 32 strings or 32
independent same-pitch instances. A new note first reuses a released tail;
otherwise it replaces the oldest held key. The Worklet tracks up to **256 held
source IDs** at their scheduled sample frames, so overlapping scheduled or live
sources share a key until the final source releases it. Duplicate source onsets
and unmatched releases are ignored. At the source limit, new onsets are dropped
and counted as overflows; accepted holds remain releasable. When the
Worklet event queue overflows, new note-ons are dropped; a release forces a
safe reset rather than leaving an indefinitely held note. Queue overflows are
counted separately from late events. Stop-all clears queued future events.
Late absolute note-ons expire; late `NOW` inputs play at the next render block
so context resume or message latency cannot silently discard the first key.

The two output channels use a simple key-position pan and two persistent,
shared body modes. This is basic coloration rather than identified soundboard
coupling or measured stereo radiation. The sustain damper uses a binary threshold at 0.5 and can
recapture a live tail without resetting its phase. Half-pedal, sostenuto,
una corda, bidirectional soundboard coupling, and radiation modeling remain forthcoming. The
engine rejects unsupported controls explicitly. The lab disables them for
the corresponding physical engine.

## Checks

```sh
cargo test --workspace
sh scripts/check-realtime-boundary.sh
npm run audio:wasm
node --experimental-strip-types --test tests/unit/basic-piano-worklet.test.mjs tests/unit/basic-piano-source-ownership.test.mjs
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
