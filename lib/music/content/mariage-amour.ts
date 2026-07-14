import { assertCourseContent, type CourseContent, type ScoreEvent } from "../schema.ts";
import { spellingToMidi } from "../pitch.ts";

const event = (
  id: string,
  measure: number,
  beat: number,
  durationBeats: number,
  spelling: string,
  hand: "left" | "right",
  finger: 1 | 2 | 3 | 4 | 5,
  syncGroup?: string,
): ScoreEvent => ({
  id,
  measure,
  beat,
  durationBeats,
  midi: spellingToMidi(spelling),
  spelling,
  hand,
  finger,
  syncGroup,
});

const measureSix = [
  event("6-R1", 6, 0, 1, "D5", "right", 4, "6-S1"),
  event("6-R2", 6, 1, 0.5, "G4", "right", 1, "6-S2"),
  event("6-R3", 6, 1.5, 0.5, "Bb4", "right", 2),
  event("6-R4", 6, 2, 0.5, "D5", "right", 4, "6-S3"),
  event("6-R5", 6, 2.5, 0.5, "C5", "right", 3),
  event("6-L1", 6, 0, 1, "G2", "left", 5, "6-S1"),
  event("6-L2", 6, 1, 1, "D3", "left", 3, "6-S2"),
  event("6-L3", 6, 2, 1, "Bb3", "left", 1, "6-S3"),
];

const measureSeven = [
  event("7-R1", 7, 0, 1, "D5", "right", 4, "7-S1"),
  event("7-R2", 7, 1, 0.5, "G4", "right", 1, "7-S2"),
  event("7-R3", 7, 1.5, 0.5, "Bb4", "right", 2),
  event("7-R4", 7, 2, 0.5, "D5", "right", 4, "7-S3"),
  event("7-R5", 7, 2.5, 0.5, "C5", "right", 3),
  event("7-L1", 7, 0, 1, "G2", "left", 5, "7-S1"),
  event("7-L2", 7, 1, 1, "D3", "left", 3, "7-S2"),
  event("7-L3", 7, 2, 1, "Bb3", "left", 1, "7-S3"),
];

const rightHandEventIds = [...measureSix, ...measureSeven]
  .filter((item) => item.hand === "right")
  .map((item) => item.id);

export const mariageAmourContent: CourseContent = assertCourseContent({
  id: "mariage-amour-beginner",
  title: "梦中的婚礼",
  referenceBpm: 150,
  beatsPerMeasure: 3,
  events: [...measureSix, ...measureSeven],
  exercises: [
    {
      id: "B1-01",
      lessonId: "B1-01",
      title: "先听见节奏",
      instruction: "听一遍，找出这段旋律的长短规律。",
      mode: "listen",
      eventIds: rightHandEventIds,
      bpm: 75,
      tempoPercent: 50,
      visibleLayers: [],
      inputPolicy: "choice",
      passCriteria: { repetitions: 1 },
    },
    {
      id: "B1-02",
      lessonId: "B1-02",
      title: "跟上月光节拍",
      instruction: "色块到达青色判定线时，点击节奏键。",
      mode: "rhythm",
      eventIds: rightHandEventIds,
      bpm: 60,
      tempoPercent: 40,
      visibleLayers: ["blocks"],
      inputPolicy: "any-key",
      passCriteria: { rhythmAccuracy: 0.8, repetitions: 2 },
    },
  ],
});

export function getExercise(id: string) {
  return mariageAmourContent.exercises.find((exercise) => exercise.id === id);
}

export function getEventsForExercise(id: string) {
  const exercise = getExercise(id);
  if (!exercise) return [];
  const ids = new Set(exercise.eventIds);
  return mariageAmourContent.events.filter((item) => ids.has(item.id));
}
