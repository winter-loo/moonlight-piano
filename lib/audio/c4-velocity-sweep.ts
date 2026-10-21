import { atSampleFrame, type SoundEngineClock, type SoundEngineEvent } from "./sound-engine.ts";

export type C4SweepKind = "listening" | "full";

/** A bounded, sample-timed gesture; the offline report measures isolated notes. */
export function createC4VelocitySweep(clock: SoundEngineClock, kind: C4SweepKind) {
  if (!Number.isFinite(clock.sampleRate) || clock.sampleRate <= 0
    || !Number.isSafeInteger(clock.currentSampleFrame) || clock.currentSampleFrame < 0) {
    throw new RangeError("Start the audio engine before scheduling a velocity sweep.");
  }
  const velocities = kind === "full"
    ? Array.from({ length: 127 }, (_, index) => (index + 1) / 127)
    : [0.08, 0.16, 0.28, 0.42, 0.6, 0.78, 1];
  // 254 events plus the preceding reset fit the worklet's 256-event queue.
  const stepFrames = Math.round(clock.sampleRate * (kind === "full" ? 0.25 : 1.5));
  const startFrame = clock.currentSampleFrame + Math.max(384, Math.round(clock.sampleRate * 0.05));
  const endFrame = startFrame + stepFrames * velocities.length;
  if (!Number.isSafeInteger(endFrame)) throw new RangeError("Sweep exceeds the audio clock range.");
  const events: SoundEngineEvent[] = velocities.flatMap((velocity, index) => {
    const frame = startFrame + stepFrames * index;
    const sourceId = `c4-sweep-${startFrame}-${index}`;
    return [
      { type: "note-on" as const, sourceId, note: 60, velocity, time: atSampleFrame(frame) },
      { type: "note-off" as const, sourceId, note: 60, releaseVelocity: 0.5,
        time: atSampleFrame(frame + Math.round(stepFrames * 0.65)) },
    ];
  });
  return { events, velocities, startFrame, endFrame, stepFrames, kind };
}
