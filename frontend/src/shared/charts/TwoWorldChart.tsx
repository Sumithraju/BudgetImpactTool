/**
 * The two worlds a budget impact is the difference of.
 *
 * Non-negotiable 2 says budget impact is incremental — world-with minus
 * world-without, never the gross cost of the new therapy. This chart is that
 * sentence drawn: two bars per year and the gap between them, so a reader
 * sees what the increment is an increment *over* rather than being asked to
 * trust a single number.
 *
 * Palette is validated, not chosen by eye. Light `#a85a28`/`#0097a7` on
 * `#ffffff` and dark `#c87a35`/`#1fa8b5` on `#131f23` both clear the
 * lightness band, chroma floor, CVD separation, normal-vision floor and
 * contrast checks. Dark is its own pair of steps, not a flip of the light
 * one. Identity never rests on colour alone: both series are direct-labelled
 * and a table carries the same numbers.
 */
import { useId, useState } from "react";
import { formatMoney, formatMoneyCompact } from "../format";

export interface TwoWorldSeries {
  /** Launch-relative year. Calendar year is derived for display only. */
  year: number;
  calendarYear: number;
  without: number;
  with: number;
  difference: number;
}

interface TwoWorldChartProps {
  series: TwoWorldSeries[];
  currency: string;
  /** Names the two worlds in the reader's terms, not the model's. */
  withoutLabel?: string;
  withLabel?: string;
}

const HEIGHT = 260;
const PAD = { top: 26, right: 12, bottom: 46, left: 58 };
const BAR_GAP = 2;          // surface gap between adjacent fills
const GROUP_GAP = 26;
const RADIUS = 4;           // rounded data-end, anchored to the baseline
const TICKS = 4;

/** Top corners rounded, bottom square: the bar is anchored to the baseline,
 *  not floating above it. A fully rounded rect reads as a detached pill and
 *  makes a short bar look like it starts above zero. */
function barPath(x: number, y: number, w: number, h: number): string {
  if (h <= 0) return "";
  const r = Math.min(RADIUS, h, w / 2);
  return [
    `M${x},${y + h}`,
    `L${x},${y + r}`,
    `Q${x},${y} ${x + r},${y}`,
    `L${x + w - r},${y}`,
    `Q${x + w},${y} ${x + w},${y + r}`,
    `L${x + w},${y + h}`,
    "Z",
  ].join(" ");
}

export function TwoWorldChart({
  series,
  currency,
  withoutLabel = "Without the intervention",
  withLabel = "With the intervention",
}: TwoWorldChartProps) {
  const titleId = useId();
  const [hover, setHover] = useState<{ index: number; world: "without" | "with" } | null>(null);

  if (series.length === 0) {
    return (
      <p className="note">
        This run predates the two-world totals. Re-run the scenario and the comparison appears.
      </p>
    );
  }

  const width = 720;
  const plotWidth = width - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;

  const peak = Math.max(...series.flatMap((s) => [s.without, s.with]), 0);
  // A zero-height plot would divide by zero; an all-zero horizon is legal.
  const scale = (value: number) => (peak > 0 ? (value / peak) * plotHeight : 0);

  const groupWidth = (plotWidth - GROUP_GAP * (series.length - 1)) / series.length;
  const barWidth = (groupWidth - BAR_GAP) / 2;

  const hovered = hover ? series[hover.index] : null;
  const hoveredValue = hovered
    ? hover?.world === "with" ? hovered.with : hovered.without
    : null;

  return (
    <figure className="twoworld">
      <figcaption id={titleId} className="eyebrow">
        What the payer spends, with and without
      </figcaption>

      <div className="twoworld-legend">
        <span><i className="swatch swatch-without" aria-hidden="true" />{withoutLabel}</span>
        <span><i className="swatch swatch-with" aria-hidden="true" />{withLabel}</span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        className="twoworld-svg"
        role="img"
        aria-labelledby={titleId}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* recessive gridlines, behind the marks */}
        {Array.from({ length: TICKS + 1 }, (_, i) => {
          const y = PAD.top + (plotHeight / TICKS) * i;
          return (
            <g key={i}>
              <line
                x1={PAD.left} x2={width - PAD.right} y1={y} y2={y}
                className="twoworld-grid"
              />
              {/* An unlabelled gridline is decoration. */}
              <text
                x={PAD.left - 8} y={y + 3} textAnchor="end"
                className="twoworld-axis twoworld-axis-dim"
              >
                {formatMoneyCompact(peak * (1 - i / TICKS), currency)}
              </text>
            </g>
          );
        })}

        {series.map((point, index) => {
          const groupX = PAD.left + index * (groupWidth + GROUP_GAP);
          const baseline = PAD.top + plotHeight;

          const bars = [
            { world: "without" as const, x: groupX, value: point.without, cls: "bar-without" },
            { world: "with" as const, x: groupX + barWidth + BAR_GAP, value: point.with, cls: "bar-with" },
          ];

          return (
            <g key={point.year}>
              {bars.map((bar) => {
                const barHeight = scale(bar.value);
                const isHovered = hover?.index === index && hover.world === bar.world;
                return (
                  <g key={bar.world}>
                    <path
                      d={barPath(bar.x, baseline - barHeight, barWidth, barHeight)}
                      className={`twoworld-bar ${bar.cls}${isHovered ? " is-hovered" : ""}`}
                    />
                    {/* Hit target spans the full plot height, so a short bar
                        is still reachable with a mouse. */}
                    <rect
                      x={bar.x} y={PAD.top} width={barWidth} height={plotHeight}
                      fill="transparent"
                      onMouseEnter={() => setHover({ index, world: bar.world })}
                      onMouseLeave={() => setHover(null)}
                    />
                  </g>
                );
              })}

              <text
                x={groupX + groupWidth / 2}
                y={baseline + 18}
                textAnchor="middle"
                className="twoworld-axis"
              >
                Y{point.year}
              </text>
              <text
                x={groupX + groupWidth / 2}
                y={baseline + 32}
                textAnchor="middle"
                className="twoworld-axis twoworld-axis-dim"
              >
                {point.calendarYear}
              </text>

              {/* The increment, labelled where it is: the gap between the two. */}
              <text
                x={groupX + groupWidth / 2}
                y={baseline - scale(Math.max(point.without, point.with)) - 8}
                textAnchor="middle"
                className="twoworld-delta"
              >
                {point.difference >= 0 ? "+" : "−"}
                {formatMoneyCompact(Math.abs(point.difference), currency)}
              </text>
            </g>
          );
        })}
      </svg>

      {hovered && hoveredValue !== null && (
        <div className="twoworld-tip" role="status">
          <strong>
            Y{hovered.year} · {hovered.calendarYear}
          </strong>
          <span>
            {hover?.world === "with" ? withLabel : withoutLabel}:{" "}
            {formatMoney(hoveredValue, currency)}
          </span>
          <span className="dim">
            Difference {formatMoney(hovered.difference, currency)}
          </span>
        </div>
      )}

      {/* Same numbers, reachable without seeing the chart. */}
      <details className="twoworld-table">
        <summary>Show these figures as a table</summary>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>{withoutLabel}</th>
                <th>{withLabel}</th>
                <th>Difference</th>
              </tr>
            </thead>
            <tbody>
              {series.map((point) => (
                <tr key={point.year}>
                  <td>Y{point.year} ({point.calendarYear})</td>
                  <td className="num">{formatMoney(point.without, currency)}</td>
                  <td className="num">{formatMoney(point.with, currency)}</td>
                  <td className="num"><strong>{formatMoney(point.difference, currency)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
