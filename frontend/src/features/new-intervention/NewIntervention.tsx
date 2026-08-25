/**
 * The new intervention — what is being introduced, and what it costs.
 *
 * This is the world-*with* half of the comparison. Everything here is an
 * input; the panel computes one figure, the annual cost per patient, and it
 * is a sum of the four costs above it rather than a model output. The
 * distinction matters enough to be stated on screen: a reader must never
 * mistake this for the budget impact, which is incremental and comes from
 * the engine (non-negotiable 2).
 */
import { useMemo } from "react";
import { formatMoney } from "../../shared/format";

export interface InterventionDraft {
  name: string;
  route: string;
  dose: string;
  frequency: string;
  /** Acquisition cost per patient per year, in the reporting currency. */
  drugCost: number;
  adminCost: number;
  monitoringCost: number;
  aeCost: number;
}

export const EMPTY_INTERVENTION: InterventionDraft = {
  name: "",
  route: "SC",
  dose: "2.4 mg",
  frequency: "Weekly",
  drugCost: 0,
  adminCost: 0,
  monitoringCost: 0,
  aeCost: 0,
};

const ROUTES = ["Oral", "SC", "IV", "IM", "Other"] as const;
const FREQUENCIES = [
  "Once daily",
  "Twice daily",
  "Weekly",
  "Fortnightly",
  "Monthly",
  "Other",
] as const;

const COST_FIELDS: { key: keyof InterventionDraft; label: string; hint: string }[] = [
  { key: "drugCost", label: "Drug acquisition", hint: "Ex-manufacturer or net, per patient per year" },
  { key: "adminCost", label: "Administration", hint: "Injection visits, infusion chair time" },
  { key: "monitoringCost", label: "Monitoring", hint: "Consultations and laboratory tests" },
  { key: "aeCost", label: "Adverse-event management", hint: "Expected annual cost of managing events" },
];

interface NewInterventionProps {
  draft: InterventionDraft;
  currency: string;
  onChange: (next: InterventionDraft) => void;
}

export function NewIntervention({ draft, currency, onChange }: NewInterventionProps) {
  const total = useMemo(
    () => draft.drugCost + draft.adminCost + draft.monitoringCost + draft.aeCost,
    [draft],
  );

  const set = <K extends keyof InterventionDraft>(key: K, value: InterventionDraft[K]) =>
    onChange({ ...draft, [key]: value });

  return (
    <section className="panel">
      <h2 className="nsec">New intervention</h2>
      <p className="lede">
        The therapy being introduced. These costs describe the world <em>with</em> it;
        what the payer actually pays extra is the difference against current care, which
        the engine computes on the Results tab.
      </p>

      <div className="intervention-grid">
        <label className="field">
          <span className="field-head">Product name</span>
          <input
            type="text"
            value={draft.name}
            placeholder="Wegovy (semaglutide 2.4 mg)"
            onChange={(e) => set("name", e.target.value)}
          />
        </label>

        <label className="field">
          <span className="field-head">Route</span>
          <select value={draft.route} onChange={(e) => set("route", e.target.value)}>
            {ROUTES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field-head">Dose</span>
          <input
            type="text"
            value={draft.dose}
            onChange={(e) => set("dose", e.target.value)}
          />
        </label>

        <label className="field">
          <span className="field-head">Frequency</span>
          <select value={draft.frequency} onChange={(e) => set("frequency", e.target.value)}>
            {FREQUENCIES.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </label>
      </div>

      <h3 className="nsec">Annual cost per patient · {currency}</h3>
      <div className="intervention-grid">
        {COST_FIELDS.map(({ key, label, hint }) => (
          <label className="field" key={key}>
            <span className="field-head">{label}</span>
            <input
              type="number"
              min={0}
              step={100}
              value={draft[key] as number}
              onChange={(e) => set(key, (Number(e.target.value) || 0) as never)}
            />
            <span className="field-foot">{hint}</span>
          </label>
        ))}
      </div>

      <div className="intervention-total">
        <span className="tlab">Total annual cost per patient</span>
        <strong className="figure">{formatMoney(total, currency)}</strong>
        <span className="field-foot">
          A gross cost, not a budget impact — it counts nothing that this therapy displaces.
        </span>
      </div>
    </section>
  );
}
