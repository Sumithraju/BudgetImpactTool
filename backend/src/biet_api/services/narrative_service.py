"""Narrative generation — M10 sections 5.1 to 5.5.

Two paths, and the choice between them is deliberate rather than a
fallback-of-last-resort. The deterministic path composes the narrative from
the engine's own numbers and always works. The model path asks Claude to
write the same account in better prose, then puts the result through
`validate_numbers` before anyone sees it — if the model invented, rounded
wrongly, or arithmetically derived any figure, the text is rejected and the
deterministic version is served instead.

That ordering is the whole design. Section 5.1's rule is that every number
in generated text originates from the deterministic engine, and the only way
to guarantee it is to check afterwards rather than to ask nicely in a prompt.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from biet_engine.models import AssumptionEntry, EngineInput, RetrievedChunk
from biet_engine.narrative import (
    MANDATORY_LIMITATIONS,
    NarrativeSection,
    build_assumption_register,
    filter_by_similarity,
    unsupported_numbers,
)

from ..schemas.calculation import CalculationResponse

log = logging.getLogger("biet.narrative")

MODEL = "claude-opus-5"
MAX_TOKENS = 8_000

#: Retrieval query per section. Written as the question the section answers,
#: because that is what the corpus was embedded on — chunks of guidance
#: prose, not keyword lists.
SECTION_QUERIES: dict[NarrativeSection, str] = {
    NarrativeSection.POPULATION: (
        "How should the eligible patient population be estimated for a budget impact analysis?"
    ),
    NarrativeSection.IMPACT: (
        "What time horizon and perspective should a budget impact analysis use?"
    ),
    NarrativeSection.AFFORDABILITY: (
        "How should budget impact be compared against an available healthcare budget?"
    ),
    NarrativeSection.UNCERTAINTY: (
        "How should uncertainty and sensitivity analysis be reported in a budget impact analysis?"
    ),
    NarrativeSection.LIMITATIONS: (
        "What limitations and assumptions must a budget impact analysis disclose?"
    ),
}


@dataclass
class Narrative:
    sections: dict[str, str]
    citations: list[RetrievedChunk]
    limitations: tuple[str, ...]
    assumptions: tuple[AssumptionEntry, ...]
    generated_by: str
    warnings: list[str] = field(default_factory=list)


def _fmt(amount: float, currency: str) -> str:
    """Money at the scale a reader actually says it aloud.

    The validator tolerates this rounding — "2.71 billion" is the same
    engine value as 2,711,990,388 presented for readability, not a
    fabricated one.
    """
    if abs(amount) >= 1e9:
        return f"{amount / 1e9:.2f} billion {currency}"
    if abs(amount) >= 1e6:
        return f"{amount / 1e6:.1f} million {currency}"
    return f"{amount:,.0f} {currency}"


class NarrativeService:
    def __init__(self, session: Any) -> None:
        self._session = session

    # ----------------------------------------------------------------- context

    def _numeric_context(self, result: CalculationResponse) -> list[float]:
        """Every number the narrative is allowed to contain.

        Assembled from the response itself, so the validator is checking
        against exactly what the engine produced — not a hand-maintained
        list that could drift.
        """
        values: list[float] = [
            result.totals.cumulative,
            float(result.totals.peak_year),
            float(result.launch_year),
            float(result.horizon_years),
            float(len(result.countries)),
            *result.totals.by_year,
        ]
        for country in result.countries:
            values.append(country.cumulative_budget_impact)
            if country.affordability:
                values.append(country.affordability.cumulative_ratio)
                values.append(country.affordability.cumulative_ratio * 100)
                values.append(country.affordability.health_budget)
            for stage in country.funnel:
                values.append(stage.value)
                if stage.factor is not None:
                    values.append(stage.factor)
                    values.append(stage.factor * 100)
            for year in country.years:
                values.extend([
                    year.addressable, year.patients_on_new, year.budget_impact,
                    year.net_cost_per_switch, year.uptake, year.uptake * 100,
                    float(year.calendar_year), float(year.year),
                ])
            values.append(country.new_therapy.unit_price)
            values.append(country.new_therapy.persistence_12m)
            values.append(country.new_therapy.persistence_12m * 100)
        return values

    def retrieve(self, section: NarrativeSection) -> list[RetrievedChunk]:
        """Guideline chunks supporting one section, above the similarity floor.

        An empty result is a documented state, not an error: the section is
        written without citations and a `NO_GROUNDING` warning travels with
        it (M10 section 6).
        """
        try:
            from fastembed import TextEmbedding

            from ..repositories.guideline import GuidelineRepository

            model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            query = next(iter(model.embed([SECTION_QUERIES[section]])))
            found = GuidelineRepository(self._session).search(query.tolist(), k=5)
            return list(filter_by_similarity(found))
        except Exception as exc:               # noqa: BLE001
            # Retrieval is an enhancement; losing it degrades citations, not
            # the narrative, so it must not take the whole export down.
            log.warning("retrieval_failed: %s", exc)
            return []

    # ----------------------------------------------------------------- generation

    def generate(
        self, result: CalculationResponse, engine_input: EngineInput,
    ) -> Narrative:
        citations: list[RetrievedChunk] = []
        seen: set[int] = set()
        for section in NarrativeSection:
            for chunk in self.retrieve(section):
                if chunk.chunk_id not in seen:
                    seen.add(chunk.chunk_id)
                    citations.append(chunk)

        warnings: list[str] = []
        if not citations:
            warnings.append(
                "NO_GROUNDING — no guideline passage cleared the similarity floor, "
                "so this narrative is uncited."
            )

        deterministic = self._compose(result)
        sections, generated_by = deterministic, "engine (deterministic)"

        drafted = self._draft_with_model(result, deterministic, citations)
        if drafted is not None:
            context = self._numeric_context(result)
            offending = {
                name: unsupported_numbers(text, context)
                for name, text in drafted.items()
            }
            bad = {name: nums for name, nums in offending.items() if nums}
            if bad:
                # The model produced a number the engine never computed.
                # Reject the whole draft rather than the offending section:
                # a narrative that is half-model and half-template reads
                # inconsistently, and the deterministic text is complete.
                warnings.append(
                    "NUMERIC_VALIDATION_FAILED — the drafted narrative contained "
                    f"figures absent from the engine output ({bad}); the "
                    "deterministic narrative was served instead."
                )
                log.warning("narrative_rejected offending=%s", bad)
            else:
                sections, generated_by = drafted, f"{MODEL} (validated)"

        return Narrative(
            sections=sections,
            citations=citations,
            limitations=MANDATORY_LIMITATIONS,
            assumptions=build_assumption_register(engine_input),
            generated_by=generated_by,
            warnings=warnings,
        )

    # ----------------------------------------------------------------- deterministic

    def _compose(self, r: CalculationResponse) -> dict[str, str]:
        """The narrative built straight from the engine's numbers.

        Always correct by construction — every figure is read from the
        result rather than written about it.
        """
        cur = r.totals.currency
        markets = ", ".join(c.country_code for c in r.countries)
        last_year = r.launch_year + r.horizon_years - 1
        biggest = max(r.countries, key=lambda c: c.cumulative_budget_impact)
        derived = [
            c.country_code for c in r.countries
            if c.new_therapy.price_basis == "ppp_derived"
        ]

        # Deliberately no cross-market total here. Summing addressable
        # populations in prose would state a number the engine never
        # computed and the response does not contain — the exact thing
        # `validate_numbers` rejects in a model draft, and the composer is
        # held to the same rule. The largest market is quoted instead,
        # because that figure is in the result.
        widest = max(r.countries, key=lambda c: c.years[-1].addressable)
        population = (
            f"Across {len(r.countries)} markets ({markets}), each funnel narrows from "
            f"national population through adult share, disease prevalence, diagnosis, "
            f"treatment, label eligibility and reimbursed access. The largest "
            f"addressable population is {widest.country_code}'s, at "
            f"{widest.years[-1].addressable:,.0f} patients in the final year of the "
            f"horizon. Every stage carries the source and confidence tier it was "
            f"resolved from."
        )

        impact = (
            f"Cumulative incremental budget impact over {r.horizon_years} years "
            f"({r.launch_year}–{last_year}) is {_fmt(r.totals.cumulative, cur)}, "
            f"peaking in year {r.totals.peak_year}. This is the incremental figure — "
            f"spend in the world with the asset minus the world without it — not the "
            f"gross cost of treating those patients. {biggest.country_code} carries the "
            f"largest share at "
            f"{_fmt(biggest.cumulative_budget_impact, biggest.currency)}."
        )

        banded = [c for c in r.countries if c.affordability]
        if banded:
            worst = max(banded, key=lambda c: c.affordability.cumulative_ratio)  # type: ignore[union-attr]
            affordability = (
                f"Against national health expenditure, every market falls in the "
                f"{worst.affordability.band} band or below.  "  # type: ignore[union-attr]
                f"{worst.country_code} is the most exposed at "
                f"{worst.affordability.cumulative_ratio * 100:.3f}% of its total health "  # type: ignore[union-attr]
                f"budget. Affordability is assessed against the whole national health "
                f"envelope rather than a pharmaceutical subset, which understates the "
                f"pressure on a drug budget specifically."
            )
        else:
            affordability = (
                "Affordability could not be assessed: no market in this scenario has a "
                "resolved health expenditure figure."
            )

        uncertainty = (
            "Uncertainty is characterised two ways. One-way sensitivity sweeps each "
            "assumption to its own bounds and ranks them by swing, which identifies "
            "where more evidence would most change the answer. Probabilistic analysis "
            "varies every uncertain input together and returns a distribution rather "
            "than a point estimate. Where the sampler has not converged, that is "
            "reported rather than smoothed over."
        )

        limitations = (
            "This is a decision-triage estimate, not an HTA submission model. "
            + (
                f"Prices for {', '.join(derived)} are derived through purchasing-power "
                f"parity from a reference market rather than observed, and are labelled "
                f"as derived wherever they appear. "
                if derived else ""
            )
            + "The full set of stated limitations accompanies this narrative."
        )

        return {
            NarrativeSection.POPULATION.value: population,
            NarrativeSection.IMPACT.value: impact,
            NarrativeSection.AFFORDABILITY.value: affordability,
            NarrativeSection.UNCERTAINTY.value: uncertainty,
            NarrativeSection.LIMITATIONS.value: limitations,
        }

    # ----------------------------------------------------------------- model path

    def _draft_with_model(
        self,
        result: CalculationResponse,
        deterministic: dict[str, str],
        citations: list[RetrievedChunk],
    ) -> dict[str, str] | None:
        """Ask Claude to rewrite the deterministic narrative more readably.

        Returns None when no credential is configured or the call fails —
        both are ordinary states here, not errors, because the deterministic
        narrative is a complete deliverable on its own.

        The model is given the already-correct text and asked to improve the
        prose, never to compute anything. That framing plus the validator on
        the way out is what makes the model path safe to offer at all.
        """
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return None

        try:
            import anthropic
        except ImportError:
            return None

        guidance = "\n\n".join(
            f"[{c.issuing_body}, {c.document_title}, p.{c.page_number}]\n{c.text}"
            for c in citations[:6]
        )

        system = (
            "You are writing the narrative section of a budget impact analysis for an "
            "internal pricing and market access audience.\n\n"
            "ABSOLUTE RULE: every number in your output must appear verbatim in the "
            "draft you are given. Do not compute, sum, average, convert, or infer any "
            "figure. Do not add a number that is not already in the draft. You may "
            "round a number for readability only if the rounded form is unambiguous "
            "(2,711,990,388 may become '2.71 billion'). Text containing any other "
            "number is rejected automatically and discarded.\n\n"
            "Improve clarity, flow and precision of language. Keep each section to one "
            "short paragraph. Use plain professional English, no marketing register, no "
            "bullet points. Return strict JSON with exactly the keys: "
            "population, impact, affordability, uncertainty, limitations."
        )

        user = (
            f"Draft to rewrite (JSON):\n{deterministic}\n\n"
            f"Relevant published guidance, for tone and framing only — do not take "
            f"numbers from it:\n{guidance or '(none retrieved)'}"
        )

        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in response.content if b.type == "text")
            import json

            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            return {
                key: str(parsed[key])
                for key in deterministic
                if key in parsed and isinstance(parsed[key], str)
            } or None
        except Exception as exc:               # noqa: BLE001
            log.warning("narrative_model_call_failed: %s", exc)
            return None
