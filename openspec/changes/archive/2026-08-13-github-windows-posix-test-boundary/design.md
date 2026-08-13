# Design

Use Pytest's platform predicate at the executable contract boundary. This keeps
the test intent explicit, preserves the positive and negative cases on POSIX,
and avoids a foreign-shell compatibility layer on Windows.
