# CI/CD deploy switched to Core Tools remote build

**Related:** [2026-08-09-cicd-pipeline.md](2026-08-09-cicd-pipeline.md)

## Problem

The Actions workflow went green but the app kept serving stale/broken content. Deploy
step log showed `remote-build: false` / `enable-oryx-build: false`, and the workflow
was hand-building deps with `pip install --target .python_packages/lib/site-packages`
on a generic `ubuntu-latest` runner. Transport was fine — `Azure/functions-action`
correctly detected Linux Consumption and used `WEBSITE_RUN_FROM_PACKAGE` + SAS blob —
so the failure was package *content*, not delivery.

## Verified Azure facts (were partly wrong in our assumptions)

- Resource group is `telegram-bot-dev`, not `telegram-bot-devs`.
- Plan is `Y1` / `Dynamic`, `kind: functionapp,linux`, `Python|3.10` → **Linux Consumption**.
- SCM basic publishing credentials are **disabled** (`allow: false`).
- CI service principal has **Website Contributor** scoped to the site; local dev is Owner.
- `ffmpeg` / `ffprobe` are tracked as mode `100755`, so a checkout already has the exec bit.

## Decision

Replicate `deploy-function.ps1` in CI: install Azure Functions Core Tools and run
`func azure functionapp publish --build remote`, letting Oryx install dependencies
inside the real Azure Functions Python image. This is the mechanism already proven
against this app.

## Changes to `.github/workflows/deploy.yml`

- Merged `build` + `deploy` into one job — a remote build ships source, so there is no
  pre-built package to pass between jobs.
- Dropped `pip install --target .python_packages/...` (incompatible with remote build).
- Dropped the `upload-artifact`/`download-artifact` round-trip, which was stripping the
  executable bit, and the `chmod +x` band-aid that compensated for it.
- Replaced `Azure/functions-action@v1` with Core Tools `func azure functionapp publish`.
- Added `AZURE_RESOURCE_GROUP: telegram-bot-dev`.
- Added `--no-emit-project` to `uv export` (verified: emits no `-e .` self-reference).
- **New step: synthesize a placeholder `local.settings.json`.** It is gitignored, so a CI
  checkout has none, and Core Tools reads `FUNCTIONS_WORKER_RUNTIME` from it to detect a
  Python project. `.funcignore` keeps it out of the package. We deliberately do *not*
  pass `--publish-local-settings` / `-i`, which would overwrite real app settings
  (`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, …) with the placeholders.

## Open / watch on next run

- Local publish works as **Owner**; CI is **Website Contributor**. If the publish fails on
  SCM/Kudu access (basic auth is disabled, so Core Tools must use its AAD token path),
  that role is the first thing to check.
- `uv export` emits `pytest` and `python-dotenv` because they sit in `[project].dependencies`
  rather than a dev group. Harmless bloat, but they ship to production — worth moving to
  `[dependency-groups]` later (relates to docs/issues/15).
- `deploy-function.ps1` stays as the manual fallback.
