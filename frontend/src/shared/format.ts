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
