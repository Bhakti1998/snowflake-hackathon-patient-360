# Transparent demo risk model

Owner: Vinay; structured input and snapshot integration: Adithya.
This is a synthetic demonstration score, not a clinically validated model.

## Fixed design weights

| Factor ID | Factor | Points if approved trigger is met |
|---|---|---:|
| `uncontrolled_lab` | Uncontrolled lab value | 30 |
| `recent_ed` | Recent ED utilization | 20 |
| `adherence_concern` | Medication adherence concern | 15 |
| `multiple_chronic_conditions` | Multiple chronic conditions | 15 |
| `care_gap` | Care gap detected | 10 |
| `recent_adverse_event` | Recent adverse event | 10 |

Each factor contributes at most once per member per scoring run. Total range:
0-100. Multiple qualifying labs/claims/notes cannot multiply one factor's points.

| Tier | Inclusive score range |
|---|---|
| Low | 0-24 |
| Moderate | 25-49 |
| High | 50-74 |
| Critical | 75-100 |

Scores outside 0-100 or duplicate factor evaluations are validation failures,
not values to clamp silently.

## Approved demo definitions

The design fixes weights and bands, **not** clinical trigger cutoffs. The user
has now approved the explicitly synthetic definitions in
[WORKFLOW.md](./WORKFLOW.md): latest source-flagged labs within 180 days;
90-day distinct ED and adverse-event windows; active non-PRN covered-days PDC
below 80% over 183 days; at least two active chronic keys; unresolved due TRC gap.
Do not introduce new clinical thresholds or silently change these approved rules.

Frozen seed is 42, as-of is 2026-09-30, rule version is `synthetic-demo-v1`;
"high-risk" means High plus Critical. Approval is recorded in
[DECISIONS.md](../.cortex/memory/DECISIONS.md).

## Factor record contract

Record member, factor ID, rule version, scoring run/as-of date, evaluation state
(`MET`, `NOT_MET`, `UNKNOWN`), points, source record/document references,
evidence date, and a plain-language trigger explanation.

`UNKNOWN` is not `NOT_MET`. If a required input is missing, expose incomplete
scoring and do not label the tier final. Any partial sum must be explicitly
identified as partial with unknown factors; do not silently treat missingness
as a confirmed absence of risk. Record conflicts without arbitrarily choosing
the source that produces a desired score.

## Explanation and tests

Explain each contribution with its evidence and approved trigger. Cite the rule
version for calculated points and source records/pages for the inputs.

- Unit-test tier classification at 0, 24, 25, 49, 50, 74, 75, 100. Some boundary
  integers are not achievable by these weights; test the classifier directly.
- Test all factors met -> 100 / Critical; none met with complete inputs -> 0 / Low.
- Test duplicate source records do not duplicate factor points.
- Test unknown inputs, contradictory adherence evidence, and exact lookback edges.
- Reconcile factor sum, snapshot score/tier, and UI breakdown for all 500 members
  across diabetes, hypertension, CKD, asthma and heart failure.
- Reject negative/out-of-range scores and duplicate factor IDs.

**Source example correction:** the full design labels a 75-point illustrative
answer High. By the published bands it is Critical. Never copy that inconsistency
into fixtures, expected answers, or agent instructions.
