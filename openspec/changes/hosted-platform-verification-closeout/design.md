# Design

Production process ownership already captures `PID + normalized executable +
create_time`. This change leaves that contract untouched. Tests compare the
captured scalar fields rather than constructing an expected path with another
platform's normalization rules. Focused fail-closed cases cover the remaining
branches without widening production behavior.
