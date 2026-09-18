% Charge — recommendation model.
% ProbLog decides WHAT to suggest and HOW SURE we are. Python does the arithmetic;
% the LLM (if any) only rephrases. Every probabilistic clause carries an id as its
% last head argument; rules.json maps that id to a source in sources.json.
%
% Stratum 1 (person + observations) and the target/4 facts (stratum 3) are
% injected per request by engine.py from the persona and data/targets.json.

% Schema sentinels: ProbLog errors on predicates with no clauses, and a persona
% may have no genome report / no habits. `nobody` never matches a real person.
prs_band(nobody, none, none).
carries(nobody, none).
habit(nobody, none).
menopause_status(nobody, none).
age(nobody, 0).
observed(nobody, none, 0.0).

% ===== 2. GENOMIC REPORT (probabilistic: the probability IS the uncertainty) =====
% p = modest, calibrated confidence that this marker meaningfully shifts THIS
% person's starting point. PRS effect sizes are small; nothing here is ever 1.0.
0.62::marker_shifts(P, bone_fragility, e_prs_osteo) :- prs_band(P, osteoporosis, high).
0.55::marker_shifts(P, bone_fragility, e_menopause) :- menopause_status(P, post).
0.30::marker_shifts(P, bone_fragility, e_col1a1)    :- carries(P, rs1800012).
0.40::marker_shifts(P, cardiometabolic, e_prs_cm)   :- prs_band(P, cardiometabolic, high).
0.35::marker_shifts(P, cardiometabolic, e_fto)      :- carries(P, rs9939609).

shifted(P, X) :- marker_shifts(P, X, _).

% ===== 3. GUIDELINE TARGETS =====
under_target(P, B) :- target(B, M, T, _), observed(P, M, V), V < T.
older_adult(P) :- age(P, A), A >= 65.

% ===== 4. RECOMMENDATION RULES (each id -> rules.json -> sources.json) =====
% Strength
0.80::recommend(P, strength_training, r_strength_who) :- under_target(P, strength).
0.88::recommend(P, impact_loading, r_impact_loading) :-
    under_target(P, strength), shifted(P, bone_fragility).

% Balance
0.80::recommend(P, balance_work, r_balance_falls) :-
    under_target(P, balance), shifted(P, bone_fragility).
0.80::recommend(P, balance_work, r_balance_older) :-
    under_target(P, balance), older_adult(P).

% Cardio endurance
0.80::recommend(P, brisk_cardio, r_cardio_who) :- under_target(P, cardio).
0.85::recommend(P, brisk_cardio, r_cardio_fto) :-
    under_target(P, cardio), shifted(P, cardiometabolic).

% HIIT / VO2max — WHO treats vigorous minutes as an alternative route to the
% aerobic target, so only suggest it when that target is not already met.
0.60::recommend(P, intervals, r_peak_who) :- under_target(P, peak), under_target(P, cardio).

% Flexibility & mobility — weakest evidence (commercial protocol), so a low weight.
0.40::recommend(P, stretch_flow, r_mobility_blueprint) :- under_target(P, mobility).

% Noisy-or across every reason for the same action.
helps(P, A) :- recommend(P, A, _).

strength_need(P) :- helps(P, impact_loading).
strength_need(P) :- helps(P, strength_training).

% Prefer ADAPTING an existing habit over introducing a new one.
0.90::recommend(P, power_yoga, r_adapt_yoga) :- habit(P, yoga), strength_need(P).
0.90::recommend(P, lift_then_ride, r_adapt_weights) :- habit(P, weights), helps(P, brisk_cardio).
0.90::recommend(P, balance_walk, r_adapt_walk) :- habit(P, walking), helps(P, balance_work).
