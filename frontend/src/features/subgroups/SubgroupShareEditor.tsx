/**
 * Subgroup shares as an input — M18 section 9's share allocator.
 *
 * Four editable shares and a residual that is shown but never editable. That
 * asymmetry is the module's central rule made visible: obesity alone is
 * derived as 100% minus the others, and letting it be typed would allow a set
 * that does not describe a whole population.
 *
 * The running total updates as you type, so a split that does not work is
 * visible while it is being made rather than discovered on submission.
 */
import { useCallback, useRef, useState } from "react";
import {
  api,
  ApiError,
  type ImportFinding,
  type SubgroupOption,
} from "../../shared/api";
import { formatPercent } from "../../shared/format";
import { GLOSSARY } from "../../shared/glossary";
import { Hint } from "../../shared/Hint";

/** Shares as fractions, keyed by subgroup code. Never percentages in state. */
export type SubgroupShares = Record<string, number>;

interface SubgroupShareEditorProps {
  options: SubgroupOption[];
  shares: SubgroupShares;
  onChange: (next: SubgroupShares) => void;
}

const PERCENT_STEP = 0.5;

export function SubgroupShareEditor({
  options,
  shares,
  onChange,
}: SubgroupShareEditorProps) {
  const [findings, setFindings] = useState<ImportFinding[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const suppliable = options.filter((o) => !o.is_residual && !o.is_disjoint);
  const residual = options.find((o) => o.is_residual);

  const suppliedTotal = suppliable.reduce((sum, o) => sum + (shares[o.code] ?? 0), 0);
  const residualShare = 1 - suppliedTotal;
  const overAllocated = residualShare < 0;

  const upload = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      try {
        const result = await api.importSubgroups(file);
        setFindings(result.findings);
        if (result.accepted) {
          onChange(
            Object.fromEntries(result.shares.map((s) => [s.code, s.share])),
          );
        }
      } catch (e) {
        setError((e as ApiError).message);
      } finally {
        setBusy(false);
      }
    },
    [onChange],
  );

  return (
    <div className="share-editor">
      <div className="field-head">
        Subgroups
        <Hint content={GLOSSARY["subgroup.share"]} label="subgroup share" />
      </div>
      <p className="field-foot">
        Who the patients with obesity are. Each counted once, in the most serious
        group they qualify for.
      </p>

      {suppliable.map((option) => {
        const share = shares[option.code] ?? 0;
        return (
          <label className="share-row" key={option.code}>
            <span className="share-label" title={option.definition}>
              {option.label.replace(/^Obesity with /, "")}
            </span>
            <span className="share-input">
              <input
                type="number"
                min={0}
                max={100}
                step={PERCENT_STEP}
                // Percentages at the boundary, fractions in state.
                value={Number((share * 100).toFixed(1))}
                onChange={(e) =>
                  onChange({
                    ...shares,
                    [option.code]: Math.max(0, Number(e.target.value) || 0) / 100,
                  })
                }
              />
              <span aria-hidden="true">%</span>
            </span>
          </label>
        );
      })}

      {residual && (
        <div className={overAllocated ? "share-row share-residual bad" : "share-row share-residual"}>
          <span className="share-label">
            {residual.label.replace(/^Obesity with /, "")}
            <Hint content={GLOSSARY["subgroup.residual"]} label="the residual" />
          </span>
          <span className="share-derived mono">{formatPercent(residualShare)}</span>
        </div>
      )}

      <div className={overAllocated ? "share-total bad" : "share-total"}>
        <span>Total</span>
        <strong className="mono">{formatPercent(suppliedTotal + Math.max(residualShare, 0))}</strong>
      </div>

      {overAllocated && (
        <p className="field-error" role="alert">
          These four already account for {formatPercent(suppliedTotal)}. They must total
          less than 100% so there is room for patients with none of these conditions.
        </p>
      )}

      <div className="share-actions">
        <a className="reset" href={api.subgroupTemplateUrl()} download>
          Template
        </a>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="visually-hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = "";
          }}
        />
        <button type="button" className="reset" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? "Checking…" : "Import Excel/CSV"}
        </button>
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}

      {findings.length > 0 && (
        <ul className="share-findings">
          {findings.map((f, i) => (
            <li key={`${f.code}-${i}`} className={f.severity === "error" ? "finding-error" : "finding-warning"}>
              {f.ref && <span className="mono">{f.ref.cell}</span>} {f.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
