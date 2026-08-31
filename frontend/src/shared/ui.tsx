/**
 * The small components everything else is built from.
 *
 * `Help` is the load-bearing one. ARCHITECTURE.md Phase 15's exit criterion is
 * that "a reader who has never seen the tool can name what any figure on
 * screen means without leaving it" — which is a requirement about *every*
 * label, not about a documentation page. So the explanation lives on the field,
 * and its text comes from the API's field guide rather than from a copy kept
 * here: the same sentence appears in the import template and the exported
 * workbook, and three copies of it is three chances to disagree.
 */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { FieldGroup, FieldSpec } from "./api";
import { Icon, type IconName } from "./Icons";

/* ------------------------------------------------------------------ help */

/** Flattened `key -> spec`, so a tooltip is a lookup rather than a search. */
export type FieldIndex = Map<string, FieldSpec>;

export function indexFields(groups: FieldGroup[]): FieldIndex {
  return new Map(groups.flatMap((g) => g.fields.map((f) => [f.key, f] as const)));
}

/**
 * An explanation attached to a label.
 *
 * Opens on hover *and* on focus, and closes on Escape. Hover alone would put
 * the explanation out of reach of anyone using a keyboard or a touch screen,
 * and this is the only place several of these numbers are defined.
 */
export function Help({ spec, children }: { spec?: FieldSpec; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const timer = useRef<number>();

  // A short close delay, so moving the pointer from the trigger into the
  // panel does not dismiss it — the panel carries a range and an example
  // worth reading rather than glancing at.
  const show = useCallback(() => {
    window.clearTimeout(timer.current);
    setOpen(true);
  }, []);
  const hide = useCallback(() => {
    timer.current = window.setTimeout(() => setOpen(false), 120);
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  if (!spec) return <>{children}</>;

  return (
    <span
      className="help"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      <button
        type="button"
        className="help-dot"
        aria-label={`What ${spec.label} means`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span role="tooltip" id={id} className="help-panel">
          <b>{spec.label}</b>
          <span>{spec.description}</span>
          {spec.effect && (
            <span className="help-effect">
              <em>Why it matters</em> {spec.effect}
            </span>
          )}
          <span className="help-meta">
            {spec.unit && <i>{spec.unit}</i>}
            {spec.example && <i>e.g. {spec.example}</i>}
            {spec.typical_range && <i>typical {spec.typical_range}</i>}
          </span>
        </span>
      )}
    </span>
  );
}

/* ------------------------------------------------------------------ tabs */

export interface TabDef {
  id: string;
  label: string;
  /** A short gloss under the label. Tabs named only by a noun make a reader
   *  click through all of them to find the one they want. */
  hint?: string;
  badge?: string | number | null;
  /** Optional glyph beside the label. Decorative — the label already names
   *  the tab, so the icon is hidden from assistive technology. */
  icon?: IconName;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}) {
  const order = useMemo(() => tabs.map((t) => t.id), [tabs]);

  // Arrow-key navigation between tabs, which is what the tab pattern is
  // expected to do and what a screen-reader user will try first.
  const onKeyDown = (event: React.KeyboardEvent) => {
    const index = order.indexOf(active);
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const next =
        event.key === "ArrowRight"
          ? (index + 1) % order.length
          : (index - 1 + order.length) % order.length;
      onChange(order[next]);
    }
  };

  return (
    <div className="tabs" role="tablist" onKeyDown={onKeyDown}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          type="button"
          id={`tab-${tab.id}`}
          aria-selected={tab.id === active}
          aria-controls={`panel-${tab.id}`}
          tabIndex={tab.id === active ? 0 : -1}
          className="tab"
          onClick={() => onChange(tab.id)}
        >
          <span className="tab-label">
            {tab.icon && <Icon name={tab.icon} className="tab-icon" />}
            {tab.label}
            {tab.badge != null && tab.badge !== "" && (
              <i className="tab-badge">{tab.badge}</i>
            )}
          </span>
          {tab.hint && <span className="tab-hint">{tab.hint}</span>}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({
  id,
  active,
  children,
}: {
  id: string;
  active: string;
  children: ReactNode;
}) {
  if (id !== active) return null;
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="panel-body">
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ stats */

/**
 * A headline figure with its label and, where it has one, its caveat.
 *
 * `caveat` renders in the warning colour on the tile itself rather than as a
 * footnote elsewhere. A PMPM computed against an assumed denominator is the
 * specific case this exists for: it looks entirely plausible and is wrong by
 * whatever ratio separates the two populations.
 */
export function Stat({
  label,
  value,
  sub,
  caveat,
  tone = "neutral",
  help,
  delta,
  trend,
  icon,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  caveat?: ReactNode;
  tone?: "neutral" | "accent" | "warn" | "good";
  help?: FieldSpec;
  /** A signed change to show as a chip, as a fraction. */
  delta?: number | null;
  /** A short series to draw as a sparkline. Two points is enough. */
  trend?: number[] | null;
  icon?: ReactNode;
}) {
  return (
    <div className={`stat stat-${tone}`}>
      <div className="stat-top">
        <Help spec={help}>
          <span className="stat-label">{label}</span>
        </Help>
        {icon && <span className="stat-icon" aria-hidden>{icon}</span>}
      </div>
      <span className="stat-value mono">{value}</span>
      <div className="stat-foot">
        {sub && <span className="stat-sub">{sub}</span>}
        {delta != null && Number.isFinite(delta) && (
          <span className={`delta ${delta >= 0 ? "delta-up" : "delta-down"}`}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta * 100).toFixed(1)}%
          </span>
        )}
      </div>
      {trend && trend.length > 1 && <Sparkline values={trend} tone={tone} />}
      {caveat && <span className="stat-caveat">{caveat}</span>}
    </div>
  );
}

/**
 * A trend line small enough to sit inside a stat card.
 *
 * Deliberately unlabelled and unaxised: it shows *shape*, and a reader who
 * needs the numbers has them in the table below. Axes on something this size
 * would be unreadable and would imply a precision the mark cannot carry.
 */
export function Sparkline({
  values,
  tone = "accent",
  width = 132,
  height = 26,
}: {
  values: number[];
  tone?: "neutral" | "accent" | "warn" | "good";
  width?: number;
  height?: number;
}) {
  const low = Math.min(...values);
  const high = Math.max(...values);
  // A flat series would divide by zero and, drawn at full height, would look
  // like a trend. Flat is drawn flat, through the middle.
  const span = high - low || 1;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - ((value - low) / span) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg
      className={`spark spark-${tone}`}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
    >
      <polyline
        points={`0,${height} ${points.join(" ")} ${width},${height}`}
        className="spark-fill"
      />
      <polyline points={points.join(" ")} className="spark-line" />
    </svg>
  );
}

export function StatRow({ children }: { children: ReactNode }) {
  return <div className="statrow">{children}</div>;
}

/* ------------------------------------------------------------------ card */

export function Card({
  title,
  lede,
  actions,
  children,
  help,
}: {
  title?: string;
  lede?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  help?: FieldSpec;
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <Help spec={help}>{title && <h3>{title}</h3>}</Help>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {/* Explanatory, so opt-in: see `.lede-explain` in styles.css. The
          dashboard's job is to be read at a glance, and a paragraph of
          reasoning above every panel buries the figures it is explaining.
          Nothing is deleted — the toggle in the header brings it all back. */}
      {lede && <p className="lede lede-explain">{lede}</p>}
      {children}
    </section>
  );
}

/** An empty state that says what to do, not just that there is nothing here. */
export function Placeholder({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="placeholder">
      <b>{title}</b>
      <p>{children}</p>
    </div>
  );
}
