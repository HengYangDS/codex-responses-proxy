## ADDED Requirements

### Requirement: GitLab main validation follows release state

The GitLab metadata verification job SHALL validate a tag pipeline against its exact tag. For an untagged main pipeline, it SHALL perform ordinary GitLab provider validation when the tag named by `VERSION` already exists and SHALL prepare a release only while that tag is absent.

#### Scenario: Main advances after publication

- **WHEN** GitLab runs an untagged main commit whose `v<VERSION>` tag already exists
- **THEN** metadata verification runs ordinary GitLab provider validation
- **AND** it does not reject the commit as an attempted duplicate release.

#### Scenario: Main carries an unpublished release candidate

- **WHEN** GitLab runs an untagged main commit whose `v<VERSION>` tag does not exist
- **THEN** metadata verification runs release preparation
- **AND** the existing pending-release chronology requirements remain enforced.
