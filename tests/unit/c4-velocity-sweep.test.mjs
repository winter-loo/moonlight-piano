import assert from "node:assert/strict";
import test from "node:test";
import { createC4VelocitySweep } from "../../lib/audio/c4-velocity-sweep.ts";
import { validateSoundEngineEvent } from "../../lib/audio/sound-engine.ts";

for (const sampleRate of [44_100, 48_000]) {
  test(`full C4 sweep fits the queue and spans every MIDI velocity at ${sampleRate} Hz`, () => {
    const currentSampleFrame = 12_800;
    const sweep = createC4VelocitySweep({ sampleRate, currentSampleFrame }, "full");
    assert.equal(sweep.events.length, 254);
    assert.ok(sweep.events.length + 1 <= 256, "reset must fit alongside the sweep");
    assert.ok(sweep.startFrame >= currentSampleFrame + 384);
    assert.equal(sweep.endFrame - sweep.startFrame, Math.round(sampleRate * 0.25) * 127);
    let previous = currentSampleFrame;
    for (const [index, event] of sweep.events.entries()) {
      validateSoundEngineEvent(event);
      assert.equal(event.time.kind, "sample-frame");
      assert.ok(event.time.frame > previous);
      previous = event.time.frame;
      if (index % 2 === 0) {
        assert.equal(event.type, "note-on");
        assert.equal(Math.round(event.velocity * 127), index / 2 + 1);
        assert.equal(event.note, 60);
        assert.equal(event.sourceId, sweep.events[index + 1].sourceId);
      } else assert.equal(event.type, "note-off");
    }
  });
}

test("listening sweep gives each dynamic 1.5 seconds and includes the strongest strike", () => {
  const sweep = createC4VelocitySweep({ sampleRate: 48_000, currentSampleFrame: 0 }, "listening");
  assert.equal(sweep.velocities.length, 7);
  assert.equal(sweep.velocities.at(-1), 1);
  assert.equal(sweep.stepFrames, 72_000);
});

test("an unavailable or invalid audio clock cannot schedule a sweep", () => {
  for (const sampleRate of [0, -1, NaN, Infinity]) {
    assert.throws(() => createC4VelocitySweep({ sampleRate, currentSampleFrame: 0 }, "full"));
  }
  assert.throws(() => createC4VelocitySweep({ sampleRate: 48_000, currentSampleFrame: Number.MAX_SAFE_INTEGER }, "full"));
});
