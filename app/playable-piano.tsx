"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Hand = "左手" | "右手";

type PlayablePianoProps = {
  hand: Hand;
  onActivity?: (message: string) => void;
};

type NoteDefinition = {
  name: string;
  octave: number;
};

type Voice = {
  gain: GainNode;
  oscillators: OscillatorNode[];
};

const NATURAL_NAMES = ["C", "D", "E", "F", "G", "A", "B"] as const;
const SEMITONES: Record<string, number> = {
  C: 0,
  "C#": 1,
  D: 2,
  "D#": 3,
  E: 4,
  F: 5,
  "F#": 6,
  G: 7,
  "G#": 8,
  A: 9,
  "A#": 10,
  B: 11,
};

const RIGHT_HAND_NOTES: Record<string, string> = {
  KeyN: "C",
  KeyI: "D",
  KeyO: "E",
  KeyP: "F",
  BracketLeft: "G",
  BracketRight: "A",
  Backslash: "B",
  KeyJ: "C#",
  Digit9: "D#",
  Digit0: "F#",
  Minus: "G#",
  Equal: "A#",
};

const LEFT_HAND_NOTES: Record<string, string> = {
  KeyQ: "C",
  KeyW: "D",
  KeyE: "E",
  KeyR: "F",
  Space: "G",
  KeyV: "A",
  KeyB: "B",
  Digit2: "C#",
  Digit3: "D#",
  Digit4: "F#",
  Digit5: "G#",
  KeyC: "A#",
};

const RIGHT_HAND_OCTAVES: Record<string, number> = {
  KeyA: 5,
  KeyS: 6,
  KeyD: 7,
  KeyZ: 3,
  KeyX: 2,
  KeyC: 1,
  KeyQ: 8,
  KeyW: 4,
  KeyE: 0,
};

const LEFT_HAND_OCTAVES: Record<string, number> = {
  KeyJ: 5,
  KeyK: 6,
  KeyL: 7,
  KeyN: 3,
  KeyM: 2,
  Comma: 1,
  KeyU: 8,
  KeyI: 4,
  KeyO: 0,
};

const KEY_LABELS: Record<string, string> = {
  Space: "空格",
  BracketLeft: "[",
  BracketRight: "]",
  Backslash: "\\",
  Minus: "-",
  Equal: "=",
};

const WHITE_KEYS: NoteDefinition[] = Array.from({ length: 23 }, (_, index) => {
  const naturalIndex = index % NATURAL_NAMES.length;
  return {
    name: NATURAL_NAMES[naturalIndex],
    octave: 3 + Math.floor(index / NATURAL_NAMES.length),
  };
});

const BLACK_KEYS = WHITE_KEYS.flatMap((key, index) => {
  if (index === WHITE_KEYS.length - 1 || key.name === "E" || key.name === "B") return [];
  return [{ name: `${key.name}#`, octave: key.octave, afterWhiteIndex: index }];
});

function noteId(note: NoteDefinition) {
  return `${note.name}${note.octave}`;
}

function midiNumber(note: NoteDefinition) {
  return (note.octave + 1) * 12 + SEMITONES[note.name];
}

function frequencyFor(note: NoteDefinition) {
  return 440 * Math.pow(2, (midiNumber(note) - 69) / 12);
}

function shortcutLabel(code?: string) {
  if (!code) return "";
  if (KEY_LABELS[code]) return KEY_LABELS[code];
  if (code.startsWith("Key")) return code.slice(3);
  if (code.startsWith("Digit")) return code.slice(5);
  return code;
}

export function PlayablePiano({ hand, onActivity }: PlayablePianoProps) {
  const [activeNotes, setActiveNotes] = useState<Set<string>>(() => new Set());
  const audioContextRef = useRef<AudioContext | null>(null);
  const compressorRef = useRef<DynamicsCompressorNode | null>(null);
  const voicesRef = useRef<Map<string, Voice>>(new Map());
  const heldCodesRef = useRef<Set<string>>(new Set());
  const heldOctavesRef = useRef<Set<string>>(new Set());
  const pointerSourcesRef = useRef<Map<number, string>>(new Map());

  const noteMap = hand === "右手" ? RIGHT_HAND_NOTES : LEFT_HAND_NOTES;
  const octaveMap = hand === "右手" ? RIGHT_HAND_OCTAVES : LEFT_HAND_OCTAVES;

  const shortcutByNote = useMemo(() => {
    const result = new Map<string, string>();
    Object.entries(noteMap).forEach(([code, name]) => result.set(`${name}4`, code));
    return result;
  }, [noteMap]);

  const ensureAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      const AudioContextConstructor = window.AudioContext;
      const context = new AudioContextConstructor({ latencyHint: "interactive" });
      const compressor = context.createDynamicsCompressor();
      compressor.threshold.value = -20;
      compressor.knee.value = 18;
      compressor.ratio.value = 6;
      compressor.attack.value = 0.003;
      compressor.release.value = 0.2;
      compressor.connect(context.destination);
      audioContextRef.current = context;
      compressorRef.current = compressor;
    }
    if (audioContextRef.current.state === "suspended") {
      void audioContextRef.current.resume();
    }
    return audioContextRef.current;
  }, []);

  const startNote = useCallback((note: NoteDefinition, source: string) => {
    if (voicesRef.current.has(source)) return;
    if (note.octave === 0 && !["A", "A#", "B"].includes(note.name)) return;
    if (note.octave === 8 && note.name !== "C") return;

    const context = ensureAudioContext();
    const compressor = compressorRef.current;
    if (!compressor) return;

    const gain = context.createGain();
    const filter = context.createBiquadFilter();
    const now = context.currentTime;
    const frequency = frequencyFor(note);

    filter.type = "lowpass";
    filter.frequency.setValueAtTime(Math.min(5200, 1600 + frequency * 5), now);
    filter.Q.value = 0.7;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.34, now + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.16, now + 0.42);
    gain.connect(filter);
    filter.connect(compressor);

    const harmonics = [
      { ratio: 1, type: "triangle" as OscillatorType, level: 0.72 },
      { ratio: 2, type: "sine" as OscillatorType, level: 0.19 },
      { ratio: 3, type: "sine" as OscillatorType, level: 0.09 },
    ];
    const oscillators = harmonics.map(({ ratio, type, level }) => {
      const oscillator = context.createOscillator();
      const partialGain = context.createGain();
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(frequency * ratio, now);
      partialGain.gain.value = level;
      oscillator.connect(partialGain);
      partialGain.connect(gain);
      oscillator.start(now);
      return oscillator;
    });

    voicesRef.current.set(source, { gain, oscillators });
    setActiveNotes((current) => new Set(current).add(noteId(note)));
    onActivity?.(`${hand}：${note.name}${note.octave}`);
  }, [ensureAudioContext, hand, onActivity]);

  const stopSource = useCallback((source: string) => {
    const voice = voicesRef.current.get(source);
    if (!voice) return;
    const context = audioContextRef.current;
    if (context) {
      const now = context.currentTime;
      voice.gain.gain.cancelScheduledValues(now);
      voice.gain.gain.setValueAtTime(Math.max(voice.gain.gain.value, 0.0001), now);
      voice.gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);
      voice.oscillators.forEach((oscillator) => oscillator.stop(now + 0.3));
    }
    voicesRef.current.delete(source);
    const soundingNotes = new Set<string>();
    voicesRef.current.forEach((_value, voiceSource) => {
      const encoded = voiceSource.split(":").at(-1);
      if (encoded) soundingNotes.add(encoded);
    });
    setActiveNotes(soundingNotes);
  }, []);

  const stopAll = useCallback(() => {
    [...voicesRef.current.keys()].forEach(stopSource);
    heldCodesRef.current.clear();
    heldOctavesRef.current.clear();
    pointerSourcesRef.current.clear();
    setActiveNotes(new Set());
  }, [stopSource]);

  useEffect(() => {
    function isTypingTarget(target: EventTarget | null) {
      const element = target as HTMLElement | null;
      return Boolean(element?.isContentEditable || element?.closest("input, textarea, select"));
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return;
      if (octaveMap[event.code] !== undefined) {
        heldOctavesRef.current.add(event.code);
        event.preventDefault();
        return;
      }
      const name = noteMap[event.code];
      if (!name || heldCodesRef.current.has(event.code) || event.repeat) return;
      heldCodesRef.current.add(event.code);
      const heldOctaveCode = [...heldOctavesRef.current].at(-1);
      const octave = heldOctaveCode ? octaveMap[heldOctaveCode] : 4;
      event.preventDefault();
      startNote({ name, octave }, `keyboard-${event.code}:${name}${octave}`);
    }

    function handleKeyUp(event: KeyboardEvent) {
      if (octaveMap[event.code] !== undefined) {
        heldOctavesRef.current.delete(event.code);
        return;
      }
      if (!heldCodesRef.current.delete(event.code)) return;
      const prefix = `keyboard-${event.code}:`;
      const source = [...voicesRef.current.keys()].find((candidate) => candidate.startsWith(prefix));
      if (source) stopSource(source);
      event.preventDefault();
    }

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", stopAll);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", stopAll);
      stopAll();
      void audioContextRef.current?.close();
      audioContextRef.current = null;
    };
  }, [noteMap, octaveMap, startNote, stopAll, stopSource]);

  function pointerDown(event: React.PointerEvent<HTMLButtonElement>, note: NoteDefinition) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const source = `pointer-${event.pointerId}:${noteId(note)}`;
    pointerSourcesRef.current.set(event.pointerId, source);
    startNote(note, source);
  }

  function pointerUp(event: React.PointerEvent<HTMLButtonElement>) {
    const source = pointerSourcesRef.current.get(event.pointerId);
    if (!source) return;
    pointerSourcesRef.current.delete(event.pointerId);
    stopSource(source);
  }

  return (
    <div className="playable-piano" aria-label={`${hand}钢琴键盘`}>
      <p className="keyboard-shortcut-hint" aria-live="polite">
        <span>{hand}快捷键</span>
        {hand === "右手" ? "N I O P [ ] \\ · 黑键 J 9 0 - =" : "Q W E R 空格 V B · 黑键 2 3 4 5 C"}
      </p>
      <div className="keyboard-surface">
        <img src="/assets/reference-keyboard.png" alt="" aria-hidden="true" draggable={false} />
        {WHITE_KEYS.map((note, index) => {
          const id = noteId(note);
          const shortcut = shortcutByNote.get(id);
          return (
            <button
              type="button"
              key={id}
              className={`piano-hit white-hit${activeNotes.has(id) ? " active" : ""}`}
              style={{ left: `${(index / WHITE_KEYS.length) * 100}%`, width: `${100 / WHITE_KEYS.length}%` }}
              aria-label={`${note.name}${note.octave}${shortcut ? `，快捷键 ${shortcutLabel(shortcut)}` : ""}`}
              data-note={id}
              data-active={activeNotes.has(id) ? "true" : "false"}
              onPointerDown={(event) => pointerDown(event, note)}
              onPointerUp={pointerUp}
              onPointerCancel={pointerUp}
              onContextMenu={(event) => event.preventDefault()}
            >
              {shortcut ? <span>{shortcutLabel(shortcut)}</span> : null}
            </button>
          );
        })}
        {BLACK_KEYS.map((note) => {
          const id = noteId(note);
          const shortcut = shortcutByNote.get(id);
          return (
            <button
              type="button"
              key={id}
              className={`piano-hit black-hit${activeNotes.has(id) ? " active" : ""}`}
              style={{ left: `${((note.afterWhiteIndex + 0.72) / WHITE_KEYS.length) * 100}%`, width: `${0.56 * (100 / WHITE_KEYS.length)}%` }}
              aria-label={`${note.name}${note.octave}${shortcut ? `，快捷键 ${shortcutLabel(shortcut)}` : ""}`}
              data-note={id}
              data-active={activeNotes.has(id) ? "true" : "false"}
              onPointerDown={(event) => pointerDown(event, note)}
              onPointerUp={pointerUp}
              onPointerCancel={pointerUp}
              onContextMenu={(event) => event.preventDefault()}
            >
              {shortcut ? <span>{shortcutLabel(shortcut)}</span> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
