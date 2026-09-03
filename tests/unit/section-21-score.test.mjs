import assert from "node:assert/strict";
import test from "node:test";

import {
  duolingoSectionTwentyOneEvents,
  duolingoSectionTwentyOneMeasureCount,
} from "../../lib/music/content/duolingo-section-21.ts";
import { layoutSectionTwentyOneScore } from "../../lib/music/section-21-score-layout.ts";

const notes = duolingoSectionTwentyOneEvents.filter((event) => event.kind === "note");
const rests = duolingoSectionTwentyOneEvents.filter((event) => event.kind === "rest");

test("product document section 21.3 is transcribed as 34 complete 3/4 measures", () => {
  assert.equal(duolingoSectionTwentyOneMeasureCount, 34);
  for (let measure = 1; measure <= 34; measure += 1) {
    const beats = duolingoSectionTwentyOneEvents
      .filter((event) => event.measure === measure)
      .reduce((total, event) => total + event.durationBeats, 0);
    assert.equal(beats, 3, `measure ${measure}`);
  }
});

test("section 21.3 note, rest, duration, and pitch totals match the document", () => {
  assert.equal(notes.length, 75);
  assert.equal(rests.length, 10);
  assert.deepEqual(
    Object.fromEntries([0.5, 1, 1.5, 2].map((duration) => [duration, notes.filter((note) => note.durationBeats === duration).length])),
    { "0.5": 14, "1": 30, "1.5": 14, "2": 17 },
  );
  assert.deepEqual(
    Object.fromEntries(["C4", "D4", "E4", "F4", "G4", "A4", "B4"].map((pitch) => [pitch, notes.filter((note) => note.spelling === pitch).length])),
    { C4: 6, D4: 20, E4: 18, F4: 11, G4: 8, A4: 8, B4: 4 },
  );
});

test("musical measure 21 preserves G quarter, A dotted-quarter, B eighth", () => {
  assert.deepEqual(
    duolingoSectionTwentyOneEvents
      .filter((event) => event.measure === 21)
      .map((event) => [event.kind === "note" ? event.spelling : "rest", event.beat, event.durationBeats]),
    [["G4", 0, 1], ["A4", 1, 1.5], ["B4", 2.5, 0.5]],
  );
});

test("the full score lays out every documented event across readable systems", () => {
  const score = layoutSectionTwentyOneScore({
    events: duolingoSectionTwentyOneEvents,
    measureCount: duolingoSectionTwentyOneMeasureCount,
  });
  const glyphs = score.systems.flatMap((system) => system.glyphs);
  assert.equal(score.systems.length, 12);
  assert.equal(glyphs.filter((glyph) => glyph.kind === "note").length, 75);
  assert.equal(glyphs.filter((glyph) => glyph.kind === "rest").length, 10);
  assert.equal(glyphs.filter((glyph) => glyph.kind === "note" && glyph.font === "bravura").length, 17);
  assert.equal(score.systems.flatMap((system) => system.dots).length, 14);
  assert.equal(score.systems.flatMap((system) => system.ledgerLines).length, 6);
  assert.deepEqual(
    score.systems.map((system) => [system.firstMeasure, system.lastMeasure]),
    [[1, 3], [4, 6], [7, 9], [10, 12], [13, 15], [16, 18], [19, 21], [22, 24], [25, 27], [28, 30], [31, 33], [34, 34]],
  );
});
