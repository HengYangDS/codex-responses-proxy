## 1. Reproduce and define

- [x] 1.1 Reproduce the real rollback through the installed command and record
      that the serving payload rolls back while the PATH command also regresses.
- [x] 1.2 Add a transaction regression that fails when reverse activation
      repoints the user command to the retained older executable.
- [x] 1.3 Define the serving, supervision, command, and installation-admission
      authorities in the runtime-upgrade delta and architecture documentation.

## 2. Implement one authority model

- [x] 2.1 Derive lifecycle control from the newest verified selected release
      and verify both selector orientations.
- [x] 2.2 Make unchanged command projection idempotent and verify its native
      link identity does not churn.
- [x] 2.3 Use the control release as the forward-install floor and verify a
      post-rollback replay is refused while a newer patch is admitted.
- [x] 2.4 Make status, recovery, transaction rollback, and uninstall consume the
      same control-generation derivation.
- [x] 2.5 Run focused lifecycle and installation tests and `nox -s quick` with no
      warnings or failures.

## 3. Close source

- [x] 3.1 Pass strict OpenSpec validation and make the completed source change
      archive-ready.
- [x] 3.2 Pass full quality, Python 3.12–3.14, release, and authentic published-
      predecessor native compatibility gates on the archive candidate tree.

## Post-archive lifecycle

Create one signed source commit from the archived tree, publish one later SemVer
patch with the same signed Git objects and byte-identical assets on GitHub and
GitLab, then prove install, a real request, rollback through the installed PATH
command, doctor, recover, forward reversal, uninstall, reinstall, and zero owned
residue. These external effects remain incomplete until their current receipts
exist.
