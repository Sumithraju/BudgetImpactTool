/**
 * M15 section 9 — what to go and find out.
 *
 * Sits beside the tornado it reinterprets. A tornado ranks by how much each
 * assumption moves the answer; this ranks by how much it moves the answer
 * times how weakly it is founded. A parameter with the largest swing in the
 * model and a published country-specific source is settled, and the tornado
 * alone would have wrongly nominated it first.
 */
import { type EvidenceGap, type EvidenceGapReport } from "../../shared/api";
import { formatMoneyCompact } from "../../shared/format";

const BAND_ORDER = ["critical", "high", "medium", "sufficient"];

export function EvidencePriority({ report }: { report: EvidenceGapReport }) {
  if (report.gaps.length === 0) return null;

  const actionable = report.gaps.filter((g) => g.priority !== "sufficient");

  return (
    <section>
      <h2>What to find out next</h2>
      <p className="lede">
        {actionable.length === 0 ? (
          <>
            Nothing here is both influential and weakly founded. Every assumption that moves
            this answer rests on something published.
          </>
        ) : (
          <>
            {actionable.length === 1 ? "One assumption" : `${actionable.length} assumptions`}{" "}
            both move this answer and rest on something weak. Ranked by influence times
            evidence weakness — a large swing with a published source is settled, and a large
            swing with a placeholder is the reason the answer cannot yet be trusted.
          </>
        )}
      </p>

      <ol className="gaps">
        {report.gaps.map((gap) => (
          <Row key={gap.parameter_path} gap={gap} currency={report.currency} />
        ))}
      </ol>
    </section>
  );
}

function Row({ gap, currency }: { gap: EvidenceGap; currency: string }) {
  const band = BAND_ORDER.includes(gap.priority) ? gap.priority : "sufficient";
  return (
    <li className={`gap gap-${band}`}>
      <div className="gap-head">
        <span className="gap-band">{gap.priority}</span>
        <strong>{gap.label}</strong>
        <span className={`tier tier-${gap.confidence_tier}`}>{gap.confidence_tier}</span>
        <span className="gap-swing num">
          moves {formatMoneyCompact(gap.swing, currency)}
        </span>
      </div>
      <div className="gap-meter">
        <span className="gap-fill" style={{ width: `${gap.priority_score * 100}%` }} />
      </div>
      <div className="gap-source">
        {gap.has_provenance ? (
          <>Rests on: {gap.source}</>
        ) : (
          <em>No stated source — treated as a placeholder, whatever number is in it.</em>
        )}
      </div>
    </li>
  );
}
