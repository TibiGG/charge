# Charge: 2-minute demo

```bash
make demo          # API :8000 + UI :5173
make test          # the 5 judged constraints, as tests
```

Open **http://localhost:5173/?p=margaret**. Before going on stage, reset any live watch samples:
`curl -X DELETE localhost:8000/api/ingest/sample`

---

## Click path (≈2 min)

**0:00 Batteries (`/`), Margaret, 54**
- "Margaret has a Bupa MY Genomic Health report and an Apple Watch. These are her five batteries."
- Point at **Stamina: Topped up**. She spins three times a week.
- "Her charge is set by her **emptiest** battery, not her average. Spin can't make up for zero strength work."
- "There's no streak to break. Each battery covers the last 7 days, so a sick week doesn't punish you."
- Tap **Suppleness**. The sheet says "This aim is our weakest one" and the source chip reads **COMMERCIAL PROTOCOL**.
  "We show that openly. It proves the source tracking is real."
- Close the sheet. Tap **Read aloud** (lands well).

**0:35 "What should I do today?" (`/today`)**
- "One thing: **Power yoga with small hops**, 25 minutes, *Friday 5:45pm, when you're free*."
- "She already does yoga, so we adapted her habit. We didn't tell a 54-year-old to start weightlifting."
- Video: **Royal Osteoporosis Society**, from our curated shelf. "No YouTube search at runtime. Unvetted content can't be cited."
- "How sure are we? *We're confident this would help you (0.86)*." The genetics line is always shown:
  *This nudges your starting point. It doesn't tell you what will happen.*
- Point at the **latency badge**.

**1:05 "Why this?"** (or open `/today#why` directly)
- Walk the tree from the bottom up:
  0 strength days vs WHO's 2 → COL1A1 (GENOMOS, *peer-reviewed*) + post-menopause + Bupa PRS band →
  "loading your bones": Royal Osteoporosis Society → she does yoga → power yoga.
- Every node has a source chip with its evidence grade.
- Open **"The exact steps our checker took"**. These are the **real ProbLog proofs**
  (KBest explain). The disjoint proofs sum to 0.86. "Verifiable, not just claimed."

**1:35 Ask (`/ask`)**
- Tap *"How can I get stronger?"* → a sourced answer.
- Tap *"I have chest pain when I run"* → **I can't help with that one.** → *Talk to someone now* → 999/111.
- "Default-deny. A regex red-flag layer that nothing can overrule, then an allow-list, then decline.
  The refusal never explains itself in clinical terms, because that would be a health claim too."

**1:55 Close.** Switch the persona dropdown to **Dan** (lifts, no cardio → *Weights, then a 20 minute ride*)
or **Priya, 68** (age alone triggers the balance rule → *your daily walk, with balance moves*).
**Sam** shows the no-watch onboarding.

---

## Safety architecture (say this if asked)

- **Python does the arithmetic** (watch samples → 7-day metrics → vial fills).
- **ProbLog decides**: which action, how sure, and why. Every probabilistic clause carries an id;
  `rules.json` maps it to `sources.json`. `make test` fails if any rule, edge or threshold lacks a resolvable source.
- **The LLM is only a renderer.** Today it's off, and static templates do the work. If one is enabled, it can only
  paraphrase a template, and `validate_llm_output` rejects any new number or banned word, so we fall back to the template.
- Pipeline is wrapped in a 6s timeout. On timeout there's a deterministic, still-cited *"quick answer"*.

## Numbers you can quote

| | |
|---|---|
| Full pipeline p95 (20 runs) | ≈0.2s (test asserts < 4s) |
| Copy reading level | Flesch–Kincaid grade ≈1.4 (test asserts ≤ 6) |
| Scope-guard fixture | 25 in-scope answered, 27 out-of-scope → 100% routed to a human |
| Sources | 13, each graded: clinical guideline / peer-reviewed / commercial protocol |

## Live watch → vial (stretch)

`POST /api/ingest/sample` takes `{metric, value, unit, start, end, device, persona}`.
`metric` is an HK workout type (e.g. `TraditionalStrengthTraining`) or `exercise_minutes`; `value` is minutes.
The batteries screen polls every 3s, so the vial fills on its own.

**iOS Shortcut recipe** (build it on the iPhone; it also runs from the Watch):
1. Shortcuts → **+** → name it *Charge: strength done*.
2. Add **Get Contents of URL**:
   URL `http://<laptop-LAN-IP>:8000/api/ingest/sample`, Method **POST**, Request Body **JSON**:
   `metric` = `TraditionalStrengthTraining`, `value` = `20`, `unit` = `min`, `device` = `watch`, `persona` = `margaret`.
   (For real data, put **Find Health Samples** (Exercise Minutes, today) before it and pass *Value* instead of 20.)
3. Turn on **Show on Apple Watch**. Run the API with `--host 0.0.0.0` so the phone can reach it.

Backup if the Wi-Fi fails:
```bash
curl -X POST localhost:8000/api/ingest/sample -H 'content-type: application/json' \
  -d '{"metric":"TraditionalStrengthTraining","value":20,"persona":"margaret","device":"watch"}'
```
Margaret's **Strength** vial moves from *Room to grow* to *Ticking over* within 3s.

## Apple Health export

There is no public HealthKit web API. The real route is Health app → profile → *Export All Health Data* → `export.zip`.
Pick **Sam (no watch)** → *Choose my Health file*. The file is stream-parsed with `lxml.iterparse`, so a 1GB export doesn't OOM.
Fixture: `data/apple_health/sample_export.xml`.
