import type { ScoreEvent } from "./schema.ts";

export type StaffClef = "treble";
export type StemDirection = "up" | "down";

export type TimeSignature = {
  beats: number;
  beatType: number;
};

export type ScoreLayoutInput = {
  events: readonly ScoreEvent[];
  measure: number;
  clef: StaffClef;
  timeSignature: TimeSignature;
  staffSpace: number;
  width: number;
};

export type MusicGlyphPlacement = {
  id: string;
  kind: "clef" | "time-signature" | "accidental" | "notehead" | "note";
  text: string;
  x: number;
  y: number;
  fontSize: number;
  anchor: "start" | "middle";
  eventId?: string;
};

export type StaffNotePlacement = {
  eventId: string;
  beat: number;
  durationBeats: number;
  spelling: string;
  staffStep: number;
  x: number;
  y: number;
  stemDirection: StemDirection;
};

export type StaffStem = {
  eventId: string;
  x: number;
  y1: number;
  y2: number;
  thickness: number;
};

export type StaffBeam = {
  id: string;
  eventIds: string[];
  direction: StemDirection;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  thickness: number;
};

export type StaffScene = {
  width: number;
  height: number;
  measure: number;
  staffSpace: number;
  measureLabel: { text: string; x: number; y: number };
  staffLines: Array<{ y: number; x1: number; x2: number }>;
  barlines: Array<{ x: number; y1: number; y2: number }>;
  glyphs: MusicGlyphPlacement[];
  notes: StaffNotePlacement[];
  stems: StaffStem[];
  beams: StaffBeam[];
  ledgerLines: Array<{ id: string; x1: number; x2: number; y: number }>;
};

const SMUFL = {
  gClef: "\uE050",
  noteheadBlack: "\uE0A4",
  noteQuarterUp: "\uE1D5",
  accidentalFlat: "\uE260",
  accidentalSharp: "\uE262",
} as const;

const LETTER_INDEX: Record<string, number> = {
  C: 0,
  D: 1,
  E: 2,
  F: 3,
  G: 4,
  A: 5,
  B: 6,
};

const TREBLE_BOTTOM_LINE_STEP = 4 * 7 + LETTER_INDEX.E;
const STAFF_MIDDLE_LINE_STEP = 4;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function parseSpelling(spelling: string) {
  const match = spelling.match(/^([A-G])([#b]?)(-?\d+)$/);
  if (!match) throw new Error(`Invalid pitch spelling: ${spelling}`);
  const [, letter, accidental, octaveText] = match;
  return {
    letter,
    accidental,
    octave: Number(octaveText),
  };
}

export function trebleStaffStep(spelling: string) {
  const { letter, octave } = parseSpelling(spelling);
  return octave * 7 + LETTER_INDEX[letter] - TREBLE_BOTTOM_LINE_STEP;
}

function timeSignatureGlyph(digit: number) {
  if (!Number.isInteger(digit) || digit < 0 || digit > 9) {
    throw new Error(`Unsupported time-signature digit: ${digit}`);
  }
  return String.fromCodePoint(0xE080 + digit);
}

function accidentalGlyph(spelling: string) {
  const { accidental } = parseSpelling(spelling);
  if (accidental === "b") return SMUFL.accidentalFlat;
  if (accidental === "#") return SMUFL.accidentalSharp;
  return null;
}

function groupEighthNotes(notes: StaffNotePlacement[]) {
  const groups: StaffNotePlacement[][] = [];
  let pending: StaffNotePlacement[] = [];

  function flush() {
    if (pending.length > 1) groups.push(pending);
    pending = [];
  }

  for (const note of notes) {
    if (note.durationBeats !== 0.5) {
      flush();
      continue;
    }
    const previous = pending.at(-1);
    const continuesBeat = previous
      && Math.abs(previous.beat + previous.durationBeats - note.beat) < 0.0001
      && Math.floor(previous.beat) === Math.floor(note.beat);
    if (!continuesBeat) flush();
    pending.push(note);
  }
  flush();
  return groups;
}

export function layoutTrebleStaff(input: ScoreLayoutInput): StaffScene {
  const { events, measure, clef, timeSignature, staffSpace, width } = input;
  if (clef !== "treble") throw new Error(`Unsupported clef: ${clef}`);
  if (!(staffSpace > 0)) throw new Error("staffSpace must be positive.");
  if (!(width >= staffSpace * 32)) throw new Error("Score width is too small for the requested staff space.");
  if (!(timeSignature.beats > 0)) throw new Error("Time signature must have at least one beat.");

  const measureEvents = events
    .filter((event) => event.measure === measure)
    .sort((left, right) => left.beat - right.beat || left.id.localeCompare(right.id));
  const unsupported = measureEvents.find((event) => event.durationBeats !== 1 && event.durationBeats !== 0.5);
  if (unsupported) throw new Error(`${unsupported.id}: only quarter and eighth notes are supported in this layout stage.`);

  const topLineY = staffSpace * 3.2;
  const bottomLineY = topLineY + staffSpace * 4;
  const staffX1 = staffSpace * 2;
  const barlineX = width - staffSpace * 3;
  const firstNoteX = staffX1 + staffSpace * 15.5;
  const beatWidth = (barlineX - firstNoteX) / timeSignature.beats;
  const musicFontSize = staffSpace * 4;
  const noteheadHalfWidth = staffSpace * 0.52;
  const stemLength = staffSpace * 3.5;
  const stemThickness = staffSpace * 0.12;
  const beamThickness = staffSpace * 0.48;

  const notes: StaffNotePlacement[] = measureEvents.map((event) => {
    const staffStep = trebleStaffStep(event.spelling);
    return {
      eventId: event.id,
      beat: event.beat,
      durationBeats: event.durationBeats,
      spelling: event.spelling,
      staffStep,
      x: firstNoteX + event.beat * beatWidth,
      y: bottomLineY - staffStep * (staffSpace / 2),
      stemDirection: staffStep < STAFF_MIDDLE_LINE_STEP ? "up" : "down",
    };
  });

  const beamGroups = groupEighthNotes(notes);
  const beamByEvent = new Map<string, StaffBeam>();
  const beams = beamGroups.map((group, index) => {
    const first = group[0];
    const last = group.at(-1)!;
    const averageStep = group.reduce((sum, note) => sum + note.staffStep, 0) / group.length;
    const direction: StemDirection = averageStep < STAFF_MIDDLE_LINE_STEP ? "up" : "down";
    const sign = direction === "up" ? -1 : 1;
    const averageY = group.reduce((sum, note) => sum + note.y, 0) / group.length;
    const slope = clamp((last.y - first.y) * 0.25, -staffSpace * 0.5, staffSpace * 0.5);
    const x1 = first.x + (direction === "up" ? noteheadHalfWidth : -noteheadHalfWidth);
    const x2 = last.x + (direction === "up" ? noteheadHalfWidth : -noteheadHalfWidth);
    const centerY = averageY + sign * stemLength;
    const beam: StaffBeam = {
      id: `measure-${measure}-beam-${index + 1}`,
      eventIds: group.map((note) => note.eventId),
      direction,
      x1,
      y1: centerY - slope / 2,
      x2,
      y2: centerY + slope / 2,
      thickness: beamThickness,
    };
    for (const note of group) {
      note.stemDirection = direction;
      beamByEvent.set(note.eventId, beam);
    }
    return beam;
  });

  const beamYAt = (beam: StaffBeam, x: number) => {
    if (beam.x1 === beam.x2) return beam.y1;
    const progress = (x - beam.x1) / (beam.x2 - beam.x1);
    return beam.y1 + (beam.y2 - beam.y1) * progress;
  };

  const stems: StaffStem[] = notes.map((note) => {
    const x = note.x + (note.stemDirection === "up" ? noteheadHalfWidth : -noteheadHalfWidth);
    const beam = beamByEvent.get(note.eventId);
    let y2 = note.y + (note.stemDirection === "up" ? -stemLength : stemLength);
    if (beam) {
      const beamY = beamYAt(beam, x);
      y2 = note.stemDirection === "up" ? beamY + beam.thickness : beamY;
    }
    return { eventId: note.eventId, x, y1: note.y, y2, thickness: stemThickness };
  });

  const glyphs: MusicGlyphPlacement[] = [
    {
      id: "treble-clef",
      kind: "clef",
      text: SMUFL.gClef,
      x: staffX1 + staffSpace * 1.6,
      y: bottomLineY - staffSpace,
      fontSize: musicFontSize,
      anchor: "start",
    },
    {
      id: "time-signature-top",
      kind: "time-signature",
      text: timeSignatureGlyph(timeSignature.beats),
      x: staffX1 + staffSpace * 9.4,
      y: topLineY + staffSpace,
      fontSize: musicFontSize,
      anchor: "middle",
    },
    {
      id: "time-signature-bottom",
      kind: "time-signature",
      text: timeSignatureGlyph(timeSignature.beatType),
      x: staffX1 + staffSpace * 9.4,
      y: topLineY + staffSpace * 3,
      fontSize: musicFontSize,
      anchor: "middle",
    },
  ];

  for (const note of notes) {
    const accidental = accidentalGlyph(note.spelling);
    if (accidental) {
      glyphs.push({
        id: `${note.eventId}-accidental`,
        kind: "accidental",
        text: accidental,
        x: note.x - staffSpace * 1.65,
        y: note.y,
        fontSize: musicFontSize,
        anchor: "middle",
        eventId: note.eventId,
      });
    }
    glyphs.push({
      id: `${note.eventId}-notehead`,
      kind: "notehead",
      text: SMUFL.noteheadBlack,
      x: note.x,
      y: note.y,
      fontSize: musicFontSize,
      anchor: "middle",
      eventId: note.eventId,
    });
  }

  const ledgerLines = notes.flatMap((note) => {
    const ledgerSteps: number[] = [];
    if (note.staffStep < 0) {
      for (let step = -2; step >= note.staffStep; step -= 2) ledgerSteps.push(step);
    } else if (note.staffStep > 8) {
      for (let step = 10; step <= note.staffStep; step += 2) ledgerSteps.push(step);
    }
    return ledgerSteps.map((step) => ({
      id: `${note.eventId}-ledger-${step}`,
      x1: note.x - staffSpace * 0.85,
      x2: note.x + staffSpace * 0.85,
      y: bottomLineY - step * (staffSpace / 2),
    }));
  });

  return {
    width,
    height: topLineY + staffSpace * 8,
    measure,
    staffSpace,
    measureLabel: {
      text: String(measure),
      x: firstNoteX,
      y: topLineY - staffSpace * 1.45,
    },
    staffLines: Array.from({ length: 5 }, (_, index) => ({
      y: topLineY + index * staffSpace,
      x1: staffX1,
      x2: barlineX,
    })),
    barlines: [{ x: barlineX, y1: topLineY, y2: bottomLineY }],
    glyphs,
    notes,
    stems,
    beams,
    ledgerLines,
  };
}

export function layoutPracticeLaneStaff(input: ScoreLayoutInput): StaffScene {
  const { events, measure, clef, timeSignature, staffSpace, width } = input;
  if (clef !== "treble") throw new Error(`Unsupported clef: ${clef}`);
  if (!(staffSpace > 0)) throw new Error("staffSpace must be positive.");
  if (!(width >= staffSpace * 32)) throw new Error("Score width is too small for the requested staff space.");
  if (!(timeSignature.beats > 0)) throw new Error("Time signature must have at least one beat.");

  const measureEvents = events
    .filter((event) => event.measure === measure)
    .sort((left, right) => left.beat - right.beat || left.id.localeCompare(right.id));
  const topLineY = staffSpace * (144 / 38);
  const bottomLineY = topLineY + staffSpace * 4;
  const staffX1 = width * (100 / 1612);
  const barlineX = width * (1490 / 1612);
  const firstNoteX = width * (385 / 1612);
  const beatWidth = (barlineX - firstNoteX) / timeSignature.beats;
  const musicFontSize = staffSpace * 4;

  const notes: StaffNotePlacement[] = measureEvents.map((event) => {
    const staffStep = trebleStaffStep(event.spelling);
    return {
      eventId: event.id,
      beat: event.beat,
      durationBeats: event.durationBeats,
      spelling: event.spelling,
      staffStep,
      x: firstNoteX + event.beat * beatWidth,
      y: bottomLineY - staffStep * (staffSpace / 2),
      stemDirection: "up",
    };
  });

  const glyphs: MusicGlyphPlacement[] = [
    {
      id: "treble-clef",
      kind: "clef",
      text: SMUFL.gClef,
      x: width * (105 / 1612),
      y: bottomLineY - staffSpace,
      fontSize: musicFontSize,
      anchor: "start",
    },
  ];

  for (const note of notes) {
    const accidental = accidentalGlyph(note.spelling);
    if (accidental) {
      glyphs.push({
        id: `${note.eventId}-accidental`,
        kind: "accidental",
        text: accidental,
        x: note.x - staffSpace * 1.3,
        y: note.y,
        fontSize: musicFontSize,
        anchor: "middle",
        eventId: note.eventId,
      });
    }
    glyphs.push({
      id: `${note.eventId}-quarter-note-up`,
      kind: "note",
      text: SMUFL.noteQuarterUp,
      x: note.x,
      y: note.y,
      fontSize: musicFontSize,
      anchor: "middle",
      eventId: note.eventId,
    });
  }

  const ledgerLines = notes.flatMap((note) => {
    const ledgerSteps: number[] = [];
    if (note.staffStep < 0) {
      for (let step = -2; step >= note.staffStep; step -= 2) ledgerSteps.push(step);
    } else if (note.staffStep > 8) {
      for (let step = 10; step <= note.staffStep; step += 2) ledgerSteps.push(step);
    }
    return ledgerSteps.map((step) => ({
      id: `${note.eventId}-ledger-${step}`,
      x1: note.x - staffSpace * 0.85,
      x2: note.x + staffSpace * 0.85,
      y: bottomLineY - step * (staffSpace / 2),
    }));
  });

  return {
    width,
    height: staffSpace * (360 / 38),
    measure,
    staffSpace,
    measureLabel: { text: "", x: firstNoteX, y: topLineY },
    staffLines: Array.from({ length: 5 }, (_, index) => ({
      y: topLineY + index * staffSpace,
      x1: staffX1,
      x2: barlineX,
    })),
    barlines: [
      { x: staffX1, y1: topLineY, y2: bottomLineY },
      { x: barlineX, y1: topLineY, y2: bottomLineY },
    ],
    glyphs,
    notes,
    stems: [],
    beams: [],
    ledgerLines,
  };
}
