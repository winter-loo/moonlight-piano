export type RhythmTarget = {
  id: string;
  beat: number;
  durationBeats: number;
};

export type RhythmTap = {
  id: string;
  beat: number;
};

export type RhythmMatch = {
  targetId: string;
  tapId: string;
  deltaBeats: number;
  timing: "early" | "on-time" | "late";
};

export type RhythmResult = {
  matches: RhythmMatch[];
  misses: string[];
  extras: string[];
  accuracy: number;
  meanAbsoluteDeltaBeats: number;
};

function timingLabel(delta: number, onTimeBeats: number): RhythmMatch["timing"] {
  if (Math.abs(delta) <= onTimeBeats) return "on-time";
  return delta < 0 ? "early" : "late";
}

export function findNearestRhythmTarget(
  targets: RhythmTarget[],
  tapBeat: number,
  matchedTargetIds: ReadonlySet<string>,
  windowBeats = 0.36,
) {
  return targets
    .filter((target) => !matchedTargetIds.has(target.id))
    .map((target) => ({ target, delta: tapBeat - target.beat }))
    .filter(({ delta }) => Math.abs(delta) <= windowBeats)
    .sort((a, b) => Math.abs(a.delta) - Math.abs(b.delta))[0] ?? null;
}

export function evaluateRhythmAttempt(
  targets: RhythmTarget[],
  taps: RhythmTap[],
  windowBeats = 0.36,
  onTimeBeats = 0.14,
): RhythmResult {
  const matchedTargets = new Set<string>();
  const matches: RhythmMatch[] = [];
  const extras: string[] = [];

  for (const tap of [...taps].sort((a, b) => a.beat - b.beat)) {
    const nearest = findNearestRhythmTarget(targets, tap.beat, matchedTargets, windowBeats);
    if (!nearest) {
      extras.push(tap.id);
      continue;
    }
    matchedTargets.add(nearest.target.id);
    matches.push({
      targetId: nearest.target.id,
      tapId: tap.id,
      deltaBeats: nearest.delta,
      timing: timingLabel(nearest.delta, onTimeBeats),
    });
  }

  const misses = targets.filter((target) => !matchedTargets.has(target.id)).map((target) => target.id);
  const accuracy = targets.length === 0 ? 0 : matches.length / Math.max(targets.length, taps.length);
  const meanAbsoluteDeltaBeats = matches.length === 0
    ? 0
    : matches.reduce((sum, match) => sum + Math.abs(match.deltaBeats), 0) / matches.length;

  return { matches, misses, extras, accuracy, meanAbsoluteDeltaBeats };
}
