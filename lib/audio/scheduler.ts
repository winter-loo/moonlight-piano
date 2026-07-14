import { midiToFrequency } from "../music/pitch.ts";

export function scheduleMetronome(context: AudioContext, time: number, accent = false) {
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(accent ? 1050 : 760, time);
  gain.gain.setValueAtTime(0.0001, time);
  gain.gain.exponentialRampToValueAtTime(accent ? 0.16 : 0.1, time + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.055);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start(time);
  oscillator.stop(time + 0.06);
}

export function scheduleMidiTone(context: AudioContext, midi: number, time: number, durationSeconds: number, volume = 0.18) {
  const gain = context.createGain();
  const filter = context.createBiquadFilter();
  const fundamental = context.createOscillator();
  const overtone = context.createOscillator();

  filter.type = "lowpass";
  filter.frequency.setValueAtTime(3100, time);
  fundamental.type = "triangle";
  overtone.type = "sine";
  fundamental.frequency.setValueAtTime(midiToFrequency(midi), time);
  overtone.frequency.setValueAtTime(midiToFrequency(midi) * 2, time);

  const overtoneGain = context.createGain();
  overtoneGain.gain.value = 0.16;
  fundamental.connect(gain);
  overtone.connect(overtoneGain);
  overtoneGain.connect(gain);
  gain.connect(filter);
  filter.connect(context.destination);

  gain.gain.setValueAtTime(0.0001, time);
  gain.gain.exponentialRampToValueAtTime(volume, time + 0.008);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.025, volume * 0.36), time + Math.min(0.22, durationSeconds * 0.5));
  gain.gain.exponentialRampToValueAtTime(0.0001, time + durationSeconds + 0.16);

  fundamental.start(time);
  overtone.start(time);
  fundamental.stop(time + durationSeconds + 0.18);
  overtone.stop(time + durationSeconds + 0.18);
}
