export type SoundEngineState =
  | "idle"
  | "starting"
  | "running"
  | "suspended"
  | "closed"
  | "error"
  | "disposed";

export type SoundEventTime =
  | { kind: "now" }
  | { kind: "audio-time"; seconds: number }
  | { kind: "sample-frame"; frame: number };

type TimedSoundEvent = {
  time?: SoundEventTime;
};

export type NoteOnEvent = TimedSoundEvent & {
  type: "note-on";
  sourceId: string;
  note: number;
  velocity: number;
  gain?: number;
};

export type NoteOffEvent = TimedSoundEvent & {
  type: "note-off";
  sourceId: string;
  note: number;
  releaseVelocity: number;
};

export type PedalEvent = TimedSoundEvent & {
  type: "sustain" | "sostenuto" | "una-corda";
  position: number;
};

export type ParameterEvent = TimedSoundEvent & {
  type: "parameter";
  parameterId: string;
  value: number;
};

export type MetronomeEvent = TimedSoundEvent & {
  type: "metronome";
  accent: boolean;
};

export type SoundEngineEvent =
  | NoteOnEvent
  | NoteOffEvent
  | PedalEvent
  | ParameterEvent
  | MetronomeEvent;

export type SoundEngineClock = {
  sampleRate: number;
  currentTimeSeconds: number;
  currentSampleFrame: number;
  state: AudioContextState | "unavailable";
  baseLatencySeconds: number | null;
  outputLatencySeconds: number | null;
};

export type SoundEnginePedals = {
  sustain: number;
  sostenuto: number;
  unaCorda: number;
};

export type SoundEngineSnapshot = {
  id: string;
  label: string;
  state: SoundEngineState;
  ready: boolean;
  profile: string;
  activeVoices: number;
  pedals: SoundEnginePedals;
  parameters: Readonly<Record<string, number>>;
  clock: SoundEngineClock;
  routeVersion: number;
  lastEventType: SoundEngineEvent["type"] | null;
  lastError: string | null;
};

export type SoundEngineListener = (snapshot: SoundEngineSnapshot) => void;

export interface SoundEngine {
  readonly id: string;
  readonly label: string;

  start(): Promise<void>;
  resume(): Promise<void>;
  suspend(): Promise<void>;
  dispatch(events: SoundEngineEvent | readonly SoundEngineEvent[]): void;
  stopAll(time?: SoundEventTime): void;
  handleRouteChange(): Promise<void>;
  dispose(): Promise<void>;
  clock(): SoundEngineClock;
  snapshot(): SoundEngineSnapshot;
  subscribe(listener: SoundEngineListener): () => void;
}

export const NOW: SoundEventTime = Object.freeze({ kind: "now" });

export function atAudioTime(seconds: number): SoundEventTime {
  if (!Number.isFinite(seconds) || seconds < 0) {
    throw new RangeError("Audio time must be a finite non-negative number.");
  }
  return { kind: "audio-time", seconds };
}

export function atSampleFrame(frame: number): SoundEventTime {
  if (!Number.isSafeInteger(frame) || frame < 0) {
    throw new RangeError("Sample frame must be a non-negative safe integer.");
  }
  return { kind: "sample-frame", frame };
}

export function resolveEventTimeSeconds(
  time: SoundEventTime | undefined,
  clock: SoundEngineClock,
): number {
  if (!time || time.kind === "now") return clock.currentTimeSeconds;
  if (time.kind === "audio-time") return time.seconds;
  if (!(clock.sampleRate > 0)) {
    throw new Error("Cannot resolve a sample-frame event before the engine exposes a sample rate.");
  }
  return time.frame / clock.sampleRate;
}

export function isSoundEngine(value: unknown): value is SoundEngine {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<SoundEngine>;
  return typeof candidate.dispatch === "function"
    && typeof candidate.start === "function"
    && typeof candidate.clock === "function"
    && typeof candidate.snapshot === "function";
}

export function validateSoundEngineEvent(event: SoundEngineEvent): void {
  validateTime(event.time);

  switch (event.type) {
    case "note-on":
      validateSourceId(event.sourceId);
      validateMidiNote(event.note);
      validateUnitInterval(event.velocity, "Velocity");
      if (event.gain !== undefined && (!Number.isFinite(event.gain) || event.gain < 0 || event.gain > 4)) {
        throw new RangeError("Per-note gain must be finite and between 0 and 4.");
      }
      return;
    case "note-off":
      validateSourceId(event.sourceId);
      validateMidiNote(event.note);
      validateUnitInterval(event.releaseVelocity, "Release velocity");
      return;
    case "sustain":
    case "sostenuto":
    case "una-corda":
      validateUnitInterval(event.position, "Pedal position");
      return;
    case "parameter":
      if (!event.parameterId.trim()) throw new TypeError("Parameter id must not be empty.");
      if (!Number.isFinite(event.value)) throw new RangeError("Parameter value must be finite.");
      return;
    case "metronome":
      if (typeof event.accent !== "boolean") throw new TypeError("Metronome accent must be boolean.");
      return;
    default: {
      const exhaustive: never = event;
      throw new TypeError(`Unsupported sound event: ${String(exhaustive)}`);
    }
  }
}

function validateTime(time: SoundEventTime | undefined) {
  if (!time || time.kind === "now") return;
  if (time.kind === "audio-time") {
    if (!Number.isFinite(time.seconds) || time.seconds < 0) {
      throw new RangeError("Audio time must be a finite non-negative number.");
    }
    return;
  }
  if (!Number.isSafeInteger(time.frame) || time.frame < 0) {
    throw new RangeError("Sample frame must be a non-negative safe integer.");
  }
}

function validateSourceId(sourceId: string) {
  if (!sourceId.trim()) throw new TypeError("Sound event source id must not be empty.");
}

function validateMidiNote(note: number) {
  if (!Number.isInteger(note) || note < 0 || note > 127) {
    throw new RangeError("MIDI note must be an integer between 0 and 127.");
  }
}

function validateUnitInterval(value: number, name: string) {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new RangeError(`${name} must be finite and between 0 and 1.`);
  }
}
