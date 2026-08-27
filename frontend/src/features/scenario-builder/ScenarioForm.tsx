import type { CountryOption, IndicationOption } from "../../shared/api";
import { formatPercent } from "../../shared/format";

export interface Draft {
  name: string;
  assetName: string;
  indicationId: number;
  launchYear: number;
  horizonYears: number;
  reportingCurrency: string;
  countryCodes: string[];
  /** null means "use the seeded default" — distinct from a user-set value. */
  diagnosisRate: number | null;
  treatmentRate: number | null;
  accessRate: number | null;
  uptakeYear1: number | null;
  uptakeTerminal: number | null;
}

interface Props {
  draft: Draft;
  onChange: (draft: Draft) => void;
  countries: CountryOption[];
  indications: IndicationOption[];
  onRun: () => void;
  busy: boolean;
  errorField: string | null;
  projectLandscape: boolean;
  onProjectLandscapeChange: (on: boolean) => void;
}

/** Sliders work in whole percent; state stays in fractions. The conversion
 *  happens at this boundary and nowhere else. */
function RateSlider({
  label,
  path,
  value,
  fallback,
  onChange,
  errorField,
}: {
  label: string;
  path: string;
  value: number | null;
  fallback: string;
  onChange: (v: number | null) => void;
  errorField: string | null;
}) {
  const overridden = value !== null;
  return (
    <div className={`field ${errorField === path ? "field-error" : ""}`}>
      <div className="field-head">
        <label htmlFor={path}>{label}</label>
        <span className={overridden ? "val val-set" : "val"}>
          {overridden ? formatPercent(value) : fallback}
        </span>
      </div>
      <input
        id={path}
        type="range"
        min={1}
        max={100}
        step={1}
        value={overridden ? Math.round(value * 100) : 50}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        aria-label={label}
      />
      <div className="field-foot">
        <span>{overridden ? "your override · tier C" : "seeded default"}</span>
        {overridden && (
          <button type="button" className="reset" onClick={() => onChange(null)}>
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

export function ScenarioForm({
  draft,
  onChange,
  countries,
  indications,
  onRun,
  busy,
  errorField,
  projectLandscape,
  onProjectLandscapeChange,
}: Props) {
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    onChange({ ...draft, [key]: value });

  const toggleMarket = (code: string) => {
    const next = draft.countryCodes.includes(code)
      ? draft.countryCodes.filter((c) => c !== code)
      : [...draft.countryCodes, code];
    if (next.length > 0) set("countryCodes", next);
  };

  return (
    <aside className="panel">
      <section>
        <h2>Asset</h2>
        <div className="field">
          <label htmlFor="asset">Name</label>
          <input
            id="asset"
            type="text"
            value={draft.assetName}
            onChange={(e) => set("assetName", e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="indication">Indication</label>
          <select
            id="indication"
            value={draft.indicationId}
            onChange={(e) => set("indicationId", Number(e.target.value))}
          >
            {indications.map((i) => (
              <option key={i.indication_id} value={i.indication_id}>
                {i.indication_name}
              </option>
            ))}
          </select>
        </div>
        <div className="row">
          <div className="field">
            <label htmlFor="launch">Launch year</label>
            <input
              id="launch"
              type="number"
              min={2026}
              max={2040}
              value={draft.launchYear}
              onChange={(e) => set("launchYear", Number(e.target.value))}
            />
          </div>
          <div className="field">
            <label htmlFor="horizon">Horizon</label>
            <select
              id="horizon"
              value={draft.horizonYears}
              onChange={(e) => set("horizonYears", Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5].map((y) => (
                <option key={y} value={y}>
                  {y} year{y > 1 ? "s" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="currency">Report in</label>
          <select
            id="currency"
            value={draft.reportingCurrency}
            onChange={(e) => set("reportingCurrency", e.target.value)}
          >
            {["USD", "EUR", "GBP", "DKK", "INR", "BRL", "CNY"].map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section>
        <h2>Markets</h2>
        <div className="markets">
          {countries.map((c) => {
            const on = draft.countryCodes.includes(c.country_code);
            return (
              <button
                key={c.country_code}
                type="button"
                className={on ? "mkt on" : "mkt"}
                aria-pressed={on}
                onClick={() => toggleMarket(c.country_code)}
                title={c.country_name}
              >
                {c.country_code}
              </button>
            );
          })}
        </div>
        <p className="hint">
          Only the USA has an observed branded price. Everything else is derived through
          purchasing-power parity and labelled as derived.
        </p>
      </section>

      <section>
        <h2>Assumptions</h2>
        <RateSlider
          label="Diagnosis rate"
          path="funnel.diagnosis_rate"
          value={draft.diagnosisRate}
          fallback="19.0% seeded"
          onChange={(v) => set("diagnosisRate", v)}
          errorField={errorField}
        />
        <RateSlider
          label="Treatment rate"
          path="funnel.treatment_rate"
          value={draft.treatmentRate}
          fallback="23.0% seeded"
          onChange={(v) => set("treatmentRate", v)}
          errorField={errorField}
        />
        <RateSlider
          label="Access rate"
          path="funnel.access_rate"
          value={draft.accessRate}
          fallback="70.0% seeded"
          onChange={(v) => set("accessRate", v)}
          errorField={errorField}
        />
        <RateSlider
          label="Year-1 uptake"
          path="uptake.year_1"
          value={draft.uptakeYear1}
          fallback="5.0% default"
          onChange={(v) => set("uptakeYear1", v)}
          errorField={errorField}
        />
        <RateSlider
          label="Terminal uptake"
          path="uptake.terminal"
          value={draft.uptakeTerminal}
          fallback="15.0% default"
          onChange={(v) => set("uptakeTerminal", v)}
          errorField={errorField}
        />
      </section>

      {/* M14 — a scenario variant, not a base case. The caveat sits at the
          toggle rather than in a footnote, because that is where the choice
          is actually made. */}
      <section>
        <h2>Launch-year market</h2>
        <label className="toggle">
          <input
            type="checkbox"
            checked={projectLandscape}
            onChange={(e) => onProjectLandscapeChange(e.target.checked)}
          />
          <span>
            Compare against the market at launch
            <small>
              Admits registered Phase II/III competitors into the world-without from the
              year they are expected to arrive. Every entrant assumes it is approved at
              all, when, and at what price — all tier D. Read the result beside the
              current-market one, not instead of it.
            </small>
          </span>
        </label>
      </section>

      <button type="button" className="run" onClick={onRun} disabled={busy}>
        {busy ? "Calculating…" : "Run scenario"}
      </button>
    </aside>
  );
}
