import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { scheduleMetronome, scheduleMidiTone } from "../../lib/audio/scheduler.ts";
import {
  NOW,
  atAudioTime,
  atSampleFrame,
  resolveEventTimeSeconds,
  validateSoundEngineEvent,
} from "../../lib/audio/sound-engine.ts";

class RecordingSoundEngine {
  id = "recording";
  label = "Recording engine";
  events = [];

  async start() {}
  async resume() {}
  async suspend() {}
  stopAll() {}
  async handleRouteChange() {}
  async dispose() {}
  subscribe() { return () => {}; }
  snapshot() {
    return {
      id: this.id,
      label: this.label,
      state: "running",
      ready: true,
      profile: "test",
      activeVoices: 0,
      pedals: { sustain: 0, sostenuto: 0, unaCorda: 0 },
      parameters: {},
      clock: this.clock(),
      routeVersion: 0,
      lastEventType: null,
      lastError: null,
    };
  }
  clock() {
    return {
      sampleRate: 48_000,
      currentTimeSeconds: 2,
      currentSampleFrame: 96_000,
      state: "running",
      baseLatencySeconds: 0.01,
      outputLatencySeconds: 0.02,
    };
  }
  dispatch(events) {
    this.events.push(...(Array.isArray(events) ? events : [events]));
  }
}

test("sound event time supports audio seconds and absolute sample frames", () => {
  const clock = new RecordingSoundEngine().clock();
  assert.equal(resolveEventTimeSeconds(NOW, clock), 2);
  assert.equal(resolveEventTimeSeconds(atAudioTime(3.25), clock), 3.25);
  assert.equal(resolveEventTimeSeconds(atSampleFrame(120_000), clock), 2.5);
});

test("scheduled lesson notes become note-on and note-off events on one engine contract", () => {
  const engine = new RecordingSoundEngine();
  const sourceId = scheduleMidiTone(engine, 60, 4, 0.5, 0.16, "lesson-c4");
  assert.equal(sourceId, "lesson-c4");
  assert.deepEqual(engine.events, [
    {
      type: "note-on",
      sourceId: "lesson-c4",
      note: 60,
      velocity: 0.8,
      gain: 0.16,
      time: { kind: "audio-time", seconds: 4 },
    },
    {
      type: "note-off",
      sourceId: "lesson-c4",
      note: 60,
      releaseVelocity: 0.5,
      time: { kind: "audio-time", seconds: 4.5 },
    },
  ]);
});

test("metronome scheduling uses the same engine boundary", () => {
  const engine = new RecordingSoundEngine();
  scheduleMetronome(engine, 7.5, true);
  assert.deepEqual(engine.events, [{
    type: "metronome",
    accent: true,
    time: { kind: "audio-time", seconds: 7.5 },
  }]);
});

test("the contract accepts note, release, pedal, parameter, and metronome events", () => {
  const events = [
    { type: "note-on", sourceId: "key-c4", note: 60, velocity: 0.7, gain: 1, time: NOW },
    { type: "note-off", sourceId: "key-c4", note: 60, releaseVelocity: 0.4, time: atSampleFrame(1_024) },
    { type: "sustain", position: 0.6, time: NOW },
    { type: "sostenuto", position: 1, time: NOW },
    { type: "una-corda", position: 0.25, time: NOW },
    { type: "parameter", parameterId: "master-gain", value: 0.8, time: NOW },
    { type: "metronome", accent: false, time: NOW },
  ];
  for (const event of events) assert.doesNotThrow(() => validateSoundEngineEvent(event));
});

test("invalid timing and expressive controls are rejected at the boundary", () => {
  assert.throws(() => atSampleFrame(-1), /non-negative safe integer/);
  assert.throws(() => atAudioTime(Number.NaN), /finite non-negative/);
  assert.throws(() => validateSoundEngineEvent({
    type: "note-on",
    sourceId: "",
    note: 128,
    velocity: 1.2,
    time: NOW,
  }), /source id/);
  assert.throws(() => validateSoundEngineEvent({
    type: "sustain",
    position: -0.1,
    time: NOW,
  }), /Pedal position/);
});


test("EngineLab detaches shared refs before awaiting slow cleanup", async () => {
  const source = await readFile("app/lab/engine/EngineLab.tsx", "utf8");

  const stopStart = source.indexOf("  const stopLab = useCallback(async () => {");
  const stopEnd = source.indexOf("\n  const start = useCallback", stopStart);
  const stopBody = source.slice(stopStart, stopEnd);
  const stopAwait = stopBody.indexOf("await Promise.all");

  assert.ok(stopAwait > 0);
  assert.ok(stopBody.indexOf("transportRef.current = null") < stopAwait);
  assert.ok(stopBody.indexOf("setSnapshot(EMPTY_SNAPSHOT)") < stopAwait);
  assert.equal(stopBody.slice(stopAwait).includes("transportRef.current = null"), false);
  assert.equal(stopBody.slice(stopAwait).includes("setSnapshot(EMPTY_SNAPSHOT)"), false);

  const disposeStart = source.indexOf("  const disposeEngine = useCallback(async () => {");
  const disposeEnd = source.indexOf("\n  const activateEngine", disposeStart);
  const disposeBody = source.slice(disposeStart, disposeEnd);
  const disposeAwait = disposeBody.indexOf("await engine.dispose()");

  assert.ok(disposeAwait > 0);
  assert.ok(disposeBody.indexOf("engineRef.current = null") < disposeAwait);
  assert.ok(disposeBody.indexOf("setEngineSnapshot(null)") < disposeAwait);
  assert.equal(disposeBody.slice(disposeAwait).includes("engineRef.current = null"), false);
  assert.equal(disposeBody.slice(disposeAwait).includes("setEngineSnapshot(null)"), false);
});
