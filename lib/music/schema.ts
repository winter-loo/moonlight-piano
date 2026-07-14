export type Hand = "left" | "right";

export type ScoreEvent = {
  id: string;
  measure: number;
  beat: number;
  durationBeats: number;
  midi: number;
  spelling: string;
  hand: Hand;
  finger?: 1 | 2 | 3 | 4 | 5;
  syncGroup?: string;
};

export type ExerciseMode = "listen" | "rhythm" | "locate" | "learn" | "follow" | "perform";
export type VisibleLayer = "blocks" | "staff" | "noteNames" | "fingering" | "keyboard";
export type InputPolicy = "none" | "choice" | "any-key" | "pitch" | "hands";

export type PassCriteria = {
  rhythmAccuracy?: number;
  pitchAccuracy?: number;
  uninterrupted?: boolean;
  repetitions?: number;
};

export type ExerciseDefinition = {
  id: string;
  lessonId: string;
  title: string;
  instruction: string;
  mode: ExerciseMode;
  eventIds: string[];
  tempoPercent?: number;
  bpm?: number;
  visibleLayers: VisibleLayer[];
  inputPolicy: InputPolicy;
  passCriteria: PassCriteria;
};

export type CourseContent = {
  id: string;
  title: string;
  referenceBpm: number;
  beatsPerMeasure: number;
  events: ScoreEvent[];
  exercises: ExerciseDefinition[];
};

function isFinger(value: number | undefined): value is 1 | 2 | 3 | 4 | 5 {
  return value === undefined || (Number.isInteger(value) && value >= 1 && value <= 5);
}

export function validateCourseContent(content: CourseContent): string[] {
  const errors: string[] = [];
  const eventIds = new Set<string>();

  if (!content.id.trim()) errors.push("Course id is required.");
  if (!content.title.trim()) errors.push("Course title is required.");
  if (!(content.referenceBpm > 0)) errors.push("Reference BPM must be positive.");
  if (!(content.beatsPerMeasure > 0)) errors.push("Beats per measure must be positive.");

  for (const event of content.events) {
    if (eventIds.has(event.id)) errors.push(`Duplicate event id: ${event.id}`);
    eventIds.add(event.id);
    if (!Number.isInteger(event.measure) || event.measure < 1) errors.push(`${event.id}: invalid measure.`);
    if (!(event.beat >= 0 && event.beat < content.beatsPerMeasure)) errors.push(`${event.id}: invalid beat.`);
    if (!(event.durationBeats > 0)) errors.push(`${event.id}: duration must be positive.`);
    if (!(event.midi >= 0 && event.midi <= 127)) errors.push(`${event.id}: invalid MIDI number.`);
    if (!isFinger(event.finger)) errors.push(`${event.id}: invalid fingering.`);
  }

  const exerciseIds = new Set<string>();
  for (const exercise of content.exercises) {
    if (exerciseIds.has(exercise.id)) errors.push(`Duplicate exercise id: ${exercise.id}`);
    exerciseIds.add(exercise.id);
    for (const id of exercise.eventIds) {
      if (!eventIds.has(id)) errors.push(`${exercise.id}: unknown event ${id}.`);
    }
    if (exercise.bpm !== undefined && exercise.bpm <= 0) errors.push(`${exercise.id}: BPM must be positive.`);
  }

  const syncGroups = new Map<string, ScoreEvent[]>();
  for (const event of content.events) {
    if (!event.syncGroup) continue;
    const group = syncGroups.get(event.syncGroup) ?? [];
    group.push(event);
    syncGroups.set(event.syncGroup, group);
  }
  for (const [groupId, group] of syncGroups) {
    const first = group[0];
    if (group.some((event) => event.measure !== first.measure || event.beat !== first.beat)) {
      errors.push(`${groupId}: synchronized events must share measure and beat.`);
    }
  }

  return errors;
}

export function assertCourseContent(content: CourseContent): CourseContent {
  const errors = validateCourseContent(content);
  if (errors.length > 0) throw new Error(`Invalid course content:\n${errors.join("\n")}`);
  return content;
}
