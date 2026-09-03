import { layoutPracticeLaneStaff, layoutTrebleStaff } from "@/lib/music/score-layout";
import type { ScoreEvent } from "@/lib/music/schema";

type StaffScoreProps = {
  events: readonly ScoreEvent[];
  measure: number;
  variant?: "engraved" | "practice-lane";
};

export function StaffScore({ events, measure, variant = "engraved" }: StaffScoreProps) {
  const layout = variant === "practice-lane" ? layoutPracticeLaneStaff : layoutTrebleStaff;
  const scene = layout({
    events,
    measure,
    clef: "treble",
    timeSignature: { beats: 3, beatType: 4 },
    staffSpace: variant === "practice-lane" ? 38 : 20,
    width: variant === "practice-lane" ? 1612 : 1000,
  });
  const noteSummary = scene.notes.map((note) => note.spelling.replace("b", "♭")).join("、");

  return (
    <div className={`staff-score staff-score--${variant}`}>
      <svg
        viewBox={`0 0 ${scene.width} ${scene.height}`}
        role="img"
        aria-labelledby={`staff-score-${measure}-title staff-score-${measure}-description`}
      >
        <title id={`staff-score-${measure}-title`}>{`第 ${measure} 小节高音谱表`}</title>
        <desc id={`staff-score-${measure}-description`}>{`3/4 拍，右手音符依次为 ${noteSummary}`}</desc>

        {variant === "practice-lane" ? (
          <rect className="staff-score-judgment" x="342" y="88" width="19" height="272" rx="10" aria-hidden="true" />
        ) : null}

        <g className="staff-score-lines" aria-hidden="true">
          {scene.staffLines.map((line) => (
            <line key={line.y} x1={line.x1} y1={line.y} x2={line.x2} y2={line.y} />
          ))}
          {scene.barlines.map((barline) => (
            <line
              key={barline.x}
              className="staff-score-barline"
              x1={barline.x}
              y1={barline.y1}
              x2={barline.x}
              y2={barline.y2}
            />
          ))}
          {scene.ledgerLines.map((line) => (
            <line key={line.id} className="staff-score-ledger" x1={line.x1} y1={line.y} x2={line.x2} y2={line.y} />
          ))}
        </g>

        {scene.measureLabel.text ? (
          <text className="staff-score-measure" x={scene.measureLabel.x} y={scene.measureLabel.y} aria-hidden="true">
            {scene.measureLabel.text}
          </text>
        ) : null}

        <g className="staff-score-stems" aria-hidden="true">
          {scene.stems.map((stem) => (
            <line
              key={stem.eventId}
              data-event-id={stem.eventId}
              x1={stem.x}
              y1={stem.y1}
              x2={stem.x}
              y2={stem.y2}
              strokeWidth={stem.thickness}
            />
          ))}
        </g>

        <g className="staff-score-beams" aria-hidden="true">
          {scene.beams.map((beam) => (
            <polygon
              key={beam.id}
              data-event-ids={beam.eventIds.join(" ")}
              points={`${beam.x1},${beam.y1} ${beam.x2},${beam.y2} ${beam.x2},${beam.y2 + beam.thickness} ${beam.x1},${beam.y1 + beam.thickness}`}
            />
          ))}
        </g>

        <g className="staff-score-glyphs" aria-hidden="true">
          {scene.glyphs.map((glyph) => (
            <text
              key={glyph.id}
              className={`staff-score-glyph staff-score-glyph--${glyph.kind}`}
              data-event-id={glyph.eventId}
              x={glyph.x}
              y={glyph.y}
              textAnchor={glyph.anchor}
              style={{ fontSize: glyph.fontSize }}
            >
              {glyph.text}
            </text>
          ))}
        </g>

        {variant === "practice-lane" ? (
          <g className="staff-score-note-highlights" aria-hidden="true">
            {scene.notes.map((note) => (
              <circle
                key={`${note.eventId}-highlight`}
                cx={note.x - scene.staffSpace * 0.2}
                cy={note.y - scene.staffSpace * 0.18}
                r={scene.staffSpace * 0.17}
              />
            ))}
          </g>
        ) : null}
      </svg>
    </div>
  );
}
