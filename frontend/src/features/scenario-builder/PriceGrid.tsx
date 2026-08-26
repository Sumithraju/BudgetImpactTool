/**
 * The editable price grid.
 *
 * This is the screen an analyst is most likely to disagree with the model on,
 * and rightly: only three of ten markets carry an observed price for this
 * class, and the rest are derived through purchasing-power parity from a US
 * list price that sits far above European reality. A grid that will not accept
 * a correction is telling the analyst their own market knowledge is
 * inadmissible.
 *
 * Two things the design keeps visible:
 *
 * **Which cells are real.** A derived price is marked as derived, before and
 * after an edit. The row an analyst should look at first is the one carrying
 * the model's guess rather than a citation.
 *
 * **What the number means.** Both the unit price and the annual cost are
 * editable and each derives the other. Nobody recognises 31.45 per unit; a lot
 * of people recognise EUR 3,925 a year, and recognition is the entire point of
 * making this editable.
 */

import { Fragment, useMemo, useState } from "react";
import type { DrugPrice } from "../../shared/api";
import { formatMoney, TIER_MEANING } from "../../shared/format";
import { Card, Placeholder } from "../../shared/ui";
import type { PriceEdit } from "./InputStudio";

interface Props {
  prices: DrugPrice[];
  edits: PriceEdit[];
  onChange: (edits: PriceEdit[]) => void;
  templateHref: string;
  loading: boolean;
}

function key(drugId: number, code: string) {
  return `${drugId}:${code}`;
}

export function PriceGrid({ prices, edits, onChange, templateHref, loading }: Props) {
  const [onlyDerived, setOnlyDerived] = useState(false);

  const editMap = useMemo(
    () => new Map(edits.map((e) => [key(e.drug_id, e.country_code), e.unit_price])),
    [edits],
  );

  const markets = useMemo(
    () => [...new Set(prices.map((p) => p.country_code))],
    [prices],
  );

  const therapies = useMemo(() => {
    const seen = new Map<number, { drug_id: number; drug_name: string }>();
    for (const p of prices) {
      if (!seen.has(p.drug_id)) {
        seen.set(p.drug_id, { drug_id: p.drug_id, drug_name: p.drug_name });
      }
    }
    return [...seen.values()];
  }, [prices]);

  const byCell = useMemo(
    () => new Map(prices.map((p) => [key(p.drug_id, p.country_code), p])),
    [prices],
  );

  const setPrice = (row: DrugPrice, unitPrice: number | null) => {
    const id = key(row.drug_id, row.country_code);
    const rest = edits.filter((e) => key(e.drug_id, e.country_code) !== id);
    if (unitPrice === null || !Number.isFinite(unitPrice) || unitPrice <= 0) {
      onChange(rest);
      return;
    }
    onChange([
      ...rest,
      { drug_id: row.drug_id, country_code: row.country_code, unit_price: unitPrice },
    ]);
  };

  const annualFactor = (row: DrugPrice) =>
    row.unit_price > 0 ? row.annual_cost / row.unit_price : 0;

  /** Enough decimals for the number to exist, and no more.
   *
   *  Unit prices in this class span four orders of magnitude — orlistat is
   *  under two cents a milligram, albiglutide is over a hundred a dose. A
   *  fixed precision either truncates the large ones or pads the small ones to
   *  meaninglessness, and a truncated price in an editable cell is worse than
   *  either: the analyst edits what they can see and silently changes the
   *  digits they cannot. */
  const displayUnit = (value: number) => {
    const magnitude = Math.abs(value);
    if (magnitude === 0) return 0;
    if (magnitude < 0.1) return Number(value.toPrecision(3));
    if (magnitude < 100) return Number(value.toFixed(2));
    return Math.round(value);
  };

  const visible = onlyDerived
    ? therapies.filter((t) =>
        markets.some((m) => byCell.get(key(t.drug_id, m))?.is_observed === false),
      )
    : therapies;

  if (loading) {
    return (
      <Card title="Prices">
        <Placeholder title="Loading the price grid">
          One row per therapy per market, with the model's own derivation
          pre-filled where no observed price exists.
        </Placeholder>
      </Card>
    );
  }

  if (!prices.length) {
    return (
      <Card title="Prices">
        <Placeholder title="No priced therapies yet">
          Pick at least one market to see the comparator basket and its prices.
        </Placeholder>
      </Card>
    );
  }

  const derivedCount = prices.filter((p) => !p.is_observed).length;

  return (
    <Card
      title="Prices — every cell editable"
      lede={
        <>
          {derivedCount} of {prices.length} cells have <b>no observed price</b> in
          that market and carry the model's purchasing-power derivation instead.
          Those are the ones worth correcting first. An edit becomes an override
          on this scenario, never a change to the reference data — your working
          assumption and a cited price stay different claims.
        </>
      }
      actions={
        <>
          <label className="switch">
            <input
              type="checkbox"
              checked={onlyDerived}
              onChange={(e) => setOnlyDerived(e.target.checked)}
            />
            <span>Only derived</span>
          </label>
          <a className="ghost-btn" href={templateHref}>
            Download as CSV
          </a>
          {edits.length > 0 && (
            <button type="button" className="ghost-btn" onClick={() => onChange([])}>
              Reset {edits.length} edit{edits.length === 1 ? "" : "s"}
            </button>
          )}
        </>
      }
    >
      <div className="tablewrap">
        <table className="grid">
          <thead>
            <tr>
              <th className="sticky-col">Therapy</th>
              {markets.map((m) => (
                <th key={m} colSpan={2}>
                  {m}
                </th>
              ))}
            </tr>
            <tr>
              <th className="sticky-col" />
              {markets.map((m) => (
                // A keyed Fragment, not a bare one: two cells per market means
                // the pair is the list item, and an unkeyed fragment leaves
                // React reconciling the columns by position — which reorders
                // the wrong prices into the wrong markets the moment the
                // market set changes.
                <Fragment key={m}>
                  <th className="sub">unit</th>
                  <th className="sub">per year</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((t) => (
              <tr key={t.drug_id}>
                <td className="sticky-col">
                  <span className="mkt-name">{t.drug_name}</span>
                </td>
                {markets.map((m) => {
                  const row = byCell.get(key(t.drug_id, m));
                  if (!row) {
                    return (
                      <Fragment key={m}>
                        <td className="num dim">—</td>
                        <td className="num dim">—</td>
                      </Fragment>
                    );
                  }
                  const edited = editMap.get(key(t.drug_id, m));
                  const unit = edited ?? row.unit_price;
                  const factor = annualFactor(row);
                  const annual = unit * factor;
                  const state = edited != null
                    ? "edited"
                    : row.is_observed
                      ? "observed"
                      : "derived";
                  return (
                    <Fragment key={m}>
                      <td className={`cell ${state}`}>
                        <input
                          type="number"
                          min={0}
                          step="any"
                          value={displayUnit(unit)}
                          aria-label={`${t.drug_name} unit price in ${m}`}
                          title={row.source}
                          onChange={(e) =>
                            setPrice(
                              row,
                              e.target.value === "" ? null : Number(e.target.value),
                            )
                          }
                        />
                        <i
                          className={`cell-flag ${state}`}
                          title={
                            state === "edited"
                              ? "Your override for this run"
                              : state === "observed"
                                ? `Observed · tier ${row.confidence_tier} — ${TIER_MEANING[row.confidence_tier] ?? ""}`
                                : "Derived by purchasing-power parity, not observed"
                          }
                        >
                          {state === "edited" ? "you" : state === "observed" ? "obs" : "der"}
                        </i>
                      </td>
                      <td className={`cell ${state}`}>
                        <input
                          type="number"
                          min={0}
                          step="any"
                          value={factor > 0 ? Math.round(annual) : 0}
                          disabled={factor <= 0}
                          aria-label={`${t.drug_name} annual cost in ${m}`}
                          onChange={(e) =>
                            setPrice(
                              row,
                              e.target.value === "" || factor <= 0
                                ? null
                                : Number(e.target.value) / factor,
                            )
                          }
                        />
                        <i className="cell-cur">{row.currency_code}</i>
                      </td>
                    </Fragment>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="sources">
        <summary>Where these prices came from</summary>
        <ul>
          {prices
            .filter((p) => p.is_observed)
            .map((p) => (
              <li key={`${p.drug_id}-${p.country_code}`}>
                <b>
                  {p.drug_name} · {p.country_code}
                </b>
                <span className={`chip t-${p.confidence_tier}`}>{p.confidence_tier}</span>
                <span>
                  {formatMoney(p.annual_cost, p.currency_code)} a year — {p.source}
                </span>
              </li>
            ))}
        </ul>
      </details>
    </Card>
  );
}
