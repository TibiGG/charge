# Charge

**One thing to do for each part of your day, and it always shows its working.**

Built in two days for the *Adeline Sprint Sessions · Health x AI Hackathon* (18 September 2026,
Google HQ London), for the Bupa challenge: *Connected Care — from treating illness to preventing it*.
**Placed in the top 3.**

Charge turns an Apple Watch feed and a Bupa MY Genomic Health report into a single, timely
suggestion for the morning, afternoon and evening — and every suggestion carries a plain-English
"why", a graded source for each step, and the probabilistic logic proof behind it.

| | |
|---|---|
| App | https://charge-bupa.vercel.app |
| API | https://charge-api-845717888369.europe-west2.run.app (Google Cloud Run, `europe-west2`) |
| Demo script | [`DEMO.md`](DEMO.md) |
| Backup screenshots | [`docs/demo-shots/`](docs/demo-shots) |
| Demo capture | `demo.mp4` |

> The hosted links depend on a hackathon lab GCP project and may be switched off. Everything runs
> locally with `make demo`.

---

## The idea

1. **Five batteries, not one score.** Strength · Cardio endurance · HIIT/VO2max · Balance &
   stability · Flexibility & mobility. Each is a rolling 7-day window against a sourced target.
2. **Your charge is set by your emptiest battery, not your average.** Three spin classes cannot
   make up for zero strength work. There is no streak to break.
3. **One action at a time.** `/today` shows three daypart cards; only the current one has a button.
4. **Accountability is the product.** Every card that recommends something carries a "why" and the
   logic behind it — including weak suggestions, "your afternoon looks full" fallbacks, and the
   deterministic quick answer. A test enforces this over every persona × time × kit × vote.
5. **The person has the last word.** Mixed evidence is shown as mixed, with an override; "more /
   less like this" votes are arguments that re-rank the next suggestion.

## How it works

```
Apple Watch / manual log ─┐
Bupa genome report ───────┼─► Python: rolling 7-day metrics, hard gates, top-8 candidates
Calendar (free/busy) ─────┤          │
Your kit + gym windows ───┘          ▼
                              ProbLog: weighted clauses  ──►  p(good(activity)) + proofs
                              (rules ← graded sources)         │
                                                               ▼
                                              Batteries · today's three cards · the "why"
```

- **Python owns the arithmetic** (`backend/app/aggregate.py`): samples → 7-day metrics → battery fills.
- **ProbLog owns the decision** (`backend/reasoner/model.pl`): which activity, how sure, and why.
  Every probabilistic clause carries an id; `reasoner/rules.json` maps that id to `data/sources.json`.
  A test fails the build if any rule, edge or threshold has no resolvable source.
- **Grounding stays small**: Python applies the deterministic hard gates (equipment, daypart, free
  slot, evidence > 0) and passes ~8 candidates to ProbLog, so the proof tree stays real and fast.
- **No LLM makes a health claim.** `backend/app/render.py` has an optional paraphrase hook whose
  output is rejected if it introduces a new number or a banned word. It is off; templates do the work.

### The model, in one example

```prolog
0.88::recommend(P, impact_loading, r_impact_loading) :-
    under_target(P, strength), shifted(P, bone_fragility).   % Royal Osteoporosis Society
0.62::marker_shifts(P, bone_fragility, e_prs_osteo) :- prs_band(P, osteoporosis, high).  % Bupa report
0.65::sleep_conflict(C, r_sleep_evening) :-                  % Sports Medicine 2019, MIXED evidence
    cand_intensity(C, vigorous), ends_near_bedtime(C), \+ user_override(sleep).
kit_ok(C) :- cand(C), \+ missing_kit(C).                     % what you own, and when you can reach it
good(C) :- good_raw(C), \+ sleep_conflict(C).
```

Ranking: `deficit × evidence × daypart fit × habit fit × taste × kit × (1 − sleep conflict)`.
Deficit stays the primary driver — a nice morning-yoga heuristic never buries three weeks of no
strength work.

## Screens

| Tab | What it does |
|---|---|
| **Welcome** | Simulated sign-up (Bupa / Google / email) and wearable connect. Nothing is sent. |
| **Batteries** | Five vials, the emptiest highlighted; tap one for what it is, where you are, what people aim for, and the source. |
| **Today** | Morning / afternoon / evening. The live card has the action; the others open to read. "Why this?" and "Check the logic" on every card. |
| **Activity** | Watch sync (synthetic) plus manual logs. Before saving you see exactly which batteries a log will fill, and can change the ticks. |
| **User** | Age, habits, kit at home (mat, chair, dumbbells, band, bike, or nothing at all), gym kit and the time windows you can actually get there. All of it becomes facts in the logic. |
| **Ask** | Default-deny scope guard. Clinical questions ("chest pain when I run") are routed to a human, never answered. |

## Design constraints, enforced by tests

- **Reading level** of the app's own text: Flesch–Kincaid ≈2.8 (test asserts ≤ 6).
- **No jargon, no banned words** ("risk of", "prevents", "you will", …) anywhere a user can see.
- **WCAG AA contrast**, 48px+ targets, 18px base, never red for a low battery.
- **Every threshold, rule and edge resolves to one of 14 graded sources** (clinical guideline /
  peer-reviewed / commercial protocol). The weakest one (a flexibility target from a commercial
  protocol) is labelled as weak *in the UI*.
- **Every recommended activity always has a why + its logic** — swept over persona × time of day ×
  kit × votes × override.
- **p95 latency < 4s** for a full day with proofs (~0.3s locally, ~1.2s on Cloud Run).
- **Refusals never explain themselves clinically** — that would be a health claim too.

`make test` → 92 tests.

## Run it

```bash
make setup     # python3.11 venv + npm install
make demo      # API on :8000, UI on :5173  →  http://localhost:5173/?p=margaret
make test      # 92 tests
```

Personas: `margaret` (54, post-menopause, genome report, spins, no strength work — the demo path),
`priya` (68, balance), `dan` (36, gym, lifts, no cardio), `sam` (no watch → onboarding).
Pin the clock with `?at=HH:MM`, e.g. `/today?p=dan&at=19:30` for the mixed-evidence sleep notice.

### Deploy

```bash
make deploy-web                  # SvelteKit → Vercel
make deploy-api PROJECT=<id>     # builds locally, pushes to Artifact Registry, deploys to Cloud Run
```

`deploy-api` builds and pushes the image rather than using `gcloud run deploy --source`, because the
hackathon lab project's Cloud Build service account could not read source uploads. The container
runs a ProbLog smoke test **and** a model smoke test at build time, so a broken rule fails the build
instead of the demo. `--min-instances=1` keeps one instance warm (no 10–20s cold start on a judge's
first click); drop it to 0 to stop paying for an idle service.

## Layout

```
backend/
  app/        main.py (API) · day.py (three cards, prefilter, ensure_why) · aggregate.py (metrics)
              schedule.py (free slots, gym windows) · render.py (sentences, bands, LLM guard)
              scope_guard.py (default-deny) · pipeline.py
  reasoner/   model.pl (the logic program) · rules.json (clause id → source) · engine.py (ProbLog)
  data/       personas · genome · calendar · catalog.json (26 activities) · sources.json · targets.json
  Dockerfile  build-time ProbLog + model smoke tests
frontend/src/
  routes/     welcome · / (batteries) · today · activity · user · ask
  lib/        DayCard · Vial · Why · SourceChip · Latency · Speak · copy.ts (all UI text, one file)
tests/        test_reasoner.py · test_constraints.py (the judged constraints, as tests) · test_ingest.py
scripts/      generators for personas, catalog and Apple Health fixtures
```

All user-visible copy lives in `frontend/src/lib/copy.ts` so the reading-level and banned-word tests
can read it.

## Honest gaps

- **No Health AI Developer Foundations model (MedGemma) is wired in.** The hackathon asked for one;
  we ran out of time. The intended fit was narrow by design: MedGemma paraphrasing a fixed template
  behind `validate_llm_output`, never making a decision.
- **Personas are synthetic.** No real member data has ever touched this.
- **The flexibility/mobility target is a placeholder** from a commercial protocol, not a clinical
  guideline. It is flagged as such in the app.
- **Manual logs, votes and kit live in the browser** (localStorage) and are sent with each request.
  Stateless by design for Cloud Run — but not an account system.
- **The sleep rule needs watch sleep data**; with no data we drop the rule entirely rather than
  guess a bedtime.

## Credits

Built at the Adeline Sprint Sessions · Health x AI Hackathon.
Organised by **Adeline Arts & Science** · Tech & venue **Google** · Healthcare **Bupa** ·
VC **AlbionVC** · Banking **HSBC Innovation Banking**.

Evidence sources are cited in `backend/data/sources.json`, each with a grade, a claim and a URL:
WHO 2020 physical activity guidelines, the Royal Osteoporosis Society's *Strong, Steady and
Straight*, GENOMOS (COL1A1), Frayling et al. and Kilpeläinen et al. (FTO), Stutz et al. 2019
(evening exercise and sleep), and Bupa's own genomic-health product pages.
