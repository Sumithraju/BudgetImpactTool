/**
 * The small line icons beside every input group and result tab.
 *
 * Inline SVG rather than an icon package: there are twenty of them, they are
 * never themed independently of the text they sit beside, and a dependency
 * that ships a thousand glyphs to use twenty is weight with no return.
 *
 * Every glyph is drawn on the same 24-unit grid with the same 1.7 stroke and
 * inherits `currentColor`, so an icon takes the colour of whatever label it
 * sits in — active tab, muted heading, error state — with no per-state rule.
 *
 * They are decorative. The label beside each one already names the thing, so
 * every icon is `aria-hidden` and a screen reader hears the words alone
 * rather than the words twice.
 */

export type IconName =
  // input groups, in the order the model computes them
  | "population"
  | "epidemiology"
  | "eligibility"
  | "current_care"
  | "new_intervention"
  | "uptake"
  | "treatment_behaviour"
  | "outcomes"
  | "healthcare_costs"
  | "time_horizon"
  | "perspective"
  // result tabs
  | "funnel"
  | "affordability"
  | "access"
  | "impact"
  | "buys"
  | "subgroups"
  | "payer"
  | "uncertainty"
  | "report";

/** Path data only — the wrapper below supplies the shared attributes. */
const PATHS: Record<IconName, string> = {
  // Who and where: a pair of figures.
  population:
    "M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19 M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7 M20 19v-1.5a3.5 3.5 0 0 0-2.6-3.4 M15.5 4.3a3.5 3.5 0 0 1 0 6.4",
  // How much of them are ill: a trace with a beat in it.
  epidemiology: "M3 12h3.5l2-5.5 3.5 11 2.5-6.5 1.5 3H21",
  // What the label and the formulary allow through: a filter.
  eligibility: "M4 5h16l-6.2 7.3V19l-3.6-2v-4.7L4 5Z",
  // What is prescribed today: a capsule.
  current_care:
    "M10.5 4.5a4.5 4.5 0 0 1 6.4 6.4l-5.9 5.9a4.5 4.5 0 0 1-6.4-6.4l5.9-5.9Z M8 8l7 7",
  // The new asset: a flask.
  new_intervention:
    "M9.5 3v6.2L4.6 17a2 2 0 0 0 1.7 3h11.4a2 2 0 0 0 1.7-3l-4.9-7.8V3 M8 3h8 M7.4 14h9.2",
  // Adoption over time: a rising line.
  uptake: "M3 17.5 9 11l4 4 8-8 M15 7h6v6",
  // Adherence and persistence: a cycle.
  treatment_behaviour:
    "M20 12a8 8 0 0 1-13.7 5.6L4 15.4 M4 12a8 8 0 0 1 13.7-5.6L20 8.6 M4 20v-4.6h4.6 M20 4v4.6h-4.6",
  // What the spend buys clinically: a heart.
  outcomes:
    "M12 20s-7.5-4.6-7.5-9.4A4.1 4.1 0 0 1 12 8.2a4.1 4.1 0 0 1 7.5 2.4c0 4.8-7.5 9.4-7.5 9.4Z",
  // What care costs: a receipt.
  healthcare_costs:
    "M6 3.5h12v17l-2.4-1.6-2.4 1.6-2.4-1.6L8.4 20.5 6 18.9v-15.4Z M9.5 8.5h5 M9.5 12.5h5",
  // How many years: a calendar.
  time_horizon:
    "M4.5 6.5h15v13h-15v-13Z M8.5 3.5v5 M15.5 3.5v5 M4.5 11h15",
  // Whose budget: an eye.
  perspective:
    "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z M12 14.4a2.4 2.4 0 1 0 0-4.8 2.4 2.4 0 0 0 0 4.8Z",

  // Where the patients come from: the funnel again, narrowing.
  funnel: "M4 5h16l-6.2 7.3V19l-3.6-2v-4.7L4 5Z",
  // Can the market pay: a gauge.
  affordability:
    "M4 18a8 8 0 1 1 16 0 M12 18l4.2-4.9",
  // Price and break-even: a key.
  access:
    "M14.8 9.2a3.8 3.8 0 1 0-3.9 3.8L9.5 14.4l-1.4 1.4 1.4 1.4-1.4 1.4-2 .3.3-2 5-5Z",
  // With versus without: paired bars.
  impact: "M4 20V10 M9.3 20V4 M14.7 20v-8 M20 20V7",
  // Events avoided: a shield with a tick.
  buys:
    "M12 3.5 19.5 6v6c0 4.3-3 7-7.5 8.5C7.5 19 4.5 16.3 4.5 12V6L12 3.5Z M9 11.8l2.2 2.2 4-4.2",
  // Where it lands: a divided circle.
  subgroups:
    "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Z M12 3.5v8.5h8.5",
  // Per member per month: a wallet.
  payer:
    "M3.5 7.5A2 2 0 0 1 5.5 5.5h11a2 2 0 0 1 2 2v1 M3.5 7.5v9a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-13a2 2 0 0 1-2-2 M17 13.5h.01",
  // What we do not yet know: a question.
  uncertainty:
    "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M9.6 9.6a2.5 2.5 0 1 1 3.3 2.4c-.6.2-.9.8-.9 1.4v.6 M12 16.8h.01",
  // Narrative and export: a document.
  report:
    "M6 3.5h7.5L18.5 8v12.5h-12.5v-17Z M13.5 3.5V8H18.5 M9 12.5h6 M9 16h4",
};

export function Icon({
  name,
  className,
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name].split(" M").map((segment, i) => (
        <path key={i} d={i === 0 ? segment : `M${segment}`} />
      ))}
    </svg>
  );
}
