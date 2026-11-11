"""The Health check: a few medical facts that keep our ideas safe and right for the person.

PRIVACY: for a signed-in person it lives in their sealed vault (app.vault), which only their
own key opens; we never store it anywhere else, and never log it. The demo's made-up people
keep theirs in the browser and send it in the request BODY (never the URL, which ends up in
access logs) each time they ask for a plan.

Readiness follows pre-exercise screening (PAR-Q+, ACSM 2015): symptoms, or a doctor saying
"supervised only", mean we suggest nothing until a doctor or nurse has said yes. Any other
"yes" keeps ideas gentle or moderate until then. We never diagnose and never explain a
clinical reason: the person is pointed to a human.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# PAR-Q+-style questions. The wording the person sees lives in frontend/src/lib/copy.ts.
SCREEN = ("heart", "chest_pain", "dizzy", "other_condition", "medicines", "joints", "supervised")
SYMPTOMS = {"chest_pain", "dizzy", "supervised"}  # see someone before ANY new activity
CONDITIONS = {"thin_bones", "type2_diabetes", "high_bp", "pregnant", "fall"}
BANDS = {"high", "average", "low"}
VARIANTS = {"col1a1": "rs1800012", "fto": "rs9939609"}

SRC_SCREEN = "src_acsm_2015_screening"
SRC_PARQ = "src_parq_plus"
SRC_PREGNANCY = "src_who_2020_pregnancy"


class ReportIn(BaseModel):
    """Bands copied by hand from a Bupa MY Genomic Health report."""
    bones: str | None = None   # osteoporosis panel
    heart: str | None = None   # cardiometabolic panel
    variants: list[str] = []


class HealthIn(BaseModel):
    screen: dict[str, bool] = {}
    cleared: bool = False      # "A doctor or nurse has said I can be active"
    conditions: list[str] = []
    menopause: str | None = None
    easy_joints: bool = False
    report: ReportIn | None = None


class PlanIn(BaseModel):
    """Body of POST /api/today/{persona} (the demo). Only the health check travels this way."""
    health: HealthIn | None = Field(default=None)


def readiness(h: HealthIn | None) -> str:
    """'ok' | 'gentle' (no hard effort yet) | 'check' (see someone first, suggest nothing)."""
    if h is None or h.cleared:
        return "ok"
    yes = {k for k in SCREEN if h.screen.get(k)}
    if yes & SYMPTOMS:
        return "check"
    if yes or "pregnant" in h.conditions:
        return "gentle"
    return "ok"


def _genome(r: ReportIn) -> dict | None:
    panels = []
    if r.bones in BANDS:
        panels.append({"condition": "osteoporosis", "prs_band": r.bones,
                       "variants": [{"rsid": VARIANTS["col1a1"]}] if "col1a1" in r.variants else []})
    if r.heart in BANDS:
        panels.append({"condition": "cardiometabolic", "prs_band": r.heart,
                       "variants": [{"rsid": VARIANTS["fto"]}] if "fto" in r.variants else []})
    return {"panels": panels, "source_id": "src_bupa_genomic"} if panels else None


def apply(persona: dict, h: HealthIn | None) -> dict:
    """The persona with the health check folded in, as facts the reasoner already knows."""
    if h is None:
        return {**persona, "readiness": "ok"}
    conds = {c for c in h.conditions if c in CONDITIONS}
    diagnosed = set()
    if "thin_bones" in conds:
        diagnosed.add("low_bone_density")
    if conds & {"type2_diabetes", "high_bp"}:
        diagnosed.add("cardiometabolic")
    out = {**persona, "readiness": readiness(h), "cleared": h.cleared, "easy_joints": h.easy_joints,
           "pregnant": "pregnant" in conds, "fell_recently": "fall" in conds, "diagnosed": sorted(diagnosed)}
    if h.menopause in ("pre", "peri", "post"):
        out["menopause_status"] = h.menopause
    if h.report and (g := _genome(h.report)):
        out["genome"] = g
    return out
