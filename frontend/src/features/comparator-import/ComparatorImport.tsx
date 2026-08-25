/**
 * Comparator import — M19 sections 5.1 to 5.6.
 *
 * The server validates; this renders what it found. Two behaviours from the
 * module spec are visible here and are the point of the panel: every finding
 * carries the sheet and cell that caused it, and a file with any error is
 * rejected whole rather than half-imported.
 */
import { useCallback, useRef, useState } from "react";
import {
  api,
  ApiError,
  type ComparatorImportResult,
  type ImportFinding,
} from "../../shared/api";
import { formatMoney, formatPercent, TIER_MEANING } from "../../shared/format";

const ACCEPTED = ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function FindingRow({ finding }: { finding: ImportFinding }) {
  const where = finding.ref ? `${finding.ref.sheet}!${finding.ref.cell}` : "whole file";
  return (
    <tr className={finding.severity === "error" ? "finding-error" : "finding-warning"}>
      <td>{finding.severity === "error" ? "Error" : "Warning"}</td>
      <td className="mono">{where}</td>
      <td>
        {finding.message}
        {finding.supplied && (
          <span className="field-foot">
            found {finding.supplied}
            {finding.expected ? ` · expected ${finding.expected}` : ""}
          </span>
        )}
      </td>
    </tr>
  );
}

export function ComparatorImport() {
  const [result, setResult] = useState<ComparatorImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.importComparators(file));
    } catch (e) {
      setError((e as ApiError).message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }, []);

  const errors = result?.findings.filter((f) => f.severity === "error") ?? [];
  const warnings = result?.findings.filter((f) => f.severity === "warning") ?? [];

  return (
    <section className="panel">
      <h2 className="nsec">Import the current comparator set</h2>
      <p className="lede">
        Upload the market model you already have, as .xlsx or .csv. Every cell is checked
        against the same rules the API enforces, and a file with any error is rejected
        whole — nothing is half-imported.
      </p>

      <div className="import-actions">
        <a className="export-btn" href={api.comparatorTemplateUrl()} download>
          Download the template
        </a>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="visually-hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = "";
          }}
        />
        <button type="button" className="run" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? "Checking…" : "Choose a file"}
        </button>
      </div>

      <p className="field-foot">
        Columns: Name, Type, Market, Currency, Market share (%), Drug cost / year,
        Administration / year, Monitoring / year, AE management / year, Source, Tier.
        Matched by name, so column order does not matter.
      </p>

      {error && (
        <div className="alert" role="alert">{error}</div>
      )}

      {result && (
        <>
          <div className={result.accepted ? "import-verdict ok" : "import-verdict bad"} role="status">
            <strong>{result.filename}</strong>{" "}
            {result.accepted
              ? `accepted — ${result.comparators.length} of ${result.rows_read} rows read.`
              : `rejected — ${errors.length} ${errors.length === 1 ? "error" : "errors"} across ${result.rows_read} rows. Nothing was imported.`}
          </div>

          {result.findings.length > 0 && (
            <div className="tablewrap">
              <table className="findings-table">
                <caption className="field-foot">
                  {errors.length} {errors.length === 1 ? "error" : "errors"},{" "}
                  {warnings.length} {warnings.length === 1 ? "warning" : "warnings"} — all
                  reported in one pass, so the file can be fixed in one go.
                </caption>
                <thead>
                  <tr><th>Severity</th><th>Where</th><th>What</th></tr>
                </thead>
                <tbody>
                  {/* Errors first: they are what stops the file. */}
                  {[...errors, ...warnings].map((f, i) => (
                    <FindingRow key={`${f.code}-${f.ref?.cell ?? "file"}-${i}`} finding={f} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.accepted && result.comparators.length > 0 && (
            <div className="tablewrap">
              <table className="registry-table">
                <thead>
                  <tr>
                    <th>Comparator</th><th>Market</th><th>Share</th>
                    <th>Drug</th><th>Admin</th><th>Monitoring</th><th>AE</th>
                    <th>Total / patient / year</th><th>Tier</th><th>From</th>
                  </tr>
                </thead>
                <tbody>
                  {result.comparators.map((c) => (
                    <tr key={c.origin}>
                      <td>
                        {c.name}
                        {c.therapy_type && <span className="field-foot">{c.therapy_type}</span>}
                      </td>
                      <td className="mono">{c.country_code}</td>
                      <td>{formatPercent(c.market_share)}</td>
                      <td>{formatMoney(c.drug_cost, c.currency_code)}</td>
                      <td>{formatMoney(c.admin_cost, c.currency_code)}</td>
                      <td>{formatMoney(c.monitoring_cost, c.currency_code)}</td>
                      <td>{formatMoney(c.ae_cost, c.currency_code)}</td>
                      <td><strong>{formatMoney(c.total_cost, c.currency_code)}</strong></td>
                      <td>
                        <span className={`tier tier-${c.confidence_tier}`} title={TIER_MEANING[c.confidence_tier]}>
                          {c.confidence_tier}
                        </span>
                      </td>
                      <td className="mono field-foot">{c.origin}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.accepted && (
            <p className="note">
              These rows are validated, not yet registered. A comparator enters a
              calculation through the registry, which requires a regimen and a priced
              source — so an imported row is promoted on the Comparators tab rather than
              written straight in. That is what keeps the registry the single record of
              what a drug is.
            </p>
          )}
        </>
      )}
    </section>
  );
}
