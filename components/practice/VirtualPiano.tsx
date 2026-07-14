"use client";

import { useCallback, useEffect, useMemo } from "react";

type PianoKey = {
  midi: number;
  label: string;
  shortcut: string;
  black?: boolean;
  afterWhite?: number;
};

type VirtualPianoProps = {
  activeMidi: number | null;
  wrongMidi?: number | null;
  hintMidi?: number | null;
  disabled?: boolean;
  onNote: (midi: number) => void;
};

const WHITE_KEYS: PianoKey[] = [
  { midi: 60, label: "C", shortcut: "A" },
  { midi: 62, label: "D", shortcut: "S" },
  { midi: 64, label: "E", shortcut: "D" },
  { midi: 65, label: "F", shortcut: "F" },
  { midi: 67, label: "G", shortcut: "G" },
  { midi: 69, label: "A", shortcut: "H" },
  { midi: 71, label: "B", shortcut: "J" },
  { midi: 72, label: "C", shortcut: "K" },
  { midi: 74, label: "D", shortcut: "L" },
  { midi: 76, label: "E", shortcut: ";" },
];

const BLACK_KEYS: PianoKey[] = [
  { midi: 61, label: "C♯", shortcut: "W", black: true, afterWhite: 0 },
  { midi: 63, label: "D♯", shortcut: "E", black: true, afterWhite: 1 },
  { midi: 66, label: "F♯", shortcut: "T", black: true, afterWhite: 3 },
  { midi: 68, label: "G♯", shortcut: "Y", black: true, afterWhite: 4 },
  { midi: 70, label: "B♭", shortcut: "U", black: true, afterWhite: 5 },
  { midi: 73, label: "C♯", shortcut: "O", black: true, afterWhite: 7 },
  { midi: 75, label: "D♯", shortcut: "P", black: true, afterWhite: 8 },
];

const NOTE_COLORS = ["#f47e86", "#e99b42", "#72b660", "#27bf99", "#7f9df4", "#ba7add", "#dd7fb3"];

export function VirtualPiano({ activeMidi, wrongMidi = null, hintMidi = null, disabled = false, onNote }: VirtualPianoProps) {
  const keys = useMemo(() => [...WHITE_KEYS, ...BLACK_KEYS], []);
  const shortcutMap = useMemo(() => new Map(keys.map((key) => [key.shortcut, key.midi])), [keys]);

  const trigger = useCallback((midi: number) => {
    if (!disabled) onNote(midi);
  }, [disabled, onNote]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("button, a, input, textarea, select")) return;
      const midi = shortcutMap.get(event.key.toUpperCase());
      if (midi === undefined) return;
      event.preventDefault();
      trigger(midi);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [shortcutMap, trigger]);

  const stateClass = (midi: number) => [
    activeMidi === midi ? "is-active" : "",
    wrongMidi === midi ? "is-wrong" : "",
    hintMidi === midi ? "is-hint" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className="echo-piano" aria-label="可弹奏的虚拟钢琴，覆盖 C4 到 E5">
      <div className="echo-white-keys">
        {WHITE_KEYS.map((key, index) => (
          <button
            type="button"
            key={key.midi}
            className={`echo-key echo-white-key ${stateClass(key.midi)}`}
            onPointerDown={(event) => { event.preventDefault(); trigger(key.midi); }}
            aria-label={`${key.label}，电脑键盘 ${key.shortcut}`}
            disabled={disabled}
          >
            <span style={{ color: NOTE_COLORS[index % NOTE_COLORS.length] }}>{key.label}</span>
            <small>{key.shortcut}</small>
          </button>
        ))}
      </div>
      <div className="echo-black-keys" aria-hidden="false">
        {BLACK_KEYS.map((key) => (
          <button
            type="button"
            key={key.midi}
            className={`echo-key echo-black-key ${stateClass(key.midi)}`}
            style={{ left: `calc(${((key.afterWhite ?? 0) + 1) * 10}% - 4.1%)` }}
            onPointerDown={(event) => { event.preventDefault(); trigger(key.midi); }}
            aria-label={`${key.label}，电脑键盘 ${key.shortcut}`}
            disabled={disabled}
          >
            <span>{key.label}</span>
            <small>{key.shortcut}</small>
          </button>
        ))}
      </div>
    </div>
  );
}
