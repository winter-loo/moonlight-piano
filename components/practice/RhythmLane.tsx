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
  showTimeSignature?: boolean;
};

const VIEWBOX_WIDTH = 1000;
const JUDGMENT_X = 286;
const BEAT_WIDTH = 132;

const NOTE_COLORS: Record<string, string> = {
  C: "#cb68f2",
  D: "#ff9d18",
  E: "#6dda3c",
  F: "#dd168d",
  G: "#7f96ff",
  A: "#f064b9",
  B: "#2bd8a5",
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

function displayLabel(label: string) {
  return label.replace("b", "♭").replace("#", "♯");
}

export function RhythmLane({ targets, currentBeat, matchedIds = new Set(), showBlocks = true, showTimeSignature = false }: RhythmLaneProps) {
  return (
    <div className="rhythm-lane" aria-label="带五线谱的节奏轨道，色块从右向左移动">
      <svg viewBox={`0 0 ${VIEWBOX_WIDTH} 230`} role="img" aria-label="色块沿五线谱接近固定判定线">
        <g className="staff-lines" aria-hidden="true">
          {[60, 80, 100, 120, 140].map((y) => <line key={y} x1="38" y1={y} x2={VIEWBOX_WIDTH} y2={y} />)}
          <line className="staff-barline" x1="585" y1="60" x2="585" y2="140" />
          <line className="staff-barline" x1="900" y1="60" x2="900" y2="140" />
        </g>
        <text className="staff-clef" x="58" y="145" aria-hidden="true">&#xE050;</text>
        <text className="staff-accidental" x="137" y="108" aria-hidden="true">&#xE260;</text>
        {showTimeSignature ? (
          <g className="staff-time-signature" aria-hidden="true">
            <text x="188" y="80" textAnchor="middle">{"\uE083"}</text>
            <text x="188" y="120" textAnchor="middle">{"\uE084"}</text>
          </g>
        ) : null}

        {showBlocks ? targets.map((target) => {
          const x = JUDGMENT_X + (target.beat - currentBeat) * BEAT_WIDTH;
          if (x < -180 || x > VIEWBOX_WIDTH + 80) return null;
          const matched = matchedIds.has(target.id);
          const missed = !matched && currentBeat - target.beat > 0.38;
          const width = Math.max(38, target.durationBeats * BEAT_WIDTH - 10);
          const y = (STAFF_Y_BY_MIDI[target.midi] ?? 110) - 13;
          const fill = colorFor(target.label);
          const nearJudgment = matched && Math.abs(currentBeat - target.beat) < 0.42;
          return (
            <g key={target.id} className={`rhythm-block${matched ? " matched" : ""}${missed ? " missed" : ""}`}>
              <rect x={x} y={y} width={width} height="27" rx="6" fill={fill} />
              <rect className="block-shine" x={x + 12} y={y + 5} width={Math.max(15, width - 27)} height="5" rx="3" />
              <text x={x + 11} y={y + 20}>{displayLabel(target.label)}</text>
              {nearJudgment ? (
                <g className="hit-fragments" style={{ color: fill }} aria-hidden="true">
                  <circle cx={JUDGMENT_X - 10} cy={y - 8} r="3" />
                  <rect x={JUDGMENT_X + 8} y={y - 14} width="6" height="6" rx="2" />
                  <circle cx={JUDGMENT_X + 17} cy={y + 37} r="2.5" />
                </g>
              ) : null}
            </g>
          );
        }) : null}

        <line className="judgment-line" x1={JUDGMENT_X} y1="20" x2={JUDGMENT_X} y2="184" />
      </svg>
    </div>
  );
}
