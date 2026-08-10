# CI/CD deploy switched to Core Tools remote build

**Related:** [2026-08-09-cicd-pipeline.md](2026-08-09-cicd-pipeline.md)

## Problem

The Actions workflow went green but the app never ran the deployed code. The deploy
step log showed `remote-build: false` / `enable-oryx-build: false` /
`scm-do-build-during-deployment: false`, and the workflow built deps with
`pip install --target .python_packages/lib/site-packages` on a generic
`ubuntu-latest` runner rather than in the Azure Functions Python image.

## Verified Azure facts (some assumptions were wrong)

- Resource group is `telegram-bot-dev`, not `telegram-bot-devs`.
- Plan is `Y1` / `Dynamic`, `kind: functionapp,linux`, `Python|3.10` → **Linux Consumption**.
- SCM basic publishing credentials are **disabled** (`allow: false`).
- CI service principal has **Website Contributor** scoped to the site; local dev is Owner.
- `ffmpeg` / `ffprobe` are tracked as mode `100755`, so a checkout already has the exec bit.

## Key finding: the action cannot remote-build on this plan

`Azure/functions-action@v1` accepts `scm-do-build-during-deployment` and
`enable-oryx-build` on Consumption per the docs support matrix, but **silently ignores
them when authenticating with RBAC/OIDC on Linux Consumption**. It hard-routes to the
`WEBSITE_RUN_FROM_PACKAGE` blob path ("Will use WEBSITE_RUN_FROM_PACKAGE ... since RBAC
is detected"), which has no Kudu build step.

Proof after that run: `WEBSITE_RUN_FROM_PACKAGE` was set to a SAS blob URL, while
`SCM_DO_BUILD_DURING_DEPLOYMENT` and `ENABLE_ORYX_BUILD` were never written to app
settings at all — and `az functionapp function list` returned `[]`. Shipping source
with no dependencies means the Python worker cannot import `function_app.py`, so no
decorators run and **zero functions register while the deploy still reports success**.

`remote-build` is not an option either: per the docs matrix it applies only to Flex
Consumption, not Consumption/Elastic Premium/Dedicated.

## Decision

Replicate `deploy-function.ps1` in CI — `func azure functionapp publish --build remote` —
since that is the only mechanism proven to work on this app.

Core Tools is installed from the **pinned GitHub release zip**, not npm:

- `npm install -g azure-functions-core-tools@4` fails; its post-install fetches
  `cdn.functions.azure.com/.../Azure.Functions.Cli.linux-x64.4.13.2.zip` → **404**. The
  npm package points at a CLI build newer than any published release (latest is 4.12.1).
- The Microsoft apt feed has **no** `azure-functions-core-tools-4` package for noble or
  jammy (checked both `binary-amd64/Packages` indexes directly).
- The zip is ~553 MB (no `min` variant exists for linux-x64), so it is cached by version.

## Changes to `.github/workflows/deploy.yml`

- Merged `build` + `deploy` into one job — a remote build ships source, so there is no
  prebuilt package to pass between jobs.
- Dropped `pip install --target .python_packages/...` and the
  `upload-artifact`/`download-artifact` round-trip (which stripped the exec bit) plus
  its compensating `chmod`.
- Install Core Tools from the pinned GitHub release, cached on `FUNC_CLI_VERSION`.
- Synthesize a placeholder `local.settings.json`: it is gitignored, so CI has no copy,
  and Core Tools reads `FUNCTIONS_WORKER_RUNTIME` from it to detect Python. `.funcignore`
  keeps it out of the package, and `--publish-local-settings` is deliberately not passed
  so real app settings are never overwritten.
- Added `--no-emit-project` to `uv export` (verified: emits no `-e .` self-reference).
- **Added a post-deploy verification step** that polls `az functionapp function list` and
  fails the run if zero functions register. A green deploy is not evidence of a working
  app — that gap is what hid this bug through three runs.

## Open / watch on next run

- Core Tools must reach the SCM/Kudu site for the remote build, and SCM basic auth is
  disabled, so it has to use its AAD token path. If the publish fails on SCM access, the
  **Website Contributor** role on the CI principal is the first thing to check — local
  publish works as Owner, so local testing cannot surface this.
- A stale `WEBSITE_RUN_FROM_PACKAGE` is currently set from the failed action run. Core
  Tools removed it on previous manual publishes, so it is expected to clear itself; if
  the app still serves stale content, delete that app setting and republish.
- `uv export` emits `pytest` and `python-dotenv` because they sit in `[project].dependencies`
  rather than a dev group. Harmless bloat, but they ship to production — worth moving to
  `[dependency-groups]` later (relates to docs/issues/15).
- `deploy-function.ps1` stays as the manual fallback, and is currently the way to restore
  service after a bad deploy.
