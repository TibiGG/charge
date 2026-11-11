"""Turn a structured recommendation into plain words.

SAFETY ARCHITECTURE: the LLM is a renderer, not a reasoner. ProbLog decides
what to suggest and how sure we are. These templates are the default path.
An optional LLM may only paraphrase the template output; `validate_llm_output`
rejects anything with a new number or a banned word, and we fall back to the
template string.
"""
from __future__ import annotations

import re

BANNED = ["risk of", "likely to develop", "predisposed", "abnormal", "danger", "warning",
          "disease", "suffer", "you will", "prevents", "cures", "guaranteed"]

GENETIC_FRAME = "This nudges your starting point. It doesn't tell you what will happen."
QUICK_ANSWER = "We used our quick answer here."

CONFIDENCE = [
    (0.80, "confident", "We're confident this would help you."),
    (0.50, "likely", "This looks likely to help, though we're less sure."),
    (0.00, "unsure", "This might help. It's worth a quick chat with a Bupa nurse first."),
]

HABIT_WORDS = {"yoga": "yoga", "spin": "spin classes", "weights": "weights", "walking": "walking"}


def confidence_band(p: float | None) -> dict:
    if p is None:
        return {"key": "quick", "sentence": QUICK_ANSWER, "p": None}
    for threshold, key, sentence in CONFIDENCE:
        if p >= threshold:
            return {"key": key, "sentence": sentence, "p": round(p, 2)}
    return {"key": "unsure", "sentence": CONFIDENCE[-1][2], "p": round(p, 2)}


def _n(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def compare(value: float, target: float) -> str:
    if value >= target:
        return "That's at or above the aim."
    if value == 0:
        return "There's room to grow here."
    return "You're part of the way there."


def observation_sentence(bid: str, value: float, target: float) -> str:
    v, t = _n(value), _n(target)
    line = {
        "strength": f"You've done {v} minutes of muscle work this week. We aim for {t}, which is 2 sessions of 30.",
        "cardio": f"You've done {v} minutes of activity that warms you up this week. People are advised to aim for {t}.",
        "peak": f"You've done {v} minutes of hard effort this week. One aim is {t} minutes.",
        "balance": f"You've done {v} minutes of balance work this week. We aim for {t}, which is 3 sessions of 20.",
        "mobility": f"You've done {v} minutes of stretching this week. We suggest {t}. This aim is not from a health body.",
    }[bid]
    return f"{line} {compare(value, target)}"


def fact_sentence(fact: dict, persona: dict) -> str:
    kind = fact["kind"]
    if kind == "observation":
        return observation_sentence(fact["battery"], fact["value"], fact["target"])
    if kind == "age":
        return f"You are {persona['age']}. The balance aim is for people over 65."
    if kind == "habit":
        return f"You told us you enjoy {HABIT_WORDS.get(fact['habit'], fact['habit'])}."
    if kind == "diagnosed":
        return {"cardiometabolic": "You told us you have high blood pressure or type 2 diabetes.",
                "low_bone_density": "You told us a doctor found your bones are thinner than usual."}.get(fact["what"], "")
    if kind == "fall":
        return "You told us you had a fall in the last year."
    return ""


def annotate(nodes: list, persona: dict, seen: set | None = None) -> None:
    """Add plain-language `said` lines to every fact in the derivation tree, in place.
    A fact already said higher up the tree is not repeated."""
    seen = set() if seen is None else seen
    for n in nodes:
        for f in n.get("facts", []):
            s = fact_sentence(f, persona)
            f["said"] = None if s in seen else s
            seen.add(s)
        annotate(n.get("children", []), persona, seen)


def _has_genetic(nodes: list) -> bool:
    return any(n.get("genetic") or _has_genetic(n.get("children", [])) for n in nodes)


def render_recommendation(rec: dict, batteries: dict, persona: dict) -> dict:
    annotate(rec["derivation"], persona)
    slot = rec.get("slot")
    when = f"{slot['label']}. You're free then." if slot else "Pick a time that suits you."
    out = {
        "headline": rec["name"],
        "how_long": f"It takes {rec['minutes']} minutes.",
        "when": when,
        "confidence": rec["confidence"]["sentence"],
        "genetic_frame": GENETIC_FRAME if _has_genetic(rec["derivation"]) else None,
    }
    out["read_aloud"] = " ".join(x for x in [out["headline"] + ".", out["how_long"], out["when"],
                                             out["confidence"], out["genetic_frame"]] if x)
    return out


# ---------- LLM output guard (used only if an LLM paraphraser is enabled) ----------

_NUM = re.compile(r"\d+(?:\.\d+)?")


def validate_llm_output(text: str, allowed_source_text: str) -> bool:
    lowered = text.lower()
    if any(b in lowered for b in BANNED):
        return False
    allowed = set(_NUM.findall(allowed_source_text))
    return all(n in allowed for n in _NUM.findall(text))


def safe_paraphrase(template: str, llm_output: str | None) -> tuple[str, bool]:
    """Return (text, used_llm). Falls back to the template on any violation."""
    if llm_output and validate_llm_output(llm_output, template):
        return llm_output, True
    return template, False
