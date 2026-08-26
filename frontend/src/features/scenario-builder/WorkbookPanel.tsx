/**
 * Import a market model that already exists — M19.
 *
 * HEOR runs on Excel. Somebody has usually built most of this in a spreadsheet
 * before they ever open a tool, and asking them to re-type it is asking them
 * not to use the tool.
 *
 * The panel shows what the file was read as *before* anything is applied. An
 * import that silently reconfigured the scenario would give nobody a chance to
 * catch a column read wrongly, and every rejected cell is reported with its
 * sheet and row so the person fixing it gets an instruction rather than a
 * puzzle.
 */

import { Fragment, useRef, useState } from "react";
import { api, ApiError, type ImportResult } from "../../shared/api";
import { Card, Placeholder } from "../../shared/ui";

interface OverrideSummary {
  path: string;
  markets: number;
  low: string;
  high: string;
}

/** One line per assumption, with the spread across the markets it covers. */
function summarise(
  overrides: { parameter_path: string; country_code?: string | null; value: number }[],
): OverrideSummary[] {
  const byPath = new Map<string, number[]>();
  for (const item of overrides) {
    const values = byPath.get(item.parameter_path) ?? [];
    values.push(Number(item.value));
    byPath.set(item.parameter_path, values);
  }
  const round = (n: number) => String(Number(n.toPrecision(4)));
  return [...byPath.entries()].map(([path, values]) => ({
    path,
    markets: values.length,
    low: round(Math.min(...values)),
    high: round(Math.max(...values)),
  }));
}

export function WorkbookPanel({
  templateXlsx,
  templateCsv,
  onApply,
}: {
  templateXlsx: string;
  templateCsv: string;
  onApply: (result: ImportResult) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(false);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    setApplied(false);
    try {
      setResult(await api.importWorkbook(file));
    } catch (e) {
      setError((e as ApiError).message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  const errors = result?.issues.filter((i) => i.severity === "error") ?? [];
  const warnings = result?.issues.filter((i) => i.severity === "warning") ?? [];

  return (
    <Card
      title="Import from Excel or CSV"
      lede={
        <>
          Download the template — it comes pre-filled with this scenario's own
          price grid, so you correct what you disagree with rather than typing
          ten markets from nothing. Every column carries the same explanation
          you see on the inputs here, because it is the same sentence.
        </>
      }
      actions={
        <>
          <a className="ghost-btn" href={templateXlsx}>
            Template (.xlsx)
          </a>
          <a className="ghost-btn" href={templateCsv}>
            Template (.csv)
          </a>
        </>
      }
    >
      <div
        className="dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) void upload(file);
        }}
      >
        <input
          ref={input}
          type="file"
          accept=".xlsx,.xlsm,.csv"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
        <button
          type="button"
          className="run"
          onClick={() => input.current?.click()}
          disabled={busy}
        >
          {busy ? "Reading…" : "Choose a workbook"}
        </button>
        <span className="dim">or drop it here · .xlsx or .csv, up to 8 MB</span>
      </div>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {result && (
        <div className="import-result">
          <div className="import-head">
            <span className={result.accepted ? "chip t-A" : "chip t-C"}>
              {result.accepted ? "read cleanly" : `${errors.length} rejected`}
            </span>
            <span className="dim">
              {result.rows_read} row{result.rows_read === 1 ? "" : "s"} read ·{" "}
              {result.scenario.overrides.length} assumption
              {result.scenario.overrides.length === 1 ? "" : "s"} ·{" "}
              {result.scenario.prices.length} price
              {result.scenario.prices.length === 1 ? "" : "s"}
            </span>
          </div>

          <dl className="import-read">
            {result.scenario.asset_name && (
              <>
                <dt>Asset</dt>
                <dd>{result.scenario.asset_name}</dd>
              </>
            )}
            {result.scenario.country_codes.length > 0 && (
              <>
                <dt>Markets</dt>
                <dd>{result.scenario.country_codes.join(", ")}</dd>
              </>
            )}
            {result.scenario.subgroup_codes.length > 0 && (
              <>
                <dt>Segments</dt>
                <dd>{result.scenario.subgroup_codes.join(", ")}</dd>
              </>
            )}
            {result.scenario.perspective && (
              <>
                <dt>Perspective</dt>
                <dd>{result.scenario.perspective}</dd>
              </>
            )}
            {result.scenario.covered_population && (
              <>
                <dt>Covered lives</dt>
                <dd>{result.scenario.covered_population.toLocaleString("en-US")}</dd>
              </>
            )}
            {result.scenario.horizon_years && (
              <>
                <dt>Horizon</dt>
                <dd>{result.scenario.horizon_years} years</dd>
              </>
            )}
            {/* Grouped by path rather than listed row by row. A per-market
                file supplies the same assumption once per country — ninety
                rows for ten markets — and ninety near-identical lines is a
                preview nobody reads. One line per assumption, with the number
                of markets it covers and the range it spans, is the same
                information at a size a person checks. */}
            {summarise(result.scenario.overrides).map((row) => (
              <Fragment key={row.path}>
                <dt>{row.path}</dt>
                <dd>
                  {row.markets > 1 ? (
                    <>
                      {row.low === row.high
                        ? row.low
                        : `${row.low} – ${row.high}`}{" "}
                      <span className="dim">across {row.markets} markets</span>
                    </>
                  ) : (
                    row.low
                  )}
                </dd>
              </Fragment>
            ))}
          </dl>

          {(errors.length > 0 || warnings.length > 0) && (
            <ul className="import-issues">
              {[...errors, ...warnings].map((issue, i) => (
                <li key={i} className={issue.severity}>
                  <code>
                    {issue.sheet} · row {issue.row}
                  </code>
                  <span>{issue.message}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="import-actions">
            <button
              type="button"
              className="run"
              disabled={applied}
              onClick={() => {
                onApply(result);
                setApplied(true);
              }}
            >
              {applied ? "Applied to the scenario" : "Apply to the scenario"}
            </button>
            <span className="dim">
              Nothing was saved by importing. Applying fills the inputs on the
              left; the run itself still goes through the same validation a
              typed scenario does.
            </span>
          </div>
        </div>
      )}

      {!result && !error && !busy && (
        <Placeholder title="Nothing imported yet">
          The importer reads by sheet name and by a hidden key column, so you can
          reorder or reformat the template freely — only renaming the sheets
          breaks it.
        </Placeholder>
      )}
    </Card>
  );
}
