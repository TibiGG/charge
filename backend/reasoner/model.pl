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
cand(none).
cand_action(none, none).
cand_battery(none, none).
cand_intensity(none, none).
cand_habit(none, none).
slot_end_min(none, 0).
deficit(none, 0.0).
now_daypart(none).
bedtime_min(nobody, 0).
user_override(none).
user_taste(none, none).
kind_taste(none, none).

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

% ===== 5. DAYPART + CANDIDATE ACTIVITIES =====
% Python injects only the ~8 best candidates for one daypart, after applying the
% two HARD gates (equipment available, free calendar slot). ProbLog then does
% selection + provenance over those, so the proof tree stays small and real.
%
% Ranking = need x evidence x daypart fit x habit fit x (1 - sleep conflict).
% Only `helps/2` (evidence) is shown to the person as "how sure we are";
% the other factors are ranking preferences.

% Practical suitability — a product preference, NOT a health claim. No citation.
daypart_fit(strength, morning,   0.9).
daypart_fit(strength, afternoon, 1.0).
daypart_fit(strength, evening,   0.8).
daypart_fit(cardio,   morning,   1.0).
daypart_fit(cardio,   afternoon, 1.0).
daypart_fit(cardio,   evening,   0.9).
daypart_fit(peak,     morning,   0.9).
daypart_fit(peak,     afternoon, 1.0).
daypart_fit(peak,     evening,   0.8).
daypart_fit(balance,  morning,   1.0).   % cheap, short, needs no kit or shower
daypart_fit(balance,  afternoon, 0.9).
daypart_fit(balance,  evening,   0.9).
daypart_fit(mobility, morning,   1.0).
daypart_fit(mobility, afternoon, 0.8).
daypart_fit(mobility, evening,   1.0).

% How empty the battery this activity fills most is. Deficit stays the primary driver.
W::need(C, p_need) :- cand_battery(C, B), deficit(B, W).
W::fits_now(C, p_daypart_fit) :- cand_battery(C, B), now_daypart(D), daypart_fit(B, D, W).

% Adapting a habit you already have beats starting a new one (a product choice).
has_habit_match(C) :- cand_habit(C, H), habit(u1, H).
% Votes are arguments about one activity (bipolar argumentation, after Toni et al.):
% "More like this" SUPPORTS it, so it counts like a habit they already enjoy.
has_habit_match(C) :- user_taste(more, C).
habit_fit(C) :- has_habit_match(C).
0.87::habit_fit(C, p_habit_fit) :- cand(C), \+ has_habit_match(C).
habit_fit(C) :- habit_fit(C, _).

% THE one daypart rule that is a health claim. Evidence is MIXED and mostly
% reassuring, so it is a soft penalty, never a block, and the person can override.
ends_near_bedtime(C) :- slot_end_min(C, E), bedtime_min(u1, B), Gap is B - E, Gap >= 0, Gap =< 60.
0.65::sleep_conflict(C, r_sleep_evening) :-
    cand_intensity(C, vigorous), ends_near_bedtime(C), \+ user_override(sleep).
sleep_conflict(C) :- sleep_conflict(C, _).

% "Less like this" ATTACKS it: a soft nudge down, never a block (their taste, not a health claim).
disliked(C) :- user_taste(less, C).
0.40::taste_ok(C, p_taste_less) :- disliked(C).
% Learned over time: 2+ "less" votes on one kind of activity become a weaker attack on that kind.
kind_disliked(C) :- cand_action(C, A), kind_taste(less, A), \+ disliked(C).
0.70::taste_ok(C, p_taste_kind) :- kind_disliked(C).
taste_ok(C) :- cand(C), \+ disliked(C), \+ kind_disliked(C).
taste_ok(C) :- taste_ok(C, _).

evidence_for(C) :- cand_action(C, A), helps(u1, A).
good_raw(C) :- need(C, _), evidence_for(C), fits_now(C, _), habit_fit(C), taste_ok(C).
good(C) :- good_raw(C), \+ sleep_conflict(C).
