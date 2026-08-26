/**
 * A chart sized from a measured container, not from `ResponsiveContainer`.
 *
 * Recharts' own responsive wrapper learns its width through a
 * `ResizeObserver`. Where that does not deliver — and it does not in every
 * environment; this was found in one where it never fires at all — the
 * container stays at zero width and the chart renders **nothing at all**. No
 * error, no empty state, no axis: a card with a caption and a blank rectangle
 * under it, which reads as "there is no data" rather than "the chart did not
 * draw".
 *
 * That failure mode is unacceptable in a tool whose charts are the deliverable,
 * so the width is measured directly, in a layout effect after render and on
 * window resize. Those are the only two things that change it — the chart's
 * column has no independently-sized content — and the mechanism works
 * everywhere.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

/** Below this the axes and legend have no room; better to say so than to draw
 *  an unreadable chart. */
const MIN_USABLE_WIDTH = 220;

export function ChartFrame({
  height,
  children,
  className = "chart",
}: {
  height: number;
  /** Given the measured width, so the chart can be sized explicitly. */
  children: (width: number) => ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  const measure = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    const next = Math.floor(element.getBoundingClientRect().width);
    // Only on a real change: this runs after every render, and writing state
    // unconditionally would render again forever.
    setWidth((current) => (current === next ? current : next));
  }, []);

  useLayoutEffect(measure);

  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  return (
    <div className={className} ref={ref} style={{ minHeight: height }}>
      {width >= MIN_USABLE_WIDTH ? children(width) : null}
    </div>
  );
}
