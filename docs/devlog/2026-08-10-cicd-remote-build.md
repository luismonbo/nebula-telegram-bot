# CI/CD deploy switched to Oryx remote build

**Related:** [2026-08-09-cicd-pipeline.md](2026-08-09-cicd-pipeline.md)

## Problem

The Actions workflow went green but the app kept serving stale/broken content. The
deploy step log showed `remote-build: false` / `enable-oryx-build: false` /
`scm-do-build-during-deployment: false`, and the workflow was building deps with
`pip install --target .python_packages/lib/site-packages` on a generic
`ubuntu-latest` runner. Transport was fine — `Azure/functions-action` correctly
detected Linux Consumption and used `WEBSITE_RUN_FROM_PACKAGE` + SAS blob — so the
failure was package *content*, not delivery.

## Verified Azure facts (some assumptions were wrong)

- Resource group is `telegram-bot-dev`, not `telegram-bot-devs`.
- Plan is `Y1` / `Dynamic`, `kind: functionapp,linux`, `Python|3.10` → **Linux Consumption**.
- SCM basic publishing credentials are **disabled** (`allow: false`).
- CI service principal has **Website Contributor** scoped to the site; local dev is Owner.
- `ffmpeg` / `ffprobe` are tracked as mode `100755`, so a checkout already has the exec bit.

## Decision

Keep `Azure/functions-action@v1` (the transport was never the problem) and hand the
build to Kudu/Oryx with `scm-do-build-during-deployment: true` + `enable-oryx-build: true`.
Both are required together; either alone is a no-op.

`remote-build` is deliberately **not** set. Per the Azure Functions docs support matrix
it applies only to **Flex Consumption** — on Consumption/Elastic Premium/Dedicated it is
listed as not applicable. This app is Y1 Consumption, so the correct knobs are the
`scm-do-build-during-deployment` + `enable-oryx-build` pair.

### Rejected: Core Tools in CI

First attempt replicated `deploy-function.ps1` by installing Core Tools and running
`func azure functionapp publish --build remote`. Abandoned:

- `npm install -g azure-functions-core-tools@4` fails — its post-install fetches
  `cdn.functions.azure.com/.../Azure.Functions.Cli.linux-x64.4.13.2.zip` and gets **404**;
  the npm package points at a CLI build newer than any published release (latest GitHub
  release is 4.12.1).
- The Microsoft apt feed has **no** `azure-functions-core-tools-4` package for noble or
  jammy (checked both `binary-amd64/Packages` indexes directly).
- The remaining option was a pinned 553 MB GitHub release zip per run — far more moving
  parts than two action inputs, for the same Oryx build.

## Changes to `.github/workflows/deploy.yml`

- Merged `build` + `deploy` into one job — Oryx builds from source, so there is no
  prebuilt package to pass between jobs.
- Dropped `pip install --target .python_packages/...` (this was the root cause).
- Dropped the `upload-artifact`/`download-artifact` round-trip, which stripped the
  executable bit, and the `chmod +x` band-aid that compensated for it.
- Added `scm-do-build-during-deployment: true` + `enable-oryx-build: true`.
- `package: '.'` with `respect-funcignore: true` (deploys the checkout directly).
- Added `--no-emit-project` to `uv export` (verified: emits no `-e .` self-reference).

## Open / watch on next run

- Oryx build runs on the SCM/Kudu site, and SCM basic auth is disabled here, so the
  action must authenticate with its RBAC bearer token. If the deploy fails on SCM
  access, the **Website Contributor** role on the CI principal is the first thing to
  check — local publish works as Owner, so local testing cannot surface this.
- Note the docs' OIDC migration section says to *remove* `scm-do-build-during-deployment`
  and `enable-oryx-build`; that guidance assumes the workflow does the build itself
  (the `pip install --target` path), which is exactly what failed for us. The parameter
  support matrix is the authority here.
- `uv export` emits `pytest` and `python-dotenv` because they sit in `[project].dependencies`
  rather than a dev group. Harmless bloat, but they ship to production — worth moving to
  `[dependency-groups]` later (relates to docs/issues/15).
- `deploy-function.ps1` stays as the manual fallback.
