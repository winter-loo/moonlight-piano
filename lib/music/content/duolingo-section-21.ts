export type DocumentedScoreDuration = 0.5 | 1 | 1.5 | 2;

export type DocumentedScoreEvent = {
  id: string;
  measure: number;
  beat: number;
  durationBeats: DocumentedScoreDuration;
} & (
  | { kind: "note"; spelling: string }
  | { kind: "rest" }
);

type SourceEvent =
  | { kind: "note"; spelling: string; durationBeats: DocumentedScoreDuration }
  | { kind: "rest"; durationBeats: 1 };

const note = (spelling: string, durationBeats: DocumentedScoreDuration): SourceEvent => ({
  kind: "note",
  spelling,
  durationBeats,
});

const rest = (): SourceEvent => ({ kind: "rest", durationBeats: 1 });

// Product document 21.3: Bicycle Built for Two — 34 measures in 3/4.
const documentedMeasures: readonly (readonly SourceEvent[])[] = [
  [note("F4", 2), rest()],
  [rest(), rest(), rest()],
  [rest(), rest(), rest()],
  [note("D4", 1), note("F4", 2)],
  [note("G4", 1), note("A4", 1.5), note("B4", 0.5)],
  [note("A4", 1), note("G4", 2)],
  [note("E4", 1), note("C4", 1.5), note("D4", 0.5)],
  [note("E4", 1), note("F4", 2)],
  [note("D4", 1), note("D4", 1.5), note("C4", 0.5)],
  [note("D4", 1), note("E4", 2)],
  [note("F4", 1), note("E4", 2)],
  [note("D4", 1), note("F4", 2)],
  [note("G4", 1), note("A4", 1.5), note("B4", 0.5)],
  [note("A4", 1), note("G4", 2)],
  [note("E4", 1), note("C4", 1.5), note("D4", 0.5)],
  [note("E4", 1), note("F4", 1.5), note("E4", 0.5)],
  [note("D4", 1), note("E4", 1.5), note("D4", 0.5)],
  [note("E4", 1), note("D4", 2)],
  [rest(), rest(), rest()],
  [note("D4", 1), note("F4", 2)],
  [note("G4", 1), note("A4", 1.5), note("B4", 0.5)],
  [note("A4", 1), note("G4", 2)],
  [note("E4", 1), note("C4", 1.5), note("D4", 0.5)],
  [note("E4", 1), note("F4", 2)],
  [note("D4", 1), note("D4", 1.5), note("C4", 0.5)],
  [note("D4", 1), note("E4", 2)],
  [note("F4", 1), note("E4", 2)],
  [note("D4", 1), note("F4", 2)],
  [note("G4", 1), note("A4", 1.5), note("B4", 0.5)],
  [note("A4", 1), note("G4", 2)],
  [note("E4", 1), note("C4", 1.5), note("D4", 0.5)],
  [note("E4", 1), note("F4", 1.5), note("E4", 0.5)],
  [note("D4", 1), note("E4", 1.5), note("D4", 0.5)],
  [note("E4", 1), note("D4", 2)],
];

export const duolingoSectionTwentyOneMeasureCount = documentedMeasures.length;

export const duolingoSectionTwentyOneEvents: readonly DocumentedScoreEvent[] = documentedMeasures.flatMap(
  (measureEvents, measureIndex) => {
    let beat = 0;
    return measureEvents.map((source, eventIndex) => {
      const event = {
        ...source,
        id: `section21-m${measureIndex + 1}-e${eventIndex + 1}`,
        measure: measureIndex + 1,
        beat,
      } as DocumentedScoreEvent;
      beat += source.durationBeats;
      return event;
    });
  },
);
