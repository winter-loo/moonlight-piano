const NOTE_TO_SEMITONE: Record<string, number> = {
  C: 0,
  "C#": 1,
  Db: 1,
  D: 2,
  "D#": 3,
  Eb: 3,
  E: 4,
  F: 5,
  "F#": 6,
  Gb: 6,
  G: 7,
  "G#": 8,
  Ab: 8,
  A: 9,
  "A#": 10,
  Bb: 10,
  B: 11,
};

export function spellingToMidi(spelling: string) {
  const match = spelling.match(/^([A-G](?:#|b)?)(-?\d+)$/);
  if (!match) throw new Error(`Invalid pitch spelling: ${spelling}`);
  const [, name, octaveText] = match;
  const semitone = NOTE_TO_SEMITONE[name];
  if (semitone === undefined) throw new Error(`Unknown pitch name: ${name}`);
  return (Number(octaveText) + 1) * 12 + semitone;
}

export function midiToFrequency(midi: number) {
  return 440 * 2 ** ((midi - 69) / 12);
}
