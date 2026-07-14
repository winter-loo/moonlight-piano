import type { RhythmTarget } from "@/lib/engine/rhythm-evaluator";

type RhythmLaneProps = {
  targets: RhythmTarget[];
  currentBeat: number;
  matchedIds?: ReadonlySet<string>;
  showBlocks?: boolean;
};

const VIEWBOX_WIDTH = 1000;
const JUDGMENT_X = 270;
const BEAT_WIDTH = 142;

export function RhythmLane({ targets, currentBeat, matchedIds = new Set(), showBlocks = true }: RhythmLaneProps) {
  return (
    <div className="rhythm-lane" aria-label="从右向左移动的节奏轨道">
      <svg viewBox={`0 0 ${VIEWBOX_WIDTH} 220`} role="img" aria-label="节奏色块接近固定判定线">
        <defs>
          <linearGradient id="moon-block" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#c782ff" />
            <stop offset="1" stopColor="#8d5cff" />
          </linearGradient>
          <filter id="judgment-glow" x="-100%" y="-30%" width="300%" height="160%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <g className="lane-lines" aria-hidden="true">
          <line x1="0" y1="76" x2={VIEWBOX_WIDTH} y2="76" />
          <line x1="0" y1="144" x2={VIEWBOX_WIDTH} y2="144" />
        </g>
        {showBlocks ? targets.map((target) => {
          const x = JUDGMENT_X + (target.beat - currentBeat) * BEAT_WIDTH;
          if (x < -180 || x > VIEWBOX_WIDTH + 80) return null;
          const matched = matchedIds.has(target.id);
          const missed = !matched && currentBeat - target.beat > 0.38;
          return (
            <rect
              key={target.id}
              className={`rhythm-block${matched ? " matched" : ""}${missed ? " missed" : ""}`}
              x={x}
              y="92"
              width={Math.max(34, target.durationBeats * BEAT_WIDTH - 10)}
              height="38"
              rx="12"
              fill="url(#moon-block)"
            />
          );
        }) : null}
        <line className="judgment-line" x1={JUDGMENT_X} y1="32" x2={JUDGMENT_X} y2="188" filter="url(#judgment-glow)" />
        <circle className="judgment-dot" cx={JUDGMENT_X} cy="111" r="8" />
      </svg>
    </div>
  );
}
