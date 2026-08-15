# Why

GitLab `v2.0.34` verified the source, tag, quality graph, and native asset but
failed while the publication job installed operating-system packages at
runtime. The Debian package client emitted more than four million bytes of
repeated delayed-download failures before exiting, so an otherwise complete
release could not be published.

# What Changes

- Run GitLab publication in the same immutable Linux release runtime declared
  by repository metadata.
- Remove operating-system package installation from the publication job.
- Keep locked Python dependencies, release signing, manifest verification, and
  the independent GitLab publication path unchanged.

# Non-goals

- Rewriting or retrying the failed `v2.0.34` release as if it had succeeded.
- Changing GitHub publication.
- Adding another CI generator, wrapper, image build, or package bootstrap.
