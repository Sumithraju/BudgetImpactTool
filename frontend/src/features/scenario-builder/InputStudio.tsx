/**
 * The inputs, in the order the model computes them.
 *
 * Population, then epidemiology, then eligibility, then current care, then the
 * intervention, uptake, behaviour, outcomes, costs, horizon, perspective. That
 * is the HEOR review's own taxonomy and it is also the order the funnel runs
 * in, so an analyst filling this in top to bottom is walking the model rather
 * than hunting for fields.
 *
 * Every field carries its explanation in place, and the explanation is fetched
 * from the API's field guide rather than written here — the same sentence
 * appears in the import template and the exported workbook.
 */

import { useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type {
  Calculation,
  CountryOption,
  CriterionOption,
  FieldGroup,
  IndicationOption,
  PerspectiveOption,
  SubgroupOption,
} from "../../shared/api";
import { Help, indexFields } from "../../shared/ui";
import { Icon, type IconName } from "../../shared/Icons";
import { formatCount, formatMoney, formatPercent } from "../../shared/format";

/** One value read out of an imported file, kept editable.
 *
 *  Held separately from the typed fields because it is addressed differently:
 *  a typed override applies to every market, while an imported one names the
 *  market it came from. Merging them would lose that, and lose the ability to
 *  say which figures came from the analyst's own file. */
export interface ImportedValue {
  parameter_path: string;
  country_code: string | null;
  value: number;
  note?: string | null;
}

export interface PriceEdit {
  drug_id: number;
  country_code: string;
  unit_price: number;
}

export interface Draft {
  name: string;
  assetName: string;
  indicationId: number;
  launchYear: number;
  horizonYears: number;
  reportingCurrency: string;
  countryCodes: string[];
  /** null means "use the seeded default" — distinct from a user-set value that
   *  happens to equal it, and the two are recorded differently. */
  prevalence: number | null;
  diagnosisRate: number | null;
  treatmentRate: number | null;
  accessRate: number | null;
  uptakeYear1: number | null;
  uptakeTerminal: number | null;
  uptakeCurve: "logistic" | "linear";
  regainPerYear: number | null;
  /** Per-criterion narrowing factors, keyed by criterion code. Absent means
   *  the seeded default; a present value is an override the run carries as
   *  tier C, exactly like every other typed input. */
  criteriaFactors: Record<string, number>;
  /** How much of the new therapy's uptake is drawn from existing treatment
   *  rather than from untreated patients. Moves what the world-without costs,
   *  which is the whole of the subtraction. */
  substitutionNaive: number | null;
  perspective: string;
  coveredPopulation: number | null;
  subgroupCodes: string[];
  priceEdits: PriceEdit[];
  /** Whatever an imported file supplied, still editable here. Empty until a
   *  file is imported, at which point the inputs it covers show its values and
   *  everything else stays on the seeded default. */
  imported: ImportedValue[];
}

interface Props {
  draft: Draft;
  /** The setter itself, not a value callback. Toggling several markets or
   *  segments in quick succession runs several updates inside one React
   *  batch, and each one built from the `draft` prop would read the same
   *  stale value — so all but the last would be silently discarded. Passing
   *  the dispatcher lets every update be functional and compose. */
  onChange: Dispatch<SetStateAction<Draft>>;
  countries: CountryOption[];
  indications: IndicationOption[];
  subgroups: SubgroupOption[];
  perspectives: PerspectiveOption[];
  guide: FieldGroup[];
  criteria: CriterionOption[];
  /** The last finished run, or null before the first one. Read only for the
   *  figures the engine derives and does not accept back as inputs — outcomes
   *  and the cost components — so those sections show real seeded values
   *  rather than controls that would move nothing. */
  calculation: Calculation | null;
  onRun: () => void;
  busy: boolean;
  errorField: string | null;
  projectLandscape: boolean;
  onProjectLandscapeChange: (on: boolean) => void;
}

/** Sliders work in whole percent; state stays in fractions. The conversion
 *  happens at this boundary and nowhere else. */
function Rate({
  label,
  fieldKey,
  path,
  value,
  fallback,
  onChange,
  errorField,
  guide,
  min = 1,
  max = 100,
}: {
  label: string;
  fieldKey: string;
  path: string;
  value: number | null;
  fallback: string;
  onChange: (v: number | null) => void;
  errorField: string | null;
  guide: ReturnType<typeof indexFields>;
  min?: number;
  max?: number;
}) {
  const set = value !== null;
  return (
    <div className={`field ${errorField === path ? "field-error" : ""}`}>
      <div className="field-head">
        <Help spec={guide.get(fieldKey)}>
          <label htmlFor={path}>{label}</label>
        </Help>
        <span className={set ? "val val-set" : "val"}>
          {set ? formatPercent(value) : fallback}
        </span>
      </div>
      <div className="rate-controls">
        <input
          id={path}
          type="range"
          min={min}
          max={max}
          step={1}
          value={set ? Math.round(value * 100) : 50}
          onChange={(e) => onChange(Number(e.target.value) / 100)}
          aria-label={label}
        />
        {/* A number box beside the slider, because an analyst who knows the
            market wants to type 23.4, not aim at it. */}
        <input
          className="rate-number"
          type="number"
          min={0}
          max={100}
          step={0.1}
          value={set ? Number((value * 100).toFixed(2)) : ""}
          placeholder="—"
          aria-label={`${label}, percent`}
          onChange={(e) =>
            onChange(e.target.value === "" ? null : Number(e.target.value) / 100)
          }
        />
        <span className="rate-unit">%</span>
      </div>
      <div className="field-foot">
        <span>{set ? "your override · tier C" : "seeded default"}</span>
        {set && (
          <button type="button" className="reset" onClick={() => onChange(null)}>
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

/** A count, on a slider with a typed box beside it.
 *
 *  Absolute rather than a share, so the scale is logarithmic — covered lives
 *  run from a small self-insured employer to a national payer, and a linear
 *  track would put every realistic value in the first millimetre. */
function Amount({
  label,
  fieldKey,
  id,
  value,
  placeholder,
  min,
  max,
  onChange,
  guide,
  note,
}: {
  label: string;
  fieldKey: string;
  id: string;
  value: number | null;
  placeholder: string;
  min: number;
  max: number;
  onChange: (v: number | null) => void;
  guide: ReturnType<typeof indexFields>;
  note?: string;
}) {
  const set = value !== null;
  const lg = (n: number) => Math.log10(Math.max(n, 1));
  const toSlider = (n: number) =>
    ((lg(n) - lg(min)) / (lg(max) - lg(min))) * 100;
  const fromSlider = (pct: number) =>
    Math.round(10 ** (lg(min) + (pct / 100) * (lg(max) - lg(min))));

  return (
    <div className="field">
      <div className="field-head">
        <Help spec={guide.get(fieldKey)}>
          <label htmlFor={id}>{label}</label>
        </Help>
        <span className={set ? "val val-set" : "val"}>
          {set ? formatCount(value) : placeholder}
        </span>
      </div>
      <div className="rate-controls">
        <input
          id={id}
          type="range"
          min={0}
          max={100}
          step={1}
          value={set ? toSlider(value) : 0}
          onChange={(e) => onChange(fromSlider(Number(e.target.value)))}
          aria-label={label}
        />
        <input
          className="rate-number"
          type="number"
          min={min}
          step={1000}
          value={set ? value : ""}
          placeholder="—"
          aria-label={`${label}, people`}
          onChange={(e) =>
            onChange(e.target.value === "" ? null : Number(e.target.value))
          }
        />
        <span className="rate-unit" />
      </div>
      <div className="field-foot">
        <span>{set ? "your override · tier C" : note ?? "not supplied"}</span>
        {set && (
          <button type="button" className="reset" onClick={() => onChange(null)}>
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

/** One eligibility criterion: a narrowing factor on a slider, and the stack
 *  position the engine gave it.
 *
 *  The enabled state is reported, not offered. `criteria.<code>.enabled` is in
 *  the override vocabulary but the engine does not read it back yet, so a
 *  switch here would look like a control and change nothing. The factor beside
 *  it does resolve, so that is what moves. */
function CriterionRow({
  spec,
  value,
  onChange,
  errorField,
}: {
  spec: CriterionOption;
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  errorField: string | null;
}) {
  const path = `criteria.${spec.criterion_code}.factor`;
  const set = value !== undefined;
  const shown = set ? value : spec.default_factor;
  // The seeded band when there is one, widened just enough to be draggable
  // when low and high are equal — otherwise the track has no travel at all.
  const lo = Math.round((spec.factor_low ?? Math.min(shown, 0.05)) * 100);
  const hi = Math.round((spec.factor_high ?? 1) * 100);
  const min = Math.max(1, Math.min(lo, Math.round(shown * 100)));
  const max = Math.max(hi, Math.round(shown * 100), min + 1);

  return (
    <div className={`criterion ${errorField === path ? "field-error" : ""}`}>
      <div className="criterion-head">
        <label htmlFor={path}>{spec.criterion_label}</label>
        <span className={set ? "val val-set" : "val"}>
          {formatPercent(shown, 0)}
        </span>
      </div>
      <div className="rate-controls">
        <input
          id={path}
          type="range"
          min={min}
          max={max}
          step={1}
          value={Math.round(shown * 100)}
          onChange={(e) => onChange(Number(e.target.value) / 100)}
          aria-label={spec.criterion_label}
        />
        <input
          className="rate-number"
          type="number"
          min={0}
          max={100}
          step={0.5}
          value={Number((shown * 100).toFixed(1))}
          aria-label={`${spec.criterion_label}, percent`}
          onChange={(e) =>
            onChange(e.target.value === "" ? undefined : Number(e.target.value) / 100)
          }
        />
        <span className="rate-unit">%</span>
      </div>
      <div className="field-foot">
        <span>
          {spec.enabled ? "in the stack" : "held out — overlaps another"} · tier{" "}
          {set ? "C" : spec.confidence_tier}
        </span>
        {set && (
          <button
            type="button"
            className="reset"
            onClick={() => onChange(undefined)}
          >
            Reset
          </button>
        )}
      </div>
      <p className="criterion-why">{spec.source}</p>
    </div>
  );
}

/** A figure the engine derives and does not take back as an input.
 *
 *  Shown rather than hidden: the review asks for outcomes and cost components
 *  to be visible where the inputs are, and they are real seeded values. They
 *  are not controls because no override path reaches them — a slider here
 *  would move nothing, which is worse than a number that admits it is fixed. */
function Readout({
  label,
  value,
  meaning,
}: {
  label: string;
  value: string;
  meaning?: string;
}) {
  return (
    <div className="readout">
      <span className="readout-label">{label}</span>
      <span className="readout-value">{value}</span>
      {meaning && <span className="readout-why">{meaning}</span>}
    </div>
  );
}

/** A path like `subgroup.htn_osa.share` in the words the panel uses elsewhere.
 *
 *  Falls back to the raw path rather than to a guess: an imported value whose
 *  path this does not recognise is still a real value the run will use, and
 *  hiding it behind a prettier but wrong label would be worse than showing the
 *  path. */
function labelForPath(path: string, subgroups: SubgroupOption[]): string {
  const subgroup = path.match(/^subgroup\.([a-z0-9_]+)\.(share|eligible_factor)$/);
  if (subgroup) {
    const name =
      subgroups.find((s) => s.subgroup_code === subgroup[1])?.subgroup_label ??
      subgroup[1];
    return subgroup[2] === "share"
      ? `${name} — share of prevalent`
      : `${name} — clinically eligible`;
  }
  return (
    {
      "epidemiology.prevalence": "Prevalence",
      "funnel.diagnosis_rate": "Diagnosed share",
      "funnel.treatment_rate": "Treated share",
      "funnel.access_rate": "Reimbursed access",
      "uptake.year_1": "Year-1 uptake",
      "uptake.terminal": "Terminal uptake",
      "outcomes.regain_per_year": "Weight regain per year",
    }[path] ?? path
  );
}

export function InputStudio({
  draft,
  onChange,
  countries,
  indications,
  subgroups,
  perspectives,
  guide,
  criteria,
  calculation,
  onRun,
  busy,
  errorField,
  projectLandscape,
  onProjectLandscapeChange,
}: Props) {
  const fields = useMemo(() => indexFields(guide), [guide]);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    onChange((current) => ({ ...current, [key]: value }));

  const toggleMarket = (code: string) =>
    onChange((current) => {
      const next = current.countryCodes.includes(code)
        ? current.countryCodes.filter((c) => c !== code)
        : [...current.countryCodes, code];
      // At least one market, always: a scenario with none is not a scenario,
      // and the API would reject it with a less obvious message.
      return next.length > 0 ? { ...current, countryCodes: next } : current;
    });

  /** Overlapping subgroups are single-select.
   *
   *  A patient with both diabetes and hypertension is in two of WHO's four
   *  subgroups, so their results cannot be added — across the ten source
   *  countries the shares sum to about 1.5x the obese population. The API
   *  refuses a multi-selection outright; offering one here and then refusing it
   *  would be a worse way to say the same thing, so the control only ever holds
   *  one. Clicking the selected subgroup again clears it, which is how you get
   *  back to modelling everybody. */
  const chooseSubgroup = (code: string) =>
    onChange((current) => ({
      ...current,
      subgroupCodes: current.subgroupCodes.includes(code) ? [] : [code],
    }));

  const setCriterion = (code: string, value: number | undefined) =>
    onChange((current) => {
      const next = { ...current.criteriaFactors };
      if (value === undefined) delete next[code];
      else next[code] = value;
      return { ...current, criteriaFactors: next };
    });

  // Outcomes and cost components come from the finished run: they are engine
  // output, and the first market is the one the panel reports since the rest
  // repeat the same structure in their own currency.
  const shown = calculation?.countries?.[0] ?? null;

  const perspective = perspectives.find((p) => p.code === draft.perspective);
  const needsCovered = perspective?.requires_covered_population ?? false;

  // What share of the prevalent population the chosen subgroup covers. Shown
  // rather than left implicit: restricting to a subgroup is a legitimate thing
  // to model, but every population and cost figure downstream is then for that
  // share only, and a reader comparing it against a whole-population run needs
  // to know the denominator moved.
  const coverage = useMemo(
    () =>
      subgroups
        .filter((s) => draft.subgroupCodes.includes(s.subgroup_code))
        .reduce((total, s) => total + s.share_of_diagnosed, 0),
    [subgroups, draft.subgroupCodes],
  );

  const Section = ({
    id,
    title,
    summary,
    children,
  }: {
    id: string;
    title: string;
    summary?: string;
    children: React.ReactNode;
  }) => {
    // The group id doubles as the icon name: both come from the same
    // eleven-module taxonomy, so a new module gets its glyph by existing
    // rather than by being registered in a second list.
    const icon = id as IconName;
    const open = openGroup === null || openGroup === id;
    return (
      <section className={`instep ${open ? "" : "collapsed"}`}>
        <button
          type="button"
          className="instep-head"
          aria-expanded={open}
          onClick={() => setOpenGroup(openGroup === id ? null : id)}
        >
          <span className="instep-title">
            <Icon name={icon} className="instep-icon" />
            {title}
          </span>
          <span className="instep-chevron" aria-hidden>
            {open ? "−" : "+"}
          </span>
        </button>
        {open && (
          <div className="instep-body">
            {summary && <p className="instep-summary">{summary}</p>}
            {children}
          </div>
        )}
      </section>
    );
  };

  const summaryFor = (key: string) => guide.find((g) => g.key === key)?.summary;

  return (
    <aside className="studio">
      <div className="studio-scroll">
        {/* 1 — POPULATION ------------------------------------------------ */}
        <Section id="population" title="1 · Population" summary={summaryFor("population")}>
          <div className="field">
            <Help spec={fields.get("country_codes")}>
              <label>Markets</label>
            </Help>
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
          </div>

          <Amount
            label="Covered population"
            fieldKey="covered_population"
            id="covered"
            value={draft.coveredPopulation}
            placeholder="whole market"
            min={10_000}
            max={1_500_000_000}
            onChange={(v) => set("coveredPopulation", v)}
            guide={fields}
            note={
              needsCovered
                ? "needed by this perspective"
                : "this perspective reads against the whole market"
            }
          />
          {needsCovered && !draft.coveredPopulation && (
            <p className="hint warn">
              Without this, every per-member figure falls back to the modelled
              population — a national average rather than this payer's.
            </p>
          )}

          <Readout
            label="Annual growth"
            value="held flat"
            meaning="The funnel runs on a fixed denominator; growth is not modelled."
          />
        </Section>

        {/* 2 — EPIDEMIOLOGY ---------------------------------------------- */}
        <Section
          id="epidemiology"
          title="2 · Epidemiology"
          summary={summaryFor("epidemiology")}
        >
          <Rate
            label="Prevalence"
            fieldKey="prevalence"
            path="epidemiology.prevalence"
            value={draft.prevalence}
            fallback="WHO, per market"
            onChange={(v) => set("prevalence", v)}
            errorField={errorField}
            guide={fields}
          />
          <Rate
            label="Diagnosed share of prevalent cases"
            fieldKey="diagnosis_rate"
            path="funnel.diagnosis_rate"
            value={draft.diagnosisRate}
            fallback="19.0% seeded"
            onChange={(v) => set("diagnosisRate", v)}
            errorField={errorField}
            guide={fields}
          />
          <Readout
            label="Incidence"
            value={
              shown?.epidemiology?.incidence_per_100k
                ? `${formatCount(shown.epidemiology.incidence_per_100k)} / 100k / yr`
                : "WHO, per market"
            }
            meaning="The annual inflow. Seeded per market and not overridable."
          />
        </Section>

        {/* 3 — ELIGIBILITY ----------------------------------------------- */}
        <Section id="eligibility" title="3 · Eligibility" summary={summaryFor("eligibility")}>
          <div className="field">
            <div className="field-head">
              <Help spec={fields.get("subgroup_codes")}>
                <label>Clinical subgroup</label>
              </Help>
              <span className={draft.subgroupCodes.length ? "val val-set" : "val"}>
                {draft.subgroupCodes.length
                  ? `${formatPercent(coverage, 0)} of prevalent cases`
                  : "everyone with the condition"}
              </span>
            </div>
            <div className="segments" role="radiogroup" aria-label="Clinical subgroup">
              <button
                type="button"
                role="radio"
                className={draft.subgroupCodes.length === 0 ? "segment on" : "segment"}
                aria-checked={draft.subgroupCodes.length === 0}
                onClick={() => set("subgroupCodes", [])}
              >
                <b>Everyone with the condition</b>
                <em>100% of prevalent cases · no comorbidity restriction</em>
              </button>
              {subgroups.map((group) => {
                const on = draft.subgroupCodes.includes(group.subgroup_code);
                return (
                  <button
                    key={group.subgroup_code}
                    type="button"
                    role="radio"
                    className={on ? "segment on" : "segment"}
                    aria-checked={on}
                    onClick={() => chooseSubgroup(group.subgroup_code)}
                    title={group.description ?? group.subgroup_label}
                  >
                    <b>{group.subgroup_label.replace(/^Obesity \+ /, "+ ")}</b>
                    <em>
                      {formatPercent(group.share_of_diagnosed, 0)} of prevalent ·{" "}
                      {formatPercent(group.eligible_factor, 0)} clinically eligible
                    </em>
                  </button>
                );
              })}
            </div>
            <p className="hint">
              One at a time — these subgroups overlap, so a patient with both
              diabetes and hypertension is in two of them and their results
              cannot be added. The <b>Subgroups</b> tab runs each independently
              and compares them.
            </p>
          </div>
          {criteria.length > 0 && (
            <div className="criteria">
              <div className="field-head">
                <Help spec={fields.get("criteria")}>
                  <label>Label and formulary restrictions</label>
                </Help>
                <span className="val">
                  {criteria.filter((c) => c.enabled).length} of {criteria.length} in
                  the stack
                </span>
              </div>
              {criteria.map((c) => (
                <CriterionRow
                  key={c.criterion_code}
                  spec={c}
                  value={draft.criteriaFactors[c.criterion_code]}
                  onChange={(v) => setCriterion(c.criterion_code, v)}
                  errorField={errorField}
                />
              ))}
            </div>
          )}
          <Rate
            label="Treated share"
            fieldKey="treatment_rate"
            path="funnel.treatment_rate"
            value={draft.treatmentRate}
            fallback="23.0% seeded"
            onChange={(v) => set("treatmentRate", v)}
            errorField={errorField}
            guide={fields}
          />
          <Rate
            label="Reimbursed access"
            fieldKey="access_rate"
            path="funnel.access_rate"
            value={draft.accessRate}
            fallback="70.0% seeded"
            onChange={(v) => set("accessRate", v)}
            errorField={errorField}
            guide={fields}
          />
        </Section>

        {/* IMPORTED VALUES — only when a file supplied some. ------------ */}
        {draft.imported.length > 0 && (
          <Section
            id="imported"
            title={`From your file · ${draft.imported.length} values`}
            summary="Every value your spreadsheet supplied, still editable. Anything your file did not cover is not listed here and stays on the model's seeded default."
          >
            <div className="imported-list">
              {draft.imported.map((item, index) => (
                <div className="imported-row" key={`${item.parameter_path}-${item.country_code}`}>
                  <div className="imported-head">
                    <span className="imported-path" title={item.note ?? ""}>
                      {labelForPath(item.parameter_path, subgroups)}
                    </span>
                    {item.country_code && (
                      <span className="imported-market">{item.country_code}</span>
                    )}
                  </div>
                  <div className="imported-controls">
                    <input
                      type="number"
                      step="any"
                      min={0}
                      value={Number(item.value.toFixed(6))}
                      aria-label={`${item.parameter_path} for ${item.country_code ?? "all markets"}`}
                      onChange={(e) =>
                        onChange((current) => {
                          const next = [...current.imported];
                          next[index] = { ...next[index], value: Number(e.target.value) };
                          return { ...current, imported: next };
                        })
                      }
                    />
                    <button
                      type="button"
                      className="reset"
                      aria-label="Drop this imported value"
                      onClick={() =>
                        onChange((current) => ({
                          ...current,
                          imported: current.imported.filter((_, i) => i !== index),
                        }))
                      }
                    >
                      Drop
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="ghost-btn"
              onClick={() => onChange((current) => ({ ...current, imported: [] }))}
            >
              Clear all imported values
            </button>
          </Section>
        )}

        {/* 4 — CURRENT CARE ---------------------------------------------- */}
        <Section id="current_care" title="4 · Current care" summary={summaryFor("current_care")}>
          <Rate
            label="Drawn from existing treatment"
            fieldKey="substitution"
            path="substitution.naive"
            value={draft.substitutionNaive}
            fallback="seeded per therapy"
            onChange={(v) => set("substitutionNaive", v)}
            errorField={errorField}
            guide={fields}
            min={0}
          />
          <p className="hint">
            The rest comes from patients on no pharmacotherapy. Raise it and the
            world-without gets dearer, so the incremental figure falls.
          </p>
          <p className="hint">
            The comparator basket and its prices are on the{" "}
            <b>Prices</b> tab — every cell editable, and the derived ones marked
            as derived.
          </p>
          <label className="toggle">
            <input
              type="checkbox"
              checked={projectLandscape}
              onChange={(e) => onProjectLandscapeChange(e.target.checked)}
            />
            <span>
              Compare against the market at launch
              <small>
                Admits registered Phase II/III competitors into the world-without
                from the year they are expected to arrive. Every entrant assumes
                it is approved at all, when, and at what price — all tier D. Read
                the result beside the current-market one, not instead of it.
              </small>
            </span>
          </label>
        </Section>

        {/* 5 — NEW INTERVENTION ------------------------------------------ */}
        <Section
          id="new_intervention"
          title="5 · New intervention"
          summary={summaryFor("new_intervention")}
        >
          <div className="field">
            <Help spec={fields.get("asset_name")}>
              <label htmlFor="asset">Asset</label>
            </Help>
            <input
              id="asset"
              type="text"
              value={draft.assetName}
              onChange={(e) => set("assetName", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="indication">Disease</label>
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
          <div className="field">
            <Help spec={fields.get("launch_year")}>
              <label htmlFor="launch">Launch year</label>
            </Help>
            <input
              id="launch"
              type="number"
              min={2026}
              max={2040}
              value={draft.launchYear}
              onChange={(e) => set("launchYear", Number(e.target.value))}
            />
          </div>
        </Section>

        {/* 6 — UPTAKE ----------------------------------------------------- */}
        <Section id="uptake" title="6 · Uptake" summary={summaryFor("uptake")}>
          <div className="field">
            <Help spec={fields.get("uptake_curve")}>
              <label htmlFor="curve">Adoption curve</label>
            </Help>
            <select
              id="curve"
              value={draft.uptakeCurve}
              onChange={(e) =>
                set("uptakeCurve", e.target.value as Draft["uptakeCurve"])
              }
            >
              <option value="logistic">Logistic — entering an established class</option>
              <option value="linear">Linear — first-in-class</option>
            </select>
          </div>
          <Rate
            label="Year-1 uptake"
            fieldKey="uptake_year_1"
            path="uptake.year_1"
            value={draft.uptakeYear1}
            fallback="5.0% default"
            onChange={(v) => set("uptakeYear1", v)}
            errorField={errorField}
            guide={fields}
            min={0}
          />
          <Rate
            label="Terminal uptake"
            fieldKey="uptake_terminal"
            path="uptake.terminal"
            value={draft.uptakeTerminal}
            fallback="15.0% default"
            onChange={(v) => set("uptakeTerminal", v)}
            errorField={errorField}
            guide={fields}
            min={0}
          />
        </Section>

        {/* 7 — TREATMENT BEHAVIOUR ---------------------------------------- */}
        <Section
          id="treatment_behaviour"
          title="7 · Treatment behaviour"
          summary={summaryFor("treatment_behaviour")}
        >
          <Rate
            label="Weight regain per year"
            fieldKey="regain_per_year"
            path="outcomes.regain_per_year"
            value={draft.regainPerYear}
            fallback="0% — trials held the effect"
            onChange={(v) => set("regainPerYear", v)}
            errorField={errorField}
            guide={fields}
            min={0}
            max={50}
          />
          <p className="hint">
            Persistence is seeded per therapy from published claims analyses and
            is shown on the Prices tab. Raise regain and every avoided-event
            count from year 2 falls.
          </p>
        </Section>

        {/* 8 — OUTCOMES ---------------------------------------------------- */}
        <Section id="outcomes" title="8 · Outcomes" summary={summaryFor("outcomes")}>
          {shown?.outcomes ? (
            <>
              <Readout
                label="Mean weight change"
                value={
                  // Already a percentage from the API, not a fraction —
                  // `formatPercent` multiplies by 100 and rendered 14.9 as
                  // 1490.0%, disagreeing with the same figure on the
                  // Outcomes tab. Signed, because this is a weight *loss*.
                  shown.outcomes.mean_weight_loss_pct != null
                    ? `−${shown.outcomes.mean_weight_loss_pct.toFixed(1)}%`
                    : "—"
                }
                meaning={
                  shown.outcomes.responder_trial
                    ? `Reported by ${shown.outcomes.responder_trial}.`
                    : undefined
                }
              />
              <Readout
                label="Responder threshold"
                value={shown.outcomes.responder_threshold ?? "—"}
                meaning="Weight loss counted as a response."
              />
              {shown.outcomes.events.map((e) => (
                <Readout
                  key={e.event_class}
                  label={e.label}
                  value={`−${formatPercent(e.relative_reduction, 0)}`}
                  meaning={`Tier ${e.effect_provenance.confidence_tier} · ${e.trial}`}
                />
              ))}
            </>
          ) : (
            <p className="hint">
              Seeded from the trials. Run once to read them here.
            </p>
          )}
          <p className="hint">
            Effect sizes are evidence, not settings — they come from the trial
            that reported them and there is no override path to move them.
          </p>
        </Section>

        {/* 9 — HEALTHCARE COSTS -------------------------------------------- */}
        <Section
          id="healthcare_costs"
          title="9 · Healthcare costs"
          summary={summaryFor("healthcare_costs")}
        >
          {shown?.cost_bridge?.terms ? (
            <>
              {shown.cost_bridge.terms.map((t) => (
                <Readout
                  key={t.component}
                  label={t.component}
                  value={formatMoney(t.delta, shown.currency)}
                  meaning={
                    t.delta === 0
                      ? "No difference between the two worlds."
                      : `${formatMoney(t.new_therapy, shown.currency)} against ${formatMoney(t.displaced, shown.currency)}`
                  }
                />
              ))}
              <Readout
                label="Net cost per switch"
                value={formatMoney(
                  shown.cost_bridge.net_cost_per_switch,
                  shown.currency,
                )}
                meaning="What one switching patient costs above the care they leave."
              />
            </>
          ) : (
            <p className="hint">
              Drug, administration, monitoring, adverse events and offsets. Run
              once to read them here.
            </p>
          )}
          <p className="hint">
            Therapy prices are editable on the <b>Prices</b> tab. The other
            components are seeded per market and carry no override path.
          </p>
        </Section>

        {/* 10 — TIME HORIZON ----------------------------------------------- */}
        <Section id="time_horizon" title="10 · Time horizon" summary={summaryFor("time_horizon")}>
          <div className="row">
            <div className="field">
              <Help spec={fields.get("horizon_years")}>
                <label htmlFor="horizon">Horizon</label>
              </Help>
              <div className="rate-controls">
                <input
                  id="horizon"
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={draft.horizonYears}
                  onChange={(e) => set("horizonYears", Number(e.target.value))}
                  aria-label="Horizon, years"
                />
                <span className="val val-set horizon-val">
                  {draft.horizonYears}y
                </span>
              </div>
            </div>
            <div className="field">
              <Help spec={fields.get("reporting_currency")}>
                <label htmlFor="currency">Report in</label>
              </Help>
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
          </div>
        </Section>

        {/* 11 — PERSPECTIVE ----------------------------------------------- */}
        <Section id="perspective" title="11 · Perspective" summary={summaryFor("perspective")}>
          <div className="field">
            <Help spec={fields.get("perspective")}>
              <label>Whose budget</label>
            </Help>
            <div className="perspectives">
              {perspectives.map((p) => (
                <button
                  key={p.code}
                  type="button"
                  className={p.code === draft.perspective ? "persp on" : "persp"}
                  aria-pressed={p.code === draft.perspective}
                  onClick={() => set("perspective", p.code)}
                  title={p.description}
                >
                  <b>{p.label}</b>
                  <em>{p.description}</em>
                </button>
              ))}
            </div>
          </div>
        </Section>
      </div>

      <div className="studio-foot">
        <button type="button" className="run" onClick={onRun} disabled={busy}>
          {busy ? "Calculating…" : "Run scenario"}
        </button>
        <span className="studio-foot-note">
          {draft.countryCodes.length} market
          {draft.countryCodes.length === 1 ? "" : "s"} ·{" "}
          {draft.subgroupCodes.length || "all"} segment
          {draft.subgroupCodes.length === 1 ? "" : "s"} · {draft.horizonYears}y
        </span>
      </div>
    </aside>
  );
}
