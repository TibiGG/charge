# Charge: 2-minute demo (current as of the three-card Today, Activity and User tabs)

```bash
make demo          # API :8000 + UI :5173
make test          # the 5 judged constraints, as tests
```

Open **http://localhost:5173/?p=margaret** (or the deployed https://charge-health.vercel.app).

---

## Click path (≈2 min, Margaret, 54)

Before going on stage, clear this browser's demo state (votes, logs, kit, sync) from the browser console:
`localStorage.clear()`. Pin the time of day with `?at=` if you need a fixed demo, e.g. `/today?at=08:00`.

**(Optional, 10s) Welcome (`/welcome`)**: *Sign in with Bupa* → *Apple Watch* → "We found 14 days of workouts and sleep." Simulated: nothing is sent.

**0:00 Batteries (`/?p=margaret`)**
- "Five batteries from her Apple Watch. Her charge is set by her **emptiest** one, not her average."
- Strength: **Room to grow**, 0 of 2 days. Cardio: **Topped up**, because she spins. "Spin can't make up for zero strength work."
- "No streak to break. Each battery looks at the last 7 days."

**0:25 Today (`/today`)**
- Three cards: **Morning · Afternoon · Evening**. Only the current one has a button, so there's one action on screen.
- At 08:00: **Your yoga, with heel drops added**, 25 min. "We adapted her habit instead of starting something new."
- "How sure are we? *We're confident this would help you (0.86)*." The genetics line is always there:
  *This nudges your starting point. It doesn't tell you what will happen.*
- Open **Why this?** (inside the card; every recommended activity has one, always). Walk it:
  0 strength days vs WHO's 2 → COL1A1 (peer-reviewed) + post-menopause + Bupa report → bone loading (Royal Osteoporosis Society) → she does yoga.
- Open **Check the logic**: the real ProbLog query, proofs, rules and facts. "Verifiable, not just claimed."
- Earlier/later cards are dimmed. **Take a look** opens them to read, with no button.

**1:00 She's in charge**
- Tap **Less like this** → the pick changes (chair squats). "Her vote is an argument against that activity; it goes into the logic."
- (Optional) **User** tab → untick *a yoga mat* → **Save** → Today: "We left out 5 other ideas because you told us you don't have a yoga mat…"

**1:25 Activity (`/activity`)**
- Tap **Weights or muscle work**, 30 min. Before saving, the preview shows **Strength 0 → 1 / 2 days a week**. The ticks are hers to change.
- **Add it** → **See my batteries** → Strength is now **Ticking over**.
- (Optional) **Sync my watch** → 2 new watch workouts → Cardio, Balance and Flexibility move.

**1:45 Ask (`/ask`)**
- Tap *"I have chest pain when I run"* → **I can't help with that one.** → a Bupa health adviser → 999/111.
- "Default-deny. The refusal never explains itself in clinical terms."

**Optional beats**
- **Dan, 19:30** (`/today?p=dan&at=19:30`): *A gentler option this evening* · **Mixed evidence** · Sports Medicine 2019 →
  **Give me the harder one instead**. "We never overrule someone on mixed evidence."
- **Margaret, 13:00**: "Your afternoon looks full. Here's a 5-minute one…". It still has a full *Why this?*.
- **Dan, 13:00**: busy all afternoon → "We'll leave you be." Not nagging is a feature.
- **Sam** shows the no-watch onboarding.

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
| Whole day plan (3 cards, with proofs) | ≈0.3–0.5s locally (test asserts p95 < 4s) |
| Copy reading level | Flesch–Kincaid grade ≈2.8 (test asserts ≤ 6) |
| Scope-guard fixture | 25 in-scope answered, 27 out-of-scope → 100% routed to a human |
| Sources | 14, each graded: clinical guideline / peer-reviewed / commercial protocol |
| Tests | 92, incl. "every recommended activity always has a why + logic" over every person × time × kit × vote |

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
