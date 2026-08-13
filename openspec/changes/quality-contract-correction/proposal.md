# Executable quality contract

Two repository-quality methods are not collected by pytest. One also repeats
an obsolete function ELOC threshold, leaving the quality suite falsely green.

This change makes both methods executable tests and binds the threshold check
to the current repository policy value. It changes no product or runtime
behavior.
