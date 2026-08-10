# CI/CD deploy: why remote build is impossible on this plan

**Related:** [2026-08-09-cicd-pipeline.md](2026-08-09-cicd-pipeline.md)

## Verified Azure facts (some assumptions were wrong)

- Resource group is `telegram-bot-dev`, not `telegram-bot-devs`.
- Plan is `Y1` / `Dynamic`, `kind: functionapp,linux`, `Python|3.10` → **Linux Consumption**.
- SCM basic publishing credentials are **disabled** (`allow: false`).
- CI service principal has **Website Contributor** scoped to the site; local dev is Owner.
- `ffmpeg` / `ffprobe` are tracked as mode `100755`, so a checkout already has the exec bit.

## Key finding

Per the Azure Functions GitHub Actions docs, deployment method by plan:

| Hosting plan | Deployment method |
| --- | --- |
| Flex Consumption | One deploy |
| Elastic Premium / Dedicated | Zip deploy |
| **Consumption** | Windows: Zip deploy · **Linux: external package URL** |

Linux Consumption deploys via **external package URL** (`WEBSITE_RUN_FROM_PACKAGE` +
SAS blob). That path has **no Kudu build step**, so `remote-build`,
`scm-do-build-during-deployment`, and `enable-oryx-build` cannot apply. The parameter
matrix lists the latter two as "Optional" for Consumption, but that covers the
Windows/zip-deploy case — on Linux they are silently ignored.

Proof: after a run with both set to `true`, `WEBSITE_RUN_FROM_PACKAGE` held a SAS blob
URL while `SCM_DO_BUILD_DURING_DEPLOYMENT` and `ENABLE_ORYX_BUILD` were never written to
app settings at all, and `az functionapp function list` returned `[]`.

**Therefore the build must happen in the workflow.** Removing
`pip install --target .python_packages/lib/site-packages` ships source with no
dependencies; the Python worker cannot import `function_app.py`, no decorators run, and
the app registers **zero functions while the deploy still reports success**.

## Decision

Use the documented approach: build in the workflow with `pip install --target`, deploy
with `Azure/functions-action@v1`. Deviations from the doc template, both deliberate:

- **Single job.** The template's build/deploy split hands the tree over via
  `upload-artifact`/`download-artifact`, which strips the executable bit off
  `ffmpeg`/`ffprobe` and needs a compensating `chmod`. One job avoids it entirely.
- **No artifact step at all**, which sidesteps a real bug in the doc's Python template:
  it omits `include-hidden-files: true`, and `.python_packages` is a *hidden* directory,
  so copied verbatim `upload-artifact@v4+` silently drops every dependency.

Also added a post-deploy step that polls `az functionapp function list` and fails the run
if nothing registers. A green deploy is not evidence of a working app — that gap hid this
across three runs.

### Rejected: Core Tools in CI

Replicating `deploy-function.ps1` (`func azure functionapp publish --build remote`) works
locally but is off the supported CI path, and installing Core Tools on the runner is hostile:

- `npm install -g azure-functions-core-tools@4` fails — its post-install fetches
  `cdn.functions.azure.com/.../Azure.Functions.Cli.linux-x64.4.13.2.zip` → **404**; the npm
  package points at a CLI build newer than any published release (latest is 4.12.1).
- The Microsoft apt feed has **no** `azure-functions-core-tools-4` package for noble or
  jammy (checked both `binary-amd64/Packages` indexes directly).
- The remaining option was a pinned ~553 MB GitHub release zip per run (no `min` variant
  exists for linux-x64).

## Open

- **Linux Consumption is planned for retirement** (flagged in the deployment-method table).
  Migrating to **Flex Consumption** would make `remote-build: true` work properly and is the
  real strategic fix — worth planning rather than deferring.
- A stale `WEBSITE_RUN_FROM_PACKAGE` may still be set from the failed run. Core Tools clears
  it on manual publishes; if the app serves stale content, delete that setting and republish.
- `uv export` emits `pytest` and `python-dotenv` because they sit in `[project].dependencies`
  rather than a dev group. Harmless bloat, but they ship to production — worth moving to
  `[dependency-groups]` later (relates to docs/issues/15).
- `deploy-function.ps1` stays as the manual fallback, and is the way to restore service
  after a bad deploy.
