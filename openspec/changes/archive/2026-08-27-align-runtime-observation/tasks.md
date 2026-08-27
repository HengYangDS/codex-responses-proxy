## 1. Remove duplicate runtime interpretation

- [x] 1.1 Make `doctor` reuse the runtime identity already admitted by `status`.
- [x] 1.2 Prove platform listener-enumeration lag does not create a false
      diagnostic failure.

## 2. Align release compatibility with lifecycle authority

- [x] 2.1 Observe candidate activation before releasing held requests.
- [x] 2.2 Prove materialization alone does not satisfy the release boundary.
- [x] 2.3 Pass the real macOS published-predecessor compatibility scenario.

## 3. Verify and close the change

- [x] 3.1 Pass strict OpenSpec validation and the repository quick gate without
      warnings.
- [x] 3.2 Pass full source quality, behavior, and release gates.
- [x] 3.3 Archive this completed change before the signed source commit.

## Post-archive lifecycle

Push one unchanged signed commit to both proposal refs. Require hosted Linux and
Windows compatibility, merge to `dev`, remove the proposal refs, advance the
release branch, publish the verified release, and prove the installed lifecycle.
