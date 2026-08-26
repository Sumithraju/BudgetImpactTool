/**
 * The chart vocabulary the result tabs are drawn from.
 *
 * The centrepiece is the two-world comparison: total cost of care as it
 * stands, against total cost with the new therapy in it, year by year — with
 * the difference charted separately, because the difference *is* the budget
 * impact and the two totals are only there to show where it comes from.
 *
 * Three decisions worth stating:
 *
 * **The two bars are nearly the same height, and that is the finding.** Budget
 * impact is a small number found between two large ones. A chart that zoomed
 * its axis to make the gap look dramatic would misrepresent the scale of the
 * decision, so the gap is annotated rather than exaggerated.
 *
 * **The incremental figure gets its own chart, not a third bar.** It is one to
 * two orders of magnitude smaller than the totals; beside them it would be an
 * invisible sliver, and on a secondary axis it would invite exactly the
 * comparison that two axes make invalid.
 *
 * **Nothing animates, and nothing is sized by `ResponsiveContainer`.** Both
 * default behaviours fail the same way — the chart renders empty, with no
 * error and no empty state, which a reader takes as "no data" rather than
 * "did not draw". See `ChartFrame` for the width half of that.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame } from "../../shared/ChartFrame";
import { formatMoneyCompact } from "../../shared/format";

const WITHOUT = "var(--series-1)";
const WITH = "var(--series-2)";
const IMPACT = "var(--series-3)";

const AXIS_TICK = { fontSize: 11, fill: "var(--ink-3)" } as const;
const CATEGORY_TICK = { fontSize: 11.5, fill: "var(--ink-2)" } as const;
const LEGEND_STYLE = { fontSize: 12, paddingTop: 8 } as const;
const MARGIN = { top: 8, right: 8, left: 8, bottom: 4 } as const;
const HORIZONTAL_MARGIN = { top: 4, right: 16, left: 8, bottom: 4 } as const;

/**
 * Recharts' default tooltip paints a hard-coded white panel with hard-coded
 * dark text, neither of which is a theme token. In dark mode that lands as a
 * white card whose own label is nearly invisible against it — and the tooltip
 * is how a reader reads an individual bar, so it is the first thing they hit.
 * Every chart therefore passes the theme through explicitly.
 */
const TOOLTIP_STYLE = {
  contentStyle: {
    background: "var(--surface)",
    border: "1px solid var(--line-2)",
    borderRadius: "8px",
    fontSize: 12,
    padding: "8px 11px",
  },
  labelStyle: { color: "var(--ink)", fontWeight: 600, marginBottom: 4 },
  itemStyle: { color: "var(--ink-2)" },
} as const;

function axisMoney(currency: string) {
  return (value: number) => formatMoneyCompact(value, currency);
}

/** Recharts' default tooltip cannot format money with a currency, and a bare
 *  number in a panel that mixes currencies and counts is exactly how a reader
 *  ends up quoting the wrong figure. */
function MoneyTooltip({
  active,
  payload,
  label,
  currency,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string }[];
  label?: string;
  currency: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rc-tip">
      <b>{label}</b>
      {payload.map((entry, index) => (
        <span key={index}>
          <i style={{ background: entry.color }} />
          {entry.name}
          <em>{formatMoneyCompact(entry.value ?? 0, currency)}</em>
        </span>
      ))}
    </div>
  );
}

const COMPARISON_HEIGHT = 300;

export function WithWithoutChart({
  launchYear,
  without,
  withNew,
  currency,
}: {
  launchYear: number;
  without: number[];
  withNew: number[];
  currency: string;
}) {
  const data = without.map((value, index) => ({
    name: `Y${index + 1} · ${launchYear + index}`,
    without: value,
    with: withNew[index] ?? 0,
  }));

  return (
    <ChartFrame height={COMPARISON_HEIGHT}>
      {(width) => (
        <BarChart
          width={width}
          height={COMPARISON_HEIGHT}
          data={data}
          margin={MARGIN}
        >
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis
            dataKey="name"
            tick={AXIS_TICK}
            axisLine={{ stroke: "var(--line-2)" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={axisMoney(currency)}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={64}
          />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            content={<MoneyTooltip currency={currency} />}
          />
          <Legend wrapperStyle={LEGEND_STYLE} iconType="square" iconSize={9} />
          <Bar
            isAnimationActive={false}
            dataKey="without"
            name="Without intervention"
            fill={WITHOUT}
            radius={[2, 2, 0, 0]}
            maxBarSize={54}
          />
          <Bar
            isAnimationActive={false}
            dataKey="with"
            name="With intervention"
            fill={WITH}
            radius={[2, 2, 0, 0]}
            maxBarSize={54}
          />
        </BarChart>
      )}
    </ChartFrame>
  );
}

const IMPACT_HEIGHT = 280;

export function ImpactChart({
  launchYear,
  impact,
  cumulative,
  currency,
  peakYear,
}: {
  launchYear: number;
  impact: number[];
  cumulative: number;
  currency: string;
  peakYear: number;
}) {
  let running = 0;
  const data = impact.map((value, index) => {
    running += value;
    return {
      name: `Y${index + 1} · ${launchYear + index}`,
      impact: value,
      cumulative: running,
      peak: index + 1 === peakYear,
    };
  });

  return (
    <>
      <ChartFrame height={IMPACT_HEIGHT}>
        {(width) => (
          <ComposedChart
            width={width}
            height={IMPACT_HEIGHT}
            data={data}
            margin={MARGIN}
          >
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="name"
              tick={AXIS_TICK}
              axisLine={{ stroke: "var(--line-2)" }}
              tickLine={false}
            />
            <YAxis
              tickFormatter={axisMoney(currency)}
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              width={64}
            />
            <Tooltip
              cursor={{ fill: "var(--surface-2)" }}
              content={<MoneyTooltip currency={currency} />}
            />
            <Legend wrapperStyle={LEGEND_STYLE} iconType="square" iconSize={9} />
            {/* Zero is drawn explicitly. A negative budget impact is a saving,
                and a chart with no zero line lets a reader miss the sign. */}
            <ReferenceLine y={0} stroke="var(--ink-3)" strokeWidth={1} />
            <Bar
              isAnimationActive={false}
              dataKey="impact"
              name="Incremental, this year"
              radius={[2, 2, 0, 0]}
              maxBarSize={60}
            >
              {data.map((row, index) => (
                <Cell
                  key={index}
                  fill={row.impact < 0 ? "var(--b-low)" : IMPACT}
                  fillOpacity={row.peak ? 1 : 0.72}
                />
              ))}
            </Bar>
            <Line
              isAnimationActive={false}
              type="monotone"
              dataKey="cumulative"
              name="Cumulative"
              stroke="var(--accent)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--accent)" }}
            />
          </ComposedChart>
        )}
      </ChartFrame>
      <p className="chart-note">
        Cumulative reaches {formatMoneyCompact(cumulative, currency)}. The peak
        single year is Y{peakYear} — the year a budget holder has to find the
        most new money, which is not usually the last one.
      </p>
    </>
  );
}

/**
 * One horizontal bar series, ranked.
 *
 * The shape three of the tabs need — events by class, cost by segment, benefit
 * by segment — where the category labels are prose rather than years and
 * therefore want the long axis.
 */
export function RankedBarChart({
  data,
  dataKey,
  name,
  fill,
  height,
  labelWidth = 180,
  tickFormatter,
  tooltipFormatter,
}: {
  data: Record<string, string | number>[];
  dataKey: string;
  name: string;
  fill: string;
  height: number;
  labelWidth?: number;
  tickFormatter?: (value: number) => string;
  tooltipFormatter?: (value: number) => string;
}) {
  return (
    <ChartFrame height={height}>
      {(width) => (
        <BarChart
          width={width}
          height={height}
          data={data}
          layout="vertical"
          margin={HORIZONTAL_MARGIN}
        >
          <CartesianGrid stroke="var(--line)" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={tickFormatter}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={labelWidth}
            tick={CATEGORY_TICK}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            formatter={tooltipFormatter}
            {...TOOLTIP_STYLE}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="square" iconSize={9} />
          <Bar
            isAnimationActive={false}
            dataKey={dataKey}
            name={name}
            fill={fill}
            radius={[0, 2, 2, 0]}
            maxBarSize={26}
          />
        </BarChart>
      )}
    </ChartFrame>
  );
}

/** One vertical bar series, for the adoption-case comparison. */
export function ColumnChart({
  data,
  dataKey,
  name,
  fill,
  height,
  currency,
}: {
  data: Record<string, string | number>[];
  dataKey: string;
  name: string;
  fill: string;
  height: number;
  currency: string;
}) {
  return (
    <ChartFrame height={height}>
      {(width) => (
        <BarChart width={width} height={height} data={data} margin={MARGIN}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis
            dataKey="name"
            tick={AXIS_TICK}
            axisLine={{ stroke: "var(--line-2)" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={axisMoney(currency)}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={64}
          />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            formatter={(value: number) => formatMoneyCompact(value, currency)}
            {...TOOLTIP_STYLE}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="square" iconSize={9} />
          <Bar
            isAnimationActive={false}
            dataKey={dataKey}
            name={name}
            fill={fill}
            radius={[2, 2, 0, 0]}
            maxBarSize={64}
          />
        </BarChart>
      )}
    </ChartFrame>
  );
}
