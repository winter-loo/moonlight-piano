export function beatsToSeconds(beats: number, bpm: number) {
  if (bpm <= 0) throw new Error("BPM must be positive.");
  return beats * (60 / bpm);
}

export function secondsToBeats(seconds: number, bpm: number) {
  if (bpm <= 0) throw new Error("BPM must be positive.");
  return seconds * (bpm / 60);
}

export function tempoPercentToBpm(referenceBpm: number, percent: number) {
  if (referenceBpm <= 0 || percent <= 0) throw new Error("Tempo values must be positive.");
  return referenceBpm * (percent / 100);
}
