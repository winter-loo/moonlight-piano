import assert from "node:assert/strict";
import test from "node:test";

import { evaluateRhythmAttempt } from "../../lib/engine/rhythm-evaluator.ts";
import { mariageAmourContent } from "../../lib/music/content/mariage-amour.ts";
import { spellingToMidi } from "../../lib/music/pitch.ts";
import { beatsToSeconds, tempoPercentToBpm } from "../../lib/music/tempo.ts";

test("calibrated measures 6-7 contain 16 valid events", () => {
  assert.equal(mariageAmourContent.events.length, 16);
  assert.equal(mariageAmourContent.exercises.length, 2);
  assert.equal(mariageAmourContent.events.filter((event) => event.hand === "right").length, 10);
  assert.equal(mariageAmourContent.events.filter((event) => event.hand === "left").length, 6);
});

test("the first listening challenge is a playable piano echo exercise", () => {
  const exercise = mariageAmourContent.exercises.find((item) => item.id === "B1-01");
  assert.equal(exercise?.inputPolicy, "pitch");
  assert.ok(exercise?.visibleLayers.includes("keyboard"));
  assert.equal(exercise?.passCriteria.pitchAccuracy, 1);
});

test("pitch spelling preserves flats while mapping to MIDI", () => {
  assert.equal(spellingToMidi("Bb4"), 70);
  assert.equal(spellingToMidi("G2"), 43);
  assert.equal(spellingToMidi("D5"), 74);
});

test("course tempo conversions match the agreed ladder", () => {
  assert.equal(tempoPercentToBpm(150, 40), 60);
  assert.equal(tempoPercentToBpm(150, 50), 75);
  assert.equal(beatsToSeconds(6, 60), 6);
});

test("perfect rhythm earns full accuracy", () => {
  const targets = [0, 1, 1.5, 2, 2.5].map((beat, index) => ({ id: `t${index}`, beat, durationBeats: index === 0 ? 1 : 0.5 }));
  const taps = targets.map((target, index) => ({ id: `a${index}`, beat: target.beat }));
  const result = evaluateRhythmAttempt(targets, taps);
  assert.equal(result.accuracy, 1);
  assert.equal(result.misses.length, 0);
  assert.equal(result.extras.length, 0);
  assert.ok(result.matches.every((match) => match.timing === "on-time"));
});

test("duplicate and late taps are diagnosed", () => {
  const targets = [{ id: "t1", beat: 1, durationBeats: 1 }];
  const taps = [{ id: "a1", beat: 1.2 }, { id: "a2", beat: 1.22 }];
  const result = evaluateRhythmAttempt(targets, taps);
  assert.equal(result.accuracy, 0.5);
  assert.equal(result.matches[0].timing, "late");
  assert.deepEqual(result.extras, ["a2"]);
});
