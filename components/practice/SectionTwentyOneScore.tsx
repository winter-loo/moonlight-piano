import {
  duolingoSectionTwentyOneEvents,
  duolingoSectionTwentyOneMeasureCount,
} from "@/lib/music/content/duolingo-section-21";
import { layoutSectionTwentyOneScore } from "@/lib/music/section-21-score-layout";

const score = layoutSectionTwentyOneScore({
  events: duolingoSectionTwentyOneEvents,
  measureCount: duolingoSectionTwentyOneMeasureCount,
});

export function SectionTwentyOneScore() {
  return (
    <section
      className="section21-score"
      aria-label={`产品文档第 21 章完整五线谱，共 ${score.measureCount} 小节、${score.noteCount} 个音符、${score.restCount} 个休止符`}
      data-source-section="21.3"
    >
      {score.systems.map((system) => (
        <svg
          key={system.id}
          className="section21-system"
          viewBox={`0 0 ${system.width} ${system.height}`}
          role="img"
          aria-labelledby={`${system.id}-title`}
        >
          <title id={`${system.id}-title`}>{`第 ${system.firstMeasure}–${system.lastMeasure} 小节`}</title>

          <g className="section21-lines" aria-hidden="true">
            {system.staffLines.map((line) => (
              <line key={line.id} x1={line.x1} y1={line.y} x2={line.x2} y2={line.y} />
            ))}
            {system.barlines.map((barline) => (
              <line
                key={barline.id}
                className="section21-barline"
                x1={barline.x}
                y1={barline.y1}
                x2={barline.x}
                y2={barline.y2}
              />
            ))}
            {system.ledgerLines.map((line) => (
              <line
                key={line.id}
                className="section21-ledger"
                data-event-id={line.eventId}
                x1={line.x1}
                y1={line.y}
                x2={line.x2}
                y2={line.y}
              />
            ))}
          </g>

          <g className="section21-measure-labels" aria-hidden="true">
            {system.measureLabels.map((label) => (
              <text key={label.measure} x={label.x} y={label.y}>{label.measure}</text>
            ))}
          </g>

          <g className="section21-glyphs" aria-hidden="true">
            {system.glyphs.map((glyph) => (
              <text
                key={glyph.id}
                className={`section21-glyph section21-glyph--${glyph.kind} section21-glyph--${glyph.font}`}
                data-event-id={glyph.eventId}
                data-measure={glyph.measure}
                data-duration={glyph.durationBeats}
                x={glyph.x}
                y={glyph.y}
                textAnchor="middle"
                style={{ fontSize: glyph.fontSize }}
              >
                {glyph.text}
              </text>
            ))}
          </g>

          <g className="section21-dots" aria-hidden="true">
            {system.dots.map((dot) => (
              <circle key={dot.id} data-event-id={dot.eventId} cx={dot.cx} cy={dot.cy} r={dot.r} />
            ))}
          </g>
        </svg>
      ))}
    </section>
  );
}
