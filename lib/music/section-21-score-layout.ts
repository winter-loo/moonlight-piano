import type { DocumentedScoreEvent } from "./content/duolingo-section-21.ts";
import { trebleStaffStep } from "./score-layout.ts";

type StemDirection = "up" | "down";

export type FullScoreGlyph = {
  id: string;
  eventId?: string;
  measure?: number;
  kind: "clef" | "time-signature" | "note" | "rest";
  font: "pianolab" | "bravura";
  text: string;
  x: number;
  y: number;
  fontSize: number;
  durationBeats?: number;
};

export type FullScoreSystem = {
  id: string;
  firstMeasure: number;
  lastMeasure: number;
  width: number;
  height: number;
  staffLines: Array<{ id: string; x1: number; x2: number; y: number }>;
  barlines: Array<{ id: string; x: number; y1: number; y2: number }>;
  measureLabels: Array<{ measure: number; x: number; y: number }>;
  glyphs: FullScoreGlyph[];
  dots: Array<{ id: string; eventId: string; cx: number; cy: number; r: number }>;
  ledgerLines: Array<{ id: string; eventId: string; x1: number; x2: number; y: number }>;
};

export type FullScoreLayout = {
  systems: FullScoreSystem[];
  noteCount: number;
  restCount: number;
  measureCount: number;
};

const SMUFL = {
  gClef: "\uE050",
  timeSig3: "\uE083",
  timeSig4: "\uE084",
  noteHalfUp: "\uE1D3",
  noteHalfDown: "\uE1D4",
  noteQuarterUp: "\uE1D5",
  noteQuarterDown: "\uE1D6",
  noteEighthUp: "\uE1D7",
  noteEighthDown: "\uE1D8",
  restQuarter: "\uE4E5",
} as const;

function noteGlyph(durationBeats: number, direction: StemDirection) {
  if (durationBeats === 0.5) {
    return direction === "up" ? SMUFL.noteEighthUp : SMUFL.noteEighthDown;
  }
  if (durationBeats === 1 || durationBeats === 1.5) {
    return direction === "up" ? SMUFL.noteQuarterUp : SMUFL.noteQuarterDown;
  }
  if (durationBeats === 2) {
    return direction === "up" ? SMUFL.noteHalfUp : SMUFL.noteHalfDown;
  }
  throw new Error(`Unsupported documented duration: ${durationBeats}`);
}

export function layoutSectionTwentyOneScore({
  events,
  measureCount,
  measuresPerSystem = 3,
  width = 1200,
  staffSpace = 20,
}: {
  events: readonly DocumentedScoreEvent[];
  measureCount: number;
  measuresPerSystem?: number;
  width?: number;
  staffSpace?: number;
}): FullScoreLayout {
  if (!Number.isInteger(measureCount) || measureCount < 1) throw new Error("measureCount must be positive.");
  if (!Number.isInteger(measuresPerSystem) || measuresPerSystem < 1) throw new Error("measuresPerSystem must be positive.");
  if (!(staffSpace > 0)) throw new Error("staffSpace must be positive.");

  const systemCount = Math.ceil(measureCount / measuresPerSystem);
  const musicFontSize = staffSpace * 4;
  const topLineY = staffSpace * 3.6;
  const bottomLineY = topLineY + staffSpace * 4;
  const height = staffSpace * 11;
  const staffX1 = staffSpace * 2;
  const staffX2 = width - staffSpace * 2;

  const systems = Array.from({ length: systemCount }, (_, systemIndex): FullScoreSystem => {
    const firstMeasure = systemIndex * measuresPerSystem + 1;
    const lastMeasure = Math.min(measureCount, firstMeasure + measuresPerSystem - 1);
    const measuresInSystem = lastMeasure - firstMeasure + 1;
    const showTimeSignature = systemIndex === 0;
    const headerWidth = staffSpace * (showTimeSignature ? 9 : 5.6);
    const contentX1 = staffX1 + headerWidth;
    const measureWidth = (staffX2 - contentX1) / measuresInSystem;
    const glyphs: FullScoreGlyph[] = [
      {
        id: `system-${systemIndex + 1}-clef`,
        kind: "clef",
        font: "pianolab",
        text: SMUFL.gClef,
        x: staffX1 + staffSpace * 0.35,
        y: bottomLineY - staffSpace,
        fontSize: musicFontSize,
      },
    ];

    if (showTimeSignature) {
      glyphs.push(
        {
          id: "time-signature-top",
          kind: "time-signature",
          font: "pianolab",
          text: SMUFL.timeSig3,
          x: staffX1 + staffSpace * 6.4,
          y: topLineY + staffSpace,
          fontSize: musicFontSize,
        },
        {
          id: "time-signature-bottom",
          kind: "time-signature",
          font: "pianolab",
          text: SMUFL.timeSig4,
          x: staffX1 + staffSpace * 6.4,
          y: topLineY + staffSpace * 3,
          fontSize: musicFontSize,
        },
      );
    }

    const dots: FullScoreSystem["dots"] = [];
    const ledgerLines: FullScoreSystem["ledgerLines"] = [];
    const barlines: FullScoreSystem["barlines"] = [];
    const measureLabels: FullScoreSystem["measureLabels"] = [];

    for (let measure = firstMeasure; measure <= lastMeasure; measure += 1) {
      const measureIndex = measure - firstMeasure;
      const measureX1 = contentX1 + measureIndex * measureWidth;
      const beatWidth = (measureWidth - staffSpace * 2.4) / 3;
      const measureEvents = events.filter((event) => event.measure === measure);
      measureLabels.push({ measure, x: measureX1 + staffSpace * 0.35, y: topLineY - staffSpace * 1.1 });
      if (measureIndex === 0) {
        barlines.push({
          id: `measure-${measure}-start`,
          x: measureX1,
          y1: topLineY,
          y2: bottomLineY,
        });
      }
      barlines.push({
        id: `measure-${measure}-end`,
        x: measureX1 + measureWidth,
        y1: topLineY,
        y2: bottomLineY,
      });

      for (const event of measureEvents) {
        const x = measureX1 + staffSpace * 1.2 + event.beat * beatWidth;
        if (event.kind === "rest") {
          glyphs.push({
            id: `${event.id}-rest`,
            eventId: event.id,
            measure,
            kind: "rest",
            font: "pianolab",
            text: SMUFL.restQuarter,
            x,
            y: topLineY + staffSpace * 2.45,
            fontSize: musicFontSize,
            durationBeats: event.durationBeats,
          });
          continue;
        }

        const staffStep = trebleStaffStep(event.spelling);
        const y = bottomLineY - staffStep * (staffSpace / 2);
        const direction: StemDirection = staffStep < 4 ? "up" : "down";
        glyphs.push({
          id: `${event.id}-note`,
          eventId: event.id,
          measure,
          kind: "note",
          font: event.durationBeats === 2 ? "bravura" : "pianolab",
          text: noteGlyph(event.durationBeats, direction),
          x,
          y,
          fontSize: musicFontSize,
          durationBeats: event.durationBeats,
        });

        if (event.durationBeats === 1.5) {
          dots.push({
            id: `${event.id}-dot`,
            eventId: event.id,
            cx: x + staffSpace * 0.8,
            cy: staffStep % 2 === 0 ? y - staffSpace / 2 : y,
            r: staffSpace * 0.15,
          });
        }

        if (staffStep < 0) {
          for (let step = -2; step >= staffStep; step -= 2) {
            ledgerLines.push({
              id: `${event.id}-ledger-${step}`,
              eventId: event.id,
              x1: x - staffSpace * 0.72,
              x2: x + staffSpace * 0.72,
              y: bottomLineY - step * (staffSpace / 2),
            });
          }
        }
      }
    }

    return {
      id: `system-${systemIndex + 1}`,
      firstMeasure,
      lastMeasure,
      width,
      height,
      staffLines: Array.from({ length: 5 }, (_, lineIndex) => ({
        id: `system-${systemIndex + 1}-line-${lineIndex + 1}`,
        x1: staffX1,
        x2: staffX2,
        y: topLineY + lineIndex * staffSpace,
      })),
      barlines,
      measureLabels,
      glyphs,
      dots,
      ledgerLines,
    };
  });

  return {
    systems,
    noteCount: events.filter((event) => event.kind === "note").length,
    restCount: events.filter((event) => event.kind === "rest").length,
    measureCount,
  };
}
