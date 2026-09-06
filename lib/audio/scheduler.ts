import { getLegacyLessonEngineForContext } from "./engine-registry.ts";
import {
  atAudioTime,
  isSoundEngine,
  type SoundEngine,
} from "./sound-engine.ts";

type SoundTarget = SoundEngine | AudioContext;

let scheduledVoiceSerial = 0;

function resolveSoundEngine(target: SoundTarget) {
  return isSoundEngine(target) ? target : getLegacyLessonEngineForContext(target);
}

export function scheduleMetronome(target: SoundTarget, time: number, accent = false) {
  const engine = resolveSoundEngine(target);
  void engine.start();
  engine.dispatch({
    type: "metronome",
    accent,
    time: atAudioTime(time),
  });
}

export function scheduleMidiTone(
  target: SoundTarget,
  midi: number,
  time: number,
  durationSeconds: number,
  volume = 0.18,
  sourceId = `scheduled-note-${++scheduledVoiceSerial}`,
) {
  const engine = resolveSoundEngine(target);
  void engine.start();
  engine.dispatch([
    {
      type: "note-on",
      sourceId,
      note: midi,
      velocity: 0.8,
      gain: volume,
      time: atAudioTime(time),
    },
    {
      type: "note-off",
      sourceId,
      note: midi,
      releaseVelocity: 0.5,
      time: atAudioTime(time + Math.max(0, durationSeconds)),
    },
  ]);
  return sourceId;
}
