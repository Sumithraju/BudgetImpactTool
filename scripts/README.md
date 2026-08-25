# scripts

## `demo_data.py` — placeholder dataset

Populates the database so every screen in the tool has something to show.

```bash
python scripts/demo_data.py status   # what is demo, what is seeded
python scripts/demo_data.py load
python scripts/demo_data.py purge    # removes exactly what load wrote
```

**Everything it writes is invented.** Not estimated, not analogue-derived —
invented, because a comparator discovered from Open Targets arrives without a
price or a regimen (M11 §5.7) and a demo that stops at *"7 therapies need
pricing"* never reaches the part worth showing.

Three things stop invented data being mistaken for evidence:

| | |
|---|---|
| **Tier D on every row** | Resolution raises `TIER_D_INPUT`, M15 ranks them critical, and they appear as placeholders in the assumption register of every export |
| **`DEMO PLACEHOLDER` in every `source`** | Visible in the interface, the register and the PDF — anywhere the value travels |
| **`purge` is exact** | Matched on that prefix, so the database returns to seeded-and-cited data with one command |

### What it adds

- **7 GLP-1 therapies** — exenatide, lixisenatide, albiglutide (marketed);
  retatrutide, survodutide, danuglipron, efinopegdutide (pipeline). Real
  ChEMBL identifiers, so registering them is idempotent with what discovery
  finds. A reference-market price only: M5 derives the other nine markets
  through purchasing-power parity and **labels them derived**, which is the
  honest treatment. Seeding a made-up price in ten markets would replace a
  labelled derivation with an unlabelled fabrication.
- **36 adverse-event unit costs** — the nine markets outside the USA, so
  `AE_COST_MISSING` stops firing on every run.
- **32 adverse-event incidences** — for the new therapies and for orlistat,
  so M13's asymmetry warning reflects a real gap rather than the demo's own.

### What it deliberately does not add

`AVEXITIDE` stays unpriced. It is a GLP-1 receptor *antagonist* developed for
post-bariatric hypoglycaemia — discovery finds it because it acts on GLP1R,
and it is not competing for these patients. Leaving it unpriced keeps a
working example of the `needs_pricing` flag on screen, and of the judgement
M11 §5.6 reserves for a human.

### Before showing anyone a number from this

Run `purge`. Then seed the real thing.
