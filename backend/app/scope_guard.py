"""Scope guard — DEFAULT DENY.

Layer (a): deterministic red-flag / deny regexes. Nothing (including any LLM) can overrule it.
Layer (b): allow-list intent classifier over the 5 batteries + sleep + "explain my report".
Layer (c): anything unmatched -> decline and route to a human.

We never explain *why* something was refused in clinical terms; that would itself be a health claim.
"""
from __future__ import annotations

import re

DENY_PATTERNS = {
    "emergency": r"\b(chest pain|chest (?:hurts|tight)|can'?t breathe|short(?:ness)? of breath|faint(?:ed|ing)?|collaps|stroke|seizure|unconscious|heart attack|numb)",
    "bleeding": r"\bbleed|\bblood\b|bloody",
    "self_harm": r"suicid|kill myself|end (?:my|it all)|self[- ]?harm|hurt myself|don'?t want to (?:live|be here)|overdose",
    "medication": r"\bstop taking\b|\bmedic(?:ine|ation)s?\b|\bpills?\b|\btablets?\b|\bdos(?:e|age|ing)\b|\bmg\b|\bprescri|\bstatins?\b|\binsulin\b|\bantibiotic|\bibuprofen|\bparacetamol|\bsupplement|\bhrt\b|\bvitamin",
    "pregnancy": r"pregnan|\bmiscarr|\bfertil|\bivf\b|trying for a baby|breastfeed",
    "lump": r"\blumps?\b|\bswelling|\brash\b|\bmole\b|\btumou?r|\bcancer",
    "child": r"\bmy (?:child|son|daughter|baby|kid|kids|toddler)\b|\bchildren\b",
    "diagnosis": r"diagnos|\bdo i have\b|\bhave i got\b|\bis it (?:serious|cancer|normal)\b|\bsymptom|\bwhat'?s wrong with me|\bam i ill\b|\bis this (?:serious|normal)\b",
    "pain_injury": r"\bpain\b|\bhurts?\b|\bache|\binjur|\bbroke(?:n)?\b|\bfracture|\bsprain|\bdizzy|\bpalpitation",
    "mental_health": r"\bdepress|\banxiety attack|\bpanic attack|\beating disorder|\bstarv",
    "other_people": r"\bmy (?:wife|husband|partner|mum|mom|dad|father|mother|friend)\b",
    "extreme_diet": r"\bfast(?:ing)? for\b|\bwater fast|\blose \d+ ?(?:kg|lbs?|pounds|stone) (?:in|by)\b",
}
_DENY = {k: re.compile(v, re.I) for k, v in DENY_PATTERNS.items()}

ALLOW_INTENTS = {
    "strength": r"\b(strength|strong(?:er)?|muscle|weights?|lift(?:ing)?|squat|press[- ]?ups?|push[- ]?ups?|resistance)\b",
    "cardio": r"\b(cardio|stamina|walk(?:ing)?|run(?:ning)?|jog(?:ging)?|cycl(?:e|ing)|spin|swim(?:ming)?|aerobic|steps?|fit(?:ter|ness)?)\b",
    "peak": r"\b(hiit|intervals?|sprint|hard effort|peak|vo2)\b",
    "balance": r"\b(balance|steady|steadiness|tai chi|wobbl\w*|falls?)\b",
    "mobility": r"\b(stretch(?:ing)?|flexib\w*|mobility|supple(?:ness)?|yoga|pilates)\b",
    "sleep": r"\b(sleep(?:ing)?|rest days?|tired|bed ?time|nap)\b",
    "report": r"\b(my report|genome|genomic|dna|gene|battery|batteries|vial|charge|explain)\b",
    "schedule": r"\b(when should|what should i do|today|this week|calendar|time for|how long|how often|how many)\b",
}
_ALLOW = {k: re.compile(v, re.I) for k, v in ALLOW_INTENTS.items()}

REFUSAL = {
    "title": "I can't help with that one.",
    "body": "That's a question for a person, not an app.",
    "cta_title": "A Bupa health adviser can help.",
    "cta": "Talk to someone now",
    "safety": "If this is an emergency, call 999. If you need urgent advice, call 111.",
}


def classify(text: str) -> dict:
    t = (text or "").strip()
    if not t:
        return {"decision": "route_to_human", "layer": "c_default_deny", "intent": None}
    # Layer (a): deny wins over everything.
    for name, rx in _DENY.items():
        if rx.search(t):
            return {"decision": "route_to_human", "layer": "a_red_flag", "intent": None, "flag": name}
    # Layer (b): allow-list.
    hits = [k for k, rx in _ALLOW.items() if rx.search(t)]
    if hits:
        return {"decision": "answer", "layer": "b_allow", "intent": hits[0], "intents": hits}
    # Layer (c): default deny.
    return {"decision": "route_to_human", "layer": "c_default_deny", "intent": None}
