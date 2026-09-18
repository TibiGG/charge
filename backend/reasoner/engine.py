"""ProbLog reasoner: selection, confidence and provenance.

Inputs are a few dozen ground facts built from the persona + aggregated metrics.
Outputs: per-action probabilities, per-rule probabilities, real proofs (KBest
explain) and a because/3-style derivation tree joined against rules.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from problog import get_evaluatable
from problog.engine import DefaultEngine
from problog.kbest import KBestFormula
from problog.program import PrologString

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data"

MODEL = (HERE / "model.pl").read_text()
RULES: dict = json.loads((HERE / "rules.json").read_text())
ACTIONS: dict = json.loads((DATA / "actions.json").read_text())
TARGETS: dict = json.loads((DATA / "targets.json").read_text())
SOURCES: dict = json.loads((DATA / "sources.json").read_text())

# Ranking preference for adapting an existing habit. A product choice, not a
# health claim, so it carries no source.
ADAPT_BONUS = 1.15

_ATOM = re.compile(r"^[a-z][a-z0-9_]*$")


def _atom(s: str) -> str:
    s = re.sub(r"[^a-z0-9_]", "_", str(s).lower())
    if not _ATOM.match(s):
        s = "x_" + s
    return s


def target_facts() -> str:
    return "\n".join(
        f"target({b}, {t['metric']}, {float(t['target'])}, {t['source_id']})." for b, t in TARGETS.items()
    )


def person_facts(persona: dict, genome: dict, metrics: dict) -> str:
    u = "u1"
    lines = [f"person({u}).", f"age({u}, {int(persona['age'])}).", f"sex({u}, {_atom(persona['sex'])})."]
    if persona.get("menopause_status"):
        lines.append(f"menopause_status({u}, {_atom(persona['menopause_status'])}).")
    for h in persona.get("habits", []):
        lines.append(f"habit({u}, {_atom('walking' if h == 'walk' else h)}).")
    for panel in genome.get("panels", []):
        lines.append(f"prs_band({u}, {_atom(panel['condition'])}, {_atom(panel['prs_band'])}).")
        for v in panel.get("variants", []):
            lines.append(f"carries({u}, {_atom(v['rsid'])}).")
    for b, t in TARGETS.items():
        lines.append(f"observed({u}, {t['metric']}, {float(metrics[t['metric']])}).")
    return "\n".join(lines)


def _program(facts: str, queries: str) -> str:
    return "\n".join([MODEL, "% ===== 3. targets (from data/targets.json) =====", target_facts(),
                      "% ===== 1. person + observations =====", facts, queries])


def evaluate(facts: str) -> dict:
    prog = _program(facts, "query(helps(u1,_)).\nquery(recommend(u1,_,_)).\nquery(marker_shifts(u1,_,_)).")
    res = get_evaluatable().create_from(PrologString(prog)).evaluate()
    helps, rules, edges = {}, {}, {}
    for term, p in res.items():
        args = [str(a) for a in term.args]
        if term.functor == "helps":
            helps[args[1]] = p
        elif term.functor == "recommend":
            rules[args[2]] = {"action": args[1], "p": p}
        elif term.functor == "marker_shifts":
            edges[args[2]] = {"trait": args[1], "p": p}
    return {"helps": helps, "rules": rules, "edges": edges}


_CHOICE = re.compile(r"choice\(\d+,\d+,(\w+)\(([^()]*)\),[^()]*?\)")


def _choice_label(m: re.Match) -> str:
    args = m.group(2).split(",")
    return f"rule {args[-1]}" if args[-1] in RULES else f"{m.group(1)}({m.group(2)})"


def explain(facts: str, action: str, query: str | None = None) -> list[dict]:
    """Real proofs from ProbLog's KBest explain, for one query only (the winner)."""
    prog = _program(facts, f"query({query or f'helps(u1,{action})'}).")
    db = DefaultEngine().prepare(PrologString(prog))
    out: list = []
    KBestFormula.create_from(db, label_all=True).evaluate(explain=out)
    proofs = []
    for line in out:
        if not line.strip() or ":-" not in line:
            continue
        body, _, prob = line.partition("% P=")
        body = body.split(":-", 1)[1].strip().rstrip(".").strip()
        body = _CHOICE.sub(_choice_label, body)
        literals = [l.strip() for l in re.split(r",\s*(?![^()]*\))", body) if l.strip()]
        # Positive literals are the proof; negated ones only make the sum disjoint.
        proofs.append({
            "uses": [l for l in literals if not l.startswith("\\+")],
            "excludes": [l[2:] for l in literals if l.startswith("\\+")],
            "p": round(float(prob), 4),
        })
    # KBest repeats proofs once per query label; keep unique.
    seen, unique = set(), []
    for pr in proofs:
        key = (tuple(pr["uses"]), tuple(pr["excludes"]))
        if key not in seen:
            seen.add(key)
            unique.append(pr)
    return unique


def rank(result: dict, batteries: dict, habits: list[str]) -> list[dict]:
    fills = {b["id"]: b["fill"] for b in batteries["batteries"]}
    candidates = []
    for action, p in result["helps"].items():
        if p <= 0 or action not in ACTIONS:
            continue
        a = ACTIONS[action]
        deficit = max(1 - fills[b] for b in a["batteries"])
        adapts = any(r["action"] == action and RULES[rid].get("adapts") for rid, r in result["rules"].items())
        score = p * deficit * (ADAPT_BONUS if adapts else 1.0)
        candidates.append({"action": action, "p": p, "deficit": deficit, "adapts": adapts, "score": score})
    superseded = {s for c in candidates for s in ACTIONS[c["action"]].get("supersedes", [])}
    candidates = [c for c in candidates if c["action"] not in superseded]
    return sorted(candidates, key=lambda c: -c["score"])


# ---------- because/3 derivation (guaranteed fallback, always rendered) ----------

def _node(rule_id: str, p: float | None, children: list | None = None, facts: list | None = None) -> dict:
    meta = RULES[rule_id]
    return {"rule_id": rule_id, "text": meta["head"], "source_id": meta["source_id"],
            "p": None if p is None else round(p, 2), "facts": facts or [], "children": children or [],
            "design_note": meta.get("design_note")}


def _target_fact(bid: str, batteries: dict) -> dict:
    b = next(x for x in batteries["batteries"] if x["id"] == bid)
    t = TARGETS[bid]
    return {"kind": "observation", "battery": bid, "value": b["value"], "target": t["target"],
            "unit": t["unit"], "source_id": t["source_id"]}


def derivation(action: str, result: dict, batteries: dict) -> dict:
    """Tree: action <- rules that fired for it <- the rules/edges/observations each body used."""
    edges = result["edges"]

    def edge_nodes(trait: str) -> list:
        return [_node(eid, e["p"]) for eid, e in edges.items() if e["trait"] == trait and e["p"] > 0]

    def rule_tree(rid: str) -> dict:
        r = result["rules"][rid]
        meta = RULES[rid]
        children, facts = [], []
        for lit in meta["body"]:
            m = re.match(r"under_target\((\w+)\)", lit)
            if m:
                facts.append(_target_fact(m.group(1), batteries))
            elif lit == "shifted(bone_fragility)":
                children.append({"text": "Together that nudges your starting point.", "genetic": True,
                                 "children": edge_nodes("bone_fragility"), "source_id": None, "facts": []})
            elif lit == "shifted(cardiometabolic)":
                children.append({"text": "Together that nudges your starting point.", "genetic": True,
                                 "children": edge_nodes("cardiometabolic"), "source_id": None, "facts": []})
            elif lit == "older_adult":
                facts.append({"kind": "age"})
            elif lit.startswith("habit("):
                facts.append({"kind": "habit", "habit": meta.get("adapts")})
            elif lit == "strength_need":
                for sub in ("r_strength_who", "r_impact_loading"):
                    if sub in result["rules"] and result["rules"][sub]["p"] > 0:
                        children.append(rule_tree(sub))
            elif lit.startswith("helps("):
                target_action = lit[6:-1]
                for sub, s in result["rules"].items():
                    if s["action"] == target_action and s["p"] > 0:
                        children.append(rule_tree(sub))
        return _node(rid, r["p"], children, facts)

    fired = [rid for rid, r in result["rules"].items() if r["action"] == action and r["p"] > 0]
    return {"action": action, "p": round(result["helps"][action], 2),
            "because": [rule_tree(rid) for rid in fired]}


def fallback(batteries: dict) -> dict:
    """Deterministic quick answer: biggest-deficit vial -> its default action. Still cited."""
    bid = batteries["emptiest"]
    action = next(a for a, m in ACTIONS.items() if m.get("default_for") == bid)
    t = TARGETS[bid]
    return {"action": action, "p": None, "because": [{
        "rule_id": None, "text": "This is your emptiest battery, so we picked the plainest way to fill it.",
        "source_id": t["source_id"], "p": None, "facts": [_target_fact(bid, batteries)], "children": [],
    }]}


def all_clause_ids() -> list[tuple[str, str, float | str]]:
    """(functor, id, probability) for EVERY probabilistic clause — used by soundness tests.
    Flexible probabilities (bound from data at run time) are reported as "flex"."""
    out = []
    for clause in PrologString(MODEL):
        head = clause.head if hasattr(clause, "head") else clause
        if head.probability is None:
            continue
        try:
            p: float | str = float(head.probability)
        except (TypeError, ValueError):
            p = "flex"
        out.append((head.functor, str(head.args[-1]), p))
    return out


# ---------- Dayparts: candidates in, winner + provenance out ----------

def candidate_facts(cands: list[dict], daypart: str, deficits: dict[str, float],
                    bedtime_min: int | None, override_sleep: bool) -> str:
    lines = [f"now_daypart({daypart})."]
    lines += [f"deficit({b}, {max(0.0, min(1.0, w)):.3f})." for b, w in deficits.items()]
    if bedtime_min is not None:  # no sleep data -> no bedtime -> sleep rule cannot fire
        lines.append(f"bedtime_min(u1, {bedtime_min}).")
    if override_sleep:
        lines.append("user_override(sleep).")
    for c in cands:
        cid = _atom(c["id"])
        lines += [f"cand({cid}).", f"cand_action({cid}, {c['action']}).",
                  f"cand_battery({cid}, {c['primary_battery']}).", f"cand_intensity({cid}, {c['intensity']})."]
        lines += [f"cand_habit({cid}, {_atom(h)})." for h in c.get("habits", [])]
        if c.get("slot_end_min") is not None:
            lines.append(f"slot_end_min({cid}, {c['slot_end_min']}).")
    return "\n".join(lines)


def evaluate_day(facts: str) -> dict:
    q = "\n".join([
        "query(good(_)).", "query(good_raw(_)).", "query(sleep_conflict(_, r_sleep_evening)).",
        "query(helps(u1,_)).", "query(recommend(u1,_,_)).", "query(marker_shifts(u1,_,_))."])
    res = get_evaluatable().create_from(PrologString(_program(facts, q))).evaluate()
    out = {"good": {}, "good_raw": {}, "sleep_conflict": {}, "helps": {}, "rules": {}, "edges": {}}
    for term, p in res.items():
        args = [str(a) for a in term.args]
        if term.functor in ("good", "good_raw"):
            if args[0] != "none":
                out[term.functor][args[0]] = p
        elif term.functor == "sleep_conflict":
            out["sleep_conflict"][args[0]] = p
        elif term.functor == "helps":
            out["helps"][args[1]] = p
        elif term.functor == "recommend":
            out["rules"][args[2]] = {"action": args[1], "p": p}
        elif term.functor == "marker_shifts":
            out["edges"][args[2]] = {"trait": args[1], "p": p}
    return out


def warm() -> None:
    evaluate("person(u1). age(u1, 40). observed(u1, strength_days_per_week, 0.0).")
