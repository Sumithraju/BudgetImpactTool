/**
 * What every field and figure means, in plain English — M21 section 7.
 *
 * Keyed by the same dotted vocabulary the override system already uses, so a
 * field and its explanation cannot drift apart by name.
 *
 * **The audience is not a modeller.** Someone reading these may be seeing a
 * budget impact model for the first time. So: no undefined acronym, no term
 * that only makes sense once you already know the answer, and no sentence
 * that explains a word by using it. "Label-eligible", "horizon", "addressable"
 * and "incremental" are all words this file is not allowed to lean on.
 *
 * **Where this should eventually live.** M21 section 7 puts the glossary in
 * the backend, so one definition feeds the interface, the PDF, the deck and
 * the exported workbook. It is here for now, which means the exports carry
 * their own wording and the two can diverge. Moving it server-side is a swap
 * of this module's implementation, not of its callers.
 */
import type { HintContent } from "./Hint";

export const GLOSSARY: Record<string, HintContent> = {
  // --- scenario -----------------------------------------------------------
  "asset.name": {
    what: "The new medicine whose cost you are working out.",
    affects: "nothing on its own — it labels this run and the reports it produces.",
  },
  "scenario.indication": {
    what: "The condition being modelled. One condition, split further down into "
      + "the groups of patients inside it.",
    affects: "which patients, which existing treatments and which trial evidence apply.",
  },
  "scenario.launch_year": {
    what: "The year the new medicine goes on sale. Everything is counted from here.",
    affects: "the year labels, and which rival medicines have arrived by then.",
  },
  "scenario.horizon_years": {
    what: "How many years ahead you are asking the payer to look.",
    affects: "the running total, and how much the later years matter.",
    watchFor: "three to five years is the normal range. Beyond that, a different "
      + "kind of model is needed — this one assumes the world holds still.",
  },
  "scenario.reporting_currency": {
    what: "The currency the combined figures are shown in.",
    affects: "how it reads, not what it costs. Each country is worked out in its "
      + "own money first, then converted at the rate fixed when this run was made.",
  },
  "scenario.markets": {
    what: "The countries you are costing. Each gets its own patients, prices and answer.",
    affects: "everything — a medicine's price and a country's population both differ.",
  },

  // --- funnel -------------------------------------------------------------
  "funnel.diagnosis_rate": {
    what: "Out of everyone who has the condition, the share a doctor has actually "
      + "identified and written down.",
    affects: "every count below this point. Nobody can be prescribed something for "
      + "a condition no one has recorded they have.",
    watchFor: "obesity is widely under-recorded. A figure near 100% is usually how "
      + "many people have it, not how many have been told they have it.",
  },
  "funnel.treatment_rate": {
    what: "Out of the patients a doctor has diagnosed, the share on any treatment "
      + "at all today.",
    affects: "how much of today's spending the new medicine would take the place of.",
    watchFor: "a diagnosed but untreated patient adds cost when they start. Someone "
      + "already being treated mostly swaps one cost for another, which is cheaper "
      + "for the payer.",
  },
  "funnel.access_rate": {
    what: "Of the patients a doctor could prescribe this to, the share who can "
      + "actually get hold of it once the insurer or health service has decided "
      + "what it will pay for.",
    affects: "the final patient count, and so every cost figure that follows.",
    watchFor: "this is about who gets it paid for, not who is medically suitable. "
      + "Those are two different filters and both apply.",
  },
  "funnel.diseased": {
    what: "How many adults in this country have the condition, from published "
      + "national health statistics.",
    affects: "everything below it, and how the patients are split into groups.",
  },

  // --- uptake -------------------------------------------------------------
  "uptake.year_1": {
    what: "Out of everyone who could be given the new medicine, the share actually "
      + "on it in its first year on sale.",
    affects: "first-year spending — often the only year a payer will commit to.",
    watchFor: "a new medicine rarely reaches more than a few percent in year one, "
      + "however good it is. Prescribing habits move slowly.",
  },
  "uptake.terminal": {
    what: "The share on the new medicine by the last year you are looking at — "
      + "roughly where take-up levels off.",
    affects: "the running total more than almost any other single number here.",
  },

  // --- subgroups ----------------------------------------------------------
  "subgroup.share": {
    what: "Of all the adults with obesity, the share whose most serious other "
      + "condition is this one.",
    affects: "how many patients sit in each group, and what each group ends up costing.",
    watchFor: "this is not the same as how common each condition is. Someone with "
      + "obesity, diabetes and high blood pressure is counted once, in the most "
      + "serious group — adding the three published figures would count them three "
      + "times over.",
  },
  "subgroup.residual": {
    what: "Everyone with obesity and none of the conditions listed above. Worked "
      + "out as whatever is left over, so it is shown rather than typed in.",
    affects: "nothing you can set directly — it moves whenever the four above move.",
  },

  // --- outputs ------------------------------------------------------------
  "result.budget_impact": {
    what: "The extra money the payer spends because this medicine exists: what "
      + "they spend with it, minus what they would have spent without it.",
    affects: "this is the headline the whole model exists to produce.",
    watchFor: "it is not the price of the new medicine. Most of what it costs "
      + "replaces spending that was already happening.",
  },
  "result.cost_without": {
    what: "What the payer spends on these patients in a year if the new medicine "
      + "never arrives — today's treatments, carrying on as they are.",
  },
  "result.cost_with": {
    what: "What the payer spends on the same patients once the medicine arrives: "
      + "the ones who switch to it, plus everyone still on what they had before.",
  },
  "result.addressable": {
    what: "Patients who could realistically be treated — diagnosed, suitable, and "
      + "able to get it paid for. Far fewer than everyone who has the condition.",
  },
  "result.patients_on_new": {
    what: "Patients actually taking the new medicine that year, after allowing for "
      + "those who stop.",
    watchFor: "lower than the take-up figure suggests, because a good share of "
      + "people stop within the first year.",
  },
  "result.net_cost_per_switch": {
    what: "What one patient moving onto the new medicine costs the payer, after "
      + "taking off the cost of whatever they were on before.",
    watchFor: "this is the extra cost per patient, not the medicine's price.",
  },
  "result.affordability": {
    what: "The extra spending set against everything this country spends on health "
      + "in total.",
    watchFor: "measured against the whole health budget, not just the medicines "
      + "budget — so it looks smaller than it will feel to a pharmacy budget holder.",
  },
  "result.cumulative": {
    what: "Every year added together — the total extra spending the payer is being "
      + "asked to absorb.",
  },
};
