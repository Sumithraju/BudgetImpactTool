/**
 * M11 section 9 — the comparator basket.
 *
 * Three grouped lists rather than one ranked one, because "approved and
 * competing today" and "will be competing by year three" are different facts
 * and merging them would let a Phase III asset silently enter the
 * world-without. Nothing is pre-selected: whether a drug is a real comparator
 * depends on line of therapy, formulary position and clinical positioning,
 * none of which the source databases know (M11 section 5.6).
 */
import { useCallback, useState } from "react";
import { warningLabel } from "../../shared/format";
import {
  api,
  type ApiError,
  type ComparatorBasket,
  type DiscoveredDrug,
  type IndicationOption,
} from "../../shared/api";

interface Props {
  indications: IndicationOption[];
  /** Lifted so the scenario builder can consume the selection. */
  onSelectionChange?: (selected: DiscoveredDrug[]) => void;
  /** Called after a molecule is registered, so the registry reloads. */
  onRegistered?: () => void;
  /** Reported upward so the registry knows which indication to show. */
  onIndicationChange?: (indicationId: number) => void;
}

const GROUPS = [
  {
    key: "direct" as const,
    title: "Direct competitors",
    blurb: "Same indication, same target, same mechanism — the closest thing to a like-for-like swap.",
  },
  {
    key: "therapeutic" as const,
    title: "Therapeutic competitors",
    blurb: "Same indication, different mechanism. Competing for the same patients by a different route.",
  },
  {
    key: "pipeline" as const,
    title: "Pipeline entrants",
    blurb: "Not marketed today, so not part of the world-without — but possibly part of it by the time this asset launches.",
  },
];

export function ComparatorDiscovery({
  indications,
  onSelectionChange,
  onRegistered,
  onIndicationChange,
}: Props) {
  const [target, setTarget] = useState("GLP1R");
  const [indicationId, setIndicationId] = useState(indications[0]?.indication_id ?? 1);
  const [mechanism, setMechanism] = useState("agonist");
  const [includePathway, setIncludePathway] = useState(false);

  const [basket, setBasket] = useState<ComparatorBasket | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Source ids currently being registered, so a row can show its own
   *  progress without a spinner over the whole basket. */
  const [registering, setRegistering] = useState<Set<string>>(new Set());
  const [registered, setRegistered] = useState<Set<string>>(new Set());

  const register = useCallback(
    async (drug: DiscoveredDrug) => {
      setRegistering((c) => new Set(c).add(drug.source_id));
      setError(null);
      try {
        await api.registerAsset({
          source_id: drug.source_id,
          asset_name: drug.name,
          indication_id: indicationId,
          target_symbol: drug.target_symbol,
          mechanism_of_action: drug.mechanism_of_action,
          action_type: drug.action_type,
          pathway_ids: drug.pathway_ids,
          drug_type: drug.drug_type,
          max_clinical_stage: drug.max_clinical_stage,
          competitor_class: drug.competitor_class,
          relevance: drug.relevance,
          rationale: drug.rationale,
          // The retrieval is the source, and it is dated by the server.
          source: drug.sources.join("+") || "open_targets",
          confidence_tier: "B",
        });
        setRegistered((c) => new Set(c).add(drug.source_id));
        onRegistered?.();
      } catch (e) {
        setError((e as ApiError).message);
      } finally {
        setRegistering((c) => {
          const next = new Set(c);
          next.delete(drug.source_id);
          return next;
        });
      }
    },
    [indicationId, onRegistered],
  );

  const discover = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const found = await api.discover(
        target.trim(),
        indicationId,
        mechanism.trim() || null,
        includePathway,
      );
      setBasket(found);
      // A fresh basket clears the selection rather than carrying it over:
      // a tick against a drug that is no longer in the list is a claim the
      // user never made.
      setSelected(new Set());
      onSelectionChange?.([]);
    } catch (e) {
      setError((e as ApiError).message);
      setBasket(null);
    } finally {
      setBusy(false);
    }
  }, [target, indicationId, mechanism, includePathway, onSelectionChange]);

  const toggle = useCallback(
    (drug: DiscoveredDrug) => {
      setSelected((current) => {
        const next = new Set(current);
        if (next.has(drug.source_id)) next.delete(drug.source_id);
        else next.add(drug.source_id);

        if (basket && onSelectionChange) {
          const all = [...basket.direct, ...basket.therapeutic, ...basket.pipeline];
          onSelectionChange(all.filter((d) => next.has(d.source_id)));
        }
        return next;
      });
    },
    [basket, onSelectionChange],
  );

  return (
    <section className="comparator">
      <h2>Comparator discovery</h2>
      <p className="lede">
        The comparator set defines the world without the new asset. Enter the molecular target
        and the indication; marketed and late-stage therapies acting on that target are
        returned classified and ranked, each with the rationale behind its score.
      </p>

      <div className="comparator-controls">
        <label>
          Target
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="GLP1R or ENSG00000112164"
          />
        </label>
        <label>
          Indication
          <select
            value={indicationId}
            onChange={(e) => {
              setIndicationId(Number(e.target.value));
              onIndicationChange?.(Number(e.target.value));
            }}
          >
            {indications.map((i) => (
              <option key={i.indication_id} value={i.indication_id}>
                {i.indication_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mechanism
          <input
            value={mechanism}
            onChange={(e) => setMechanism(e.target.value)}
            placeholder="agonist"
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={includePathway}
            onChange={(e) => setIncludePathway(e.target.checked)}
          />
          <span>
            Search the whole pathway
            <small>
              Finds competitors acting on a different target — slower, several more lookups.
            </small>
          </span>
        </label>
        <button type="button" onClick={discover} disabled={busy || !target.trim()}>
          {busy ? "Searching…" : "Discover comparators"}
        </button>
      </div>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {basket && (
        <>
          <div className="comparator-meta">
            <span>
              {basket.target_symbol} · {basket.target_id}
            </span>
            <span>{basket.indication_name}</span>
            {basket.pathway_ids.length > 0 && (
              <span>{basket.pathway_ids.length} Reactome pathways</span>
            )}
          </div>

          {basket.warnings.map((w) => (
            <div key={warningLabel(w.code)} className="warning" role="status">
              <strong>{warningLabel(w.code)}</strong> {w.message}
            </div>
          ))}

          {GROUPS.map(({ key, title, blurb }) => (
            <Group
              key={key}
              title={title}
              blurb={blurb}
              drugs={basket[key]}
              selected={selected}
              onToggle={toggle}
              onRegister={register}
              registering={registering}
              registered={registered}
            />
          ))}

          {basket.excluded.length > 0 && (
            <details className="comparator-excluded">
              <summary>
                {basket.excluded.length} retrieved and excluded — indicated for a different disease
              </summary>
              <ul>
                {basket.excluded.map((d) => (
                  <li key={d.source_id}>
                    {d.name} — {d.indications.slice(0, 3).join(", ") || "no indication listed"}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function Group({
  title,
  blurb,
  drugs,
  selected,
  onToggle,
  onRegister,
  registering,
  registered,
}: {
  title: string;
  blurb: string;
  drugs: DiscoveredDrug[];
  selected: Set<string>;
  onToggle: (drug: DiscoveredDrug) => void;
  onRegister: (drug: DiscoveredDrug) => void;
  registering: Set<string>;
  registered: Set<string>;
}) {
  return (
    <div className="comparator-group">
      <h3>
        {title} <span className="count">{drugs.length}</span>
      </h3>
      <p className="group-blurb">{blurb}</p>
      {drugs.length === 0 ? (
        <p className="empty-row">None found.</p>
      ) : (
        <ul className="comparator-list">
          {drugs.map((drug) => (
            <Row
              key={drug.source_id}
              drug={drug}
              checked={selected.has(drug.source_id)}
              onToggle={onToggle}
              onRegister={onRegister}
              busy={registering.has(drug.source_id)}
              done={registered.has(drug.source_id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({
  drug,
  checked,
  onToggle,
  onRegister,
  busy,
  done,
}: {
  drug: DiscoveredDrug;
  checked: boolean;
  onToggle: (drug: DiscoveredDrug) => void;
  onRegister: (drug: DiscoveredDrug) => void;
  busy: boolean;
  done: boolean;
}) {
  return (
    <li className={drug.needs_pricing ? "comparator-row unpriced" : "comparator-row"}>
      <label>
        <input type="checkbox" checked={checked} onChange={() => onToggle(drug)} />
        <div className="comparator-row-body">
          <div className="comparator-row-head">
            <strong>{drug.name}</strong>
            <span className="stage">{drug.max_clinical_stage.replace("_", " ")}</span>
            <span className="target">{drug.target_symbol}</span>
            <span className="relevance">{(drug.relevance * 100).toFixed(0)}</span>
          </div>

          {drug.mechanism_of_action && <div className="moa">{drug.mechanism_of_action}</div>}

          {/* The factor ticks, so the score is checkable rather than trusted. */}
          <div className="factors">
            {drug.factors.map((f) => (
              <span key={f.name} className={f.matched ? "factor on" : "factor off"}>
                {f.matched ? "✓" : "✗"} {f.name}
              </span>
            ))}
          </div>

          <div className="rationale">{drug.rationale}</div>

          {drug.needs_pricing && (
            <div className="needs-pricing">
              No price or regimen seeded. Discovery finds a molecule, not a cost — this cannot
              enter a calculation until both are supplied.
            </div>
          )}

          <div className="row-actions">
            <button
              type="button"
              className="ghost"
              disabled={busy || done}
              onClick={(e) => {
                // The row's label toggles the checkbox; registering is a
                // different act and must not also tick the box.
                e.preventDefault();
                onRegister(drug);
              }}
            >
              {done ? "In registry" : busy ? "Registering…" : "Add to registry"}
            </button>
          </div>
        </div>
      </label>
    </li>
  );
}
