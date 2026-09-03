import assert from "node:assert/strict";
import test from "node:test";

import { layoutPracticeLaneStaff, layoutTrebleStaff, trebleStaffStep } from "../../lib/music/score-layout.ts";
import { mariageAmourContent } from "../../lib/music/content/mariage-amour.ts";

const rightHandEvents = mariageAmourContent.events.filter((event) => event.hand === "right");

function measureSixScene() {
  return layoutTrebleStaff({
    events: rightHandEvents,
    measure: 6,
    clef: "treble",
    timeSignature: { beats: 3, beatType: 4 },
    staffSpace: 20,
    width: 1000,
  });
}

test("the static review lays out only measure 6", () => {
  const scene = measureSixScene();
  assert.equal(scene.measure, 6);
  assert.deepEqual(scene.notes.map((note) => note.eventId), ["6-R1", "6-R2", "6-R3", "6-R4", "6-R5"]);
  assert.deepEqual(scene.notes.map((note) => note.spelling), ["D5", "G4", "Bb4", "D5", "C5"]);
  assert.equal(scene.barlines.length, 1);
});

test("written spelling, not MIDI, determines the staff position", () => {
  assert.equal(trebleStaffStep("G4"), 2);
  assert.equal(trebleStaffStep("Bb4"), 4);
  assert.equal(trebleStaffStep("B4"), 4);
  assert.equal(trebleStaffStep("D5"), 6);

  const scene = measureSixScene();
  const yByEvent = Object.fromEntries(scene.notes.map((note) => [note.eventId, note.y]));
  assert.equal(yByEvent["6-R1"], 84);
  assert.equal(yByEvent["6-R2"], 124);
  assert.equal(yByEvent["6-R3"], 104);
  assert.equal(yByEvent["6-R4"], 84);
  assert.equal(yByEvent["6-R5"], 94);
});

test("beat spacing is linear and the two eighth-note pairs are beamed", () => {
  const scene = measureSixScene();
  const [first, second, third, fourth, fifth] = scene.notes;
  assert.ok(Math.abs((second.x - first.x) - (third.x - second.x) * 2) < 1e-9);
  assert.ok(Math.abs((fourth.x - third.x) - (fifth.x - fourth.x)) < 1e-9);
  assert.deepEqual(scene.beams.map((beam) => beam.eventIds), [
    ["6-R2", "6-R3"],
    ["6-R4", "6-R5"],
  ]);
  assert.deepEqual(scene.beams.map((beam) => beam.direction), ["up", "down"]);
});

test("B-flat receives one local accidental and the phrase needs no ledger lines", () => {
  const scene = measureSixScene();
  const accidentals = scene.glyphs.filter((glyph) => glyph.kind === "accidental");
  assert.equal(accidentals.length, 1);
  assert.equal(accidentals[0].eventId, "6-R3");
  assert.equal(accidentals[0].text, "\uE260");
  assert.equal(scene.ledgerLines.length, 0);
});

test("the practice lane follows the captured phone staff geometry", () => {
  const scene = layoutPracticeLaneStaff({
    events: rightHandEvents,
    measure: 6,
    clef: "treble",
    timeSignature: { beats: 3, beatType: 4 },
    staffSpace: 38,
    width: 1612,
  });
  assert.equal(scene.height, 360);
  assert.deepEqual(scene.staffLines.map((line) => line.y), [144, 182, 220, 258, 296]);
  assert.equal(scene.staffLines[0].x1, 100);
  assert.deepEqual(scene.barlines, [
    { x: 100, y1: 144, y2: 296 },
    { x: 1490, y1: 144, y2: 296 },
  ]);
  assert.deepEqual(scene.notes.map((note) => note.spelling), ["D5", "G4", "Bb4", "D5", "C5"]);
  assert.ok(scene.notes.every((note) => note.stemDirection === "up"));
  assert.equal(scene.stems.length, 0);
  assert.equal(scene.beams.length, 0);
  assert.deepEqual(
    scene.glyphs.filter((glyph) => glyph.kind === "note").map((glyph) => glyph.text),
    Array(5).fill("\uE1D5"),
  );
  assert.deepEqual(
    scene.glyphs.filter((glyph) => glyph.kind === "accidental").map((glyph) => [glyph.eventId, glyph.text]),
    [["6-R3", "\uE260"]],
  );
  assert.equal(scene.glyphs.filter((glyph) => glyph.kind === "notehead").length, 0);
  assert.equal(scene.glyphs.filter((glyph) => glyph.kind === "time-signature").length, 0);
});
