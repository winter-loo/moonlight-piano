import type { RhythmTarget } from "@/lib/engine/rhythm-evaluator";

export type StaffRhythmTarget = RhythmTarget & {
  midi: number;
  label: string;
};

type RhythmLaneProps = {
  targets: StaffRhythmTarget[];
  currentBeat: number;
  matchedIds?: ReadonlySet<string>;
  showBlocks?: boolean;
};

const VIEWBOX_WIDTH = 1000;
const JUDGMENT_X = 244;
const BEAT_WIDTH = 142;

const NOTE_COLORS: Record<string, string> = {
  C: "#c77cff",
  D: "#f0a31f",
  E: "#61cf3b",
  F: "#d93a9a",
  G: "#6b8df4",
  A: "#ee78c8",
  B: "#21bfa9",
};

const STAFF_Y_BY_MIDI: Record<number, number> = {
  60: 170,
  61: 170,
  62: 160,
  63: 160,
  64: 140,
  65: 130,
  66: 130,
  67: 120,
  68: 120,
  69: 110,
  70: 100,
  71: 100,
  72: 90,
  73: 90,
  74: 80,
  75: 80,
  76: 70,
};

function colorFor(label: string) {
  return NOTE_COLORS[label[0]] ?? "#ee78c8";
}

export function RhythmLane({ targets, currentBeat, matchedIds = new Set(), showBlocks = true }: RhythmLaneProps) {
  return (
    <div className="rhythm-lane" aria-label="带五线谱的节奏轨道，色块从右向左移动">
      <svg viewBox={`0 0 ${VIEWBOX_WIDTH} 220`} role="img" aria-label="色块沿五线谱接近固定判定线">
        <g className="staff-lines" aria-hidden="true">
          {[60, 80, 100, 120, 140].map((y) => <line key={y} x1="42" y1={y} x2={VIEWBOX_WIDTH} y2={y} />)}
          <line className="staff-barline" x1="610" y1="60" x2="610" y2="140" />
          <line className="staff-barline" x1="900" y1="60" x2="900" y2="140" />
        </g>
        <text className="staff-clef" x="68" y="143" aria-hidden="true">&#xE050;</text>
        <text className="staff-accidental" x="137" y="112" aria-hidden="true">&#xE260;</text>

        {showBlocks ? targets.map((target) => {
          const x = JUDGMENT_X + (target.beat - currentBeat) * BEAT_WIDTH;
          if (x < -180 || x > VIEWBOX_WIDTH + 80) return null;
          const matched = matchedIds.has(target.id);
          const missed = !matched && currentBeat - target.beat > 0.38;
          const width = Math.max(42, target.durationBeats * BEAT_WIDTH - 10);
          const y = (STAFF_Y_BY_MIDI[target.midi] ?? 110) - 13;
          const fill = colorFor(target.label);
          return (
            <g key={target.id} className={`rhythm-block${matched ? " matched" : ""}${missed ? " missed" : ""}`}>
              <rect x={x} y={y} width={width} height="27" rx="6" fill={fill} />
              <text x={x + 12} y={y + 19}>{target.label}</text>
            </g>
          );
        }) : null}

        <line className="judgment-line" x1={JUDGMENT_X} y1="35" x2={JUDGMENT_X} y2="177" />
        <circle className="judgment-dot" cx={JUDGMENT_X} cy="181" r="7" />
      </svg>
    </div>
  );
}
