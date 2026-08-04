## 1. The invariant

- [x] 1.1 Census the live rotated proxy logs to measure, for every matched
  queue-timeout denial, how much longer its blocking holder actually ran.
- [x] 1.2 Add a RED unit contract asserting the default queue wait is not
  shorter than one total upstream stream deadline; observe the RED.
- [x] 1.3 Derive `DEFAULT_RESPONSES_QUEUE_TIMEOUT` from
  `DEFAULT_UPSTREAM_TIMEOUT`; obtain focused GREEN.

## 2. Correcting the prior record

- [x] 2.1 Correct the `route-slot-lease` chronicle and claim, which recorded
  that an install delivers a changed queue-timeout value the same way an
  operator export does. It does not: no install flag and no context parameter
  exists, so the code default is the only lever a supervised install has.
- [x] 2.2 Rewrite the diagnosis-table row, which offered the operator knob as
  the remedy for a default that was itself the defect.

## 3. Verification

- [x] 3.1 Run full quality with statement and branch coverage above 95 percent.
- [x] 3.2 Confirm no other source, test, or document restates the old constant.

## 4. Post-archive acceptance boundary

The following are live-system claims. They remain open after this repository
change is archived and must not be marked complete by OpenSpec archival.

- A reinstall must re-render the native unit so a supervised listener actually
  observes the new default.
- The reported `gpt-5.6` route must complete a turn that previously denied, and
  `responses_local_queue_timeouts` must stop growing on the live counter.
- The total-deadline bound must still truncate a stalled trickle, so the change
  must not be read as removing an upper bound on a held route slot.
