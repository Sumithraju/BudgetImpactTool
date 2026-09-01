/**
 * The results, as tabs rather than as one long scroll.
 *
 * A budget-impact result answers about eight different questions, and the
 * person reading it has one of them at a time. Stacked vertically they compete:
 * whatever is at the top wins, everything below it is found by scrolling past
 * things the reader did not ask for, and the panel that answers the actual
 * question is the one nobody reaches.
 *
 * The tab order is the order a formulary conversation runs in — what does it
 * cost, what does it buy, who pays, where is it concentrated, how sure are we,
 * what should we go and find out. Summary is first because it is the answer;
 * everything after it is the working.
 */

import { useMemo, useState } from "react";
import type {
  BreakEven,
  Calculation,
  EvidenceGapReport,
  Owsa,
  Psa,
  UptakeScenarios,
} from "../../shared/api";
import { Tabs, TabPanel, type TabDef } from "../../shared/ui";
import { PopulationTab } from "./tabs/PopulationTab";
import { AffordabilityTab } from "./tabs/AffordabilityTab";
import { MarketAccessTab } from "./tabs/MarketAccessTab";
import { SummaryTab } from "./tabs/SummaryTab";
import { OutcomesTab } from "./tabs/OutcomesTab";
import { PayerTab } from "./tabs/PayerTab";
import { SubgroupsTab } from "./tabs/SubgroupsTab";
import { UncertaintyTab } from "./tabs/UncertaintyTab";
import { DeliverableTab } from "./tabs/DeliverableTab";

export function ResultsView({
  calculation,
  owsa,
  psa,
  gaps,
  bands,
  breakEven,
  uptakeCases,
  analysisBusy,
}: {
  calculation: Calculation;
  owsa: Owsa | null;
  psa: Psa | null;
  gaps: EvidenceGapReport | null;
  bands: Record<string, number>;
  breakEven: BreakEven | null;
  uptakeCases: UptakeScenarios | null;
  analysisBusy: boolean;
}) {
  const [active, setActive] = useState("population");

  const outcomeCount = useMemo(
    () =>
      calculation.countries.reduce(
        (total, c) =>
          total +
          (c.outcomes?.events.reduce((n, e) => n + e.total_avoided, 0) ?? 0),
        0,
      ),
    [calculation],
  );

  const tabs: TabDef[] = [
    // The order a budget-impact conversation actually runs in: who are the
    // patients, can the market pay, what would it take to get reimbursed —
    // and only then the headline number and everything behind it.
    { id: "population", label: "Population funnel", hint: "where the patients come from", icon: "funnel" },
    { id: "affordability", label: "Affordability", hint: "can the market pay", icon: "affordability" },
    { id: "access", label: "Market access", hint: "price & break-even", icon: "access" },
    { id: "summary", label: "Budget impact", hint: "with vs without", icon: "impact" },
    {
      id: "outcomes",
      label: "What it buys",
      hint: "events avoided",
      icon: "buys",
      badge: outcomeCount >= 1 ? Math.round(outcomeCount).toLocaleString("en-US") : null,
    },
    {
      id: "subgroups",
      label: "Subgroups",
      hint: "where it lands",
      icon: "subgroups",
      badge: calculation.subgroups.length || null,
    },
    { id: "payer", label: "Payer view", hint: "PMPM & uptake cases", icon: "payer" },
    { id: "uncertainty", label: "Uncertainty", hint: "and what to learn", icon: "uncertainty" },
    {
      id: "deliverable",
      label: "Report",
      hint: "narrative & export",
      icon: "report",
      badge: calculation.warnings.length || null,
    },
  ];

  return (
    <div className="results-shell">
      <Tabs tabs={tabs} active={active} onChange={setActive} />

      <TabPanel id="population" active={active}>
        <PopulationTab calculation={calculation} />
      </TabPanel>
      <TabPanel id="affordability" active={active}>
        <AffordabilityTab calculation={calculation} bands={bands} />
      </TabPanel>
      <TabPanel id="access" active={active}>
        <MarketAccessTab
          calculation={calculation}
          breakEven={breakEven}
          busy={analysisBusy}
        />
      </TabPanel>
      <TabPanel id="summary" active={active}>
        <SummaryTab calculation={calculation} psa={psa} />
      </TabPanel>
      <TabPanel id="outcomes" active={active}>
        <OutcomesTab calculation={calculation} />
      </TabPanel>
      <TabPanel id="subgroups" active={active}>
        <SubgroupsTab calculation={calculation} />
      </TabPanel>
      <TabPanel id="payer" active={active}>
        <PayerTab
          calculation={calculation}
          breakEven={breakEven}
          uptakeCases={uptakeCases}
          busy={analysisBusy}
        />
      </TabPanel>
      <TabPanel id="uncertainty" active={active}>
        <UncertaintyTab owsa={owsa} psa={psa} gaps={gaps} busy={analysisBusy} />
      </TabPanel>
      <TabPanel id="deliverable" active={active}>
        <DeliverableTab calculation={calculation} />
      </TabPanel>
    </div>
  );
}
