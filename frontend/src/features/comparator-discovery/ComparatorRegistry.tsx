/**
 * M12 section 9 — the registry, and the promotion that makes a discovered
 * molecule usable.
 *
 * Discovery yields a molecule. M5 needs a price, a regimen and a persistence
 * figure, and no public target database carries any of the three. This is
 * where a curator supplies them, and every field demands a source: a value
 * without one is a placeholder, whatever number is in it.
 */
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type CountryOption,
  type PromotionRequest,
  type RegisteredAsset,
} from "../../shared/api";

interface Props {
  indicationId: number;
  countries: CountryOption[];
  /** Bumped by the discovery panel when it registers something, so the
   *  registry reloads without either component owning the other's state. */
  reloadToken: number;
}

export function ComparatorRegistry({ indicationId, countries, reloadToken }: Props) {
  const [assets, setAssets] = useState<RegisteredAsset[]>([]);
  const [promoting, setPromoting] = useState<RegisteredAsset | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listAssets(indicationId)
      .then(setAssets)
      .catch((e: ApiError) => setError(e.message));
  }, [indicationId]);

  useEffect(load, [load, reloadToken]);

  if (assets.length === 0) return null;

  return (
    <section className="comparator-registry">
      <h2>Comparator registry</h2>
      <p className="lede">
        What this system knows about each molecule, and what still stands between it and a
        calculation. An unpromoted comparator is not quietly dropped from the world-without —
        naming it in a scenario fails, by name.
      </p>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      <table className="registry-table">
        <thead>
          <tr>
            <th>Molecule</th>
            <th>Class</th>
            <th>Stage</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.asset_id} className={asset.is_promoted ? "" : "unpromoted"}>
              <td>
                <strong>{asset.asset_name}</strong>
                {asset.brand_name && <span className="brand"> {asset.brand_name}</span>}
                <div className="sub">{asset.target_symbol}</div>
              </td>
              <td>{asset.competitor_class}</td>
              <td className="mono">{asset.max_clinical_stage.replace("_", " ")}</td>
              <td>
                {asset.is_promoted ? (
                  <span className="ok">usable</span>
                ) : (
                  <span className="gap">
                    needs {asset.missing_for_promotion.join(", ")}
                  </span>
                )}
              </td>
              <td>
                <button type="button" onClick={() => setPromoting(asset)}>
                  {asset.is_promoted ? "Edit pricing" : "Add pricing"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {promoting && (
        <PromotionForm
          asset={promoting}
          countries={countries}
          onClose={() => setPromoting(null)}
          onDone={() => {
            setPromoting(null);
            load();
          }}
        />
      )}
    </section>
  );
}

const DEFAULT_REGIMEN = {
  dose_amount: 1,
  dose_unit: "mg",
  units_per_admin: 1,
  admins_per_year: 52,
  wastage_pct: 0,
  persistence_12m: 0.65,
  source: "",
  confidence_tier: "C",
};

function PromotionForm({
  asset,
  countries,
  onClose,
  onDone,
}: {
  asset: RegisteredAsset;
  countries: CountryOption[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [regimen, setRegimen] = useState(DEFAULT_REGIMEN);
  const [countryCode, setCountryCode] = useState(countries[0]?.country_code ?? "USA");
  const [price, setPrice] = useState(0);
  const [priceSource, setPriceSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currency =
    countries.find((c) => c.country_code === countryCode)?.currency_code ?? "USD";

  const submit = useCallback(async () => {
    setBusy(true);
    setError(null);
    const body: PromotionRequest = {
      regimen: { ...regimen, confidence_tier: "C" },
      prices: [
        {
          country_code: countryCode,
          price_local: price,
          // The market's own currency, never a chosen one — a euro price
          // filed against Japan computes a plausible, wrong annual cost.
          currency_code: currency,
          price_basis: "list",
          source: priceSource,
          confidence_tier: "C",
        },
      ],
    };
    try {
      await api.promoteAsset(asset.asset_id, body);
      onDone();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }, [asset.asset_id, regimen, countryCode, currency, price, priceSource, onDone]);

  const ready = regimen.source.trim() !== "" && priceSource.trim() !== "" && price > 0;

  return (
    <div className="promotion-form">
      <h3>Pricing for {asset.asset_name}</h3>
      <p className="sub">
        Discovery found the molecule. A price, a regimen and a persistence figure are what M5
        needs, and no public target database carries any of them.
      </p>

      <div className="promotion-grid">
        <label>
          Units per administration
          <input
            type="number"
            value={regimen.units_per_admin}
            onChange={(e) =>
              setRegimen({ ...regimen, units_per_admin: Number(e.target.value) })
            }
          />
        </label>
        <label>
          Administrations per year
          <input
            type="number"
            value={regimen.admins_per_year}
            onChange={(e) =>
              setRegimen({ ...regimen, admins_per_year: Number(e.target.value) })
            }
          />
        </label>
        <label>
          12-month persistence
          <input
            type="number"
            step="0.01"
            min="0.01"
            max="1"
            value={regimen.persistence_12m}
            onChange={(e) =>
              setRegimen({ ...regimen, persistence_12m: Number(e.target.value) })
            }
          />
        </label>
        <label>
          Regimen source
          <input
            value={regimen.source}
            onChange={(e) => setRegimen({ ...regimen, source: e.target.value })}
            placeholder="e.g. FDA label, 2024"
          />
        </label>
        <label>
          Market
          <select value={countryCode} onChange={(e) => setCountryCode(e.target.value)}>
            {countries.map((c) => (
              <option key={c.country_code} value={c.country_code}>
                {c.country_name} ({c.currency_code})
              </option>
            ))}
          </select>
        </label>
        <label>
          Unit price ({currency})
          <input
            type="number"
            value={price}
            onChange={(e) => setPrice(Number(e.target.value))}
          />
        </label>
        <label>
          Price source
          <input
            value={priceSource}
            onChange={(e) => setPriceSource(e.target.value)}
            placeholder="e.g. Lauer-Taxe, Aug 2026"
          />
        </label>
      </div>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      <div className="promotion-actions">
        <button type="button" onClick={submit} disabled={busy || !ready}>
          {busy ? "Saving…" : "Promote"}
        </button>
        <button type="button" className="ghost" onClick={onClose}>
          Cancel
        </button>
        {!ready && (
          <span className="sub">
            Both sources are required. A value with no stated origin is a placeholder,
            whatever number is in it.
          </span>
        )}
      </div>
    </div>
  );
}
