package ci

import "list"

// pipeline.cue owns the provider-neutral proof graph. Forge YAML files remain
// projections; product behavior stays in Nox and repository-owned Python tools.

#RuntimeMatrix: {
	"python": ["3.12", "3.13", "3.14"]
}

#Conditions: {
	productProof: "(github.event_name == 'pull_request' && github.base_ref == 'dev') || (github.event_name == 'push' && github.ref == 'refs/heads/dev')"
	nativeProof:  #Conditions.productProof + " || github.ref_type == 'tag'"
	productSHA:   "${{ github.event.pull_request.head.sha || github.sha }}"
}

#Toolchains: {
	githubMiseAction: "jdx/mise-action@3c2e0cf82a5b2e5249f0d3635a4d83d0ae861518"
	gitlabMiseImage:  "ghcr.io/jdx/mise@sha256:f2d637d5e5189f7ec177b73bce5cd5db7e7b17a4f466f887c1b88ac2dd431129"
	quality:          "python,uv,cue,npm:@fission-ai/openspec,github:gitleaks/gitleaks,github:rhysd/actionlint,github:lycheeverse/lychee"
}

gitlab: {
	workflow: rules: [{
		if: "$CI_COMMIT_TAG"
	}, {
		if: "$CI_PIPELINE_SOURCE == \"merge_request_event\""
	}, {
		if: "$CI_COMMIT_BRANCH == \"dev\" || $CI_COMMIT_BRANCH == \"main\""
	}, {
		if:   "$CI_COMMIT_BRANCH && $CI_OPEN_MERGE_REQUESTS"
		when: "never"
	}]
	stages: ["verify", "release"]
	variables: {
		DEBIAN_FRONTEND:                          "noninteractive"
		CODEX_RESPONSES_PROXY_RELEASE_TAG_REMOTE: "origin"
		UV_PYTHON_FLOOR_IMAGE:                    "ghcr.io/astral-sh/uv:0.12.5-python3.12-trixie-slim@sha256:4677e08839853fe91c523b593f822ec1e87c7b91ba4c6b30929016b2e0933cd5"
		UV_PYTHON_LATEST_IMAGE:                   "ghcr.io/astral-sh/uv:0.12.5-python3.14-trixie-slim@sha256:dc360d7e5f968c682e8b59e83027a315a0232dead15cb9dfe3e707a12ba390e1"
		UV_CACHE_DIR:                             "$CI_PROJECT_DIR/.cache/uv"
		UV_PYTHON_INSTALL_DIR:                    "$CI_PROJECT_DIR/.cache/uv/python"
		CODEX_RESPONSES_PROXY_CI_TARGET:          "linux-amd64"
	}
	default: {
		image: {
			name: "$UV_PYTHON_LATEST_IMAGE"
			docker: platform: "linux/amd64"
		}
		tags: ["$CODEX_RESPONSES_PROXY_GITLAB_LINUX_RUNNER_TAG"]
		cache: {
			key: "uv-$CODEX_RESPONSES_PROXY_CI_TARGET"
			paths: [".cache/uv/"]
		}
	}

	#productRules: [{
		if: "$CI_PIPELINE_SOURCE == \"merge_request_event\" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == \"dev\""
	}, {
		if: "$CI_COMMIT_BRANCH == \"dev\""
	}]
	#uvContract: """
		UV_REQUIREMENT="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["tool"]["uv"]["required-version"])')"
		UV_VERSION="$(uv --version)"
		UV_VERSION="${UV_VERSION#uv }"
		ACTUAL_UV_VERSION="${UV_VERSION%% *}"
		EXPECTED_UV_VERSION="${UV_REQUIREMENT#==}"
		if [ "$ACTUAL_UV_VERSION" != "$EXPECTED_UV_VERSION" ]; then
		  printf 'uv version mismatch: expected %s, actual %s\n' "$EXPECTED_UV_VERSION" "$ACTUAL_UV_VERSION" >&2
		  exit 1
		fi
		"""
	#systemBootstrap: [
		#uvContract,
		"apt-get update -qq",
		"apt-get install -qq -y --no-install-recommends git openssh-client",
	]
	#qualityBootstrap: list.Concat([#systemBootstrap, [
		"git fetch --tags --force --prune --prune-tags origin",
		"uv sync --locked --group quality --no-install-project --python python --no-python-downloads",
	]])

	"source-and-governance": {
		stage: "verify"
		rules: #productRules
		image: {
			name: #Toolchains.gitlabMiseImage
			entrypoint: [""]
		}
		variables: {
			GIT_DEPTH:        "0"
			MISE_ENABLE_TOOLS: #Toolchains.quality
		}
		before_script: [
			"mise install --locked",
			"git fetch --tags --force --prune --prune-tags origin",
			"mise exec --locked -- uv sync --locked --group quality --no-install-project --python python --no-python-downloads",
		]
		script: [
			"mise exec --locked -- uv run --locked --no-sync --python python --no-python-downloads python -m tools.quality.governance --online-links",
		]
	}
	"verify-python": {
		stage: "verify"
		rules: #productRules
		parallel: matrix: [{PYTHON_VERSION: #RuntimeMatrix.python}]
		variables: GIT_DEPTH: "0"
		before_script: list.Concat([#systemBootstrap, [
			"apt-get install -qq -y --no-install-recommends binutils",
			"git fetch --tags --force --prune --prune-tags origin",
			"uv sync --locked --group quality --no-install-project --python python --no-python-downloads",
			"uv python install --no-bin $PYTHON_VERSION",
		]])
		script: [
			"python --version",
			"uv run --locked --no-sync --python python --no-python-downloads nox -s \"tests-$PYTHON_VERSION\"",
		]
	}
	"verify-python-quality": {
		stage: "verify"
		rules: #productRules
		image: {
			name: "$UV_PYTHON_FLOOR_IMAGE"
			docker: platform: "linux/amd64"
		}
		variables: GIT_DEPTH: "0"
		before_script: list.Concat([#systemBootstrap, [
			"apt-get install -qq -y --no-install-recommends binutils",
			"git fetch --tags --force --prune --prune-tags origin",
		]])
		script: [
			"uv sync --locked --group quality --no-install-project --python python --no-python-downloads",
			"uv run --locked --no-sync --python python --no-python-downloads nox -s quality",
		]
	}
	"verify-accepted-source": {
		stage: "verify"
		rules: [{if: "$CI_COMMIT_BRANCH == \"dev\" || $CI_COMMIT_BRANCH == \"main\""}]
		variables: GIT_DEPTH: "0"
		before_script: #qualityBootstrap
		script: [
			"uv run --locked --no-sync --python python --no-python-downloads python tools/release/metadata.py",
			"uv run --locked --no-sync --python python --no-python-downloads python -m tools.quality.repository",
		]
	}
	"verify-promotion": {
		stage: "verify"
		rules: [{
			if: "$CI_PIPELINE_SOURCE == \"merge_request_event\" && $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME == \"dev\" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == \"main\""
		}]
		variables: GIT_DEPTH: "0"
		before_script: list.Concat([#systemBootstrap, [
			"git fetch origin main dev --tags --force --prune --prune-tags",
			"uv sync --locked --group quality --no-install-project --python python --no-python-downloads",
		]])
		script: [
			"git merge-base --is-ancestor origin/main \"$CI_COMMIT_SHA\"",
			"uv run --locked --no-sync --python python --no-python-downloads python tools/release/metadata.py",
			"uv run --locked --no-sync --python python --no-python-downloads python -m tools.quality.repository",
		]
	}
	"verify-release-tag": {
		stage: "release"
		rules: [{if: "$CI_COMMIT_TAG"}]
		variables: GIT_DEPTH: "0"
		before_script: list.Concat([#qualityBootstrap, [
			"test -f \"${CODEX_RESPONSES_PROXY_GITLAB_TAG_TRUST:-}\"",
		]])
		script: [
			"uv run --locked --no-sync --python python --no-python-downloads python tools/release/metadata.py --tag \"$CI_COMMIT_TAG\"",
			"uv run --locked --no-sync --python python --no-python-downloads python -m tools.forge.tag_signature . \"$CI_COMMIT_TAG\" \"$CODEX_RESPONSES_PROXY_GITLAB_TAG_TRUST\"",
		]
	}
}

githubVerify: {
	name: "Verify"
	on: {
		pull_request: branches: ["dev", "main"]
		push: {
			branches: ["dev", "main"]
			tags: ["v*"]
		}
	}
	permissions: contents: "read"
	env: {
		CODEX_RESPONSES_PROXY_RELEASE_TAG_REMOTE: "origin"
		GIT_CONFIG_COUNT:                         "1"
		GIT_CONFIG_KEY_0:                         "init.defaultBranch"
		GIT_CONFIG_VALUE_0:                       "main"
	}
	concurrency: {
		group:                "verify-${{ github.workflow }}-${{ github.ref }}"
		"cancel-in-progress": true
	}
	jobs: {
		"python-matrix": {
			name:              "Resolve supported Python versions"
			if:                #Conditions.nativeProof
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 5
			outputs: {
				versions:              "${{ steps.versions.outputs.value }}"
				floor:                 "${{ steps.versions.outputs.floor }}"
				latest:                "${{ steps.versions.outputs.latest }}"
				release:               "${{ steps.versions.outputs.release }}"
				"linux-release-image": "${{ steps.versions.outputs.linux-release-image }}"
			}
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				name: "Install the locked matrix tool environment"
				run:  "uv sync --locked --all-groups"
			}, {
				name: "Read the repository Python matrix"
				id:   "versions"
				run:  "uv run --locked --no-sync python -m tools.quality.python_matrix"
			}]
		}
		"source-and-governance": {
			name:              "Source and governance"
			if:                #Conditions.productProof
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 10
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           #Conditions.productSHA
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
				with: "python-version-file": ".python-release"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d"
			}, {
				uses: #Toolchains.githubMiseAction
				with: {
					install:     true
					cache:       true
					tool_config: "mise.toml"
				}
			}, {
				name: "Confirm source identity and repository governance"
				run: """
					uv sync --locked --all-groups
					uv run --locked --no-sync python -m tools.quality.governance --online-links
					"""
			}]
		}
		python: {
			name:              "Python ${{ matrix.python-version }}"
			if:                #Conditions.productProof
			needs:             "python-matrix"
			"runs-on":         "macos-26"
			"timeout-minutes": 15
			strategy: {
				"fail-fast": false
				matrix: "python-version": "${{ fromJSON(needs.python-matrix.outputs.versions) }}"
			}
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           #Conditions.productSHA
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version": "${{ matrix.python-version }}"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
				with: "cache-suffix": "${{ matrix.python-version }}"
			}, {
				name: "Compile and test"
				run:  "uv run --locked --group quality nox -s \"tests-${{ matrix.python-version }}\""
			}]
		}
		"python-windows": {
			name:              "Python ${{ matrix.python-version }} (Windows)"
			if:                #Conditions.productProof
			needs:             "python-matrix"
			"runs-on":         "windows-2025"
			"timeout-minutes": 15
			strategy: {
				"fail-fast": false
				matrix: "python-version": "${{ fromJSON(needs.python-matrix.outputs.versions) }}"
			}
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           #Conditions.productSHA
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version": "${{ matrix.python-version }}"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
				with: "cache-suffix": "${{ matrix.python-version }}"
			}, {
				name: "Compile and test"
				run:  "uv run --locked --group quality nox -s \"tests-${{ matrix.python-version }}\""
			}]
		}
		"accepted-source": {
			name:              "Accepted source"
			if:                "github.event_name == 'push' && github.ref_type == 'branch'"
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 10
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version-file": ".python-release"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				name: "Confirm accepted source and metadata"
				run: """
					uv sync --locked --all-groups
					uv run --locked --no-sync python tools/release/metadata.py
					uv run --locked --no-sync python -m tools.quality.repository

					"""
			}]
		}
		promotion: {
			name:              "Promote dev to main"
			if:                "github.event_name == 'pull_request' && github.base_ref == 'main' && github.head_ref == 'dev'"
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 10
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           "${{ github.event.pull_request.head.sha }}"
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
				with: "python-version-file": ".python-release"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d"
			}, {
				name: "Prove exact dev-to-main promotion"
				run: """
					git fetch origin main dev --tags --force --prune --prune-tags
					git merge-base --is-ancestor origin/main "${{ github.event.pull_request.head.sha }}"
					uv sync --locked --all-groups
					uv run --locked --no-sync python tools/release/metadata.py
					uv run --locked --no-sync python -m tools.quality.repository
					"""
			}]
		}
		"tag-metadata": {
			name:              "Tag metadata and governance"
			if:                "github.ref_type == 'tag'"
			needs:             "python-matrix"
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 15
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version": "${{ needs.python-matrix.outputs.latest }}"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				name: "Install the complete locked tool environment"
				run:  "uv sync --locked --all-groups"
			}, {
				name: "Fetch the exact annotated tag object"
				run:  "uv run --locked --no-sync python -m tools.release.publish prepare-checkout --tag \"$GITHUB_REF_NAME\" --commit-oid \"$GITHUB_SHA\""
			}, {
				name: "Verify exact release metadata"
				run:  "uv run --locked --no-sync python tools/release/metadata.py --tag \"$GITHUB_REF_NAME\""
			}, {
				name: "Verify repository governance"
				run:  "uv run --locked --no-sync python -m pytest -q tests/quality/test_contract.py tests/forge/test_workflow_contracts.py tests/forge/test_tagging.py tests/release/test_publish.py tests/release/test_publish_gitlab.py"
			}]
		}
		"python-quality": {
			name:              "Python quality"
			if:                #Conditions.productProof
			needs:             "python-matrix"
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 15
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           #Conditions.productSHA
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version": "${{ needs.python-matrix.outputs.floor }}"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				uses: #Toolchains.githubMiseAction
				with: {
					install:     true
					cache:       true
					tool_config: "mise.toml"
				}
			}, {
				name: "Verify lint, format, types, structure, docstrings, and product branch coverage"
				run:  "uv run --locked --group quality nox -s quality"
			}]
		}
		"native-assets": {
			name:              "Native asset (${{ matrix.platform }})"
			if:                #Conditions.nativeProof
			needs:             "python-matrix"
			"runs-on":         "${{ matrix.runner }}"
			"timeout-minutes": 20
			strategy: {
				"fail-fast": false
				matrix: include: [{
					platform: "macos-arm64"
					runner:   "macos-26"
				}, {
					platform: "windows-x86_64"
					runner:   "windows-2025"
				}]
			}
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           #Conditions.productSHA
				}
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version": "${{ needs.python-matrix.outputs.release }}"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				name: "Install the locked release tool environment"
				run:  "uv sync --locked --only-group quality"
			}, {
				name: "Build and accept the native release asset"
				run:  "uv run --locked --no-sync nox -s release -- \"${{ runner.temp }}/native-assets\""
			}, {
				uses: "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" // v7.0.1
				with: {
					name:                "native-${{ matrix.platform }}"
					path:                "${{ runner.temp }}/native-assets"
					"if-no-files-found": "error"
					"retention-days":    7
				}
			}]
		}
		"native-linux": {
			name:              "Native asset (linux-x86_64)"
			if:                #Conditions.nativeProof
			needs:             "python-matrix"
			"runs-on":         "ubuntu-24.04"
			container:         "${{ needs.python-matrix.outputs.linux-release-image }}"
			"timeout-minutes": 20
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
				with: {
					"fetch-depth": 0
					"fetch-tags":  true
					ref:           #Conditions.productSHA
				}
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				name: "Materialize the canonical release source root"
				run:  "install -d /workspace && git -c safe.directory=\"$GITHUB_WORKSPACE\" archive --format=tar HEAD | tar -xf - -C /workspace"
			}, {
				name: "Install the locked release tool environment"
				run:  "cd /workspace && uv sync --locked --only-group quality --python python --no-python-downloads"
			}, {
				name: "Build and accept the native release asset"
				run:  "cd /workspace && uv run --locked --no-sync --python python --no-python-downloads nox -s release -- \"$GITHUB_WORKSPACE/.release-assets/linux-x86_64\""
			}, {
				uses: "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" // v7.0.1
				with: {
					name:                "native-linux-x86_64"
					path:                "${{ github.workspace }}/.release-assets/linux-x86_64"
					"if-no-files-found": "error"
					"retention-days":    7
				}
			}]
		}
		"release-assets": {
			name: "Release assets"
			if:   "github.ref_type == 'tag'"
			needs: ["python-matrix", "native-assets", "native-linux"]
			"runs-on":         "ubuntu-24.04"
			"timeout-minutes": 10
			steps: [{
				uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" // v7.0.1
			}, {
				uses: "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" // v7.0.0
				with: "python-version": "${{ needs.python-matrix.outputs.latest }}"
			}, {
				uses: "astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d" // v10.0.1
			}, {
				name: "Download native release assets"
				env: GH_TOKEN: "${{ github.token }}"
				run: "gh run download \"$GITHUB_RUN_ID\" --pattern 'native-*' --dir \"$RUNNER_TEMP/native\""
			}, {
				name: "Install the complete locked tool environment"
				run:  "uv sync --locked --all-groups"
			}, {
				name: "Materialize the protected release signing key"
				env: RELEASE_ASSET_SIGNING_KEY_TEXT: "${{ secrets.CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY }}"
				run: """
					install -m 600 /dev/null "$RUNNER_TEMP/release-asset-signing-key"
					printf '%s\\n' "$RELEASE_ASSET_SIGNING_KEY_TEXT" > "$RUNNER_TEMP/release-asset-signing-key"

					"""
			}, {
				name: "Assemble, sign, and verify the release set"
				env: {
					RELEASE_ASSET_SIGNING_KEY_PATH: "${{ runner.temp }}/release-asset-signing-key"
					RELEASE_ASSET_TRUST:            "${{ secrets.CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST }}"
				}
				run: "uv run --locked --no-sync python -m tools.release.assemble_assets --input \"$RUNNER_TEMP/native/native-linux-x86_64\" --input \"$RUNNER_TEMP/native/native-macos-arm64\" --input \"$RUNNER_TEMP/native/native-windows-x86_64\" --output \"$RUNNER_TEMP/release-assets\" --sign"
			}, {
				uses: "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" // v7.0.1
				with: {
					name:                "release-assets"
					path:                "${{ runner.temp }}/release-assets"
					"if-no-files-found": "error"
					"retention-days":    7
				}
			}]
		}
	}
}
