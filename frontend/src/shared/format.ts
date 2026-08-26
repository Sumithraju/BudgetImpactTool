/**
 * Formatting lives here, not in components.
 *
 * Two domain rules this file exists to enforce: rates are fractions
 * everywhere in state and only ever become percentages at display time, and
 * money always carries its currency — there is no function that formats a
 * bare amount, because that is how a EUR total ends up rendered with a
 * dollar sign.
 */

const COMPACT = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2,
});

export const formatCount = (value: number): string =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);

export function formatMoney(amount: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * For per-member figures, which are legitimately small.
 *
 * PMPM on a national denominator lands in the tens of cents, and the
 * whole-unit rounding `formatMoney` uses would render every one of them as
 * zero — a figure a payer would read as "this costs nothing", which is the
 * opposite of what a two-decimal figure says.
 */
export function formatMoneyPrecise(amount: number, currency: string): string {
  const magnitude = Math.abs(amount);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    // Below a unit, show enough places for the number to exist at all;
    // above it, two is what a per-member figure is quoted to.
    minimumFractionDigits: magnitude > 0 && magnitude < 0.01 ? 4 : 2,
    maximumFractionDigits: magnitude > 0 && magnitude < 0.01 ? 4 : 2,
  }).format(amount);
}

/** For headline figures, where "€2.71B" reads better than nine digits. */
export function formatMoneyCompact(amount: number, currency: string): string {
  const symbol = currencySymbol(currency);
  return `${symbol}${COMPACT.format(amount)}`;
}

export function currencySymbol(currency: string): string {
  const parts = new Intl.NumberFormat("en-US", { style: "currency", currency })
    .formatToParts(0)
    .find((p) => p.type === "currency");
  return parts?.value ?? currency + " ";
}

/** Takes a fraction. Multiplying by 100 happens here and nowhere else. */
export const formatPercent = (fraction: number, digits = 1): string =>
  `${(fraction * 100).toFixed(digits)}%`;

export const STAGE_LABELS: Record<string, string> = {
  total_population: "Total population",
  adult_population: "Adult population",
  diseased: "Diseased",
  diagnosed: "Diagnosed",
  treated: "Treated",
  label_eligible: "Label-eligible",
  addressable: "Addressable",
};

export const TIER_MEANING: Record<string, string> = {
  A: "Published, country-specific, with a stated interval",
  B: "Published, but regional or extrapolated",
  C: "Analogue-derived or an expert assumption",
  D: "Placeholder — must be replaced before this is relied on",
};

export const BASIS_LABELS: Record<string, string> = {
  list: "List price",
  nadac: "NADAC",
  estimated_net: "Estimated net",
  ppp_derived: "PPP-derived",
};

/**
 * A reader-facing name for each warning code.
 *
 * The codes themselves are the app's own vocabulary — `DeliverableTab` sorts on
 * them, and a run's stored snapshot records them — so they stay in the data.
 * What a person sees is this instead. `MIXED_PRICE_BASIS` tells an engineer
 * where to look and tells a market-access reader nothing; "Prices are not
 * like-for-like" tells the reader what is wrong with the number in front of
 * them, which is the only thing a warning is for.
 *
 * A code with no entry here falls back to its own text, sentence-cased. That is
 * deliberately plain rather than clever: a new warning should read a little
 * awkwardly until someone writes it a name, not silently look finished.
 */
export const WARNING_LABELS: Record<string, string> = {
  MIXED_PRICE_BASIS: "Prices are not like-for-like",
  COMPARATOR_UNPRICED: "A current treatment has no price",
  COMPARATORS_NEED_PRICING: "Some therapies still need a price",
  NO_COMPARATORS_FOUND: "No competing therapies found",
  UNPRICED_MARKET: "No price in this market",
  ESTIMATED_NET_PRICE: "Price is an estimated net, not a list price",
  TIER_D_INPUT: "Built on a placeholder figure",
  STALE_VINTAGE: "Data is older than usual",
  PROJECTED_VALUE: "Figure is projected, not observed",
  MISSING_NDC_MAPPING: "A price could not be matched to a dose",
  AE_PROFILE_ASYMMETRIC: "Side-effect costs are missing for some therapies",
  AE_COST_DERIVED: "Side-effect costs are estimated, not observed",
  AE_COST_MISSING: "No side-effect costs for this market",
  EVENT_COST_MISSING: "An avoided event has no cost attached",
  PIPELINE_ENTRANT_MODELLED: "Includes therapies not yet approved",
  PIPELINE_ENTRANT_EXCLUDED: "Unapproved therapies left out",
  SUBGROUP_SHARES_UNBALANCED: "This covers part of the population",
  BASELINE_RATE_PARTIAL: "An event rate covers part of the population",
  COVERED_POPULATION_ASSUMED: "Covered lives were assumed",
  NO_OUTCOME_EVIDENCE: "No published effect for this therapy",
  EFFECT_BEYOND_FOLLOW_UP: "Projected beyond the trial's follow-up",
  EFFECT_TRANSPORTED: "Effect measured in a different population",
  IMPORT_CELL_REJECTED: "A cell in your file was rejected",
  SUBSTITUTION_FLOOR: "Market shares hit their floor",
  CORRELATED_CRITERIA: "Two eligibility criteria overlap",
  DISTRIBUTION_SHRUNK: "An uncertainty range was narrowed to fit",
  PPP_FLOOR_APPLIED: "A derived price hit its floor",
  NO_GROUNDING: "No supporting guideline text found",
  NO_BREAK_EVEN: "No break-even price could be found",
};

/** The reader-facing name for a warning, or a readable fallback. */
export function warningLabel(code: string): string {
  const known = WARNING_LABELS[code];
  if (known) return known;
  const words = code.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
