"""Launch-year landscape — M14, the impure half.

Reads pipeline entrants out of M12's registry and turns them into the engine's
`PipelineEntrant`. The projection arithmetic is in `biet_engine.landscape`.

Nothing here decides that an entrant *should* be modelled. That is a scenario
choice, made explicitly, because every entrant carries three assumptions the
evidence does not supply — that it is approved at all, when, and at what price.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from biet_engine.constants import (
    ENTRANT_DEFAULT_RAMP_YEARS,
    REGULATORY_LAG_YEARS,
    ConfidenceTier,
    ResolutionLevel,
)
from biet_engine.landscape import expected_entry_year
from biet_engine.models import PipelineEntrant, Provenance, Valued, Warning_

from ..constants.comparator import CompetitorClass
from ..models.comparator import ComparatorAsset
from ..repositories.comparator_asset import ComparatorAssetRepository

log = logging.getLogger("biet.landscape")


class LandscapeService:
    def __init__(self, session: Session) -> None:
        self._assets = ComparatorAssetRepository(session)

    def entrants(
        self, indication_id: int, *, launch_year: int, horizon_years: int,
    ) -> tuple[list[PipelineEntrant], list[Warning_]]:
        """Modellable pipeline entrants, and what was left out and why.

        An entrant is modellable only if it is promoted (it needs a price like
        any therapy) and carries an assumed plateau share (nothing else can
        supply one). Anything short of that is reported rather than guessed
        at — an entrant admitted on invented numbers is worse than one left
        out, because it changes the world-without invisibly.
        """
        rows = self._assets.list_for_indication(
            indication_id, competitor_class=CompetitorClass.PIPELINE.value,
        )

        modellable: list[PipelineEntrant] = []
        warnings: list[Warning_] = []

        for asset in rows:
            entry = self._entry_year(asset, launch_year)
            if entry is None:
                warnings.append(_skip(
                    asset, "no expected entry year, and no trial completion date to "
                    "derive one from",
                ))
                continue
            if entry > horizon_years:
                warnings.append(_skip(
                    asset, f"expected in year {entry}, after the {horizon_years}-year "
                    "horizon ends — it cannot affect a result that finishes first",
                ))
                continue
            if asset.drug_id is None:
                # M12's guard, in the one place it is genuinely reachable: an
                # entrant with no price cannot enter a calculation, and
                # dropping it silently would understate the world-without.
                warnings.append(_skip(
                    asset, "not promoted — it has no price or regimen, and an entrant "
                    "needs both like any other therapy",
                ))
                continue
            if asset.assumed_terminal_pct is None:
                warnings.append(_skip(
                    asset, "no assumed plateau share; nothing in the public record "
                    "supplies one and this module will not invent it",
                ))
                continue

            modellable.append(PipelineEntrant(
                drug_id=asset.drug_id,
                name=asset.asset_name,
                sponsor=asset.sponsor,
                entry_year=entry,
                terminal_share=Valued(
                    value=float(asset.assumed_terminal_pct),
                    provenance=Provenance(
                        source=(
                            "analyst assumption — no public source supplies a plateau "
                            "share for an unapproved asset"
                        ),
                        confidence_tier=ConfidenceTier.D,
                        resolution_level=ResolutionLevel.SCENARIO_OVERRIDE,
                    ),
                ),
                ramp_years=ENTRANT_DEFAULT_RAMP_YEARS,
            ))

        return modellable, warnings

    def pipeline_drug_ids(self, indication_id: int) -> set[int]:
        """Promoted therapies that are registered as *not yet marketed*.

        These must be kept out of the world-without unless the scenario
        explicitly projects the landscape. Promotion writes a `drugs` row, and
        `list_drugs_with_regimens` selects everything for the indication, so
        without this filter a Phase III asset joins the current market with a
        full incumbent share — asserting it is on sale today, which is exactly
        what M11 section 5.3 separates the pipeline bucket to avoid.
        """
        rows = self._assets.list_for_indication(
            indication_id, competitor_class=CompetitorClass.PIPELINE.value,
        )
        return {a.drug_id for a in rows if a.drug_id is not None}

    def preview(
        self, indication_id: int, *, launch_year: int, horizon_years: int,
    ) -> dict[str, object]:
        """What the market looks like at launch, without running a scenario."""
        modellable, warnings = self.entrants(
            indication_id, launch_year=launch_year, horizon_years=horizon_years,
        )
        return {
            "indication_id": indication_id,
            "launch_year": launch_year,
            "horizon_years": horizon_years,
            "regulatory_lag_years": REGULATORY_LAG_YEARS,
            "entrants": [
                {
                    "drug_id": e.drug_id,
                    "name": e.name,
                    "sponsor": e.sponsor,
                    "entry_year": e.entry_year,
                    "calendar_entry_year": launch_year + e.entry_year - 1,
                    "terminal_share": e.terminal_share.value,
                    "ramp_years": e.ramp_years,
                }
                for e in modellable
            ],
            "excluded": [
                {"code": w.code, "message": w.message} for w in warnings
            ],
        }

    @staticmethod
    def _entry_year(asset: ComparatorAsset, launch_year: int) -> int | None:
        """A stated entry year wins; otherwise derive one from the trial.

        Stated beats derived for the same reason an observed price beats a
        purchasing-power-derived one: someone looked at this asset and made a
        judgement, and a formula did not.
        """
        if asset.expected_entry_year is not None:
            return int(asset.expected_entry_year)
        if asset.primary_completion is not None:
            return expected_entry_year(
                asset.primary_completion.year,
                launch_year=launch_year,
                regulatory_lag_years=REGULATORY_LAG_YEARS,
            )
        return None


def _skip(asset: ComparatorAsset, why: str) -> Warning_:
    return Warning_(
        code="PIPELINE_ENTRANT_SKIPPED",
        message=f"{asset.asset_name} was not modelled as an entrant: {why}.",
    )


__all__ = ["LandscapeService"]
