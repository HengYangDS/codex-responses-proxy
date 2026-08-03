## 1. Diagnosability of the denial

- [x] 1.1 Add a RED transport test proving the queue-timeout denial names the
  provider route and both the route and process limits.
- [x] 1.2 Name the route width in admission and quote route, route limit, and
  process limit in the denial; obtain focused GREEN.
- [x] 1.3 Add a RED test proving the queue-timeout 503 advertises a retry hint,
  then emit it; document the symptom as a diagnosis-table row.

## 2. Bounded route-slot lifetime

- [x] 2.1 Add RED tests proving a stalled committed stream ends at the total
  upstream deadline and that a pre-content reconnect is refused once the
  deadline has passed.
- [x] 2.2 Add a RED test proving an abandoned stalled stream releases its
  upstream connection instead of leaving it for garbage collection.
- [x] 2.3 Thread one total deadline through every relay attempt, clamp each
  per-read budget to the remaining deadline, and close the upstream on every
  path the relay stops reading; obtain focused GREEN.

## 3. Verification and closeout

- [x] 3.1 Run release metadata, markdown, and metadata tests.
- [x] 3.2 Run full quality with statement and branch coverage above 95% and the
  Python 3.12-3.14 compile gates.
- [x] 3.3 Record the rejected route-width widening, its evidence, and the
  operator queue-timeout lever in design, claim, and chronicle.
- [x] 3.4 Document how the queue-timeout knob is actually applied under native
  supervision, after confirming that raising the released default in code would
  reach no already-installed operator.

## 4. Post-archive acceptance boundary

Landing order, live provider behavior, and operator retuning remain active
claim evidence after this repository change is archived. They are not
planning-artifact completion criteria and must not be marked complete by
OpenSpec archival.

- This branch was promoted to `candidate/dev` ahead of the concurrent AIGW
  model-catalog change on the owner's explicit instruction, inverting the order
  first recorded here. The AIGW lane rebases onto the advanced `candidate/dev`,
  reconciles the five overlapping files, and still owns the `VERSION` bump; the
  release-train identity rule stays unsatisfied until that bump lands.
- The reported `gpt-5.6` route must complete a turn that previously denied, and
  the total-deadline bound must not truncate a legitimate long turn.
- Raising the released `responses_queue_timeout` default was evaluated and
  rejected on evidence, not deferred. Revisiting it requires first deciding how
  a changed default would reach an already-installed unit.
