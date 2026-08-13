## Context

GitLab verification currently starts from bare Python images, installs UV with
pip, lets UV download the primary interpreter, and invokes isolated builds that
resolve Hatchling again. On the admitted Docker runner, these repeated public
downloads fail before repository tests begin. See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:**

- Make ordinary GitLab verification start with UV and its primary interpreter
  already present.
- Preserve `uv.lock`, `.python-versions`, Nox, and the release-image metadata as
  their existing single authorities.
- Keep cold-cache execution correct and GitHub operationally independent.

**Non-Goals:**

- Baking project dependencies or credentials into an image.
- Moving runner configuration into the repository.
- Changing product runtime, release payloads, or GitHub publication behavior.

## Decisions

### Use official digest-pinned UV images for verification

GitLab verification uses official UV images that contain UV and the selected
Python minor. Digests make the executor immutable; `uv.lock` still supplies all
project packages. This removes per-job pip bootstrap and primary-interpreter
download without creating a repository-built CI image.

**Alternatives considered:** Retrying public downloads preserves the failure
mode. A custom project image adds a release and maintenance surface. Plain
Python images keep the redundant bootstrap.

### Keep compatibility versions in `.python-versions`

The latest supported interpreter runs the full matrix owner, while the floor
image runs quality. UV may install the additional compatibility interpreters
listed by `.python-versions`; no workflow-local patch inventory is introduced.

**Alternative considered:** One GitLab job per hard-coded Python image would
duplicate version ownership and expand the pipeline surface.

### Reuse the runner cache without trusting it

Jobs use a project-scoped `UV_CACHE_DIR` inside the checkout and declare it to
GitLab's cache service. The cache is an optimization only: an empty cache must
still resolve from the lock and pass. No host path or runner identity enters
the repository.

### Do not build the project in the bootstrap environment

The GitLab bootstrap installs locked product dependencies and quality tools but
uses UV's `--no-install-project` boundary. Nox remains the sole build owner: its
sessions build a wheel and exercise that artifact. This removes the redundant
editable build and its isolated Hatchling resolution without weakening the
artifact-under-test contract.

**Alternatives considered:** Disabling build isolation for the editable project
still requires the undeclared `editables` backend helper and creates a second
build owner. Adding that helper would preserve the redundant editable build.

## Risks / Trade-offs

- **Official image digest becomes stale** → supply-chain checks update the one
  declared image owner and contract tests verify the UV/Python relation.
- **Warm cache masks missing inputs** → local and hosted gates retain locked
  cold-install verification; cache contents never authorize success.
- **Bootstrap omits the project** → Nox continues to build and install the wheel
  before behavior checks, preserving the released-artifact boundary.

## Migration Plan

1. Add an executable CI contract that fails on the current redundant bootstrap.
2. Replace verification images and bootstrap with the immutable official image,
   project-scoped cache, and locked dependency-only sync.
3. Run focused contracts, quick, quality, Python matrix, and release gates.
4. Prove the exact tree locally, then require independent hosted GitLab and
   GitHub success. Revert the single CI commit if hosted bootstrap regresses.
